import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import event_bundle


class EventBundleTests(unittest.TestCase):
    def test_source_bound_bundle(self):
        manifest=event_bundle.verify()
        self.assertEqual(len(manifest['dependencies']),4)
        self.assertEqual(set(manifest['files']),event_bundle.NAMES)

    def test_missing_changed_and_unknown_payloads_rejected(self):
        base=event_bundle.DEMO/'generated'
        with tempfile.TemporaryDirectory(prefix='event-test-',dir=base) as temporary:
            target=Path(temporary)
            for source in (base/'event').iterdir():shutil.copyfile(source,target/source.name)
            path=target/'expression-00.png'
            original=path.read_bytes()
            for mutation in ('missing','changed','extra'):
                if mutation=='missing':path.unlink()
                elif mutation=='changed':path.write_bytes(original[:-1])
                else:
                    path.write_bytes(original)
                    (target/'unapproved.gd').write_text('extends Node')
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):event_bundle.verify(target)
                path.write_bytes(original)

    def test_translation_identity(self):
        data=json.loads((event_bundle.DEMO/'generated/event/core.json').read_text(encoding='utf-8'))
        pages=data['contract']['dialogue']['pages']
        self.assertEqual([p['id'] for p in pages],['map001_00afe2_p01','map001_00afe2_p02'])


if __name__=='__main__':unittest.main()
