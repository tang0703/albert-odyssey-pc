"""Continuous full-object comparison at CPU checkpoints; no state re-seeding."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import room_decoration as model
from validate_character_animation import watch
from verify_character_capture import inspect

def validate(folder: Path) -> dict:
    evidence=inspect(folder)
    def read(name):
        raw=(folder/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=evidence['outputs'][name]:
            raise ValueError('Capture changed during validation')
        return raw
    high=read('frame-000000/wram-high.bin')
    source=Path(__file__).resolve().parents[2]/'work/extract'
    programs=model.profiles(high,(source/'TWN.BIN').read_bytes(),(source/'MAP001.TWN').read_bytes())
    states=[p.initial for p in programs]
    history=[{'update':0,'states':[r.hex() for r in states]}]
    failures=[];checks=0;order=[];stage='before';updates=0;seed_tail=False
    def compare(expected,actual,label,row):
        nonlocal checks
        checks+=1
        if expected!=actual:
            failures.append({'update':updates,'frame':row['frame'],'checkpoint':label,
                             'expected':expected.hex(),'actual':actual.hex()})
    expected_seq=high[0xe8a21:0xe8a21+98]
    for row in evidence['hooks']:
        pc=row['pc']
        if pc not in model.PCS and pc!=0x060915a6: continue
        raw=watch(row,0x060ca4c0,120)
        compare(expected_seq,watch(row,0x260e8a21,98),'immutable program',row)
        if pc==0x060915a6:
            if stage!='before': raise ValueError('Camera/decorations reordered')
            compare(b''.join(states),raw,'before object loop',row)
            order=[];stage='objects'
        elif pc==0x060915ac:
            if updates==0 and stage=='before' and not seed_tail:
                # The named seed is after its last object's update but before
                # the dispatcher returns. Preserve this witnessed tail.
                compare(b''.join(states),raw,'inherited seed loop tail',row)
                seed_tail=True
                continue
            if stage!='objects' or order!=[(s,p) for s in (6,7) for p in (0x0609ddb4,0x0609e00a,0x0609ddc4)]:
                raise ValueError('Decoration dispatch checkpoints changed')
            compare(b''.join(states),raw,'after object loop',row)
            updates+=1;stage='before'
            history.append({'update':updates,'frame':row['frame'],'states':[r.hex() for r in states]})
        else:
            slot=(row['r'][4]-0x060ca358)//60
            if slot not in (6,7): continue
            if stage!='objects' or row['r'][4]!=0x060ca358+slot*60:
                raise ValueError('Object pointer/order changed')
            order.append((slot,pc));index=slot-6
            current=raw[index*60:(index+1)*60]
            if pc==0x0609ddb4: expected=states[index]
            elif pc==0x0609e00a: expected=model.step(states[index],programs[index],before_pointer=True)
            else:
                expected=model.step(states[index],programs[index]);states[index]=expected
            compare(expected,current,f'object {slot} at {pc:08x}',row)
    return {'schema':'ao_room_decoration_validation_v1','folder':str(folder.resolve()),
            'manifest_sha256':evidence['manifest_sha256'],'passed':not failures,
            'updates':updates,'checks':checks,'failures':failures[:30],
            'programs':[p.metadata() for p in programs],'history':history,
            'inherited_seed_loop_tail':seed_tail,
            'trailing_checkpoint_prefix':order if stage!='before' else []}

def main():
    p=argparse.ArgumentParser();p.add_argument('--captures',nargs='+',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    reports=[validate(f) for f in a.captures]
    manifests=[json.loads((f/'manifest.json').read_text(encoding='utf-8-sig')) for f in a.captures]
    same=all(m['outputs']==manifests[0]['outputs'] for m in manifests)
    result={'schema':'ao_room_decorations_gate_v1','passed':len(reports)==3 and same and all(r['passed'] for r in reports),
            'three_replays_identical':same,'captures':reports}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='captures'}))
    if not result['passed']: raise SystemExit(1)
if __name__=='__main__': main()
