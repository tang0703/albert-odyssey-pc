"""Freeze/verify original bytes before the Unity migration; never rewrite parents.

The checked-in lock contains identities only. Source payloads and replay data stay
local. The initial lock is created once; subsequent prepare/verify always use it.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'exploration-demo/generated'
LOCK = ROOT / 'unity-remake/SourceContracts/source-baseline.json'
DEST = ROOT / 'unity-remake/Assets/StreamingAssets/SourceLocal'
BUNDLES = ('scene','character','character-hd','room','event','interaction',
           'equipment','transition','landing-event','enhanced25d','enhanced25d-landing')
RUNTIME = ('scene/flags.bin', 'character/profile.json',
           'character/animation-bank.bin', 'character/image-table.bin',
           'room/room.json', 'equipment/core.json')
CORE_FILES = ('movement_core.gd', 'character_animation_core.gd',
              'room_movement_core.gd', 'room_decoration_core.gd', 'equipment_core.gd')

def identity(path: Path) -> dict:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise ValueError(f'Not an ordinary file: {path}')
    raw = path.read_bytes()
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def write_json(path: Path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def collect():
    result = {}
    for bundle in BUNDLES:
        folder = SOURCE / bundle
        if folder.is_symlink() or folder.is_junction():
            raise ValueError('Redirected source bundle: '+bundle)
        if not (folder/'package.json').is_file():
            raise ValueError('Missing bundle: '+bundle)
        for p in sorted(folder.rglob('*')):
            if p.is_symlink() or p.is_junction():
                raise ValueError('Redirected bundle member')
            if p.is_file(): result[p.relative_to(SOURCE).as_posix()] = identity(p)
    return result

def validate_relative(name: str):
    parts = name.split('/')
    if not name or '\\' in name or ':' in name or any(p in ('','.','..') for p in parts):
        raise ValueError('Unsafe source path: '+name)

def validate_identity(actual: dict, expected: dict):
    if actual != expected:
        missing = sorted(expected.keys()-actual.keys())
        added = sorted(actual.keys()-expected.keys())
        changed = sorted(k for k in actual.keys() & expected.keys() if actual[k]!=expected[k])
        raise ValueError(f'Source bytes differ: missing={missing}, added={added}, changed={changed}')

def freeze():
    if LOCK.exists(): raise ValueError('Baseline already exists; refusing to replace it')
    # Invoke the established independent parent verifier before freezing identities.
    from equipment_bundle import verify as verify_equipment
    verify_equipment()
    files = collect()
    for name in RUNTIME:
        if name not in files: raise ValueError('Missing runtime source: '+name)
    cores = {name:identity(ROOT/'exploration-demo'/name) for name in CORE_FILES}
    write_json(LOCK, {'schema':'ao_unity_source_baseline_v1',
        'baseline_commit':'abd0f5d2d2afc3c55def08be0ec5746bd97a4956',
        'source_local_only':True,'bundles':list(BUNDLES),'files':files,
        'godot_cores':cores,'runtime_files':list(RUNTIME),
        'performance_validation':'deferred_by_user'})
    return verify()

def verify():
    lock=json.loads(LOCK.read_bytes())
    if lock['schema']!='ao_unity_source_baseline_v1' or lock['bundles']!=list(BUNDLES) or lock['runtime_files']!=list(RUNTIME):
        raise ValueError('Unknown Unity baseline schema or runtime list')
    for name in lock['files']: validate_relative(name)
    validate_identity(collect(),lock['files'])
    validate_identity({n:identity(ROOT/'exploration-demo'/n) for n in CORE_FILES},lock['godot_cores'])
    return {'passed':True,'bundles':len(BUNDLES),'files':len(lock['files']),
            'baseline_sha256':identity(LOCK)['sha256'],'performance_tested':False}

def inventory():
    verify()
    data=json.loads((SOURCE/'equipment/core.json').read_bytes())
    rows=[{'program':name,**row} for name,program in data['contract']['programs'].items() for row in program]
    special=[r for r in rows if r['action'] in ('actor_animation','player_pose','expression','cirrus_animation','spawn_story_spark','remove_story_spark','player_pickup_y')]
    references=[]
    for file in sorted((SOURCE/'equipment').glob('reference-*.json')):
        fixture=json.loads(file.read_bytes())
        references.append({'file':file.name,'updates':len(fixture['updates']),
                           'terminal_boundary':fixture['terminal'] is not None,**identity(file)})
    report={'schema':'ao_unity_u1_inventory_v1','special_actions':special,
            'extra_animations':data['extra_animations'],'interaction':data['interaction'],
            'reference_routes':references,'reference_updates':sum(r['updates'] for r in references),
            'rule':'No post-initial replay state may drive the runtime core.',
            'performance_tested':False}
    write_json(ROOT/'reports/unity/u1-source-inventory.json',report)
    return {'passed':True,'routes':len(references),'updates':report['reference_updates'],'special_actions':len(special)}

def prepare():
    verify()
    allowed=set(RUNTIME)|{'unity-source-manifest.json'}
    if DEST.exists():
        existing={p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file() and p.suffix!='.meta'}
        if existing-allowed: raise ValueError('Unapproved files in local Unity source directory')
    # Check destination containment/reparse points before copying any bytes.
    for parent in [DEST,*DEST.parents]:
        if parent.is_symlink() or parent.is_junction(): raise ValueError('Redirected Unity destination')
        if parent==ROOT: break
    lock=json.loads(LOCK.read_bytes())
    for name in RUNTIME:
        target=DEST/name
        for parent in [target.parent,*target.parents]:
            if parent.is_symlink() or parent.is_junction(): raise ValueError('Redirected Unity destination')
            if parent==DEST: break
        if target.is_symlink() or target.is_junction(): raise ValueError('Redirected Unity destination file')
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(SOURCE/name,target)
        if identity(target)!=lock['files'][name]: raise ValueError('Copied source bytes differ')
    write_json(DEST/'unity-source-manifest.json', {'schema':'ao_unity_runtime_sources_v1',
        'baseline_sha256':identity(LOCK)['sha256'],
        'files':{n:lock['files'][n] for n in RUNTIME},'source_local_only':True})
    approved={n:lock['files'][n] for n in RUNTIME}
    approved['unity-source-manifest.json']=identity(DEST/'unity-source-manifest.json')
    lines=['// Generated from the sealed U1 source baseline; contains identities only.',
           'namespace Ao.SourceContracts { public static class SourcePins {',
           'public static readonly SourceIdentity[] Files = new SourceIdentity[] {']
    for name,item in approved.items():
        lines.append(f'new SourceIdentity("{name}", {item["bytes"]}L, "{item["sha256"]}"),')
    lines.extend(['};','} }',''])
    (ROOT/'unity-remake/Assets/Scripts/Core/SourcePins.cs').write_text('\n'.join(lines),encoding='utf-8')
    return {'passed':True,'runtime_files':len(RUNTIME),'golden_replays_in_runtime':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('freeze','verify','inventory','prepare'))
    action=parser.parse_args().action
    print(json.dumps(globals()[action](),ensure_ascii=False))
