"""Eighth local source-bound bundle. Core-only stage is not a playable release."""
import argparse
import json
from transition_source import ROOT,ROUTES,sha
from equipment_contract import encoded,canonical
from equipment_bundle import DEPENDENCIES as EARLIER,verify as verify_equipment
from exploration_bundle import no_redirect

DEPENDENCIES={**EARLIER,'equipment':'485cd1339805f5c9e288529cb65c3b4a405dd61a953cdfba91ef43a0590eafae'}
DEFAULT=ROOT/'exploration-demo/generated/transition'
PIN=ROOT/'exploration-demo/transition-pin.json'
NAMES={'core.json',*[f'reference-{route}.json' for route in ROUTES]}
CORE_SHA='11b0ded372f5becfa78d75abc9904c30366865fa5009f77d42144c6e4224ce69'


def verify(folder=DEFAULT):
    no_redirect(folder)
    if {p.name for p in folder.iterdir()}!=NAMES|{'package.json'}:raise ValueError('Unknown transition payload')
    for path in folder.iterdir():
        no_redirect(path)
        if not path.is_file():raise ValueError('Transition payload is not a regular file')
    for name,digest in DEPENDENCIES.items():
        if sha((folder.parent/name/'package.json').read_bytes())!=digest:raise ValueError('Changed parent: '+name)
    raw=(folder/'package.json').read_bytes();manifest=json.loads(raw)
    pin=json.loads(PIN.read_bytes())
    if sha(raw)!=pin.get('manifest_sha256'):raise ValueError('Changed transition manifest')
    if (manifest.get('schema')!='ao_pc_transition_bundle_v1' or manifest.get('dependencies')!=DEPENDENCIES
            or manifest.get('stage')!='core_only' or manifest.get('runtime_approved') is not False
            or manifest.get('source_local_only') is not True or set(manifest.get('files',{}))!=NAMES):
        raise ValueError('Unsupported transition bundle contract')
    for name,record in manifest['files'].items():
        raw=(folder/name).read_bytes()
        if sha(raw)!=record['sha256'] or len(raw)!=record['bytes']:raise ValueError('Changed transition resource: '+name)
    if canonical(json.loads((folder/'core.json').read_bytes()))!=CORE_SHA:raise ValueError('Unapproved transition core')
    return manifest


def build():
    verify_equipment()
    evidence={}
    for name in ('t1-acceptance','t2-python','t2-godot'):
        raw=(ROOT/'reports/transition'/f'{name}.json').read_bytes();report=json.loads(raw)
        if not report.get('t1_complete' if name=='t1-acceptance' else 'passed'):raise ValueError('Incomplete transition evidence')
        if report.get('performance_tested') is not False:raise ValueError('Performance status must remain deferred')
        evidence[name]=sha(raw)
    DEFAULT.mkdir(parents=True,exist_ok=True)
    if {p.name for p in DEFAULT.iterdir()}-NAMES-{'package.json'}:raise ValueError('Existing unapproved payload')
    files={}
    for name in sorted(NAMES):
        source=ROOT/'generated/transition'/('reference/'+name.removeprefix('reference-') if name.startswith('reference-') else name)
        raw=source.read_bytes();(DEFAULT/name).write_bytes(raw);files[name]={'bytes':len(raw),'sha256':sha(raw)}
    raw=encoded({'schema':'ao_pc_transition_bundle_v1','stage':'core_only','runtime_approved':False,
                 'source_local_only':True,'dependencies':DEPENDENCIES,'files':files,'evidence':evidence})
    (DEFAULT/'package.json').write_bytes(raw)
    PIN.write_bytes(encoded({'schema':'ao_pc_transition_pin_v1','manifest_sha256':sha(raw),'dependencies':DEPENDENCIES,'runtime_approved':False}))
    verify()
    return {'passed':True,'manifest_sha256':sha(raw),'runtime_approved':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','verify'));a=p.parse_args()
    print(json.dumps(build() if a.action=='build' else {'passed':bool(verify()),'runtime_approved':False}))
