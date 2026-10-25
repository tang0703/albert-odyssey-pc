"""Convert the observed pickup/unequipped branches to bounded PC instructions.

Equipped-story execution remains unsupported. This conversion alone is not a
source, Godot, display, input, or release acceptance result.
"""
import argparse
import json
from pathlib import Path
import event_contract
from pipeline import import_dialogue
from interaction_trigger import MAP_SHA

ROOT=Path(__file__).resolve().parents[1]
PROGRAMS={**event_contract.PROGRAMS,'equip_entry':(0x2f2f,0x2f3c),'equip_warning':(0x2f83,0x2fb2),
          'pickup_entry':(0x2fb4,0x2fc3),'pickup':(0x2fc3,0x2fe6),
          'pickup_actor':(0x1e95,0x1edc),'spark':(0x1edc,0x1ee1)}
LENGTHS={**event_contract.LENGTHS,0x1f:3,0x30:3,0x37:3,0x4c:3,0x57:2,
         0x5f:2,0x60:5,0x61:2,0x6b:4,0x6c:9,0x72:7,0x81:4}
TEXT_IDS={1:'map001_00afe2',2:'map001_00b061',3:'map001_00b0b5'}


def convert(source):
    if event_contract.sha(source)!=MAP_SHA:raise ValueError('Unapproved interaction source')
    old={row['source']['offset']:row for rows in event_contract.convert(source).values() for row in rows}
    result={}
    for name,(begin,end) in PROGRAMS.items():
        cursor=begin;rows=[]
        while cursor<end:
            op=source[cursor];size=LENGTHS.get(op)
            if size is None or cursor+size>end:raise ValueError('Unknown or truncated interaction instruction')
            raw=source[cursor:cursor+size];data=raw[1:]
            u16=lambda n=0:int.from_bytes(data[n:n+2],'big')
            ptr=lambda n=0:int.from_bytes(data[n:n+4],'big')-0x260e0000+8
            args={}
            if cursor in old and op!=9:
                action=old[cursor]['action'];args=old[cursor]['args']
            elif op==0:action='end'
            elif op==9:
                bit={0x2f22:1,0x2f2f:2,0x2fb4:1}.get(cursor)
                if bit is None or data[8:]!=bytes((2,0,bit,0)):raise ValueError('Unknown interaction condition')
                action='branch_story'
                args={'allowed_bytes':[1,3],'mask':1<<bit,'if_clear':ptr(),
                      'if_set':None if bit==2 else ptr(4),'source_if_set':ptr(4)}
            elif op==0x37:action='set_story_bit';args={'bit':u16(),'required_byte':1}
            elif op==0x25:action='lock_control'
            elif op==0x26:action='unlock_control'
            elif op==0x1d:
                target=next((key for key,value in PROGRAMS.items() if value[0]==ptr(2)),None)
                if target is None or u16() not in (0,49):raise ValueError('Unknown child program')
                action='attach_actor';args={'actor_id':u16(),'program':target}
            elif op==0x2e:action='wait_actor';args={'actor_id':u16()}
            elif op==0x4c:action='hide_decoration';args={'object_id':u16()}
            elif op==0x4d:action='source_text_layout';args={'y':u16(3)}
            elif op==0x2d:
                if data[:2]!=b'\0\0' or data[2] not in TEXT_IDS:raise ValueError('Unknown source text')
                action='dialogue';args={'id':TEXT_IDS[data[2]]}
            elif op==0x57:action='grant_story_item';args={'item_id':data[0],'required_count':0,'result_count':1}
            elif op==0x61:action='player_palette';args={'selector':data[0]}
            elif op==0x5f:action='player_mode';args={'mode':data[0]}
            elif op==0x81:action='player_aux_input';args={'actor_id':u16(),'value':data[2]}
            elif op==0x60:
                if u16()!=0xfff0:raise ValueError('Unverified pickup X assignment')
                action='player_pickup_y';args={'y_raw':u16(2),'preserve_x':True}
            elif op==0x1f:action='actor_animation';args={'index':u16()}
            elif op==0x43:
                if ptr()!=0xefb8:raise ValueError('Unverified pickup audio')
                action='load_audio';args={'id':'cirrus_pickup_audio'}
            elif op==0x44:action='wait_audio_loaded'
            elif op==0x45:action='play_audio';args={'id':'cirrus_pickup_audio'}
            elif op==0x6b:action='save_actor_position';args={'slot':data[0],'actor_id':u16(1)}
            elif op==0x6c:
                if data[0]!=0:raise ValueError('Unknown temporary-coordinate mode')
                action='offset_saved_position';args={'slot':data[1],'delta_raw':[u16(i) for i in (2,4,6)]}
            elif op==0x72:
                action='spawn_story_spark';args={'actor_id':u16(),'slot':data[2],'spawn_bytes':list(data[3:])}
            elif op==0x30:action='remove_story_spark';args={'actor_id':u16()}
            elif op==2:action='player_pose';args={'heading':data[0]}
            elif op==1:action='wait_updates';args={'count':u16()}
            elif op==0x24:action='camera_target';args={'x_raw':u16(),'y_raw':u16(2),'speed_raw':u16(4)}
            elif op==0x3a:action='wait_camera';args={'restore_speed':data[0]==2}
            elif op==0x28:action='camera_follow_player'
            else:raise ValueError(f'No bounded mapping for opcode {op:02x}')
            rows.append({'id':f'{name}_{len(rows):02d}','action':action,'args':args,
                         'source':{'offset':cursor,'span':size,'sha256':event_contract.sha(raw),'opcode':op}})
            cursor+=size
        result[name]=rows
    return result


