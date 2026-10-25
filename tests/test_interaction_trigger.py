import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from interaction_trigger import point, hit, requested


class InteractionPointTests(unittest.TestCase):
    def test_collision_shape_projects_all_four_directions(self):
        shape = (-192, -96, 64, 384, 192)
        self.assertEqual([point(1000, 2000, h, shape) for h in (0, 2, 4, 6)],
                         [(1224, 2000), (1000, 2128), (776, 2000), (1000, 1872)])

    def test_inclusive_bounds_and_one_raw_unit_outside(self):
        record = {'bounds': [11856, 27376, 12208, 27648]}
        for p in ((11856, 27376), (12208, 27648)):
            self.assertTrue(hit(record, p))
        for p in ((11855, 27376), (12209, 27648), (11856, 27375), (12208, 27649)):
            self.assertFalse(hit(record, p))

    def test_pressed_confirmation_and_control_lock(self):
        actor = bytearray(112)
        actor[:4] = bytes.fromhex('2f406a70')
        actor[0x26:0x28] = b'\x00\x02'
        record = {'bounds': [11856, 27376, 12208, 27648]}
        for button in (0x200, 0x400):
            self.assertTrue(requested(record, actor, (-192, -96, 64, 384, 192), button, 0))
        for button, disabled in ((0, 0), (0x200, 255), (0x100, 0)):
            self.assertFalse(requested(record, actor, (-192, -96, 64, 384, 192), button, disabled))


if __name__ == '__main__':
    unittest.main()
