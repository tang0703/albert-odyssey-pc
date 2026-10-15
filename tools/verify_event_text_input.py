"""Source confirmation gate for F6 page wait and FA end wait.

This checks source input edges and phase changes, not original font rasterizing
or its typewriter/scroll pacing. PC whole-page UI remains a separate adapter.
"""
import argparse
import hashlib
import json
from pathlib import Path
from inspect_event_capture import watched
from character_graphics import TWN_SHA256
from verify_event_capture_links import ROUTES


def verify(folder):
    source=(Path(__file__).resolve().parents[2]/'work/extract/TWN.BIN').read_bytes()
    if hashlib.sha256(source).hexdigest()!=TWN_SHA256:raise ValueError('Source text handlers changed')
    # Dispatch phases 8/9 point to the two independently inspected edge gates.
    if source[0x27238:0x27240]!=bytes.fromhex('060b0c46060b0d32'):raise ValueError('Unknown text phase dispatch')
    manifest_raw=(folder/'manifest.json').read_bytes();manifest=json.loads(manifest_raw.decode('utf-8-sig'))
    wanted=next(r['sha256'] for r in manifest['outputs'] if r['path']=='hooks.jsonl')
    digest=hashlib.sha256();pending=None;checks=0;accepted=[];waiting={8:0,9:0};phase_changes=[];prior=None
    for line in (folder/'hooks.jsonl').open('rb'):
        digest.update(line);row=json.loads(line)
        if row['pc']==0x060915be:
            if pending is not None:raise ValueError('Unclosed source text update')
            raw=watched(row,0x060c51d4,64)
            pending={'phase':raw[25],'flags':int.from_bytes(raw[:2],'big'),
                     'edge':int.from_bytes(watched(row,0x06036646,2),'big'),'frame':row['frame']}
        elif row['pc']==0x060915c4:
            if pending is None:raise ValueError('Source text completion without its input boundary')
            raw=watched(row,0x060c51d4,64);phase=raw[25]
            if phase!=prior:phase_changes.append({'frame':row['frame'],'phase':phase});prior=phase
            if pending['phase'] in (8,9):
                if pending['flags']!=17:raise ValueError('Unverified automatic text-advance mode')
                pressed=bool(pending['edge']&0x600)
                expected=(3 if pending['phase']==8 else 7) if pressed else pending['phase']
                if phase!=expected:raise ValueError('Source confirmation transition differs')
                if int.from_bytes(raw[:2],'big')!=17:raise ValueError('Confirmation unexpectedly ended the active source window')
                checks+=1
                if pressed:accepted.append(pending|{'next_phase':phase,'completion_frame':row['frame']})
                else:waiting[pending['phase']]+=1
            pending=None
    if pending is not None:raise ValueError('Partial final source text update')
    if digest.hexdigest()!=wanted:raise ValueError('Changed source text input evidence')
    if (folder/'manifest.json').read_bytes()!=manifest_raw:raise ValueError('Changed capture manifest')
    return {'schema':'ao_pc_cirrus_source_confirmation_v1','passed':checks>0,
            'capture_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),'checks':checks,
            'accepted_confirmations':accepted,'waiting_updates':waiting,'phase_changes':phase_changes,
            'source_handlers':[0x060b0c46,0x060b0d32],'source_edge_word':0x06036646,'source_confirm_mask':0x600,
            'scope':'F6/FA confirmation gates only; original text rendering/scroll timing is an external device boundary.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('reports/event'));a=p.parse_args()
    for route in ROUTES:
        result=verify(a.root/'d1-render'/f'{route}-a')
        if len(result['accepted_confirmations'])!=(0 if route=='wait' else 4 if route=='reenter' else 2):raise ValueError('Unexpected source confirmation count')
        (a.root/f'd1-{route}-text-input.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'route':route,'passed':result['passed'],'checks':result['checks'],'confirmations':len(result['accepted_confirmations'])}),flush=True)
