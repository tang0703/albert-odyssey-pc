"""Compare continuous MAP001 player/camera predictions at source CPU boundaries.

Frame callbacks can interrupt the camera routine. Group by original update
order, never by presumed equal CPU/video frame latency. No later source actor
or camera state is injected into either model.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import character_animation as animation
import room_camera as camera
from validate_character_animation import validate_evidence, watch


def validate(folder: Path) -> tuple[dict, dict]:
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['schema'] == 'ao_ymir_capture_manifest_v1':
        from verify_exploration_replay import inspect
    elif manifest['schema'] == 'ao_ymir_character_capture_manifest_v2':
        from verify_character_capture import inspect
    else:
        raise ValueError('Unsupported capture schema')
    evidence = inspect(folder)
    actor_evidence = dict(evidence)
    actor_evidence['hooks'] = [r for r in evidence['hooks'] if r['pc'] not in camera.CAMERA_PCS]
    actor_report, actor_fixture = validate_evidence(actor_evidence)
    if not actor_report['passed']:
        raise ValueError('Source actor comparison failed')
    def read(name: str) -> bytes:
        raw = (folder/name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != evidence['outputs'][name]:
            raise ValueError('Source changed after verification')
        return raw
    high, low = read('frame-000000/wram-high.bin'), read('frame-000000/wram-low.bin')
    source = (Path(__file__).resolve().parents[2]/'work/extract/TWN.BIN').read_bytes()
    cp = camera.profile_from_snapshot(high, source)
    ap = animation.profile_from_snapshot(high, low)
    actor = dict(ap.initial_state)
    states = [camera.state_from_bytes(high, 0xc4288+slot*60) for slot in (0, 1)]
    initial_cameras = [dict(s) for s in states]
    expected_parameters = high[0xc426c:0xc427e]
    expected_headers = [high[0xc4288+slot*60:0xc4292+slot*60] for slot in (0, 1)]
    stage, current_pad, pending = 'input', None, None
    ordinal, completed, comparisons = 0, 0, 0
    failures, records, queried = [], [], set()
    phases = []
    slots = []
    def mismatch(label, expected, actual, row):
        nonlocal comparisons
        comparisons += 1
        if expected != actual:
            failures.append({'update': ordinal, 'frame': row['frame'], 'pc': row['pc'],
                             'checkpoint': label, 'predicted': expected, 'observed': actual})
    for row in evidence['hooks']:
        pc = row['pc']
        if pc == 0x06094afc:
            if stage != 'input':
                raise ValueError('Next input began before prior camera completed')
            current_pad = int.from_bytes(watch(row, 0x06036642, 2), 'big')
            stage = 'actor'
        if pc not in camera.CAMERA_PCS:
            continue
        block = watch(row, 0x060c4200, 0x100)
        if block[0x6c:0x7e] != expected_parameters:
            raise ValueError('Camera parameters changed')
        for slot in (0, 1):
            if block[0x88+slot*60:0x92+slot*60] != expected_headers[slot]:
                raise ValueError('Camera dispatcher or layer mode changed')
        if pc == 0x060915a0:
            if stage != 'actor' or current_pad is None:
                raise ValueError('Actor/camera update order changed')
            actor, diagnostics = animation.step_game_input(actor, current_pad, ap)
            queried.update(item['index'] for item in diagnostics['movement']['lookups'])
            ordinal += 1
            mismatch('actor before camera', actor,
                     animation.state_from_actor(watch(row, 0x060c8758, 0x70)), row)
            pending = [camera.step(s, (actor['x_word'], actor['y_word']), cp) for s in states]
            phases = [pc]
            slots = []
            stage = 'camera'
        else:
            if stage != 'camera' or pending is None:
                raise ValueError('Camera checkpoint outside a continuous update')
            phases.append(pc)
        if pc == 0x0609b028:
            slot = row['r'][4]
            if slot not in (0, 1):
                raise ValueError('Unexpected active camera slot')
            slots.append(slot)
            copied = dict(states[slot])
            copied.update(display_x=states[slot]['x'], display_y=states[slot]['y'])
            mismatch(f'layer {slot} display copy', copied, camera.state_from_bytes(block, 0x88+slot*60), row)
        if pc == 0x0609b254:
            slot = (row['r'][14]-0x060c4288)//60
            if slot not in (0, 1) or row['r'][14] != 0x060c4288+slot*60:
                raise ValueError('Unbound camera structure')
            slots.append(slot)
            mismatch(f'layer {slot} follow/clamp', pending[slot], camera.state_from_bytes(block, 0x88+slot*60), row)
        if pc == 0x060915a6:
            if phases != [0x060915a0, 0x0609ae32, 0x0609b028, 0x0609b254,
                          0x0609b028, 0x0609b254, 0x060915a6] or slots != [0,0,1,1]:
                raise ValueError('Camera calls reordered, missing or duplicated')
            for slot in (0, 1):
                mismatch(f'layer {slot} completion', pending[slot], camera.state_from_bytes(block, 0x88+slot*60), row)
            states, pending, stage = pending, None, 'input'
            completed += 1
            records.append({'update': ordinal, 'sample_frame': row['frame'], 'pad': current_pad,
                            'actor': dict(actor), 'cameras': [dict(s) for s in states]})
    if not completed or ordinal != actor_report['updates_compared'] or ordinal-completed not in (0, 1):
        raise ValueError('Incomplete or unbound room update stream')
    report = {'schema': 'ao_pc_room_trace_v1', 'passed': not failures,
              'capture': str(folder.resolve()), 'manifest_sha256': evidence['manifest_sha256'],
              'actor_updates': ordinal, 'completed_camera_updates': completed,
              'camera_checkpoints': comparisons, 'mismatches': len(failures),
              'partial_camera_tail': phases if stage == 'camera' else [],
              'prediction': 'Initial state and input words only; no later actor/camera injection',
              'camera_profile': cp.metadata(), 'verified_query_indices': sorted(queried),
              'actor_validation': actor_report, 'failures': failures,
              'limits': ['No room completeness or graphics timing acceptance from this comparison alone.',
                         'A trailing incomplete camera update is explicit and excluded from completed fixtures.']}
    fixture = {'schema': 'ao_pc_room_trace_fixture_v1', 'manifest_sha256': evidence['manifest_sha256'],
               'initial_actor': ap.initial_state, 'initial_cameras': initial_cameras,
               'camera_profile': cp.metadata(), 'updates': records,
               'actor_fixture': actor_fixture}
    return report, fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fixture', type=Path)
    args = parser.parse_args()
    report, fixture = validate(args.capture)
    for path, value in ((args.out, report), (args.fixture, fixture)):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('passed', 'actor_updates', 'completed_camera_updates', 'mismatches')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
