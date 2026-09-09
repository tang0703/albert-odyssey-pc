import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import probe_scene_metadata as p


class MetadataTests(unittest.TestCase):
    def test_system_ram_boundaries_and_mutation(self):
        lock=p.read_json(p.PROJECT/'savestate-lock.json')
        data=(p.WORKSPACE/lock['path']).read_bytes()
        low,high,spans=p.system_ram(data,lock)
        self.assertEqual((len(low),len(high)),(0x100000,0x100000))
        self.assertEqual(spans['high_state_offset'],0x1000dd)
        with self.assertRaises(ValueError):p.system_ram(data[:-1],lock)
        broken=bytearray(data);broken[0x2000dd]^=1
        changed=dict(lock,sha256=p.digest(broken))
        with self.assertRaises(ValueError):p.system_ram(broken,changed)

    def test_structural_records_remain_opaque(self):
        rows=p.counted_runs(b'\0\1\x10\x20\0\0\0\0')
        self.assertEqual([r['count'] for r in rows],[1,0])
        self.assertEqual(rows[0]['role'],'unassigned')
        self.assertEqual(rows[0]['zero_c_or_d'],1)
        self.assertTrue(rows[1]['zero_count_or_alignment_ambiguous'])
        for value in [b'\0',b'\0\2\1\2\3\4']:
            with self.assertRaises(ValueError):p.counted_runs(value)

    def test_static_queue_opcodes_and_literals_guarded(self):
        code=(p.WORKSPACE/'work/extract/TWN.BIN').read_bytes()
        self.assertEqual(p.palette_queue_evidence(code)['record_bytes'],6)
        for offset in [0xac4c,0xacf8]:
            broken=bytearray(code);broken[offset]^=1
            with self.assertRaises(ValueError):p.palette_queue_evidence(broken)

    def test_real_block_provenance_without_collision_claim(self):
        result=p.run()
        self.assertEqual(result['block_runtime'],0x060f4000)
        self.assertEqual(result['block_exact_match_bytes'],3740)
        self.assertEqual([r['count'] for r in result['structural_runs']],[433,0,20,0,1,0,477,0])
        self.assertEqual(result['palette_queue']['captured_active_count'],0)
        self.assertFalse(result['collision_verified'])
        self.assertFalse(result['player_coordinate_verified'])


if __name__=='__main__':unittest.main()
