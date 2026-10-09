import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import audit_battle_package as package


def pck(files):
    blob = bytearray(112)
    blob[:4] = b'GDPC'
    struct.pack_into('<5I', blob, 4, 4, 4, 7, 2, 2)
    records = []
    for name, payload in files.items():
        offset = len(blob) - 112
        blob.extend(payload)
        name = name.encode('utf-8')
        records.append(struct.pack('<I', len(name)) + name + struct.pack('<QQ', offset, len(payload))
                       + hashlib.md5(payload).digest() + struct.pack('<I', 0))
    directory = len(blob)
    blob.extend(struct.pack('<I', len(records)))
    for record in records:
        blob.extend(record)
    struct.pack_into('<QQ', blob, 24, 112, directory)
    return bytes(blob)


class PackageTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / 'reports' / 'package-test-temp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = dict.fromkeys(package.CORE, b'fixture')
        self.scene = '.godot/exported/123/export-' + 'a' * 32 + '-main.scn'
        self.files[self.scene] = b'scene'
        self.files['main.tscn.remap'] = f'[remap]\npath="res://{self.scene}"\n'.encode()
        self.write('data/encounter.json', b'fixture')
        self.write('data/appearances.json', b'fixture')

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def add_art(self):
        self.name = 'assets/pike/atlas.png'
        self.compiled = '.godot/imported/atlas.png-' + 'b' * 32 + '.ctex'
        source = b'approved source image'
        self.manifest = {'schema': 'battle_assets_v1', 'assets': [
            {'path': self.name, 'sha256': package.sha256(source), 'role': 'sprite', 'character': 'pike'}]}
        manifest_bytes = json.dumps(self.manifest).encode()
        self.write(package.MANIFEST, manifest_bytes)
        self.files[package.MANIFEST] = manifest_bytes
        self.write(self.name, source)
        self.remap = f'[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\npath="res://{self.compiled}"\n'
        deps = f'\n[deps]\n\nsource_file="res://{self.name}"\ndest_files=["res://{self.compiled}"]\n'
        self.write(self.name + '.import', (self.remap + deps).encode())
        self.write(self.compiled, b'imported pixels')
        self.write(self.compiled[:-5] + '.md5', f'source_md5="{hashlib.md5(source).hexdigest()}"\n'.encode())
        self.files[self.name + '.import'] = self.remap.encode() + b'\0'
        self.files[self.compiled] = b'imported pixels'

    def check(self):
        return package.audit(pck(self.files), self.root)

    def test_baseline_and_approved_texture_closure(self):
        self.assertEqual(len(self.check()), 15)
        self.add_art()
        self.assertEqual(len(self.check()), 18)

    def test_unlisted_asset_and_raw_source_are_rejected(self):
        self.add_art()
        for name in ('assets/unapproved.png', self.name, self.compiled[:-5] + '.md5'):
            with self.subTest(name=name):
                self.files[name] = b'unapproved'
                with self.assertRaises(ValueError):
                    self.check()
                del self.files[name]

    def test_changed_source_and_stale_import_are_rejected(self):
        self.add_art()
        self.write(self.name, b'changed source')
        with self.assertRaisesRegex(ValueError, 'source hash'):
            self.check()
        self.manifest['assets'][0]['sha256'] = package.sha256(b'changed source')
        raw = json.dumps(self.manifest).encode()
        self.write(package.MANIFEST, raw)
        self.files[package.MANIFEST] = raw
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.check()

    def test_remap_and_compiled_content_are_checked(self):
        self.add_art()
        self.files[self.name + '.import'] = self.remap.replace('CompressedTexture2D', 'UnexpectedType').encode()
        with self.assertRaisesRegex(ValueError, 'mapping'):
            self.check()
        self.files[self.name + '.import'] = self.remap.encode()
        self.files[self.compiled] = b'tampered cached pixels'
        with self.assertRaisesRegex(ValueError, 'texture differs'):
            self.check()

    def test_source_dependency_and_manifest_path_are_checked(self):
        self.add_art()
        path = self.root / (self.name + '.import')
        path.write_text(path.read_text().replace('source_file="res://assets/pike/', 'source_file="res://assets/other/'))
        with self.assertRaisesRegex(ValueError, 'dependencies'):
            self.check()
        for name in ('../secret.png', 'assets/../secret.png', 'G:/secret.png', 'assets\\secret.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package.resource_path(name)

    def test_missing_resource_wrong_definition_and_truncated_directory(self):
        del self.files['core.gdc']
        with self.assertRaisesRegex(ValueError, 'missing='):
            self.check()
        self.files['core.gdc'] = b'fixture'
        self.files['data/encounter.json'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'definitions'):
            self.check()
        with self.assertRaises(ValueError):
            package.audit(pck(self.files)[:-1], self.root)

    def test_payload_corruption_and_overlapping_entries_are_rejected(self):
        raw = bytearray(pck(self.files))
        raw[112] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            package.audit(bytes(raw), self.root)
        raw = bytearray(pck(self.files))
        directory = struct.unpack_from('<Q', raw, 32)[0]
        pos = directory + 4
        first_length = struct.unpack_from('<I', raw, pos)[0]
        pos += 4 + first_length + 36
        second_length = struct.unpack_from('<I', raw, pos)[0]
        struct.pack_into('<Q', raw, pos + 4 + second_length, 0)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            package.audit(bytes(raw), self.root)


if __name__ == '__main__':
    unittest.main()
