"""R1 gate: three identical source replays, exact lookup coverage and exit evidence."""
from __future__ import annotations
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import struct

import exploration_movement as movement
import room_boundaries as boundaries
from validate_character_animation import watch
from validate_room_trace import validate as validate_trace
from verify_exploration_replay import inspect, verify as verify_v1

PROJECT = Path(__file__).resolve().parents[1]
MOVEMENT_ROUTES = ('interior', 'contacts', 'perimeter')
BOUNDARY_ROUTES = ('exit-top', 'exit-center', 'exit-bottom')
VIDEO_ROUTES = ('visual-west', 'visual-east')


def component(high: bytes, low: bytes, records: list[dict]) -> dict:
    """Enumerate model candidates only; source union below is the acceptance gate.

    All movement fields participate in the key. No artificial bounding rectangle
    is imposed. A runaway/other-room graph is rejected at the state budget.
    """
    profile = movement.profile_from_snapshot(high, low)
    fields = tuple(movement.FIELDS)
    key = lambda state: tuple(state[field] for field in fields)
    queue = deque([profile.initial_state])
    visited, xy, indices = {key(profile.initial_state)}, set(), set()
    boundary_contacts = set()
    while queue:
        state = queue.popleft()
        xy.add((state['x_word'], state['y_word']))
        for direction in movement.PAD_WORDS:
            proposed, diagnostic = movement.step(state, direction, profile)
            hit = boundaries.contacts(records, proposed['x_word'], proposed['y_word'])
            if hit:
                boundary_contacts.update(hit)
                continue
            indices.update(row['index'] for row in diagnostic['lookups'])
            candidate = key(proposed)
            if candidate not in visited:
                visited.add(candidate)
                queue.append(proposed)
            if len(visited) > 200000:
                raise ValueError('Reachability search escaped the bounded room state budget')
    return {'model_states':len(visited), 'model_positions':len(xy),
            'required_query_indices':sorted(indices), 'reachable_raw_xy':sorted(xy),
            'event_boundary_contacts':sorted(boundary_contacts),
            'scope':'Model component is an audit target; only matching original traces approve lookup indices.'}


def verify_exit(folder: Path) -> dict:
    evidence = inspect(folder)
    high = (folder/'frame-000000/wram-high.bin').read_bytes()
    if hashlib.sha256(high).hexdigest() != evidence['outputs']['frame-000000/wram-high.bin']:
        raise ValueError('Boundary snapshot changed after integrity verification')
    records = boundaries.read_boundaries(high,
        (PROJECT.parent/'work/extract/MAP001.TWN').read_bytes(),
        (PROJECT.parent/'work/extract/TWN.BIN').read_bytes())
    entry, creation, lock = [], [], []
    for row in evidence['hooks']:
        if row['pc'] == 0x060ac458:
            raise ValueError('Scene transition executed; boundary probe escaped the room')
        if row['pc'] not in (0x060ac4a4, 0x060ac4e0, 0x060a14de):
            continue
        table = watch(row, 0x060cb55a, 64)
        if table != high[0xcb55a:0xcb59a]:
            raise ValueError('Runtime event boundary table changed')
        xy = struct.unpack_from('>hh', watch(row, 0x060c8758, 0x70))
        if boundaries.contacts(records, *xy) != ['stair_script_boundary']:
            raise ValueError('Event consumer ran outside the source script boundary')
        if row['pc'] == 0x060ac4a4:
            if row['r'][13] != 0x060cb57a or watch(row,0x060c1e26,2) != b'\0\0':
                raise ValueError('Different event record or event-busy gate')
            entry.append(row)
        elif row['pc'] == 0x060ac4e0:
            if row['r'][5] != records[1]['event_pointer']:
                raise ValueError('Created event differs from the source record')
            creation.append(row)
        else:
            lock.append(row)
    if len(entry) != 1 or len(creation) != 1 or len(lock) != 1:
        raise ValueError('Expected one staircase trigger, creation and control lock')
    if not entry[0]['hook_index'] < creation[0]['hook_index'] < lock[0]['hook_index']:
        raise ValueError('Staircase trigger order differs')
    frames = [r for r in evidence['frames'] if r['frame'] >= lock[0]['frame']]
    if not frames or any(watch(r,0x060c41ec,1) != b'\xff' for r in frames):
        raise ValueError('Source control lock did not persist after the event')
    return {'capture':str(folder), 'manifest_sha256':evidence['manifest_sha256'],
            'trigger_frame':entry[0]['frame'],
            'trigger_raw_xy':list(struct.unpack_from('>hh',watch(entry[0],0x060c8758,0x70))),
            'event_pointer':records[1]['event_pointer'], 'source_records':records,
            'scene_transition_executed':False, 'passed':True}


def run(root: Path, include_video: bool) -> dict:
    rows, reports, indices = {}, {}, set()
    for route in (*MOVEMENT_ROUTES, *BOUNDARY_ROUTES, *(VIDEO_ROUTES if include_video else ())):
        print('Verifying original replay and model: '+route, flush=True)
        folders = [root/f'{route}-{suffix}' for suffix in 'abc']
        if route in VIDEO_ROUTES:
            from verify_character_capture import verify as verify_v2
            replay = verify_v2(folders)
        else:
            replay = verify_v1(folders)
        if not replay['passed']:
            raise ValueError('Original replay changed: '+route)
        rows[route] = replay
        if route in BOUNDARY_ROUTES:
            reports[route] = verify_exit(folders[0])
        else:
            result, fixture = validate_trace(folders[0])
            if not result['passed']:
                raise ValueError('Continuous model differs: '+route)
            indices.update(result['verified_query_indices'])
            reports[route] = result
            (root/f'{route}-fixture.json').write_text(json.dumps(fixture,indent=2)+'\n',encoding='utf-8')
    seed = root/'interior-a/frame-000000'
    high,low = (seed/'wram-high.bin').read_bytes(),(seed/'wram-low.bin').read_bytes()
    records = boundaries.read_boundaries(high,
        (PROJECT.parent/'work/extract/MAP001.TWN').read_bytes(),
        (PROJECT.parent/'work/extract/TWN.BIN').read_bytes())
    coverage = component(high,low,records)
    missing = sorted(set(coverage['required_query_indices'])-indices)
    if missing:
        raise ValueError(f'Original traces have {len(missing)} unobserved candidate lookup cells')
    return {'schema':'ao_pc_room_survey_v1', 'passed':True,
            'stage_r1_complete':include_video, 'route_replays':rows, 'comparisons':reports,
            'verified_query_indices':sorted(indices), 'coverage':coverage,
            'unobserved_required_queries':missing, 'boundaries':records,
            'source_sample_clock':'CPU instruction checkpoints and complete video callbacks remain distinct',
            'limits':['R1 does not approve R3 source pixel composition or R5 delivery.',
                      'The stair script boundary precedes the actual scene exit; neither event runs in the demo.',
                      'Shadow and decoration 6/7 omissions require the later overlap audit.']}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=PROJECT/'reports/room')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--include-video',action='store_true')
    args=parser.parse_args()
    result=run(args.root,args.include_video)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'r1_complete':result['stage_r1_complete'],
                      'routes':len(result['route_replays']), 'verified_queries':len(result['verified_query_indices'])}))
    return 0


if __name__ == '__main__':raise SystemExit(main())
