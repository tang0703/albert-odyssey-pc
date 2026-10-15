"""Predicted world commands versus executed VDP commands, with explicit UI scope."""
import argparse
import bisect
import hashlib
import json
import struct
from pathlib import Path
from verify_event_sequence import validate
from event_draw_order import scene
from character_draw_order import _matches,verify_source
from inspect_event_capture import watched


def predicted_scene(high,low,source,state):
    mem=bytearray(high)
    mem[0xc8758:0xc87c8]=bytes.fromhex(state['player'])
    mem[0xca4c0:0xca4fc]=bytes.fromhex(state['decor'])
    mem[0xca4fc:0xca538]=bytes.fromhex(state['ambient'])
    for i,c in enumerate(state['cameras']):
        for key,offset in (('x',10),('y',12),('display_x',14),('display_y',16),('dx',24),('dy',26),('offset_x',28),('offset_y',30)):
            struct.pack_into('>h',mem,0xc4288+i*60+offset,c[key])
    raw=bytearray(112);effect=state['effect']
    if effect:
        for offset,value in ((0,state['effect_xy'][0]),(2,state['effect_xy'][1]),(6,effect['flags']),
                             (8,0x80),(0xe,217),(0x12,2),(0x16,0x23),(0x34,effect['image'])):
            struct.pack_into('>H',raw,offset,value)
        raw[0x45]=255
        struct.pack_into('>I',raw,0x58,0x260e5a24)
        struct.pack_into('>I',raw,0x60,0x260e8c48)
        p=0x5a2c+effect['image']*4
        raw[0x5c:0x60]=source[p:p+4]
    mem[0xc87c8:0xc8838]=raw
    return scene(bytes(mem),low)


def check(folder):
    reference=validate(folder,collect_world=True)
    if not reference['passed']:raise ValueError('Event core failed before world comparison')
    high=(folder/'frame-000000/wram-high.bin').read_bytes();low=(folder/'frame-000000/wram-low.bin').read_bytes()
    source=(Path(__file__).resolve().parents[2]/'work/extract/MAP001.TWN').read_bytes()
    extracted=Path(__file__).resolve().parents[2]/'work/extract'
    core=(extracted/'0').read_bytes()
    source_ranges=verify_source((extracted/'TWN.BIN').read_bytes(),core)
    if high[0x86f90:0x8705c]!=core[0x76f90:0x7705c]:raise ValueError('Runtime command submission code changed')
    states=reference.pop('world_predictions');indices=[s['event_index'] for s in states]
    submissions=[];pending=None
    for line in (folder/'hooks.jsonl').open('rb'):
        row=json.loads(line)
        if row['pc']==0x06086fca:
            if pending is not None:raise ValueError('Overlapping priority-chain submission')
            bank=int.from_bytes(watched(row,0x06074208,4),'big')&0x7ffff
            if bank not in (0x20,0x2a20) or row['r'][9]&0x7ffff!=bank or row['r'][10]*8!=bank:
                raise ValueError('Unknown source command buffer')
            index=bisect.bisect_left(indices,row['event_index'])-1
            if index<0:raise ValueError('Submission precedes captured world state')
            pending={'bank':bank,'state_index':index,'entry':row['event_index'],'update':states[index]['update']}
        elif row['pc']==0x06087050:
            if pending is None or row['r'][10]*8!=pending['bank']:raise ValueError('Unpaired command submission')
            end=(row['r'][9]&0x7ffff)+32
            if not pending['bank']<end<=pending['bank']+0x2a00:raise ValueError('Command buffer overflow')
            submissions.append(pending|{'end':end,'complete':row['event_index']});pending=None
    if pending is not None or not submissions:raise ValueError('Incomplete command buffer evidence')
    manifest_raw=(folder/'manifest.json').read_bytes();manifest=json.loads(manifest_raw.decode('utf-8-sig'))
    expected=next(r['sha256'] for r in manifest['outputs'] if r['path']=='vdp-events.jsonl')
    digest=hashlib.sha256();frames=[];errors=[];start=None;commands=[];skipped=[]
    def finish():
        if start is None:return
        if not commands:raise ValueError('Source draw contains no executed commands')
        first=commands[0]['event_index']
        candidates=[s for s in submissions if s['complete']<first and
                    all(s['bank']<=e['command_address']<s['end'] for e in commands)]
        if not candidates:
            if frames or skipped:raise ValueError('Executed list has no prior completed submission')
            skipped.append({'frame':start['frame'],'reason':'Inherited command list before first captured submission'})
            return
        submission=candidates[-1];index=submission['state_index']
        current=predicted_scene(high,low,source,states[index]);observed=[];ui=0;shadow=0;unbound=[]
        for event in commands:
            raw=bytes.fromhex(event['command_hex']);words=struct.unpack('>16H',raw)
            matches=[p for p in current['ordered_pieces'] if _matches(p,raw)]
            if len(matches)>1:raise ValueError('Ambiguous event world command')
            if matches:observed.append(matches[0]['id']);continue
            opcode=words[0]&15
            if opcode in (9,10):continue
            if opcode==2 and words[3]==0x27c0:shadow+=1;continue
            # Original text composition is replaced by the approved PC UI.
            # These are bounded, separately counted UI commands, never world art.
            indicator=(opcode==0 and words[3]==0x72d0 and words[5]==0x210 and words[6:8]==(0x110,0x40))
            if opcode==8 or (opcode==0 and words[3]==0x72f0) or (opcode==2 and words[3]==0x72e0) or indicator:
                ui+=1;continue
            unbound.append({'address':event['command_address'],'raw':event['command_hex']})
        if observed!=current['body_and_prop_order'] or unbound:
            errors.append({'frame':start['frame'],'predicted_update':states[index]['update'],
                'missing':[p for p in current['body_and_prop_order'] if p not in observed],
                'order_matches':observed==current['body_and_prop_order'],'unbound':unbound})
        frames.append({'frame':start['frame'],'update':states[index]['update'],'submission_complete':submission['complete'],
            'command_bank':submission['bank'],'world_pieces':len(observed),'source_ui_commands':ui,'shadow_commands':shadow})
    for line in (folder/'vdp-events.jsonl').open('rb'):
        digest.update(line);row=json.loads(line)
        if row['kind']=='vdp1_begin':finish();start=row;commands=[]
        elif row['kind']=='command_execute_before':commands.append(row)
    finish()
    if digest.hexdigest()!=expected:raise ValueError('Changed VDP command evidence')
    return {'schema':'ao_pc_event_predicted_world_diagnostic_v1','passed':not errors and bool(frames),
        'full_event_acceptance':False,'capture_integrity_required':True,'capture_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),
        'core_checks':reference['checks'],'render_phase':'Latest completed priority-chain submission for the consumed command bank; no fixed video-frame subtraction.',
        'source_ranges':source_ranges,
        'frames':frames,'errors':errors,'inherited_frames':skipped,
        'limits':['Source text/UI commands counted separately; no text pixel parity claim.','Original player shadow omitted.','Pixel composition is a separate gate.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=check(a.capture);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'frames':len(r['frames']),'errors':r['errors'][:5],'error_count':len(r['errors'])}))
    raise SystemExit(0 if r['passed'] else 1)
