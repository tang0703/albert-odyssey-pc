import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import room_bundle as b

class RoomBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)/'room'
        shutil.copytree(b.DEFAULT,self.folder)
        self.pin=json.loads(b.PIN.read_text())['manifest_sha256']

    def tearDown(self):self.tmp.cleanup()

    def test_actual_bundle_and_three_dependency_manifests(self):
        self.assertTrue(b.verify(b.DEFAULT,self.pin,b.DEFAULT.parent)['passed'])

    def test_missing_png_is_rejected(self):
        (self.folder/'decoration-7-16.png').unlink()
        with self.assertRaises(ValueError):b.verify(self.folder,self.pin)

    def test_unlisted_script_is_rejected(self):
        (self.folder/'extra.gd').write_text('extends Node')
        with self.assertRaises(ValueError):b.verify(self.folder,self.pin)

    def test_truncated_png_and_edited_camera_are_rejected(self):
        path=self.folder/'background.png';original=path.read_bytes();path.write_bytes(original[:20])
        with self.assertRaises(ValueError):b.verify(self.folder,self.pin)
        path.write_bytes(original)
        path=self.folder/'room.json';data=json.loads(path.read_text(encoding='utf-8'))
        data['camera_profile']['speed_limit_raw']=64;path.write_bytes(b.encoded(data))
        with self.assertRaises(ValueError):b.verify(self.folder,self.pin)

    def test_manifest_change_is_rejected(self):
        path=self.folder/'package.json';data=json.loads(path.read_text())
        data['dependencies']['scene']='0'*64;path.write_bytes(b.encoded(data))
        with self.assertRaises(ValueError):b.verify(self.folder,self.pin)

if __name__=='__main__':unittest.main()
