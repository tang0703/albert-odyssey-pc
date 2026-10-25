"""Q2 fixtures bind semantic operations to continuously verified source updates."""
import json
from equipment_contract import ROOT, ROUTES, build, encoded, sha, canonical
from verify_equipment_sequence import validate
from equipment_pc_reference import PcModel

def snapshot(m):
    return {'player':m.player.hex(),'decor':m.decor.hex(),'ambient':m.ambient.hex(),
        'effect':vars(m.effect) if m.effect else None,'effect_xy':list(m.effect_xy) if m.effect_xy else None,
        'cameras':m.cameras,'disabled':m.disabled,'fixed_camera':m.fixed,'camera_target':m.target,'camera_speed':m.speed,
        'root':vars(m.root) if m.root else None,'child':vars(m.child) if m.child else None,
        'runs':m.runs,'story':m.story.hex(),'commands':[list(c) for c in m.commands],'requests':m.requests,'update':m.update,
        'spark':m.spark.hex() if m.spark is not None else None,'spark_child':vars(m.spark_child) if m.spark_child else None,
        'temporary_coordinates':{str(k):list(v) for k,v in m.temp.items()},'item_count':m.item_count,'resource':m.resource,
        'weapon':m.weapon,'attack':m.attack,'transition_pending':m.transition_pending}

def build_all():
    base=ROOT/'reports/equipment';gate_raw=(base/'q1-acceptance.json').read_bytes();gate=json.loads(gate_raw)
    if gate['passed'] is not True:raise ValueError('Q1 required')
    output=ROOT/'generated/equipment';(output/'reference').mkdir(parents=True,exist_ok=True)
    contract=build();data=json.loads((ROOT/'generated/interaction/core.json').read_bytes())
    data['schema']='ao_pc_equipment_core_v1';data['contract']=contract
    data['source_acceptance_sha256']=sha(gate_raw);data['additional_query_indices']=gate['additional_query_indices']
    for key in ('event_index','frame'):data['initial_state'].pop(key,None)
    data['initial_state'].update(weapon=255,attack=10,transition_pending=False)
    (output/'core.json').write_bytes(encoded(data))
    checks=0;routes=[]
    for route in ROUTES:
        folder=base/'q1'/f'{route}-a';report=validate(folder,True)
        if not report['passed']:raise ValueError('Source model failed')
        states=report['world_predictions'];devices={r['update']:r for r in report['devices']}
        if [s['update'] for s in states]!=list(range(len(states))):raise ValueError('Noncontiguous source states')
        seed=folder/'frame-000000';source=ROOT.parent/'work/extract'
        m=PcModel((seed/'wram-high.bin').read_bytes(),(seed/'wram-low.bin').read_bytes(),
                  (source/'MAP001.TWN').read_bytes(),(source/'TWN.BIN').read_bytes(),contract)
        if snapshot(m)!=data['initial_state']:raise ValueError('Initial state mismatch')
        rows=[]
        for state in states[1:]:
            inp=devices[state['update']];ops=[r['action'] for r in report['equipment_ops'] if r['before_update']==state['update']-1]
            for op in ops:m.equipment(op)
            m.step(inp['pad'],{k:inp[k] for k in ('resource_loaded','resource_playing','text_active')},inp['pressed'])
            expected={k:v for k,v in state.items() if k not in ('event_index','frame')}
            expected=json.loads(json.dumps(expected))
            if snapshot(m)!=expected:raise ValueError(f'PC model mismatch {route} {state["update"]}: {[k for k in expected if snapshot(m)[k]!=expected[k]]}')
            checks+=len(expected);rows.append({'equipment':ops,'input':inp,'expected':expected})
        terminal=None
        if report['transition']:
            pad=report['transition']['pad'];m.step(pad,{'resource_loaded':0,'resource_playing':0,'text_active':False})
            if m.player.hex()!=report['transition']['player'] or not m.transition_pending:raise ValueError('Boundary state differs')
            terminal={'pad':pad,'expected':snapshot(m)}
        fixture={'schema':'ao_pc_equipment_reference_v1','capture_manifest_sha256':report['capture_manifest_sha256'],
            'initial_state':data['initial_state'],'updates':rows,'terminal':terminal}
        (output/'reference'/f'{route}.json').write_bytes(encoded(fixture));routes.append({'route':route,'updates':len(rows)})
    result={'passed':True,'checks':checks,'routes':routes,'source_gate_sha256':sha(gate_raw),'core_sha256':canonical(data),'programs_sha256':canonical(contract['programs'])}
    (base/'q2-python.json').write_bytes(encoded(result));print(json.dumps(result))
    return result

if __name__=='__main__':build_all()
