import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from equipment_contract import source_contract, build
from equipment_sequence_reference import Model

@unittest.skipUnless((ROOT/'reports/equipment/q1/equip-stairs-a/manifest.json').exists(),'Local source required')
class EquipmentSourceTests(unittest.TestCase):
    def model(self):
        seed=ROOT/'reports/equipment/q1/equip-stairs-a/frame-000000'
        return Model((seed/'wram-high.bin').read_bytes(),(seed/'wram-low.bin').read_bytes(),
                     (ROOT.parent/'work/extract/MAP001.TWN').read_bytes(),(ROOT.parent/'work/extract/TWN.BIN').read_bytes())

    def test_source_rules_and_terminal(self):
        contract=build()
        self.assertEqual(contract['equipment']['attack_bonus'],5)
        self.assertEqual(contract['programs']['equip_entry'][0]['args']['if_set'],0x2fb2)
        self.assertEqual(contract['programs']['equipped_end'][0]['action'],'end')

    def test_changed_main_rejected(self):
        read=Path.read_bytes
        def changed(path):
            raw=read(path)
            return bytes([raw[0]^1])+raw[1:] if path==ROOT.parent/'work/extract/0' else raw
        with patch.object(Path,'read_bytes',changed),self.assertRaises(ValueError):source_contract()

    def test_unowned_and_unknown_rejected(self):
        m=self.model()
        self.assertFalse(m.equipment('equip'))
        self.assertFalse(m.equipment('remove'))
        with self.assertRaises(ValueError):m.equipment('grant')
        self.assertEqual((m.story,m.weapon,m.item_count,m.attack),(b'\x01',255,0,10))

    def test_conservation_and_sticky_story(self):
        m=self.model();m.story=b'\x03';m.item_count=1
        self.assertTrue(m.equipment('equip'))
        self.assertEqual((m.weapon,m.item_count,m.attack,m.story),(27,0,15,b'\x07'))
        self.assertFalse(m.equipment('equip'))
        self.assertTrue(m.equipment('remove'))
        self.assertEqual((m.weapon,m.item_count,m.attack,m.story),(255,1,10,b'\x07'))
        self.assertFalse(m.equipment('remove'))
        self.assertTrue(m.equipment('equip'))

    def test_event_lock_cannot_equip(self):
        m=self.model();m.story=b'\x03';m.item_count=1;m.disabled=255
        with self.assertRaises(ValueError):m.equipment('equip')
        self.assertEqual((m.weapon,m.item_count,m.story),(255,1,b'\x03'))

if __name__=='__main__':unittest.main()
