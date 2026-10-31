"""Expand the new contract only with actual zero-difference source queries."""
import json
from transition_source import ROOT,sha
from equipment_contract import encoded,canonical
from verify_transition_capture import verify_files
from verify_transition_sequence import validate


def build():
    base=ROOT/'generated/transition'
    data=json.loads((base/'core.json').read_bytes())
    fingerprints=None;results=[];queries=set(data['landing_query_indices'])
    for repeat in (1,2,3):
        folder=ROOT/'reports/transition'/f't3-corridor-{repeat}'
        _,files,digest=verify_files(folder)
        if fingerprints is None:fingerprints=files
        elif files!=fingerprints:raise ValueError('Landing repeat payloads differ')
        result=validate(folder,True)
        if not result['passed']:raise ValueError('Landing continuous model failed')
        queries.update(result['query_indices'])
        results.append({k:result[k] for k in ('checks','capture_manifest_sha256','landing_updates','query_indices')})
        if repeat==1:
            old=json.loads((base/'reference/equip-stairs.json').read_bytes())
            rows=[]
            for index,expected in enumerate(result['predictions']):
                inp=result['inputs'][index]
                rows.append({'input':inp,'initialize':inp['stage']=='fade_in' and (not rows or rows[-1]['input']['stage']=='fade_out'),
                             'expected':{k:v for k,v in expected.items() if k not in ('frame','event_index','update')}})
            fixture={'schema':'ao_pc_transition_reference_v1','prefix':old['prefix'],'post_commit':rows,'capture_manifest_sha256':digest}
            (base/'reference/landing-corridor.json').write_bytes(encoded(fixture))
    data['landing_query_indices']=sorted(queries)
    data['landing_coverage']={'route':'landing-corridor','repeats':3,'capture_manifest_sha256':[r['capture_manifest_sha256'] for r in results],
                              'scope':'Actual source lookup union within first control viewport; not a filled rectangle or whole destination room.'}
    (base/'core.json').write_bytes(encoded(data))
    report={'passed':True,'replays':results,'approved_query_count':len(queries),'core_sha256':canonical(data),
            'performance_tested':False,'graphics_passed':False,'runtime_approved':False}
    (ROOT/'reports/transition/t3-reference.json').write_bytes(encoded(report))
    print(json.dumps(report))


if __name__=='__main__':build()
