"""Compare complete scheduler predictions against a detailed source capture.

Device acknowledgements are explicit inputs, not reconstructed event state.
This does not certify PC dialogue input mapping, graphics, or device providers.
"""
import argparse
import hashlib
import json
from pathlib import Path
from equipment_sequence_reference import Model
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
    errors=[];observed=[];pending=False;checks=0;updates=0;devices=[];commands=[];initial_tail=False;world=[];verified_queries=[];final_observed=None;equipment_ops=[];transition=None
    digest=hashlib.sha256()
    for line in (folder/'hooks.jsonl').open('rb'):
        digest.update(line)
        row=json.loads(line);pc=row['pc']
        if transition is not None:continue
        if pc==0x06017ede:
            index=4*row['r'][11]+row['r'][13]
            selected=watched(row,0x06036aac+index,1)[0]
            if selected not in (27,254):raise ValueError('Unverified equipment selection')
            action='equip' if selected==27 else 'remove'
            changed=model.equipment(action)
            equipment_ops.append({'frame':row['frame'],'before_update':model.update,'action':action,'changed':changed,'weapon':model.weapon,'item_count':model.item_count,'attack':model.attack,'story':model.story.hex()})
        if pc in (0x06018226,0x06018248):
            actual=(watched(row,0x060366b7,1)[0],watched(row,0x060367cf,1)[0],int.from_bytes(watched(row,0x060366a0,2),'big'),watched(row,0x06036938,1).hex())
            expected=(model.weapon,model.item_count,model.attack,model.story.hex())
            if actual!=expected:errors.append({'frame':row['frame'],'equipment_actual':actual,'expected':expected})
            checks+=4
        if pc==0x060ac458:
            import room_boundaries
            if 'stair_scene_boundary' not in room_boundaries.contacts(model.boundaries,*[int.from_bytes(model.player[i:i+2],'big',signed=True) for i in (0,2)]):raise ValueError('Unexpected scene trigger')
            model.step(int.from_bytes(watched(row,0x06036642,2),'big'),{'resource_loaded':0,'resource_playing':0,'text_active':False})
            if watched(row,0x060c8758,112)!=model.player:errors.append({'frame':row['frame'],'transition_player':'mismatch'})
            transition={'frame':row['frame'],'update':model.update,'player':model.player.hex(),'record':watched(row,0x060cb55a,32).hex(),'scene_commit_performed':False}
            continue
        if pc==0x06091594:
            if pending:raise ValueError('Missing complete update hook')
            signals={'resource_loaded':watched(row,0x06074094,1)[0],
                     'resource_playing':watched(row,0x06074084,1)[0],
                     'text_active':bool(int.from_bytes(watched(row,0x060c51d4,2),'big'))}
            pad=int.from_bytes(watched(row,0x06036642,2),'big')
            pressed=int.from_bytes(watched(row,0x06036646,2),'big')
            model.step(pad,signals,pressed);observed=[];pending=True
            devices.append({'update':model.update,'frame':row['frame'],'pad':pad,'pressed':pressed,**signals})
        if pc==0x0609e092:
            if not pending:raise ValueError('Dispatch outside captured logical update')
            offset=int.from_bytes(watched(row,0x060c66bc,4),'big')-0x260e0000+7
            slot=row['r'][14]
            owner='root' if slot==0x060c7fd8 else 'spark' if slot==0x060c8028 else 'decoration' if int.from_bytes(watched(row,slot+0x14,2),'big')&0x800 else 'actor'
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
        player_raw=watched(row,0x060c8758,112)
        for start,size in ((0x12,2),(0x16,2),(0x2a,2),(0x38,2),(0x49,1)):
            if player_raw[start:start+size]!=model.player[start:start+size]:
                delta[f'player_{start:02x}']=[player_raw[start:start+size].hex(),model.player[start:start+size].hex()]
            checks+=1
        if actual_cameras!=model.cameras:delta['cameras']={'actual':actual_cameras,'predicted':model.cameras}
        if actual_decor!=model.decor:delta['decoration']={hex(i):[actual_decor[i],model.decor[i]] for i in range(60) if actual_decor[i]!=model.decor[i]}
        ambient=watched(row,0x060ca4fc,60)
        if ambient!=model.ambient:delta['ambient']={hex(i):[ambient[i],model.ambient[i]] for i in range(60) if ambient[i]!=model.ambient[i]}
        checks+=60
        actual_disabled=watched(row,0x060c41ec,1)[0]
        if actual_disabled!=model.disabled:delta['control']=[actual_disabled,model.disabled]
        if watched(row,0x06036938,1)!=model.story:delta['story']='Source condition byte changed'
        if watched(row,0x060367cf,1)[0]!=model.item_count:delta['item_count']=[watched(row,0x060367cf,1)[0],model.item_count]
        inventory=bytearray(high[0x367b4:0x368b4]);inventory[0x1b]=model.item_count
        actual_inventory=watched(row,0x060367b4,256)
        if actual_inventory!=inventory:delta['inventory']='Unexplained source inventory change'
        checks+=256
        party=bytearray(high[0x3666c:0x367b4]);party[0x4b]=model.weapon;party[0x34:0x36]=model.attack.to_bytes(2,'big')
        if watched(row,0x0603668c,260)!=party[32:292]:delta['party_members']={hex(i):[watched(row,0x0603666c,328)[i],party[i]] for i in range(32,292) if watched(row,0x0603666c,328)[i]!=party[i]}
        checks+=260
        if model.temp and any(w['address']==0x060c41fc for w in row['watches']):
            raw_temp=watched(row,0x060c4226,6)
            expected_temp=b''.join(v.to_bytes(2,'big') for v in model.temp[7])
            if raw_temp!=expected_temp:delta['temporary_coordinates']=[raw_temp.hex(),expected_temp.hex()]
            checks+=3
        for address,slot in ((0x060c7fd8,model.root),(0x060c8000,model.child),(0x060c8028,model.spark_child)):
            if slot is None:continue
            raw_slot=watched(row,address,40)
            active=bool(int.from_bytes(raw_slot[0x14:0x16],'big')&0x8000)
            waiting=bool(int.from_bytes(raw_slot[0x14:0x16],'big')&0x4000)
            cursor=int.from_bytes(raw_slot[:4],'big')-0x260e0000+8
            actual_slot=(active,waiting,cursor)
            expected_slot=(slot.active,slot.wait is not None,slot.pc)
            if actual_slot!=expected_slot:delta[hex(address)]=[actual_slot,expected_slot]
            checks+=3
        if model.spark is not None and not (model.effect and model.effect.flags&0x8000):
            raw_spark=watched(row,0x060c87c8,112)
            if raw_spark!=model.spark:
                delta['spark']={hex(i):[raw_spark[i],model.spark[i]] for i in range(112) if raw_spark[i]!=model.spark[i]}
            checks+=112
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
        final_observed={'frame':row['frame'],'story':watched(row,0x06036938,1).hex(),
            'item_count':watched(row,0x060367cf,1)[0],'control_disabled':actual_disabled,
            'player_xy_raw':[int.from_bytes(player_raw[i:i+2],'big') for i in (0,2)],
            'root_active':bool(int.from_bytes(watched(row,0x060c7fec,2),'big')&0x8000)}
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
            world[-1].update(spark=model.spark.hex() if model.spark is not None else None,
                spark_child=dict(vars(model.spark_child)) if model.spark_child else None,
                item_count=model.item_count,temporary_coordinates={str(k):list(v) for k,v in model.temp.items()},resource=model.resource,weapon=model.weapon,attack=model.attack,transition_pending=model.transition_pending)
    if digest.hexdigest()!=records['hooks.jsonl']['sha256']:raise ValueError('Changed source hook stream')
    if (folder/'manifest.json').read_bytes()!=manifest_raw:raise ValueError('Manifest changed during comparison')
    return {'schema':'ao_pc_interaction_sequence_device_input_reference_v1','passed':not errors and updates>0,
        'full_event_acceptance':False,'scope':'Continuous scheduler, player, camera and Cirrus from initial state; source resource/text device acknowledgements are inputs.',
        'capture_integrity_required':True,'capture_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),
        'updates':updates,'checks':checks,'runs':model.runs,'errors':errors,'devices':devices,'commands':commands,
        'complete_updates':updates-int(initial_tail),'predicted_updates':model.update,
        'initial_partial_update_checked':initial_tail,'final_update_completion_not_captured':pending,
        'pending_gates':['PC dialogue/device mapping','effect graphics and scene composition','three-repeat synchronization','Godot parity'],
        'equipment_ops':equipment_ops,'transition':transition,'query_indices':verified_queries,'world_predictions':world,'final_observed':final_observed}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=validate(a.capture);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'updates':r['updates'],'runs':r['runs'],'error_count':len(r['errors']),'errors':r['errors'][:3]}))
    raise SystemExit(0 if r['passed'] else 1)
