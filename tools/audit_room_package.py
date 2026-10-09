"""Closed resource/ZIP inventory for the independent local room delivery."""
from __future__ import annotations
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
import room_bundle as room

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=character.SCRIPTS|{'room_main','room_loader','room_camera_core','room_movement_core','room_decoration_core'}
BUNDLES={**character.BUNDLES,'room':room.PAYLOADS|{'package.json'}}
PINS=character.PINS|{'room-pin.json'}
DOCUMENTS={'README.md','GODOT-LICENSE.txt','GODOT-COPYRIGHT.txt','room-coverage.png',
           'ROOM_STAGE_R1.md','ROOM_STAGE_R2.md','ROOM_STAGE_R3.md','ROOM_STAGE_R4.md','ROOM_VALIDATION.json'}
FILES=DOCUMENTS|{'MAP001-Room.exe','MAP001-Room.pck'}

def pins() -> dict:return {name:(ROOT/'exploration-demo'/name).read_bytes() for name in PINS}

def audit_pck(raw: bytes,trusted: dict) -> list:
    character.validate_pins({n:trusted[n] for n in character.PINS})
    pin=json.loads(trusted['room-pin.json'])
    if pin.get('schema')!='ao_pc_room_bundle_pin_v1' or pin.get('dependencies')!=room.PINS:raise ValueError('Invalid room pin')
    files=unpack(raw)
    main=remap_target(files.get('room_main.tscn.remap',b''))
    if not re.fullmatch(r'\.godot/exported/\d+/export-[0-9a-f]{32}-room_main\.scn',main):raise ValueError('Unexpected room scene remap')
    allowed={'.godot/global_script_class_cache.cfg','.godot/uid_cache.bin','project.binary','room_main.tscn.remap',
             'room_priority.gdshader','character_priority.gdshader',main}|PINS|{f'{n}.{suffix}' for n in SCRIPTS for suffix in ('gdc','gd.remap')}
    if set(files)!=allowed:raise ValueError(f'Unapproved PCK closure: extra={set(files)-allowed}, missing={allowed-set(files)}')
    for name in PINS:
        if files[name]!=trusted[name]:raise ValueError('PCK pin mismatch: '+name)
    for name in SCRIPTS:
        if remap_target(files[name+'.gd.remap'])!=name+'.gdc' or not files[name+'.gdc'].startswith(b'GDSC'):raise ValueError('Invalid script resource')
    settings=character.project_values(files['project.binary']);key='application/run/main_scene'
    if {n for n in settings if n==key or n.startswith(key+'.')}!={key,key+'.character_demo',key+'.room_demo'}:raise ValueError('Ambiguous entry settings')
    for k,wanted in {'_custom_features':'room_demo',key:'res://main.tscn',key+'.character_demo':'res://character_main.tscn',key+'.room_demo':'res://room_main.tscn'}.items():
        if character.variant_string(settings.get(k,b''))!=wanted:raise ValueError('Room export does not select its independent entry')
    return [{'path':n,'bytes':len(raw),'sha256':room.sha(raw)} for n,raw in sorted(files.items())]

def inventory(folder: Path,include_build=True) -> dict[str,Path]:
    room.no_redirect(folder)
    present={p.name for p in folder.iterdir()}
    allowed=FILES|set(BUNDLES)|({'BUILD-INFO.json'} if include_build else set())
    if 'MAP001-Room.console.exe' in present:allowed.add('MAP001-Room.console.exe')
    if present!=allowed:raise ValueError(f'Unapproved delivery contents: extra={present-allowed}, missing={allowed-present}')
    result={}
    for path in folder.iterdir():
        room.no_redirect(path)
        if path.name in BUNDLES:
            if {p.name for p in path.iterdir()}!=BUNDLES[path.name]:raise ValueError('External package inventory changed')
            for child in path.iterdir():
                room.no_redirect(child)
                if not child.is_file():raise ValueError('External package entry is not a file')
                result[path.name+'/'+child.name]=child
        elif path.is_file():result[path.name]=path
        else:raise ValueError('Invalid delivery object')
    return result

