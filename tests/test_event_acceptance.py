"""Reject stale or incomplete final evidence without editing local proof files."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import summarize_event_acceptance as acceptance


@unittest.skipUnless((acceptance.BASE / 'soak-release-01/soak-4k/acceptance.json').exists(), 'Local final event evidence required')
class EventAcceptanceTests(unittest.TestCase):
    def reject(self, suffix, mutate):
        original = Path.read_bytes

        def altered(path):
            raw = original(path)
            if path.as_posix().endswith(suffix):
                data = json.loads(raw)
                mutate(data)
                return json.dumps(data).encode()
            return raw

        with patch.object(Path, 'read_bytes', altered), self.assertRaises(ValueError):
            acceptance.summarize()

    def test_current_local_evidence_passes(self):
        self.assertTrue(acceptance.summarize()['passed'])

    def test_incomplete_soak_rejected(self):
        self.reject('soak-4k/acceptance.json', lambda d: d.update(recomputed_measured_seconds=599))

    def test_unreviewed_spike_rejected(self):
        self.reject('soak-4k/acceptance.json', lambda d: d.update(spikes_over_100ms_require_reproduction_review=True))

    def test_mixed_binary_rejected(self):
        self.reject('1920x1080-page-1/launch.json', lambda d: d.update(pck_sha256='0' * 64))

    def test_wrong_page_rejected(self):
        self.reject('2560x1440-page-2/report.json', lambda d: d.update(dialogue_page=0))

    def test_background_load_rejected(self):
        self.reject('d4-host-preflight.json', lambda d: d['assessment'].update(status='blocked'))

    def test_wrong_source_coverage_rejected(self):
        self.reject('d3-gpu.json', lambda d: d['cases'][0].update(differences=1))


if __name__ == '__main__':
    unittest.main()
