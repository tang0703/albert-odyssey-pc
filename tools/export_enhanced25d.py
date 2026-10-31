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
import audit_landing_event_package as old
from audit_battle_package import unpack
from audit_exploration_package import remap_target

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'exploration-demo'
REPORTS=ROOT/'reports/enhanced25d'
SCRIPTS=old.SCRIPTS|{'enhanced25d_main','enhanced25d_loader','enhanced25d_renderer'}
PINS=old.PINS|{'enhanced25d-pin.json'}
DOCS={'README.md':'ENHANCED25D_README.md','ART-NOTICE.md':'ENHANCED25D_ART.md'}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args): return subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),*args],cwd=ROOT,text=True).strip()

def audit_pck(path):
    files=unpack(path.read_bytes())
    scene=remap_target(files.get('enhanced25d_main.tscn.remap',b''))
    if not re.fullmatch(r'\.godot/exported/\d+/export-[0-9a-f]{32}-enhanced25d_main\.scn',scene): raise ValueError('Wrong isolated scene')
    allowed={'.godot/global_script_class_cache.cfg','.godot/uid_cache.bin','project.binary','enhanced25d_main.tscn.remap',scene,
             'room_priority.gdshader','character_priority.gdshader','transition_fade.gdshader'}|PINS|{f'{n}.{s}' for n in SCRIPTS for s in ('gdc','gd.remap')}
    if set(files)!=allowed: raise ValueError(f'Unapproved PCK closure: {set(files)^allowed}')
    for name in PINS:
        if files[name]!=(SOURCE/name).read_bytes(): raise ValueError('Packaged pin differs: '+name)
    for name in SCRIPTS:
        if remap_target(files[name+'.gd.remap'])!=name+'.gdc' or not files[name+'.gdc'].startswith(b'GDSC'): raise ValueError('Invalid compiled script')
    values=old.character.project_values(files['project.binary'])
    if old.character.variant_string(values['application/run/main_scene'])!='res://enhanced25d_main.tscn': raise ValueError('Wrong main scene')
    return [{'path':n,'sha256':hashlib.sha256(v).hexdigest()} for n,v in sorted(files.items())]

def external_files():
    pin=read(SOURCE/'enhanced25d-pin.json')
    files={}
    for bundle,names in old.BUNDLES.items():
        if sha(SOURCE/'generated'/bundle/'package.json')!=pin['dependencies'][bundle]: raise ValueError('Old bundle identity changed')
        for name in names: files[bundle+'/'+name]=SOURCE/'generated'/bundle/name
    folder=SOURCE/'generated/enhanced25d'
    if sha(folder/'package.json')!=pin['manifest_sha256']: raise ValueError('Art pin differs')
    manifest=read(folder/'package.json')
    if manifest['dependencies']!=pin['dependencies'] or set(manifest['files'])!=set(pin['files']): raise ValueError('Art dependencies or closure differ')
    if {p.name for p in folder.iterdir()}!=set(pin['files'])|{'package.json'}: raise ValueError('Unapproved external art')
    for name in pin['files']:
        if sha(folder/name)!=manifest['files'][name]['sha256']: raise ValueError('Art content changed: '+name)
    for name in [*pin['files'],'package.json']: files['enhanced25d/'+name]=folder/name
    return files

def export(output):
    if git('status','--porcelain'): raise ValueError('Commit source before export')
    output=output.resolve()
    if output.parent!=(ROOT/'build').resolve() or output.exists(): raise ValueError('New direct build child required')
    external=external_files()
    stage=ROOT/'build'/('enhanced25d-export-'+uuid.uuid4().hex)
    stage.mkdir(); output.mkdir()
    for name in SCRIPTS: shutil.copyfile(SOURCE/(name+'.gd'),stage/(name+'.gd'))
    for name in PINS|{'enhanced25d_main.tscn','character_priority.gdshader','room_priority.gdshader','transition_fade.gdshader'}: shutil.copyfile(SOURCE/name,stage/name)
    settings=(SOURCE/'project.godot').read_text(encoding='utf-8')
    settings='\n'.join(s for s in settings.splitlines() if not s.startswith('run/main_scene.'))+'\n'
    settings=settings.replace('run/main_scene="res://main.tscn"','run/main_scene="res://enhanced25d_main.tscn"')
    (stage/'project.godot').write_text(settings,encoding='utf-8')
    templates=(ROOT.parent/'tools/pc-remake/export-templates-4.7.2/templates').as_posix()
    preset='''[preset.0]
name="Windows Enhanced25D"
platform="Windows Desktop"
runnable=true
export_filter="selected_scenes"
export_files=PackedStringArray("res://enhanced25d_main.tscn")
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
    for name,args in [('import',['--editor','--import','--quit']),('export',['--export-release','Windows Enhanced25D',str(output/'MAP001-25D.exe')])]:
        result=subprocess.run([str(godot),'--headless','--path',str(stage),*args],env=env,capture_output=True,text=True,encoding='utf-8')
        log=result.stdout+result.stderr;(REPORTS/('export-'+name+'.log')).write_text(log,encoding='utf-8')
        if result.returncode or any(s in log for s in ['SCRIPT ERROR:','ERROR:','Parse Error:']): raise ValueError('Export failed: '+name)
    pck=audit_pck(output/'MAP001-25D.pck')
    for name,source in external.items():
        target=output/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
    for name in ['GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt']: shutil.copyfile(ROOT/'licenses'/name,output/name)
    for target,source in DOCS.items(): shutil.copyfile(ROOT/'docs'/source,output/target)
    commit=git('rev-parse','HEAD')
    write(output/'BUILD-INFO.json',{'schema':'ao_pc_enhanced25d_build_v1','source_commit':commit,'dirty':False,'performance_tested':False,'pck_resources':pck,
        'files':{p.relative_to(output).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file()}})
    write(REPORTS/'candidate.json',{'directory':str(output),'source_commit':commit,'stage':str(stage)})
    print(json.dumps({'directory':str(output),'commit':commit}))

def package(folder,archive,extracted):
    if archive.exists() or extracted.exists(): raise ValueError('Preserve earlier archives and extracted runs')
    info=read(folder/'BUILD-INFO.json');expected=set(info['files'])|{'BUILD-INFO.json'}
    actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual!=expected: raise ValueError('Delivery file closure differs')
    for name,row in info['files'].items():
        if sha(folder/name)!=row['sha256']: raise ValueError('Delivery file changed')
    audit_pck(folder/'MAP001-25D.pck')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(expected): z.write(folder/name,name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or set(z.namelist())!=expected: raise ValueError('ZIP closure or CRC failed')
        z.extractall(extracted)
    for name in expected:
        if sha(extracted/name)!=sha(folder/name): raise ValueError('Extracted file mismatch')
    result={'schema':'ao_pc_enhanced25d_package_audit_v1','passed':True,'archive':str(archive),'sha256':sha(archive),'files':len(expected),'source_commit':info['source_commit'],'extracted':str(extracted),'performance_tested':False}
    write(REPORTS/'package-audit.json',result);print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    e=s.add_parser('export');e.add_argument('--output',type=Path,required=True)
    e=s.add_parser('package');e.add_argument('--folder',type=Path,required=True);e.add_argument('--archive',type=Path,required=True);e.add_argument('--extracted',type=Path,required=True)
    a=p.parse_args()
    if a.command=='export': export(a.output)
    else: package(a.folder,a.archive,a.extracted)
