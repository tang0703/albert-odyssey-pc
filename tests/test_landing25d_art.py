import unittest
import sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_landing25d_bundle import read,sha,ART,PROJECT

class LandingArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ART/'animation-candidate-01';cls.art=read(cls.folder/'animation.json')
    def test_approval_and_generated_inputs(self):
        a=self.art
        self.assertEqual(a['approval_sha256'],sha(ART/'approval.json'))
        self.assertTrue(read(ART/'approval.json')['approved'])
        for name,r in a['sources'].items(): self.assertEqual(sha(ART/name),r['sha256'])
        for name,r in a['files'].items(): self.assertEqual(sha(self.folder/name),r['sha256'])
    def test_52_complete_transparent_frames_and_exact_atlas(self):
        self.assertEqual(len(self.art['frames']),52)
        self.assertEqual(len({r['canonical_pose_sha256'] for r in self.art['frames']}),52)
        for d in ['down','left','right','up']:
            atlas=Image.open(self.folder/f'atlases/{d}.png');self.assertEqual(atlas.size,(2048,2048))
            rows=[r for r in self.art['frames'] if r['direction']==d]
            self.assertEqual([r['cell'] for r in rows],list(range(13)))
            for r in rows:
                im=Image.open(self.folder/r['file']);self.assertEqual(im.mode,'RGBA');self.assertEqual(im.size,(512,512))
                b=im.getchannel('A').getbbox();self.assertGreaterEqual(min(b[0],b[1],512-b[2],512-b[3]),8)
                self.assertLessEqual(abs(b[3]-448),1);self.assertEqual(r['ground_anchor'],[256,448])
                x,y,w,h=r['rect'];self.assertEqual(im.tobytes(),atlas.crop((x,y,x+w,y+h)).tobytes())
            for i in range(13,16): self.assertIsNone(atlas.crop((i%4*512,i//4*512,i%4*512+512,i//4*512+512)).getchannel('A').getbbox())
    def test_source_cycle_and_object_closure(self):
        data=read(PROJECT/'generated/enhanced25d-landing/appearance.json')
        self.assertEqual(data['phase']['cycle_updates'],48)
        self.assertEqual(len(data['pose_mapping']),9)
        self.assertEqual(len(data['layout']['dynamic_props']),7)
        self.assertEqual(data['layout']['origin'],[512,1792])
        self.assertEqual(len([n for n in data['textures'] if n.startswith('steam-')]),8)
        for i in range(8):
            im=Image.open(PROJECT/f'generated/enhanced25d-landing/steam-{i}.png');b=im.getchannel('A').getbbox()
            self.assertTrue(b);self.assertGreater(min(b[0],b[1],512-b[2],512-b[3]),0)
    def test_ten_inputs_unchanged(self):
        pin=read(PROJECT/'landing25d-pin.json');self.assertEqual(len(pin['dependencies']),10)
        for name,value in pin['dependencies'].items(): self.assertEqual(sha(PROJECT/'generated'/name/'package.json'),value)
        folder=PROJECT/'generated/enhanced25d-landing';manifest=read(folder/'package.json')
        self.assertEqual(sha(folder/'package.json'),pin['manifest_sha256'])
        self.assertEqual({p.name for p in folder.iterdir()},set(pin['files'])|{'package.json'})
        for name,r in manifest['files'].items(): self.assertEqual(sha(folder/name),r['sha256'])

if __name__=='__main__': unittest.main()
