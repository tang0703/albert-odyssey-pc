"""Compile ninth-stage fixtures only after the sealed L1 source gate."""
import json
from pathlib import Path
from equipment_contract import encoded, canonical
from landing_event_source import ROOT, programs, text_records, sha
from landing_event_actor import Profile
from transition_objects import Resources
from transition_source import landing_contacts, sources
from verify_landing_event_sequence import validate
from verify_equipment_sequence import validate as verify_prefix


def build():
    gate_path = ROOT/'reports/landing-event/l1-acceptance.json'
    gate_raw = gate_path.read_bytes()
    gate = json.loads(gate_raw)
    lock = json.loads((ROOT/'data/landing-event/source-lock.json').read_bytes())
    if not gate.get('l1_complete') or sha(gate_raw) != lock['gate_report_sha256']:
        raise ValueError('L1 landing-event source gate missing or changed')
    base = ROOT/'generated/landing-event'
    (base/'reference').mkdir(parents=True, exist_ok=True)
    queries = set(json.loads((ROOT/'generated/transition/core.json').read_bytes())['landing_query_indices'])
    reports = []
    for name in ('equip', 'remove', 'reequip', 'edge-held'):
        folder = ROOT/'reports/landing-event'/f'l1-{name}-1'
        proof = validate(folder, collect=True)
        if not proof['passed']: raise ValueError('Continuous landing-event model failed')
        prefix = verify_prefix(folder)
        prior = json.loads((ROOT/'generated/equipment/reference'/f"{name if name != 'edge-held' else 'equip'}-stairs.json").read_bytes())
        if [r['input'] for r in prior['updates']] != prefix['devices']:
            raise ValueError('Original-room input prefix changed')
        if prior['terminal']['expected']['player'] != prefix['transition']['player']:
            raise ValueError('Original-room terminal state changed')
        rows = []
        for index, expected in enumerate(proof['predictions']):
            inp = proof['inputs'][index]
            # PC reset generations have no Saturn counterpart. Compare the
            # semantic requests here; exercise generation rejection separately.
            expected['event_state']['requests'] = [{k:v for k,v in request.items() if k != 'generation'}
                                                   for request in expected['event_state']['requests']]
            rows.append({'input': inp,
                         'initialize': inp['stage'] == 'fade_in' and (not rows or rows[-1]['input']['stage'] == 'fade_out'),
                         'expected': {k: v for k, v in expected.items() if k not in ('frame', 'event_index', 'update')}})
        (base/'reference'/f'{name}.json').write_bytes(encoded({'schema': 'ao_pc_landing_event_reference_v1',
            'prefix': prior, 'post_commit': rows, 'capture_manifest_sha256': proof['capture_manifest_sha256']}))
        queries.update(proof['query_indices'])
        reports.append({k: proof[k] for k in ('passed', 'checks', 'prefix_updates', 'transfer_and_landing_updates',
                                            'event_runs', 'event_completed', 'ambient_loops', 'capture_manifest_sha256')})
    resources = Resources(bytes([7])+bytes(127))
    profile = Profile(resources)
    _, source = sources()
    data = {'schema': 'ao_pc_landing_event_core_v1', 'source_acceptance_sha256': sha(gate_raw),
            'programs': programs(), 'actor_program': {
                'sequences': {str(k): list(v) for k, v in profile.sequences.items()},
                'images': {str(i): profile.image_pointer(i) for i in sorted(profile.images)}},
            'trigger': next(c for c in landing_contacts(source) if c.get('script_offset') == 0x2c17),
            'landing_query_indices': sorted(queries), 'viewport_world': [640, 1816, 960, 2040],
            'post_event_equipment_verified': bool(gate.get('post_event_equipment_verified')),
            'runtime_approved': False}
    (base/'core.json').write_bytes(encoded(data))
    (base/'dialogue.json').write_bytes(encoded({'schema': 'ao_pc_landing_event_dialogue_v1', 'records': text_records()}))
    report = {'passed': True, 'runtime_approved': False, 'performance_tested': False,
              'core_sha256': canonical(data), 'routes': reports, 'query_count': len(queries)}
    (ROOT/'reports/landing-event/l2-python.json').write_bytes(encoded(report))
    print(json.dumps(report))
    return report


if __name__ == '__main__': build()
