"""Source-free structural package tests plus an explicit local-bundle integration.

Structural cases mock only semantic scene verification, which is independently
covered by test_exploration_bundle. PCK parsing and ZIP checks are always real.
"""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_exploration_package as package


def pck(files):
    blob = bytearray(112)
    blob[:4] = b'GDPC'
    struct.pack_into('<5I', blob, 4, 4, 4, 7, 2, 2)
    records = []
    for name, payload in sorted(files.items()):
        offset = len(blob) - 112
        blob.extend(payload)
        name = name.encode()
        records.append(struct.pack('<I', len(name)) + name + struct.pack('<QQ', offset, len(payload))
                       + hashlib.md5(payload).digest() + struct.pack('<I', 0))
    directory = len(blob)
    blob.extend(struct.pack('<I', len(records)))
    for record in records:
        blob.extend(record)
    struct.pack_into('<QQ', blob, 24, 112, directory)
    return bytes(blob)


class ExplorationPackageTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'reports/exploration/package-test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        assert Path(self.temp.name).resolve().parent == scratch.resolve()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.delivery = self.root / 'delivery'
        self.delivery.mkdir()
        (self.delivery / 'scene').mkdir()
        for name in package.ROOT_FILES:
            (self.delivery / name).write_bytes(b'MZ synthetic' if name.endswith('.exe') else b'synthetic document')
        for name in package.bundle.FILES:
            (self.delivery / 'scene' / name).write_bytes(b'synthetic scene payload')
        self.pin = package.bundle.encoded({'schema': package.bundle.PIN_SCHEMA,
            'manifest_sha256': package.sha((self.delivery / 'scene/package.json').read_bytes())})
        self.files = dict.fromkeys(package.PCK_FILES, b'synthetic cache')
        self.scene = '.godot/exported/123/export-' + 'a' * 32 + '-main.scn'
        self.files[self.scene] = b'synthetic compiled scene'
        self.files['main.tscn.remap'] = f'[remap]\npath="res://{self.scene}"\n'.encode()
        self.files['bundle-pin.json'] = self.pin
        self.files['project.binary'] = b'ECFG synthetic'
        for name in package.SCRIPTS:
            self.files[name + '.gdc'] = b'GDSC synthetic compiled script'
            self.files[name + '.gd.remap'] = f'[remap]\npath="res://{name}.gdc"\n'.encode()
        self.semantic = patch.object(package.bundle, 'verify', return_value={'passed': True})
        self.semantic.start()
        self.addCleanup(self.semantic.stop)
        self.rebuild()

    def rebuild(self):
        (self.delivery / 'MAP001-Walk.pck').write_bytes(pck(self.files))
        package.write_build_info(self.delivery, self.pin, 'a' * 40, True)

    def check(self):
        return package.audit_delivery(self.delivery, self.pin)

    def test_exact_package_and_optional_console(self):
        self.assertTrue(self.check()['passed'])
        self.assertEqual(len(self.check()['pck_resources']), 12)
        (self.delivery / package.CONSOLE).write_bytes(b'MZ console fixture')
        self.rebuild()
        self.assertIn(package.CONSOLE, [entry['path'] for entry in self.check()['files']])

    def test_pck_forbidden_resources(self):
        for name in ['generated/scene/flags.bin', 'tests/test_ui.gdc', 'source.iso', 'wram-high.bin',
                     'BIOS.bin', 'snapshot.savestate', 'main.gd', 'extra.gdc']:
            with self.subTest(name=name):
                files = {**self.files, name: b'forbidden'}
                with self.assertRaisesRegex(ValueError, 'resource mismatch'):
                    package.audit_pck(pck(files), self.pin)

    def test_missing_script_and_wrong_remap(self):
        files = dict(self.files)
        del files['movement_core.gdc']
        with self.assertRaisesRegex(ValueError, 'missing='):
            package.audit_pck(pck(files), self.pin)
        files = dict(self.files)
        files['movement_core.gd.remap'] = b'[remap]\npath="res://main.gdc"\n'
        with self.assertRaisesRegex(ValueError, 'Script remap'):
            package.audit_pck(pck(files), self.pin)

    def test_malicious_scene_remap_and_compiled_format(self):
        for raw in [b'[remap]\npath="res://../private.bin"\n', b'[remap]\npath="res://main.gdc"\n',
                    b'[remap]\npath="res://main.gdc"\nextra="secret"\n']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                package.audit_pck(pck({**self.files, 'main.tscn.remap': raw}), self.pin)
        with self.assertRaisesRegex(ValueError, 'compiled script'):
            package.audit_pck(pck({**self.files, 'main.gdc': b'plain source'}), self.pin)

    def test_pck_checksum_and_truncation(self):
        raw = bytearray(pck(self.files))
        raw[112] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            package.audit_pck(bytes(raw), self.pin)
        with self.assertRaises(ValueError):
            package.audit_pck(pck(self.files)[:-1], self.pin)

    def test_wrong_or_ambiguous_pin(self):
        wrong = package.bundle.encoded({'schema': package.bundle.PIN_SCHEMA, 'manifest_sha256': 'b' * 64})
        with self.assertRaisesRegex(ValueError, 'bundle pin'):
            package.audit_pck(pck({**self.files, 'bundle-pin.json': wrong}), self.pin)
        for raw in [b'{}', b'{"schema":"first","schema":"second"}', b'{"manifest_sha256":"bad"}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                package.pin_value(raw)

    def test_extra_outer_source_and_missing_scene_payload(self):
        path = self.delivery / 'disc.bin'
        path.write_bytes(b'forbidden')
        with self.assertRaisesRegex(ValueError, 'file mismatch'):
            self.check()
        path.unlink()
        (self.delivery / 'scene/flags.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'six approved'):
            self.check()

    def test_changed_outer_or_payload_bytes_and_false_build_identity(self):
        for name in ['README.md', 'scene/flags.bin']:
            path = self.delivery / name
            original = path.read_bytes()
            path.write_bytes(original + b' changed')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'inventory'):
                self.check()
            path.write_bytes(original)
        info = json.loads((self.delivery / package.BUILD_INFO).read_text())
        info['source_has_uncommitted_changes'] = 'false'
        (self.delivery / package.BUILD_INFO).write_text(json.dumps(info))
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.check()

    def test_zip_round_trip_and_existing_target_rejection(self):
        archive = self.root / 'delivery.zip'
        target = self.root / 'extracted'
        report = package.create_zip(self.delivery, archive, target, self.pin)
        self.assertTrue(report['passed'] and report['extraction_verified'])
        self.assertEqual(self.check()['files'], package.audit_delivery(target, self.pin)['files'])
        with self.assertRaisesRegex(ValueError, 'must not exist'):
            package.verify_zip(archive, self.delivery, target, self.pin)

    def malicious_zip(self, mutation):
        archive = self.root / 'bad.zip'
        items = [(name, path.read_bytes()) for name,path in package.delivery_files(self.delivery).items()]
        with zipfile.ZipFile(archive, 'w') as zipped:
            for name, raw in mutation(items):
                zipped.writestr(name, raw)
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            package.verify_zip(archive, self.delivery, self.root / 'never-created', self.pin)
        self.assertFalse((self.root / 'never-created').exists())

    def test_zip_traversal_extra_missing_and_changed_bytes_rejected_before_extraction(self):
        cases = [lambda rows: rows + [('../escape', b'bad')],
                 lambda rows: rows + [('disc.bin', b'bad')],
                 lambda rows: rows[:-1],
                 lambda rows: [(name, raw + b'changed' if name == 'README.md' else raw) for name,raw in rows],
                 lambda rows: rows + [('readme.md', b'case alias')]]
        for index, mutation in enumerate(cases):
            with self.subTest(case=index):
                self.malicious_zip(mutation)

    def test_zip_symlink_rejected(self):
        item = zipfile.ZipInfo('README.md')
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.malicious_zip(lambda rows: [(item if name == 'README.md' else name, raw) for name,raw in rows])

    def test_real_local_bundle_pin_and_payload_integration(self):
        source = ROOT / 'exploration-demo/generated/scene'
        pin = ROOT / 'exploration-demo/bundle-pin.json'
        if not source.is_dir() or not pin.is_file():
            self.skipTest('Local source-derived bundle is unavailable; synthetic structural tests still run')
        self.semantic.stop()
        self.pin = pin.read_bytes()
        self.files['bundle-pin.json'] = self.pin
        for name in package.bundle.FILES:
            shutil.copyfile(source / name, self.delivery / 'scene' / name)
        self.rebuild()
        self.assertEqual(self.check()['bundle']['updates_compared'], 560)
        original = self.delivery / 'scene/flags.bin'
        data = bytearray(original.read_bytes())
        data[0] ^= 1
        original.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'hash or size'):
            self.check()


if __name__ == '__main__':
    unittest.main()
