import shutil
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import interaction_bundle as bundle


class InteractionBundleTests(unittest.TestCase):
    def test_source_bound_sixth_bundle_and_parent_identity(self):
        manifest=bundle.verify()
        self.assertEqual(len(manifest['dependencies']),5)
        self.assertEqual(set(manifest['files']),bundle.NAMES)

    def test_missing_changed_and_unknown_resources_are_rejected(self):
        source=bundle.DEMO/'generated/interaction'
        temporary_root=(bundle.ROOT/'reports/interaction/bundle-tests').resolve()
        temporary_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            self.assertTrue(Path(temporary).resolve().is_relative_to(temporary_root))
            root=Path(temporary);target=root/'interaction';shutil.copytree(source,target)
            for name in bundle.DEPENDENCIES:
                (root/name).mkdir();shutil.copyfile(source.parent/name/'package.json',root/name/'package.json')
            image=target/'pickup-35.png';saved=image.read_bytes();image.unlink()
            with self.assertRaises(ValueError):bundle.verify(target)
            image.write_bytes(saved[:-1])
            with self.assertRaises(ValueError):bundle.verify(target)
            image.write_bytes(saved);unknown=target/'unapproved.bin';unknown.write_bytes(b'unknown')
            with self.assertRaises(ValueError):bundle.verify(target)
            unknown.unlink();(root/'event/package.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):bundle.verify(target)


if __name__=='__main__':unittest.main()
