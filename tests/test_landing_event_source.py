import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from landing_event_source import programs, text_records
from transition_source import sources
from transition_objects import Resources, initialize_actor, LandingActorProfile
from landing_event_actor import Profile, pose, forced_step
from event_actor_reference import word, put
from verify_landing_event_l1 import waiting_page


@unittest.skipUnless((ROOT.parent/'work/extract/MAP001.TWN').exists(), 'Local original source required')
class LandingEventSourceTests(unittest.TestCase):
    def test_cursor_at_next_page_does_not_prove_next_page_was_displayed(self):
        pages = text_records()['map001_00b141']['pages']
        raw = bytearray(64); put(raw, 0, 17)
        raw[28:32] = (0x260e0000+pages[1]['offset']-8).to_bytes(4, 'big')
        raw[25] = 1
        self.assertIsNone(waiting_page(raw, pages))
        raw[25] = 8
        self.assertEqual(waiting_page(raw, pages)['id'], pages[0]['id'])
        put(raw, 0, 0)
        self.assertIsNone(waiting_page(raw, pages))

    def test_all_required_text_has_locked_translation_and_source_page_order(self):
        texts = text_records()
        self.assertEqual([len(t['pages']) for t in texts.values()], [5, 3])
        for text in texts.values():
            self.assertEqual(text['speaker'], 'LAIA')
            self.assertTrue(all(p['en'] and p['zh_tw'] and p['playback_allowed'] for p in text['pages']))

    def test_unknown_instruction_and_out_of_program_jump_are_rejected(self):
        twn, source = sources()
        for address, value in ((0x2c26, 0xff), (0x2d04, 0xff)):
            changed = bytearray(source)
            changed[address] = value
            with patch('landing_event_source.sources', return_value=(twn, bytes(changed))):
                with self.assertRaises(ValueError): programs()

    def test_npc_animation_does_not_relax_old_landing_profile(self):
        resources = Resources(bytes([7])+bytes(127))
        raw, old = initialize_actor(resources)
        new = Profile(resources)
        with self.assertRaises(ValueError): old.read_record(7, 0)
        for selector, cursor in ((8, 0), (12, 0), (7, -3), (7, 2), (7, 15)):
            with self.assertRaises(ValueError): new.read_record(selector, cursor)
        with self.assertRaises(ValueError): new.image_pointer(127)
        with self.assertRaises(ValueError): pose(raw, 2, new)
        with self.assertRaises(ValueError): forced_step(raw, 0, 0x2681, new)
        wrong = bytearray(raw); put(wrong, 8, 1)
        with self.assertRaises(ValueError): pose(wrong, 0, new)

    def test_source_move_clamps_without_overshoot_and_keeps_fractional_units(self):
        resources = Resources(bytes([7])+bytes(127))
        raw, _ = initialize_actor(resources)
        profile = Profile(resources)
        put(raw, 0x24, 1); put(raw, 0, 0x2bf8)
        result, done = forced_step(raw, 0, 0x2c00, profile)
        self.assertTrue(done)
        self.assertEqual(word(result, 0), 0x2c00)
        self.assertEqual(word(result, 0x18), 0)
        self.assertEqual(word(result, 0x36), 4)
        self.assertEqual(word(raw, 0), 0x2bf8)


if __name__ == '__main__': unittest.main()
