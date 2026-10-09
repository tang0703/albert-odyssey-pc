"""Camera arithmetic and event-boundary failure contracts, independent of UI."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import room_camera as c
import room_boundaries as b


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.profile = c.CameraProfile(128, (8192, 24576, 10240, 25088), 0)
        self.state = dict(x=8704, y=24576, display_x=8704, display_y=24576,
                          dx=0, dy=0, offset_x=0, offset_y=0)

    def test_deadzone_edges_and_display_copy(self):
        for point in ((10880,25984), (11904,27008)):
            self.assertEqual(c.step(self.state, point, self.profile), self.state)
        new = c.step(self.state, (11936,27040), self.profile)
        self.assertEqual((new['x'],new['y'],new['dx'],new['dy']), (8736,24608,32,32))
        self.assertEqual((new['display_x'],new['display_y']), (8704,24576))

    def test_clamp_clears_source_delta_when_exceeded(self):
        state = self.state | {'x':10224,'y':25072}
        new = c.step(state, (15000,30000), self.profile)
        self.assertEqual((new['x'],new['y'],new['dx'],new['dy']), (10240,25088,0,0))
        state = self.state | {'x':8208}
        new = c.step(state, (9000,24000), self.profile)
        self.assertEqual((new['x'],new['y'],new['dx'],new['dy']), (8192,24576,0,0))

    def test_source_speed_cap_and_reverse(self):
        new = c.step(self.state, (13000,28000), self.profile)
        self.assertEqual((new['dx'],new['dy']), (128,128))
        reverse = c.step(new, (10000,25000), self.profile)
        self.assertEqual((reverse['dx'],reverse['dy']), (-128,-128))
        self.assertEqual((reverse['x'],reverse['y']), (8704,24576))

    def test_unknown_parameters_and_displacement_rejected(self):
        for args in [(129,(8192,24576,10240,25088),0), (128,(0,0,0,0),0), (128,(8192,24576,10240,25088),1)]:
            with self.assertRaises(ValueError): c.CameraProfile(*args)
        for change in ({'offset_x':1},{'x':True},{'extra':0},{'x':32768}):
            with self.assertRaises(ValueError): c.step(self.state | change,(11488,26016),self.profile)
        with self.assertRaises(ValueError): c.state_from_bytes(bytes(31))


class BoundaryTests(unittest.TestCase):
    def test_inclusive_edges_are_test_boundaries(self):
        record = [{'id':'script','raw_bounds_inclusive':[13568,26368,14080,27136]}]
        for x in (13568,14080):
            for y in (26368,27136): self.assertEqual(b.contacts(record,x,y),['script'])
        for x,y in ((13567,26368),(14081,27136),(13568,26367),(14080,27137)):
            self.assertEqual(b.contacts(record,x,y),[])
        with self.assertRaises(ValueError): b.contacts(record,True,26368)

    def test_local_source_binding_and_corruption(self):
        root = Path(__file__).resolve().parents[1]
        sample = root/'reports/room/survey-perimeter/frame-000000/wram-high.bin'
        if not sample.exists(): self.skipTest('Original room capture absent')
        high=sample.read_bytes();source=(root.parent/'work/extract/MAP001.TWN').read_bytes()
        twn=(root.parent/'work/extract/TWN.BIN').read_bytes()
        records=b.read_boundaries(high,source,twn)
        self.assertEqual(records[1]['event_file_offset'],0x2f22)
        for offset in (0xcb57a,0xc41ee,0xac3e0):
            changed=bytearray(high);changed[offset]^=1
            with self.assertRaises(ValueError):b.read_boundaries(bytes(changed),source,twn)


if __name__ == '__main__': unittest.main()
