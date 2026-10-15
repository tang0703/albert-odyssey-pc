"""Source-bound event timing and rejection boundaries; no UI acceptance claims."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from event_sequence_reference import Model,Slot
import event_effect_reference as effect
import event_camera_reference as camera
import event_actor_reference as actor
import event_audio


class EventReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        seed=root/'reports/exploration/e1-nav-05/frame-000600'
        if not (seed/'wram-high.bin').exists():raise unittest.SkipTest('Named local source capture absent')
        cls.args=((seed/'wram-high.bin').read_bytes(),(seed/'wram-low.bin').read_bytes(),
                  (root.parent/'work/extract/MAP001.TWN').read_bytes(),(root.parent/'work/extract/TWN.BIN').read_bytes())

    def setUp(self):
        self.m=Model(*self.args)
        self.signals={'resource_loaded':0,'resource_playing':0,'text_active':True}

    def test_source_identity_and_unverified_story_branch_are_rejected(self):
        for index,offset in ((2,0),(3,0),(0,0x36938)):
            args=list(self.args);value=bytearray(args[index]);value[offset]^=2;args[index]=bytes(value)
            with self.assertRaises(ValueError):Model(*args)

    def test_wait_expiry_does_not_execute_next_command_in_the_same_update(self):
        slot=Slot(0x1e7f,'actor',wait=0,arg=1)
        self.m.dispatch(slot,self.signals)
        self.assertEqual((slot.wait,slot.arg,slot.pc),(0,0,0x1e7f))
        self.m.dispatch(slot,self.signals)
        self.assertEqual((slot.wait,slot.arg,slot.pc),(None,65535,0x1e7f))
        self.assertTrue(slot.active)
        self.m.dispatch(slot,self.signals)
        self.assertFalse(slot.active)

    def test_device_waits_require_their_distinct_acknowledgements(self):
        for code in (8,15,19):
            slot=Slot(0x2f55,'root',wait=code)
            self.assertFalse(self.m.wait(slot,self.signals))
        loaded=self.signals|{'resource_loaded':1}
        self.assertTrue(self.m.wait(Slot(0,'root',wait=15),loaded))
        self.assertFalse(self.m.wait(Slot(0,'root',wait=19),loaded))
        self.assertTrue(self.m.wait(Slot(0,'root',wait=8),self.signals|{'text_active':False}))

    def test_original_load_timeout_is_over_300_not_at_300(self):
        slot=Slot(0,'root',wait=15,arg=300)
        self.assertFalse(self.m.wait(slot,self.signals))
        self.assertEqual(slot.arg,301)
        self.assertTrue(self.m.wait(slot,self.signals))

    def test_expression_has_a_finite_ninety_update_lifetime(self):
        state=effect.Effect();programs=effect.sequences(self.args[2])
        for _ in range(89):state=effect.step(state,programs)
        self.assertFalse(state.ended)
        state=effect.step(state,programs)
        self.assertTrue(state.ended);self.assertEqual(state.flags,0)
        with self.assertRaises(ValueError):effect.step(state,programs)

    def test_forced_movement_clamps_exactly_and_clears_velocity(self):
        raw=bytearray(self.m.player);actor.put(raw,0,0x3500);actor.put(raw,0x24,1)
        for tick in range(30):
            raw,done=actor.forced_step(raw,0,0x3320,self.m.profile)
            self.assertEqual(done,tick==29)
        self.assertEqual(actor.word(raw,0),0x3320);self.assertEqual(actor.word(raw,0x18),0)

    def test_fixed_camera_moves_without_follow_deadzone(self):
        state=dict(self.m.cameras[0]);state.update(x=0x26a0,y=0x6070,dx=0,dy=0)
        new=camera.step(state,(0x26b0,0x6070),16,True)
        self.assertEqual((new['x'],new['dx']),(0x26b0,16))
        settled=camera.step(new,(0x26b0,0x6070),16,True)
        self.assertEqual((settled['x'],settled['dx']),(0x26b0,0))

    def test_unknown_wait_and_incomplete_device_inputs_stop(self):
        with self.assertRaises(ValueError):self.m.wait(Slot(0,'root',wait=255),self.signals)
        with self.assertRaises(ValueError):self.m.step(0,{})

    def test_original_audio_conversion_preserves_every_pcm_sample(self):
        root=Path(__file__).resolve().parents[2]
        raw=(root/'work/extract/IVENT041.AIF').read_bytes()
        wav,report=event_audio.convert(raw)
        self.assertTrue(report['pcm_roundtrip_passed']);self.assertEqual(report['sample_count'],15324)
        self.assertEqual(len(wav),15324*2+44)
        with self.assertRaises(ValueError):event_audio.convert(raw[:-1])
        with self.assertRaises(ValueError):event_audio.convert(bytes([raw[0]^1])+raw[1:])


if __name__=='__main__':unittest.main()
