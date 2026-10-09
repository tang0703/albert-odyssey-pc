"""Bounded source reconstruction of MAP001 scene-object/actor draw ordering.

This models the game's bucket insertion and command priority chains, not VDP1
rasterization. Sprite-shadow geometry and VDP2 composition remain separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TWN_SHA = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
CORE_SHA = '95054f9128b7ab47f88c6659b103e7bee9db94c13548f815bbda5999b30da2ff'
RANGES = (
    ('TWN.BIN', 0x5030, 0x580e, 'ec56f77ccc1433d0ebc22b66e736dd7f9762a339cb8bfabd4773adb61c2141a6'),
    ('TWN.BIN', 0x8d46, 0x935c, '2ed5046afa791488061bd59d05abf6af63b0ebebf257c4a387bc66ec279365a6'),
    ('0', 0x76f20, 0x7705c, 'f17b818d6da48a8de350c68d4c607c73a5d645c339edcfc52723b7c74cae45ea'),
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_source(twn: bytes, core: bytes) -> list[dict]:
    sources = {'TWN.BIN': twn, '0': core}
    if sha(twn) != TWN_SHA or sha(core) != CORE_SHA:
        raise ValueError('Draw-order source identity changed')
    result = []
    for name, start, end, expected in RANGES:
        if sha(sources[name][start:end]) != expected:
            raise ValueError('Draw-order source range changed')
        result.append({'file': 'work/extract/' + name, 'start': start, 'end_exclusive': end, 'sha256': expected})
    return result


def u16(raw: bytes, offset: int) -> int:
    return struct.unpack_from('>H', raw, offset)[0]


def s16(raw: bytes, offset: int) -> int:
    return struct.unpack_from('>h', raw, offset)[0]


def u32(raw: bytes, offset: int) -> int:
    return struct.unpack_from('>I', raw, offset)[0]


def divide16(number: int) -> int:
    return number // 16 if number >= 0 else -((-number) // 16)


def bucket_order(objects: list[dict], actors: list[dict]) -> dict:
    """06095098..060952D8: objects first, ascending slot, then actors.

    The occupied bucket advances, including across another object's original
    key. Consequently this is not interchangeable with stable sorting by Y.
    This bounded model rejects overflow instead of reproducing an overwrite.
    """
    buckets = [None] * 768
    unsorted, placements = [], []
    for kind, rows in [('object', objects), ('actor', actors)]:
        if [r['slot'] for r in rows] != sorted({r['slot'] for r in rows}):
            raise ValueError('Duplicate or unordered source slots')
        for row in rows:
            if (type(row['slot']) is not int or not 0 <= row['slot'] < (64 if kind == 'object' else 32)
                    or type(row['y_sorted']) is not bool
                    or any(type(row[k]) is not int or not -32768 <= row[k] <= 32767
                           for k in ('y_raw', 'camera_y_raw'))):
                raise ValueError('Invalid bucket input fields')
            item = {'kind': kind, 'slot': row['slot']}
            if not row['y_sorted']:
                unsorted.append(item)
                continue
            key = divide16(row['y_raw'] - row['camera_y_raw']) + 256
            if not 40 <= key <= 700:
                raise ValueError('Draw-order test boundary: initial bucket outside 40..700')
            bucket = key
            while bucket < 767 and buckets[bucket] is not None:
                bucket += 1
            if buckets[bucket] is not None:
                raise ValueError('Draw-order bucket overflow is unverified')
            buckets[bucket] = item
            placements.append(item | {'initial_bucket': key, 'assigned_bucket': bucket})
    return {'unsorted': unsorted, 'sorted': [r for r in buckets if r is not None], 'placements': placements}


def priority_order(items: list[dict], limit: int) -> list[dict]:
    """06086F20 tail-append + 06086FCC ascending priority traversal."""
    if type(limit) is not int or limit != 256:
        raise ValueError('Unverified command-priority configuration')
    for row in items:
        if type(row.get('priority')) is not int or row['priority'] < 0:
            raise ValueError('Invalid command priority')
    return sorted(items, key=lambda row: min(row['priority'], limit - 1))


def _memory(high: bytes, low: bytes, address: int, size: int) -> bytes:
    if 0x06000000 <= (address & 0x0fffffff) < 0x06100000:
        data, offset = high, address & 0xfffff
    elif 0x00200000 <= (address & 0x0fffffff) < 0x00300000:
        data, offset = low, (address & 0x0fffffff) - 0x00200000
    else:
        raise ValueError('Unverified image-record memory region')
    if size < 1 or offset + size > len(data):
        raise ValueError('Truncated image record')
    return data[offset:offset + size]


def scene_from_snapshot(high: bytes, low: bytes, *, decoration_snapshot: bytes | None = None,
                        camera_at_command_target: list[int] | None = None) -> dict:
    """Extract source anchors, pieces and sorting inputs from a sealed sample.

    The caller must verify the capture manifest first. This function rejects
    unsupported runtime modes rather than claiming arbitrary maps work.
    """
    if len(high) != 0x100000 or len(low) != 0x100000 or (decoration_snapshot is not None and len(decoration_snapshot) != 0x100000):
        raise ValueError('Incomplete scene RAM')
    camera = [s16(high, 0xc4292), s16(high, 0xc4294)]
    if camera_at_command_target is not None:
        if (not isinstance(camera_at_command_target, list) or len(camera_at_command_target) != 2
                or any(type(v) is not int for v in camera_at_command_target)):
            raise ValueError('Invalid command-target camera')
        camera = camera_at_command_target
    if not 512 * 16 <= camera[0] <= 544 * 16 or not 1536 * 16 <= camera[1] <= 1554 * 16 or s16(high, 0xc42a4) or s16(high, 0xc42a6):
        raise ValueError('Unverified camera or camera displacement')
    if u32(high, 0x741f4) != 1 or u32(high, 0x741e8) != 256:
        raise ValueError('Unverified priority-chain mode')
    if u16(high, 0x36644) & 0x20:
        raise ValueError('Source debug object suppression is active')
    texture_table = u32(high, 0x741e0)
    objects, actors = [], []
    for kind, base, stride, count in [('object', 0xca358, 60, 64), ('actor', 0xc8758, 112, 32)]:
        for slot in range(count):
            memory = decoration_snapshot if kind == 'object' and slot == 7 and decoration_snapshot is not None else high
            raw = memory[base + slot * stride:base + (slot + 1) * stride]
            flags = u16(raw, 0x16)
            active = u16(raw, 0xa if kind == 'object' else 6) & 0x8000
            image = u16(raw, 0x22 if kind == 'object' else 0x34)
            if not active or image >= 127:
                continue
            if kind == 'actor' and (u16(raw, 8) & 0x100 or raw[0x45] != 255):
                continue
            if kind == 'actor' and (slot != 0 or u16(raw, 0x56) != 0 or u16(raw, 8) != 9 or s16(raw, 4) != 0):
                raise ValueError('Actor branch outside the verified room contract')
            if kind == 'object' and (slot > 7 or u16(raw, 0x14) != 0):
                raise ValueError('Unverified scene-object branch')
            pointer = u32(raw, 0x30 if kind == 'object' else 0x5c)
            piece_count = u16(_memory(high, low, pointer, 2), 0)
            if not 1 <= piece_count <= 16:
                raise ValueError('Invalid image-piece count')
            row = {'kind': kind, 'slot': slot, 'id': f'{kind}_{slot}',
                   'world_xy_raw': [s16(raw, 0), s16(raw, 2)], 'y_raw': s16(raw, 2),
                   'camera_y_raw': camera[1], 'y_sorted': bool(flags & 0x10),
                   'render_flags': flags, 'record_address': pointer, 'pieces': []}
            priority = 10 if row['y_sorted'] or not flags & 0x20 else 100
            for piece in range(piece_count):
                x, y, attr = struct.unpack('>hhH', _memory(high, low, pointer + 2 + 6 * piece, 6))
                texture_id = u16(raw, 0xe) + (attr & 255)
                tex = _memory(high, low, texture_table + texture_id * 10, 10)
                width, height = (u16(tex, 2) >> 8) * 8, u16(tex, 2) & 255
                if not width or not height or attr & 0xc000:
                    raise ValueError('Unverified piece geometry or mirror attributes')
                origin = [(row['world_xy_raw'][i] & ~15) // 16 - camera[i] // 16 for i in (0, 1)]
                flip = kind == 'actor' and bool(u16(raw, 0x14) & 1)
                origin[0] += -x - width if flip else x
                origin[1] += y
                palette = u16(raw, 0x12)
                if palette == 255:
                    palette = (attr >> 8) & 63
                mode = u16(raw, 0x10) >> 3
                shifts = {0: 4, 2: 6}
                if mode not in shifts:
                    raise ValueError('Unknown color mode')
                colr = (palette << shifts[mode]) | ((flags & 7) << 12)
                if kind == 'object':
                    colr |= ((flags >> 4) & 7) << 10
                # Object renderflag 0x20 raises the request for every piece.
                # This saturates at 255 in the current 256-priority core.
                requested = priority + (512 * (piece + 1) if kind == 'object' and flags & 0x20 else 0)
                row['pieces'].append({'piece': piece, 'id': f'{kind}_{slot}:{piece}',
                    'offset': [x, y], 'source_anchor': [-x, -y], 'attributes': attr,
                    'runtime_texture_id': texture_id, 'texture_offset': u16(tex, 0) * 8,
                    'width': width, 'height': height, 'screen_origin': origin, 'flip_x': flip,
                    'colr': colr, 'color_mode': mode, 'priority': requested, 'effective_priority': min(requested, 255)})
            (objects if kind == 'object' else actors).append(row)
    if [r['slot'] for r in objects] != list(range(8)) or len(actors) != 1:
        raise ValueError('Room population changed')
    order = bucket_order(objects, actors)
    lookup = {(r['kind'], r['slot']): r for r in objects + actors}
    pieces = [p for item in order['unsorted'] + order['sorted']
              for p in lookup[(item['kind'], item['slot'])]['pieces']]
    ordered = priority_order(pieces, 256)
    return {'schema': 'ao_character_draw_order_scene_v1', 'camera_raw': camera,
            'objects': objects, 'actors': actors, 'buckets': order,
            'body_and_prop_order': [p['id'] for p in ordered], 'ordered_pieces': ordered,
            'shadow_geometry_validated': False}


def _matches(piece: dict, command: bytes) -> bool:
    words = struct.unpack('>16H', command)
    x, y = piece['screen_origin']
    w, h = piece['width'], piece['height']
    vertices = (x, y, x + w - 1, y, x + w - 1, y + h - 1, x, y + h - 1)
    return (words[0] & 15 == 2 and bool(words[0] & 0x10) == piece['flip_x']
            and (words[2] >> 3) & 7 == piece['color_mode'] and words[4] * 8 == piece['texture_offset']
            and words[5] == (w // 8) * 256 + h and words[3] == piece['colr']
            and struct.unpack('>8h', command[12:28]) == vertices)


def compare_commands(scene: dict, events: list[dict]) -> dict:
    observed, excluded = [], []
    for event in events:
        command = bytes.fromhex(event['command_hex'])
        matches = [p for p in scene['ordered_pieces'] if _matches(p, command)]
        if len(matches) > 1:
            raise ValueError('Ambiguous draw-order command identity')
        if matches:
            observed.append(matches[0]['id'])
        else:
            words = struct.unpack('>16H', command)
            # Only clipping, local-coordinate and the separately acknowledged
            # player-shadow path may be outside this body/prop-order proof.
            if words[0] & 15 not in (9, 10) and not (words[0] & 15 == 2 and words[3] == 0x27c0):
                raise ValueError(f'Unbound executed command at {event["command_address"]:#x}')
            if observed:
                raise ValueError('State/shadow command occurred after a body or prop')
            excluded.append({'command_address': event['command_address'], 'opcode': words[0] & 15,
                             'reason': 'shadow_geometry_not_validated' if words[3] == 0x27c0 else 'non_sprite_state'})
    if observed != scene['body_and_prop_order']:
        raise ValueError(f'Source order differs: {observed} != {scene["body_and_prop_order"]}')
    return {'observed_order': observed, 'excluded_commands': excluded}


def validate_capture(folder: Path) -> dict:
    from verify_character_capture import inspect
    evidence = inspect(folder)
    capture = evidence['capture']
    del evidence
    frames = capture['frames']
    rows, scenes = [], {}
    def flush(frame: int, commands: list[dict]) -> None:
        source_frame = max(frame - 2, 0)
        path = folder / f'frame-{source_frame:06d}'
        high, low = (path / 'wram-high.bin').read_bytes(), (path / 'wram-low.bin').read_bytes()
        target = json.loads((folder / f'frame-{frame:06d}' / 'sample.json').read_text(encoding='utf-8'))['vdp2']
        if (target['SCXIN0'] != target['SCXIN1'] or target['SCYIN0'] != target['SCYIN1']
                or any(target[k] for k in ('SCXDN0', 'SCYDN0', 'SCXDN1', 'SCYDN1'))):
            raise ValueError('Unverified command-target scroll mode')
        camera = [target['SCXIN0'] * 16, target['SCYIN0'] * 16]
        scene = scene_from_snapshot(high, low, camera_at_command_target=camera)
        decoration_frame = source_frame
        try:
            result = compare_commands(scene, commands)
        except ValueError:
            # RunFrame ends inside the scene-object update loop. Slot 7 is an
            # animated decoration, so the end snapshot can fall either side
            # of its update. This binds its complete command pieces to one of
            # two sealed records, NOT a reproduction of its animation timing.
            decoration_frame = max(frame - 1, 0)
            later = (folder / f'frame-{decoration_frame:06d}' / 'wram-high.bin').read_bytes()
            scene = scene_from_snapshot(high, low, decoration_snapshot=later, camera_at_command_target=camera)
            try:
                result = compare_commands(scene, commands)
            except ValueError as error:
                raise ValueError(f'{folder.name} frame {frame}: {error}') from error
        rows.append({'frame': frame, 'actor_furniture_source_state_frame': source_frame,
                     'camera_target_vdp2_sample_frame': frame,
                     'decoration7_record_snapshot_frame': decoration_frame,
                     'decoration7_animation_timing_validated': False,
                     'camera_raw': scene['camera_raw'], 'commands': len(commands), **result})
        if source_frame == 0:
            scenes['initial'] = scene
    current, commands = 1, []
    for line in (folder / 'vdp-events.jsonl').open(encoding='utf-8'):
        event = json.loads(line)
        if event['frame'] > current:
            flush(current, commands)
            current, commands = event['frame'], []
        if event['kind'] == 'command_execute_before':
            commands.append(event)
    flush(current, commands)
    if len(rows) != frames:
        raise ValueError('Capture frame coverage is incomplete')
    return {'folder': str(folder), 'manifest_sha256': sha((folder / 'manifest.json').read_bytes()),
            'frames': rows, 'initial_scene': scenes['initial'], 'frame_count': frames}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('captures', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    ranges = verify_source((ROOT.parent / 'work/extract/TWN.BIN').read_bytes(), (ROOT.parent / 'work/extract/0').read_bytes())
    reports = [validate_capture(path.resolve()) for path in args.captures]
    result = {'schema': 'ao_character_draw_order_validation_v1', 'passed': True,
              'source_ranges': ranges, 'captures': reports,
              'source_sha256': {'TWN.BIN': TWN_SHA, '0': CORE_SHA},
              'model_sha256': sha(Path(__file__).read_bytes()),
              'frame_count': sum(r['frame_count'] for r in reports),
              'unbound_body_prop_commands': 0, 'ordering_mismatches': 0,
              'decoration7_animation_timing_validated': False,
              'shadow_geometry_validated': False,
              'scope': 'MAP001 fixed-room body/prop command order; not shadow or full-scene rasterization'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'frames': result['frame_count'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