def audit(folder: Path,require_build=True) -> dict:
    trusted=pins();files=inventory(folder,require_build)
    pck=audit_pck(files['MAP001-Room.pck'].read_bytes(),trusted)
    values=character.validate_pins({n:trusted[n] for n in character.PINS})
    bundles=character.verify_external_bundles(folder,values)
    bundles['room']=room.verify(folder/'room',json.loads(trusted['room-pin.json'])['manifest_sha256'],folder)
    for name,path in files.items():
        if name.endswith('.exe') and not path.read_bytes().startswith(b'MZ'):raise ValueError('Invalid Windows executable')
    contents=[{'path':name,'bytes':path.stat().st_size,'sha256':room.sha(path.read_bytes())} for name,path in sorted(files.items()) if name!='BUILD-INFO.json']
    if require_build:
        info=json.loads(files['BUILD-INFO.json'].read_bytes())
        if info.get('schema')!='ao_pc_room_build_v1' or info.get('files')!=contents or not re.fullmatch('[0-9a-f]{40}',info.get('source_commit','')):raise ValueError('Build identity or hashes differ')
    return {'schema':'ao_pc_room_delivery_audit_v1','passed':True,'files':contents,'pck_resources':pck,'bundles':bundles}

def write_build(folder: Path,commit: str,dirty: bool) -> dict:
    # BUILD-INFO may be refreshed after adding the final evidence summary.
    if (folder/'BUILD-INFO.json').exists():
        old=(folder/'BUILD-INFO.json').read_bytes()
        (folder/'BUILD-INFO.json').unlink()
        try: result=audit(folder,False)
        except Exception:
            (folder/'BUILD-INFO.json').write_bytes(old);raise
    else:result=audit(folder,False)
    info={'schema':'ao_pc_room_build_v1','source_commit':commit,'source_has_uncommitted_changes':dirty,'godot':'4.7.2',
          'built_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':result['files']}
    (folder/'BUILD-INFO.json').write_bytes(room.encoded(info))
    return audit(folder)

def package(folder: Path,archive: Path,extraction: Path) -> dict:
    result=audit(folder)
    validation=json.loads((folder/'ROOM_VALIDATION.json').read_bytes())
    if validation.get('passed') is not True:raise ValueError('R5 acceptance has not passed')
    if archive.exists() or extraction.exists():raise ValueError('Preserve previous delivery/extraction')
    files=inventory(folder)
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in sorted(files.items()):z.write(path,name)
    # Exact pre-extraction inventory and byte hashes prohibit traversal/extra files.
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())!=len(files) or set(z.namelist())!=set(files):raise ValueError('ZIP file closure differs')
        for info in z.infolist():
            if stat.S_ISLNK(info.external_attr>>16) or z.read(info.filename)!=files[info.filename].read_bytes():raise ValueError('ZIP entry changed or redirected')
        extraction.mkdir(parents=True)
        for name in files:
            path=extraction/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
    extracted=audit(extraction)
    if extracted!=result:raise ValueError('Extracted inventory differs')
    return {'schema':'ao_pc_room_zip_audit_v1','passed':True,'path':str(archive.resolve()),'sha256':room.sha(archive.read_bytes()),
            'bytes':archive.stat().st_size,'files':len(files),'extraction':str(extraction.resolve())}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['audit','build-info','zip']);p.add_argument('folder',type=Path)
    p.add_argument('--commit');p.add_argument('--dirty',action='store_true');p.add_argument('--zip',type=Path);p.add_argument('--extract',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    result=write_build(a.folder,a.commit,a.dirty) if a.action=='build-info' else package(a.folder,a.zip,a.extract) if a.action=='zip' else audit(a.folder)
    if a.report:a.report.write_bytes(room.encoded(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','pck_resources','bundles')}))
