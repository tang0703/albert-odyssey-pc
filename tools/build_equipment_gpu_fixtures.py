"""Bind source scanout images to completed command submissions, not guessed frames."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from event_pixel_reference import dialogue_window
from event_contract import sha

ROOT = Path(__file__).resolve().parents[1]


def build():
    gate_raw = (ROOT/'reports/equipment/q1-acceptance.json').read_bytes()
    world_raw = (ROOT/'reports/equipment/q1-world.json').read_bytes()
    world = json.loads(world_raw)
    if not json.loads(gate_raw)['passed'] or not world['passed'] or not world['pixels']['passed']:
        raise ValueError('Complete source gates required')
    folder = ROOT/'reports/equipment/q1-render/equip-stairs'
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
    records = {r['path']:r for r in manifest['outputs']}
    identities = {r['sha256']:r['path'] for r in manifest['outputs'] if r['path'].endswith(('/vdp1-fb0.bin','/vdp1-fb1.bin'))}
    def read(name):
        raw = (folder/name).read_bytes()
        if sha(raw) != records[name]['sha256']: raise ValueError('Changed source '+name)
        return raw
    reference = json.loads((ROOT/'generated/equipment/reference/equip-stairs.json').read_bytes())
    states = [reference['initial_state']] + [r['expected'] for r in reference['updates']]
    draw_updates = {r['frame']:r['update'] for r in world['frames']}
    out = ROOT/'reports/equipment/gpu-fixtures'; out.mkdir(exist_ok=True)
    cases=[]; completed={}; seen=set(); frame=None; digest=hashlib.sha256()
    for line in (folder/'vdp-events.jsonl').open('rb'):
        digest.update(line); row=json.loads(line)
        if row['kind']=='vdp1_begin': frame=row['frame']
        elif row['kind']=='vdp1_swap_after_flip' and frame in draw_updates:
            completed[row['framebuffer_sha256'][row['display_bank']]]=(draw_updates[frame],row['event_index'])
        elif row['kind']=='software_video_complete':
            fb_sha=row['framebuffer_sha256'][row['display_bank']]
            if fb_sha not in completed: continue
            update,event_index=completed[fb_sha]
            if update+3>=len(states) or event_index>=row['event_index']: continue
            state=states[update]; actor=bytes.fromhex(state['player']); spark=bytes.fromhex(state['spark']) if state['spark'] else None
            image=int.from_bytes(actor[0x34:0x36],'big')
            spark_image=int.from_bytes(spark[0x34:0x36],'big') if spark and int.from_bytes(spark[6:8],'big')&0x8000 else None
            effect=state['effect']; effect_image=effect['image'] if effect and not effect['ended'] else None
            category=(update//12,)
            if category in seen or update%6: continue
            seen.add(category)
            video=read(f"frame-{row['frame']:06d}/video-rgba.bin")
            if sha(video)!=row['video_sha256']: raise ValueError('Scanout identity differs')
            codes=np.frombuffer(read(identities[fb_sha]),dtype='>u2').reshape(256,512)[:224,:320]
            excluded=((codes&0xffc0)==0x27c0)|np.isin(codes&0xfff0,[0x72d0,0x72e0,0x72f0])
            vram=read(f"frame-{row['frame']-1:06d}/vram2.bin")
            if any(vram[0x4000:0x4380]): excluded|=dialogue_window(vram[0x4000:0x4380])
            mask=np.full((224,320,4),255,dtype=np.uint8);mask[excluded]=0
            name=f"direct-{row['frame']:04d}"; image_path=out/(name+'.png'); mask_path=out/(name+'-mask.png')
            Image.frombytes('RGBA',(320,224),video).save(image_path);Image.fromarray(mask).save(mask_path)
            cases.append({'id':name,'route':0,'updates':update+3,'shown_update':update,'source_video_frame':row['frame'],
                'expected':str(image_path),'mask':str(mask_path),'expected_sha256':sha(image_path.read_bytes()),'mask_sha256':sha(mask_path.read_bytes())})
    if digest.hexdigest()!=records['vdp-events.jsonl']['sha256']:raise ValueError('Changed VDP evidence')
    result={'schema':'ao_equipment_gpu_fixtures_v1','source_acceptance_sha256':sha(gate_raw),'world_acceptance_sha256':sha(world_raw),
            'mapping':'Completed source framebuffer identity -> independently predicted update; PC presentation queue drains three logic updates later. No core state injection.', 'cases':cases}
    (out/'fixtures.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'cases':len(cases)}))

if __name__=='__main__':build()
