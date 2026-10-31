import hashlib
import json
from pathlib import Path
import sys
import unittest
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from export_enhanced25d import external_files
ART=ROOT/'art/enhanced25d/v1'
ANIMATION=ART/'animation-candidate-03'

class EnhancedArtTests(unittest.TestCase):
    def test_approval_and_source_hashes(self):
        approval=json.loads((ART/'approval.json').read_bytes())
        self.assertTrue(approval['approved'])
        self.assertEqual(approval['character_height_world'],36)
        for r in approval['references'].values():
            self.assertEqual(hashlib.sha256((ART/r['file']).read_bytes()).hexdigest(),r['sha256'])
        data=json.loads((ANIMATION/'animation.json').read_bytes())
        for name,r in data['sources'].items():
            self.assertEqual(hashlib.sha256((ART/name).read_bytes()).hexdigest(),r['sha256'])

    def test_all_52_frames_and_atlas_cells(self):
        data=json.loads((ANIMATION/'animation.json').read_bytes())
        self.assertEqual(len(data['frames']),52)
        identities=set()
        for r in data['frames']:
            im=Image.open(ANIMATION/r['file'])
            self.assertEqual(im.mode,'RGBA');self.assertEqual(im.size,(512,512))
            box=im.getchannel('A').getbbox()
            self.assertGreaterEqual(min(box[0],box[1],512-box[2],512-box[3]),8)
            self.assertEqual(r['ground_anchor'],[256,448])
            atlas=Image.open(ANIMATION/r['atlas']);self.assertEqual(atlas.size,(2048,2048))
            x,y,w,h=r['rect'];self.assertEqual(atlas.crop((x,y,x+w,y+h)).tobytes(),im.tobytes())
            identities.add(hashlib.sha256(im.tobytes()).hexdigest())
        self.assertEqual(len(identities),52)
        for direction in ['down','left','right','up']:
            atlas=Image.open(ANIMATION/'atlases'/f'{direction}.png')
            for i in [13,14,15]: self.assertIsNone(atlas.crop((i%4*512,i//4*512,i%4*512+512,i//4*512+512)).getchannel('A').getbbox())

    def test_phase_intervals_preserve_40_updates(self):
        data=json.loads((ANIMATION/'animation.json').read_bytes())
        self.assertEqual(data['phase']['cycle_updates'],40)
        self.assertEqual([sum(p*3//10==i for p in range(40)) for i in range(12)],[4,3,3]*4)
        self.assertFalse(data['phase']['changes_logic_clock'])
        self.assertEqual(sum(r['kind']=='primary' for r in data['frames']),16)
        self.assertEqual(sum(r['kind']=='transition' for r in data['frames']),32)

    def test_closed_bundle_preserves_nine_dependencies(self):
        files=external_files()
        self.assertEqual(len({n.split('/')[0] for n in files}),10)
        self.assertIn('enhanced25d/player-down.png',files)
        self.assertFalse(any('savestate' in n or n.endswith('.iso') for n in files))

if __name__=='__main__': unittest.main()
