"""Cirrus slot 6 component: source 46/47 and wait 16; no later state injection."""
import argparse
import json
import struct
from pathlib import Path
import room_decoration
from event_actor_reference import word, put
from inspect_event_capture import watched


def program(source):
    from event_effect_reference import sequences
    sequences(source)
    address=int.from_bytes(source[0x8b58+5*4:0x8b5c+5*4],'big')
    if address!=0x260e8a83:raise ValueError('Unknown Cirrus event animation')
    seq=source[0x8a8b:0x8a8b+37]
    if seq!=bytes.fromhex('082e10084710')*6+b'\0':raise ValueError('Changed Cirrus sequence')
    return seq


def event_step(raw,seq,pointers):
    result=bytearray(raw);timer=(word(raw,0x1e)+1)&65535;cursor=word(raw,0x1c)
    if cursor%3 or cursor>=len(seq)-1:raise ValueError('Unverified Cirrus cursor')
    if timer>=word(raw,0x20):
        timer=0;cursor+=3;put(result,0xa,word(result,0xa)|0x80)
        if seq[cursor]:put(result,0x1c,cursor)
    put(result,0x1e,timer)
    ended=not seq[cursor]
    if ended:put(result,0xa,word(result,0xa)|0x100)
    else:
        put(result,0x20,seq[cursor]);put(result,0x22,seq[cursor+1])
    put(result,0x14,word(result,0x14)&0xfffe)
    struct.pack_into('>I',result,0x30,pointers[word(result,0x22)])
    return result,ended


def validate(folder):
    high=(folder/'frame-000000/wram-high.bin').read_bytes()
    workspace=Path(__file__).resolve().parents[2]
    source=(workspace/'work/extract/MAP001.TWN').read_bytes()
    twn=(workspace/'work/extract/TWN.BIN').read_bytes()
    initial=room_decoration.profiles(high,twn,source)[0];seq=program(source)
    raw=bytearray(initial.initial);attached=False;waiting=False;processed=False
    errors=[];checks=0;updates=0;runs=0
    for line in (folder/'hooks.jsonl').open(encoding='utf-8'):
        row=json.loads(line);pc=row['pc']
        if pc==0x0609e092:
            offset=int.from_bytes(watched(row,0x060c66bc,4),'big')-0x260e0000+7
            op=source[offset]
            if op==0x46:
                if source[offset+1:offset+3]!=b'\0\x30':raise ValueError('Unknown decoration attachment')
                attached=True;put(raw,0xa,word(raw,0xa)|4);put(raw,0x26,1)
            elif row['r'][14]==0x060c8000 and attached:
                if op==0x47:
                    if source[offset+1:offset+3]!=b'\0\5':raise ValueError('Unknown decoration animation')
                    put(raw,0x24,5);put(raw,0x1e,0);put(raw,0x1c,0)
                    # 47 calls the non-ticking DE9C decoder, then E00A.
                    put(raw,0x20,seq[0]);put(raw,0x22,seq[1]);put(raw,0x14,word(raw,0x14)&0xfffe)
                    put(raw,0xa,word(raw,0xa)&0xfeff)
                    struct.pack_into('>I',raw,0x30,initial.image_pointers[seq[1]])
                    waiting=True;processed=True;runs+=1
                elif op==0:
                    attached=False;put(raw,0xa,word(raw,0xa)&0xfffb);processed=True
        if pc==0x060915a6:
            # Before decoration loop; its actual commands follow this hook.
            if waiting:
                put(raw,6,0);put(raw,8,0)
                raw,ended=event_step(raw,seq,initial.image_pointers)
                if ended:
                    put(raw,0xa,word(raw,0xa)&0xfeff);put(raw,0x1a,0);waiting=False
                processed=True
            elif not attached and word(raw,0x1a):
                raw=bytearray(room_decoration.step(raw,initial));processed=True
        if pc==0x060915ac:
            actual=watched(row,0x060ca4c0,60)
            # All original 60 bytes, including persistent post-animation state.
            delta={hex(i):[actual[i],raw[i]] for i in range(60) if actual[i]!=raw[i]}
            if delta:errors.append({'frame':row['frame'],'bytes':delta})
            checks+=60;updates+=1;processed=False
    return {'schema':'ao_pc_event_decoration_reference_v1','passed':not errors and runs>0,
        'full_event_model_passed':False,'component_inputs':'Source command dispatch; no later decoration state injected.',
        'runs':runs,'updates':updates,'checks':checks,'errors':errors}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=validate(a.capture);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**{k:r[k] for k in ('passed','runs','checks')},'errors':r['errors'][:3],'error_count':len(r['errors'])}))
    raise SystemExit(0 if r['passed'] else 1)
