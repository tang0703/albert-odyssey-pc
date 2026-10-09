"""Synthetic HD contract faults. These fixtures never authorize production art."""
import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import character_hd_bundle as hd
import exploration_bundle as common

def image_bytes(image):
    stream=io.BytesIO(); image.save(stream,format='PNG'); return stream.getvalue()

def fixture():
    payload={}; rows=[]
    atlases={d:Image.new('RGBA',(2048,2048)) for d in hd.DIRECTIONS}
    for i,base in enumerate(hd.expected_frames()):
        image=Image.new('RGBA',(512,512)); draw=ImageDraw.Draw(image)
        draw.rectangle((180+i%13,64,320,447),fill=(20+i*3,120,180,255))
        payload[base['file']]=image_bytes(image)
        atlases[base['direction']].paste(image,tuple(base['rect'][:2]))
        rows.append({**base,'ground_anchor':[256,448],'actor_anchor':[256.0,414.25],'display_scale':0.0875})
    payload.update({d+'-atlas.png':image_bytes(im) for d,im in atlases.items()})
    payload['appearances.json']=common.encoded({'schema':hd.APPEARANCE_SCHEMA,'character_id':'map001_player_hd','timing':hd.TIMING,'frames':rows})
    package={'schema':hd.SCHEMA,'character_id':'map001_player_hd','source_local_only':True,'state':'approved_52_frames',
      'scene_manifest_sha256':'a'*64,'source_character_manifest_sha256':'b'*64,
      'source':{'art_manifest_sha256':'c'*64,'draft_approval_record_sha256':'d'*64,'approved_drafts':hd.DRAFTS,'art_review_status':'approved'}}
    package['files']={n:{'bytes':len(b),'sha256':common.digest(b)} for n,b in payload.items()}
    return package,payload

class HDContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base,cls.raw=fixture()
        (hd.ROOT/'reports/tmp').mkdir(parents=True,exist_ok=True)

    def setUp(self):
        self.package=copy.deepcopy(self.base); self.payload=copy.deepcopy(self.raw)

    def repin(self):
        self.package['files']={n:{'bytes':len(b),'sha256':common.digest(b)} for n,b in self.payload.items()}

    def verify(self):
        return hd.validate_payload(self.package,self.payload,'a'*64,'b'*64)

    def test_complete_contract(self):
        self.assertEqual(self.verify()['frame_count'],52)
        self.assertEqual(len(hd.FILES),58)
        self.assertEqual([r['cell'] for r in hd.expected_frames() if r['action']=='idle'],[12]*4)

    def test_draft_unknown_schema_and_source_versions(self):
        for key,value in [('schema','unknown'),('state','draft'),('scene_manifest_sha256','e'*64),('source_character_manifest_sha256','e'*64),('source_local_only',False)]:
            self.package=copy.deepcopy(self.base); self.package[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): self.verify()

    def test_unapproved_art_and_unknown_draft(self):
        for key,value in [('art_review_status','pending'),('art_manifest_sha256','bad'),('approved_drafts',{}),('draft_approval_record_sha256',None)]:
            self.package=copy.deepcopy(self.base); self.package['source'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): self.verify()

    def test_missing_extra_escape_truncation_and_hash(self):
        for mode in ['missing','extra','escape','truncated','hash']:
            self.package=copy.deepcopy(self.base); self.payload=copy.deepcopy(self.raw)
            if mode=='missing': del self.payload['down-walk-00.png']
            elif mode=='extra': self.payload['draft.png']=b'x'
            elif mode=='escape': self.payload['../down.png']=self.payload.pop('down-walk-00.png'); self.repin()
            elif mode=='truncated': self.payload['down-walk-00.png']=b'\x89PNG'
            else: self.package['files']['down-walk-00.png']['sha256']='f'*64
            with self.subTest(mode=mode),self.assertRaises(ValueError): self.verify()

    def test_geometry_timing_and_metadata_errors(self):
        for field,value in [('actor_anchor',[256,700]),('ground_anchor',[256,447]),('display_scale',float('nan')),('display_scale',True),('cell',1),('primary_source_index',True),('rect',[0,0,511,512]),('file','../bad.png')]:
            appearances=common.decoded(self.raw['appearances.json']); appearances['frames'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): hd.validate_appearances(appearances)
        appearances=common.decoded(self.raw['appearances.json']); appearances['timing']['cycle_updates']=36
        with self.assertRaises(ValueError): hd.validate_appearances(appearances)

    def test_missing_pose_and_reordered_pose(self):
        appearances=common.decoded(self.raw['appearances.json']); appearances['frames'].pop()
        with self.assertRaises(ValueError): hd.validate_appearances(appearances)
        appearances=common.decoded(self.raw['appearances.json']); appearances['frames'][0],appearances['frames'][1]=appearances['frames'][1],appearances['frames'][0]
        with self.assertRaises(ValueError): hd.validate_appearances(appearances)

    def test_wrong_image_size_and_alpha(self):
        for size,color in [((511,512),(0,0,0,0)),((512,512),(0,0,0,0)),((512,512),(1,2,3,255))]:
            self.payload=copy.deepcopy(self.raw); self.payload['down-walk-00.png']=image_bytes(Image.new('RGBA',size,color)); self.repin()
            with self.subTest(size=size,color=color),self.assertRaises(ValueError): self.verify()

    def test_atlas_pixel_mismatch_empty_cells_and_duplicate_still(self):
        for mode in ['mismatch','unused','duplicate']:
            self.payload=copy.deepcopy(self.raw)
            atlas=hd.png(self.payload['down-atlas.png'],(2048,2048))
            if mode=='mismatch': atlas.putpixel((200,200),(1,2,3,4))
            elif mode=='unused': atlas.putpixel((1536,1536),(1,0,0,0))
            else:
                self.payload['down-walk-01.png']=self.payload['down-walk-00.png']
                atlas.paste(hd.png(self.payload['down-walk-00.png'],(512,512)),(512,0))
            self.payload['down-atlas.png']=image_bytes(atlas); self.repin()
            with self.subTest(mode=mode),self.assertRaises(ValueError): self.verify()

    def test_exact_files_manifest_pin_and_unlisted_directory(self):
        with tempfile.TemporaryDirectory(dir=hd.ROOT/'reports/tmp',prefix='hd-contract-') as directory:
            folder=Path(directory)
            for n,b in self.payload.items(): (folder/n).write_bytes(b)
            manifest=common.encoded(self.package); (folder/'package.json').write_bytes(manifest); identity=common.digest(manifest)
            with patch.object(hd.source,'verify',return_value={'passed':True}):
                self.assertTrue(hd.verify(folder,identity,expected_scene_sha='a'*64,expected_source_character_sha='b'*64)['passed'])
                (folder/'package.json').write_bytes(manifest+b' ')
                with self.assertRaises(ValueError): hd.verify(folder,identity,expected_scene_sha='a'*64,expected_source_character_sha='b'*64)
            (folder/'package.json').write_bytes(manifest)
            (folder/'unknown').mkdir()
            with self.assertRaises(ValueError): hd.exact_files(folder)

    def test_missing_final_manifest_or_untrusted_hash_never_builds(self):
        with self.assertRaises(ValueError): hd.build(Path('missing'),None)
        with self.assertRaises((ValueError,FileNotFoundError)): hd.build(Path('missing'),'a'*64)
        with self.assertRaises(ValueError): hd._art_file(Path('.'),'../escape.png')
        with self.assertRaises(ValueError): hd.verify(Path('missing'),'a'*64)

    def test_art_source_binding_cannot_rebind_to_current_pins(self):
        with tempfile.TemporaryDirectory(dir=hd.ROOT/'reports/tmp',prefix='hd-pins-') as directory:
            folder=Path(directory); scene_pin=folder/'scene-pin.json'; source_pin=folder/'source-pin.json'
            scene_pin.write_bytes(common.encoded({'schema':'ao_pc_exploration_bundle_pin_v1','manifest_sha256':'a'*64}))
            source_pin.write_bytes(common.encoded({'schema':'ao_pc_character_bundle_pin_v1','manifest_sha256':'b'*64,'scene_manifest_sha256':'a'*64}))
            art={'scene_manifest_sha256':'a'*64,'source_character_manifest_sha256':'b'*64}
            with patch.object(hd.scene,'DEFAULT_PIN',scene_pin),patch.object(hd.source,'DEFAULT_PIN',source_pin):
                scene_sha,source_sha,snapshots=hd._bound_sources(art)
                self.assertEqual((scene_sha,source_sha),('a'*64,'b'*64))
                for field in art:
                    changed={**art,field:'e'*64}
                    with self.subTest(field=field),self.assertRaisesRegex(ValueError,'bindings differ'): hd._bound_sources(changed)
                for field in art:
                    absent={k:v for k,v in art.items() if k!=field}
                    with self.subTest(absent=field),self.assertRaises(ValueError): hd._bound_sources(absent)
                source_pin.write_bytes(common.encoded({'schema':'ao_pc_character_bundle_pin_v1','manifest_sha256':'b'*64,'scene_manifest_sha256':'e'*64}))
                with self.assertRaisesRegex(ValueError,'bindings differ'): hd._bound_sources(art)
                with self.assertRaisesRegex(ValueError,'changed during'): hd._unchanged_pins(snapshots)

    def test_fresh_publication_and_exact_idempotence_never_rewrites(self):
        with tempfile.TemporaryDirectory(dir=hd.ROOT/'reports/tmp',prefix='hd-publish-') as directory:
            folder=Path(directory); output=folder/'bundle'; pin=folder/'hd-pin.json'; manifest=common.encoded(self.package)
            with patch.object(hd.source,'verify',return_value={'passed':True}):
                result=hd._publish(output,pin,self.payload,manifest,'a'*64,'b'*64,{})
                self.assertTrue(result['passed']); hd.exact_files(output)
                before={p:p.stat().st_mtime_ns for p in [pin,*output.iterdir()]}
                with patch.object(Path,'write_bytes',side_effect=AssertionError('idempotent build must not write')):
                    self.assertEqual(result,hd._publish(output,pin,self.payload,manifest,'a'*64,'b'*64,{}))
                self.assertEqual(before,{p:p.stat().st_mtime_ns for p in before})
                old={p:p.read_bytes() for p in before}
                changed=copy.deepcopy(self.package); changed['source']['art_manifest_sha256']='e'*64
                with self.assertRaisesRegex(ValueError,'Existing HD output differs'):
                    hd._publish(output,pin,self.payload,common.encoded(changed),'a'*64,'b'*64,{})
                self.assertEqual(old,{p:p.read_bytes() for p in old})

    def test_staging_failure_never_publishes_partial_package(self):
        with tempfile.TemporaryDirectory(dir=hd.ROOT/'reports/tmp',prefix='hd-stage-') as directory:
            folder=Path(directory); output=folder/'bundle'; pin=folder/'hd-pin.json'
            with patch.object(hd,'verify',side_effect=ValueError('injected verification failure')):
                with self.assertRaisesRegex(ValueError,'injected'):
                    hd._publish(output,pin,self.payload,common.encoded(self.package),'a'*64,'b'*64,{})
            self.assertFalse(output.exists()); self.assertFalse(pin.exists())
            self.assertEqual(len(list(folder.glob('bundle.staging-*'))),1)

    def test_changed_source_pin_during_staging_prevents_publication(self):
        with tempfile.TemporaryDirectory(dir=hd.ROOT/'reports/tmp',prefix='hd-pin-change-') as directory:
            folder=Path(directory); output=folder/'bundle'; pin=folder/'hd-pin.json'; source_pin=folder/'source-pin.json'
            source_pin.write_bytes(b'old')
            def changed(*args):
                source_pin.write_bytes(b'new')
                return {'passed':True}
            with patch.object(hd,'verify',side_effect=changed),self.assertRaisesRegex(ValueError,'changed during'):
                hd._publish(output,pin,self.payload,common.encoded(self.package),'a'*64,'b'*64,{source_pin:b'old'})
            self.assertFalse(output.exists()); self.assertFalse(pin.exists())

    def test_existing_untrusted_output_or_orphan_pin_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=hd.ROOT/'reports/tmp',prefix='hd-prior-') as directory:
            folder=Path(directory); output=folder/'bundle'; pin=folder/'hd-pin.json'
            pin.write_bytes(b'prior trusted pin')
            with self.assertRaisesRegex(ValueError,'Existing HD pin without output'):
                hd._publish(output,pin,self.payload,common.encoded(self.package),'a'*64,'b'*64,{})
            self.assertEqual(pin.read_bytes(),b'prior trusted pin')
            output.mkdir(); (output/'user-file').write_bytes(b'prior data')
            with self.assertRaisesRegex(ValueError,'58 approved files'):
                hd._publish(output,pin,self.payload,common.encoded(self.package),'a'*64,'b'*64,{})
            self.assertEqual((output/'user-file').read_bytes(),b'prior data')

if __name__=='__main__': unittest.main()
