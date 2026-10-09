"""Audit the pinned Godot PCK and the exact import closure of approved artwork."""
import hashlib
import json
import re
import struct
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CORE = {
    '.godot/global_script_class_cache.cfg', '.godot/uid_cache.bin',
    'data/appearances.json', 'data/encounter.json', 'project.binary', 'main.tscn.remap',
    *(f'{name}.{suffix}' for name in ('ui', 'core', 'fighter', 'backdrop') for suffix in ('gdc', 'gd.remap')),
}
MANIFEST = 'data/asset-manifest.json'


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def resource_path(value: str) -> str:
    """Only canonical project-relative resources; never read outside the project."""
    if not isinstance(value, str):
        raise ValueError('Resource path must be a string')
    name = value.removeprefix('res://')
    if (not name or '\\' in name or ':' in name or name.startswith('/')
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError(f'Invalid resource path: {value}')
    return name


def local_bytes(root: Path, name: str) -> bytes:
    path = (root / resource_path(name)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Resource escapes project directory')
    return path.read_bytes()


def import_paths(blob: bytes) -> set[str]:
    text = blob.rstrip(b'\0').decode('utf-8')
    paths = re.findall(r'^path(?:\.[\w]+)?="(res://[^"\r\n]+)"\s*$', text, re.M)
    if not paths or not re.search(r'^importer="texture"\s*$', text, re.M):
        raise ValueError('Approved PNG does not use a texture import')
    names = {resource_path(path) for path in paths}
    if any(not re.fullmatch(r'\.godot/imported/[^/]+-[0-9a-f]{32}(?:\.[\w]+)?\.ctex', name) for name in names):
        raise ValueError('Unexpected texture import destination')
    return names


def approved_art(root: Path) -> dict[str, dict]:
    """Validate source hashes and source-to-import dependencies before export."""
    if not (root / MANIFEST).exists():
        return {}
    manifest = json.loads(local_bytes(root, MANIFEST))
    if manifest.get('schema') != 'battle_assets_v1' or not isinstance(manifest.get('assets'), list):
        raise ValueError('Unsupported asset manifest')
    approved = {}
    for entry in manifest['assets']:
        name = resource_path(entry.get('path'))
        if (not name.startswith('assets/') or PurePosixPath(name).suffix != '.png'
                or name in approved or entry.get('role') != 'sprite'
                or not isinstance(entry.get('character'), str) or not entry['character']):
            raise ValueError(f'Invalid or duplicate approved asset: {name}')
        source = local_bytes(root, name)
        if not re.fullmatch('[0-9a-f]{64}', entry.get('sha256', '')) or sha256(source) != entry['sha256']:
            raise ValueError(f'Approved source hash mismatch: {name}')
        imported = local_bytes(root, name + '.import')
        paths = import_paths(imported)
        text = imported.decode('utf-8')
        source_match = re.search(r'^source_file="([^"\r\n]+)"\s*$', text, re.M)
        destinations = re.search(r'^dest_files=\[([^\]\r\n]*)\]\s*$', text, re.M)
        if (not source_match or resource_path(source_match[1]) != name or not destinations
                or {resource_path(value) for value in re.findall(r'"([^"]+)"', destinations[1])} != paths):
            raise ValueError(f'Import dependencies disagree with approved source: {name}')
        # Reject an old import even when the PNG's approved hash has changed.
        for destination in paths:
            cache_stem = re.sub(r'(?:\.[\w]+)?\.ctex$', '', destination)
            md5_file = local_bytes(root, cache_stem + '.md5').decode('ascii')
            match = re.search(r'^source_md5="([0-9a-f]{32})"\s*$', md5_file, re.M)
            if not match or match[1] != hashlib.md5(source).hexdigest():
                raise ValueError(f'Stale imported source: {name}')
        approved[name] = {'entry': entry, 'paths': paths, 'remap': text.split('[deps]', 1)[0].strip()}
    appearances = json.loads(local_bytes(root, 'data/appearances.json'))
    referenced = set()
    for appearance in appearances.values():
        if appearance.get('renderer') != 'sprite':
            continue
        for state in appearance.get('states', {}).values():
            if not isinstance(state, dict) or not isinstance(state.get('frames'), list):
                raise ValueError('Sprite appearance has invalid frame definitions')
            referenced.update(resource_path(path) for path in state['frames'])
    if referenced != set(approved):
        raise ValueError(f'Appearance/manifest asset mismatch; unapproved={sorted(referenced - set(approved))}, unused={sorted(set(approved) - referenced)}')
    return approved


def unpack(blob: bytes) -> dict[str, bytes]:
    if len(blob) < 112 or blob[:4] != b'GDPC':
        raise ValueError('Not the expected PCK')
    if struct.unpack_from('<5I', blob, 4) != (4, 4, 7, 2, 2):
        raise ValueError('Unsupported package layout')
    base, directory = struct.unpack_from('<QQ', blob, 24)
    if not 112 <= base <= directory <= len(blob) - 4:
        raise ValueError('Invalid directory bounds')
    count = struct.unpack_from('<I', blob, directory)[0]
    if not 1 <= count <= 4096:
        raise ValueError('Invalid package entry count')
    pos, payloads, spans = directory + 4, {}, []
    for _ in range(count):
        if pos + 4 > len(blob):
            raise ValueError('Truncated directory entry')
        length = struct.unpack_from('<I', blob, pos)[0]
        pos += 4
        if not 0 < length <= 512 or pos + length + 36 > len(blob):
            raise ValueError('Invalid directory entry')
        name = resource_path(blob[pos:pos + length].rstrip(b'\0').decode('utf-8'))
        pos += length
        start, size = struct.unpack_from('<QQ', blob, pos)
        expected = blob[pos + 16:pos + 32]
        entry_flags = struct.unpack_from('<I', blob, pos + 32)[0]
        pos += 36
        if name in payloads:
            raise ValueError(f'Duplicate package resource: {name}')
        if entry_flags or base + start + size > directory:
            raise ValueError('Unsupported flags or payload span')
        span = (base + start, base + start + size)
        if size and any(span[0] < end and begin < span[1] for begin, end in spans):
            raise ValueError('Overlapping package payloads')
        spans.append(span)
        payload = blob[span[0]:span[1]]
        if hashlib.md5(payload).digest() != expected:
            raise ValueError('Package payload checksum mismatch')
        payloads[name] = payload
    if pos != len(blob):
        raise ValueError('Trailing package data')
    return payloads


def audit(blob: bytes, source_root: Path | None = None) -> list[dict]:
    root = source_root or ROOT / 'battle-demo'
    payloads = unpack(blob)
    allowed = set(CORE)
    # This known helper is absent from the original baseline project.
    if (root / 'qa_recorder.gd').exists():
        allowed.update({'qa_recorder.gdc', 'qa_recorder.gd.remap'})
    if (root / MANIFEST).exists():
        allowed.add(MANIFEST)
    for name, asset in approved_art(root).items():
        remap = name + '.import'
        if remap not in payloads:
            raise ValueError(f'Missing approved texture import: {name}')
        paths = import_paths(payloads[remap])
        if paths != asset['paths'] or payloads[remap].rstrip(b'\0').decode('utf-8').strip() != asset['remap']:
            raise ValueError(f'Packaged import differs from approved mapping: {name}')
        allowed.add(remap)
        allowed.update(paths)
        for path in paths:
            if payloads.get(path) != local_bytes(root, path):
                raise ValueError(f'Packaged texture differs from approved import: {name}')
    remap = payloads.get('main.tscn.remap', b'').decode('utf-8')
    target = re.search(r'^path="res://(\.godot/exported/\d+/export-[0-9a-f]{32}-main\.scn)"\s*$', remap, re.M)
    if not target:
        raise ValueError('Invalid scene remap')
    allowed.add(target[1])
    if set(payloads) != allowed:
        raise ValueError(f'Package resource mismatch; extra={sorted(set(payloads) - allowed)}, missing={sorted(allowed - set(payloads))}')
    for name, payload in payloads.items():
        if name.startswith('data/') and payload != local_bytes(root, name):
            raise ValueError(f'Packaged definitions differ from source: {name}')
    return [{'path': name, 'bytes': len(payload), 'sha256': sha256(payload)} for name, payload in payloads.items()]


if __name__ == '__main__':
    blob = (ROOT / 'build/battle-demo/Triad-Trial.pck').read_bytes()
    entries = audit(blob)
    corrupted = bytearray(blob)
    corrupted[112] ^= 1
    renamed = blob.replace(b'data/encounter.json', b'data/forbidden.json')
    for bad in (bytes(corrupted), renamed, blob[:-1]):
        try:
            audit(bad)
        except (ValueError, struct.error):
            continue
        raise AssertionError('Invalid package accepted')
    report = {'schema': 'battle_demo_package_audit_v2', 'pck_sha256': sha256(blob),
              'files': entries, 'approved_art': [value['entry'] for value in approved_art(ROOT / 'battle-demo').values()],
              'negative_checks': 3, 'original_game_assets_included': False}
    (ROOT / 'reports/battle-package.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Battle package: {len(entries)} approved resources; 3 invalid-package cases rejected.')
