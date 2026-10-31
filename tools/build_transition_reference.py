"""Compile source-derived landing initializers and verified GDScript fixtures."""
import json
from transition_source import ROOT,ROUTES,sha,build
from transition_initialization import initialize_player,initialize_camera,camera_profile
from transition_objects import Resources,initialize_objects,initialize_actor
from verify_transition_sequence import validate
from verify_equipment_sequence import validate as prefix_validate
from equipment_contract import canonical,encoded
import character_animation


def build_all():
    gate=(ROOT/'reports/transition/t1-acceptance.json').read_bytes()
    lock=json.loads((ROOT/'data/transition/source-lock.json').read_bytes())
    if sha(gate)!=lock['gate_report_sha256'] or not json.loads(gate)['t1_complete']:
        raise ValueError('T1 source acceptance missing or changed')
    base=ROOT/'generated/transition';(base/'reference').mkdir(parents=True,exist_ok=True)
    seed=ROOT/'reports/exploration/e1-nav-05/frame-000600'
    high=(seed/'wram-high.bin').read_bytes();low=(seed/'wram-low.bin').read_bytes()
    story=bytes([7])+high[0x36939:0x369b8];resources=Resources(story)
    objects,programs=initialize_objects(resources);npc,npc_profile=initialize_actor(resources)
    profile=character_animation.profile_from_snapshot(high,low)
    source=build(story)
    queries=set();reports=[]
    for route in ROUTES:
        capture=ROOT/'reports/transition'/f't1-{route}-1'
        result=validate(capture,True)
        if not result['passed']:raise ValueError('Continuous source model failed')
        prefix=prefix_validate(capture)
        old=json.loads((ROOT/'generated/equipment/reference'/f'{route}.json').read_bytes())
        if ([r['input'] for r in old['updates']]!=prefix['devices']
                or old['terminal']['expected']['player']!=prefix['transition']['player']):
            raise ValueError('Old equipment fixture does not match new continuous prefix')
        queries.update(result['query_indices'])
        rows=[]
        for index,expected in enumerate(result['predictions']):
            inp=result['inputs'][index]
            rows.append({'input':inp,'initialize':inp['stage']=='fade_in' and (not rows or rows[-1]['input']['stage']=='fade_out'),
                         'expected':{k:v for k,v in expected.items() if k!='frame'}})
        (base/'reference'/f'{route}.json').write_bytes(encoded({'schema':'ao_pc_transition_reference_v1',
            'prefix':old,'post_commit':rows,'capture_manifest_sha256':result['capture_manifest_sha256']}))
        reports.append({k:result[k] for k in ('passed','checks','prefix_updates','transfer_and_landing_updates','landing_updates','capture_manifest_sha256')})
    data={'schema':'ao_pc_transition_core_v1','source_acceptance_sha256':sha(gate),
          'destination':source['destination'],'initialization':source['initialization'],
          'player_initializer':initialize_player(high,low,profile).hex(),
          'camera_initializer':initialize_camera((0x3880,0x7780),camera_profile(story)),
          'camera_limits_raw':list(camera_profile(story).limits),
          'object_initializers':[r.hex() for r in objects],
          'object_programs':[{'sequence':list(p.sequence),'images':{str(k):v for k,v in p.images.items()}} for p in programs],
          'actor_initializer':npc.hex(),'actor_program':{'sequence':list(npc_profile.seq),'image_pointer':npc_profile.image_pointer(3)},
          'landing_query_indices':sorted(queries),'contacts':next(r['contacts'] for r in source['initialization'] if r['opcode']==0x18),
          'viewport_world':[640,1816,960,2040],'runtime_approved':False,
          'source_initializers_basis':'Compiled original operands and resource headers, independently compared to source; not captured post-transfer RAM.'}
    (base/'core.json').write_bytes(encoded(data))
    report={'passed':True,'core_sha256':canonical(data),'routes':reports,'performance_tested':False,'runtime_approved':False}
    (ROOT/'reports/transition/t2-python.json').write_bytes(encoded(report))
    print(json.dumps(report))
    return report


if __name__=='__main__':build_all()
