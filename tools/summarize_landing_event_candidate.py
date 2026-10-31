"""Final functional gates and exact screenshot attachments; performance stays deferred."""
import argparse
import json
from pathlib import Path
import shutil
from PIL import Image
from landing_event_source import ROOT, sha
from equipment_contract import encoded
import audit_landing_event_package as audit


def summarize(folder,screens):
    inventory=audit.audit(folder);info=json.loads((folder/'BUILD-INFO.json').read_bytes())
    if info['source_has_uncommitted_changes']:raise ValueError('Dirty binary source')
    base=ROOT/'reports/landing-event';evidence={}
    def gate(path,key='passed'):
        raw=path.read_bytes();data=json.loads(raw.decode('utf-8-sig'))
        if data.get(key) is not True:raise ValueError('Failed functional gate: '+str(path))
        evidence[path.relative_to(ROOT).as_posix()]=sha(raw);return data
    gate(base/'l1-acceptance.json','l1_complete')
    for name in ('l2-python','l2-godot','l3-acceptance','l4-ui','l4-input','l4-gpu','l4-text-layout','l5-regression'):
        gate(base/(name+'.json'))
    python=gate(base/'l5-python.json','available_tests_passed')
    if python['unexpected'] or len(python['unavailable_old_snapshot'])!=9 or len(python['skipped'])!=7:raise ValueError('Unexpected regression gaps')
    screenshots=gate(screens/'screenshots.json');images=[];seen=set()
    pin=json.loads((ROOT/'exploration-demo/landing-event-pin.json').read_bytes())['manifest_sha256']
    for case in screenshots['cases']:
        key=(case['size'],case['state'])
        if key in seen:raise ValueError('Duplicate screenshot')
        seen.add(key);image=Path(case['image']);report=Path(case['report'])
        if sha(image.read_bytes())!=case['sha256'] or sha(report.read_bytes())!=case['report_sha256']:raise ValueError('Changed screenshot')
        data=gate(report);size=tuple(map(int,case['size'].split('x')))
        if data['performance_tested'] is not False or data['mode']!='screenshot' or data['frame_intervals_ms'] or data['samples'] or data['measured_seconds']!=0:raise ValueError('Unexpected performance measurement')
        if data['event_manifest_sha256']!=pin or not all(data[k] for k in ('panel_layout_valid','toolbar_layout_valid','content_bounds_valid','surface_verified','old_scene_hidden')):raise ValueError('Screenshot layout or bundle failed')
        if tuple(data['actual_viewport'])!=size or Image.open(image).size!=size:raise ValueError('Wrong screenshot resolution')
        story='07' if case['state']=='before' else '0f'
        if (data['weapon'],data['story_item_count'],data['story'],data['attack'])!=(27,0,story,15) or data['scene_id']!=7:raise ValueError('Wrong screenshot state')
        if case['state'] in ('after','boundary') and not data['landing_event_completed']:raise ValueError('Missing event endpoint')
        images.append({'file':case['size']+'-'+case['state']+'.png','sha256':case['sha256'],'size':case['size'],'state':case['state'],'source_image':str(image)})
    if {r['file'] for r in images}!=audit.SCREENSHOTS:raise ValueError('Incomplete screenshot matrix')
    return {'schema':'ao_pc_landing_event_acceptance_v1','passed':False,'functional_passed':True,'performance_tested':False,
        'status':'performance_validation_deferred_by_user','binary_source_commit':info['source_commit'],
        'binary_files':[r for r in inventory['files'] if r['path'].endswith(('.exe','.pck'))],
        'evidence':evidence,'screenshots':images,'python':python,
        'endpoint':'same_scene_control_restored','limits':['No performance/load/FPS test performed.','Original shadows and full music playback remain outside acceptance.','Only source-tested connected query union; no full room, other event, return or third scene.','Old snapshot nine tests unavailable; seven performance-evidence tests skipped.','Stage B incomplete.']}


def install(folder,report):
    for row in report['screenshots']:shutil.copyfile(row['source_image'],folder/row['file'])
    (folder/'LANDING_EVENT_SCREENSHOTS.json').write_bytes(encoded({'passed':True,'performance_tested':False,'cases':[{k:v for k,v in r.items() if k!='source_image'} for r in report['screenshots']]}))
    (folder/'LANDING_EVENT_VALIDATION.json').write_bytes(encoded(report))
    audit.write_build(folder,report['binary_source_commit'],False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--screens',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--install',action='store_true');a=p.parse_args()
    result=summarize(a.folder.resolve(),a.screens.resolve());a.out.write_bytes(encoded(result))
    if a.install:install(a.folder.resolve(),result)
    print(json.dumps({'functional_passed':True,'performance_tested':False,'screenshots':len(result['screenshots']),'binary_source_commit':result['binary_source_commit']}))
