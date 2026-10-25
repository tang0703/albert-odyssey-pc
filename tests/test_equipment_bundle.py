import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import equipment_bundle as bundle

@unittest.skipUnless((bundle.DEFAULT/'package.json').exists(),'Local equipment bundle required')
class EquipmentBundleTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'reports/equipment/bundle-tests';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
        self.folder=self.root/'equipment';shutil.copytree(bundle.DEFAULT,self.folder)
        for name in bundle.DEPENDENCIES:
            (self.root/name).mkdir();shutil.copy2(bundle.DEFAULT.parent/name/'package.json',self.root/name/'package.json')
    def tearDown(self):self.temp.cleanup()
    def test_valid(self):self.assertEqual(bundle.verify(self.folder)['schema'],'ao_pc_equipment_bundle_v1')
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
        (self.root/'interaction/package.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):bundle.verify(self.folder)

if __name__=='__main__':unittest.main()
