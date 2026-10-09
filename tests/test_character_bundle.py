"""Package fault fixtures; fixtures do not authorize a runtime character release."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import character_bundle as bundle
import character_animation as animation
import exploration_bundle as scene

ROOT=Path(__file__).resolve().parents[1]


class CharacterBundleContracts(unittest.TestCase):
    def test_complete_mapping_and_upward_anchor(self):
        frames=bundle.expected_frames()
        self.assertEqual(len(frames),20)
        self.assertEqual({f['file'] for f in frames},bundle.PNG_FILES)
        self.assertEqual({tuple(f['anchor']) for f in frames if f['direction']=='up' and f['action']=='walk'},{(16,36)})
        self.assertTrue(all(f['baked_mirror_x']==(f['direction']=='right') for f in frames))

    def test_unknown_trust_and_unverified_presentations_refused(self):
        with self.assertRaises(ValueError): bundle.verify(Path('missing'),'bad',expected_scene_sha='bad')
        with self.assertRaises(ValueError): bundle._presentation({})
        with self.assertRaises(ValueError): bundle._accepted_evidence(scene.encoded({'passed':False}),{})


class CharacterBundleFaultFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required=[bundle.ART/'manifest.json',scene.DEFAULT_OUT/'package.json',ROOT/'reports/character/cardinal-a/frame-000000/wram-high.bin',
            bundle.PROPS_SOURCE/'manifest.json',bundle.FOREGROUND/'manifest.json']
        if not all(p.is_file() for p in required): raise unittest.SkipTest('Local source data absent; package source fault fixtures not run')
        cls.scene_sha=scene.digest(scene.stable_read(scene.DEFAULT_OUT/'package.json'))
        cls.profile=animation.profile_from_snapshot(scene.stable_read(required[2]),scene.stable_read(required[2].with_name('wram-low.bin')))
        foreground,foreground_png,_=bundle.load_foreground(scene.stable_read(bundle.PRESENTATION_INDEX))
        cls.payload={'profile.json':scene.encoded(cls.profile.metadata()),'animation-bank.bin':cls.profile.animation_bank,
            'image-table.bin':cls.profile.image_table,'appearances.json':scene.encoded({'schema':bundle.APPEARANCE_SCHEMA,
                'character_id':'map001_player','frames':bundle.expected_frames()}),
            'nbg-priority-foreground.png':foreground_png,
            'layers.json':scene.encoded({'schema':bundle.LAYER_SCHEMA,'foreground':foreground,'props':bundle.expected_props(),
                'sorting':bundle.SORTING,'omitted_object_slots':[6,7],'shadow_omitted':True})}
        cls.payload.update({name:scene.stable_read(bundle.ART/name) for name in bundle.PNG_FILES})
        cls.payload.update({name:scene.stable_read(bundle.PROPS_SOURCE/name) for name in bundle.PROP_FILES})
        cls.package={'schema':bundle.SCHEMA,'character_id':'map001_player','source_local_only':True,
            'scene_manifest_sha256':cls.scene_sha,'camera':[544,1536],'viewport':[320,224],
            'source':{'seed_sha256':bundle.SEED_SHA,'source_files':bundle.SOURCES,
                'reference_art_manifest_sha256':'a'*64,'animation_validation_sha256':'b'*64,
                'presentation_index_sha256':'d'*64,'foreground_manifest_sha256':'e'*64,'props_manifest_sha256':'f'*64,
                'draw_order_validation_sha256':'1'*64,'map_v1n_sha256':bundle.graphics.MAP_V1N_SHA256,
                'presentation_reports':{r:'c'*64 for r in bundle.ROUTES},
                'capture_manifests':{f'{r}-{n}':scene.digest(f'{r}-{n}'.encode()) for r in bundle.ROUTES for n in 'abc'}},
            'presentation':{'state':'source_draw_and_visibility_verified','delay_profile':bundle.DELAY,
                'scope':bundle.SCOPE}}
        (ROOT/'reports/tmp').mkdir(parents=True,exist_ok=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='character-fault-fixture-',dir=ROOT/'reports/tmp')
        self.folder=Path(self.temp.name)
        self.payload=copy.deepcopy(type(self).payload)
        self.package=copy.deepcopy(type(self).package)
        self.write()

    def tearDown(self): self.temp.cleanup()

    def write(self):
        for name,raw in self.payload.items(): (self.folder/name).write_bytes(raw)
        self.package['files']={n:{'bytes':len(b),'sha256':scene.digest(b)} for n,b in self.payload.items()}
        self.write_manifest()

    def write_manifest(self):
        raw=scene.encoded(self.package)
        (self.folder/'package.json').write_bytes(raw)
        self.pin=scene.digest(raw)

    def verify(self): return bundle.verify(self.folder,self.pin,scene.DEFAULT_OUT,self.scene_sha)

    def test_valid_source_content_fixture(self):
        result=self.verify()
        self.assertTrue(result['passed'])
        self.assertEqual(result['original_frames'],20)

    def test_missing_extra_nested_and_truncated_files_rejected(self):
        for kind in ['missing','extra','nested','truncated']:
            with self.subTest(kind=kind):
                target=self.folder/'down-idle.png'
                if kind=='missing': target.unlink()
                elif kind=='extra': (self.folder/'extra.bin').write_bytes(b'x')
                elif kind=='nested': (self.folder/'nested').mkdir()
                else: target.write_bytes(b'\x89PNG')
                with self.assertRaises((ValueError,OSError)): self.verify()
                if kind=='extra': (self.folder/'extra.bin').unlink()
                if kind=='nested': (self.folder/'nested').rmdir()
                self.write()

    def test_manifest_tamper_refused_without_repin(self):
        path=self.folder/'package.json'; path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError): self.verify()

    def test_path_escape_wrong_scene_and_unknown_schema_refused_even_if_repinned(self):
        original=copy.deepcopy(self.package)
        for key,value in [('schema','unknown'),('scene_manifest_sha256','d'*64),('camera',[0,0])]:
            self.package=copy.deepcopy(original); self.package[key]=value; self.write_manifest()
            with self.subTest(key=key),self.assertRaises(ValueError): self.verify()
        self.package=copy.deepcopy(original)
        self.package['files']['../escape.png']=self.package['files'].pop('down-idle.png')
        self.write_manifest()
        with self.assertRaises(ValueError): self.verify()

    def test_unknown_profile_bank_and_image_table_refused_even_if_repinned(self):
        original=copy.deepcopy(self.payload)
        for filename in ['profile.json','animation-bank.bin','image-table.bin']:
            self.payload=copy.deepcopy(original)
            if filename.endswith('.json'):
                profile=scene.decoded(self.payload[filename]); profile['schema']='unknown'; self.payload[filename]=scene.encoded(profile)
            else: self.payload[filename]=b'\0'+self.payload[filename][1:]
            self.write()
            with self.subTest(filename=filename),self.assertRaises(ValueError): self.verify()

    def test_wrong_anchor_mirror_pose_and_fractional_metadata_rejected(self):
        for key,value in [('anchor',[16,35.5]),('baked_mirror_x',True),('primary_index',0),('image_index',3)]:
            appearance={'schema':bundle.APPEARANCE_SCHEMA,'character_id':'map001_player','frames':bundle.expected_frames()}
            appearance['frames'][0][key]=value
            self.payload['appearances.json']=scene.encoded(appearance); self.write()
            with self.subTest(key=key),self.assertRaises(ValueError): self.verify()

    def test_wrong_image_dimensions_and_delay_rejected(self):
        import io
        from PIL import Image
        image=Image.new('RGBA',(32,39)); buffer=io.BytesIO(); image.save(buffer,format='PNG')
        self.payload['down-idle.png']=buffer.getvalue(); self.write()
        with self.assertRaises(ValueError): self.verify()
        self.payload=copy.deepcopy(type(self).payload)
        self.package['presentation']['delay_profile']['presented_body_source_sample_lag']=0
        self.write()
        with self.assertRaises(ValueError): self.verify()

    def test_source_alpha_priority_sorting_and_omitted_scope_rejected(self):
        import io
        from PIL import Image
        image=Image.new('RGBA',(32,40),(1,2,3,128)); output=io.BytesIO(); image.save(output,format='PNG')
        self.payload['down-idle.png']=output.getvalue(); self.write()
        with self.assertRaises(ValueError): self.verify()
        self.payload=copy.deepcopy(type(self).payload)
        original=scene.decoded(self.payload['layers.json'])
        for key in ['sorting','priority','omitted']:
            layers=copy.deepcopy(original)
            if key=='sorting': layers['sorting']['objects_before_actor']=False
            elif key=='priority': layers['props'][4]['sprite_priority']=2
            else: layers['omitted_object_slots']=[]
            self.payload['layers.json']=scene.encoded(layers); self.write()
            with self.subTest(key=key),self.assertRaises(ValueError): self.verify()

    def test_build_cannot_bypass_missing_acceptance(self):
        output=self.folder/'unbuilt'
        with patch.object(bundle,'_accepted_evidence',side_effect=ValueError('unresolved visible pixels')):
            with self.assertRaises((ValueError,OSError)):
                bundle.build(output,self.folder/'pin.json',ROOT/'reports/character/absent')
        self.assertFalse(output.exists())


if __name__=='__main__': unittest.main()
