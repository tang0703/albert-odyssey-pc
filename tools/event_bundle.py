"""Build/verify the fifth local-only bundle without modifying its four parents."""
import argparse
import json
from pathlib import Path
from PIL import Image
from event_contract import build as contract_build, sha
from verify_event_capture_links import ROUTES

ROOT=Path(__file__).resolve().parents[1]
DEMO=ROOT/'exploration-demo'
DEPENDENCIES={'scene':'bf837ef145c4ac413f6cb383c70d6a1d7e1e6d2544300719e3add645830e7fbc',
              'character':'ccc35c6e98a0a95cf517a555f338b3147dd307c1e60d3a284ffdded76f2bfd21',
              'character-hd':'00f009e7eded1ab6a3a5fb8b4c621ab03c705b43b701822eb62fb601718e511c',
              'room':'4f5871775e4ff5de364cb78ed6aab695bcca5e60b57be4977d01270c7ed3e8d2'}
NAMES={'core.json','sprites.json','cirrus-event.wav','cirrus-71.png',
       *[f'expression-{n:02}.png' for n in (0,1,2,14,15)],*[f'reference-{r}.json' for r in ROUTES]}


def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')


def parents(directory):
    for name,expected in DEPENDENCIES.items():
        if sha((directory.parent/name/'package.json').read_bytes())!=expected:
            raise ValueError('Parent bundle identity changed: '+name)


def verify(directory=DEMO/'generated/event'):
    parents(directory)
    pin=json.loads((DEMO/'event-pin.json').read_text())
    raw=(directory/'package.json').read_bytes()
    if sha(raw)!=pin['manifest_sha256']:raise ValueError('Event manifest identity changed')
    manifest=json.loads(raw)
    if manifest['dependencies']!=DEPENDENCIES or not manifest['source_local_only'] or set(manifest['files'])!=NAMES:
        raise ValueError('Unknown event package content')
    if {p.name for p in directory.iterdir()}!=NAMES|{'package.json'} or any(p.is_symlink() or not p.is_file() for p in directory.iterdir()):
        raise ValueError('Unapproved event files or directories')
    for name,identity in manifest['files'].items():
        raw=(directory/name).read_bytes()
        if len(raw)!=identity['bytes'] or sha(raw)!=identity['sha256']:raise ValueError('Event payload changed: '+name)
    core=json.loads((directory/'core.json').read_text(encoding='utf-8'))
    if core['contract']!=json.loads(encoded(contract_build())):raise ValueError('Unknown event program or translated text')
    return manifest


def build():
    directory=DEMO/'generated/event'
    parents(directory)
    evidence={}
    for name in ('d1-acceptance','d2-python','d2-godot'):
        raw=(ROOT/'reports/event'/f'{name}.json').read_bytes()
        if json.loads(raw).get('passed') is not True:raise ValueError('Unpassed gate: '+name)
        evidence[name]=sha(raw)
    core=json.loads((ROOT/'generated/event/core.json').read_text(encoding='utf-8'))
    if core['contract']!=json.loads(encoded(contract_build())) or core['source_acceptance_sha256']!=evidence['d1-acceptance']:
        raise ValueError('Source core contract changed')
    sprites=json.loads((ROOT/'generated/event/source-sprites/source-sprites.json').read_text())
    payloads={'core.json':encoded(core),'sprites.json':encoded(sprites)}
    for row in sprites['sprites']:
        raw=(ROOT/'generated/event/source-sprites'/row['file']).read_bytes()
        if sha(raw)!=row['sha256']:raise ValueError('Changed source sprite')
        payloads[row['file']]=raw
    audio=json.loads((ROOT/'generated/event/source-audio/source-audio.json').read_text())
    payloads['cirrus-event.wav']=(ROOT/'generated/event/source-audio/cirrus-event.wav').read_bytes()
    if sha(payloads['cirrus-event.wav'])!=audio['output_sha256'] or not audio['pcm_roundtrip_passed']:
        raise ValueError('Audio conversion differs')
    for route in ROUTES:
        payloads[f'reference-{route}.json']=(ROOT/'generated/event/reference'/f'{route}.json').read_bytes()
    if set(payloads)!=NAMES:raise ValueError('Incomplete payload population')
    directory.mkdir(parents=True,exist_ok=True)
    if {p.name for p in directory.iterdir()}-NAMES-{'package.json'}:raise ValueError('Refuse unapproved existing bundle files')
    files={}
    for name,raw in payloads.items():
        (directory/name).write_bytes(raw)
        files[name]={'bytes':len(raw),'sha256':sha(raw)}
        if name.endswith('.png'):
            with Image.open(directory/name) as image:files[name]['dimensions']=list(image.size)
    manifest={'schema':'ao_pc_event_bundle_v1','source_local_only':True,'dependencies':DEPENDENCIES,
              'event_id':'map001_cirrus_stair','files':files,'evidence':evidence,
              'limits':core['contract']['limitations'],'audio':audio}
    raw=encoded(manifest)
    (directory/'package.json').write_bytes(raw)
    (DEMO/'event-pin.json').write_bytes(encoded({'schema':'ao_pc_event_bundle_pin_v1','manifest_sha256':sha(raw),'dependencies':DEPENDENCIES}))
    verify(directory)
    return {'directory':str(directory),'files':len(files),'manifest_sha256':sha(raw)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','verify'));a=p.parse_args()
    print(json.dumps(build() if a.action=='build' else {'passed':bool(verify())}))