def build():
    old=event_contract.build()
    source=(ROOT.parent/'work/extract/MAP001.TWN').read_bytes()
    source_inputs={name:(ROOT.parent/name).read_bytes() for name in old['sources']}
    if any(event_contract.sha(raw)!=old['sources'][name] for name,raw in source_inputs.items()):
        raise ValueError('Source or translation changed during conversion')
    descriptor=json.loads(source_inputs['work/analysis/dialogue_twn_all_descriptors.json'].decode('utf-8-sig'))
    tsv=source_inputs['translation/zh-TW/dialogue_twn_all.tsv'].decode('utf-8-sig')
    rows=import_dialogue(source,descriptor,tsv)
    texts={row['id']:row for row in rows if row['id'] in TEXT_IDS.values()}
    if set(texts)!=set(TEXT_IDS.values()) or [len(texts[TEXT_IDS[i]]['pages']) for i in (1,2,3)]!=[2,1,2]:
        raise ValueError('Missing source translation')
    if any(not p['playback_allowed'] for row in texts.values() for p in row['pages']):raise ValueError('Unknown text control')
    return {'schema':'ao_pc_cirrus_interaction_contract_v1','acceptance':False,'sources':old['sources'],
            'programs':convert(source),'dialogues':texts,'expression_sequences':old['expression_sequences'],
            'cirrus_sequence':old['cirrus_sequence'],'device_inputs':old['device_inputs'],
            'update_order':['input_gate','region_then_interaction','root_event','player','auxiliary_actor','camera','decorations'],
            'wait_rule':old['wait_rule'],'story_values':[1,3],
            'confirmation':'Fresh edge; event-opening input is not a page confirmation. Device closure waits for required actor presentation.',
            'limitations':['Equipped story bit and adjacent scene remain unsupported.','Source pickup poses are used in every appearance mode.',
                          'No generic inventory/equipment UI.','Original shadow omitted.','No full MAP001 or Stage B acceptance.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('generated/interaction/source-contract.json'))
    a=p.parse_args();r=build();a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'programs':len(r['programs']),'instructions':sum(map(len,r['programs'].values())),'dialogues':len(r['dialogues'])}))
