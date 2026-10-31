import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from enhanced25d_projection import project_raw,inverse_raw,viewport,validate_art_grid


class ProjectionTests(unittest.TestCase):
    def test_source_fraction_and_nonstretch(self):
        for w,h in [(1920,1080),(2560,1440),(3840,2160)]:
            for raw in [(8192,24576),(11489,26017),(15359,28671)]:
                actual=inverse_raw(*project_raw(*raw,w,h),w,h)
                for a,b in zip(raw,actual): self.assertAlmostEqual(a,b,8)
            p=project_raw(11488,26016,w,h)
            px=project_raw(11504,26016,w,h); py=project_raw(11488,26032,w,h)
            self.assertAlmostEqual(px[0]-p[0],py[1]-p[1],8)
            self.assertGreaterEqual(viewport(w,h)[0],0)

    def test_reject_bad_input(self):
        for w,h in [(0,1),(-1,10),(math.inf,20),(10,math.nan)]:
            with self.assertRaises(ValueError): viewport(w,h)
        for raw in [(1.5,20),(True,20),(32768,20)]:
            with self.assertRaises(ValueError): project_raw(*raw,1920,1080)

    def test_no_folded_art_warp(self):
        validate_art_grid([0,126,448],[0,128,448],448)
        for a,b in [([0,126,448],[0,448]),([0,126,448],[0,0,448]),([0,448],[0,449])]:
            with self.assertRaises(ValueError): validate_art_grid(a,b,448)


if __name__=='__main__': unittest.main()
