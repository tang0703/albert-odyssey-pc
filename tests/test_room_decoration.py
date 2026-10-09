import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import room_decoration as d

class RoomDecorationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.high=(root/'reports/room/decor-east-a/frame-000000/wram-high.bin').read_bytes()
        cls.twn=(root.parent/'work/extract/TWN.BIN').read_bytes()
        cls.map=(root.parent/'work/extract/MAP001.TWN').read_bytes()
        cls.programs=d.profiles(cls.high,cls.twn,cls.map)

    def test_cycle_is_exactly_155_updates_and_static_object_stays_fixed(self):
        for p in self.programs:
            state=p.initial
            for _ in range(155): state=d.step(state,p)
            self.assertEqual(state,p.initial)
        self.assertEqual(d.step(self.programs[0].initial,self.programs[0]),self.programs[0].initial)

    def test_all_sixteen_images_are_reached(self):
        p=self.programs[1];state=p.initial;images=set()
        for _ in range(155):
            state=d.step(state,p);images.add(d.word(state,0x22))
        self.assertEqual(images,set(range(16,32)))

    def test_rejects_changed_source_and_runtime_code(self):
        for which in range(3):
            args=[self.high,self.twn,self.map];changed=bytearray(args[which]);changed[0x9ddb4 if which==0 else 0]^=1;args[which]=bytes(changed)
            with self.assertRaises(ValueError): d.profiles(*args)

    def test_rejects_truncated_and_invalid_cursor(self):
        p=self.programs[1]
        for state in (p.initial[:-1],p.initial[:0x1c]+b'\x00\x01'+p.initial[0x1e:]):
            with self.assertRaises(ValueError): d.step(state,p)

    def test_pointer_changes_only_at_pointer_checkpoint(self):
        p=self.programs[1];state=p.initial
        while d.word(state,0x1e)<5: state=d.step(state,p)
        before=d.step(state,p,before_pointer=True);after=d.step(state,p)
        self.assertEqual(before[:0x30],after[:0x30])
        self.assertEqual(before[0x34:],after[0x34:])
        self.assertEqual(before[0x30:0x34],state[0x30:0x34])
        self.assertNotEqual(before[0x30:0x34],after[0x30:0x34])

if __name__=='__main__': unittest.main()
