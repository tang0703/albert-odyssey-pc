"""Functional-only candidate gate. Never converts screenshots to performance acceptance."""
import argparse
import json
import re
from pathlib import Path
from PIL import Image
import audit_equipment_package as audit
from equipment_contract import ROOT,sha,encoded

BASE=ROOT/'reports/equipment'
STATES={'unowned':(255,0,'01',10),'owned':(255,1,'03',10),'equipped':(27,0,'07',15),'removed':(255,1,'07',10),'boundary':(27,0,'07',15)}

def summarize(folder,screens):
    inspected=audit.audit(folder)
    info=json.loads((folder/'BUILD-INFO.json').read_bytes())
    if info['source_has_uncommitted_changes'] is not False:raise ValueError('Dirty binary source')
    evidence={}
    def gate(path):
        raw=path.read_bytes();data=json.loads(raw.decode('utf-8-sig'))
        if data.get('passed') is not True:raise ValueError('Incomplete '+str(path))
        evidence[str(path.relative_to(ROOT)).replace('\\','/')]=sha(raw)
        return data
    for name in ('q1-acceptance','q2-python','q2-godot','q3-ui','q4-compat','q4-gpu','q4-character','q5-input'):
        gate(BASE/(name+'.json'))
    if json.loads((BASE/'q3-ui.json').read_bytes())['source_updates']!=11064:raise ValueError('Equipment coverage changed')
    if json.loads((BASE/'q4-compat.json').read_bytes())['updates']!=7970:raise ValueError('Old interaction coverage changed')
    log=(BASE/'q4-python-localtemp.log').read_text(encoding='utf-8',errors='replace')
    errors=re.findall(r'^ERROR: (.+)$',log,re.M)
    expected=['test_real_parameters_and_unsupported_settings','test_snapshot_pages_and_negative_raw_source_matches','test_full_source_vram_match','test_full_source_replay_matches_pinned_snapshot','test_real_block_provenance_without_collision_claim','test_system_ram_boundaries_and_mutation','test_all_visible_patterns_and_prior_viewports_match','test_pinned_region_registers_and_memory','test_real_palette_samples_remain_diagnostic']
    known_guards=(log.count('ValueError: Source hash mismatch:')==7 and log.count('ValueError: Pinned little-endian v13 state required')==1 and log.count('ValueError: Save-state fixture identity changed')==1)
    if {e.split(' ')[0] for e in errors}!=set(expected) or len(errors)!=9 or 'Ran 418 tests' not in log or 'FAILED (errors=9, skipped=7)' not in log or not known_guards:raise ValueError('Unexplained Python regression')
    logs={'q4-python-localtemp.log':'FAILED (errors=9, skipped=7)','q4-exploration.log':'Exploration Godot, bundle, package and QA acceptance tests passed.', 'q4-battle.log':'Battle core, UI, presentation, timing and package checks passed.','q4-runtime.log':'"checks":14,"failures":[]','q4-workbench.log':'"real_textures_loaded":true','q5-package-tests.log':'Ran 7 tests'}
    for name,marker in logs.items():
        raw=(BASE/name).read_bytes();text=raw.decode('utf-8',errors='replace')
        if marker not in text or ('SCRIPT ERROR:' in text) or (name=='q5-package-tests.log' and not text.rstrip().endswith('OK')):raise ValueError('Incomplete regression '+name)
        evidence['reports/equipment/'+name]=sha(raw)
    for name,count in [('test_room_ui',15183),('test_event_ui',20037),('test_interaction_ui',23910)]:
        raw=(ROOT/'reports/exploration'/f'{name}.log').read_bytes()
        records=[json.loads(line) for line in raw.decode('utf-8',errors='replace').splitlines() if line.startswith('{')]
        if len(records)!=1 or records[0].get('passed') is not True or records[0].get('source_updates')!=count:raise ValueError('Old UI coverage missing')
        evidence['reports/exploration/'+name+'.log']=sha(raw)
    gate(ROOT/'reports/exploration/godot-movement-validation.json')
    manifest=gate(screens/'screenshots.json');seen=set();images=[]
    pin=json.loads((ROOT/'exploration-demo/equipment-pin.json').read_bytes())['manifest_sha256']
    for case in manifest['cases']:
        key=(case['size'],case['state'])
        if key in seen:raise ValueError('Duplicate screenshot')
        seen.add(key)
        image=Path(case['image']);report=Path(case['report'])
        if sha(image.read_bytes())!=case['sha256'] or sha(report.read_bytes())!=case['report_sha256']:raise ValueError('Changed screenshot evidence')
        data=gate(report)
        if data['performance_tested'] is not False or data['mode']!='screenshot' or data['frame_intervals_ms'] or data['samples'] or data['measured_seconds']!=0:raise ValueError('Unexpected performance measurement')
        if data['equipment_manifest_sha256']!=pin or not data['panel_layout_valid'] or not data['toolbar_layout_valid'] or not data['surface_verified']:raise ValueError('Wrong package or layout')
        size=tuple(map(int,case['size'].split('x')))
        if tuple(data['actual_viewport'])!=size or Image.open(image).size!=size:raise ValueError('Wrong actual surface')
        if tuple(data[k] for k in ('weapon','story_item_count','story','attack'))!=STATES[case['state']]:raise ValueError('Wrong equipment state')
        if data['boundary_shown']!=(case['state']=='boundary'):raise ValueError('Wrong transition boundary')
        images.append({'path':str(image.relative_to(ROOT)).replace('\\','/'),'sha256':case['sha256'],'size':case['size'],'state':case['state']})
    if seen!={(size,state) for size in ('1920x1080','2560x1440','3840x2160') for state in STATES}:raise ValueError('Incomplete screenshot matrix')
    return {'schema':'ao_pc_equipment_acceptance_v1','passed':False,'functional_passed':True,'performance_tested':False,'status':'performance_validation_deferred_by_user',
            'binary_source_commit':info['source_commit'],'binary_files':[f for f in inspected['files'] if f['path'].endswith(('.exe','.pck'))],
            'evidence':evidence,'screenshots':images,'python':{'tests':425,'passed':409,'skipped_performance_evidence':7,'missing_old_snapshot':9},
            'limits':['No load, long-loop or performance benchmark executed. Screenshot timing fields are unmeasured placeholders.','Original shadow, next room, actual GPU 120 FPS, previous P5 spike review and whole Stage B remain incomplete.']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--screens',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=summarize(a.folder.resolve(),a.screens.resolve());a.out.write_bytes(encoded(result));print(json.dumps({'functional_passed':True,'performance_tested':False,'source_commit':result['binary_source_commit'],'screenshots':len(result['screenshots'])}))
