"""Exact local event resource closure, executable/source inventory and ZIP audit."""
import argparse
import datetime
import json
from pathlib import Path
import re
import stat
import zipfile
from audit_battle_package import unpack
from audit_exploration_package import remap_target
import audit_character_package as character
import audit_room_package as room_audit
import room_bundle as room
import event_bundle as event
import interaction_bundle as interaction
import equipment_bundle as equipment

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=room_audit.SCRIPTS|{'event_core','event_loader','event_visual','interaction_main','interaction_core','interaction_loader','interaction_dialogue','equipment_main','equipment_core','equipment_loader'}
BUNDLES={**room_audit.BUNDLES,'event':event.NAMES|{'package.json'},'interaction':interaction.NAMES|{'package.json'},'equipment':equipment.NAMES|{'package.json'}}
PINS=room_audit.PINS|{'event-pin.json','interaction-pin.json','equipment-pin.json'}
DOCUMENTS={'README.md','GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt','EQUIPMENT_SOURCE.md','EQUIPMENT_STAGE_Q2.md','EQUIPMENT_DELIVERY.md','EQUIPMENT_VALIDATION.json'}
FILES=DOCUMENTS|{'MAP001-Equipment.exe','MAP001-Equipment.pck'}


def audit_pck(raw):
    files=unpack(raw)
    main=remap_target(files.get('equipment_main.tscn.remap',b''))
    if not re.fullmatch(r'\.godot/exported/\d+/export-[0-9a-f]{32}-equipment_main\.scn',main):raise ValueError('Wrong event scene remap')
    allowed={'.godot/global_script_class_cache.cfg','.godot/uid_cache.bin','project.binary','equipment_main.tscn.remap',
             'room_priority.gdshader','character_priority.gdshader',main}|PINS|{f'{n}.{s}' for n in SCRIPTS for s in ('gdc','gd.remap')}
    if set(files)!=allowed:raise ValueError(f'Unapproved event PCK: extra={set(files)-allowed}, missing={allowed-set(files)}')
    for name in PINS:
        if files[name]!=(ROOT/'exploration-demo'/name).read_bytes():raise ValueError('Changed packaged pin')
    for name in SCRIPTS:
        if remap_target(files[name+'.gd.remap'])!=name+'.gdc' or not files[name+'.gdc'].startswith(b'GDSC'):raise ValueError('Invalid packaged script')
    settings=character.project_values(files['project.binary']);key='application/run/main_scene'
    if {n for n in settings if n==key or n.startswith(key+'.')}!={key}:raise ValueError('Ambiguous isolated event entry')
    if character.variant_string(settings.get(key,b''))!='res://equipment_main.tscn':raise ValueError('Incorrect event main scene')
    return [{'path':n,'bytes':len(v),'sha256':room.sha(v)} for n,v in sorted(files.items())]


def inventory(folder,include_build=True):
    room.no_redirect(folder)
    expected=FILES|set(BUNDLES)|({'BUILD-INFO.json'} if include_build else set())
    if (folder/'MAP001-Equipment.console.exe').exists():expected.add('MAP001-Equipment.console.exe')
    if {p.name for p in folder.iterdir()}!=expected:raise ValueError('Unapproved event delivery root')
    result={}
    for path in folder.iterdir():
        room.no_redirect(path)
        if path.name in BUNDLES:
            if {p.name for p in path.iterdir()}!=BUNDLES[path.name]:raise ValueError('Bundle file closure differs: '+path.name)
            for child in path.iterdir():
                room.no_redirect(child)
                if not child.is_file():raise ValueError('Non-file bundle payload')
                result[path.name+'/'+child.name]=child
        elif path.is_file():result[path.name]=path
        else:raise ValueError('Unapproved folder')
    return result


