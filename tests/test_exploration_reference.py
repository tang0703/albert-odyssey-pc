"""Reference custody tests use synthetic files, not missing historical states."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import exploration_reference as reference


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def record(self, name):
        content = name.encode()
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}

    def test_changed_and_truncated_evidence_rejected(self):
        record = self.record('reports/a.bin')
        path = reference.pinned_file(self.root, record)
        path.write_bytes(b'x' * record['bytes'])
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            reference.pinned_file(self.root, record)
        path.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            reference.pinned_file(self.root, record)

    def test_paths_must_remain_under_project(self):
        record = self.record('safe.bin')
        for name in ('../safe.bin', '/safe.bin', 'C:/safe.bin', 'a\\safe.bin', 'a//safe.bin'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                reference.pinned_file(self.root, {**record, 'path': name})

    def test_complete_distinct_triples_required(self):
        lock = {'schema': 'ao_pc_exploration_reference_lock_v1',
                **{k: self.record(k) for k in ('seed', 'sources', 'build', 'scene')},
                'navigation': [self.record(f'nav/{i}') for i in range(5)],
                'captures': {k: [self.record(f'{k}/{i}') for i in range(3)]
                             for k in ('cardinal', 'corners', 'open', 'release')}}
        path = self.root / 'lock.json'
        def load():
            path.write_text(json.dumps(lock), encoding='utf-8')
            with patch.object(reference, 'ROOT', self.root):
                return reference.load_lock(path)
        self.assertEqual(load(), lock)
        lock['captures']['open'].pop()
        with self.assertRaisesRegex(ValueError, 'three pinned'):
            load()
        lock['captures']['open'].append(lock['captures']['open'][0])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            load()


if __name__ == '__main__':
    unittest.main()
