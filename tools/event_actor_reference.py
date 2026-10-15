"""Continuous player component under source command inputs; not a full event VM."""
import argparse
import json
import struct
from pathlib import Path
import probe_movement as movement
import character_animation as animation
from inspect_event_capture import watched


def word(raw, offset):return int.from_bytes(raw[offset:offset+2],'big')
def put(raw,offset,value):struct.pack_into('>H',raw,offset,value&65535)


def decode(raw,profile,advance):
    if advance:
        put(raw,0x30,word(raw,0x30)+1)
        if word(raw,0x30)>=word(raw,0x32):
            put(raw,0x30,0);put(raw,0x2c,word(raw,0x2c)+3);put(raw,6,word(raw,6)|0x80)
    duration,image,flags=profile.read_record(word(raw,0x36),word(raw,0x2c))
    if duration==0:
        put(raw,0x2c,0);put(raw,6,word(raw,6)|0x100)
        duration,image,flags=profile.read_record(word(raw,0x36),0)
    put(raw,0x32,duration);put(raw,0x34,image);put(raw,0x14,(word(raw,0x14)&0xfffe)|(1 if flags&4 else 0))
    struct.pack_into('>I',raw,0x5c,profile.image_pointer(image))


def pose(raw,heading,profile):
    raw=bytearray(raw)
    for offset in (0x30,0x2c,0x18,0x1a):put(raw,offset,0)
    put(raw,0x26,heading);put(raw,0x36,heading)
    decode(raw,profile,False)
    return raw


def forced_step(raw,axis,target,profile):
    raw=bytearray(raw);position=word(raw,axis*2)
    delta=movement.signed16(target-position)
    speed=movement.SPEED_COMPONENTS[word(raw,0x24)][0]
    if delta<0:heading=4 if axis==0 else 6;amount=max(delta,-speed)
    else:heading=0 if axis==0 else 2;amount=min(delta,speed)
    put(raw,0x26,heading);put(raw,0x18,amount if axis==0 else 0);put(raw,0x1a,amount if axis==1 else 0)
    put(raw,0x36,8+heading);decode(raw,profile,True)
    put(raw,axis*2,position+amount)
    done=word(raw,axis*2)&0xfff0==target&0xfff0
    if done:put(raw,6,word(raw,6)&0xfeff);put(raw,0x18+axis*2,0)
    return raw,done


def free_step(raw,profile,flags,disabled=0):
    raw=bytearray(raw)
    if disabled!=255:
        if word(raw,6)&2:raw=bytearray(movement.replay_velocity(raw))
        else:put(raw,0x2c,0);put(raw,0x36,word(raw,0x26))
        put(raw,0x18,word(raw,0x18)+word(raw,0x1e));put(raw,0x1a,word(raw,0x1a)+word(raw,0x20))
        put(raw,0x1e,0);put(raw,0x20,0)
    decode(raw,profile,True)
    out,diagnostics=movement.replay_step(raw,flags,movement.APPROVED_SHAPES)
    return bytearray(out),diagnostics


def validate(folder):
    high=(folder/'frame-000000/wram-high.bin').read_bytes();low=(folder/'frame-000000/wram-low.bin').read_bytes()
    profile=animation.profile_from_snapshot(high,low)
    source=(Path(__file__).resolve().parents[2]/'work/extract/MAP001.TWN').read_bytes()
    raw=bytearray(high[0xc8758:0xc87c8]);flags=low[0x10000:0x20000]
    disabled=0;gated=False;force=None;force_done=False;actor_phase=False;updates=0;errors=[];queries=set()
    for line in (folder/'hooks.jsonl').open(encoding='utf-8'):
        row=json.loads(line);pc=row['pc']
        if not gated:
            pad=int.from_bytes(watched(row,0x06036642,2),'big')
            raw=bytearray(movement.replay_input_gate(raw,pad,3,disabled)[0]);gated=True
        if pc==0x0609e092:
            offset=int.from_bytes(watched(row,0x060c66bc,4),'big')-0x260e0000+7
            op=source[offset];slot=row['r'][14]
            if op==0x25:
                disabled=255;put(raw,0x2c,0);put(raw,0x36,word(raw,0x26))
            elif op==0x26:disabled=0
            elif op==0x1d and source[offset+1:offset+3]==b'\0\0':put(raw,6,word(raw,6)|4)
            elif slot==0x060c8000:
                if op==0 and word(raw,6)&4:put(raw,6,word(raw,6)&0xfffb)
                elif op==2:raw=pose(raw,source[offset+1],profile)
                elif op==0x29:put(raw,0x24,source[offset+1])
                elif op in (6,7):
                    target=int.from_bytes(source[offset+1:offset+3],'big');axis=op-6
                    if word(raw,axis*2)&0xfff0!=target&0xfff0:
                        put(raw,0x2c,0);put(raw,0x30,0);force=(axis,target)
                        raw,force_done=forced_step(raw,axis,target,profile)
                        if force_done:force=None
        if pc==0x0609159a:
            actor_phase=True
            if force:
                raw,force_done=forced_step(raw,*force,profile)
                if force_done:force=None
            elif not word(raw,6)&4:
                raw,diag=free_step(raw,profile,flags,disabled)
                queries.update(d['index'] for d in diag['lookups'])
        if pc==0x060915a0:
            if not actor_phase:raise ValueError('Missing actor phase')
            actual=animation.state_from_actor(watched(row,0x060c8758,112));expected=animation.state_from_actor(raw)
            delta={k:{'actual':actual[k],'predicted':expected[k]} for k in actual if actual[k]!=expected[k]}
            if delta:errors.append({'frame':row['frame'],'update':updates+1,'fields':delta})
            updates+=1;actor_phase=False
        if pc==0x060915b2:gated=False
    return {'schema':'ao_pc_event_actor_reference_v1','passed':not errors and updates>0,
        'full_event_model_passed':False,'component_inputs':'Decoded source event commands and game pad; no later actor state injected.',
        'updates':updates,'checks':updates*len(animation.FIELDS),'query_indices':sorted(queries),'errors':errors}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=validate(a.capture);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'updates':r['updates'],'error_count':len(r['errors']),'errors':r['errors'][:3]}))
    raise SystemExit(0 if r['passed'] else 1)
