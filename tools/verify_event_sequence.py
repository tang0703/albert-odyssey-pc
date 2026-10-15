"""Compare complete scheduler predictions against a detailed source capture.

Device acknowledgements are explicit inputs, not reconstructed event state.
This does not certify PC dialogue input mapping, graphics, or device providers.
"""
import argparse
import hashlib
import json
from pathlib import Path
from event_sequence_reference import Model
from inspect_event_capture import watched
import character_animation
import room_camera


def validate(folder,collect_world=False):
    root=Path(__file__).resolve().parents[2]
    manifest_raw=(folder/'manifest.json').read_bytes()
    manifest=json.loads(manifest_raw.decode('utf-8-sig'))
    if manifest.get('schema')!='ao_ymir_character_capture_manifest_v2' or manifest.get('inputs_unchanged') is not True:
        raise ValueError('Missing completed source manifest')
    records={r['path']:r for r in manifest['outputs']}
    high=(folder/'frame-000000/wram-high.bin').read_bytes()
    low=(folder/'frame-000000/wram-low.bin').read_bytes()
    for name,raw in (('wram-high.bin',high),('wram-low.bin',low)):
        record=records['frame-000000/'+name]
        if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:
            raise ValueError('Changed initial model state')
    source=(root/'work/extract/MAP001.TWN').read_bytes()
    model=Model(high,low,source,(root/'work/extract/TWN.BIN').read_bytes())
    errors=[];observed=[];pending=False;checks=0;updates=0;devices=[];commands=[];initial_tail=False;world=[];verified_queries=[]
    digest=hashlib.sha256()
    for line in (folder/'hooks.jsonl').open('rb'):
        digest.update(line)
        row=json.loads(line);pc=row['pc']
        if pc==0x06091594:
            if pending:raise ValueError('Missing complete update hook')
            signals={'resource_loaded':watched(row,0x06074094,1)[0],
                     'resource_playing':watched(row,0x06074084,1)[0],
                     'text_active':bool(int.from_bytes(watched(row,0x060c51d4,2),'big'))}
            pad=int.from_bytes(watched(row,0x06036642,2),'big')
            model.step(pad,signals);observed=[];pending=True
            devices.append({'update':model.update,'frame':row['frame'],'pad':pad,**signals})
        if pc==0x0609e092:
            if not pending:raise ValueError('Dispatch outside captured logical update')
            offset=int.from_bytes(watched(row,0x060c66bc,4),'big')-0x260e0000+7
            slot=row['r'][14]
            owner='root' if slot==0x060c7fd8 else 'decoration' if int.from_bytes(watched(row,slot+0x14,2),'big')&0x800 else 'actor'
            observed.append((owner,offset,row['r'][11]))
        if pc!=0x060915c4:continue
        if not pending:
            if updates or initial_tail:raise ValueError('Completion without logical update')
            initial_tail=True
        pending=False;updates+=1
        actual_actor=character_animation.state_from_actor(watched(row,0x060c8758,112))
        expected_actor=character_animation.state_from_actor(model.player)
        actual_cameras=[room_camera.state_from_bytes(watched(row,0x060c4288+i*60,60)) for i in range(2)]
        actual_decor=watched(row,0x060ca4c0,60)
        delta={}
        if observed!=model.commands:delta['commands']={'actual':observed,'predicted':model.commands}
        if actual_actor!=expected_actor:delta['actor']={k:[actual_actor[k],expected_actor[k]] for k in actual_actor if actual_actor[k]!=expected_actor[k]}
        if actual_cameras!=model.cameras:delta['cameras']={'actual':actual_cameras,'predicted':model.cameras}
        if actual_decor!=model.decor:delta['decoration']={hex(i):[actual_decor[i],model.decor[i]] for i in range(60) if actual_decor[i]!=model.decor[i]}
        ambient=watched(row,0x060ca4fc,60)
        if ambient!=model.ambient:delta['ambient']={hex(i):[ambient[i],model.ambient[i]] for i in range(60) if ambient[i]!=model.ambient[i]}
        checks+=60
        actual_disabled=watched(row,0x060c41ec,1)[0]
        if actual_disabled!=model.disabled:delta['control']=[actual_disabled,model.disabled]
        if watched(row,0x06036938,1)!=model.story:delta['story']='Source condition byte changed'
        for address,slot in ((0x060c7fd8,model.root),(0x060c8000,model.child)):
            if slot is None:continue
            raw_slot=watched(row,address,40)
            active=bool(int.from_bytes(raw_slot[0x14:0x16],'big')&0x8000)
            waiting=bool(int.from_bytes(raw_slot[0x14:0x16],'big')&0x4000)
            cursor=int.from_bytes(raw_slot[:4],'big')-0x260e0000+8
            actual_slot=(active,waiting,cursor)
            expected_slot=(slot.active,slot.wait is not None,slot.pc)
            if actual_slot!=expected_slot:delta[hex(address)]=[actual_slot,expected_slot]
            checks+=3
        if model.effect is not None:
            raw_effect=watched(row,0x060c87c8,112)
            xy=tuple(int.from_bytes(raw_effect[i:i+2],'big') for i in (0,2))
            if xy!=model.effect_xy:delta['effect_position']=[xy,model.effect_xy]
            checks+=2
            for name,offset in {'flags':6,'cursor':0x2c,'timer':0x30,'duration':0x32,'image':0x34,'animation':0x36}.items():
                value=int.from_bytes(raw_effect[offset:offset+2],'big')
                if value!=getattr(model.effect,name):delta['effect_'+name]=[value,getattr(model.effect,name)]
                checks+=1
        if delta:errors.append({'update':model.update,'frame':row['frame'],'fields':delta})
        verified_queries=sorted(model.queries)
        checks+=len(actual_actor)+16+60+2
        if model.commands:commands.append({'update':model.update,'frame':row['frame'],'commands':model.commands,'requests':model.requests})
        if collect_world:
            world.append({'event_index':row['event_index'],'update':model.update,'frame':row['frame'],
                'player':model.player.hex(),'decor':model.decor.hex(),'ambient':model.ambient.hex(),
                'effect':dict(vars(model.effect)) if model.effect else None,'effect_xy':model.effect_xy,
                'cameras':[dict(c) for c in model.cameras],
                'disabled':model.disabled,'fixed_camera':model.fixed,'camera_target':model.target,'camera_speed':model.speed,
                'root':dict(vars(model.root)) if model.root else None,'child':dict(vars(model.child)) if model.child else None,
                'runs':model.runs,'story':model.story.hex(),'commands':list(model.commands),'requests':list(model.requests)})
    if digest.hexdigest()!=records['hooks.jsonl']['sha256']:raise ValueError('Changed source hook stream')
    if (folder/'manifest.json').read_bytes()!=manifest_raw:raise ValueError('Manifest changed during comparison')
    return {'schema':'ao_pc_event_sequence_device_input_reference_v1','passed':not errors and updates>0,
        'full_event_acceptance':False,'scope':'Continuous scheduler, player, camera and Cirrus from initial state; source resource/text device acknowledgements are inputs.',
        'capture_integrity_required':True,'capture_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),
        'updates':updates,'checks':checks,'runs':model.runs,'errors':errors,'devices':devices,'commands':commands,
        'complete_updates':updates-int(initial_tail),'predicted_updates':model.update,
        'initial_partial_update_checked':initial_tail,'final_update_completion_not_captured':pending,
        'pending_gates':['PC dialogue/device mapping','effect graphics and scene composition','three-repeat synchronization','Godot parity'],
        'query_indices':verified_queries,'world_predictions':world}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=validate(a.capture);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'updates':r['updates'],'runs':r['runs'],'error_count':len(r['errors']),'errors':r['errors'][:3]}))
    raise SystemExit(0 if r['passed'] else 1)
