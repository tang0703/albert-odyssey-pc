"""GPU expected PNGs are captured original video, never our rendered output."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from character_graphics import sha

ROOT=Path(__file__).resolve().parents[1]

def build():
    report_raw=(ROOT/'reports/room/graphics-validation.json').read_bytes()
    report=json.loads(report_raw)
    if not report.get('passed'):raise ValueError('Source graphics gate required')
    out=ROOT/'reports/room/gpu-fixtures';out.mkdir(parents=True,exist_ok=False)
    cases=[]
    for route,folder_name in ((3,'visual-west-a'),(4,'visual-east-a')):
        folder=ROOT/'reports/room'/folder_name
        proof=next(r for r in report['captures'] if Path(r['folder']).resolve()==folder.resolve())
        raw=(folder/'manifest.json').read_bytes()
        if sha(raw)!=proof['manifest_sha256']:raise ValueError('Capture manifest changed')
        manifest=json.loads(raw);hashes={r['path']:r['sha256'] for r in manifest['outputs']}
        def read(name):
            raw=(folder/name).read_bytes()
            if sha(raw)!=hashes[name]:raise ValueError('Capture changed')
            return raw
        events={}
        for line in (folder/'vdp-events.jsonl').open():
            event=json.loads(line)
            if event['kind']=='software_video_complete':events[event['frame']]=event
        frames=sorted(set([2,10,30,50,70,90,110,130,150,170,190,210,230,250,270,proof['frames']]))
        for frame in frames:
            video=read(f'frame-{frame:06d}/video-rgba.bin');bank=events[frame]['display_bank']
            fb=read(f'frame-{frame-1:06d}/vdp1-fb{bank}.bin')
            if sha(fb)!=events[frame]['framebuffer_sha256'][bank]:raise ValueError('Framebuffer timing mismatch')
            pixels=np.frombuffer(fb,dtype='>u2').reshape(256,512)[:224,:320]
            mask=np.full((224,320,4),255,dtype=np.uint8);mask[(pixels&0xffc0)==0x27c0]=0
            name=f'{folder_name}-{frame:04d}'
            expected=out/(name+'.png');masked=out/(name+'-mask.png')
            Image.frombytes('RGBA',(320,224),video).save(expected);Image.fromarray(mask).save(masked)
            cases.append({'id':name,'route':route,'updates':frame,'expected':str(expected),'mask':str(masked),
                          'expected_sha256':sha(expected.read_bytes()),'mask_sha256':sha(masked.read_bytes())})
    result={'schema':'ao_room_gpu_fixtures_v1','source_report_sha256':sha(report_raw),'cases':cases}
    (out/'fixtures.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'passed':True}))
if __name__=='__main__':build()
