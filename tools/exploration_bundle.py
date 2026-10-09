"""Build and verify the local-only, source-pinned MAP001 exploration bundle."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat

from PIL import Image

from exploration_capture import read_json_bytes, stable_read
import exploration_movement as movement
import exploration_reference as reference
from validate_player_trace import validate as validate_trace

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'exploration-demo/generated/scene'
DEFAULT_PIN = ROOT / 'exploration-demo/bundle-pin.json'
SCHEMA = 'ao_pc_exploration_bundle_v1'
PIN_SCHEMA = 'ao_pc_exploration_bundle_pin_v1'
PAYLOADS = {'nbg0.png', 'nbg1.png', 'flags.bin', 'profile.json', 'traces.json'}
FILES = PAYLOADS | {'package.json'}
LABELS = {'cardinal':'四方向接觸與持續壓牆', 'corners':'轉角與滑移',
          'open':'四方向空地移動', 'release':'滑移後放開按鍵'}
COUNTS = {'cardinal':240, 'corners':170, 'open':118, 'release':32}
SOURCE_KEYS = {'seed_sha256', 'reference_lock_sha256', 'source_lock_sha256',
               'map_sha256', 'code_sha256', 'core_sha256', 'capture_sources_sha256',
               'capture_build_sha256', 'scene_validation_sha256', 'capture_manifests'}
HASH = re.compile(r'[0-9a-f]{64}\Z')


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def decoded(raw: bytes):
    # Reuse the duplicate-key rejecting reader for arrays as well as objects.
    return read_json_bytes(b'{"root":' + raw + b'}')['root']


def valid_hash(value) -> bool:
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def no_redirect(path: Path) -> None:
    info = path.lstat()
    if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f'Bundle path is a link or reparse point: {path.name}')


def exact_files(folder: Path) -> None:
    no_redirect(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != FILES:
        raise ValueError('Bundle must contain exactly the six approved files')
    for path in folder.iterdir():
        no_redirect(path)
        if not path.is_file() or path.resolve().parent != folder.resolve():
            raise ValueError('Bundle entry is not a direct regular file')


def load_profile(raw: bytes, flags: bytes) -> movement.MovementProfile:
    value = decoded(raw)
    if not isinstance(value, dict) or value.get('schema') != movement.SCHEMA:
        raise ValueError('Unsupported movement profile')
    indices = value.get('verified_query_indices')
    if (not isinstance(indices, list) or not indices or
            any(type(i) is not int for i in indices) or indices != sorted(set(indices))):
        raise ValueError('Missing or invalid verified domain')
    if any(type(value.get(key)) is not int for key in ('control_word','disabled_byte','actor_address')):
        raise ValueError('Profile control identifiers must be integers')
    profile = movement.MovementProfile(flags, value['initial_state'], value['animation_root_sha256'],
        frozenset(indices), value['control_word'], value['disabled_byte'], value['actor_address'])
    if json.dumps(value,sort_keys=True) != json.dumps(profile.metadata(),sort_keys=True):
        raise ValueError('Unknown or altered movement profile fields')
    return profile


def verify(bundle: Path, expected_manifest_sha: str) -> dict:
    """Verify without original disc, BIOS, snapshots, extracted files or locks.

    The caller must provide the trusted build-time pin, not derive it from an
    untrusted package.json. Trace replay also rejects a widened query domain.
    """
    if not valid_hash(expected_manifest_sha):
        raise ValueError('A trusted manifest SHA256 is required')
    bundle = Path(bundle)
    exact_files(bundle)
    raw_manifest = stable_read(bundle / 'package.json')
    if digest(raw_manifest) != expected_manifest_sha:
        raise ValueError('Package manifest differs from trusted pin')
    package = decoded(raw_manifest)
    if not isinstance(package, dict) or set(package) != {
            'schema','reference_id','camera','viewport','source_local_only','files','source','state'}:
        raise ValueError('Unknown package fields')
    if (package['schema'] != SCHEMA or package['reference_id'] != 'map001-freewalk-20261009' or
            package['camera'] != [544,1536] or package['viewport'] != [320,224] or
            any(type(v) is not int for v in package['camera'] + package['viewport']) or
            package['source_local_only'] is not True or package['state'] != 'verified_region_only'):
        raise ValueError('Unsupported source scene or verification state')
    sources = package['source']
    if not isinstance(sources, dict) or set(sources) != SOURCE_KEYS:
        raise ValueError('Missing source provenance')
    for key in SOURCE_KEYS - {'capture_manifests'}:
        if not valid_hash(sources[key]):
            raise ValueError('Invalid source identity')
    if sources['code_sha256'] != movement.p.TWN_HASH or sources['core_sha256'] != movement.p.CORE_HASH:
        raise ValueError('Source code identity differs from movement model')
    manifests = sources['capture_manifests']
    if (not isinstance(manifests, dict) or set(manifests) != set(LABELS) or any(
            not isinstance(rows, list) or len(rows) != 3 or len(set(rows)) != 3 or
            any(not valid_hash(item) for item in rows) for rows in manifests.values())):
        raise ValueError('Each route must retain three distinct capture manifest identities')
    files = package['files']
    if not isinstance(files, dict) or set(files) != PAYLOADS:
        raise ValueError('Manifest payload names are not the exact allowlist')
    payload = {}
    for name in sorted(PAYLOADS):
        record = files[name]
        if (not isinstance(record, dict) or set(record) != {'bytes','sha256'} or
                type(record['bytes']) is not int or record['bytes'] <= 0 or not valid_hash(record['sha256'])):
            raise ValueError('Invalid payload record')
        raw = stable_read(bundle / name)
        if len(raw) != record['bytes'] or digest(raw) != record['sha256']:
            raise ValueError(f'Payload hash or size changed: {name}')
        payload[name] = raw
    for name in ('nbg0.png','nbg1.png'):
        with Image.open(io.BytesIO(payload[name])) as image:
            if image.format != 'PNG' or image.size != (320,224) or image.mode != 'RGBA':
                raise ValueError('Scene image must be RGBA PNG at 320x224')
            image.verify()
        with Image.open(io.BytesIO(payload[name])) as image:
            image.load()
    profile = load_profile(payload['profile.json'], payload['flags.bin'])
    traces = decoded(payload['traces.json'])
    if (not isinstance(traces, list) or len(traces) != 4 or
            any(not isinstance(t, dict) or set(t) != {'id','label','initial_state','updates'} for t in traces) or
            [t['id'] for t in traces] != list(LABELS)):
        raise ValueError('Exactly four ordered unique reference traces are required')
    union, compared = set(), 0
    for trace in traces:
        name = trace['id']
        if trace['label'] != LABELS[name] or trace['initial_state'] != profile.initial_state:
            raise ValueError('Trace label or initial state differs from profile')
        updates = trace['updates']
        if not isinstance(updates, list) or len(updates) != COUNTS[name]:
            raise ValueError('Reference trace is truncated or has extra updates')
        state = dict(profile.initial_state)
        for frame, row in enumerate(updates, 1):
            if (not isinstance(row, dict) or set(row) != {'frame','game_pad_word','expected','query_indices'} or
                    type(row['frame']) is not int or row['frame'] != frame):
                raise ValueError('Unknown or reordered trace update')
            movement.actor_from_state(row['expected'])
            state, diagnostics = movement.step_game_input(state, row['game_pad_word'], profile)
            indices = sorted({entry['index'] for entry in diagnostics['lookups']})
            if (not diagnostics['applied'] or state != row['expected'] or
                    row['query_indices'] != indices or any(type(i) is not int for i in row['query_indices'])):
                raise ValueError(f'Reference movement diverges: {name} frame {frame}')
            union.update(indices)
            compared += 1
    if union != profile.verified_query_indices:
        raise ValueError('Verified domain differs from exact replay query union')
    # Detect replacements during the verification interval as well as while read.
    exact_files(bundle)
    if stable_read(bundle / 'package.json') != raw_manifest or any(
            stable_read(bundle / name) != raw for name,raw in payload.items()):
        raise ValueError('Bundle changed during verification')
    return {'schema':'ao_pc_exploration_bundle_verification_v1', 'passed':True,
            'manifest_sha256':expected_manifest_sha, 'files':len(FILES),
            'updates_compared':compared, 'verified_query_count':len(union),
            'source_local_only':True, 'state':'verified_region_only'}


def build(output: Path = DEFAULT_OUT, pin_path: Path = DEFAULT_PIN) -> dict:
    output, pin_path = Path(output), Path(pin_path)
    if pin_path.resolve().is_relative_to(output.resolve()):
        raise ValueError('Trusted pin must be outside the six-file source bundle')
    pin = None
    if pin_path.exists():
        no_redirect(pin_path)
        pin = decoded(stable_read(pin_path))
        if (not isinstance(pin,dict) or set(pin) != {'schema','manifest_sha256'} or
                pin['schema'] != PIN_SCHEMA or not valid_hash(pin['manifest_sha256'])):
            raise ValueError('Existing pin file is not an approved bundle pin')
    if output.exists():
        if pin is None:
            raise ValueError('Existing bundle lacks a valid trusted pin')
        verify(output, pin['manifest_sha256'])
    elif output.is_symlink():
        raise ValueError('Output path may not be a link')
    lock_path = ROOT / 'exploration-reference-lock.json'
    lock_raw = stable_read(lock_path)
    validated = reference.validate()
    lock = reference.load_lock()
    if validated.get('e1_passed') is not True or stable_read(lock_path) != lock_raw:
        raise ValueError('Source baseline validation failed or changed')
    scene_path = reference.pinned_file(ROOT, lock['scene'])
    scene = read_json_bytes(stable_read(scene_path))
    reports, traces = [], []
    for name in LABELS:
        for number, record in enumerate(lock['captures'][name]):
            report, fixture = validate_trace(reference.pinned_file(ROOT, record).parent)
            if not report['passed'] or report['mismatched_updates']:
                raise ValueError('Original player trace comparison failed')
            reports.append(report)
            if number == 0:
                traces.append({'id':name,'label':LABELS[name],
                    'initial_state':fixture['initial_state'],'updates':fixture['updates']})
    metadata = dict(reports[0]['profile'])
    comparable = {k:v for k,v in metadata.items() if k != 'verified_query_indices'}
    if any({k:v for k,v in r['profile'].items() if k != 'verified_query_indices'} != comparable for r in reports):
        raise ValueError('Original routes do not share one scene and initial actor state')
    metadata['verified_query_indices'] = sorted(set().union(*(r['profile']['verified_query_indices'] for r in reports)))
    payload = {'profile.json':encoded(metadata),'traces.json':encoded(traces)}
    for name, record in scene['outputs'].items():
        payload[name] = stable_read(reference.pinned_file(scene_path.parent, {'path':name,**record}))
    if set(payload) != PAYLOADS:
        raise ValueError('Source scene introduced an unapproved payload')
    sources = {'seed_sha256':lock['seed']['sha256'], 'reference_lock_sha256':digest(lock_raw),
        'source_lock_sha256':scene['source_lock_sha256'], 'map_sha256':scene['source_sha256'],
        'code_sha256':scene['source_code_sha256'], 'core_sha256':movement.p.CORE_HASH,
        'capture_sources_sha256':lock['sources']['sha256'], 'capture_build_sha256':lock['build']['sha256'],
        'scene_validation_sha256':lock['scene']['sha256'],
        'capture_manifests':{name:[r['sha256'] for r in lock['captures'][name]] for name in LABELS}}
    package = {'schema':SCHEMA,'reference_id':lock['reference_id'],'camera':[544,1536],
        'viewport':[320,224],'source_local_only':True,'state':'verified_region_only',
        'files':{name:{'bytes':len(raw),'sha256':digest(raw)} for name,raw in sorted(payload.items())}, 'source':sources}
    raw_manifest = encoded(package)
    manifest_hash = digest(raw_manifest)
    if reference.load_lock() != lock or stable_read(lock_path) != lock_raw:
        raise ValueError('Source baseline changed before bundle publication')
    if output.resolve() == DEFAULT_OUT.resolve():
        marker = output.parent / '.gdignore'
        if marker.exists():
            no_redirect(marker)
            if stable_read(marker) != b'':
                raise ValueError('Unexpected generated-directory import exclusion file')
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b'')
    # Only known direct files are ever replaced; no recursive deletion or copy.
    if output.exists():
        verify(output, decoded(stable_read(pin_path))['manifest_sha256'])
    else:
        output.mkdir(parents=True)
    for name, raw in payload.items():
        (output / name).write_bytes(raw)
    (output / 'package.json').write_bytes(raw_manifest)
    result = verify(output, manifest_hash)
    pin_path.parent.mkdir(parents=True, exist_ok=True)
    pin_path.write_bytes(encoded({'schema':PIN_SCHEMA,'manifest_sha256':manifest_hash}))
    result['source_updates_compared'] = sum(r['updates_compared'] for r in reports)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('build')
    make.add_argument('--out', type=Path, default=DEFAULT_OUT)
    make.add_argument('--pin', type=Path, default=DEFAULT_PIN)
    check = commands.add_parser('verify')
    check.add_argument('bundle', type=Path)
    check.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    try:
        result = build(args.out,args.pin) if args.command == 'build' else verify(args.bundle,args.manifest_sha256)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.exit(1, f'Exploration bundle rejected: {exc}\n')
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
