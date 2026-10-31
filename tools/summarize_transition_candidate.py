"""Functional candidate gate; deliberately cannot approve deferred performance."""
import argparse
import json
from pathlib import Path
import shutil
from PIL import Image
from transition_source import ROOT,sha
from equipment_contract import encoded
import audit_transition_package as audit


def summarize(folder,screens):
    inspected=audit.audit(folder);info=json.loads((folder/'BUILD-INFO.json').read_bytes())
    if info['source_has_uncommitted_changes'] is not False:raise ValueError('Binary source must be clean')
    base=ROOT/'reports/transition';evidence={}
    def gate(path):
        raw=path.read_bytes();data=json.loads(raw.decode('utf-8-sig'))
        if data.get('passed') is not True:raise ValueError('Failed functional gate: '+str(path))
        evidence[path.relative_to(ROOT).as_posix()]=sha(raw);return data
    for name in ('t1-acceptance','t3-acceptance','t4-core','t4-ui','t4-input','t4-gpu','t5-character'):
        # T1 explicitly reports source-stage completion rather than release pass.
        if name=='t1-acceptance':
            raw=(base/(name+'.json')).read_bytes();data=json.loads(raw)
            if not data['t1_complete']:raise ValueError('T1 source incomplete')
            evidence[(base/(name+'.json')).relative_to(ROOT).as_posix()]=sha(raw)
        else:gate(base/(name+'.json'))
    if gate(base/'t4-ui.json')['source_updates']!=10965:raise ValueError('Transition UI coverage missing')
    if gate(base/'t5-character.json')['source_updates']!=6156:raise ValueError('Actual HD/original/marker character regression missing')
    movement=gate(ROOT/'reports/exploration/godot-movement-validation.json')
    if movement['updates']!=1680:raise ValueError('Movement regression incomplete')
    regressions={}
    for name,count in [('room',15183),('event',20037),('interaction',23910),('equipment',11064)]:
        path=ROOT/'reports/exploration'/f'test_{name}_ui.log';raw=path.read_bytes();text=raw.decode('utf-8')
        rows=[json.loads(line) for line in text.splitlines() if line.startswith('{')]
        if len(rows)!=1 or not rows[0]['passed'] or rows[0]['source_updates']!=count or 'SCRIPT ERROR:' in text:raise ValueError('Legacy source regression failed: '+name)
        evidence[path.relative_to(ROOT).as_posix()]=sha(raw);regressions[name]=count
    for name,marker in [('t5-exploration.log','Exploration Godot, bundle, package and QA acceptance tests passed.'),
                         ('t5-battle.log','Battle core, UI, presentation, timing and package checks passed.'),
                         ('t5-runtime.log','"checks":14,"failures":[]'),('t5-workbench.log','"real_textures_loaded":true'),
                         ('t5-package-tests.log','Ran 7 tests')]:
        raw=(base/name).read_bytes();text=raw.decode('utf-8',errors='replace')
        if marker not in text or any(t in text for t in ('SCRIPT ERROR:','Parse Error:','FAILED (')):raise ValueError('Missing regression evidence: '+name)
        evidence[(base/name).relative_to(ROOT).as_posix()]=sha(raw)
    raw=(base/'t5-python.json').read_bytes();python=json.loads(raw)
    if not python['available_tests_passed'] or python['unexpected'] or len(python['unavailable_old_snapshot'])!=9 or len(python['skipped'])!=7:raise ValueError('Unexpected Python test gaps')
    evidence['reports/transition/t5-python.json']=sha(raw)
    screenshots=gate(screens/'screenshots.json');seen=set();images=[]
    pin=json.loads((ROOT/'exploration-demo/transition-pin.json').read_bytes())['manifest_sha256']
    for case in screenshots['cases']:
        key=(case['size'],case['state'])
        if key in seen:raise ValueError('Duplicate screenshot case')
        seen.add(key);image=Path(case['image']);report=Path(case['report'])
        if sha(image.read_bytes())!=case['sha256'] or sha(report.read_bytes())!=case['report_sha256']:raise ValueError('Screenshot evidence changed')
        data=gate(report);size=tuple(map(int,case['size'].split('x')))
        if data['performance_tested'] is not False or data['mode']!='screenshot' or data['frame_intervals_ms'] or data['samples'] or data['measured_seconds']!=0:raise ValueError('Unexpected performance measurement')
        if data['transition_manifest_sha256']!=pin or not all(data[k] for k in ('panel_layout_valid','toolbar_layout_valid','content_bounds_valid','surface_verified','old_scene_hidden')):raise ValueError('Wrong screenshot bundle or layout')
        if tuple(data['actual_viewport'])!=size or Image.open(image).size!=size:raise ValueError('Wrong actual screenshot resolution')
        if (data['weapon'],data['story_item_count'],data['story'],data['attack'])!=(27,0,'07',15):raise ValueError('Persistent state changed')
        if data['scene_id']!=(8 if case['state']=='before' else 7):raise ValueError('Wrong screenshot scene')
        if case['state']=='fade' and data['rgb']!=[-127]*3:raise ValueError('Fade screenshot is not mid-presentation')
        images.append({'file':case['size']+'-'+case['state']+'.png','sha256':case['sha256'],'size':case['size'],'state':case['state'],'source_image':str(image)})
    if {r['file'] for r in images}!=audit.SCREENSHOTS:raise ValueError('Incomplete three-resolution screenshot matrix')
    return {'schema':'ao_pc_transition_acceptance_v1','passed':False,'functional_passed':True,'performance_tested':False,
            'status':'performance_validation_deferred_by_user','binary_source_commit':info['source_commit'],
            'binary_files':[f for f in inspected['files'] if f['path'].endswith(('.exe','.pck'))],
            'evidence':evidence,'screenshots':images,'legacy_source_updates':{'movement':1680,'character':6156,**regressions},
            'python':{'full_run':python['tests'],'full_run_passed':python['passed'],'additional_package_tests':7,'total_passed':python['passed']+7,
                      'unavailable_old_snapshot':python['unavailable_old_snapshot'],'skipped_performance_evidence':python['skipped']},
            'limits':['No load, long-loop, performance benchmark or actual GPU FPS test executed.',
                      'Only first controllable viewport connected source-tested corridor; no return or other event/scene.',
                      'Shadow, full destination exploration, prior performance acceptance and whole Stage B incomplete.']}


def install(folder,report):
    for row in report['screenshots']:shutil.copyfile(row['source_image'],folder/row['file'])
    (folder/'TRANSITION_SCREENSHOTS.json').write_bytes(encoded({'passed':True,'performance_tested':False,'cases':[{k:v for k,v in r.items() if k!='source_image'} for r in report['screenshots']]}))
    (folder/'TRANSITION_VALIDATION.json').write_bytes(encoded(report))
    audit.write_build(folder,report['binary_source_commit'],False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--screens',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--install',action='store_true');a=p.parse_args()
    result=summarize(a.folder.resolve(),a.screens.resolve());a.out.write_bytes(encoded(result))
    if a.install:install(a.folder.resolve(),result)
    print(json.dumps({'functional_passed':True,'performance_tested':False,'screenshots':len(result['screenshots']),'binary_source_commit':result['binary_source_commit']}))
