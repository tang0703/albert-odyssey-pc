"""Audit the exact local-only Windows/PCK/scene delivery and its ZIP round trip.

The trusted pin is supplied from the build project, never from the external
scene manifest. Original-source verification belongs to exploration_bundle.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import zipfile

from audit_battle_package import resource_path, unpack
import exploration_bundle as bundle
from exploration_capture import stable_read

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {'main', 'movement_core', 'package_loader'}
PCK_FILES = {'.godot/global_script_class_cache.cfg', '.godot/uid_cache.bin',
             'project.binary', 'main.tscn.remap', 'bundle-pin.json'} | {
                 f'{script}.{suffix}' for script in SCRIPTS for suffix in ('gdc', 'gd.remap')}
ROOT_FILES = {'MAP001-Walk.exe', 'MAP001-Walk.pck', 'README.md', 'GODOT-LICENSE.txt',
              'GODOT-COPYRIGHT.txt', 'EXPLORATION_MOVEMENT.md', 'EXPLORATION_ACCEPTANCE.md'}
CONSOLE = 'MAP001-Walk.console.exe'
BUILD_INFO = 'BUILD-INFO.json'
BUILD_SCHEMA = 'ao_pc_exploration_build_v1'


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin_value(raw: bytes) -> dict:
    value = bundle.decoded(raw)
    if (not isinstance(value, dict) or set(value) != {'schema', 'manifest_sha256'}
            or value['schema'] != bundle.PIN_SCHEMA or not bundle.valid_hash(value['manifest_sha256'])):
        raise ValueError('Invalid trusted bundle pin')
    return value


def remap_target(raw: bytes) -> str:
    text = raw.rstrip(b'\0').decode('utf-8')
    match = re.fullmatch(r'\s*\[remap\]\s+path="(res://[^"\r\n]+)"\s*', text)
    if not match:
        raise ValueError('Invalid resource remap')
    return resource_path(match[1])


def audit_pck(raw: bytes, trusted_pin: bytes) -> list[dict]:
    pin_value(trusted_pin)
    files = unpack(raw)  # Validates fixed 4.7.2 layout, spans, duplicate names and every MD5.
    scene = remap_target(files.get('main.tscn.remap', b''))
    if not re.fullmatch(r'\.godot/exported/\d+/export-[0-9a-f]{32}-main\.scn', scene):
        raise ValueError('Unexpected main scene remap target')
    allowed = PCK_FILES | {scene}
    if set(files) != allowed:
        raise ValueError(f'PCK resource mismatch: extra={sorted(set(files)-allowed)}, missing={sorted(allowed-set(files))}')
    if files['bundle-pin.json'] != trusted_pin:
        raise ValueError('PCK bundle pin differs from trusted build pin')
    for name in SCRIPTS:
        if remap_target(files[f'{name}.gd.remap']) != f'{name}.gdc':
            raise ValueError(f'Script remap differs: {name}')
        if len(files[f'{name}.gdc']) < 12 or not files[f'{name}.gdc'].startswith(b'GDSC'):
            raise ValueError(f'Invalid compiled script: {name}')
    if not files['project.binary'].startswith(b'ECFG') or not files[scene]:
        raise ValueError('Invalid project or main scene resource')
    return [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name,raw in sorted(files.items())]


def delivery_files(folder: Path, require_build: bool = True) -> dict[str, Path]:
    folder = Path(folder)
    bundle.no_redirect(folder)
    expected = ROOT_FILES | {'scene'} | ({BUILD_INFO} if require_build else set())
    actual = {path.name for path in folder.iterdir()}
    if CONSOLE in actual:
        expected.add(CONSOLE)
    if not require_build and BUILD_INFO in actual:
        expected.add(BUILD_INFO)
    if actual != expected:
        raise ValueError(f'Delivery file mismatch: extra={sorted(actual-expected)}, missing={sorted(expected-actual)}')
    found = {}
    for path in folder.iterdir():
        bundle.no_redirect(path)
        if path.name == 'scene':
            bundle.exact_files(path)
            for child in path.iterdir():
                found['scene/' + child.name] = child
        elif path.is_file() and path.resolve().parent == folder.resolve():
            found[path.name] = path
        else:
            raise ValueError('Delivery entry must be a direct regular file')
    return found


def inventory(files: dict[str, Path], exclude_build: bool = False) -> list[dict]:
    result = []
    for name, path in sorted(files.items()):
        if exclude_build and name == BUILD_INFO:
            continue
        raw = stable_read(path)
        if not raw:
            raise ValueError(f'Empty delivery file: {name}')
        result.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
    return result


def content_audit(folder: Path, trusted_pin: bytes, require_build: bool = True) -> dict:
    pin = pin_value(trusted_pin)
    files = delivery_files(folder, require_build)
    pck_files = audit_pck(stable_read(files['MAP001-Walk.pck']), trusted_pin)
    scene = bundle.verify(folder / 'scene', pin['manifest_sha256'])
    for name in ('MAP001-Walk.exe', CONSOLE):
        if name in files and not stable_read(files[name]).startswith(b'MZ'):
            raise ValueError(f'Not a Windows executable: {name}')
    return {'files': inventory(files, exclude_build=True), 'pck_resources': pck_files, 'bundle': scene}


def write_build_info(folder: Path, trusted_pin: bytes, source_commit: str, dirty: bool) -> dict:
    if not re.fullmatch('[0-9a-f]{40}', source_commit) or type(dirty) is not bool:
        raise ValueError('Invalid source revision or dirty state')
    checked = content_audit(folder, trusted_pin, require_build=False)
    info = {'schema': BUILD_SCHEMA, 'source_commit': source_commit,
            'source_has_uncommitted_changes': dirty, 'godot': '4.7.2',
            'built_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'bundle_manifest_sha256': pin_value(trusted_pin)['manifest_sha256'],
            'files': checked['files']}
    (folder / BUILD_INFO).write_bytes(bundle.encoded(info))
    return audit_delivery(folder, trusted_pin)


def audit_delivery(folder: Path, trusted_pin: bytes) -> dict:
    folder = Path(folder)
    checked = content_audit(folder, trusted_pin)
    info = bundle.decoded(stable_read(folder / BUILD_INFO))
    if (not isinstance(info, dict) or set(info) != {'schema', 'source_commit',
            'source_has_uncommitted_changes', 'godot', 'built_utc', 'bundle_manifest_sha256', 'files'}
            or info['schema'] != BUILD_SCHEMA or not isinstance(info['source_commit'], str)
            or not re.fullmatch('[0-9a-f]{40}', info['source_commit'])
            or type(info['source_has_uncommitted_changes']) is not bool or info['godot'] != '4.7.2'
            or info['bundle_manifest_sha256'] != pin_value(trusted_pin)['manifest_sha256']):
        raise ValueError('Invalid build identity record')
    try:
        stamp = datetime.datetime.fromisoformat(info['built_utc'])
        if stamp.tzinfo is None:
            raise ValueError('Build timestamp has no time zone')
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid build timestamp') from exc
    if info['files'] != checked['files']:
        raise ValueError('Build inventory differs from actual delivery bytes')
    files = inventory(delivery_files(folder))
    return {'schema': 'ao_pc_exploration_package_audit_v1', 'passed': True,
            'source_commit': info['source_commit'], 'source_has_uncommitted_changes': info['source_has_uncommitted_changes'],
            'bundle_manifest_sha256': info['bundle_manifest_sha256'], 'files': files,
            'pck_resources': checked['pck_resources'], 'bundle': checked['bundle'],
            'original_scene_images_included': True, 'disc_bios_ram_savestates_included': False,
            'distribution_scope': 'local_only', 'cold_start_tested': False}


def verify_zip(archive: Path, delivery: Path, extracted: Path, trusted_pin: bytes) -> dict:
    """Verify before extraction; every permitted filename is a fixed audited file.

    The extraction directory must be new. No archive-controlled path is passed
    to extractall(), and a failed verification never removes an existing path.
    """
    expected = audit_delivery(delivery, trusted_pin)
    expected_files = {item['path']: item for item in expected['files']}
    bundle.no_redirect(archive)
    if extracted.exists() or extracted.is_symlink():
        raise ValueError('ZIP extraction directory must not exist')
    raw_payloads = {}
    archive_raw = stable_read(archive)
    with zipfile.ZipFile(io.BytesIO(archive_raw), 'r') as zipped:
        seen = set()
        for item in zipped.infolist():
            name = item.filename
            mode = item.external_attr >> 16
            if name.endswith('/'):
                if name != 'scene/' or name in seen or item.file_size != 0 or stat.S_ISLNK(mode):
                    raise ValueError('Unexpected ZIP directory')
                seen.add(name)
                continue
            resource_path(name)
            if name.casefold() in {key.casefold() for key in raw_payloads} or name not in expected_files:
                raise ValueError('Unexpected or duplicate ZIP entry')
            if stat.S_ISLNK(mode) or (mode & 0o170000) not in (0, stat.S_IFREG):
                raise ValueError('ZIP entry is not a regular file')
            if item.flag_bits & 1 or item.file_size != expected_files[name]['bytes']:
                raise ValueError('ZIP encryption or size differs from delivery')
            raw = zipped.read(item)  # CRC is checked by zipfile; SHA256 is checked below.
            if sha(raw) != expected_files[name]['sha256']:
                raise ValueError(f'ZIP content hash differs: {name}')
            raw_payloads[name] = raw
    if set(raw_payloads) != set(expected_files):
        raise ValueError('ZIP file list differs from audited delivery')
    extracted.mkdir(parents=False, exist_ok=False)
    (extracted / 'scene').mkdir()
    for name, raw in raw_payloads.items():
        (extracted / name).write_bytes(raw)
    actual = audit_delivery(extracted, trusted_pin)
    if actual['files'] != expected['files']:
        raise ValueError('Extracted ZIP files differ from delivery')
    if stable_read(archive) != archive_raw:
        raise ValueError('ZIP changed during verification')
    return {'schema': 'ao_pc_exploration_zip_audit_v1', 'passed': True,
            'zip_sha256': sha(archive_raw), 'zip_bytes': len(archive_raw),
            'extraction_verified': True, 'extraction_path': str(extracted.resolve()),
            'source_commit': expected['source_commit'],
            'source_has_uncommitted_changes': expected['source_has_uncommitted_changes'],
            'bundle_manifest_sha256': expected['bundle_manifest_sha256'], 'files': actual['files'],
            'distribution_scope': 'local_only', 'cold_start_tested': False}


def create_zip(delivery: Path, archive: Path, extracted: Path, trusted_pin: bytes) -> dict:
    audit_delivery(delivery, trusted_pin)
    if archive.exists():
        bundle.no_redirect(archive)
        if not archive.is_file():
            raise ValueError('ZIP output must be a regular file')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for name, path in sorted(delivery_files(delivery).items()):
            zipped.writestr(name, stable_read(path))
    return verify_zip(archive, delivery, extracted, trusted_pin)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build-info', 'audit', 'zip', 'verify-zip'])
    parser.add_argument('--delivery', type=Path, default=ROOT / 'build/exploration-demo')
    parser.add_argument('--pin', type=Path, default=ROOT / 'exploration-demo/bundle-pin.json')
    parser.add_argument('--source-commit')
    parser.add_argument('--dirty', choices=['true', 'false'])
    parser.add_argument('--zip', type=Path, dest='archive', default=ROOT / 'build/MAP001-Walk-Windows-x64.zip')
    parser.add_argument('--extract-to', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        trusted_pin = stable_read(args.pin)
        if args.action == 'build-info':
            if args.source_commit is None or args.dirty is None:
                raise ValueError('Build-info requires explicit source commit and dirty state')
            result = write_build_info(args.delivery, trusted_pin, args.source_commit, args.dirty == 'true')
        elif args.action == 'audit':
            result = audit_delivery(args.delivery, trusted_pin)
        else:
            if args.extract_to is None:
                raise ValueError('ZIP verification requires a new extraction path')
            if args.action == 'zip':
                result = create_zip(args.delivery, args.archive, args.extract_to, trusted_pin)
            else:
                result = verify_zip(args.archive, args.delivery, args.extract_to, trusted_pin)
        if args.report:
            args.report.write_bytes(bundle.encoded(result))
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Exploration package rejected: {exc}\n')
    print(json.dumps({key: value for key,value in result.items() if key not in {'files','pck_resources','bundle'}}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
