"""Isolated 2.5D candidate export with explicit script and external-art closure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import zipfile
from PIL import Image
import audit_landing_event_package as old
from audit_battle_package import unpack
from audit_exploration_package import remap_target

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'exploration-demo'
REPORTS=ROOT/'reports/enhanced25d-landing'
SCRIPTS=old.SCRIPTS|{'enhanced25d_main','enhanced25d_loader','enhanced25d_renderer','landing25d_main','landing25d_loader','landing25d_renderer','landing25d_animation'}
PINS=old.PINS|{'enhanced25d-pin.json','landing25d-pin.json'}
DOCS={'README.md':'LANDING25D_README.md','ART-NOTICE.md':'LANDING25D_ART.md'}
STATES=['start','equipment-equipped','before','approach',*[f'page-{i}' for i in range(1,9)],'after','boundary']
SIZES=['1920x1080','2560x1440','3840x2160']
ANIMATION=ROOT/'art/enhanced25d-landing/v1/animation-candidate-01'
ATTACHED={'FUNCTIONAL.json':'functional.json','LOADER.json':'loader.json','INPUT.json':'input.json','ANIMATION-TEST.json':'animation-test.json','CHARACTER-REGRESSION.json':'character-regression.json'}
LAYERS=ROOT/'art/enhanced25d-landing/v1'
LAYER_FILES=['landing-layers.ora','production-layout.json','layers-manifest.json','approval.json']

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args): return subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),*args],cwd=ROOT,text=True).strip()

def audit_pck(path):
    files=unpack(path.read_bytes())
    scene=remap_target(files.get('landing25d_main.tscn.remap',b''))
    if not re.fullmatch(r'\.godot/exported/\d+/export-[0-9a-f]{32}-landing25d_main\.scn',scene): raise ValueError('Wrong isolated scene')
    allowed={'.godot/global_script_class_cache.cfg','.godot/uid_cache.bin','project.binary','landing25d_main.tscn.remap',scene,
             'room_priority.gdshader','character_priority.gdshader','transition_fade.gdshader'}|PINS|{f'{n}.{s}' for n in SCRIPTS for s in ('gdc','gd.remap')}
    if set(files)!=allowed: raise ValueError(f'Unapproved PCK closure: {set(files)^allowed}')
    for name in PINS:
        if files[name]!=(SOURCE/name).read_bytes(): raise ValueError('Packaged pin differs: '+name)
    for name in SCRIPTS:
        if remap_target(files[name+'.gd.remap'])!=name+'.gdc' or not files[name+'.gdc'].startswith(b'GDSC'): raise ValueError('Invalid compiled script')
    values=old.character.project_values(files['project.binary'])
    if old.character.variant_string(values['application/run/main_scene'])!='res://landing25d_main.tscn': raise ValueError('Wrong main scene')
    return [{'path':n,'sha256':hashlib.sha256(v).hexdigest()} for n,v in sorted(files.items())]

def external_files():
    import export_enhanced25d as previous
    files=previous.external_files()
    pin=read(SOURCE/'landing25d-pin.json');folder=SOURCE/'generated/enhanced25d-landing'
    if sha(folder/'package.json')!=pin['manifest_sha256']: raise ValueError('Landing art manifest changed')
    manifest=read(folder/'package.json')
    if len(pin['dependencies'])!=10 or manifest['dependencies']!=pin['dependencies']: raise ValueError('Incomplete dependencies')
    for name,value in pin['dependencies'].items():
        if sha(SOURCE/'generated'/name/'package.json')!=value: raise ValueError('Changed input '+name)
    if {p.name for p in folder.iterdir()}!=set(pin['files'])|{'package.json'} or set(manifest['files'])!=set(pin['files']): raise ValueError('Unapproved landing resource')
    for name,r in manifest['files'].items():
        if sha(folder/name)!=r['sha256'] or (folder/name).stat().st_size!=r['bytes']: raise ValueError('Changed art '+name)
    for name in [*pin['files'],'package.json']: files['enhanced25d-landing/'+name]=folder/name
    return files

def attach(folder):
    info=read(folder/'BUILD-INFO.json')
    for name,row in info['files'].items():
        if sha(folder/name)!=row['sha256']: raise ValueError('Changed export before attachment')
    functional=read(REPORTS/'functional.json');loader=read(REPORTS/'loader.json')
    if not functional['passed'] or functional['source_updates']!=57188 or not loader['passed']: raise ValueError('Functional gates incomplete')
    python=read(ROOT/'reports/landing-event/l5-python.json')
    if python['unexpected'] or len(python['unavailable_old_snapshot'])!=9 or len(python['skipped'])!=7: raise ValueError('Python regression differs')
    character=read(REPORTS/'character-regression.json')
    if not character['passed'] or character['source_updates']!=6156: raise ValueError('Character source regression missing')
    counts={'character':6156,'landing25d':57188}
    evidence={}
    for name,count in [('room',15183),('event',20037),('interaction',23910),('equipment',11064),('landing_event',42891),('enhanced25d',57188)]:
        path=ROOT/'reports/exploration'/f'test_{name}_ui.log'
        text=path.read_text(encoding='utf-8-sig');rows=[json.loads(s) for s in text.splitlines() if s.startswith('{')]
        if len(rows)!=1 or not rows[0]['passed'] or rows[0]['source_updates']!=count: raise ValueError('Incomplete regression '+name)
        counts[name]=count;evidence[path.relative_to(ROOT).as_posix()]=sha(path)
    for name,path,count,key in [('movement',ROOT/'reports/exploration/godot-movement-validation.json',1680,'updates'),('transition',ROOT/'reports/transition/t4-ui.json',10965,'source_updates')]:
        data=read(path)
        if not data['passed'] or data[key]!=count: raise ValueError('Incomplete regression '+name)
        counts[name]=count;evidence[path.relative_to(ROOT).as_posix()]=sha(path)
    for leaf,marker in [('battle-regression.log','Battle core, UI, presentation, timing and package checks passed.'),('exploration-regression.log','Exploration Godot, bundle, package and QA acceptance tests passed.'),('runtime-regression.log','"checks":14,"failures":[]'),('workbench-regression.log','"real_textures_loaded":true'),('art-tests.log','Ran 4 tests')]:
        path=REPORTS/leaf;text=path.read_text(encoding='utf-8-sig')
        if marker not in text or any(s in text for s in ['SCRIPT ERROR:','Parse Error:','Assertion failed','FAILED (']): raise ValueError('Missing regression '+leaf)
        evidence[path.relative_to(ROOT).as_posix()]=sha(path)
    matrix=json.loads((REPORTS/'capture-matrix.json').read_text(encoding='utf-8-sig'))
    if len(matrix)!=len(STATES)*len(SIZES) or {(r['size'],r['state']) for r in matrix}!={(s,t) for s in SIZES for t in STATES}: raise ValueError('Incomplete screenshot matrix')
    (folder/'SCREENSHOTS').mkdir();(folder/'REPORTS').mkdir()
    screens=[]
    for row in matrix:
        origin=Path(row['folder']); report=read(origin/'result.json')
        size=list(map(int,row['size'].split('x')))
        if not report['passed'] or not report['content_bounds_valid'] or report['actual_viewport']!=size or report['mode']!='screenshot' or report['measured_seconds']!=0 or report['frame_intervals_ms'] or report['performance_tested']: raise ValueError('Invalid functional screenshot')
        if report['effective_appearance']!='enhanced25d': raise ValueError('Wrong scene appearance policy')
        if row['state']=='after' and not report['landing_event_completed']: raise ValueError('LAIA did not finish')
        with Image.open(origin/'screen.png') as image:
            if list(image.size)!=size: raise ValueError('Screenshot size differs')
        name=row['size']+'-'+row['state']
        shutil.copyfile(origin/'screen.png',folder/'SCREENSHOTS'/(name+'.png'))
        shutil.copyfile(origin/'result.json',folder/'REPORTS'/(name+'.json'))
        screens.append({'size':size,'state':row['state'],'sha256':sha(origin/'screen.png')})
    for name in ['input.json','animation-test.json']:
        if not read(REPORTS/name)['passed']: raise ValueError('New input/animation check failed')
    for target,source in ATTACHED.items(): shutil.copyfile(REPORTS/source,folder/target)
    write(folder/'PYTHON.json',python)
    write(folder/'REGRESSION.json',{'passed':True,'source_updates':counts,'evidence':evidence,'performance_tested':False})
    write(folder/'VALIDATION.json',{'schema':'ao_pc_landing25d_acceptance_v1','functional_passed':True,'performance_tested':False,'performance_status':'deferred_by_user','source_commit':info['source_commit'],'source_updates':counts,'screenshots':screens,'old_missing_snapshot_tests':9,'performance_dependent_skips':7,'new_art_python_tests':4,'initial_appdata_log_warning_preserved':True,'package_and_extracted_launch':'recorded_separately_after_archive_creation'})
    for name in LAYER_FILES:
        target=folder/'ART-LAYERS'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(LAYERS/name,target)
    art=read(ANIMATION/'animation.json')
    for name,row in art['files'].items():
        if sha(ANIMATION/name)!=row['sha256']: raise ValueError('Changed animation attachment')
        target=folder/'ANIMATION'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ANIMATION/name,target)
    shutil.copyfile(ANIMATION/'animation.json',folder/'ANIMATION/animation.json')
    info['files']={p.relative_to(folder).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='BUILD-INFO.json'}
    write(folder/'BUILD-INFO.json',info)
    write(REPORTS/'acceptance.json',read(folder/'VALIDATION.json'))
    print(json.dumps({'attachments':len(info['files']),'screenshots':len(matrix),'performance_tested':False}))

def approved_delivery_names():
    art=read(ANIMATION/'animation.json')
    return set(external_files())|{'MAP001-25D-Landing.exe','MAP001-25D-Landing.pck','BUILD-INFO.json','GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt','PYTHON.json','REGRESSION.json','VALIDATION.json'}|set(DOCS)|set(ATTACHED)|{'ANIMATION/'+n for n in art['files']}|{'ANIMATION/animation.json'}|{'ART-LAYERS/'+n for n in LAYER_FILES}|{'SCREENSHOTS/'+s+'-'+t+'.png' for s in SIZES for t in STATES}|{'REPORTS/'+s+'-'+t+'.json' for s in SIZES for t in STATES}

def export(output):
    if git('status','--porcelain'): raise ValueError('Commit source before export')
    output=output.resolve()
    if output.parent!=(ROOT/'build').resolve() or output.exists(): raise ValueError('New direct build child required')
    external=external_files()
    stage=ROOT/'build'/('landing25d-export-'+uuid.uuid4().hex)
    stage.mkdir(); output.mkdir()
    for name in SCRIPTS: shutil.copyfile(SOURCE/(name+'.gd'),stage/(name+'.gd'))
    for name in PINS|{'landing25d_main.tscn','character_priority.gdshader','room_priority.gdshader','transition_fade.gdshader'}: shutil.copyfile(SOURCE/name,stage/name)
    settings=(SOURCE/'project.godot').read_text(encoding='utf-8')
    settings='\n'.join(s for s in settings.splitlines() if not s.startswith('run/main_scene.'))+'\n'
    settings=settings.replace('run/main_scene="res://main.tscn"','run/main_scene="res://landing25d_main.tscn"')
    (stage/'project.godot').write_text(settings,encoding='utf-8')
    templates=(ROOT.parent/'tools/pc-remake/export-templates-4.7.2/templates').as_posix()
    preset='''[preset.0]
name="Windows Landing25D"
platform="Windows Desktop"
runnable=true
export_filter="selected_scenes"
export_files=PackedStringArray("res://landing25d_main.tscn")
include_filter="PINS"
exclude_filter="generated/*,tests/*,*.md"
script_export_mode=2
[preset.0.options]
custom_template/debug="TEMPLATES/windows_debug_x86_64.exe"
custom_template/release="TEMPLATES/windows_release_x86_64.exe"
binary_format/architecture="x86_64"
binary_format/embed_pck=false
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
codesign/enable=false
application/modify_resources=false
'''.replace('TEMPLATES',templates).replace('PINS',','.join(sorted(PINS)))
    (stage/'export_presets.cfg').write_text(preset,encoding='utf-8')
    env=os.environ.copy()
    for name,leaf in [('APPDATA','appdata'),('TEMP','temp'),('TMP','temp')]:
        path=stage/leaf;path.mkdir(exist_ok=True);env[name]=str(path)
    godot=ROOT.parent/'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
    for name,args in [('import',['--editor','--import','--quit']),('export',['--export-release','Windows Landing25D',str(output/'MAP001-25D-Landing.exe')])]:
        result=subprocess.run([str(godot),'--headless','--path',str(stage),*args],env=env,capture_output=True,text=True,encoding='utf-8')
        log=result.stdout+result.stderr;(REPORTS/('export-'+name+'.log')).write_text(log,encoding='utf-8')
        if result.returncode or any(s in log for s in ['SCRIPT ERROR:','ERROR:','Parse Error:']): raise ValueError('Export failed: '+name)
    pck=audit_pck(output/'MAP001-25D-Landing.pck')
    for name,source in external.items():
        target=output/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
    for name in ['GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt']: shutil.copyfile(ROOT/'licenses'/name,output/name)
    for target,source in DOCS.items(): shutil.copyfile(ROOT/'docs'/source,output/target)
    commit=git('rev-parse','HEAD')
    write(output/'BUILD-INFO.json',{'schema':'ao_pc_landing25d_build_v1','source_commit':commit,'dirty':False,'performance_tested':False,'pck_resources':pck,
        'files':{p.relative_to(output).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file()}})
    write(REPORTS/'candidate.json',{'directory':str(output),'source_commit':commit,'stage':str(stage)})
    print(json.dumps({'directory':str(output),'commit':commit}))

def package(folder,archive,extracted):
    if archive.exists() or extracted.exists(): raise ValueError('Preserve earlier archives and extracted runs')
    info=read(folder/'BUILD-INFO.json');expected=set(info['files'])|{'BUILD-INFO.json'}
    actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual!=approved_delivery_names(): raise ValueError('Unapproved delivery resources: '+str(actual^approved_delivery_names()))
    expected_dirs={str(Path(n).parent).replace('\\','/') for n in actual if '/' in n}
    expected_dirs|={str(Path(n).parent).replace('\\','/') for n in list(expected_dirs) if '/' in n}
    if {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_dir()}!=expected_dirs: raise ValueError('Unapproved delivery directories')
    for path in folder.rglob('*'): old.room.no_redirect(path)
    if actual!=expected: raise ValueError('Delivery file closure differs')
    for name,row in info['files'].items():
        if sha(folder/name)!=row['sha256']: raise ValueError('Delivery file changed')
    audit_pck(folder/'MAP001-25D-Landing.pck')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(expected): z.write(folder/name,name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or set(z.namelist())!=expected: raise ValueError('ZIP closure or CRC failed')
        z.extractall(extracted)
    for name in expected:
        if sha(extracted/name)!=sha(folder/name): raise ValueError('Extracted file mismatch')
    result={'schema':'ao_pc_landing25d_package_audit_v1','passed':True,'archive':str(archive),'sha256':sha(archive),'files':len(expected),'source_commit':info['source_commit'],'extracted':str(extracted),'performance_tested':False}
    write(REPORTS/'package-audit.json',result);print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    e=s.add_parser('export');e.add_argument('--output',type=Path,required=True)
    e=s.add_parser('attach');e.add_argument('--folder',type=Path,required=True)
    e=s.add_parser('package');e.add_argument('--folder',type=Path,required=True);e.add_argument('--archive',type=Path,required=True);e.add_argument('--extracted',type=Path,required=True)
    a=p.parse_args()
    if a.command=='export': export(a.output)
    elif a.command=='attach': attach(a.folder)
    else: package(a.folder,a.archive,a.extracted)
