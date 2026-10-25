"""Source-bound event scheduling tests; UI and rendered acceptance are separate."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from interaction_sequence_reference import Model, Slot
import interaction_animation
import interaction_audio
import event_actor_reference as actor
from interaction_contract import build, convert


class InteractionReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        seed=root/'reports/exploration/e1-nav-05/frame-000600'
        if not (seed/'wram-high.bin').exists():raise unittest.SkipTest('Named source capture absent')
        cls.args=tuple((seed/n).read_bytes() for n in ('wram-high.bin','wram-low.bin'))+tuple(
            (root.parent/'work/extract'/n).read_bytes() for n in ('MAP001.TWN','TWN.BIN'))

    def setUp(self):
        self.m=Model(*self.args)
        self.ready={'resource_loaded':1,'resource_playing':1,'text_active':False}

    def test_fast_text_closure_waits_for_pickup_and_grants_once(self):
        self.m.root=Slot(0x2fb4,'root')
        self.m.step(0,self.ready)
        self.assertEqual(self.m.story,b'\x03')
        self.assertEqual((self.m.disabled,self.m.item_count),(255,0))
        for _ in range(300):
            self.m.step(0,self.ready)
            if not self.m.root.active:break
        self.assertFalse(self.m.root.active)
        self.assertEqual((self.m.disabled,self.m.item_count),(0,1))
        self.assertEqual(actor.word(self.m.spark,6),0)
        self.m.root=Slot(0x2fb4,'root')
        self.m.step(0,self.ready)
        self.assertFalse(self.m.root.active)
        self.assertEqual(self.m.item_count,1)
        self.assertEqual([c[2] for c in self.m.commands],[9,0])

    def test_pickup_end_preserves_last_pose_instead_of_wrapping(self):
        raw=bytearray(self.m.player)
        interaction_animation.select(raw,self.m.profile,24)
        self.assertEqual(actor.word(raw,0x34),35)
        for _ in range(71):self.assertFalse(interaction_animation.wait_step(raw,self.m.profile))
        self.assertTrue(interaction_animation.wait_step(raw,self.m.profile))
        self.assertEqual((actor.word(raw,0x34),actor.word(raw,0x2c),actor.word(raw,0x30)),(38,0,0))

    def test_equipped_branch_and_unknown_wait_are_rejected(self):
        self.m.story=b'\x07'
        with self.assertRaises(ValueError):self.m.dispatch(Slot(0x2f2f,'root'),self.ready)
        with self.assertRaises(ValueError):self.m.wait(Slot(0,'actor',wait=255),self.ready)

    def test_changed_source_is_rejected_and_approved_pages_are_preserved(self):
        source=bytearray(self.args[2]);source[0x2fc3]^=1
        with self.assertRaises(ValueError):convert(bytes(source))
        contract=build()
        self.assertEqual(len(contract['programs']),11)
        self.assertEqual([len(contract['dialogues'][k]['pages']) for k in
            ('map001_00afe2','map001_00b061','map001_00b0b5')],[2,1,2])

    def test_pickup_audio_roundtrips_and_rejects_truncation(self):
        raw=(Path(__file__).resolve().parents[2]/'work/extract/IVENT176.AIF').read_bytes()
        wav,report=interaction_audio.convert(raw)
        self.assertTrue(report['pcm_roundtrip_passed'])
        self.assertEqual(len(wav),28146*2+44)
        with self.assertRaises(ValueError):interaction_audio.convert(raw[:-1])


if __name__=='__main__':unittest.main()
