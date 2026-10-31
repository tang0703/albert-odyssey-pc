"""Continuous original-room/transfer/landing reference comparison.

External inputs are source pad edges, semantic equipment requests and named
text/audio/resource completions. No later actor/camera/flag value is fed back.
"""
import argparse
import json
from pathlib import Path
from inspect_event_capture import watched
from verify_equipment_sequence import validate as verify_prefix
from transition_reference import Model
from transition_source import ROOT
import room_camera


def validate(folder,collect=False):
    prefix=verify_prefix(folder)
    if not prefix['passed'] or not prefix['transition']:raise ValueError('Original-room reference failed')
    initial=folder/'frame-000000'
    high=(initial/'wram-high.bin').read_bytes();low=(initial/'wram-low.bin').read_bytes()
    model=Model(high,low,(ROOT.parent/'work/extract/MAP001.TWN').read_bytes(),(ROOT.parent/'work/extract/TWN.BIN').read_bytes())
    operations=list(prefix['equipment_ops'])
    for device in prefix['devices']:
        while operations and operations[0]['before_update']==model.room.update:
            model.equipment(operations.pop(0)['action'])
        model.step(device['pad'],{k:device[k] for k in ('resource_loaded','resource_playing','text_active')},device['pressed'])
    while operations and operations[0]['before_update']==model.room.update:
        model.equipment(operations.pop(0)['action'])
    if operations:raise ValueError('Unconsumed equipment input')
    model.step(prefix['transition']['pad'],{'resource_loaded':0,'resource_playing':0,'text_active':False})
    if model.stage!='fade_out':raise ValueError('Predicted room flow did not request transfer')
    active=False;first=True;pending=False;initialized=False;errors=[];checks=prefix['checks'];updates=0;states=[];inputs=[]
    observed_commands=[];begin=False
    for line in (folder/'hooks.jsonl').open(encoding='utf-8'):
        row=json.loads(line);pc=row['pc']
        if pc==0x060ac458:
            if active:raise ValueError('Repeated source transfer')
            active=True
        if not active:continue
        init_entry=(pc==0x0609e092 and int.from_bytes(watched(row,0x060c66bc,4),'big')==0x260e1000)
        if not begin and not initialized and (pc==0x060933b8 or init_entry):
            # Fade completion performs no actor update. There are then no
            # normal hooks during source collision decode/display upload.
            model.step(0)
            if model.stage!='loading':raise ValueError('Source initialized before predicted black completion')
            begin=True
        if begin and pc==0x0609e092:
            offset=int.from_bytes(watched(row,0x060c66bc,4),'big')-0x260e0000+7
            observed_commands.append((offset,row['r'][11]))
        if begin and pc==0x0609e096 and int.from_bytes(watched(row,0x060c66bc,4),'big')==0x260e10e4:
            # Source END uses a two-byte span and leaves cursor at file 10EC.
            accepted=model.scene_resources_ready(model.generation,'map001_scene7_resources')
            if not accepted:raise ValueError('Unexpected scene-resource completion')
            expected=[(c['offset'],c['opcode']) for c in model.commands]
            if expected!=observed_commands:raise ValueError('Predicted initializer command stream differs')
            initialized=True;begin=False
            checks+=len(expected)*2
        if pc==0x06091594:
            if pending:raise ValueError('Overlapping logical update')
            pad=int.from_bytes(watched(row,0x06036642,2),'big')
            if first:first=False
            else:model.step(pad,source_replay=True)
            pending=True;inputs.append({'frame':row['frame'],'pad':pad,'stage':model.stage})
        if pc==0x060915a0 and pending:
            actual=watched(row,0x060c8758,112)
            if actual!=model.player:errors.append({'frame':row['frame'],'player':{hex(i):[actual[i],model.player[i]] for i in range(112) if actual[i]!=model.player[i]}})
            checks+=112
            if initialized:
                actual=watched(row,0x060c87c8,112)
                if actual!=model.arrival_actor:errors.append({'frame':row['frame'],'arrival_actor':'mismatch'})
                checks+=112
        if pc==0x060915a6 and pending:
            actual=[room_camera.state_from_bytes(watched(row,0x060c4288+i*60,60)) for i in range(2)]
            if actual!=model.cameras:errors.append({'frame':row['frame'],'camera':[actual,model.cameras]})
            checks+=16
        if pc==0x060915b2 and pending:
            if initialized:
                for slot,obj in enumerate(model.objects):
                    actual=watched(row,0x060ca358+slot*60,60)
                    if actual!=obj:errors.append({'frame':row['frame'],'object':slot,'fields':{hex(i):[actual[i],obj[i]] for i in range(60) if actual[i]!=obj[i]}})
                    checks+=60
            phase=int.from_bytes(watched(row,0x060c27aa,2),'big')
            if phase!=model.fade:errors.append({'frame':row['frame'],'fade':[phase,model.fade]})
            values=(watched(row,0x060366b7,1)[0],watched(row,0x060367cf,1)[0],int.from_bytes(watched(row,0x060366a0,2),'big'),watched(row,0x06036938,1),watched(row,0x060c41ec,1)[0])
            predicted=(model.room.weapon,model.room.item_count,model.room.attack,model.room.story,model.room.disabled)
            if values!=predicted:errors.append({'frame':row['frame'],'persistent_or_control':'mismatch'})
            checks+=6;updates+=1;pending=False
            if collect:states.append({'frame':row['frame'],'scene':model.scene,'stage':model.stage,'fade':model.fade,'rgb':list(model.rgb),
                'player':model.player.hex(),'cameras':[dict(c) for c in model.cameras],
                'objects':[o.hex() for o in model.objects],'arrival_actor':model.arrival_actor.hex() if model.arrival_actor else None})
    if not initialized or model.stage!='landing' or not model.landing_updates:raise ValueError('Incomplete continuous landing replay')
    return {'schema':'ao_pc_transition_continuous_reference_v1','passed':not errors,'checks':checks,
            'prefix_updates':prefix['updates'],'transfer_and_landing_updates':updates,'landing_updates':model.landing_updates,
            'query_indices':sorted(model.landing_queries),'errors':errors,'inputs':inputs,'predictions':states,
            'initialization_commands':len(observed_commands),'godot_passed':False,'graphics_passed':False,
            'performance_tested':False,'capture_manifest_sha256':prefix['capture_manifest_sha256'],
            'scope':'Continuous predicted state from original named room seed; no later source state backfill. Source device completion timing is an explicit input.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--collect',action='store_true')
    a=p.parse_args();r=validate(a.capture.resolve(),a.collect)
    a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k not in ('predictions','inputs','errors','query_indices')}))
    print(json.dumps(r['errors'][:5]));raise SystemExit(0 if r['passed'] else 1)
