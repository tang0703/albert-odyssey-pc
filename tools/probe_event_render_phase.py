"""Locate event world-command submission boundaries; diagnostic, never acceptance."""
import argparse
import bisect
import json
from pathlib import Path
from event_draw_order import scene
from character_draw_order import _matches


def probe(folder,selected):
    high=(folder/'frame-000000/wram-high.bin').read_bytes();low=(folder/'frame-000000/wram-low.bin').read_bytes()
    checkpoints=[]
    for line in (folder/'hooks.jsonl').open(encoding='utf-8'):
        r=json.loads(line)
        if r['pc']==0x060915c4:checkpoints.append(r)
    indices=[r['event_index'] for r in checkpoints]
    rows={f:{'commands':[]} for f in selected}
    for line in (folder/'vdp-events.jsonl').open(encoding='utf-8'):
        r=json.loads(line)
        if r['frame'] not in rows:continue
        if r['kind']=='vdp1_begin':rows[r['frame']]['start']=r
        if r['kind']=='command_execute_before':rows[r['frame']]['commands'].append(r)
    result=[]
    for frame,row in rows.items():
        latest=bisect.bisect_left(indices,row['start']['event_index'])-1
        candidates=[]
        for delay in range(4):
            checkpoint=checkpoints[latest-delay];mem=bytearray(high)
            for watch in checkpoint['watches']:
                address=watch['address']&0x1fffffff;raw=bytes.fromhex(watch['hex'])
                if 0x06000000<=address<0x06100000:
                    offset=address-0x06000000;mem[offset:offset+len(raw)]=raw
            current=scene(bytes(mem),low)
            observed=[];unbound=[]
            for event in row['commands']:
                matches=[p for p in current['ordered_pieces'] if _matches(p,bytes.fromhex(event['command_hex']))]
                if matches:observed.append(matches[0]['id'])
                else:unbound.append(event['command_hex'])
            candidates.append({'delay_from_last_c4':delay,'checkpoint_frame':checkpoint['frame'],
                'checkpoint_index':latest-delay,'world_order_matches':observed==current['body_and_prop_order'],
                'missing':[p for p in current['body_and_prop_order'] if p not in observed],'unbound':unbound})
        result.append({'frame':frame,'candidates':candidates})
    return {'semantic_acceptance':False,'frames':result}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--frames',type=int,nargs='+',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=probe(a.capture,a.frames);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([(f['frame'],[(c['delay_from_last_c4'],c['world_order_matches'],c['missing']) for c in f['candidates']]) for f in r['frames']]))
