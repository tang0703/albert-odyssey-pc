"""Verify the separately versioned MAP001 baseline without changing old locks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from exploration_capture import read_json_bytes, stable_read, verify_sources
from verify_exploration_replay import inspect, verify

ROOT = Path(__file__).resolve().parents[1]


def pinned_file(root: Path, record: dict) -> Path:
    name = record.get('path')
    if (not isinstance(name, str) or '\\' in name or ':' in name
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('Invalid reference path')
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Reference path escapes the project')
    raw = stable_read(path)
    if len(raw) != record.get('bytes') or hashlib.sha256(raw).hexdigest() != record.get('sha256'):
        raise ValueError(f'Locked exploration evidence changed: {name}')
    return path


def load_lock(path: Path = ROOT / 'exploration-reference-lock.json') -> dict:
    lock = read_json_bytes(stable_read(path))
    if lock.get('schema') != 'ao_pc_exploration_reference_lock_v1':
        raise ValueError('Unsupported exploration reference lock')
    if set(lock.get('captures', {})) != {'cardinal', 'corners', 'open', 'release'}:
        raise ValueError('Missing required MAP001 route groups')
    if len(lock.get('navigation', [])) != 5:
        raise ValueError('Incomplete navigation lineage')
    records = [lock[key] for key in ('seed', 'sources', 'build', 'scene')]
    records.extend(lock['navigation'])
    for group in lock['captures'].values():
        if len(group) != 3:
            raise ValueError('Every route requires three pinned captures')
        records.extend(group)
    if len({r['path'] for r in records}) != len(records):
        raise ValueError('Duplicate reference identity')
    for record in records:
        pinned_file(ROOT, record)
    return lock


def validate() -> dict:
    lock = load_lock()
    source_path = pinned_file(ROOT, lock['sources'])
    sources = verify_sources(source_path, lock['sources']['sha256'])
    source_records = read_json_bytes(stable_read(source_path))
    build = read_json_bytes(stable_read(pinned_file(ROOT, lock['build'])))
    seed = pinned_file(ROOT, lock['seed'])
    scene_path = pinned_file(ROOT, lock['scene'])
    scene = read_json_bytes(stable_read(scene_path))
    if (scene.get('schema') != 'ao_pc_exploration_scene_v1' or scene.get('passed') is not True
            or scene.get('snapshot_sha256') != lock['seed']['sha256']
            or scene.get('camera') != [544, 1536] or scene.get('viewport') != [320, 224]):
        raise ValueError('Scene validation does not describe the locked free-walk seed')
    if set(scene.get('outputs', {})) != {'nbg0.png', 'nbg1.png', 'flags.bin'}:
        raise ValueError('Incomplete source-verified scene files')
    for name, record in scene['outputs'].items():
        pinned_file(scene_path.parent, {'path': name, **record})
    source_ids = {r['path']: r['sha256'] for r in source_records['disc_files']}
    for role in ('cue', 'bios'):
        record = source_records['inputs'][role]
        source_ids[record['path']] = record['sha256']
    if build != source_records['build_metadata']:
        raise ValueError('Capture build does not match the source baseline')
    previous_final = None
    navigation = []
    for record in lock['navigation']:
        folder = pinned_file(ROOT, record).parent
        run = inspect(folder)
        inputs = {name: sha for name, size, sha in run['inputs']}
        if run['build'] != build or any(inputs.get(p) != sha for p, sha in source_ids.items()):
            raise ValueError('Navigation changes the pinned emulator or disc sources')
        options = dict(run['arguments'])
        if previous_final is not None and options.get('--load-state') != str(previous_final):
            raise ValueError('Navigation does not resume its previous terminal state')
        previous_final = folder / f"frame-{run['capture']['frames']:06d}/state.savestate"
        navigation.append({'manifest_sha256': record['sha256'], 'frames': run['capture']['frames']})
    if hashlib.sha256(stable_read(previous_final)).hexdigest() != lock['seed']['sha256']:
        raise ValueError('Free-walk seed is not the navigation terminal state')
    replays = {}
    for name, group in lock['captures'].items():
        folders = [pinned_file(ROOT, record).parent for record in group]
        result = verify(folders)
        if not result['passed']:
            raise ValueError(f'{name} replays diverge')
        for folder in folders:
            manifest = read_json_bytes(stable_read(folder / 'manifest.json'))
            inputs = {r['path']: r['sha256'] for r in manifest['inputs']}
            argv = manifest['arguments']
            captured_seed = Path(argv[argv.index('--load-state') + 1])
            if not captured_seed.is_absolute():
                captured_seed = Path(manifest['working_directory']) / captured_seed
            if (manifest['build'] != build or inputs.get(str(captured_seed.resolve())) != lock['seed']['sha256']
                    or any(inputs.get(p) != sha for p, sha in source_ids.items())):
                raise ValueError('Replay does not use the pinned free-walk seed and sources')
        replays[name] = result
    # Re-read pins after all potentially long source checks.
    if load_lock() != lock:
        raise ValueError('Reference lock changed during validation')
    return {'schema': 'ao_pc_exploration_reference_validation_v1',
            'reference_id': lock['reference_id'], 'source_integrity': sources['source_integrity'],
            'synchronized_sampling_passed': True, 'source_scene_passed': True,
            'e1_passed': True, 'navigation': navigation, 'replays': replays,
            'movement_model_evidence_passed': False,
            'limits': ['This validates source identity, scene pixels and synchronized replay, not movement rules.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Pinned sources, navigation and four route replay groups passed.')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'Reference rejected: {exc}\n')
