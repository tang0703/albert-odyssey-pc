"""Seal source research only; later Godot, pixels, input and ZIP gates remain."""
import json
from pathlib import Path
from landing_event_source import ROOT, programs, text_records, sha
from verify_landing_event_l1 import review, HISTORIES, SEED_SHA
from verify_landing_event_equipment import validate as equipment_review
from verify_transition_capture import verify_files
from transition_bundle import DEPENDENCIES as OLD_SEVEN
from equipment_contract import canonical, encoded


def seal():
    base = ROOT/'reports/landing-event'
    formal_raw = (base/'l1-formal-review.json').read_bytes()
    formal = json.loads(formal_raw)
    if not formal.get('formal_replays_passed') or len(formal.get('replays', [])) != 9:
        raise ValueError('Nine formal source closures have not passed')
    for row in formal['replays']:
        path = base/f"l1-{row['history']}-{row['repeat']}"/'manifest.json'
        if sha(path.read_bytes()) != row['manifest_sha256']:
            raise ValueError('Formal source manifest changed after closure validation')
    reviews = {name: review(base/f'l1-{name}-1') for name in HISTORIES}
    edge = []
    reference = None
    for repeat in (1, 2, 3):
        folder = base/f'l1-edge-held-{repeat}'
        manifest, files, digest = verify_files(folder)
        if not any(Path(row['path']).suffix == '.savestate' and row['sha256'] == SEED_SHA for row in manifest['inputs']):
            raise ValueError('Input-edge source seed changed')
        if reference is None: reference = files
        elif reference != files: raise ValueError('Input-edge source replay differs')
        edge.append({'repeat':repeat, 'manifest_sha256':digest, 'payloads_identical':True})
        print(f'Input source closure {repeat}', flush=True)
    reviews['edge-held'] = review(base/'l1-edge-held-1')
    parent_raw = (base/'l1-equip-1/manifest.json').read_bytes()
    parent = json.loads(parent_raw.decode('utf-8-sig'))
    state_sha = next(row['sha256'] for row in parent['outputs'] if row['path'] == 'frame-003838/state.savestate')
    equipment = []
    reference = None
    for repeat in (1, 2, 3):
        folder = base/f'l1-post-equipment-{repeat}'
        manifest, files, digest = verify_files(folder)
        if not any(Path(row['path']).suffix == '.savestate' and row['sha256'] == state_sha for row in manifest['inputs']):
            raise ValueError('Post-event equipment seed chain changed')
        if reference is None:
            reference = files
            proof = equipment_review(folder)
        elif reference != files: raise ValueError('Post-event equipment replay differs')
        equipment.append({'repeat':repeat, 'manifest_sha256':digest, 'payloads_identical':True,
                          'proof':proof if repeat == 1 else None})
        print(f'Equipment source closure {repeat}', flush=True)
    dependencies = {**OLD_SEVEN, 'transition':'9e817699364aca759cdb4d8fe87ccab34bc5afc4a6fbd9cf5cdb50d1c9277aa8'}
    for name, digest in dependencies.items():
        if sha((ROOT/'exploration-demo/generated'/name/'package.json').read_bytes()) != digest:
            raise ValueError('Old package identity changed: '+name)
    result = {'schema':'ao_pc_landing_event_l1_acceptance_v1', 'l1_complete':True,
              'baseline_commit':'70f836a7fbcc04fc46380437b7aaea23984ddc73',
              'runtime_approved':False, 'godot_passed':False, 'graphics_passed':False, 'performance_tested':False,
              'formal_closure_report_sha256':sha(formal_raw), 'formal_replays':formal['replays'],
              'continuous_reviews':reviews, 'input_edge_replays':edge, 'post_event_equipment_replays':equipment,
              'post_event_equipment_verified':True,
              'post_event_seed':{'path':'reports/landing-event/l1-equip-1/frame-003838/state.savestate',
                                  'sha256':state_sha, 'parent_manifest_sha256':sha(parent_raw)},
              'programs_sha256':canonical(programs()), 'dialogues_sha256':canonical(text_records()),
              'dependencies':dependencies, 'endpoint':'same_scene_control_restored',
              'remaining_gates':['GDScript continuous parity and ninth local bundle',
                                 'Source pixel/occlusion/presentation timing',
                                 'Interactive controls and complete reset', 'Short screenshot and Windows package checks'],
              'excluded_probe':'l1-post-equipment-probe navigated to System Menu because source cursor is retained; it is not equipment evidence.'}
    raw = encoded(result)
    (base/'l1-acceptance.json').write_bytes(raw)
    lock = {'schema':'ao_pc_landing_event_source_lock_v1', 'baseline_commit':result['baseline_commit'],
            'gate_report_sha256':sha(raw), 'programs_sha256':result['programs_sha256'],
            'dialogues_sha256':result['dialogues_sha256'], 'dependencies':dependencies,
            'l1_complete':True, 'runtime_approved':False, 'performance_tested':False,
            'endpoint':result['endpoint'], 'formal_replay_count':12, 'post_event_equipment_replay_count':3}
    (ROOT/'data/landing-event/source-lock.json').write_bytes(encoded(lock))
    print(json.dumps(lock))
    return result


if __name__ == '__main__': seal()
