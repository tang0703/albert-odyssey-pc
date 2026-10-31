import shutil
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import transition_bundle as bundle

@unittest.skipUnless((bundle.DEFAULT/'package.json').exists(),'Local transition bundle required')
class TransitionBundleTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'reports/transition/bundle-tests';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
        self.folder=self.root/'transition';shutil.copytree(bundle.DEFAULT,self.folder)
        for name in bundle.DEPENDENCIES:
            (self.root/name).mkdir();shutil.copy2(bundle.DEFAULT.parent/name/'package.json',self.root/name/'package.json')
    def tearDown(self):self.temp.cleanup()
    def test_valid_source_bundle_performance_deferred(self):
        result=bundle.verify(self.folder)
        self.assertEqual(result['stage'],'source_verified');self.assertTrue(result['runtime_approved']);self.assertFalse(result['performance_tested'])
    def test_missing(self):
        (self.folder/'core.json').unlink()
        with self.assertRaises(ValueError):bundle.verify(self.folder)
    def test_changed(self):
        (self.folder/'core.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):bundle.verify(self.folder)
    def test_extra(self):
        (self.folder/'unapproved.gd').write_text('')
        with self.assertRaises(ValueError):bundle.verify(self.folder)
    def test_parent_changed(self):
        (self.root/'equipment/package.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):bundle.verify(self.folder)

if __name__=='__main__':unittest.main()
