"""Fourth local package; existing scene, source character and HD stay immutable."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image
from character_graphics import sha
from exploration_bundle import no_redirect

ROOT=Path(__file__).resolve().parents[1]
PINS={'scene':'bf837ef145c4ac413f6cb383c70d6a1d7e1e6d2544300719e3add645830e7fbc',
      'character':'ccc35c6e98a0a95cf517a555f338b3147dd307c1e60d3a284ffdded76f2bfd21',
      'character-hd':'00f009e7eded1ab6a3a5fb8b4c621ab03c705b43b701822eb62fb601718e511c'}
IMAGES={'background.png','foreground.png','decoration-6-46.png'}|{f'decoration-7-{n:02d}.png' for n in range(16,32)}
PAYLOADS=IMAGES|{'room.json'}
DEFAULT=ROOT/'exploration-demo/generated/room'
PIN=ROOT/'exploration-demo/room-pin.json'

def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')

def verify(folder: Path,expected: str,base: Path|None=None) -> dict:
    no_redirect(folder)
    if {p.name for p in folder.iterdir()}!=PAYLOADS|{'package.json'}:raise ValueError('Unapproved room package files')
    for p in folder.iterdir():
        no_redirect(p)
        if not p.is_file():raise ValueError('Room entries must be regular files')
    raw=(folder/'package.json').read_bytes()
    if sha(raw)!=expected:raise ValueError('Room manifest changed')
    manifest=json.loads(raw)
    if manifest.get('schema')!='ao_pc_room_bundle_v1' or manifest.get('dependencies')!=PINS or manifest.get('source_local_only') is not True or set(manifest.get('files',{}))!=PAYLOADS:
        raise ValueError('Invalid room package contract')
    for name,identity in manifest['files'].items():
        content=(folder/name).read_bytes()
        if len(content)!=identity['bytes'] or sha(content)!=identity['sha256']:raise ValueError('Room payload changed: '+name)
        if name in IMAGES:
            with Image.open(folder/name) as image:
                if image.mode!='RGBA' or list(image.size)!=identity['dimensions']:raise ValueError('Room PNG dimensions changed')
                image.verify()
    if base:
        for name,pin in PINS.items():
            if sha((base/name/'package.json').read_bytes())!=pin:raise ValueError('Existing dependency changed: '+name)
    return {'schema':'ao_pc_room_bundle_validation_v1','passed':True,'files':21,'manifest_sha256':expected}

def build() -> dict:
    source=ROOT/'reports/room/visuals';visual_raw=(source/'visuals.json').read_bytes();visual=json.loads(visual_raw)
    ref_raw=(ROOT/'reports/room/reference.json').read_bytes();ref=json.loads(ref_raw)
    if sha(ref_raw)!='a2fade02e6f80c0acf60fdf331983faa85b05750d0c0d5f693b6f6c0d90b0d0a':raise ValueError('R2 reference changed')
    if sha(visual_raw)!='15f108d71fd2a918191d7f2f270d353eb67ba4925905e05be8c37a9815887864':raise ValueError('R3 visuals changed')
    for name,pin in PINS.items():
        if sha((DEFAULT.parent/name/'package.json').read_bytes())!=pin:raise ValueError('Original dependency changed')
    for name,digest in visual['evidence'].items():
        raw=(ROOT/'reports/room'/name).read_bytes()
        if sha(raw)!=digest or not json.loads(raw).get('passed'):raise ValueError('Source graphics gate changed')
    traces=[]
    for trace in ref['traces']:
        updates=[]
        for update in trace['actor_fixture']['updates']:
            row=dict(update);row['actor_expected']=row['expected']
            row['expected']={k:v for k,v in row['actor_expected'].items() if k in ref['movement_profile']['initial_state']}
            index=len(updates)
            row['camera_expected']=trace['updates'][index]['cameras'] if index<len(trace['updates']) else None
            updates.append(row)
        traces.append({'id':trace['id'],'initial_state':ref['movement_profile']['initial_state'],'updates':updates})
    data={'schema':'ao_pc_room_scene_v1','movement_profile':ref['movement_profile'],'camera_profile':ref['camera_profile'],
          'initial_cameras':ref['traces'][0]['initial_cameras'],'boundaries':ref['boundaries'] if 'boundaries' in ref else ref['boundary_records'],
          'traces':traces,'visuals':visual,'reference_sha256':sha(ref_raw),'visuals_sha256':sha(visual_raw)}
    payload={'room.json':encoded(data)}
    for name in IMAGES:
        content=(source/name).read_bytes()
        if sha(content)!=visual['files'][name]['sha256']:raise ValueError('Source image changed')
        payload[name]=content
    manifest={'schema':'ao_pc_room_bundle_v1','source_local_only':True,'dependencies':PINS,
              'files':{n:{'bytes':len(raw),'sha256':sha(raw),**({'dimensions':visual['files'][n]['dimensions']} if n in IMAGES else {})} for n,raw in sorted(payload.items())}}
    manifest_raw=encoded(manifest);digest=sha(manifest_raw)
    if DEFAULT.exists():
        result=verify(DEFAULT,digest,DEFAULT.parent)
    else:
        DEFAULT.mkdir(parents=True)
        for name,raw in payload.items():(DEFAULT/name).write_bytes(raw)
        (DEFAULT/'package.json').write_bytes(manifest_raw)
        result=verify(DEFAULT,digest,DEFAULT.parent)
    PIN.write_bytes(encoded({'schema':'ao_pc_room_bundle_pin_v1','manifest_sha256':digest,'dependencies':PINS}))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','verify']);p.add_argument('--folder',type=Path,default=DEFAULT);p.add_argument('--sha256');a=p.parse_args()
    print(json.dumps(build() if a.action=='build' else verify(a.folder,a.sha256 or json.loads(PIN.read_text())['manifest_sha256'],a.folder.parent)))
