import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_movement as p


class MovementProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.twn = (p.WORKSPACE / 'work/extract/TWN.BIN').read_bytes()
        cls.core = (p.WORKSPACE / 'work/extract/0').read_bytes()
        cls.shapes = p.load_shapes(cls.twn, cls.core)

    def actor(self, x=100, y=100, dx=0, dy=0, shape=1, selector=0):
        actor = bytearray(0x70)
        struct.pack_into('>HH', actor, 0, x * 16, y * 16)
        struct.pack_into('>H', actor, 0x0a, selector)
        struct.pack_into('>hh', actor, 0x18, dx, dy)
        actor[0x29] = shape
        return actor

    def run_step(self, actor, flags=None):
        return p.replay_step(actor, bytes(65536) if flags is None else flags, self.shapes)

    def wall(self, axis, cell, mask=0x80):
        flags = bytearray(65536)
        for i in range(256):
            flags[i * 256 + cell if axis == 'x' else cell * 256 + i] = mask
        return flags

    def test_source_hashes_and_shape_records(self):
        self.assertEqual(self.shapes[1], (-192, -96, 64, 384, 192))
        self.assertEqual(self.shapes[6], (-256, -256, 64, 544, 192))
        for target, location in [('twn', 0x1b61a), ('twn', 0x268dc), ('core', 0x13380), ('core', 0x13a48)]:
            changed = bytearray(self.twn if target == 'twn' else self.core)
            changed[location] ^= 1
            with self.assertRaisesRegex(ValueError, 'hash changed'):
                p.load_shapes(changed if target == 'twn' else self.twn, changed if target == 'core' else self.core)

    def test_input_decoder_uses_captured_gate_and_source_table(self):
        self.assertEqual(tuple(self.twn[0x25ef4:0x25f04]), p.DIRECTION_NIBBLES)
        for nibble in range(16):
            actor = self.actor(dx=100, dy=-100)
            struct.pack_into('>H', actor, 0x26, 7)
            out, report = p.replay_input_gate(actor, nibble << 12, 2, 0)
            expected = p.DIRECTION_NIBBLES[nibble]
            self.assertTrue(report['enabled'])
            self.assertEqual(struct.unpack_from('>HH', out, 0x18), (0, 0))
            self.assertEqual(struct.unpack_from('>H', out, 6)[0] & 2, 2 if expected != 255 else 0)
            self.assertEqual(struct.unpack_from('>HH', out, 0x24), (3, expected if expected != 255 else 7))
        for control, disabled, flags in [(0, 0, 0), (1, 0, 0), (2, 255, 0), (2, 0, 4)]:
            actor = self.actor(dx=32, dy=32)
            struct.pack_into('>H', actor, 6, flags | 2)
            out, report = p.replay_input_gate(actor, 0x8000, control, disabled)
            self.assertFalse(report['enabled'])
            self.assertEqual(struct.unpack_from('>HH', out, 0x18), (0, 0))
            self.assertEqual(struct.unpack_from('>H', out, 0x24)[0], 0)

    def test_velocity_table_covers_all_speeds_and_headings(self):
        for speed in range(6):
            source = struct.unpack_from('>16h', self.twn, 0x2678c + speed * 32)
            for heading in range(8):
                actor = self.actor()
                struct.pack_into('>HH', actor, 0x24, speed, heading)
                for flags in [0, 1]:
                    struct.pack_into('>H', actor, 8, flags)
                    out = p.replay_velocity(actor)
                    self.assertEqual(struct.unpack_from('>hh', out, 0x18), (source[heading], source[8 + heading]))
                    animation_table = 0x26894 if flags else 0x268bc
                    animation_pointer = struct.unpack_from('>I', self.twn, animation_table + speed * 4)[0]
                    animation_index = heading if flags else heading // 2
                    source_animation = struct.unpack_from('>H', self.twn,
                        animation_pointer - 0x06090000 + animation_index * 2)[0]
                    self.assertEqual(struct.unpack_from('>H', out, 0x36)[0], source_animation)

    def test_new_probe_apis_reject_uncaptured_or_out_of_table_values(self):
        for pad, control, disabled in [(-1, 2, 0), (65536, 2, 0), (0, -1, 0), (0, 2, 256)]:
            with self.assertRaises(ValueError):
                p.replay_input_gate(self.actor(), pad, control, disabled)
        for speed, heading in [(6, 0), (0, 8), (65535, 0)]:
            actor = self.actor()
            struct.pack_into('>HH', actor, 0x24, speed, heading)
            with self.assertRaises(ValueError):
                p.replay_velocity(actor)

    def test_free_four_directions_and_center(self):
        for dx, dy, flag in [(16, 0, 8), (-16, 0, 4), (0, 16, 2), (0, -16, 1)]:
            out, report = self.run_step(self.actor(dx=dx, dy=dy))
            self.assertEqual(report['after'], [1600 + dx, 1600 + dy])
            self.assertEqual(report['free_direction_byte'], flag)
            self.assertEqual(out[0x4b], 0)
            self.assertEqual(report['lookups'][-1]['axis'], 'center')
            self.assertEqual(report['global_writes'], [
                {'address': '0x060DDDC4', 'size': 2, 'value': 1600},
                {'address': '0x060DDDC6', 'size': 2, 'value': 1600}])
            self.assertFalse(report['dynamic_verified'])

    def test_four_wall_contacts_snap_to_original_cell_edge(self):
        cases = [('x', 14, 100, 100, 16, 0, 8), ('x', 10, 100, 100, -16, 0, 4),
                 ('y', 13, 100, 98, 0, 16, 2), ('y', 11, 100, 102, 0, -16, 1)]
        for axis, cell, x, y, dx, dy, contact in cases:
            with self.subTest(axis=axis, dx=dx, dy=dy):
                out, report = self.run_step(self.actor(x=x, y=y, dx=dx, dy=dy), self.wall(axis, cell))
                self.assertEqual(report['after'], [x * 16, y * 16])
                self.assertEqual(out[0x4b], contact)
                self.assertEqual(struct.unpack_from('>H', out, 6)[0], 0x200)

    def test_selector_chooses_distinct_masks_not_bit20(self):
        for selector, wall_mask, expected_x in [(0, 0x80, 1600), (1, 0x80, 1616),
                                               (255, 0x40, 1600), (0, 0x40, 1616), (0, 0x20, 1616)]:
            _, report = self.run_step(self.actor(dx=16, selector=selector), self.wall('x', 14, wall_mask))
            self.assertEqual(report['after'][0], expected_x)

    def test_slide_is_queued_once_without_immediate_perpendicular_move(self):
        flags = bytearray(65536)
        flags[12 * 256 + 14] = 0x80
        out, report = self.run_step(self.actor(dx=16), flags)
        self.assertEqual(report['after'], [1600, 1600])
        self.assertEqual(struct.unpack_from('>h', out, 0x20)[0], -16)
        # Top sample occupied, bottom free selects the opposite slide.
        flags[11 * 256 + 14] = 0x80
        out, _ = self.run_step(self.actor(dx=16), flags)
        self.assertEqual(struct.unpack_from('>h', out, 0x20)[0], 16)

    def test_directions_reset_but_opaque_bytes_and_existing_slide_are_preserved(self):
        actor = self.actor()
        actor[0x48] = actor[0x4b] = 0xff
        actor[0x50:] = b'\xa5' * (len(actor) - 0x50)
        struct.pack_into('>H', actor, 6, 0x1200)
        struct.pack_into('>hh', actor, 0x1e, -16, 32)
        out, _ = self.run_step(actor)
        self.assertEqual(out[0x48], 0)
        self.assertEqual(out[0x4b], 0)
        self.assertEqual(out[0x50:], actor[0x50:])
        self.assertEqual(struct.unpack_from('>H', out, 6)[0], 0x1000)
        self.assertEqual(struct.unpack_from('>hh', out, 0x1e), (-16, 32))

    def test_bypass_skips_contacts_but_moves_and_updates_center(self):
        actor = self.actor(dx=16)
        struct.pack_into('>H', actor, 6, 0x220)
        out, report = self.run_step(actor, bytes([0x80]) * 65536)
        self.assertEqual(report['after'], [1616, 1600])
        self.assertEqual(out[0x4b], 0)
        self.assertEqual(out[0x4a], 0x80)
        self.assertEqual(len(report['lookups']), 1)

    def test_center_modes_and_selector_priority(self):
        for initial, center, expected in [(0, 0x20, 0xab13), (1, 0x20, 0xab12),
                                          (1, 0x10, 0xab13), (0, 0x10, 0xab12)]:
            actor = self.actor(selector=initial)
            struct.pack_into('>H', actor, 0x16, 0xabf0)
            flags = bytearray(65536)
            flags[12 * 256 + 12] = center | 0x0c
            out, _ = self.run_step(actor, flags)
            self.assertEqual(struct.unpack_from('>H', out, 0x16)[0], expected)
            self.assertEqual(struct.unpack_from('>H', out, 0x0a)[0], 0)
        out, _ = self.run_step(self.actor(), bytes([8]) * 65536)
        self.assertEqual(struct.unpack_from('>H', out, 0x0a)[0], 255)

    def test_signed_division_and_word_wrap(self):
        self.assertEqual([p.divide16(n) for n in [-17, -16, -15, 15, 16, 17]], [-1, -1, 0, 0, 1, 1])
        actor = self.actor(dx=16)
        struct.pack_into('>H', actor, 0, 65535)
        struct.pack_into('>H', actor, 6, 0x20)
        _, report = self.run_step(actor)
        self.assertEqual(report['after'][0], 15)

    def test_invalid_inputs_fail_closed(self):
        for actor, flags in [(bytes(75), bytes(65536)), (self.actor(), bytes(65535)),
                             (self.actor(shape=7), bytes(65536))]:
            with self.assertRaises(ValueError):
                self.run_step(actor, flags)
        bad = list(self.shapes)
        bad[1] = (0, 0, 0, 0, 0)
        with self.assertRaises(ValueError):
            p.replay_step(self.actor(), bytes(65536), tuple(bad))
        bad[1] = (-192, -96, 64, 385, 192)
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            p.replay_step(self.actor(), bytes(65536), tuple(bad))

    def test_report_never_claims_player_or_dynamic_validation(self):
        report = p.run()
        self.assertFalse(report['player_identity_verified'])
        self.assertFalse(report['collision_verified'])


if __name__ == '__main__':
    unittest.main()
