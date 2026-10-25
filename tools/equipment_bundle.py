"""Seventh local bundle; all six existing parents remain unchanged."""
import argparse
import json
from pathlib import Path
from equipment_contract import ROOT, ROUTES, build as contract, encoded, sha
from interaction_bundle import DEPENDENCIES as PREVIOUS, verify as verify_previous
from exploration_bundle import no_redirect

DEPENDENCIES={**PREVIOUS,'interaction':'365489c2f1c59410f26babb2e461c3dd2d25fb597d65306c4788aca01ff6a71e'}
DEFAULT=ROOT/'exploration-demo/generated/equipment'
NAMES={'core.json',*[f'reference-{r}.json' for r in ROUTES]}
PIN=ROOT/'exploration-demo/equipment-pin.json'
def verify(folder=DEFAULT):
    no_redirect(folder)
    if {p.name for p in folder.iterdir()}!=NAMES|{'package.json'}:raise ValueError('Unapproved equipment resources')
    for p in folder.iterdir():
        no_redirect(p)
        if not p.is_file():raise ValueError('Equipment payload is not a file')
    for name,digest in DEPENDENCIES.items():
        if sha((folder.parent/name/'package.json').read_bytes())!=digest:raise ValueError('Parent changed: '+name)
    pin=json.loads(PIN.read_bytes());raw=(folder/'package.json').read_bytes()
    if sha(raw)!=pin['manifest_sha256']:raise ValueError('Equipment manifest changed')
    manifest=json.loads(raw)
    if manifest.get('schema')!='ao_pc_equipment_bundle_v1' or manifest.get('dependencies')!=DEPENDENCIES or set(manifest.get('files',{}))!=NAMES or manifest.get('source_local_only') is not True:raise ValueError('Invalid equipment bundle')
    for name,record in manifest['files'].items():
        raw=(folder/name).read_bytes()
        if sha(raw)!=record['sha256'] or len(raw)!=record['bytes']:raise ValueError('Changed equipment payload')
    if json.loads((folder/'core.json').read_bytes())['contract']!=json.loads(encoded(contract())):raise ValueError('Unapproved equipment operations')
    return manifest

def build():
    verify_previous()
    evidence={}
    for name in ('q1-acceptance','q2-python','q2-godot'):
        raw=(ROOT/'reports/equipment'/f'{name}.json').read_bytes()
        if json.loads(raw)['passed'] is not True:raise ValueError('Incomplete '+name)
        evidence[name]=sha(raw)
    DEFAULT.mkdir(parents=True,exist_ok=True)
    if {p.name for p in DEFAULT.iterdir()}-NAMES-{'package.json'}:raise ValueError('Unknown existing equipment files')
    files={}
    for name in sorted(NAMES):
        source=ROOT/'generated/equipment'/('reference/'+name.removeprefix('reference-') if name.startswith('reference-') else name)
        raw=source.read_bytes();(DEFAULT/name).write_bytes(raw);files[name]={'bytes':len(raw),'sha256':sha(raw)}
    manifest={'schema':'ao_pc_equipment_bundle_v1','source_local_only':True,'dependencies':DEPENDENCIES,'files':files,'evidence':evidence}
    raw=encoded(manifest);(DEFAULT/'package.json').write_bytes(raw)
    PIN.write_bytes(encoded({'schema':'ao_pc_equipment_pin_v1','manifest_sha256':sha(raw),'dependencies':DEPENDENCIES}))
    verify();return {'manifest_sha256':sha(raw),'files':len(files)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','verify'));a=p.parse_args()
    r=build() if a.action=='build' else verify();print(json.dumps({'passed':True,'manifest_sha256':sha((DEFAULT/'package.json').read_bytes())}))
