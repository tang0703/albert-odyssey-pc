"""Guard translation identity, bounded conversion and observer equivalence."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from event_contract import build,convert,PROGRAMS
from verify_event_capture_links import compare_outputs
from event_pixel_reference import dialogue_window
import struct


class EventContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[2]/'work/extract/MAP001.TWN'
        if not path.exists():raise unittest.SkipTest('Local source unavailable')
        cls.source=path.read_bytes()

    def test_each_bounded_script_is_converted_without_holes(self):
        programs=convert(self.source)
        self.assertEqual(sum(map(len,programs.values())),35)
        for name,rows in programs.items():
            cursor,end=PROGRAMS[name]
            for row in rows:
                self.assertEqual(row['source']['offset'],cursor)
                cursor+=row['source']['span']
            self.assertEqual(cursor,end)
        self.assertEqual(programs['entry'][0]['args']['next_program'],'main')
        self.assertEqual([r['args']['program'] for r in programs['main'] if r['action']=='attach_player'],['expression','retreat'])

    def test_changed_or_truncated_sources_are_rejected(self):
        with self.assertRaises(ValueError):convert(self.source[:-1])
        source=bytearray(self.source);source[0x2f3c]^=1
        with self.assertRaises(ValueError):convert(bytes(source))

    def test_existing_translation_ids_and_page_order_are_preserved(self):
        result=build();pages=result['dialogue']['pages']
        self.assertEqual([p['id'] for p in pages],['map001_00afe2_p01','map001_00afe2_p02'])
        self.assertEqual([p['zh_tw'] for p in pages],['嗨，瞌睡蟲！你在做什麼，夢遊嗎？','別丟下我一個人。我發誓要保護你，記得嗎？'])
        self.assertEqual(result['dialogue']['speaker'],'CIRRUS')
        self.assertFalse(result['acceptance'])

    def test_render_observer_must_preserve_all_shared_binary_samples(self):
        baseline={'frame-000000/wram-high.bin':'a','frame-000008/video-rgba.bin':'b'}
        self.assertEqual(len(compare_outputs(baseline,baseline)),2)
        with self.assertRaises(ValueError):compare_outputs(baseline|{'frame-000000/wram-high.bin':'x'},baseline)
        with self.assertRaises(ValueError):compare_outputs(baseline,{'frame-000000/wram-high.bin':'a'})
        with self.assertRaises(ValueError):compare_outputs({},baseline)

    def test_dialogue_window_mask_is_bounded_and_uses_inclusive_source_edges(self):
        table=bytearray(struct.pack('>HH',640,642)*224)
        self.assertEqual(int(dialogue_window(table).sum()),0)
        for y in range(40,56):struct.pack_into('>HH',table,y*4,56,584)
        mask=dialogue_window(table)
        self.assertEqual(int(mask.sum()),4240)
        self.assertTrue(mask[40,28]);self.assertTrue(mask[55,292]);self.assertFalse(mask[40,293])
        with self.assertRaises(ValueError):dialogue_window(table[:-1])
        struct.pack_into('>HH',table,100*4,56,584)
        with self.assertRaises(ValueError):dialogue_window(table)


if __name__=='__main__':unittest.main()
