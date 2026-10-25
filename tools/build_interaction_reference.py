"""Build initial-state/input fixtures only after continuous source comparison."""
import json
from pathlib import Path
from verify_interaction_sequence import validate
from summarize_interaction_source import ROUTES

ROOT=Path(__file__).resolve().parents[1]


if __name__=='__main__':
    gate=json.loads((ROOT/'reports/interaction/p1-acceptance.json').read_text())
    if gate.get('passed') is not True:raise ValueError('P1 must pass first')
    output=ROOT/'generated/interaction/reference';output.mkdir(parents=True,exist_ok=True)
    for route in ROUTES:
        base='p1-v1' if route in ('direct','reminder-first') else 'p1-v2'
        report=validate(ROOT/'reports/interaction'/base/f'{route}-a',collect_world=True)
        if not report['passed']:raise ValueError('Source model failed '+route)
        states=report.pop('world_predictions');devices={r['update']:r for r in report['devices']}
        if [s['update'] for s in states]!=list(range(len(states))):raise ValueError('Noncontiguous source states')
        fixture={'schema':'ao_pc_interaction_reference_v1','capture_manifest_sha256':report['capture_manifest_sha256'],
                 'initial_state':states[0],'updates':[{'input':devices[s['update']],'expected':s} for s in states[1:]],
                 'trailing_unfinished_update_excluded':report['final_update_completion_not_captured']}
        (output/f'{route}.json').write_text(json.dumps(fixture,indent=2)+'\n',encoding='utf-8')
        print(route,len(fixture['updates']),flush=True)
