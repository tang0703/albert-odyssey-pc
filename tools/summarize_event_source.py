"""D1 source gate, with no PC runtime, UI, performance or delivery claim."""
import argparse
import hashlib
import json
from pathlib import Path
from event_contract import build
from verify_event_capture_links import ROUTES,compare_outputs

ROOT=Path(__file__).resolve().parents[1]


def sha(raw):return hashlib.sha256(raw).hexdigest()


def summarize(root):
    evidence={};routes=[];queries=set();totals={'logical_checkpoints':0,'complete_updates':0,'field_checks':0,'world_draws':0,'world_pixels':0,'source_replays':0}
    def report(path):
        raw=path.read_bytes();value=json.loads(raw.decode('utf-8-sig'))
        if value.get('passed') is not True:raise ValueError('Unpassed D1 gate: '+str(path))
        evidence[path.relative_to(root).as_posix()]=sha(raw);return value
    for route in ROUTES:
        replay=report(root/'d1-v1'/f'{route}-replay.json')
        link=report(root/f'd1-{route}-capture-link.json')
        world=report(root/f'd1-{route}-world-pixels-v3.json')
        model=report(root/f'd1-{route}-sequence-model.json')
        text=report(root/f'd1-{route}-text-input.json')
        paths={name:root/f'd1-{name}'/f'{route}-a' for name in ('v1','render','detail')}
        manifests={name:json.loads((path/'manifest.json').read_text(encoding='utf-8-sig')) for name,path in paths.items()}
        identities={name:sha((path/'manifest.json').read_bytes()) for name,path in paths.items()}
        for name in ('render','detail'):
            if manifests[name]['inputs']!=manifests['v1']['inputs'] or manifests[name]['build']!=manifests['v1']['build']:
                raise ValueError('Different source inputs or observer build')
            compare_outputs({r['path']:r['sha256'] for r in manifests[name]['outputs']},
                            {r['path']:r['sha256'] for r in manifests['v1']['outputs']})
        if (world['capture_manifest_sha256']!=identities['render'] or model['capture_manifest_sha256']!=identities['detail']
            or link['render_manifest_sha256']!=identities['render'] or link['formal_manifest_sha256']!=identities['v1']
            or text['capture_manifest_sha256']!=identities['render']
            or world['pixels']['capture_manifest_sha256']!=identities['v1']
            or link['replay_report_sha256']!=evidence[f'd1-v1/{route}-replay.json']):
            raise ValueError('D1 report source identities do not agree')
        if replay['replays']!=3 or replay['differing_outputs'] or model['errors'] or world['errors'] or world['pixels']['errors']:
            raise ValueError('Incomplete or differing D1 evidence')
        for capture in replay['captures']:
            if sha((Path(capture['folder'])/'manifest.json').read_bytes())!=capture['manifest_sha256']:raise ValueError('Formal source manifest changed')
        if model['runs']!=(2 if route=='reenter' else 1):raise ValueError('Wrong event count')
        if len(text['accepted_confirmations'])!=(0 if route=='wait' else 4 if route=='reenter' else 2):raise ValueError('Wrong source confirmation count')
        if len(world['frames'])!=model['complete_updates'] or len(world['pixels']['frames'])!=replay['frames_per_replay']-2:
            raise ValueError('Missing source logical/draw/video coverage')
        if any(row['unexplained_pixels'] for row in world['pixels']['frames']):raise ValueError('Unexplained world pixels')
        totals['logical_checkpoints']+=model['updates'];totals['complete_updates']+=model['complete_updates']
        totals['field_checks']+=model['checks'];totals['world_draws']+=len(world['frames'])
        totals['world_pixels']+=world['pixels']['compared_world_pixels'];totals['source_replays']+=3
        queries.update(model['query_indices'])
        routes.append({'id':route,'event_runs':model['runs'],'checkpoints':model['updates'],'complete_updates':model['complete_updates'],
                       'source_frames':replay['frames_per_replay'],'identities':identities})
    contract=build()
    return {'schema':'ao_pc_cirrus_source_acceptance_v1','passed':True,'stage':'D1','pc_event_acceptance':False,
        'totals':totals,'routes':routes,'verified_query_indices':sorted(queries),'evidence':evidence,
        'source_contract_sha256':sha((json.dumps(contract,ensure_ascii=False,indent=2)+'\n').encode('utf-8')),
        'scope':'Captured initial story branch, complete script semantics, control return/reentry, source animation and world composition.',
        'limits':['Device acknowledgements are explicit external inputs; PC adapters remain D2/D3 work.',
                  'Initial partial logic remainder is checked separately; trailing incomplete updates are excluded.',
                  'First two inherited videos, original UI line-window/palette pixels and player shadow are excluded from world pixel parity.',
                  'D2/D3/D4, adjacent scenes and whole Stage B are not accepted.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'reports/event');a=p.parse_args()
    try:result=summarize(a.root)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result={'schema':'ao_pc_cirrus_source_acceptance_v1','passed':False,'stage':'D1','pc_event_acceptance':False,'error':str(exc)}
    path=a.root/'d1-acceptance.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result.get('totals',result)))
    raise SystemExit(0 if result['passed'] else 1)
