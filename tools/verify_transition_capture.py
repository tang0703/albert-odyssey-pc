"""Verify T1 source captures; never treats capture agreement as a PC model pass."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path, PurePosixPath

from inspect_event_capture import inspect, watched
from transition_source import ROOT, ROUTES, build, sha
from verify_equipment_sequence import validate as equipment_prefix


def verify_files(folder):
    raw = (folder/'manifest.json').read_bytes()
    manifest = json.loads(raw.decode('utf-8-sig'))
    if manifest.get('inputs_unchanged') is not True or manifest.get('schema') != 'ao_ymir_character_capture_manifest_v2':
        raise ValueError('Incomplete transition capture')
    entries = {}
    for record in manifest['outputs']:
        name = record['path']
        if (not isinstance(name,str) or not name or name in entries or ':' in name or '\\' in name
                or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts
                or PurePosixPath(name).as_posix()!=name):
            raise ValueError('Invalid capture manifest path')
        path = folder/name
        cursor=path
        while cursor!=folder:
            if cursor.is_symlink() or (hasattr(cursor,'is_junction') and cursor.is_junction()):
                raise ValueError('Linked capture path')
            cursor=cursor.parent
        if not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError('Capture path escapes root')
        if not path.is_file() or path.is_symlink() or path.stat().st_size != record['bytes']:
            raise ValueError(f'Capture file missing/changed: {name}')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != record['sha256']:
            raise ValueError(f'Capture hash mismatch: {name}')
        entries[name] = record['sha256']
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != set(entries)|{'manifest.json'} or (folder/'manifest.json').read_bytes() != raw:
        raise ValueError('Capture closure changed')
    return manifest, entries, sha(raw)


def review(folder, entries):
    prefix = equipment_prefix(folder)
    if not prefix['passed'] or not prefix['transition']:
        raise ValueError('Original-room continuous reference did not reach the staircase')
    commit = prefix['transition']['frame']
    frames = [json.loads(line) for line in (folder/'frames.jsonl').open(encoding='utf-8')]
    if [r['frame'] for r in frames] != list(range(1, len(frames)+1)):
        raise ValueError('Non-contiguous source video frames')
    high = (folder/'frame-000000/wram-high.bin').read_bytes()
    story = bytearray(high[0x36938:0x369b8])
    # These are the source-verified effects of the prefix, not later RAM input.
    story[0] = int(prefix['equipment_ops'][-1]['story'], 16)
    contract = build(story)
    inventory = inspect(folder)
    calls = [c for c in inventory['calls'] if c['frame'] >= commit]
    expected = contract['initialization']
    if len(calls) != len(expected):
        raise ValueError('Additional or missing arrival event instructions')
    for actual, predicted in zip(calls, expected):
        values = (int(actual['offset'],16), int(actual['opcode'],16), int(actual['handler'],16),
                  int(actual['next_cursor'],16)-0x260e0000+8)
        if values != tuple(predicted[k] for k in ('offset','opcode','handler','next_offset')):
            raise ValueError('Arrival initialization differs from independent source traversal')
        if actual['slot'] != '0x60c7fd8' or actual['result'] != (0 if predicted['opcode']==0 else 0xffffffff):
            raise ValueError('Unexpected initializer slot or command result')
    phases = []
    previous = None
    first_ready = None
    first_move = None
    final = frames[-1]
    for row in frames:
        if row['frame'] < commit:
            continue
        phase = list(struct.unpack('>HH', watched(row, 0x060c27aa, 4)))
        if phase != previous:
            phases.append({'frame':row['frame'], 'fade_state':phase[0], 'main_state':phase[1]})
            previous = phase
        if row['frame'] >= calls[-1]['return_frame'] and phase == [2,2]:
            if first_ready is None:
                first_ready = row['frame']
            player = watched(row,0x060c8758,112)
            if player[:4] != bytes.fromhex('38807780') and first_move is None:
                first_move = row['frame']
        last_op = prefix['equipment_ops'][-1]
        actual = (watched(row,0x060366b7,1)[0], watched(row,0x060367cf,1)[0],
                  int.from_bytes(watched(row,0x060366a0,2),'big'), watched(row,0x06036938,1).hex())
        if actual != (last_op['weapon'],last_op['item_count'],last_op['attack'],last_op['story']):
            raise ValueError('Equipment/story changed during scene transfer')
        if watched(row,0x060c51d4,2) != b'\0\0':
            raise ValueError('Arrival dialogue requires additional source study')
    if [(r['fade_state'],r['main_state']) for r in phases] != [(1,12),(2,12),(0,12),(0,2),(2,2)]:
        raise ValueError('Unexpected scene-transfer phase sequence')
    if first_ready is None or first_move is None:
        raise ValueError('No dynamically demonstrated controllable landing')
    limits = list(struct.unpack('>4H', watched(final,0x060c426e,8)))
    expected_limits = next(r['limits_raw'] for r in expected if r['action']=='set_camera_limits')
    if limits != expected_limits or watched(final,0x060c41ec,1) != b'\0':
        raise ValueError('Arrival camera/control initialization differs')
    terminal = folder/f"frame-{len(frames):06}"
    final_high = (terminal/'wram-high.bin').read_bytes()
    final_low = (terminal/'wram-low.bin').read_bytes()
    source = (ROOT.parent/'work/extract/MAP001.TWN').read_bytes()
    segment_size = int.from_bytes(source[4:8],'big')
    if final_high[0xe0000:0xe0000+segment_size] != source[8:8+segment_size]:
        raise ValueError('Destination script bytes are not MAP001 source')
    if final_low[0x10000:0x20000] != (folder/'frame-000000/wram-low.bin').read_bytes()[0x10000:0x20000]:
        raise ValueError('Collision table changed; decoder must be extended')
    objects = [r for r in expected if r['action']=='spawn_scene_object']
    for slot, obj in enumerate(objects):
        raw = final_high[0xca358+60*slot:0xca358+60*(slot+1)]
        if list(struct.unpack('>HH',raw[:4])) != obj['world_xy_raw'] or int.from_bytes(raw[0x28:0x2a],'big') != obj['resource_id']:
            raise ValueError('Initialized scene object does not match script operands')
    actor = next(r for r in expected if r['action']=='spawn_scene_actor')
    raw = final_high[0xc87c8:0xc8838]
    if list(struct.unpack('>HH',raw[:4])) != actor['world_xy_raw'] or int.from_bytes(raw[0x3a:0x3c],'big') != actor['resource_id']:
        raise ValueError('Initialized auxiliary actor differs from script')
    contact_rows = next(r['contacts'] for r in expected if r['action']=='install_scene_contact_tables')
    for index, contact in enumerate(contact_rows):
        raw = final_high[0xcb55a+index*32:0xcb55a+(index+1)*32]
        if list(struct.unpack('>4H',raw[:8])) != contact['bounds_raw'] or raw[8] != contact['kind']:
            raise ValueError('Arrival contact table differs from source operands')
    tables=next(r['additional_tables'] for r in expected if r['action']=='install_scene_contact_tables')
    if list(struct.unpack_from('>3H',final_high,0xc41f0))!=tables['group_counts']:
        raise ValueError('Auxiliary contact counts differ')
    for record in tables['records']:
        start=record['runtime_address']&0xfffff
        raw=final_high[start:start+32]
        if (list(struct.unpack_from('>4H',raw))!=record['bounds_raw'] or raw[8]!=record['kind']
                or list(struct.unpack_from('>3H',raw,9))!=record['parameters']):
            raise ValueError('Auxiliary contact parameters differ')
    return {'capture':folder.relative_to(ROOT).as_posix(), 'source_replay_passed':True,
            'frames':len(frames),'prefix_updates':prefix['updates'],'prefix_checks':prefix['checks'],
            'equipment_operations':prefix['equipment_ops'],'commit_frame':commit,'phases':phases,
            'initialization_commands':len(expected),'initialization_begin_frame':calls[0]['frame'],
            'initialization_end_frame':calls[-1]['return_frame'], 'first_control_ready_frame':first_ready,
            'first_walk_frame':first_move,'destination':contract['destination'],
            'camera_limits_raw':limits, 'arrival_dialogue_observed':False,
            'active_source_objects':len(objects),'additional_actor_id':actor['resource_id'],
            'additional_actor_xy_raw':actor['world_xy_raw'],
            'collision_table_sha256':sha(final_low[0x10000:0x20000]),
            'script_segment_sha256':sha(final_high[0xe0000:0xe0000+segment_size]),
            'stream_hashes':{k:entries[k] for k in ('frames.jsonl','hooks.jsonl','vdp-events.jsonl')},
            'pc_model_passed':False,'graphics_passed':False,'performance_tested':False}


def run(base):
    results = []
    for route in ROUTES:
        baseline = None
        representative = None
        for repeat in range(1,4):
            folder = base/f't1-{route}-{repeat}'
            _, entries, manifest_sha = verify_files(folder)
            # Equality includes every raw RAM/framebuffer/video sample, not
            # just selected player fields. Manifest time/path are excluded.
            if baseline is None:
                baseline = entries
                representative = review(folder, entries)
            elif entries != baseline:
                raise ValueError(f'Non-deterministic replay: {route}/{repeat}')
            results.append({'route':route,'repeat':repeat,'manifest_sha256':manifest_sha,
                            'all_capture_payloads_identical':True,
                            'source_review':representative if repeat==1 else None})
            print(f'Verified {route} repeat {repeat}', flush=True)
    return {'schema':'ao_pc_transition_t1_capture_review_v1','source_replays_passed':True,
            'sequences':3,'repeats_per_sequence':3,'replays':results,
            't1_complete':False,'pc_model_passed':False,'performance_tested':False,
            'remaining_t1_evidence':['Display fade and first-visible alignment',
                                     'Player/camera reset semantics and loader acknowledgement boundaries'],
            'runtime_use_permitted':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=ROOT/'reports/transition')
    parser.add_argument('--out',type=Path,default=ROOT/'reports/transition/t1-capture-review.json')
    args=parser.parse_args()
    result=run(args.base.resolve())
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='replays'}))
