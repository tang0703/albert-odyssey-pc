"""Short GPU correctness cases, driven by replay inputs without state injection."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from transition_source import ROOT,sha
from equipment_contract import encoded


def build():
    base=ROOT/'reports/transition';folder=base/'t3-render'
    gate=(base/'t3-acceptance.json').read_bytes();world_raw=(base/'t3-world.json').read_bytes();world=json.loads(world_raw)
    if not json.loads(gate)['passed'] or not world['passed'] or not world['pixels']['passed']:raise ValueError('Landing source gate missing')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
    records={r['path']:r for r in manifest['outputs']}
    identities={r['sha256']:r['path'] for r in manifest['outputs'] if r['path'].endswith(('/vdp1-fb0.bin','/vdp1-fb1.bin'))}
    def read(name):
        raw=(folder/name).read_bytes()
        if sha(raw)!=records[name]['sha256']:raise ValueError('Changed source fixture')
        return raw
    wanted={1145,1146,1155,1168,1177,1259,1305,1355,1400,1450,1500,1550,1585}
    pixels={r['frame']:r for r in world['pixels']['frames'] if r['frame'] in wanted}
    if set(pixels)!=wanted:raise ValueError('Missing representative source frames')
    fixture=json.loads((ROOT/'generated/transition/reference/landing-corridor.json').read_bytes())
    prefix=len(fixture['prefix']['updates']);out=base/'gpu-fixtures';out.mkdir(exist_ok=True);cases=[]
    for line in (folder/'vdp-events.jsonl').open('rb'):
        row=json.loads(line)
        if row['kind']!='software_video_complete' or row['frame'] not in pixels:continue
        r=pixels[row['frame']];video=read(f"frame-{row['frame']:06d}/video-rgba.bin")
        if sha(video)!=row['video_sha256']:raise ValueError('Source video differs')
        digest=row['framebuffer_sha256'][row['display_bank']]
        codes=np.frombuffer(read(identities[digest]),dtype='>u2').reshape(256,512)[:224,:320]
        mask=np.full((224,320,4),255,dtype=np.uint8);mask[(codes&0xffc0)==0x27c0]=0
        name=f"landing-{row['frame']:04d}";image=out/(name+'.png');maskfile=out/(name+'-mask.png')
        Image.frombytes('RGBA',(320,224),video).save(image);Image.fromarray(mask).save(maskfile)
        cases.append({'id':name,'route':3,'updates':prefix+r['model_update']+2,'shown_update':r['model_update'],
                      'rgb_offset':r['rgb_offset'],'source_video_frame':row['frame'],'expected':str(image),'mask':str(maskfile),
                      'expected_sha256':sha(image.read_bytes()),'mask_sha256':sha(maskfile.read_bytes())})
    result={'schema':'ao_transition_gpu_fixtures_v1','source_acceptance_sha256':sha(gate),'world_acceptance_sha256':sha(world_raw),
            'mapping':'Continuous replay plus independently proven two-update presentation queue. RGB is the separate current source fade tick. No state injection.','cases':cases,'performance_tested':False}
    (out/'fixtures.json').write_bytes(encoded(result));print(json.dumps({'passed':True,'cases':len(cases)}))

if __name__=='__main__':build()
