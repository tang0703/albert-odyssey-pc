"""Q1 source gate; no PC UI, packaging or performance acceptance implied."""
import json
from equipment_contract import ROOT, ROUTES, sha, encoded, source_contract
from verify_equipment_sequence import validate

def build():
    base=ROOT/'reports/equipment';evidence={};routes=[];queries=set()
    expected={'equip-stairs':['equip'],'remove-stairs':['equip','remove'],'reequip-stairs':['equip','remove','equip'],
              'unowned':['remove'],'cancel-owned':[],'hold-equip':['equip'],'cancel-selection':[]}
    for route in ROUTES:
        name=f'q1/{route}-replay.json';raw=(base/name).read_bytes();replay=json.loads(raw);evidence[name]=sha(raw)
        if replay['passed'] is not True or replay['replays']!=3 or replay['differing_outputs']:raise ValueError('Replay incomplete '+route)
        for record in replay['captures']:
            from pathlib import Path
            if sha((Path(record['folder'])/'manifest.json').read_bytes())!=record['manifest_sha256']:raise ValueError('Capture manifest changed')
        report=validate(base/'q1'/f'{route}-a')
        if not report['passed'] or [r['action'] for r in report['equipment_ops']]!=expected[route]:raise ValueError('Unexpected source operations '+route)
        if bool(report['transition'])!=route.endswith('stairs'):raise ValueError('Transition coverage differs')
        if route=='unowned' and any(r['changed'] for r in report['equipment_ops']):raise ValueError('Unowned operation changed state')
        (base/'q1'/f'{route}-model.json').write_bytes(encoded(report))
        evidence[f'q1/{route}-model.json']=sha(encoded(report));queries.update(report['query_indices'])
        routes.append({'route':route,'complete_updates':report['complete_updates'],'checks':report['checks'],
                       'equipment_ops':report['equipment_ops'],'transition':report['transition']})
    for name in ('q1-world.json','q1-render-link.json'):
        raw=(base/name).read_bytes();r=json.loads(raw);evidence[name]=sha(raw)
        if r['passed'] is not True:raise ValueError('Source render gate incomplete')
    world=json.loads((base/'q1-world.json').read_bytes())
    if world['pixels']['passed'] is not True:raise ValueError('Source world pixels differ')
    old=json.loads((ROOT/'exploration-demo/generated/room/room.json').read_bytes())['movement_profile']['verified_query_indices']
    result={'schema':'ao_pc_equipment_source_gate_v1','passed':True,'replays':21,'routes':routes,
        'complete_updates':sum(r['complete_updates'] for r in routes),'checks':sum(r['checks'] for r in routes),
        'verified_query_indices':sorted(queries),'additional_query_indices':sorted(queries-set(old)),
        'source_rules':source_contract(),'world_frames':len(world['frames']),'world_pixels':world['pixels']['compared_world_pixels'],
        'evidence_sha256':evidence,'performance_tested':False,
        'limits':['Semantic menu operations; source menu cursor caches and navigation timing are not PC runtime state.',
                  'Original menu fade excluded from stable world pixel comparison; no player/world masks added.',
                  'Scene request observed normally; PC must stop before 060AC458 commits its destination.']}
    (base/'q1-acceptance.json').write_bytes(encoded(result))
    print(json.dumps({k:result[k] for k in ('passed','replays','complete_updates','checks','world_frames','world_pixels')}))
    return result

if __name__=='__main__':build()
