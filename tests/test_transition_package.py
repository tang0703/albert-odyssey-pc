"""Mutate the actual equipment export inventory, never placeholder release art."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_transition_package as audit
from audit_battle_package import unpack
from test_exploration_package import pck
from test_character_package import project


class TransitionPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate=json.loads((audit.ROOT/'reports/transition/candidate.json').read_bytes())
        cls.folder=Path(candidate['directory'])
        cls.raw=(cls.folder/'MAP001-Transition.pck').read_bytes()
        cls.files=unpack(cls.raw)

    def test_real_eight_bundle_delivery(self):
        self.assertTrue(audit.audit(self.folder)['passed'])
        self.assertEqual(len(audit.BUNDLES),8)

    def test_unknown_script_or_source_rejected(self):
        for name in ('extra.gdc','wram-high.bin','source.cue','BIOS.bin','preview.png'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                audit.audit_pck(pck(self.files|{name:b'unknown'}))

    def test_missing_dependency_rejected(self):
        for name in ('transition_core.gdc','event_core.gdc','room_priority.gdshader','transition-pin.json'):
            changed=dict(self.files);del changed[name]
            with self.subTest(name=name),self.assertRaises(ValueError):audit.audit_pck(pck(changed))

    def test_all_eight_pins_remain_locked(self):
        for name in audit.PINS:
            with self.subTest(name=name),self.assertRaises(ValueError):
                audit.audit_pck(pck(self.files|{name:self.files[name]+b' '}))

    def test_other_entry_and_feature_override_rejected(self):
        for feature in ('room_demo','character_demo',''):
            with self.subTest(feature=feature),self.assertRaises(ValueError):
                audit.audit_pck(pck(self.files|{'project.binary':project(feature=feature,extra={'application/run/main_scene.event_demo':'res://event_main.tscn'})}))

    def test_truncated_export_rejected(self):
        with self.assertRaises(ValueError):audit.audit_pck(self.raw[:len(self.raw)//2])

    def test_candidate_cannot_claim_performance(self):
        good={'passed':False,'functional_passed':True,'performance_tested':False,'status':'performance_validation_deferred_by_user'}
        archive=Path('MAP001-Transition-Candidate-Windows-x64.zip')
        audit.validate_candidate(good,archive,True,False)
        for changes in ({'passed':True},{'functional_passed':False},{'performance_tested':True},{'status':'accepted'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):audit.validate_candidate(good|changes,archive,True,False)
        for name,candidate,dirty in [('MAP001-Transition-Windows-x64.zip',True,False),(archive.name,False,False),(archive.name,True,True)]:
            with self.assertRaises(ValueError):audit.validate_candidate(good,Path(name),candidate,dirty)

if __name__=='__main__':unittest.main()
