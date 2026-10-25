"""Separate source draw contract for pickup and hidden Cirrus decorations.

Shares verified ordering primitives; the old eight-object gate is unchanged.
"""
import struct
from character_draw_order import u16,u32,s16,_memory,bucket_order,priority_order

def scene(high: bytes, low: bytes, *, decoration_snapshot: bytes | None = None,
                        camera_at_command_target: list[int] | None = None,
                        room_camera_scope: bool = False) -> dict:
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
    if type(room_camera_scope) is not bool:
        raise ValueError('Invalid camera evidence scope')
    maximum = (640, 1568) if room_camera_scope else (544, 1554)
    if not 512 * 16 <= camera[0] <= maximum[0] * 16 or not 1536 * 16 <= camera[1] <= maximum[1] * 16 or s16(high, 0xc42a4) or s16(high, 0xc42a6):
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
            if kind == 'actor' and (slot not in (0,1) or u16(raw, 0x56) != 0 or (slot == 0 and u16(raw, 8) != 9) or s16(raw, 4) != 0):
                raise ValueError('Actor branch outside the verified room contract')
            if kind == 'actor' and slot == 1:
                expression = (u16(raw,8),u16(raw,0xe),u16(raw,0x12),u32(raw,0x58),u32(raw,0x60)) == (0x80,217,2,0x260e5a24,0x260e8c48)
                spark = (u16(raw,8),u16(raw,0xe),u16(raw,0x12),u32(raw,0x58),u32(raw,0x60)) == (0,159,14,0x260e5748,0x260e8b50)
                if not (expression or spark) or flags != 0x23 or u16(raw,0x14) != 0:
                    raise ValueError('Unverified interaction auxiliary actor')
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
    if [r['slot'] for r in objects] not in (list(range(8)),list(range(6))) or [r['slot'] for r in actors] not in ([0],[0,1]):
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

