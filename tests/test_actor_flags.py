import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import probe_actor_flags as p


class ActorFlagsTests(unittest.TestCase):
    def test_fraction_cell_and_wrapped_boundaries(self):
        for x, y, expected in [(0, 0, 0), (127, 127, 0), (128, 128, 257),
                               (32767, 32767, 65535), (32768, 32768, 0),
                               (65535, 65535, 65535)]:
            self.assertEqual(p.cell_index(x, y), expected)

    def test_signed_delta_word_overflow_and_preserved_bytes(self):
        actor = bytearray([0xa5] * 40)
        struct.pack_into('>HH', actor, 0, 0, 65535)
        struct.pack_into('>HH', actor, 0x18, 65520, 1)  # -16, +1
        updated, sample = p.update_actor(actor, bytes(65536))
        self.assertEqual(struct.unpack_from('>HH', updated), (65520, 0))
        self.assertEqual(sample['index'], 255)
        for i in range(len(actor)):
            if i not in [0, 1, 2, 3, 8, 9]: self.assertEqual(updated[i], actor[i])

    def test_bit20_sets_and_clears_only_actor_bit1(self):
        actor = bytearray(28)
        struct.pack_into('>H', actor, 8, 0xfffd)
        for flag, expected in [(0, 0xfffd), (0x20, 0xffff), (0x80, 0xfffd), (0xff, 0xffff)]:
            flags = bytearray(65536); flags[0] = flag
            updated, _ = p.update_actor(actor, flags)
            self.assertEqual(struct.unpack_from('>H', updated, 8)[0], expected)
        struct.pack_into('>H', actor, 8, 0xffff)
        updated, _ = p.update_actor(actor, bytes(65536))
        self.assertEqual(struct.unpack_from('>H', updated, 8)[0], 0xfffd)

    def test_mode_guard_and_complete_low_byte_replacement(self):
        for mode, flag, expected in [(0xabf0, 0, 0xab12), (0xabf0, 0x20, 0xab13),
                                      (0xabef, 0x20, 0xabef)]:
            actor = bytearray(28); struct.pack_into('>H', actor, 0x16, mode)
            flags = bytearray(65536); flags[0] = flag
            updated, _ = p.update_actor(actor, flags)
            self.assertEqual(struct.unpack_from('>H', updated, 0x16)[0], expected)

    def test_query_uses_position_after_delta(self):
        actor = bytearray(28)
        struct.pack_into('>HH', actor, 0, 127, 127)
        struct.pack_into('>HH', actor, 0x18, 1, 1)
        flags = bytearray(65536); flags[257] = 0x20
        updated, sample = p.update_actor(actor, flags)
        self.assertEqual(sample['index'], 257)
        self.assertEqual(struct.unpack_from('>H', updated, 8)[0], 2)

    def test_bad_input_and_code_mutation_rejected(self):
        for x, y in [(-1, 0), (0, 65536)]:
            with self.assertRaises(ValueError): p.cell_index(x, y)
        for actor, flags in [(bytes(27), bytes(65536)), (bytes(28), bytes(65535))]:
            with self.assertRaises(ValueError): p.update_actor(actor, flags)
        code = (p.WORKSPACE / 'work/extract/TWN.BIN').read_bytes()
        p.verify_code(code)
        for offset in [0x1bf18, 0x1bfc6, 0x1c054, 0x1b740, 0xe6d4]:
            altered = bytearray(code); altered[offset] ^= 1
            with self.assertRaises(ValueError): p.verify_code(altered)

    def test_source_grid_exhaustive_probe_is_labeled_synthetic(self):
        report = p.run()
        self.assertEqual(report['synthetic_probe_count'], 65536)
        self.assertEqual(report['synthetic_mode_counts'], {'18': 64494, '19': 1042})
        self.assertFalse(report['collision_verified'])
        self.assertFalse(report['player_identity_verified'])


if __name__ == '__main__': unittest.main()
