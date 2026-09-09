import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import decode_source_scene as s


class SourceSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(s.WORKSPACE/'work/extract/MAP001.TWN').read_bytes()
        cls.tiles,cls.layout,cls.palette,cls.blocks=s.source_data(raw)

    def test_compact_indices_priority_and_flips(self):
        self.assertEqual(s.pattern_word(0x2312),0x20003890)
        self.assertEqual(s.pattern_word(0x4353),0x40003a98)
        self.assertEqual(s.pattern_word(0x8001),0x80002008)
        for value in [-1,65536,0x0400,0x0800,0x1000]:
            with self.assertRaises(ValueError):s.pattern_word(value)

    def test_source_only_render_and_layout_stride(self):
        image,records=s.render_view(self.tiles,self.layout,self.palette,0)
        self.assertEqual(image.size,(320,224))
        self.assertEqual(len(records),280)
        self.assertEqual(records[0]['world_tile'],[34,96])
        self.assertEqual(records[20]['layout_decoded_offset']-records[0]['layout_decoded_offset'],256)
        self.assertEqual(records[1]['layout_decoded_offset']-records[0]['layout_decoded_offset'],2)

    def test_palette_zero_rgb_is_irrelevant_when_transparent(self):
        for layer in (0,1):
            a,_=s.render_view(self.tiles,self.layout,self.palette,layer)
            b,_=s.render_view(self.tiles,self.layout,b'\xff\xff'+self.palette[2:],layer)
            self.assertEqual(a.tobytes(),b.tobytes())

    def test_dimensions_layer_and_camera_rejected(self):
        for layer,camera in [(2,s.CAMERA),(0,(-16,0)),(0,(1,0)),(0,(2048,0))]:
            with self.assertRaises(ValueError):s.render_view(self.tiles,self.layout,self.palette,layer,camera)
        with self.assertRaises(ValueError):s.render_view(self.tiles,self.layout[:-1],self.palette,0)

    def test_all_visible_patterns_and_prior_viewports_match(self):
        report=s.run()
        self.assertEqual([l['matched_patterns'] for l in report['layers']],[280,280])
        self.assertEqual(report['palette']['matched_nontransparent_bytes'],510)
        self.assertEqual(report['palette']['source_offset'],0x2c420)


if __name__=='__main__':unittest.main()
