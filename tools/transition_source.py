"""Bounded MAP001 8 -> 7 source inventory, independent of capture outcomes.

This is a source-study contract, not a PC transition implementation or release
gate. The old seven bundles and their validators are deliberately untouched.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TWN_SHA = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
MAP_SHA = '8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9'
BASE = 0x260e0000
ROUTES = ('equip-stairs', 'remove-stairs', 'reequip-stairs')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sources():
    twn = (ROOT.parent/'work/extract/TWN.BIN').read_bytes()
    source = (ROOT.parent/'work/extract/MAP001.TWN').read_bytes()
    if sha(twn) != TWN_SHA or sha(source) != MAP_SHA:
        raise ValueError('Transition executable/map identity changed')
    return twn, source


def pointer(raw, offset):
    value = int.from_bytes(raw[offset:offset+4], 'big') - BASE + 8
    if not 8 <= value < 0xf230:
        raise ValueError('Pointer outside the pinned MAP001 script segment')
    return value


def destination(twn, source):
    """060AC458 record -> 060933B8 scene table -> MAP script pointer table."""
    if sha(twn) != TWN_SHA or sha(source) != MAP_SHA:
        raise ValueError('Changed transition source identity')
    record = source[0x1580:0x1590]
    if len(record) != 16 or record[0] != 0:
        raise ValueError('Stair destination record changed')
    values = struct.unpack('>7HB', record[1:])
    bounds, scene, x, y, heading = values[:4], values[4], values[5], values[6], values[7]
    table_offset = 0x30550 + scene * 6
    map_id, entry, tag, auxiliary = struct.unpack('>HHBB', twn[table_offset:table_offset+6])
    count = int.from_bytes(source[0x408:0x40a], 'big')
    if scene != 7 or map_id != 1 or entry >= count or (tag, auxiliary) != (255, 0):
        raise ValueError('Unverified destination table record')
    script = pointer(source, 0x40a + entry * 4)
    if (x, y, heading, script) != (0x3880, 0x7780, 2, 0x1007):
        raise ValueError('Unverified destination initialization')
    return {'source_scene_id': 8, 'destination_scene_id': scene,
            'resource_map_id': map_id, 'entry_index': entry, 'script_offset': script,
            'stair_record_offset': 0x1580, 'scene_table_offset': table_offset,
            'scene_table_sha256': sha(twn[table_offset:table_offset+6]),
            'bounds_raw': list(bounds), 'spawn_raw': [x, y], 'heading': heading,
            'resource_identity_basis': 'Executed scene-table lookup and cached MAP001 segment; scene id is not a filename.'}


# Sizes are bound to the executed handler and source operand layout. 18 has a
# variable table layout; this stage accepts just the complete verified record.
SIZES = {0x2b: 5, 0x2c: 1, 0x5c: 3, 0x13: 3, 0x0c: 3, 0x1a: 3,
         0x1e: 13, 0x1b: 15, 0x14: 2, 0x17: 2, 0x15: 11, 0x16: 9,
         0x33: 20, 0x09: 13, 0x0e: 3, 0x18: 62, 0x35: 11,
         0x4b: 14, 0x1c: 10, 0: 2}
ACTIONS = {0x2b: 'call_initialization', 0x2c: 'return_initialization',
           0x5c: 'set_scene_parameter', 0x13: 'ensure_map_collision_resource',
           0x0c: 'ensure_chr_resource', 0x1a: 'ensure_v1n_sprite_resource',
           0x1e: 'set_actor_resource_tables', 0x1b: 'set_object_resource_tables',
           0x14: 'initialize_display', 0x17: 'select_camera_actor',
           0x15: 'upload_palette', 0x16: 'set_camera_limits',
           0x33: 'initialize_camera_plane', 0x09: 'branch_story_bit',
           0x0e: 'request_source_music', 0x18: 'install_scene_contact_tables',
           0x35: 'spawn_scene_object', 0x4b: 'install_actor_interaction',
           0x1c: 'spawn_scene_actor', 0: 'end_initialization'}


def initialization(source, twn, story):
    """Follow original call/return/bit tests using initial persistent flags only.

    No capture supplies instruction offsets, branch targets or later flags.
    Unsupported branches/opcodes fail closed instead of being skipped.
    """
    if len(story) < 21 or story[0] != 7:
        raise ValueError('Initialization requires the verified ever-equipped state')
    cursor = destination(twn, source)['script_offset']
    stack = []
    rows = []
    allowed = set(range(0xa2b, 0xa97)) | set(range(0x1007, 0x102d)) | set(range(0x1087, 0x10ec)) | set(range(0x1459, 0x14c1))
    for _ in range(80):
        if cursor not in allowed:
            raise ValueError(f'Unverified initialization branch {cursor:04x}')
        op = source[cursor]
        size = SIZES.get(op)
        if size is None:
            raise ValueError(f'Unknown initialization opcode {op:02x}')
        raw = source[cursor:cursor+size]
        next_cursor = cursor + size
        row = {'offset': cursor, 'opcode': op, 'action': ACTIONS[op], 'span': size,
               'handler': int.from_bytes(twn[0x262f8+op*4:0x262fc+op*4], 'big'),
               'source_sha256': sha(raw)}
        if op == 0x2b:
            stack.append(next_cursor)
            next_cursor = pointer(source, cursor+1)
            row['target'] = next_cursor
        elif op == 0x2c:
            if not stack:
                raise ValueError('Initialization return stack underflow')
            next_cursor = stack.pop()
        elif op == 9:
            mode, bit, end = raw[9], int.from_bytes(raw[10:12], 'big'), raw[12]
            if mode not in (1, 2) or end != 0 or bit not in (3, 11, 161):
                raise ValueError('Unverified arrival condition')
            is_set = bool(story[bit//8] & (1 << (bit % 8)))
            truth = is_set if mode == 1 else not is_set
            next_cursor = pointer(source, cursor+(1 if truth else 5))
            row.update(bit=bit, required_set=mode == 1, result=truth, target=next_cursor)
        elif op in (0x5c, 0x13, 0x0c, 0x1a):
            row['value'] = int.from_bytes(raw[1:3], 'big')
        elif op == 0x16:
            x0, y0, x1, y1 = struct.unpack('>4H', raw[1:])
            row['limits_raw'] = [x0, y0, (x1-0x1300)&65535, (y1-0xd00)&65535]
        elif op in (0x1e, 0x1b):
            row['table_offsets'] = [pointer(source, cursor+i) for i in ((1,5,9) if op==0x1e else (3,7,11))]
        elif op in (0x35, 0x1c):
            row.update(resource_id=int.from_bytes(raw[1:3], 'big'),
                       world_xy_raw=list(struct.unpack('>2H', raw[3:7])),
                       options=list(raw[7:]))
        elif op == 0x0e:
            if raw[1] != 0:
                raise ValueError('Unverified arrival audio operation')
            row['music_id'] = raw[2]
        elif op == 0x18:
            if cursor != 0x108a or raw[1] != 3:
                raise ValueError('Unverified contact-table layout')
            row['contacts'] = landing_contacts(source)
            row['additional_tables'] = landing_auxiliary_tables(source)
        row['next_offset'] = next_cursor
        rows.append(row)
        cursor = next_cursor
        if op == 0:
            if stack or row['offset'] != 0x10ea:
                raise ValueError('Incomplete arrival initialization')
            return rows
    raise ValueError('Initialization command budget exhausted')


def landing_contacts(source):
    cursor = 0x108c
    rows = []
    for _ in range(3):
        kind = source[cursor]
        bounds = list(struct.unpack_from('>4H', source, cursor+1))
        row = {'kind': kind, 'bounds_raw': bounds, 'source_offset': cursor}
        if kind == 0:
            scene, x, y, heading = struct.unpack('>3HB', source[cursor+9:cursor+16])
            row.update(scene=scene, spawn_raw=[x, y], heading=heading,
                       policy='return_stair_test_boundary')
            cursor += 16
        elif kind == 2:
            row.update(script_offset=pointer(source,cursor+9), policy='out_of_scope_event_test_boundary')
            cursor += 13
        else:
            raise ValueError('Unknown landing contact kind')
        rows.append(row)
    if cursor != 0x10b6:
        raise ValueError('Landing contact layout differs')
    return rows


def landing_auxiliary_tables(source):
    """Remaining op18 groups. Installed operands, not interaction execution."""
    raw=source[0x10b6:0x10c8]
    if raw!=bytes.fromhex('0001033100740031f074f000440002007000'):
        raise ValueError('Unverified auxiliary landing contacts')
    return {'source_span':[0x10b6,0x10c8], 'group_counts':[0,1,0],
            'records':[{'runtime_address':0x060cc55a,'kind':3,
                        'bounds_raw':list(struct.unpack('>4H',raw[3:11])),
                        'parameters':list(struct.unpack('>3H',raw[11:17])),
                        'policy':'not an approved interaction; outside landing walking coverage'}]}


def build(story):
    twn, source = sources()
    ranges = [(0x1c458,0x1c50c),(0x33b8,0x3b36),(0x4728,0x49a8),
              (0x199e4,0x19b00),(0x234e,0x23a8),(0x2a18,0x2dc0),
              (0x149fc,0x14ae6),(0x1016c,0x10270)]
    return {'schema':'ao_pc_transition_source_inventory_v1', 'runtime_approved':False,
            'source_map_sha256':MAP_SHA, 'source_twn_sha256':TWN_SHA,
            'destination':destination(twn,source), 'initialization':initialization(source,twn,story),
            'source_ranges':[{'offset':a,'end_exclusive':b,'sha256':sha(twn[a:b])} for a,b in ranges],
            'scope':'One-way scene 8 to 7. No whole-room or adjacent-scene acceptance.',
            'performance_tested':False}
