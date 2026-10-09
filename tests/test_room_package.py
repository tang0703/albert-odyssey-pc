"""Corrupt a real local export; never bless placeholders as release artwork."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_room_package as a
from audit_battle_package import unpack
from test_exploration_package import pck
from test_character_package import project

class RoomPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(a.ROOT/'build/room-candidate-initial/MAP001-Room.pck').read_bytes()
        cls.files=unpack(cls.raw)
        cls.pins=a.pins()

    def test_actual_room_pck_has_closed_approved_resource_set(self):
        self.assertEqual(len(a.audit_pck(self.raw,self.pins)),len(self.files))

    def test_unknown_scripts_and_original_ram_are_rejected(self):
        for name in ('extra.gdc','wram-high.bin','source.cue','BIOS.bin','preview.png'):
            with self.subTest(name=name),self.assertRaises(ValueError):a.audit_pck(pck(self.files|{name:b'unapproved'}),self.pins)

    def test_missing_shader_or_changed_pin_is_rejected(self):
        files=dict(self.files);del files['room_priority.gdshader']
        with self.assertRaises(ValueError):a.audit_pck(pck(files),self.pins)
        files=dict(self.files);files['room-pin.json']+=b' '
        with self.assertRaises(ValueError):a.audit_pck(pck(files),self.pins)

    def test_wrong_active_feature_cannot_launch_old_entry(self):
        for feature in ('character_demo','room_demo,character_demo',''):
            files=self.files|{'project.binary':project(feature=feature,extra={'application/run/main_scene.room_demo':'res://room_main.tscn'})}
            with self.assertRaises(ValueError):a.audit_pck(pck(files),self.pins)

    def test_pck_truncation_is_rejected(self):
        with self.assertRaises(ValueError):a.audit_pck(self.raw[:len(self.raw)//2],self.pins)

if __name__=='__main__':unittest.main()
