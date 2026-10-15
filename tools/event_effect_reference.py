"""Bounded source model for 5D subtype 3, wait-23; no later state injection.

TWN 060A314C, 060A961E, 0609EEF8 and 060AC0B6/20C.
This is a diagnostic model, not a completed event acceptance gate.
"""
from dataclasses import dataclass
import hashlib

MAP_SHA='8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9'


@dataclass
class Effect:
    phase: int=0
    counter: int=30
    animation: int=0
    cursor: int=0
    timer: int=0
    duration: int=5
    image: int=0
    flags: int=0x8000
    ended: bool=False


def sequences(source):
    if hashlib.sha256(source).hexdigest()!=MAP_SHA: raise ValueError('Changed MAP source')
    result={}
    for i in (0,1,9):
        p=int.from_bytes(source[0x8c50+i*4:0x8c54+i*4],'big')-0x260e0000+8
        records=[]
        while source[p]:
            if source[p+2]!=0: raise ValueError('Unverified effect motion or mirror')
            records.append((source[p],source[p+1]));p+=3
            if len(records)>80: raise ValueError('Unterminated effect')
        result[i]=records
    if result!={0:[(5,0),(5,1),(5,2)],1:[(5,2),(5,1),(5,0)],9:[(5,14),(5,15)]}:
        raise ValueError('Subtype-3 sequence differs')
    return result


def step(state, programs):
    if state.ended: raise ValueError('Inactive wait-23 effect')
    s=Effect(**vars(state))
    def select(index):
        s.animation=index;s.timer=0;s.cursor=0;s.duration=programs[index][0][0];s.flags&=0xfeff
    if s.phase==4:
        s.counter=(s.counter-1)&65535
        if s.counter==0:s.phase=5
        return s
    # States 1/2/3 use the middle sequence. Switch helpers at the previous
    # completion can temporarily set the final sequence; preserve that order.
    s.animation=0 if s.phase==0 else 1 if s.phase==5 else 9
    s.timer=(s.timer+1)&65535
    if s.timer>=s.duration:
        s.timer=0;s.cursor+=3;s.flags|=0x80
    if s.cursor//3==len(programs[s.animation]):
        s.cursor=0;s.flags|=0x100
    s.duration,s.image=programs[s.animation][s.cursor//3]
    if s.flags&0x100:
        s.flags&=0xfeff
        if s.phase==5:
            select(1);s.flags=0;s.ended=True
        else:
            s.phase+=1
            select(9 if s.phase==1 else 1)
    return s


def validate(capture, source):
    import json
    from inspect_event_capture import watched
    programs=sequences(source);state=None;comparisons=0;errors=[];runs=0
    fields={'flags':6,'cursor':0x2c,'timer':0x30,'duration':0x32,'image':0x34,'animation':0x36}
    for line in (capture/'hooks.jsonl').open(encoding='utf-8'):
        row=json.loads(line)
        if row['pc']!=0x060915a0:continue
        slot=watched(row,0x060c8000,40)
        raw=watched(row,0x060c87c8,112)
        wait=int.from_bytes(slot[4:6],'big')
        active=bool(int.from_bytes(slot[0x14:0x16],'big')&0xc000==0xc000)
        if state is None:
            if not active or wait!=23: continue
            state=Effect();runs+=1
        else:
            state=step(state,programs)
        expected={key:getattr(state,key) for key in fields}
        actual={key:int.from_bytes(raw[offset:offset+2],'big') for key,offset in fields.items()}
        comparisons+=len(fields)
        if actual!=expected:
            errors.append({'frame':row['frame'],'actual':actual,'predicted':expected})
        if state.ended:state=None
    return {'schema':'ao_pc_event_effect_reference_v1','passed':not errors and runs>0,
        'runs':runs,'comparisons':comparisons,'errors':errors}


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=validate(a.capture,(Path(__file__).resolve().parents[2]/'work/extract/MAP001.TWN').read_bytes())
    a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'runs':r['runs'],'comparisons':r['comparisons'],'errors':r['errors'][:3]}))
    raise SystemExit(0 if r['passed'] else 1)
