"""Ninth local source-bound bundle. Source approval does not certify performance."""
import argparse
import json
from landing_event_source import ROOT,sha
from equipment_contract import encoded,canonical
from transition_bundle import DEPENDENCIES as EARLIER,verify as verify_transition
from exploration_bundle import no_redirect

DEPENDENCIES={**EARLIER,'transition':'9e817699364aca759cdb4d8fe87ccab34bc5afc4a6fbd9cf5cdb50d1c9277aa8'}
DEFAULT=ROOT/'exploration-demo/generated/landing-event'
PIN=ROOT/'exploration-demo/landing-event-pin.json'
ROUTES=('equip','remove','reequip','edge-held')
ART={f'actor-50-{image:02d}-{flip}.png' for image in range(3,9) for flip in ((0,1) if image in (3,4,5) else (0,))}
NAMES={'core.json','visuals.json','dialogue.json',*ART,*[f'reference-{route}.json' for route in ROUTES]}
CORE_SHA='4226836f9db95c244f7bfe6cbdd5a37fb49fecd9e482a66fc625533286269f32'



def verify(folder=DEFAULT):
    no_redirect(folder)
    if {p.name for p in folder.iterdir()}!=NAMES|{'package.json'}:raise ValueError('Unknown landing-event payload')
    for path in folder.iterdir():
        no_redirect(path)
        if not path.is_file():raise ValueError('Transition payload is not a regular file')
    for name,digest in DEPENDENCIES.items():
        if sha((folder.parent/name/'package.json').read_bytes())!=digest:raise ValueError('Changed parent: '+name)
    raw=(folder/'package.json').read_bytes();manifest=json.loads(raw)
    pin=json.loads(PIN.read_bytes())
    if sha(raw)!=pin.get('manifest_sha256'):raise ValueError('Changed landing-event manifest')
    if (manifest.get('schema')!='ao_pc_landing_event_bundle_v1' or manifest.get('dependencies')!=DEPENDENCIES
            or manifest.get('stage')!='source_verified' or manifest.get('runtime_approved') is not True
            or manifest.get('source_local_only') is not True or set(manifest.get('files',{}))!=NAMES):
        raise ValueError('Unsupported landing-event bundle contract')
    for name,record in manifest['files'].items():
        raw=(folder/name).read_bytes()
        if sha(raw)!=record['sha256'] or len(raw)!=record['bytes']:raise ValueError('Changed landing-event resource: '+name)
    if canonical(json.loads((folder/'core.json').read_bytes()))!=CORE_SHA:raise ValueError('Unapproved landing-event core')
    return manifest


def build():
    verify_transition()
    evidence={}
    for name in ('l1-acceptance','l2-python','l2-godot','l3-acceptance'):
        raw=(ROOT/'reports/landing-event'/f'{name}.json').read_bytes();report=json.loads(raw)
        if not report.get('l1_complete' if name=='l1-acceptance' else 'passed'):raise ValueError('Incomplete landing-event evidence')
        if report.get('performance_tested') is not False:raise ValueError('Performance status must remain deferred')
        evidence[name]=sha(raw)
    lock=json.loads((ROOT/'data/landing-event/visual-lock.json').read_bytes())
    if evidence['l3-acceptance']!=lock['report_sha256'] or sha((ROOT/'generated/landing-event/visuals.json').read_bytes())!=lock['visuals_sha256']:raise ValueError('Landing evidence or art changed')
    DEFAULT.mkdir(parents=True,exist_ok=True)
    if {p.name for p in DEFAULT.iterdir()}-NAMES-{'package.json'}:raise ValueError('Existing unapproved payload')
    files={}
    for name in sorted(NAMES):
        source=ROOT/'generated/landing-event'/('reference/'+name.removeprefix('reference-') if name.startswith('reference-') else name)
        raw=source.read_bytes();(DEFAULT/name).write_bytes(raw);files[name]={'bytes':len(raw),'sha256':sha(raw)}
    raw=encoded({'schema':'ao_pc_landing_event_bundle_v1','stage':'source_verified','runtime_approved':True,
                 'performance_tested':False,'source_local_only':True,'dependencies':DEPENDENCIES,'files':files,'evidence':evidence})
    (DEFAULT/'package.json').write_bytes(raw)
    PIN.write_bytes(encoded({'schema':'ao_pc_landing_event_pin_v1','manifest_sha256':sha(raw),'dependencies':DEPENDENCIES,'runtime_approved':True}))
    verify()
    return {'passed':True,'manifest_sha256':sha(raw),'runtime_approved':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','verify'));a=p.parse_args()
    print(json.dumps(build() if a.action=='build' else {'passed':bool(verify()),'runtime_approved':True}))
