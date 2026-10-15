"""Stage an isolated event export; leave existing project entry settings intact."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import audit_event_package as audit

ROOT=Path(__file__).resolve().parents[1]


def export(output):
    output=output.resolve();build=(ROOT/'build').resolve()
    audit.room.no_redirect(build)
    if output.parent!=build or output.exists():raise ValueError('Use a new direct child of build')
    stage=build/('event-export-'+uuid.uuid4().hex)
    stage.mkdir();output.mkdir()
    source=ROOT/'exploration-demo'
    for name in audit.SCRIPTS:
        shutil.copyfile(source/(name+'.gd'),stage/(name+'.gd'))
        uid=source/(name+'.gd.uid')
        if uid.exists():shutil.copyfile(uid,stage/uid.name)
    for name in audit.PINS|{'event_main.tscn','character_priority.gdshader','room_priority.gdshader'}:
        shutil.copyfile(source/name,stage/name)
    settings=(source/'project.godot').read_text(encoding='utf-8')
    settings='\n'.join(line for line in settings.splitlines() if not line.startswith('run/main_scene.'))+'\n'
    settings=settings.replace('run/main_scene="res://main.tscn"','run/main_scene="res://event_main.tscn"')
    settings=settings.replace('config/name="MAP001 行走驗證台"','config/name="MAP001 Cirrus 事件"')
    (stage/'project.godot').write_text(settings,encoding='utf-8')
    templates=(ROOT.parent/'tools/pc-remake/export-templates-4.7.2/templates').as_posix()
    preset='''[preset.0]
name="Windows Event Workbench"
platform="Windows Desktop"
runnable=true
export_filter="selected_scenes"
export_files=PackedStringArray("res://event_main.tscn")
include_filter="bundle-pin.json,character-pin.json,character-hd-pin.json,room-pin.json,event-pin.json"
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
'''.replace('TEMPLATES',templates)
    (stage/'export_presets.cfg').write_text(preset)
    godot=ROOT.parent/'tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
    environment=os.environ.copy()
    for name,leaf in (('APPDATA','appdata'),('TEMP','temp'),('TMP','temp')):
        folder=stage/leaf;folder.mkdir(exist_ok=True);environment[name]=str(folder)
    for name,args in [('import',['--editor','--import','--quit']),('export',['--export-release','Windows Event Workbench',str(output/'MAP001-Event.exe')])]:
        log=ROOT/'reports/event'/('export-'+name+'.log')
        result=subprocess.run([str(godot),'--headless','--log-file',str(log),'--path',str(stage),*args],capture_output=True,text=True,encoding='utf-8',env=environment)
        (ROOT/'reports/event'/('export-'+name+'-output.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        print('Godot '+name+': exit '+str(result.returncode))
        if result.returncode or any(word in result.stdout+result.stderr for word in ('SCRIPT ERROR:','ERROR:','Parse Error:')):
            raise ValueError(result.stderr+' Event export failed')
    for bundle,names in audit.BUNDLES.items():
        (output/bundle).mkdir()
        for name in names:shutil.copyfile(source/'generated'/bundle/name,output/bundle/name)
    for name in ('GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt'):shutil.copyfile(ROOT/'licenses'/name,output/name)
    for name in ('EVENT_SOURCE_PROGRESS.md','EVENT_STAGE_D2.md','EVENT_DELIVERY.md'):shutil.copyfile(ROOT/'docs'/name,output/name)
    shutil.copyfile(ROOT/'docs/EVENT_README.md',output/'README.md')
    (output/'EVENT_VALIDATION.json').write_text(json.dumps({'schema':'ao_pc_event_acceptance_v1','passed':False,'status':'candidate_pending_D4'})+'\n')
    command=['git','-c','safe.directory='+ROOT.as_posix()]
    commit=subprocess.check_output(command+['rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(command+['status','--porcelain'],cwd=ROOT))
    audit.write_build(output,commit,dirty)
    result={'directory':str(output),'source_commit':commit,'dirty':dirty,'staging':str(stage)}
    (ROOT/'reports/event/candidate.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();export(a.output)
