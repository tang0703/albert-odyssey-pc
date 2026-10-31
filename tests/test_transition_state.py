import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from transition_reference import Model
from transition_objects import Resources,initialize_objects,step_object


@unittest.skipUnless((ROOT/'generated/equipment/reference/equip-stairs.json').exists(),'Local source fixtures required')
class TransitionStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed=ROOT/'reports/exploration/e1-nav-05/frame-000600'
        source=ROOT.parent/'work/extract'
        cls.model=Model((seed/'wram-high.bin').read_bytes(),(seed/'wram-low.bin').read_bytes(),
                        (source/'MAP001.TWN').read_bytes(),(source/'TWN.BIN').read_bytes())
        fixture=json.loads((ROOT/'generated/equipment/reference/equip-stairs.json').read_bytes())
        for row in fixture['updates']:
            for action in row['equipment']:cls.model.equipment(action)
            inp=row['input']
            cls.model.step(inp['pad'],{k:inp[k] for k in ('resource_loaded','resource_playing','text_active')},inp['pressed'])
        cls.model.step(fixture['terminal']['pad'],{'resource_loaded':0,'resource_playing':0,'text_active':False})

    def loading(self):
        m=copy.deepcopy(self.model)
        for _ in range(33):m.step(0)
        self.assertEqual(m.stage,'loading')
        return m

    def test_no_early_control_or_equipment_and_persistent_state(self):
        m=self.loading()
        original=(m.room.weapon,m.room.item_count,m.room.attack,m.room.story)
        with self.assertRaises(ValueError):m.equipment('remove')
        self.assertTrue(m.scene_resources_ready(m.generation,'map001_scene7_resources'))
        m.step(0x2000)
        for _ in range(32):m.step(0x2000)
        self.assertEqual(m.player[:4],bytes.fromhex('38807780'))
        self.assertEqual(m.stage,'fade_in')
        m.step(0x2000)
        self.assertEqual(m.player[:4],bytes.fromhex('388077a0'))
        self.assertEqual(m.stage,'landing')
        self.assertEqual((m.room.weapon,m.room.item_count,m.room.attack,m.room.story),original)

    def test_stale_duplicate_and_reset_during_pending_load(self):
        m=self.loading();generation=m.generation;before=bytes(m.player)
        self.assertFalse(m.scene_resources_ready(generation-1,'map001_scene7_resources'))
        self.assertFalse(m.scene_resources_ready(generation,'other'))
        self.assertEqual(bytes(m.player),before)
        self.assertTrue(m.scene_resources_ready(generation,'map001_scene7_resources'))
        m.step(0);before=bytes(m.player)
        self.assertFalse(m.scene_resources_ready(generation,'map001_scene7_resources'))
        self.assertEqual(bytes(m.player),before)
        m=self.loading();generation=m.generation;m.reset()
        self.assertFalse(m.scene_resources_ready(generation,'map001_scene7_resources'))
        self.assertEqual((m.stage,m.scene,m.pending,m.objects,m.arrival_actor),('original_room',8,None,[],None))
        self.assertEqual((m.room.story,m.room.weapon,m.room.item_count,m.room.attack),(b'\x01',255,0,10))

    def test_unknown_actor_prototype_or_object_animation_rejected(self):
        resources=Resources(bytes([7])+bytes(127))
        with self.assertRaises(ValueError):resources.prototype(51)
        objects,programs=initialize_objects(resources)
        program=copy.deepcopy(programs[0]);program.sequence=bytes([1,0,128,0])
        with self.assertRaises(ValueError):step_object(objects[0],program)
        changed=bytearray(objects[0]);changed[0x1c:0x1e]=b'\0\1'
        with self.assertRaises(ValueError):step_object(changed,programs[0])


if __name__=='__main__':unittest.main()