def audit(folder,require_build=True):
    files=inventory(folder,require_build)
    pck=audit_pck(files['MAP001-Equipment.pck'].read_bytes())
    trusted=room_audit.pins()
    values=character.validate_pins({n:trusted[n] for n in character.PINS})
    character.verify_external_bundles(folder,values)
    room.verify(folder/'room',event.DEPENDENCIES['room'],folder)
    event.verify(folder/'event')
    interaction.verify(folder/'interaction')
    equipment.verify(folder/'equipment')
    for name,path in files.items():
        if name.endswith('.exe') and not path.read_bytes().startswith(b'MZ'):raise ValueError('Invalid Windows executable')
    contents=[{'path':n,'bytes':p.stat().st_size,'sha256':room.sha(p.read_bytes())} for n,p in sorted(files.items()) if n!='BUILD-INFO.json']
    if require_build:
        info=json.loads(files['BUILD-INFO.json'].read_bytes())
        if info.get('schema')!='ao_pc_equipment_build_v1' or info.get('files')!=contents or not re.fullmatch('[0-9a-f]{40}',info.get('source_commit','')):raise ValueError('Build identity or content hashes differ')
    return {'schema':'ao_pc_equipment_delivery_audit_v1','passed':True,'files':contents,'pck_resources':pck}


def write_build(folder,commit,dirty):
    # Ignore only this tool's manifest during re-indexing; never remove payloads.
    old=folder/'BUILD-INFO.json'
    if old.exists():
        inventory(folder,True)
        saved=old.read_bytes();old.unlink()
        try:result=audit(folder,False)
        except Exception:old.write_bytes(saved);raise
    else:result=audit(folder,False)
    info={'schema':'ao_pc_equipment_build_v1','source_commit':commit,'source_has_uncommitted_changes':dirty,'godot':'4.7.2',
          'built_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':result['files'],
          'export_method':'Isolated export staging with explicit event main scene; all previous entry settings unchanged.'}
    old.write_bytes(room.encoded(info))
    return audit(folder)


def validate_candidate(validation,archive,candidate,dirty):
    if not candidate or archive.name!='MAP001-Equipment-Candidate-Windows-x64.zip':
        raise ValueError('Only explicitly named candidate delivery is authorized')
    if validation.get('passed') is not False or validation.get('functional_passed') is not True or validation.get('performance_tested') is not False or validation.get('status')!='performance_validation_deferred_by_user':
        raise ValueError('Candidate requires functional gates and deferred performance status')
    if dirty is not False:
        raise ValueError('Candidate requires clean binary source commit')


def package(folder,archive,extraction,candidate=False):
    result=audit(folder)
    validation=json.loads((folder/'EQUIPMENT_VALIDATION.json').read_bytes())
    validate_candidate(validation,archive,candidate,json.loads((folder/'BUILD-INFO.json').read_bytes())['source_has_uncommitted_changes'])
    if archive.exists() or extraction.exists():raise ValueError('Preserve previous ZIP/extraction')
    files=inventory(folder)
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in sorted(files.items()):z.write(path,name)
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())!=len(files) or set(z.namelist())!=set(files):raise ValueError('ZIP closure differs')
        for info in z.infolist():
            if stat.S_ISLNK(info.external_attr>>16) or z.read(info.filename)!=files[info.filename].read_bytes():raise ValueError('ZIP payload changed')
        extraction.mkdir(parents=True)
        for name in files:
            path=extraction/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
    if audit(extraction)!=result:raise ValueError('Extracted delivery differs')
    return {'schema':'ao_pc_equipment_zip_audit_v1','passed':True,'runtime_acceptance':not candidate,'release_status':'candidate_performance_pending' if candidate else 'accepted','path':str(archive.resolve()),'sha256':room.sha(archive.read_bytes()),
            'bytes':archive.stat().st_size,'files':len(files),'extraction':str(extraction.resolve())}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('audit','build-info','zip'));p.add_argument('folder',type=Path)
    p.add_argument('--commit');p.add_argument('--dirty',action='store_true');p.add_argument('--zip',type=Path);p.add_argument('--extract',type=Path);p.add_argument('--report',type=Path);p.add_argument('--candidate',action='store_true');a=p.parse_args()
    result=write_build(a.folder,a.commit,a.dirty) if a.action=='build-info' else package(a.folder,a.zip,a.extract,a.candidate) if a.action=='zip' else audit(a.folder)
    if a.report:a.report.write_bytes(room.encoded(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','pck_resources')}))
