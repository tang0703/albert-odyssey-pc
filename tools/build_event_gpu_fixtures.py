"""Selected GPU checks use actual original video and source UI/shadow masks."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from event_contract import sha
from event_pixel_reference import dialogue_window

ROOT=Path(__file__).resolve().parents[1]


def build():
    gate_raw=(ROOT/'reports/event/d1-acceptance.json').read_bytes()
    if json.loads(gate_raw).get('passed') is not True:raise ValueError('D1 gate required')
    out=ROOT/'reports/event/gpu-fixtures';out.mkdir(exist_ok=True)
    cases=[]
    for route,name in enumerate(('center','top','bottom','reenter','wait','hold')):
        frames=([100,104,110,118,124,145,175,195,205,220,244,252,276,350,430,500,596,630,665,700,710,730,739]
                if route==0 else [104,124,205,252,350,710] if route in (1,2) else
                [850,1024,1140,1310,1550,1700] if route==3 else [350,650,900] if route==4 else [500,900,970,1020,1100,1120])
        folder=ROOT/'reports/event/d1-v1'/f'{name}-a'
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
        identities={r['path']:r['sha256'] for r in manifest['outputs']}
        def read(relative):
            raw=(folder/relative).read_bytes()
            if sha(raw)!=identities[relative]:raise ValueError('Source sample changed')
            return raw
        events={};digest=__import__('hashlib').sha256()
        for line in (folder/'vdp-events.jsonl').open('rb'):
            digest.update(line)
            row=json.loads(line)
            if row['kind']=='software_video_complete' and row['frame'] in frames:events[row['frame']]=row
        if digest.hexdigest()!=identities['vdp-events.jsonl']:raise ValueError('Source VDP observer changed')
        for frame in frames:
            event=events[frame];bank=event['display_bank']
            video=read(f'frame-{frame:06d}/video-rgba.bin')
            fb=read(f'frame-{frame-1:06d}/vdp1-fb{bank}.bin')
            if sha(fb)!=event['framebuffer_sha256'][bank] or sha(video)!=event['video_sha256']:raise ValueError('Video/framebuffer timing differs')
            codes=np.frombuffer(fb,dtype='>u2').reshape(256,512)[:224,:320]
            excluded=((codes&0xffc0)==0x27c0)|np.isin(codes&0xfff0,[0x72d0,0x72e0,0x72f0])
            vram=read(f'frame-{frame-1:06d}/vram2.bin')
            excluded|=dialogue_window(vram[0x4000:0x4380])
            mask=np.full((224,320,4),255,dtype=np.uint8);mask[excluded]=0
            case=f'{name}-{frame:04d}';image=out/(case+'.png');mask_path=out/(case+'-mask.png')
            Image.frombytes('RGBA',(320,224),video).save(image);Image.fromarray(mask).save(mask_path)
            cases.append({'id':case,'route':route,'updates':frame,'expected':str(image),'mask':str(mask_path),
                          'expected_sha256':sha(image.read_bytes()),'mask_sha256':sha(mask_path.read_bytes())})
    result={'schema':'ao_event_gpu_fixtures_v1','source_acceptance_sha256':sha(gate_raw),'cases':cases}
    (out/'fixtures.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'passed':True}))


if __name__=='__main__':build()
