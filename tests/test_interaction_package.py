"""Mutate the actual interaction export inventory, never placeholder release art."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_interaction_package as audit
from audit_battle_package import unpack
from test_exploration_package import pck
from test_character_package import project


class InteractionPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate=json.loads((audit.ROOT/'reports/interaction/candidate.json').read_bytes())
        cls.folder=Path(candidate['directory'])
        cls.raw=(cls.folder/'MAP001-Interaction.pck').read_bytes()
        cls.files=unpack(cls.raw)

    def test_real_six_bundle_delivery(self):
        self.assertTrue(audit.audit(self.folder)['passed'])
        self.assertEqual(len(audit.BUNDLES),6)

    def test_unknown_script_or_source_rejected(self):
        for name in ('extra.gdc','wram-high.bin','source.cue','BIOS.bin','preview.png'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                audit.audit_pck(pck(self.files|{name:b'unknown'}))

    def test_missing_dependency_rejected(self):
        for name in ('interaction_core.gdc','event_core.gdc','room_priority.gdshader','interaction-pin.json'):
            changed=dict(self.files);del changed[name]
            with self.subTest(name=name),self.assertRaises(ValueError):audit.audit_pck(pck(changed))

    def test_all_six_pins_remain_locked(self):
        for name in audit.PINS:
            with self.subTest(name=name),self.assertRaises(ValueError):
                audit.audit_pck(pck(self.files|{name:self.files[name]+b' '}))

    def test_other_entry_and_feature_override_rejected(self):
        for feature in ('room_demo','character_demo',''):
            with self.subTest(feature=feature),self.assertRaises(ValueError):
                audit.audit_pck(pck(self.files|{'project.binary':project(feature=feature,extra={'application/run/main_scene.event_demo':'res://event_main.tscn'})}))

    def test_truncated_export_rejected(self):
        with self.assertRaises(ValueError):audit.audit_pck(self.raw[:len(self.raw)//2])

if __name__=='__main__':unittest.main()
