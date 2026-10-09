"""Contract tests plus optional, source-bound full-loop capture regression."""
import dataclasses
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import exploration_movement as m
from validate_player_trace import validate

ROOT = Path(__file__).resolve().parents[1]
INITIAL = {'x_word':11488, 'y_word':26016, 'status_word':0x8180, 'flags_word':9,
    'selector_word':0, 'mode_word':18, 'dx_word':0, 'dy_word':0, 'slide_x_word':0,
    'slide_y_word':0, 'speed_index':3, 'heading':2, 'shape_index':1, 'animation_index':2,
    'free_direction':0, 'center_flag':1, 'contact_bits':0}


class MovementContractTests(unittest.TestCase):
    def test_raw_field_roundtrip_and_invalid_modes(self):
        self.assertEqual(m.state_from_actor(m.actor_from_state(INITIAL)), INITIAL)
        for key, value in [('shape_index',2), ('speed_index',4), ('flags_word',0),
                           ('heading',8), ('status_word',0x8184), ('x_word',-1),
                           ('contact_bits',256), ('y_word',True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.actor_from_state({**INITIAL, key:value})
        with self.assertRaises(ValueError):
            m.actor_from_state({**INITIAL, 'unconfirmed_field':0})
        with self.assertRaises(ValueError):
            m.state_from_actor(bytes(111))

    def test_invalid_input_is_rejected_before_any_step(self):
        for pad in [0x3000, 0x1001, -1, 65536, True, 'right']:
            with self.subTest(pad=pad), self.assertRaises(ValueError):
                m.step_game_input(INITIAL, pad, None)
        with self.assertRaises(ValueError):
            m.step(INITIAL, 'diagonal', None)

    def test_unknown_scene_cannot_create_a_profile(self):
        with self.assertRaisesRegex(ValueError, 'scene flags'):
            m.MovementProfile(bytes(65536), INITIAL, m.ANIMATION_ROOT_SHA256)
        with self.assertRaisesRegex(ValueError, 'complete synchronous'):
            m.profile_from_snapshot(bytes(8), bytes(8))


class MovementCapturedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = ROOT/'reports/exploration'
        cls.names = ['cardinal-a', 'corners-a', 'open-a', 'release-a']
        if not all((cls.base/name/'manifest.json').is_file() for name in cls.names):
            raise unittest.SkipTest('Local original captures absent; source-backed regression not run')
        cls.high = (cls.base/'cardinal-a/frame-000000/wram-high.bin').read_bytes()
        cls.low = (cls.base/'cardinal-a/frame-000000/wram-low.bin').read_bytes()
        cls.profile = m.profile_from_snapshot(cls.high, cls.low)
        cls.pairs = [validate(cls.base/name) for name in cls.names]

    def test_full_control_loop_matches_all_captured_updates(self):
        self.assertEqual(sum(report['updates_compared'] for report,_ in self.pairs), 560)
        for report, _ in self.pairs:
            self.assertTrue(report['passed'], report['failures'])
            self.assertTrue(report['controlled_actor_identity_verified'])
        self.assertEqual(self.pairs[2][0]['coverage']['contacts'], {'0':118})
        self.assertEqual(self.pairs[1][0]['coverage']['consumed_slide_updates'], 4)
        self.assertEqual(self.pairs[3][0]['coverage']['neutral_slide_updates'], 1)

    def test_boundary_rejects_whole_update_and_keeps_contact_and_heading(self):
        fixture = self.pairs[0][1]
        state = next(row['expected'] for row in fixture['updates'] if row['expected']['contact_bits'] == 4)
        _, proposed = m.step(state, 'right', self.profile)
        indices = frozenset(item['index'] for item in proposed['lookups'])
        outside = next(iter(indices))
        domain = frozenset(range(65536)) - {outside}
        restricted = dataclasses.replace(self.profile, verified_query_indices=domain)
        result, diagnostic = m.step(state, 'right', restricted)
        self.assertEqual(result, state)
        self.assertEqual(result['contact_bits'], 4)
        self.assertFalse(diagnostic['applied'])
        self.assertEqual(diagnostic['reason'], 'test_boundary')
        self.assertIn(outside, diagnostic['unverified_query_indices'])

    def test_slide_queue_consumed_once_and_neutral_does_not_cancel_queue(self):
        # release-a frame 26 queues +32; frame 27 is original neutral input.
        updates = self.pairs[3][1]['updates']
        row = next(row for row in updates if row['expected']['slide_y_word'])
        state = row['expected']
        result, _ = m.step(state, 'none', self.profile)
        self.assertEqual(updates[row['frame']]['game_pad_word'], 0)
        self.assertEqual(result, updates[row['frame']]['expected'])
        self.assertEqual(result['y_word'] - state['y_word'], state['slide_y_word'])
        self.assertEqual(result['slide_y_word'], 0)
        self.assertEqual(result['dy_word'], state['slide_y_word'])
        again, _ = m.step(result, 'none', self.profile)
        self.assertEqual((again['x_word'],again['y_word']), (result['x_word'],result['y_word']))
        self.assertEqual(again['dy_word'], 0)

    def test_reset_and_logical_batching_keep_same_result(self):
        fixture = self.pairs[1][1]
        original_initial = dict(self.profile.initial_state)
        for batch_size in [1, 2, 4, 9]:
            state = dict(self.profile.initial_state)
            updates = fixture['updates']
            for start in range(0, len(updates), batch_size):
                for row in updates[start:start+batch_size]:
                    state, _ = m.step_game_input(state, row['game_pad_word'], self.profile)
                    self.assertEqual(state, row['expected'])
            self.assertEqual(self.profile.initial_state, original_initial)

    def test_source_root_flags_dispatch_and_domain_changes_rejected(self):
        for label, high_offset, low_offset in [('root',0xc8758+0x60,None),
                ('dispatch',0xc8758+0x2b,None), ('slot',0xc27ae,None),
                ('code',0x94afc,None), ('animation',None,0x20078), ('flags',None,0x10000)]:
            high, low = bytearray(self.high), bytearray(self.low)
            if high_offset is not None:
                high[high_offset] ^= 1
            if low_offset is not None:
                low[low_offset] ^= 1
            with self.subTest(label=label), self.assertRaises(ValueError):
                m.profile_from_snapshot(high, low)
        with self.assertRaises(ValueError):
            dataclasses.replace(self.profile, animation_root_sha256='0'*64)
        with self.assertRaises(ValueError):
            dataclasses.replace(self.profile, verified_query_indices=frozenset())


if __name__ == '__main__':
    unittest.main()
