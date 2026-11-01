"""Guard against traversal, source tampering and packaging golden replay data."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unity_source_baseline as baseline

class UnityBaselineTests(unittest.TestCase):
    def test_traversal_rejected(self):
        for name in ('../room.json','a/../b','/absolute','C:/x','a\\b','a//b'):
            with self.subTest(name=name), self.assertRaises(ValueError): baseline.validate_relative(name)
        baseline.validate_relative('room/room.json')

    def test_source_change_rejected(self):
        expected={'a':{'bytes':4,'sha256':'abcd'}}
        for actual in ({},{'a':{'bytes':4,'sha256':'ffff'}},{**expected,'extra':{}}):
            with self.assertRaises(ValueError): baseline.validate_identity(actual,expected)

    def test_replay_not_runtime(self):
        self.assertTrue(all('reference-' not in name for name in baseline.RUNTIME))

if __name__=='__main__': unittest.main()
