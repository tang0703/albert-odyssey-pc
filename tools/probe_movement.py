"""Static replay of TWN.BIN+1B61A, not a verified player movement engine.

This bounded probe accepts the actor bytes *at the function entry*. Input,
speed, actor-to-actor collision and deferred slide processing live in callers
and are deliberately not replaced with invented rules. No emulator fixture is
needed for synthetic tests. Real captures must still establish reachability.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
TWN_HASH = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
CORE_HASH = '95054f9128b7ab47f88c6659b103e7bee9db94c13548f815bbda5999b30da2ff'
TWN_RANGES = (
    (0x1b61a, 0x1bb24, '669a3f00f9a06fba4411c34ac4f0f53e15dd559ac1badccc389bf1274d9937ca'),
    (0x268dc, 0x26922, '2f1937ab11b554c0e266655ba6f0bc2ee96c1464cf8cd05531c2b192cfd59546'),
    (0x4afc, 0x4cc4, 'f95f78dbebfc724cd120aa5335b599d0bf50c9d83d563a41645a7306c38c0ccf'),
    (0x25ef4, 0x25f04, '6bfee35147b425262703cda1ad5823d72896677b43123362a4f0b0a74ccd5076'),
    (0x2678c, 0x268dc, '7f15314a5f23363528f524813d0d2da7ba358533e7eb8c403eccf89dd6fb9d95'),
    (0x1bfc8, 0x1c034, '449eca384724df5535f3ec7c9762851757d3c3c4a42f1f9dfb0e4f40d3865ff4'),
)
CORE_RANGES = (
    (0x13380, 0x13434, '69114299f8bc6b25ffc08090cce3a87f30292d2e9b9523c55730804d7a3dbbc3'),
    (0x13a28, 0x13abc, '03f056cb801498bd37311d3dd5c326435d0907d598f5389921661eef5a69cf4b'),
)
APPROVED_SHAPES = (
    (-320, -256, 64, 512, 512), (-192, -96, 64, 384, 192),
    (-240, -192, 64, 480, 256), (-176, -128, 48, 352, 176),
    (-160, -256, 64, 352, 256), (-320, -256, 64, 576, 192),
    (-256, -256, 64, 544, 192),
)
DIRECTION_NIBBLES = (255, 6, 2, 255, 4, 5, 3, 255, 0, 7, 1, 255, 255, 255, 255, 255)
SPEED_COMPONENTS = ((8, 6), (16, 11), (24, 17), (32, 22), (40, 28), (48, 34))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_code(twn: bytes, core: bytes) -> None:
    for name, blob, expected, ranges in (
        ('TWN.BIN', twn, TWN_HASH, TWN_RANGES), ('0', core, CORE_HASH, CORE_RANGES)
    ):
        if sha(blob) != expected:
            raise ValueError(f'{name} source hash changed')
        for start, end, expected_range in ranges:
            if len(blob) < end or sha(blob[start:end]) != expected_range:
                raise ValueError(f'{name} code range changed at {start:#x}')


def load_shapes(twn: bytes, core: bytes) -> tuple[tuple[int, ...], ...]:
    verify_code(twn, core)
    # These seven non-zero records are observed in the pinned source. The
    # machine wraps (actor[0x29]*10)&255; other indices are not approved here.
    records = tuple(struct.unpack_from('>5h', twn, 0x268dc + i * 10) for i in range(7))
    if records != APPROVED_SHAPES:
        raise ValueError('Shape records differ from the source-bound contract')
    return records


def signed16(value: int) -> int:
    value &= 0xffff
    return value - 0x10000 if value & 0x8000 else value


def divide16(value: int) -> int:
    """Signed C division helper 06023380: truncation towards zero."""
    return value // 16 if value >= 0 else -((-value) // 16)


def replay_input_gate(actor: bytes, pad_word: int, control_word: int, disabled_byte: int) -> tuple[bytes, dict]:
    """Local actor writes from 06094AFC; caller must select the correct actor.

    Source selects slot via byte[060C27AE]. Input is the already decoded word
    at 06036642, not Ymir/Saturn transport button bits. No rate is assumed.
    """
    if len(actor) < 0x3e or not all(type(v) is int and 0 <= v <= limit for v, limit in
                                  [(pad_word, 65535), (control_word, 65535), (disabled_byte, 255)]):
        raise ValueError('Invalid input-gate actor or captured control values')
    out = bytearray(actor)
    flags = struct.unpack_from('>H', out, 6)[0] & 0xfffd
    struct.pack_into('>H', out, 6, flags)
    struct.pack_into('>HH', out, 0x18, 0, 0)
    enabled = not (flags & 4 or disabled_byte == 255 or control_word in (0, 1))
    direction = DIRECTION_NIBBLES[(pad_word >> 12) & 15]
    if enabled:
        if direction != 255:
            struct.pack_into('>H', out, 0x26, direction)
            struct.pack_into('>H', out, 6, flags | 2)
        # Source 4BBC first rewrites heading; compare at 4BCE is then equal.
        # The alternate gradual-turn branch is unreachable on this path.
        struct.pack_into('>H', out, 0x24, 3)
    return bytes(out), {'routine_runtime': '0x06094AFC', 'enabled': enabled,
                        'direction_nibble': (pad_word >> 12) & 15,
                        'decoded_heading': direction, 'dynamic_verified': False}


def replay_velocity(actor: bytes) -> bytes:
    """060ABFC8 table reader. Must only be called under the original caller gate."""
    if len(actor) < 0x38:
        raise ValueError('Velocity actor is truncated')
    speed, heading = struct.unpack_from('>HH', actor, 0x24)
    if speed >= 6 or heading >= 8:
        raise ValueError('Unsupported source speed/heading index')
    straight, diagonal = SPEED_COMPONENTS[speed]
    xs = (straight, diagonal, 0, -diagonal, -straight, -diagonal, 0, diagonal)
    ys = (0, diagonal, straight, diagonal, 0, -diagonal, -straight, -diagonal)
    out = bytearray(actor)
    struct.pack_into('>hh', out, 0x18, xs[heading], ys[heading])
    flags = struct.unpack_from('>H', out, 8)[0]
    # 060B6894 -> 060B687C holds 8..15; 060B68BC -> 060B688C holds 4..7.
    # The 0..7 / 0..3 tables belong to the caller's idle-animation path.
    struct.pack_into('>H', out, 0x36, 8 + heading if flags & 1 else 4 + (heading >> 1))
    return bytes(out)


def replay_step(actor: bytes, flags: bytes, shapes: tuple[tuple[int, ...], ...]) -> tuple[bytes, dict]:
    """Replay one 060AB61A call and expose every flag lookup.

    Deliberately rejects unapproved shape records and accesses beyond the
    64 KiB table. A rejected wrap is a probe limitation, not an original wall.
    Returned slide words +1E/+20 are queued values, not additional motion.
    """
    if len(actor) < 0x4c or len(flags) != 0x10000:
        raise ValueError('Expected actor prefix >=76 bytes and exactly 64 KiB flags')
    index = actor[0x29]
    if shapes != APPROVED_SHAPES or index >= len(shapes):
        raise ValueError('Only the seven source-bound shape records are supported')
    shape = shapes[index]
    if len(shape) != 5 or any(type(v) is not int or not -32768 <= v <= 32767 for v in shape):
        raise ValueError('Expected five signed 16-bit shape words')
    if shape[3] <= 0 or shape[4] <= 0 or shape[3] > 1024 or shape[4] > 1024:
        raise ValueError('Unsupported shape extent')
    out = bytearray(actor)
    word = lambda offset: struct.unpack_from('>H', out, offset)[0]
    sw = lambda offset: signed16(word(offset))

    def put(offset: int, value: int) -> None:
        struct.pack_into('>H', out, offset, value & 0xffff)

    lookups = []
    selector = word(0x0a)
    mask = 0x80 if selector == 0 else 0x40
    mode_mask = 0x20 if selector == 0 else 0x10
    before = [word(0), word(2)]
    out[0x48] = out[0x4b] = 0
    put(6, word(6) & ~0x200)
    dx, dy = sw(0x18), sw(0x1a)
    bypass = bool(word(6) & 0x20)

    def sample(x: int, y: int, axis: str) -> int:
        address = (y >> 3) * 256 + (x >> 3)
        if not 0 <= address < len(flags):
            raise ValueError('Original lookup exceeds captured flags; no inferred boundary')
        value = flags[address]
        lookups.append({'axis': axis, 'x': x, 'y': y, 'index': address, 'flag': value})
        return value

    def contact(bit: int) -> None:
        out[0x4b] |= bit
        put(6, word(6) | 0x200)

    def queue_slide(offset: int, bitmap: int, count: int, correction: int) -> None:
        # Each hit shifts left once, leaving bit zero clear. Highest and lowest
        # sampled cells are tested in this order; do not replace with any-hit.
        if not bitmap & (1 << count):
            put(offset, -correction)
        elif not bitmap & 2:
            put(offset, correction)

    put(0, word(0) + dx)
    if dx and not bypass:
        top_unmasked = divide16(sw(2) + shape[1])
        top = top_unmasked & 0x7ff
        bottom = (top_unmasked + divide16(shape[4]) - 1) & 0x7ff
        bottom += 7 - (bottom & 7)
        edge = divide16(sw(0) + shape[0]) & 0x7ff
        if dx > 0:
            edge = (edge + divide16(shape[3]) - 1) & 0xffff
        bitmap = count = 0
        cursor = top
        while cursor <= bottom:
            cursor &= 0x7ff
            bitmap = ((bitmap + bool(sample(edge, cursor, 'x') & mask)) * 2) & 0xffffffff
            count += 1
            cursor += 8
            if count > 256:
                raise ValueError('Unsupported wrapping scan')
        if signed16(bitmap):
            correction = ((edge & 7) + 1 if dx > 0 else 8 - (edge & 7)) * 16
            put(0, (word(0) + (-correction if dx > 0 else correction)) & 0xfff0)
            contact(8 if dx > 0 else 4)
            if dy == 0:
                queue_slide(0x20, bitmap, count, correction)
        else:
            out[0x48] = 8 if dx > 0 else 4

    put(2, word(2) + dy)
    if dy and not bypass:
        edge = divide16(sw(2) + shape[1]) & 0x7ff
        left = divide16(sw(0) + shape[0]) & 0x7ff
        if dy > 0:
            edge += divide16(shape[4]) - 1
        last_sample = divide16(shape[3]) >> 3
        if left & 7 == 0:
            last_sample -= 1
        bitmap = count = 0
        cursor = left
        for _ in range(last_sample + 1):
            cursor &= 0x7ff
            bitmap = ((bitmap + bool(sample(cursor, edge, 'y') & mask)) * 2) & 0xffffffff
            count += 1
            cursor += 8
        if signed16(bitmap):
            correction = ((edge & 7) + 1 if dy > 0 else 8 - (edge & 7)) * 16
            put(2, (word(2) + (-correction if dy > 0 else correction)) & 0xfff0)
            contact(2 if dy > 0 else 1)
            if dx == 0:
                queue_slide(0x1e, bitmap, count, correction)
        else:
            out[0x48] = 2 if dy > 0 else 1

    center = sample((sw(0) >> 4) & 0x7ff, (sw(2) >> 4) & 0x7ff, 'center')
    if word(0x16) & 0x10:
        put(0x16, (word(0x16) & 0xff00) | (0x13 if center & mode_mask else 0x12))
    if center & 8:
        put(0x0a, 255)
    if center & 4:
        put(0x0a, 0)
    out[0x4a] = center
    return bytes(out), {
        'routine_runtime': '0x060AB61A', 'shape_index': index, 'initial_selector': selector,
        'blocking_mask': mask, 'mode_mask': mode_mask, 'collision_bypassed': bypass,
        'before': before, 'after': [word(0), word(2)], 'delta_words': [word(0x18), word(0x1a)],
        'global_writes': [{'address': '0x060DDDC4', 'size': 2, 'value': before[0]},
                          {'address': '0x060DDDC6', 'size': 2, 'value': before[1]}],
        'contact_bits': out[0x4b], 'free_direction_byte': out[0x48],
        'queued_slide_words': [word(0x1e), word(0x20)], 'lookups': lookups,
        'dynamic_verified': False,
    }


def run() -> dict:
    twn = (WORKSPACE / 'work/extract/TWN.BIN').read_bytes()
    core = (WORKSPACE / 'work/extract/0').read_bytes()
    shapes = load_shapes(twn, core)
    report = {
        'schema': 'ao_pc_movement_static_probe_v1',
        'sources': {'work/extract/TWN.BIN': sha(twn), 'work/extract/0': sha(core)},
        'routine_runtime': '0x060AB61A', 'routine_end_exclusive': '0x060ABB24',
        'shape_base': '0x060B68DC', 'shape_stride': 10,
        'shape_selector_offset': 0x29, 'shape_records_raw': shapes,
        'shape_fields': ['left', 'top', 'unresolved_word', 'width', 'height'],
        'static_callers': ['0x060AA1BC', '0x060AAE3E', '0x060AAEAC'],
        'actor_array_candidate': {'base': '0x060C8758', 'stride': 0x70, 'count': 32},
        'controlled_slot_byte': '0x060C27AE',
        'input_entry': '0x06094AFC', 'input_word': '0x06036642',
        'input_gates': {'disabled_byte': '0x060C41EC', 'control_word': '0x060C27AA'},
        'direction_nibbles': DIRECTION_NIBBLES, 'speed_components_raw': SPEED_COMPONENTS,
        'velocity_reader': '0x060ABFC8', 'actor_update_dispatch': '0x060AA0DE',
        'axis_order': ['x', 'y', 'center_flags'], 'coordinate_fraction_bits': 4,
        'player_identity_verified': False, 'collision_verified': False,
        'limits': [
            'Static function replay with synthetic inputs, not original emulator execution.',
            'Input gate and velocity table have separate static replays; complete caller effects are not modeled.',
            'Only seven nonzero source-bound shape records are accepted; shape word +4 is unresolved.',
            'Out-of-capture or nonterminating wrap is rejected, not converted into a wall.',
            'Collision may queue perpendicular slide for the next caller update; it is not applied here.',
        ],
    }
    path = ROOT / 'reports/exploration/movement-static.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    result = run()
    print(json.dumps({key: result[key] for key in ('routine_runtime', 'shape_records_raw', 'collision_verified')}, indent=2))
