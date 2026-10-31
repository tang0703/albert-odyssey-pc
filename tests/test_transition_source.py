import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from transition_source import sources,destination,initialization,landing_contacts
from transition_initialization import fade_step,LandingCameraProfile,initialize_camera,initialize_player


class TransitionFadeTests(unittest.TestCase):
    def test_completion_is_one_tick_after_saturation(self):
        phase,rgb=1,(0,0,0)
        for _ in range(32):phase,rgb=fade_step(phase,rgb)
        self.assertEqual((phase,rgb),(1,(-255,)*3))
        self.assertEqual(fade_step(phase,rgb),(2,(-255,)*3))
        phase=0
        for _ in range(32):phase,rgb=fade_step(phase,rgb)
        self.assertEqual((phase,rgb),(0,(0,)*3))
        self.assertEqual(fade_step(phase,rgb),(2,(0,)*3))

    def test_unknown_fade_and_camera_modes_rejected(self):
        for phase,rgb in ((3,(0,)*3),(0,(-256,)*3),(0,(1,)*3),(2,(-10,)*3)):
            with self.assertRaises(ValueError):fade_step(phase,rgb)
        with self.assertRaises(ValueError):LandingCameraProfile((8192,24576,10240,25088))

    def test_camera_initializer_does_not_keep_old_display(self):
        result=initialize_camera((0x3880,0x7780),LandingCameraProfile((8192,28672,10240,29184)))
        self.assertEqual((result['x'],result['y'],result['display_x'],result['display_y']),(10240,29056,-1,-1))
        with self.assertRaises(ValueError):initialize_camera((0,0),LandingCameraProfile((8192,28672,10240,29184)))


@unittest.skipUnless((ROOT.parent/'work/extract/MAP001.TWN').exists(),'Local original source required')
class TransitionSourceTests(unittest.TestCase):
    def test_destination_is_table_lookup_not_map_filename(self):
        twn,source=sources();d=destination(twn,source)
        self.assertEqual((d['destination_scene_id'],d['resource_map_id'],d['entry_index'],d['script_offset']),(7,1,3,0x1007))

    def test_independent_command_traversal_and_contacts(self):
        twn,source=sources();story=bytes([7])+bytes(127)
        rows=initialization(source,twn,story)
        self.assertEqual(len(rows),39)
        self.assertEqual(rows[-1]['offset'],0x10ea)
        self.assertEqual(sum(r['action']=='spawn_scene_object' for r in rows),8)
        self.assertFalse(any(r['opcode']==0x2d for r in rows))
        self.assertEqual([r['kind'] for r in landing_contacts(source)],[0,2,2])

    def test_source_mutation_and_unverified_branches_rejected(self):
        twn,source=sources()
        changed=bytearray(source);changed[0x1007]=0xff
        with self.assertRaises(ValueError):initialization(bytes(changed),twn,bytes([7])+bytes(127))
        for story in (bytes(128),bytes([15])+bytes(127),bytes([7,8])+bytes(126),bytes([7])+bytes(19)+bytes([2])+bytes(107)):
            with self.assertRaises(ValueError):initialization(source,twn,story)

    def test_initialization_rejects_resource_header_change(self):
        seed=ROOT/'reports/exploration/e1-nav-05/frame-000600'
        if not seed.exists():self.skipTest('Local named seed required')
        import character_animation
        high=(seed/'wram-high.bin').read_bytes();low=(seed/'wram-low.bin').read_bytes()
        profile=character_animation.profile_from_snapshot(high,low)
        player=initialize_player(high,low,profile)
        self.assertEqual(player[:4],bytes.fromhex('38807780'))
        self.assertEqual(int.from_bytes(player[0x24:0x26],'big'),1)
        mutated=bytearray(low);mutated[0x20003]^=1
        with self.assertRaises(ValueError):initialize_player(high,bytes(mutated),profile)


if __name__=='__main__':unittest.main()
