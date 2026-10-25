"""Build/verify the sixth local-only bundle without modifying its five parents."""
import argparse
import json
from pathlib import Path
from PIL import Image
from interaction_contract import build as contract_build
from event_contract import sha
from summarize_interaction_source import ROUTES

ROOT=Path(__file__).resolve().parents[1]
DEMO=ROOT/'exploration-demo'
from event_bundle import DEPENDENCIES as OLD_DEPENDENCIES
DEPENDENCIES={**OLD_DEPENDENCIES,'event':'4c830604e9eaeadb0542df39f37355f7d37509f24940ed7cc8a210c012f04510'}
NAMES={'core.json','sprites.json','cirrus-pickup.wav',*[f'pickup-{n:02}.png' for n in range(35,39)],
       *[f'spark-{n:02}.png' for n in (*range(32,43),44)],*[f'reference-{r}.json' for r in ROUTES]}


def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')


def parents(directory):
    for name,expected in DEPENDENCIES.items():
        if sha((directory.parent/name/'package.json').read_bytes())!=expected:
            raise ValueError('Parent bundle identity changed: '+name)


def verify(directory=DEMO/'generated/interaction'):
    parents(directory)
    pin=json.loads((DEMO/'interaction-pin.json').read_text())
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
    directory=DEMO/'generated/interaction'
    parents(directory)
    evidence={}
    for name in ('p1-acceptance','p2-python','p2-godot'):
        raw=(ROOT/'reports/interaction'/f'{name}.json').read_bytes()
        if json.loads(raw).get('passed') is not True:raise ValueError('Unpassed gate: '+name)
        evidence[name]=sha(raw)
    core=json.loads((ROOT/'generated/interaction/core.json').read_text(encoding='utf-8'))
    if core['contract']!=json.loads(encoded(contract_build())) or core['source_acceptance_sha256']!=evidence['p1-acceptance']:
        raise ValueError('Source core contract changed')
    sprites=json.loads((ROOT/'generated/interaction/source-sprites/source-sprites.json').read_text())
    payloads={'core.json':encoded(core),'sprites.json':encoded(sprites)}
    for row in sprites['sprites']:
        raw=(ROOT/'generated/interaction/source-sprites'/row['file']).read_bytes()
        if sha(raw)!=row['sha256']:raise ValueError('Changed source sprite')
        payloads[row['file']]=raw
    audio=json.loads((ROOT/'generated/interaction/source-audio/source-audio.json').read_text())
    payloads['cirrus-pickup.wav']=(ROOT/'generated/interaction/source-audio/cirrus-pickup.wav').read_bytes()
    if sha(payloads['cirrus-pickup.wav'])!=audio['output_sha256'] or not audio['pcm_roundtrip_passed']:
        raise ValueError('Audio conversion differs')
    for route in ROUTES:
        payloads[f'reference-{route}.json']=(ROOT/'generated/interaction/reference'/f'{route}.json').read_bytes()
    if set(payloads)!=NAMES:raise ValueError('Incomplete payload population')
    directory.mkdir(parents=True,exist_ok=True)
    if {p.name for p in directory.iterdir()}-NAMES-{'package.json'}:raise ValueError('Refuse unapproved existing bundle files')
    files={}
    for name,raw in payloads.items():
        (directory/name).write_bytes(raw)
        files[name]={'bytes':len(raw),'sha256':sha(raw)}
        if name.endswith('.png'):
            with Image.open(directory/name) as image:files[name]['dimensions']=list(image.size)
    manifest={'schema':'ao_pc_interaction_bundle_v1','source_local_only':True,'dependencies':DEPENDENCIES,
              'event_id':'map001_cirrus_interaction','files':files,'evidence':evidence,
              'limits':core['contract']['limitations'],'audio':audio}
    raw=encoded(manifest)
    (directory/'package.json').write_bytes(raw)
    (DEMO/'interaction-pin.json').write_bytes(encoded({'schema':'ao_pc_interaction_bundle_pin_v1','manifest_sha256':sha(raw),'dependencies':DEPENDENCIES}))
    verify(directory)
    return {'directory':str(directory),'files':len(files),'manifest_sha256':sha(raw)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','verify'));a=p.parse_args()
    print(json.dumps(build() if a.action=='build' else {'passed':bool(verify())}))
