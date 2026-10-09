"""Strict local-only character delivery closure. Does not grant A6 QA approval."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import struct
import zipfile

from audit_battle_package import unpack, resource_path
from audit_exploration_package import remap_target
import exploration_bundle as scene
import character_bundle as character
from exploration_capture import stable_read

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {'main', 'movement_core', 'package_loader', 'character_main',
           'character_animation_core', 'character_loader', 'character_layer',
           'character_hd_animation', 'character_hd_loader'}
PINS = {'bundle-pin.json', 'character-pin.json', 'character-hd-pin.json'}
PCK_FILES = {'.godot/global_script_class_cache.cfg', '.godot/uid_cache.bin',
             'project.binary', 'character_main.tscn.remap', 'character_priority.gdshader'} | PINS | {
                 f'{script}.{suffix}' for script in SCRIPTS for suffix in ('gdc', 'gd.remap')}
HD_FILES = {'package.json', 'appearances.json'} | {
    f'{direction}-{action}.png' for direction in ('down', 'left', 'right', 'up')
    for action in ('idle', *(f'walk-{n:02d}' for n in range(12)), 'atlas')}
BUNDLES = {'scene': scene.FILES, 'character': character.FILES, 'character-hd': HD_FILES}
ROOT_FILES = {'MAP001-Character.exe', 'MAP001-Character.pck', 'README.md',
              'GODOT-LICENSE.txt', 'GODOT-COPYRIGHT.txt', 'CHARACTER_DELIVERY.md',
              'CHARACTER_STAGE_A2.md', 'CHARACTER_ANIMATION_MODEL.md'}
CONSOLE = 'MAP001-Character.console.exe'
BUILD_INFO = 'BUILD-INFO.json'
BUILD_SCHEMA = 'ao_pc_character_build_v1'


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_pins(pins: dict[str, bytes]) -> dict:
    if set(pins) != PINS:
        raise ValueError('Exactly three independent trusted pins are required')
    values = {name: scene.decoded(raw) for name, raw in pins.items()}
    schemas = {'bundle-pin.json': ('ao_pc_exploration_bundle_pin_v1', {'manifest_sha256'}),
               'character-pin.json': ('ao_pc_character_bundle_pin_v1', {'manifest_sha256', 'scene_manifest_sha256'}),
               'character-hd-pin.json': ('ao_pc_character_hd_bundle_pin_v1',
                                        {'manifest_sha256', 'scene_manifest_sha256', 'source_character_manifest_sha256'})}
    for name, (schema, hashes) in schemas.items():
        value = values[name]
        if (not isinstance(value, dict) or set(value) != hashes | {'schema'} or value['schema'] != schema
                or any(not scene.valid_hash(value[key]) for key in hashes)):
            raise ValueError('Invalid trusted pin: ' + name)
    base, source, hd = (values[name] for name in ('bundle-pin.json', 'character-pin.json', 'character-hd-pin.json'))
    if (base['manifest_sha256'] != source['scene_manifest_sha256']
            or base['manifest_sha256'] != hd['scene_manifest_sha256']
            or source['manifest_sha256'] != hd['source_character_manifest_sha256']):
        raise ValueError('Cross-package pin identities disagree')
    return values


def project_values(raw: bytes) -> dict[str, bytes]:
    """Read bounded Godot ECFG entries, without interpreting arbitrary Variants."""
    if len(raw) < 8 or raw[:4] != b'ECFG':
        raise ValueError('Invalid project.binary')
    count, = struct.unpack_from('<I', raw, 4)
    if not 1 <= count <= 512:
        raise ValueError('Invalid project setting count')
    pos, result = 8, {}
    for _ in range(count):
        if pos + 4 > len(raw): raise ValueError('Truncated project setting')
        length, = struct.unpack_from('<I', raw, pos); pos += 4
        if not 1 <= length <= 512 or pos + length + 4 > len(raw):
            raise ValueError('Invalid project setting name')
        name = raw[pos:pos + length].decode('utf-8'); pos += length
        size, = struct.unpack_from('<I', raw, pos); pos += 4
        if name in result or size < 4 or pos + size > len(raw):
            raise ValueError('Duplicate or truncated project value')
        result[name] = raw[pos:pos + size]; pos += size
    if pos != len(raw): raise ValueError('Trailing project bytes')
    return result


def variant_string(raw: bytes) -> str:
    if len(raw) < 8 or struct.unpack_from('<I', raw, 0)[0] != 4:
        raise ValueError('Project entry is not a string Variant')
    length, = struct.unpack_from('<I', raw, 4)
    if len(raw) != 8 + ((length + 3) & ~3) or any(raw[8 + length:]):
        raise ValueError('Invalid project string length/padding')
    return raw[8:8 + length].decode('utf-8')


def audit_pck(raw: bytes, pins: dict[str, bytes]) -> list[dict]:
    validate_pins(pins)
    files = unpack(raw)
    main = remap_target(files.get('character_main.tscn.remap', b''))
    if not re.fullmatch(r'\.godot/exported/\d+/export-[0-9a-f]{32}-character_main\.scn', main):
        raise ValueError('Unexpected character entry scene remap')
    allowed = PCK_FILES | {main}
    if set(files) != allowed:
        raise ValueError(f'PCK resource mismatch: extra={sorted(set(files)-allowed)}, missing={sorted(allowed-set(files))}')
    for name, expected in pins.items():
        if files[name] != expected: raise ValueError('PCK trusted pin differs: ' + name)
    for name in SCRIPTS:
        if remap_target(files[name + '.gd.remap']) != name + '.gdc':
            raise ValueError('Script remap differs: ' + name)
        if len(files[name + '.gdc']) < 12 or not files[name + '.gdc'].startswith(b'GDSC'):
            raise ValueError('Invalid compiled script: ' + name)
    settings = project_values(files['project.binary'])
    # Export must resolve the character_demo override into the actual entry.
    # Merely including a character scene beside the old main is insufficient.
    if variant_string(settings.get('application/run/main_scene', b'')) != 'res://character_main.tscn':
        raise ValueError('Exported project does not launch the character entry')
    if not files[main] or b'shader_type canvas_item;' not in files['character_priority.gdshader']:
        raise ValueError('Missing compiled scene or priority shader')
    return [{'path': name, 'bytes': len(value), 'sha256': sha(value)} for name, value in sorted(files.items())]


def delivery_files(folder: Path, require_build: bool = True) -> dict[str, Path]:
    scene.no_redirect(folder)
    actual = {path.name for path in folder.iterdir()}
    allowed = ROOT_FILES | set(BUNDLES) | ({BUILD_INFO} if require_build else set())
    if CONSOLE in actual: allowed.add(CONSOLE)
    if not require_build and BUILD_INFO in actual: allowed.add(BUILD_INFO)
    if actual != allowed:
        raise ValueError(f'Delivery file mismatch: extra={sorted(actual-allowed)}, missing={sorted(allowed-actual)}')
    result = {}
    for path in folder.iterdir():
        scene.no_redirect(path)
        if path.name in BUNDLES:
            if not path.is_dir() or {p.name for p in path.iterdir()} != set(BUNDLES[path.name]):
                raise ValueError('External bundle exact file closure differs: ' + path.name)
            for child in path.iterdir():
                scene.no_redirect(child)
                if not child.is_file() or child.resolve().parent != path.resolve():
                    raise ValueError('Bundle entry is not a direct regular file')
                result[path.name + '/' + child.name] = child
        elif path.is_file() and path.resolve().parent == folder.resolve(): result[path.name] = path
        else: raise ValueError('Delivery entry is not a direct regular file')
    return result


def inventory(files: dict[str, Path], exclude_build: bool = False) -> list[dict]:
    result = []
    for name, path in sorted(files.items()):
        if exclude_build and name == BUILD_INFO: continue
        raw = stable_read(path)
        if not raw: raise ValueError('Empty delivery file: ' + name)
        result.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
    return result


def verify_external_bundles(folder: Path, values: dict) -> dict:
    # Import lazily: structural tests never create or approve placeholder HD.
    import character_hd_bundle as hd
    base = values['bundle-pin.json']['manifest_sha256']
    source = values['character-pin.json']['manifest_sha256']
    return {'scene': scene.verify(folder / 'scene', base),
            'character': character.verify(folder / 'character', source, scene_bundle=folder / 'scene', expected_scene_sha=base),
            'character-hd': hd.verify(folder / 'character-hd', values['character-hd-pin.json']['manifest_sha256'],
                scene_bundle=folder / 'scene', expected_scene_sha=base,
                source_character_bundle=folder / 'character', expected_source_character_sha=source)}


def content_audit(folder: Path, pins: dict[str, bytes], require_build: bool = True) -> dict:
    values = validate_pins(pins)
    files = delivery_files(folder, require_build)
    pck = audit_pck(stable_read(files['MAP001-Character.pck']), pins)
    bundles = verify_external_bundles(folder, values)
    for name in ('MAP001-Character.exe', CONSOLE):
        if name in files and not stable_read(files[name]).startswith(b'MZ'):
            raise ValueError('Not a Windows executable: ' + name)
    return {'files': inventory(files, True), 'pck_resources': pck, 'bundles': bundles}


def write_build_info(folder: Path, pins: dict[str, bytes], source_commit: str, dirty: bool) -> dict:
    if not re.fullmatch('[0-9a-f]{40}', source_commit) or type(dirty) is not bool:
        raise ValueError('Invalid source commit/dirty state')
    checked = content_audit(folder, pins, False)
    info = {'schema': BUILD_SCHEMA, 'source_commit': source_commit,
            'source_has_uncommitted_changes': dirty, 'godot': '4.7.2',
            'built_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'pin_sha256': {name: sha(raw) for name, raw in sorted(pins.items())}, 'files': checked['files']}
    (folder / BUILD_INFO).write_bytes(scene.encoded(info))
    return audit_delivery(folder, pins)


def audit_delivery(folder: Path, pins: dict[str, bytes]) -> dict:
    checked = content_audit(folder, pins)
    info = scene.decoded(stable_read(folder / BUILD_INFO))
    if (not isinstance(info, dict) or set(info) != {'schema', 'source_commit', 'source_has_uncommitted_changes', 'godot', 'built_utc', 'pin_sha256', 'files'}
            or info['schema'] != BUILD_SCHEMA or not isinstance(info['source_commit'], str)
            or not re.fullmatch('[0-9a-f]{40}', info['source_commit']) or type(info['source_has_uncommitted_changes']) is not bool
            or info['godot'] != '4.7.2' or info['pin_sha256'] != {name: sha(raw) for name, raw in sorted(pins.items())}):
        raise ValueError('Invalid build identity')
    try:
        if datetime.datetime.fromisoformat(info['built_utc']).tzinfo is None: raise ValueError('No timezone')
    except (ValueError, TypeError) as exc: raise ValueError('Invalid build timestamp') from exc
    if info['files'] != checked['files']: raise ValueError('Build inventory differs from delivery bytes')
    return {'schema': 'ao_pc_character_package_audit_v1', 'passed': True,
            'source_commit': info['source_commit'], 'source_has_uncommitted_changes': info['source_has_uncommitted_changes'],
            'pin_sha256': info['pin_sha256'], 'bundle_manifest_sha256': {name: sha(stable_read(folder / name / 'package.json')) for name in BUNDLES},
            'files': inventory(delivery_files(folder)), 'pck_resources': checked['pck_resources'], 'bundles': checked['bundles'],
            'distribution_scope': 'local_only', 'original_images_included': True,
            'disc_bios_ram_savestates_included': False, 'cold_start_tested': False, 'a6_performance_passed': False}


def verify_zip(archive: Path, delivery: Path, extracted: Path, pins: dict[str, bytes]) -> dict:
    expected = audit_delivery(delivery, pins)
    fixed = {r['path']: r for r in expected['files']}
    scene.no_redirect(archive)
    if extracted.exists() or extracted.is_symlink(): raise ValueError('ZIP extraction directory must not exist')
    payloads, dirs = {}, set()
    archive_raw = stable_read(archive)
    with zipfile.ZipFile(io.BytesIO(archive_raw), 'r') as zipped:
        for item in zipped.infolist():
            name, mode = item.filename, item.external_attr >> 16
            if name.endswith('/'):
                if name not in {key + '/' for key in BUNDLES} or name in dirs or item.file_size or stat.S_ISLNK(mode):
                    raise ValueError('Unexpected ZIP directory')
                dirs.add(name); continue
            resource_path(name)
            if name.casefold() in {v.casefold() for v in payloads} or name not in fixed:
                raise ValueError('Unexpected or duplicate ZIP entry')
            if stat.S_ISLNK(mode) or (mode & 0o170000) not in (0, stat.S_IFREG): raise ValueError('ZIP entry is not regular')
            if item.flag_bits & 1 or item.file_size != fixed[name]['bytes']: raise ValueError('ZIP encryption or size differs')
            raw = zipped.read(item)
            if sha(raw) != fixed[name]['sha256']: raise ValueError('ZIP hash differs: ' + name)
            payloads[name] = raw
    if set(payloads) != set(fixed): raise ValueError('ZIP closure differs')
    extracted.mkdir(parents=False, exist_ok=False)
    for name in BUNDLES: (extracted / name).mkdir()
    for name, raw in payloads.items(): (extracted / name).write_bytes(raw)
    actual = audit_delivery(extracted, pins)
    if actual['files'] != expected['files'] or stable_read(archive) != archive_raw:
        raise ValueError('ZIP changed or extracted bytes differ')
    return {'schema': 'ao_pc_character_zip_audit_v1', 'passed': True, 'zip_sha256': sha(archive_raw),
            'zip_bytes': len(archive_raw), 'extraction_verified': True, 'extraction_path': str(extracted.resolve()),
            'source_commit': expected['source_commit'], 'files': actual['files'], 'distribution_scope': 'local_only',
            'cold_start_tested': False, 'a6_performance_passed': False}


def create_zip(delivery: Path, archive: Path, extracted: Path, pins: dict[str, bytes]) -> dict:
    audit_delivery(delivery, pins)
    if archive.exists() or archive.is_symlink(): raise ValueError('Use a new ZIP path; previous deliveries must be preserved')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for name, path in sorted(delivery_files(delivery).items()): zipped.writestr(name, stable_read(path))
    return verify_zip(archive, delivery, extracted, pins)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build-info', 'audit', 'zip', 'verify-zip'])
    parser.add_argument('--delivery', type=Path, default=ROOT / 'build/character-demo')
    parser.add_argument('--scene-pin', type=Path, default=ROOT / 'exploration-demo/bundle-pin.json')
    parser.add_argument('--character-pin', type=Path, default=ROOT / 'exploration-demo/character-pin.json')
    parser.add_argument('--hd-pin', type=Path, default=ROOT / 'exploration-demo/character-hd-pin.json')
    parser.add_argument('--source-commit'); parser.add_argument('--dirty', choices=['true', 'false'])
    parser.add_argument('--zip', type=Path, dest='archive', default=ROOT / 'build/MAP001-Character-Windows-x64.zip')
    parser.add_argument('--extract-to', type=Path); parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        pins = {'bundle-pin.json': stable_read(args.scene_pin), 'character-pin.json': stable_read(args.character_pin),
                'character-hd-pin.json': stable_read(args.hd_pin)}
        if args.action == 'build-info':
            if args.source_commit is None or args.dirty is None: raise ValueError('Explicit source revision is required')
            result = write_build_info(args.delivery, pins, args.source_commit, args.dirty == 'true')
        elif args.action == 'audit': result = audit_delivery(args.delivery, pins)
        else:
            if args.extract_to is None: raise ValueError('New extraction path required')
            function = create_zip if args.action == 'zip' else verify_zip
            result = function(args.delivery, args.archive, args.extract_to, pins) if args.action == 'zip' else function(args.archive, args.delivery, args.extract_to, pins)
        if args.report: args.report.write_bytes(scene.encoded(result))
    except (OSError, ValueError, KeyError, TypeError, ImportError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Character package rejected: {exc}\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'files', 'pck_resources', 'bundles'}}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
