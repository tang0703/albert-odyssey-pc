"""Audit this project's unencrypted Godot 4.7.2 PCK v4 against a strict file list."""
import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    '.godot/global_script_class_cache.cfg', '.godot/uid_cache.bin',
    'data/appearances.json', 'data/encounter.json', 'project.binary', 'main.tscn.remap',
    *(f'{name}.{suffix}' for name in ('ui', 'core', 'fighter', 'backdrop') for suffix in ('gdc', 'gd.remap')),
}


def audit(blob: bytes) -> list[dict]:
    if len(blob) < 112 or blob[:4] != b'GDPC':
        raise ValueError('Not the expected PCK')
    version, major, minor, patch, flags = struct.unpack_from('<5I', blob, 4)
    if (version, major, minor, patch, flags) != (4, 4, 7, 2, 2):
        raise ValueError('Unsupported package layout')
    base, directory = struct.unpack_from('<QQ', blob, 24)
    if not 112 <= base <= directory <= len(blob) - 4:
        raise ValueError('Invalid directory bounds')
    count = struct.unpack_from('<I', blob, directory)[0]
    if count != 15:
        raise ValueError('Unexpected package file count')
    pos, entries, names = directory + 4, [], set()
    for _ in range(count):
        length = struct.unpack_from('<I', blob, pos)[0]
        pos += 4
        if not 0 < length <= 512 or pos + length + 36 > len(blob):
            raise ValueError('Invalid directory entry')
        name = blob[pos:pos + length].rstrip(b'\0').decode('utf-8')
        pos += length
        start, size = struct.unpack_from('<QQ', blob, pos)
        expected = blob[pos + 16:pos + 32]
        entry_flags = struct.unpack_from('<I', blob, pos + 32)[0]
        pos += 36
        if name in names or (name not in ALLOWED and not re.fullmatch(r'\.godot/exported/\d+/export-[0-9a-f]{32}-main\.scn', name)):
            raise ValueError(f'Unexpected or duplicate package resource: {name}')
        if entry_flags or base + start + size > directory:
            raise ValueError('Unsupported flags or payload span')
        payload = blob[base + start:base + start + size]
        if hashlib.md5(payload).digest() != expected:
            raise ValueError('Package payload checksum mismatch')
        if name.startswith('data/') and payload != (ROOT / 'battle-demo' / name).read_bytes():
            raise ValueError('Packaged definitions differ from source')
        entries.append({'path': name, 'bytes': size, 'sha256': hashlib.sha256(payload).hexdigest()})
        names.add(name)
    if pos != len(blob) or not ALLOWED.issubset(names):
        raise ValueError('Missing resources or trailing data')
    return entries


if __name__ == '__main__':
    path = ROOT / 'build/battle-demo/Triad-Trial.pck'
    blob = path.read_bytes()
    entries = audit(blob)
    # Real-package negative checks: altered content and unapproved file identity.
    corrupted = bytearray(blob)
    corrupted[112] ^= 1
    renamed = blob.replace(b'data/encounter.json', b'data/forbidden.json')
    for bad in (bytes(corrupted), renamed, blob[:-1]):
        try:
            audit(bad)
        except (ValueError, struct.error):
            continue
        raise AssertionError('Invalid package accepted')
    report = {'schema': 'battle_demo_package_audit_v1', 'pck_sha256': hashlib.sha256(blob).hexdigest(),
              'files': entries, 'negative_checks': 3, 'source_assets_included': False}
    (ROOT / 'reports/battle-package.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Battle package: 15 approved resources; 3 invalid-package cases rejected.')
