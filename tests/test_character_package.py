"""Source-free PCK/three-bundle/ZIP faults. Semantic asset verification is mocked.

These fixtures are not approved HD artwork and must never become a release.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_character_package as package
from test_exploration_package import pck


def project(main='res://character_main.tscn'):
    value = main.encode()
    payload = struct.pack('<II', 4, len(value)) + value + b'\0' * (-len(value) % 4)
    key = b'application/run/main_scene'
    return b'ECFG' + struct.pack('<II', 1, len(key)) + key + struct.pack('<I', len(payload)) + payload


class CharacterPackageTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'reports/character/package-test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.delivery = self.root / 'delivery'; self.delivery.mkdir()
        for name in package.ROOT_FILES:
            (self.delivery / name).write_bytes(b'MZ synthetic' if name.endswith('.exe') else b'Synthetic document')
        for folder, names in package.BUNDLES.items():
            (self.delivery / folder).mkdir()
            for name in names: (self.delivery / folder / name).write_bytes(b'Synthetic payload ' + name.encode())
        self.pins = {
            'bundle-pin.json': package.scene.encoded({'schema':'ao_pc_exploration_bundle_pin_v1','manifest_sha256':'a'*64}),
            'character-pin.json': package.scene.encoded({'schema':'ao_pc_character_bundle_pin_v1','manifest_sha256':'b'*64,'scene_manifest_sha256':'a'*64}),
            'character-hd-pin.json': package.scene.encoded({'schema':'ao_pc_character_hd_bundle_pin_v1','manifest_sha256':'c'*64,'scene_manifest_sha256':'a'*64,'source_character_manifest_sha256':'b'*64})}
        self.files = dict.fromkeys(package.PCK_FILES, b'synthetic cache')
        self.main = '.godot/exported/123/export-' + 'd'*32 + '-character_main.scn'
        self.files[self.main] = b'Compiled scene'
        self.files['character_main.tscn.remap'] = f'[remap]\npath="res://{self.main}"\n'.encode()
        self.files['character_priority.gdshader'] = b'shader_type canvas_item;\n'
        self.files['project.binary'] = project()
        self.files.update(self.pins)
        for name in package.SCRIPTS:
            self.files[name+'.gdc'] = b'GDSC synthetic compiled script'
            self.files[name+'.gd.remap'] = f'[remap]\npath="res://{name}.gdc"\n'.encode()
        self.semantic = patch.object(package, 'verify_external_bundles', return_value={'synthetic_semantic_mock':True})
        self.semantic.start(); self.addCleanup(self.semantic.stop)
        self.rebuild()

    def rebuild(self):
        (self.delivery / 'MAP001-Character.pck').write_bytes(pck(self.files))
        package.write_build_info(self.delivery, self.pins, 'e'*40, True)

    def test_exact_three_bundle_closure(self):
        result = package.audit_delivery(self.delivery, self.pins)
        self.assertTrue(result['passed'])
        self.assertEqual([len(package.BUNDLES[k]) for k in ['scene','character','character-hd']], [6,33,58])
        self.assertFalse(result['cold_start_tested'] or result['a6_performance_passed'])
        (self.delivery / package.CONSOLE).write_bytes(b'MZ synthetic console'); self.rebuild()

    def test_semantic_verifiers_use_delivered_siblings_not_editor_paths(self):
        import character_hd_bundle as hd
        self.semantic.stop()
        with patch.object(package.scene,'verify',return_value={'passed':True}) as base, \
             patch.object(package.character,'verify',return_value={'passed':True}) as original, \
             patch.object(hd,'verify',return_value={'passed':True}) as high:
            package.verify_external_bundles(self.delivery,package.validate_pins(self.pins))
            base.assert_called_once_with(self.delivery/'scene','a'*64)
            self.assertEqual(original.call_args.kwargs['scene_bundle'],self.delivery/'scene')
            self.assertEqual(high.call_args.kwargs['scene_bundle'],self.delivery/'scene')
            self.assertEqual(high.call_args.kwargs['source_character_bundle'],self.delivery/'character')

    def test_old_main_entry_rejected_even_with_character_scene(self):
        for main in ['res://main.tscn', 'res://tests/test_character_ui.gd']:
            with self.subTest(main=main), self.assertRaisesRegex(ValueError, 'launch'):
                package.audit_pck(pck(self.files | {'project.binary':project(main)}), self.pins)

    def test_pck_raw_sources_reference_png_and_tests_rejected(self):
        for name in ['wram-high.bin','BIOS.bin','source.cue','reference.png','generated/character/up-idle.png',
                     'tests/test_ui.gdc','extra.gdc','main.tscn.remap','character_main.gd']:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'resource mismatch'):
                package.audit_pck(pck(self.files | {name:b'unapproved'}), self.pins)

    def test_missing_compiled_script_or_wrong_remap(self):
        files = dict(self.files); del files['character_hd_loader.gdc']
        with self.assertRaises(ValueError): package.audit_pck(pck(files), self.pins)
        files = self.files | {'character_hd_loader.gd.remap':b'[remap]\npath="res://main.gdc"\n'}
        with self.assertRaisesRegex(ValueError,'remap'): package.audit_pck(pck(files),self.pins)

    def test_each_pin_identity_and_cross_binding_enforced(self):
        for name in package.PINS:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'pin differs'):
                package.audit_pck(pck(self.files | {name:b'{}'}),self.pins)
        pins = dict(self.pins)
        hd = json.loads(pins['character-hd-pin.json']); hd['source_character_manifest_sha256']='d'*64
        pins['character-hd-pin.json'] = package.scene.encoded(hd)
        with self.assertRaisesRegex(ValueError,'disagree'): package.validate_pins(pins)
        with self.assertRaises(ValueError): package.validate_pins({})

    def test_pck_checksum_truncation_and_project_trailing_bytes(self):
        raw = bytearray(pck(self.files)); raw[112] ^= 1
        with self.assertRaisesRegex(ValueError,'checksum'): package.audit_pck(bytes(raw),self.pins)
        with self.assertRaises(ValueError): package.audit_pck(pck(self.files)[:-1],self.pins)
        with self.assertRaises(ValueError): package.project_values(project()+b'bad')
        with self.assertRaises(ValueError): package.project_values(project()[:-2])

    def test_extra_outer_source_missing_hd_and_changed_payload(self):
        bad=self.delivery/'snapshot.savestate';bad.write_bytes(b'forbidden')
        with self.assertRaisesRegex(ValueError,'file mismatch'): package.audit_delivery(self.delivery,self.pins)
        bad.unlink()
        original=self.delivery/'character-hd/up-walk-11.png'; data=original.read_bytes();original.unlink()
        with self.assertRaisesRegex(ValueError,'closure'): package.audit_delivery(self.delivery,self.pins)
        original.write_bytes(data+b'changed')
        with self.assertRaisesRegex(ValueError,'inventory'): package.audit_delivery(self.delivery,self.pins)

    def test_build_source_identity_and_document_inventory(self):
        info=json.loads((self.delivery/package.BUILD_INFO).read_text());info['source_has_uncommitted_changes']='false'
        (self.delivery/package.BUILD_INFO).write_text(json.dumps(info))
        with self.assertRaisesRegex(ValueError,'identity'): package.audit_delivery(self.delivery,self.pins)
        self.rebuild();(self.delivery/'README.md').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'inventory'): package.audit_delivery(self.delivery,self.pins)

    def test_zip_round_trip_and_prior_zip_preserved(self):
        archive=self.root/'new.zip'; target=self.root/'extract'
        report=package.create_zip(self.delivery,archive,target,self.pins)
        self.assertTrue(report['passed'] and report['extraction_verified'])
        with self.assertRaisesRegex(ValueError,'new ZIP'): package.create_zip(self.delivery,archive,self.root/'other',self.pins)
        with self.assertRaisesRegex(ValueError,'must not exist'): package.verify_zip(archive,self.delivery,target,self.pins)

    def test_bad_zip_fails_before_any_extraction(self):
        base=[(name,p.read_bytes()) for name,p in package.delivery_files(self.delivery).items()]
        mutations=[lambda r:r+[('../escape',b'bad')],lambda r:r+[('source.iso',b'bad')],
                   lambda r:r[:-1],lambda r:r+[('readme.md',b'alias')],
                   lambda r:[(n,b'changed' if n=='character-hd/up-walk-11.png' else b) for n,b in r]]
        for index, change in enumerate(mutations):
            archive=self.root/f'bad{index}.zip';target=self.root/f'not-created{index}'
            with zipfile.ZipFile(archive,'w') as zipped:
                for name,raw in change(base):zipped.writestr(name,raw)
            with self.assertRaises(ValueError):package.verify_zip(archive,self.delivery,target,self.pins)
            self.assertFalse(target.exists())


if __name__ == '__main__': unittest.main()
