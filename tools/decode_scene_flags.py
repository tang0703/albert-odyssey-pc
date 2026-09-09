"""Replay the verified MAP001 block-3 reader; flag gameplay meanings stay unknown."""
import json
import struct
from collections import Counter

from pipeline import PROJECT, WORKSPACE, digest, read_json, verify_source, write_json
from decode_map_graphics import map001_blocks
from probe_scene_metadata import system_ram

OPERATIONS = [('or', 0x80), ('or', 0x40), ('or', 0x20), ('or', 0x10),
              ('skip', 0x08), ('skip', 0x04), ('and', 0xfd), ('and', 0xfe)]
# Bounds exported with Ghidra from the pinned zero-based TWN.BIN. Guard the
# whole reader (including branches), helper literals, and the reset call site.
CODE_RANGES = [
    (0x1e34e, 0x1e52c, 'b5eb346378ffd583d89d7a64761ac5f272528da2cabd4552cfe102f98435e368'),
    (0x1e55e, 0x1e564, '721ebe7873547b86eedcc68bba6247377acdaa0a7ec95f1eeb0b2400b5eeb79f'),
    (0x1e62, 0x1e6a, '421ff6fa16b4931909aa6d665abd29329dfeb890a567ced7c97dc29bc40783c4'),
    (0x1f6c, 0x1f74, 'e8c078fa79a9e9ed599ad0a47f454b6ef1d658347bdc70636aba3465d038b7bd'),
]


def verify_reader(code: bytes) -> list[dict]:
    for start, end, expected in CODE_RANGES:
        if len(code) < end or digest(code[start:end]) != expected:
            raise ValueError(f'Scene flag reader changed at {start:#x}')
    return [{'start': s, 'end_exclusive': e, 'sha256': h} for s, e, h in CODE_RANGES]


def decode_flags(payload: bytes) -> tuple[bytes, list[dict]]:
    """Eight counted groups, four bytes per record. Zero counts are real groups.

    Helpers address bytes linearly as y*256+x; deliberately do not clamp or wrap
    rectangles at row edges. Writes beyond the verified 64 KiB buffer fail.
    Groups 4/5 consume records without writing, matching helper 0x1e51a.
    """
    grid = bytearray([3]) * 65536
    pos, groups = 0, []
    for index, (operation, mask) in enumerate(OPERATIONS):
        if pos + 2 > len(payload):
            raise ValueError('Missing group count')
        count = struct.unpack_from('>H', payload, pos)[0]
        start, pos = pos, pos + 2
        end = pos + count * 4
        if end > len(payload):
            raise ValueError('Truncated group records')
        writes = 0
        for offset in range(pos, end, 4):
            x, y, width, height = payload[offset:offset + 4]
            if operation == 'skip' or width == 0 or height == 0:
                continue
            if (y + height - 1) * 256 + x + width > len(grid):
                raise ValueError('Record writes outside verified flag buffer')
            for row in range(height):
                begin = (y + row) * 256 + x
                for address in range(begin, begin + width):
                    grid[address] = (grid[address] | mask if operation == 'or'
                                     else grid[address] & mask)
                    writes += 1
        groups.append({'index': index, 'offset': start, 'count': count,
                       'operation': operation, 'mask': mask, 'byte_writes': writes})
        pos = end
    if pos != len(payload):
        raise ValueError('Unexpected data after eight groups')
    return bytes(grid), groups


def run() -> dict:
    sources = read_json(PROJECT / 'source-lock.json')['sources']
    path = 'work/extract/MAP001.TWN'
    raw = verify_source(WORKSPACE, path, sources[path])
    code = verify_source(WORKSPACE, 'work/extract/TWN.BIN', sources['work/extract/TWN.BIN'])
    evidence = verify_reader(code)
    block = map001_blocks(raw)[2]
    payload = raw[block['payload_offset']:block['payload_offset'] + block['size']]
    grid, groups = decode_flags(payload)
    lock = read_json(PROJECT / 'savestate-lock.json')
    state = verify_source(WORKSPACE, lock['path'], lock['sha256'])
    low, high, _ = system_ram(state, lock)
    if high[0xf4000:0xf4000 + len(payload)] != payload:
        raise ValueError('Block-3 placement changed')
    reference = low[0x10000:0x20000]
    differences = sum(a != b for a, b in zip(grid, reference))
    if differences:
        raise ValueError(f'Flag buffer differs at {differences} bytes')
    report = {'schema': 'ao_pc_scene_flags_v1', 'source_sha256': digest(raw),
              'code_sha256': digest(code), 'snapshot_sha256': digest(state),
              'block': block, 'reader_runtime': 0x060ae34e,
              'block_reader_address': 0x260f4000, 'buffer_writer_address': 0x20210000,
              'reference_low_ram_offset': 0x10000, 'width': 256, 'height': 256,
              'initial_value': 3, 'groups': groups, 'code_ranges': evidence,
              'decoded_sha256': digest(grid), 'reference_sha256': digest(reference),
              'exact_match_bytes': len(grid), 'different_bytes': differences,
              'value_counts': {str(k): v for k, v in sorted(Counter(grid).items())},
              'collision_verified': False, 'player_coordinate_verified': False,
              'limits': ['Buffer construction verified against one snapshot only.',
                         'Flag meanings, movement consumers and world-coordinate scale remain unknown.',
                         'Groups 4 and 5 are skipped by this reader; other consumers are not excluded.']}
    output = PROJECT / 'reports/scene-flags'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'flags.bin').write_bytes(grid)
    write_json(PROJECT / 'reports/scene-flags.json', report)
    return report


if __name__ == '__main__':
    r = run()
    print(json.dumps({k: r[k] for k in ['exact_match_bytes', 'different_bytes', 'decoded_sha256']}, indent=2))
