"""Save source-compared initial-state/inputs/expected-state fixtures locally."""
import json
from pathlib import Path
from verify_event_sequence import validate
from verify_event_capture_links import ROUTES

ROOT=Path(__file__).resolve().parents[1]


if __name__=='__main__':
    out=ROOT/'generated/event/reference';out.mkdir(parents=True,exist_ok=True)
    for route in ROUTES:
        print('Comparing complete event sequence '+route,flush=True)
        report=validate(ROOT/'reports/event/d1-detail'/f'{route}-a',collect_world=True)
        if not report['passed']:raise ValueError('Failed source sequence '+route)
        states=report.pop('world_predictions')
        if states[0]['update']!=0 or len(states)!=report['updates']:raise ValueError('Missing initial source remainder')
        devices={r['update']:r for r in report['devices']}
        if [s['update'] for s in states]!=list(range(len(states))):raise ValueError('Noncontiguous logical comparison points')
        fixture={'schema':'ao_pc_cirrus_reference_fixture_v1','capture_manifest_sha256':report['capture_manifest_sha256'],
                 'initial_state':states[0],'updates':[{'input':devices[s['update']],'expected':s} for s in states[1:]],
                 'limits':report['scope'],'trailing_unfinished_update_excluded':report['final_update_completion_not_captured']}
        (out/f'{route}.json').write_text(json.dumps(fixture,indent=2)+'\n',encoding='utf-8')
        (ROOT/'reports/event'/f'd1-{route}-sequence-model.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'route':route,'passed':report['passed'],'checks':report['checks'],'complete_updates':len(fixture['updates'])}),flush=True)
