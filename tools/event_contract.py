"""Convert only the source-confirmed Cirrus branch into named PC instructions.

This is a source description, not a declaration that D1 or the PC runtime passes.
Generated source text and records stay local with the other source packages.
"""
import argparse
import hashlib
import json
from pathlib import Path
from pipeline import import_dialogue
from event_effect_reference import MAP_SHA,sequences
from event_decoration_reference import program as cirrus_program

ROOT=Path(__file__).resolve().parents[1]
PROGRAMS={'entry':(0x2f22,0x2f2f),'main':(0x2f3c,0x2f83),
          'expression':(0x1e79,0x1e81),'retreat':(0x1e81,0x1e95),'cirrus':(0x1e74,0x1e79)}
LENGTHS={0:2,1:3,2:2,6:3,7:3,9:13,0x1d:7,0x24:7,0x25:1,0x26:1,0x28:3,
         0x29:2,0x2d:4,0x2e:3,0x3a:2,0x43:5,0x44:1,0x45:1,0x46:7,0x47:3,0x4d:6,0x51:1,0x5d:4}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def convert(source):
    if sha(source)!=MAP_SHA:raise ValueError('Unapproved source script')
    output={}
    for name,(begin,end) in PROGRAMS.items():
        cursor=begin;rows=[]
        while cursor<end:
            op=source[cursor]
            if op not in LENGTHS:raise ValueError('Unknown source opcode')
            size=LENGTHS[op];raw=source[cursor:cursor+size];data=raw[1:]
            if cursor+size>end:raise ValueError('Truncated source instruction')
            u16=lambda n=0:int.from_bytes(data[n:n+2],'big')
            ptr=lambda n=0:int.from_bytes(data[n:n+4],'big')-0x260e0000+8
            args={}
            if op==0:action='end'
            elif op==9:
                action='require_story_branch';args={'byte':1,'mask':2,'expected':0,'next_program':'main'}
                if ptr()!=PROGRAMS['main'][0] or data[8:]!=bytes.fromhex('02000100'):raise ValueError('Unverified branch')
            elif op==1:action='wait_updates';args={'count':u16()}
            elif op==2:action='player_pose';args={'heading':data[0]}
            elif op in (6,7):action='player_move_axis';args={'axis':op-6,'target_raw':u16()}
            elif op==0x1d:
                action='attach_player'
                target=next((key for key in ('expression','retreat') if PROGRAMS[key][0]==ptr(2)),None)
                if u16()!=0 or target is None:raise ValueError('Unknown player child program')
                args={'program':target}
            elif op==0x24:action='camera_target';args={'x_raw':u16(),'y_raw':u16(2),'speed_raw':u16(4)}
            elif op==0x25:action='lock_control'
            elif op==0x26:action='unlock_control'
            elif op==0x28:action='camera_follow_player'
            elif op==0x29:action='player_speed';args={'index':data[0]}
            elif op==0x2d:action='dialogue';args={'id':'map001_00afe2'}
            elif op==0x2e:action='wait_player'
            elif op==0x3a:action='wait_camera';args={'restore_speed':data[0]==2}
            elif op==0x43:action='load_audio';args={'id':'cirrus_original_audio'}
            elif op==0x44:action='wait_audio_loaded'
            elif op==0x45:action='play_audio';args={'id':'cirrus_original_audio'}
            elif op==0x46:action='attach_cirrus';args={'program':'cirrus'}
            elif op==0x47:action='cirrus_animation';args={'index':u16()}
            elif op==0x4d:action='source_text_layout';args={'y':u16(3)}
            elif op==0x51:action='wait_audio_started'
            elif op==0x5d:action='expression';args={'subtype':data[0],'hold_updates':u16(1)}
            else:raise ValueError('No PC instruction mapping')
            rows.append({'id':f'{name}_{len(rows):02d}','action':action,'args':args,
                         'source':{'offset':cursor,'span':size,'sha256':sha(raw),'opcode':op}})
            cursor+=size
        if cursor!=end or (name!='entry' and rows[-1]['action']!='end'):raise ValueError('Incomplete bounded program')
        output[name]=rows
    return output


def build():
    lock=json.loads((ROOT/'source-lock.json').read_text())['sources']
    inputs={}
    for name in ('work/extract/MAP001.TWN','work/analysis/dialogue_twn_all_descriptors.json','translation/zh-TW/dialogue_twn_all.tsv'):
        raw=(ROOT.parent/name).read_bytes()
        if sha(raw)!=lock[name]:raise ValueError('Source/translation lock changed: '+name)
        inputs[name]=raw
    source=inputs['work/extract/MAP001.TWN']
    texts=import_dialogue(source,json.loads(inputs['work/analysis/dialogue_twn_all_descriptors.json'].decode('utf-8-sig')),
                          inputs['translation/zh-TW/dialogue_twn_all.tsv'].decode('utf-8-sig'))
    selected=[row for row in texts if row['id']=='map001_00afe2']
    if len(selected)!=1 or len(selected[0]['pages'])!=2:raise ValueError('Incomplete source dialogue')
    if any(not page['playback_allowed'] for page in selected[0]['pages']):raise ValueError('Unknown dialogue controls')
    return {'schema':'ao_pc_cirrus_source_contract_v1','acceptance':False,
        'sources':{name:sha(raw) for name,raw in inputs.items()},'programs':convert(source),'dialogue':selected[0],
        'expression_sequences':sequences(source),'cirrus_sequence':list(cirrus_program(source)),
        'update_order':['input_gate','region_trigger','root_event','player','camera','cirrus_and_ambient'],
        'wait_rule':'A completed wait clears its wait flag and returns; dispatch continues next update.',
        'device_inputs':['resource_loaded','resource_playing','text_active'],
        'player_visual_contract':{
            'identity':['image_index','image_pointer','render_flags_word'],
            'selection_cache_can_lag':True,
            'evidence':'Control lock changes animation selection/cursor before the attached expression ends; the last rendered player image remains cached.',
            'forced_walk':'Script axis movement can animate a walk with input-moving bit clear; image cache, not input ownership, selects the visual.'},
        'pc_device_contract':{'audio':'Preload before play; acknowledge successful local load/start, not emulated CD latency.',
            'text':'Present two whole pages; each fresh confirmation advances one; clear active after the second.',
            'source_parity':'Feed original device acknowledgements only in the source comparison harness.'},
        'retrigger':'Region test runs each update while root is inactive; source branch byte remains 1.',
        'limitations':['Only captured story branch supported.','Source text drawing is replaced by approved HD UI.',
                       'Source shadow remains omitted.','No adjacent scene or whole Stage B acceptance.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('generated/event/source-contract.json'));a=p.parse_args()
    result=build();a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'programs':len(result['programs']),'instructions':sum(map(len,result['programs'].values())),'pages':len(result['dialogue']['pages'])}))
