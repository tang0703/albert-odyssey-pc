import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from transition_draw_order import piece_visible

class DestinationCullingTests(unittest.TestCase):
    def test_source_inclusive_edges(self):
        # Source command culling reaches line 256, beyond the 224-line video.
        for x,y in [(-7,0),(319,0),(0,-7),(0,256)]:
            self.assertTrue(piece_visible({'screen_origin':[x,y],'width':8,'height':8}))
        for x,y in [(-8,0),(320,0),(0,-8),(0,257)]:
            self.assertFalse(piece_visible({'screen_origin':[x,y],'width':8,'height':8}))

if __name__=='__main__':unittest.main()
