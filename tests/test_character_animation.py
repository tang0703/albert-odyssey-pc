"""Source-backed continuous animation regression and contract failures."""
import copy
import dataclasses
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import character_animation as a
import validate_character_animation as validator
from verify_exploration_replay import inspect

ROOT = Path(__file__).resolve().parents[1]


class CharacterContractTests(unittest.TestCase):
    def test_complete_actor_and_known_fields_required(self):
        for size in (0,111,113):
            with self.assertRaises(ValueError):
                a.state_from_actor(bytes(size))
        with self.assertRaises(ValueError):
            a.actor_from_state({})
        with self.assertRaises(ValueError):
            a.step({},'diagonal',None)


class CharacterSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'reports/exploration/cardinal-a'
        if not (cls.folder/'manifest.json').is_file():
            raise unittest.SkipTest('Local original capture is absent; dynamic animation regression not run')
        cls.high=(cls.folder/'frame-000000/wram-high.bin').read_bytes()
        cls.low=(cls.folder/'frame-000000/wram-low.bin').read_bytes()
        cls.profile=a.profile_from_snapshot(cls.high,cls.low)
        cls.pairs=[validator.validate(ROOT/'reports/exploration'/name)
                   for name in ('cardinal-a','corners-a','open-a','release-a')]

    def test_continuous_original_hooks_and_final_snapshots_match(self):
        self.assertEqual(sum(report['updates_compared'] for report,_ in self.pairs),560)
        for report,_ in self.pairs:
            self.assertTrue(report['passed'],report['failures'])
            self.assertFalse(report['later_actor_state_injection'])
            self.assertFalse(report['presentation_verified'])
            self.assertFalse(report['source_bank_each_hook_verified'])
        self.assertEqual(sum(r['coverage']['starts'] for r,_ in self.pairs),13)
        self.assertEqual(sum(r['coverage']['starts_at_second_pose'] for r,_ in self.pairs),13)
        self.assertEqual(sum(r['coverage']['stops_with_retained_timer'] for r,_ in self.pairs),8)

    def test_walk_cycle_is_forty_ticks_and_starts_at_second_source_pose(self):
        state=dict(self.profile.initial_state)
        observed=[]
        for _ in range(41):
            state,diagnostic=a.step(state,'right',self.profile)
            observed.append((state['image_index'],state['animation_timer'],state['animation_cursor']))
            self.assertTrue(state['render_flags_word']&1)
        self.assertEqual([v[0] for v in observed[:40]], [10]*10+[11]*10+[12]*10+[9]*10)
        self.assertEqual(observed[0],(10,0,3))
        self.assertEqual(observed[40],observed[0])
        self.assertEqual([v[1] for v in observed[:40]],list(range(10))*4)

    def test_turn_preserves_phase_and_still_advances_at_duration_boundary(self):
        state=dict(self.profile.initial_state)
        for _ in range(8):
            state,_=a.step(state,'right',self.profile)
        self.assertEqual((state['animation_cursor'],state['animation_timer']),(3,7))
        state,_=a.step(state,'up',self.profile)
        self.assertEqual((state['animation_cursor'],state['animation_timer'],state['image_index']),(3,8,14))
        self.assertFalse(state['render_flags_word']&1)
        state,_=a.step(state,'left',self.profile)
        self.assertEqual((state['animation_cursor'],state['animation_timer'],state['image_index']),(3,9,10))
        state,_=a.step(state,'down',self.profile)
        self.assertEqual((state['animation_cursor'],state['animation_timer'],state['image_index']),(6,0,7))

    def test_stop_keeps_timer_then_restart_uses_cached_idle_duration(self):
        state=dict(self.profile.initial_state)
        for _ in range(8):
            state,_=a.step(state,'right',self.profile)
        stopped,_=a.step(state,'none',self.profile)
        self.assertEqual((stopped['animation_cursor'],stopped['animation_timer'],stopped['animation_duration'],stopped['image_index']),(0,8,1,1))
        restarted,_=a.step(stopped,'left',self.profile)
        self.assertEqual((restarted['animation_cursor'],restarted['animation_timer'],restarted['animation_duration'],restarted['image_index']),(3,0,10,10))
        self.assertFalse(restarted['render_flags_word']&1)
        settled,_=a.step(stopped,'none',self.profile)
        self.assertEqual((settled['animation_cursor'],settled['animation_timer'],settled['animation_duration']),(0,0,1))

    def test_image_pointer_comes_from_image_index_and_mirror_is_record_bit(self):
        right,_=a.step(self.profile.initial_state,'right',self.profile)
        left,_=a.step(self.profile.initial_state,'left',self.profile)
        self.assertNotEqual(right['animation_index'],left['animation_index'])
        self.assertEqual(right['image_index'],left['image_index'])
        self.assertEqual(right['image_pointer'],left['image_pointer'])
        self.assertEqual(right['render_flags_word']&1,1)
        self.assertEqual(left['render_flags_word']&1,0)
        self.assertEqual(right['image_pointer'],self.profile.image_pointer(right['image_index']))

    def test_changed_source_code_bank_image_table_and_roots_rejected(self):
        for high_offset,low_offset in [(0xac0b6,None),(0xac20c,None),(0xac34a,None),
                (0xc8758+0x58,None),(0xc8758+0x60,None),(None,0x20098),(None,0x20158)]:
            high,low=bytearray(self.high),bytearray(self.low)
            if high_offset is not None: high[high_offset]^=1
            if low_offset is not None: low[low_offset]^=1
            with self.subTest(high=high_offset,low=low_offset),self.assertRaises(ValueError):
                a.profile_from_snapshot(high,low)
        changed=bytearray(self.profile.image_table);changed[1]^=1
        with self.assertRaises(ValueError):
            dataclasses.replace(self.profile,image_table=bytes(changed))

    def test_invalid_cache_or_unknown_state_rejected(self):
        for key,value in [('image_pointer',0),('image_index',1),('animation_duration',10),
                ('animation_cursor',256),('animation_timer',10),('animation_root',0),
                ('animation_index',6),('heading',1),('render_flags_word',1),('animation_timer',True)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                a.step({**self.profile.initial_state,key:value},'none',self.profile)
        with self.assertRaises(ValueError):
            self.profile.read_record(2,9)

    def test_boundary_rejects_animation_and_movement_as_one_update(self):
        base=dataclasses.replace(self.profile.movement_profile,verified_query_indices=frozenset({0}))
        limited=dataclasses.replace(self.profile,movement_profile=base)
        state,diagnostic=a.step(limited.initial_state,'right',limited)
        self.assertFalse(diagnostic['applied'])
        self.assertEqual(state,limited.initial_state)

    def test_capture_mismatch_is_not_injected_into_subsequent_predictions(self):
        evidence=copy.deepcopy(inspect(self.folder))
        row=next(r for r in evidence['hooks'] if r['frame']==1 and r['kind']=='return')
        actor=bytearray.fromhex(row['actor_hex']);actor[0x31]=1;row['actor_hex']=actor.hex()
        report,_=validator.validate_evidence(evidence)
        self.assertFalse(report['passed'])
        self.assertEqual(report['mismatched_updates'],1)
        self.assertEqual({r['frame'] for r in report['failures']},{1})

    def test_v2_animation_requires_bank_custody_and_complete_animation_hooks(self):
        evidence=copy.deepcopy(inspect(self.folder))
        evidence['capture']['schema']='ao_ymir_character_capture_v2'
        with self.assertRaisesRegex(ValueError,'source bank watch'):
            validator.validate_evidence(evidence)
        bank=self.low[0x20010:0x20350]
        for row in evidence['hooks']:
            row['watches'].append({'address':0x20220010,'bytes':len(bank),'hex':bank.hex()})
        with self.assertRaisesRegex(ValueError,'Expected one animation/control update'):
            validator.validate_evidence(evidence)

    def test_reset_and_batch_grouping_preserve_original_timing(self):
        updates=self.pairs[1][1]['updates']
        for size in (1,3,7):
            state=dict(self.profile.initial_state)
            for start in range(0,len(updates),size):
                for row in updates[start:start+size]:
                    state,_=a.step_game_input(state,row['game_pad_word'],self.profile)
                    self.assertEqual(state,row['expected'])


if __name__ == '__main__':
    unittest.main()
