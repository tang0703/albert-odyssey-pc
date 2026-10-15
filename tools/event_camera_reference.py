"""Source camera component proof with decoded event operands, not later camera state.

Player position is this component's input; full event/player parity is separate.
"""
import argparse
import json
from pathlib import Path
from room_camera import state_from_bytes,signed16
from inspect_event_capture import watched
from event_effect_reference import sequences


def step(state, target, speed, fixed):
    result=dict(state);result.update(display_x=state['x'],display_y=state['y'],dx=0,dy=0)
    for axis,value,center,minimum,maximum in (
        ('x',target[0],0 if fixed else 0xa80,8192,10240),
        ('y',target[1],0 if fixed else 0x780,24576,25088)):
        margin=0 if fixed else 0x200
        upper=signed16(state[axis]+center+margin);lower=signed16(state[axis]+center-margin)
        if value>upper:
            delta=min(speed,signed16(value-upper));proposed=signed16(state[axis]+delta)
            if proposed>maximum:proposed,delta=maximum,0
            result[axis]=proposed;result['d'+axis]=delta
        if value<lower:
            delta=min(speed,signed16(lower-value));proposed=signed16(result[axis]-delta)
            if proposed<minimum:proposed,delta=minimum,0
            result[axis]=proposed;result['d'+axis]=-delta
    return result


def validate(capture, source):
    sequences(source)  # Full pinned source identity.
    high=(capture/'frame-000000/wram-high.bin').read_bytes()
    states=[state_from_bytes(high,0xc4288+i*60) for i in range(2)]
    fixed=False;target=None;speed=128;restore=False;pending=None;checks=0;errors=[];updates=0
    for line in (capture/'hooks.jsonl').open(encoding='utf-8'):
        row=json.loads(line);pc=row['pc']
        if pc==0x0609159a and restore and not states[0]['dx'] and not states[0]['dy']:
            speed=128;fixed=False;restore=False
        if pc==0x0609e092:
            cursor=int.from_bytes(watched(row,0x060c66bc,4),'big')-1
            offset=cursor-0x260e0000+8;op=source[offset]
            if op==0x24:
                values=[int.from_bytes(source[offset+i:offset+i+2],'big') for i in (1,3,5)]
                if values!=[0x26b0,0x6070,16]:raise ValueError('Unverified event camera target')
                target=values[:2];speed=values[2];fixed=True
            elif op==0x28:
                if source[offset+1:offset+3]!=b'\0\0':raise ValueError('Unknown follow actor')
                fixed=False
            elif op==0x3a and source[offset+1]==2:restore=True
        if pc==0x060915a0:
            player=watched(row,0x060c8758,4)
            xy=target if fixed else [int.from_bytes(player[i:i+2],'big',signed=True) for i in (0,2)]
            pending=[step(s,xy,speed,fixed) for s in states]
        if pc==0x060915a6:
            if pending is None:raise ValueError('Camera completion without begin')
            for slot in range(2):
                actual=state_from_bytes(watched(row,0x060c4288+slot*60,60))
                checks+=len(actual)
                if actual!=pending[slot]:errors.append({'frame':row['frame'],'slot':slot,'actual':actual,'predicted':pending[slot]})
            states=pending;pending=None;updates+=1
    return {'schema':'ao_pc_event_camera_reference_v1','passed':not errors and updates>0,
        'component_inputs':'Source actor coordinates; event operands from pinned MAP; camera is rolled forward independently.',
        'full_event_model_passed':False,'updates':updates,'checks':checks,'errors':errors}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=validate(a.capture,(Path(__file__).resolve().parents[2]/'work/extract/MAP001.TWN').read_bytes())
    a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'updates':r['updates'],'checks':r['checks'],'errors':r['errors'][:2]}))
    raise SystemExit(0 if r['passed'] else 1)
