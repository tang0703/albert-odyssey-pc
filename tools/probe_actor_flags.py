"""Bounded static reconstruction of two actor flag consumers, not a movement engine."""
import json
import struct
from collections import Counter

from pipeline import PROJECT, WORKSPACE, digest, read_json, verify_source, write_json
from decode_scene_flags import decode_flags
from decode_map_graphics import map001_blocks

RANGES = [
    (0x1bf18, 0x1bfc8, '1ad6cff303efdcca46bbf11d08daf79181b0e11ef8a07f81b91af6fc57b0cee3'),
    (0x1c054, 0x1c05c, 'f50ba9c38002d5ff06aea6c7bd03ca3fcca012edfc5dd1070f36ba2fe9a22690'),
    (0x1b61a, 0x1b670, '330bc0dc78d4e39c2d0362f845d5b91b9921b97637d5fff4dec1615c1f272fd1'),
    (0x1b714, 0x1b780, 'db04cfee55e85eb00fa6d12c9c955a0e3794d4c48e8de46b95adaec80ed0245a'),
    (0x1b7a6, 0x1b7be, '661b8dc707c27ffe6d15551dada09d0b201768740bc9cf446bba4833414ca286'),
    (0xe66e, 0xe67a, 'ceaf30703b48b6029ed9ec25c6fd11ea3f6207f272f6ebc4b2c696f23fb8e2e8'),
    (0xe6d4, 0xe6dc, '24131439e32b59f6f1b0d7da932a9f256810e4baa6179fda3ce075e943695b7a'),
]


def verify_code(code: bytes) -> None:
    for start, end, expected in RANGES:
        if len(code) < end or digest(code[start:end]) != expected:
            raise ValueError(f'Actor reader code changed at {start:#x}')


def cell_index(x_word: int, y_word: int) -> int:
    """SH-2 signed word >>4, mask 0x7ff, >>3. Return linear 256x256 index.

    Masking makes either signed/unsigned 16-bit representation equivalent here.
    Do not apply this wrap rule to the PC world's unverified movement boundary.
    """
    if not 0 <= x_word <= 0xffff or not 0 <= y_word <= 0xffff:
        raise ValueError('Expected raw unsigned 16-bit coordinate words')
    return (((y_word >> 4) & 0x7ff) >> 3) * 256 + (((x_word >> 4) & 0x7ff) >> 3)


def update_actor(actor: bytes, flags: bytes) -> tuple[bytes, dict]:
    """Replay 1BF70 then 1BF18, the order confirmed at E66E/E674.

    Input is an opaque actor prefix; offsets are verified but actor identity is
    unknown. This path advances position without resolving collision itself.
    """
    if len(actor) < 0x1c or len(flags) != 65536:
        raise ValueError('Expected actor prefix >=28 bytes and 64 KiB flags')
    result = bytearray(actor)
    word = lambda offset: struct.unpack_from('>H', result, offset)[0]
    for position, delta in [(0, 0x18), (2, 0x1a)]:
        struct.pack_into('>H', result, position, (word(position) + word(delta)) & 0xffff)
    index = cell_index(word(0), word(2))
    flag = flags[index]
    # 1BF70: copy table bit 5 into actor word +8 bit 1, preserving other bits.
    struct.pack_into('>H', result, 8, (word(8) & 0xfffd) | (2 if flag & 0x20 else 0))
    mode_updated = bool(word(0x16) & 0x10)
    # 1BF18: conditional replacement of the complete low byte, not merely bit 0.
    if mode_updated:
        struct.pack_into('>H', result, 0x16, (word(0x16) & 0xff00) | (0x13 if flag & 0x20 else 0x12))
    return bytes(result), {'index': index, 'cell_x': index % 256, 'cell_y': index // 256,
                           'flag': flag, 'mode_updated': mode_updated}


def run() -> dict:
    sources = read_json(PROJECT / 'source-lock.json')['sources']
    code = verify_source(WORKSPACE, 'work/extract/TWN.BIN', sources['work/extract/TWN.BIN'])
    verify_code(code)
    path = 'work/extract/MAP001.TWN'
    raw = verify_source(WORKSPACE, path, sources[path])
    block = map001_blocks(raw)[2]
    flags, _ = decode_flags(raw[block['payload_offset']:block['payload_offset'] + block['size']])
    counts = Counter()
    # Synthetic actor probes at every source cell; NOT captured player states.
    for index in range(65536):
        actor = bytearray(28)
        struct.pack_into('>HH', actor, 0, (index % 256) * 128, (index // 256) * 128)
        struct.pack_into('>H', actor, 0x16, 0x10)
        updated, sample = update_actor(actor, flags)
        if sample['index'] != index:
            raise ValueError('Source cell addressing failed')
        counts[str(struct.unpack_from('>H', updated, 0x16)[0])] += 1
    report = {'schema': 'ao_pc_actor_flag_probe_v1', 'source_sha256': digest(raw),
              'code_sha256': digest(code), 'flags_sha256': digest(flags),
              'code_ranges': [{'start': s, 'end_exclusive': e, 'sha256': h} for s, e, h in RANGES],
              'coordinate_fraction_bits': 4, 'pixel_index_mask': 0x7ff, 'cell_pixel_shift': 3,
              'coordinate_offsets': [0, 2], 'delta_offsets': [0x18, 0x1a],
              'source_flag_mask': 0x20, 'actor_flag_offset': 8, 'actor_flag_mask': 2,
              'mode_offset': 0x16, 'mode_low_bytes': [0x12, 0x13],
              'synthetic_probe_count': 65536, 'synthetic_mode_counts': dict(sorted(counts.items())),
              'positive_x_correction_evidence': {'routine': 0x1b61a, 'selector_offset': 0xa,
                  'zero_selector_mask': 0x80, 'nonzero_selector_mask': 0x40,
                  'contact_byte_offset': 0x4b, 'contact_mask': 8,
                  'status_word_offset': 6, 'status_mask': 0x200},
              'collision_verified': False, 'player_identity_verified': False,
              'limits': ['Static reconstruction and synthetic inputs; no new emulator movement trace.',
                         'Positive-X correction path identified, not fully ported or tested.',
                         'Actor identity, selector meaning, shape offsets and full axis handling remain unknown.',
                         'Table bit 0x20 updates actor state; it is not a universal blocking flag.']}
    write_json(PROJECT / 'reports/actor-flags.json', report)
    return report


if __name__ == '__main__':
    result = run()
    print(json.dumps({k: result[k] for k in ['synthetic_probe_count', 'synthetic_mode_counts']}, indent=2))
