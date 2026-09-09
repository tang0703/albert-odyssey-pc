import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import decode_scene_flags as p


def pack(groups):
    return b''.join(struct.pack('>H', len(g)) + b''.join(bytes(r) for r in g) for g in groups)


class SceneFlagsTests(unittest.TestCase):
    def test_group_order_masks_and_skipped_records(self):
        groups = [[(1, 2, 1, 1)] for _ in range(8)]
        grid, result = p.decode_flags(pack(groups))
        self.assertEqual(grid[513], 0xf0)
        self.assertEqual(grid[512], 3)
        self.assertEqual([g['byte_writes'] for g in result], [1, 1, 1, 1, 0, 0, 1, 1])

    def test_zero_dimensions_and_skip_do_not_write(self):
        groups = [[] for _ in range(8)]
        groups[0] = [(255, 255, 0, 255), (255, 255, 255, 0)]
        groups[4] = [(255, 255, 255, 255)]
        grid, _ = p.decode_flags(pack(groups))
        self.assertEqual(grid, bytes([3]) * 65536)

    def test_linear_row_crossing_matches_reader(self):
        groups = [[] for _ in range(8)]
        groups[0] = [(255, 0, 2, 1)]
        grid, _ = p.decode_flags(pack(groups))
        self.assertEqual(grid[254:258], bytes([3, 131, 131, 3]))

    def test_invalid_structure_and_out_of_buffer_rejected(self):
        empty = pack([[] for _ in range(8)])
        for broken in [empty[:-1], empty + b'\0\0', b'\0\1\0']:
            with self.assertRaises(ValueError): p.decode_flags(broken)
        groups = [[] for _ in range(8)]
        groups[6] = [(255, 255, 2, 1)]
        with self.assertRaises(ValueError): p.decode_flags(pack(groups))

    def test_reader_mutations_fail_closed(self):
        code = (p.WORKSPACE / 'work/extract/TWN.BIN').read_bytes()
        p.verify_reader(code)
        for offset in [0x1e35c, 0x1e478, 0x1e4ec, 0x1e51a, 0x1e560, 0x1f6c]:
            altered = bytearray(code)
            altered[offset] ^= 1
            with self.assertRaises(ValueError): p.verify_reader(altered)
        with self.assertRaises(ValueError): p.verify_reader(code[:100])

    def test_full_source_replay_matches_pinned_snapshot(self):
        result = p.run()
        self.assertEqual(result['exact_match_bytes'], 65536)
        self.assertEqual(result['different_bytes'], 0)
        self.assertEqual(result['decoded_sha256'], '78863dedbf02a07158821486a059af56f31a0b18d11a9eee6a7986dd10943e5b')
        self.assertEqual([g['count'] for g in result['groups']], [433, 0, 20, 0, 1, 0, 477, 0])
        self.assertFalse(result['collision_verified'])


if __name__ == '__main__': unittest.main()
