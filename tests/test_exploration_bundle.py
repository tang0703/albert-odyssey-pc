"""Self-contained fault tests; fixture pixels/flags are synthetic, not game RAM."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import exploration_bundle as b
import exploration_movement as m


class ExplorationBundleTests(unittest.TestCase):
    def setUp(self):
        temporary_root = b.ROOT / 'reports/tmp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='ao-bundle-test-', dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)/'scene'
        self.folder.mkdir()
        flags = bytes(65536)
        patched = patch.object(m, 'FLAGS_SHA256', b.digest(flags))
        patched.start()
        self.addCleanup(patched.stop)
        initial = dict(zip(m.FIELDS, [11488,26016,0x8180,9,0,18,0,0,0,0,3,2,1,2,0,1,0]))
        profile = m.MovementProfile(flags, initial, m.ANIMATION_ROOT_SHA256)
        traces, union = [], set()
        for name in b.LABELS:
            state, updates = dict(initial), []
            for frame in range(1, b.COUNTS[name]+1):
                pad = [0,0x8000,0x2000,0x4000,0x1000][(frame//6)%5]
                state, diagnostic = m.step_game_input(state, pad, profile)
                indices = sorted({row['index'] for row in diagnostic['lookups']})
                union.update(indices)
                updates.append({'frame':frame,'game_pad_word':pad,'expected':state,'query_indices':indices})
            traces.append({'id':name,'label':b.LABELS[name],'initial_state':initial,'updates':updates})
        metadata = profile.metadata()
        metadata['verified_query_indices'] = sorted(union)
        image = io.BytesIO()
        Image.new('RGBA',(320,224),(0,0,0,0)).save(image,format='PNG')
        payload = {'nbg0.png':image.getvalue(),'nbg1.png':image.getvalue(),'flags.bin':flags,
                   'profile.json':b.encoded(metadata),'traces.json':b.encoded(traces)}
        source = {name:'1'*64 for name in b.SOURCE_KEYS-{'capture_manifests'}}
        source.update(code_sha256=m.p.TWN_HASH,core_sha256=m.p.CORE_HASH,
            capture_manifests={name:['2'*64,'3'*64,'4'*64] for name in b.LABELS})
        package = {'schema':b.SCHEMA,'reference_id':'map001-freewalk-20261009',
            'camera':[544,1536],'viewport':[320,224],'source_local_only':True,
            'state':'verified_region_only','source':source,
            'files':{name:{'bytes':len(raw),'sha256':b.digest(raw)} for name,raw in payload.items()}}
        for name,raw in payload.items():
            (self.folder/name).write_bytes(raw)
        (self.folder/'package.json').write_bytes(b.encoded(package))
        self.pin = self.manifest_hash()

    def manifest_hash(self):
        return b.digest((self.folder/'package.json').read_bytes())

    def changed_payload(self,name,value):
        raw = value if isinstance(value,bytes) else b.encoded(value)
        (self.folder/name).write_bytes(raw)
        package = b.decoded((self.folder/'package.json').read_bytes())
        package['files'][name] = {'bytes':len(raw),'sha256':b.digest(raw)}
        (self.folder/'package.json').write_bytes(b.encoded(package))
        return self.manifest_hash()

    def read(self,name):
        return b.decoded((self.folder/name).read_bytes())

    def test_synthetic_bundle_replays_without_original_source_files(self):
        with patch.object(b.reference,'validate',side_effect=AssertionError('No source required during verify')):
            result = b.verify(self.folder,self.pin)
        self.assertTrue(result['passed'])
        self.assertEqual(result['updates_compared'],560)
        self.assertEqual(result['files'],6)

    def test_missing_file_and_unlisted_file_rejected(self):
        path=self.folder/'flags.bin'; raw=path.read_bytes(); path.unlink()
        with self.assertRaisesRegex(ValueError,'six approved'):
            b.verify(self.folder,self.pin)
        path.write_bytes(raw)
        (self.folder/'unexpected.bin').write_bytes(b'unapproved')
        with self.assertRaisesRegex(ValueError,'six approved'):
            b.verify(self.folder,self.pin)

    def test_truncation_and_hash_mismatch_rejected(self):
        path=self.folder/'flags.bin'; raw=path.read_bytes()
        path.write_bytes(raw[:-1])
        with self.assertRaisesRegex(ValueError,'hash or size'):
            b.verify(self.folder,self.pin)
        path.write_bytes(bytes([1])+raw[1:])
        with self.assertRaisesRegex(ValueError,'hash or size'):
            b.verify(self.folder,self.pin)

    def test_manifest_tamper_and_untrusted_pin_rejected(self):
        manifest=self.folder/'package.json'; manifest.write_bytes(manifest.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'trusted pin'):
            b.verify(self.folder,self.pin)
        with self.assertRaisesRegex(ValueError,'trusted manifest'):
            b.verify(self.folder,'')

    def test_unknown_profile_or_shape_rejected_even_with_rehashed_payload(self):
        original=self.read('profile.json')
        for change in [{'schema':'future'}, {'shape_raw':[-1,-1,0,1,1]},
                       {'verified_query_indices':None}, {'unknown':True}, {'disabled_byte':False}]:
            pin=self.changed_payload('profile.json',{**original,**change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                b.verify(self.folder,pin)

    def test_domain_widening_rejected_even_with_rehashed_payload(self):
        profile=self.read('profile.json')
        missing=next(i for i in range(65536) if i not in profile['verified_query_indices'])
        profile['verified_query_indices']=sorted(profile['verified_query_indices']+[missing])
        pin=self.changed_payload('profile.json',profile)
        with self.assertRaisesRegex(ValueError,'exact replay query union'):
            b.verify(self.folder,pin)

    def test_path_escape_manifest_key_rejected_before_any_external_read(self):
        package=self.read('package.json')
        package['files']['../flags.bin']=package['files'].pop('flags.bin')
        (self.folder/'package.json').write_bytes(b.encoded(package))
        with self.assertRaisesRegex(ValueError,'exact allowlist'):
            b.verify(self.folder,self.manifest_hash())

    def test_invalid_png_dimensions_rejected_after_hash_verification(self):
        image=io.BytesIO(); Image.new('RGBA',(319,224)).save(image,format='PNG')
        pin=self.changed_payload('nbg0.png',image.getvalue())
        with self.assertRaisesRegex(ValueError,'320x224'):
            b.verify(self.folder,pin)

    def test_trace_truncation_and_numeric_divergence_rejected(self):
        original=self.read('traces.json')
        changed=self.read('traces.json'); changed[0]['updates'].pop()
        pin=self.changed_payload('traces.json',changed)
        with self.assertRaisesRegex(ValueError,'truncated'):
            b.verify(self.folder,pin)
        original[0]['updates'][0]['expected']['x_word']+=1
        pin=self.changed_payload('traces.json',original)
        with self.assertRaisesRegex(ValueError,'movement diverges'):
            b.verify(self.folder,pin)

    def test_source_code_change_rejected_even_with_new_pin(self):
        package=self.read('package.json'); package['source']['code_sha256']='0'*64
        (self.folder/'package.json').write_bytes(b.encoded(package))
        with self.assertRaisesRegex(ValueError,'Source code identity'):
            b.verify(self.folder,self.manifest_hash())

    def test_duplicate_json_keys_rejected(self):
        raw=(self.folder/'profile.json').read_bytes()
        raw=raw.replace(b'{',b'{"schema":"duplicate",',1)
        pin=self.changed_payload('profile.json',raw)
        with self.assertRaisesRegex(ValueError,'Duplicate JSON key'):
            b.verify(self.folder,pin)

    def test_existing_output_unknown_file_is_preserved_and_build_stops(self):
        pin=Path(self.temporary.name)/'pin.json'
        pin.write_bytes(b.encoded({'schema':b.PIN_SCHEMA,'manifest_sha256':self.pin}))
        unexpected=self.folder/'keep-me.txt'; unexpected.write_bytes(b'user data')
        with patch.object(b.reference,'validate',side_effect=AssertionError('Do not reach source build')):
            with self.assertRaisesRegex(ValueError,'six approved'):
                b.build(self.folder,pin)
        self.assertEqual(unexpected.read_bytes(),b'user data')
        self.assertEqual(self.manifest_hash(),self.pin)

    def test_pin_inside_bundle_rejected_before_any_write(self):
        with self.assertRaisesRegex(ValueError,'outside the six-file'):
            b.build(self.folder,self.folder/'package.json')
        self.assertEqual(self.manifest_hash(),self.pin)


if __name__ == '__main__':
    unittest.main()
