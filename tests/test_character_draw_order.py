"""Synthetic draw-order contract tests; no original game data in Git."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import character_draw_order as model


def row(slot, key, sorted=True):
    return {'slot': slot, 'y_sorted': sorted, 'y_raw': (key - 256) * 16,
            'camera_y_raw': 0}


def piece(name, x=10):
    return {'id': name, 'screen_origin': [x, 20], 'width': 16, 'height': 24,
            'texture_offset': 0x200, 'colr': 0x2720, 'flip_x': False, 'color_mode': 0}


def event(p, address=0x100):
    x, y = p['screen_origin']; w, h = p['width'], p['height']
    words = [2 | (0x10 if p['flip_x'] else 0), 0, p['color_mode'] << 3, p['colr'],
             p['texture_offset'] // 8, (w // 8) * 256 + h,
             x, y, x + w - 1, y, x + w - 1, y + h - 1, x, y + h - 1, 0, 0]
    return {'command_address': address, 'command_hex': struct.pack('>16H', *words).hex()}


class DrawOrderTests(unittest.TestCase):
    def test_equal_key_furniture_before_actor(self):
        got = model.bucket_order([row(1, 100), row(2, 100)], [row(0, 100)])
        self.assertEqual(got['sorted'], [{'kind': 'object', 'slot': 1},
                         {'kind': 'object', 'slot': 2}, {'kind': 'actor', 'slot': 0}])
        self.assertEqual([p['assigned_bucket'] for p in got['placements']], [100, 101, 102])

    def test_collision_is_not_stable_y_sort(self):
        # A lower-key actor arrives after two objects have taken its bucket.
        got = model.bucket_order([row(0, 100), row(1, 100), row(2, 101)], [row(0, 100)])
        self.assertEqual([p['assigned_bucket'] for p in got['placements']], [100, 101, 102, 103])
        self.assertEqual(got['sorted'][-1], {'kind': 'actor', 'slot': 0})

    def test_direct_list_preserves_object_then_actor_slots(self):
        got = model.bucket_order([row(2, 100, False), row(7, 90, False)], [row(0, 70, False)])
        self.assertEqual(got['sorted'], [])
        self.assertEqual([p['slot'] for p in got['unsorted']], [2, 7, 0])

    def test_signed_division_truncates_toward_zero(self):
        self.assertEqual([model.divide16(v) for v in [-17, -16, -15, -1, 0, 15, 16]],
                         [-1, -1, 0, 0, 0, 0, 1])

    def test_bounds_and_overflow_reject(self):
        for key in [39, 701]:
            with self.assertRaisesRegex(ValueError, 'boundary'):
                model.bucket_order([row(0, key)], [])
        with self.assertRaisesRegex(ValueError, 'overflow'):
            model.bucket_order([row(i, 700) for i in range(64)], [row(i, 700) for i in range(5)])

    def test_duplicate_and_unordered_slots_reject(self):
        for items in [[row(1, 100), row(1, 100)], [row(2, 100), row(1, 100)]]:
            with self.assertRaisesRegex(ValueError, 'slots'):
                model.bucket_order(items, [])
        for field, value in [('slot', 64), ('y_sorted', 1), ('y_raw', 1.0), ('camera_y_raw', 40000)]:
            with self.assertRaisesRegex(ValueError, 'input fields'):
                model.bucket_order([row(0, 100) | {field: value}], [])

    def test_priority_clamp_preserves_fifo(self):
        source = [{'id': 'early_high', 'priority': 612}, {'id': 'later_high', 'priority': 1124},
                  {'id': 'body', 'priority': 10}, {'id': 'furniture', 'priority': 10}]
        self.assertEqual([p['id'] for p in model.priority_order(source, 256)],
                         ['body', 'furniture', 'early_high', 'later_high'])
        self.assertEqual(source[0]['id'], 'early_high')
        with self.assertRaises(ValueError): model.priority_order(source, 512)
        with self.assertRaises(ValueError): model.priority_order([{'priority': -1}], 256)

    def test_execution_sequence_not_command_address(self):
        pieces = [piece('first'), piece('second', 30)]
        scene = {'ordered_pieces': pieces, 'body_and_prop_order': ['first', 'second']}
        commands = [event(pieces[0], 0x200), event(pieces[1], 0x100)]
        self.assertEqual(model.compare_commands(scene, commands)['observed_order'], ['first', 'second'])
        with self.assertRaisesRegex(ValueError, 'order differs'):
            model.compare_commands(scene, commands[::-1])

    def test_missing_duplicate_unknown_and_ambiguous_commands_reject(self):
        p = piece('first'); scene = {'ordered_pieces': [p], 'body_and_prop_order': ['first']}
        for commands in [[], [event(p), event(p)], [event(piece('unknown', 100))]]:
            with self.assertRaises(ValueError): model.compare_commands(scene, commands)
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            model.compare_commands({'ordered_pieces': [p, p], 'body_and_prop_order': []}, [event(p)])

    def test_flip_palette_and_mode_are_identity(self):
        p = piece('first'); scene = {'ordered_pieces': [p], 'body_and_prop_order': ['first']}
        for key, value in [('flip_x', True), ('color_mode', 2), ('colr', 0x2760)]:
            changed = p | {key: value}
            with self.assertRaisesRegex(ValueError, 'Unbound'):
                model.compare_commands(scene, [event(changed)])

    def test_shadow_is_explicitly_outside_geometry_proof(self):
        shadow = piece('shadow') | {'colr': 0x27c0}
        got = model.compare_commands({'ordered_pieces': [], 'body_and_prop_order': []}, [event(shadow)])
        self.assertEqual(got['excluded_commands'][0]['reason'], 'shadow_geometry_not_validated')
        p = piece('first')
        with self.assertRaisesRegex(ValueError, 'after a body'):
            model.compare_commands({'ordered_pieces': [p], 'body_and_prop_order': ['first']},
                                   [event(p), event(shadow)])

    def test_changed_source_and_truncated_ram_reject(self):
        with self.assertRaisesRegex(ValueError, 'source identity'):
            model.verify_source(b'changed TWN', b'changed core')
        for high, low in [(b'', b''), (bytes(0x100000), bytes(100))]:
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                model.scene_from_snapshot(high, low)
        with self.assertRaisesRegex(ValueError, 'camera'):
            model.scene_from_snapshot(bytes(0x100000), bytes(0x100000))

    def test_source_memory_alias_and_region_guard(self):
        high = bytes(16); low = bytes(range(16))
        self.assertEqual(model._memory(high, low, 0x20200001, 2), b'\x01\x02')
        self.assertEqual(model._memory(high, low, 0x26000002, 2), b'\0\0')
        for address, size in [(0x1234, 1), (0x2020000f, 2)]:
            with self.assertRaises(ValueError): model._memory(high, low, address, size)


if __name__ == '__main__':
    unittest.main()
