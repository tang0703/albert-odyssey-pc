"""Adversarial synthetic capture bundles, not original Saturn acceptance data."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import verify_exploration_replay as replay
import validate_movement_capture as movement


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows), encoding='utf-8')


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def state_bytes(low):
    return (b'\x01\x0d\0\0\0Syst' + bytes(25) + low + bytes(0x100000)
            + b'MSH2' + bytes(256) + b'VDP#' + bytes(0x181000 + 16 + 20 + 284 + 8 + 14 + 8 + 3))


class ReplayEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / 'reports/tmp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='replay-evidence-', dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / 'sources'
        self.sources.mkdir()
        self.cue = self.sources / 'game.cue'
        self.track = self.sources / 'track.bin'
        self.bios = self.sources / 'bios.bin'
        self.sequence = self.sources / 'sequence.txt'
        self.executable = self.sources / 'capture.exe'
        self.cue.write_text('FILE "track.bin" BINARY\n TRACK 01 MODE1/2352\n', encoding='utf-8')
        self.track.write_bytes(b'synthetic disc sectors')
        self.bios.write_bytes(bytes(0x80000))
        self.sequence.write_text('none 2\n', encoding='utf-8')
        self.executable.write_bytes(b'synthetic fixture executable; never launched')
        self.build = {'schema': 'ao_ymir_capture_build_v1', 'ymir_revision': '1' * 40,
                      'cereal_revision': '2' * 40, 'configuration': 'synthetic fixtures',
                      'executable': str(self.executable), 'executable_sha256': hashed(self.executable.read_bytes()),
                      'sources': [{'path': name, 'sha256': hashed(name.encode())}
                                  for name in ('main.cpp', 'CMakeLists.txt', 'build.ps1')]}
        self.actor = bytearray(0x70)
        struct.pack_into('>HH', self.actor, 0, 1600, 1600)
        self.actor[0x29] = 1

    def reseal(self, folder, mutate=None):
        path = folder / 'manifest.json'
        manifest = json.loads(path.read_text())
        if mutate:
            mutate(manifest)
        manifest['outputs'] = [{'path': p.relative_to(folder).as_posix(), 'bytes': p.stat().st_size,
                                'sha256': hashed(p.read_bytes())}
                               for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'manifest.json']
        write_json(path, manifest)

    def run_fixture(self, name='run-a', alternate_table=False):
        folder = self.root / name
        folder.mkdir()
        capture = {'schema': 'ao_ymir_capture_v1', 'ymir_revision': self.build['ymir_revision'], 'status': 'complete',
                   'frames': 2, 'video_serial': 2, 'function_calls': 2, 'pending_calls': 0,
                   'rtc': 'virtual_fixed_1994_or_loaded_state', 'render_threads': 0, 'sh2_cache': False,
                   'hook_boundary': replay.BOUNDARY}
        write_json(folder / 'capture.json', capture)
        frames, hooks = [], []
        for frame in range(3):
            table = bytearray(0x10000)
            if alternate_table and frame == 2:
                table[12 * 256 + 12] = 4
            low = bytes(0x10000) + table + bytes(0xe0000)
            sub = folder / f'frame-{frame:06d}'
            sub.mkdir()
            for filename, size in replay.MEMORY.items():
                (sub / filename).write_bytes(low if filename == 'wram-low.bin' else bytes(size))
            sample = {'schema': 'ao_ymir_frame_sample_v1', 'frame': frame, 'video_serial': frame,
                      'boundary': 'after_RunFrame_return' if frame else 'initial_before_RunFrame',
                      'scheduler_count': 100 + frame * 100, 'video_width': int(frame > 0), 'video_height': int(frame > 0),
                      'input': 'none', 'input_polls': frame, 'function_calls': frame, 'watches': [],
                      'flags_sha256': hashed(table)}
            write_json(sub / 'sample.json', sample)
            if frame in (0, 2):
                (sub / 'state.savestate').write_bytes(state_bytes(low))
            if not frame:
                continue
            (sub / 'video-rgba.bin').write_bytes(bytes(4))
            (sub / 'video.ppm').write_bytes(b'P6\n1 1\n255\n' + bytes(3))
            frames.append({'frame': frame, 'video_serial': frame, 'input': 'none', 'input_polls': frame,
                           'function_calls': frame, 'watches': []})
            common = {'frame': frame, 'function_call_index': frame, 'input': 'none', 'input_polls': frame,
                      'actor_address': 0x060c8758, 'pr': 0x060aae42, 'flags_sha256': hashed(table),
                      'r': [0, 0, 0, 0, 0x060c8758] + [0] * 11, 'watches': []}
            entry = dict(common, kind='entry', hook_index=frame * 2 - 1, pc=0x060ab61a, actor_hex=self.actor.hex())
            actual = bytearray(self.actor)
            if alternate_table and frame == 2:
                actual[0x4a] = 4  # Observed center flag; no call to the model to manufacture this expectation.
            returned = dict(common, kind='return', hook_index=frame * 2, pc=0x060aae42, actor_hex=actual.hex())
            hooks.extend([entry, returned])
        write_rows(folder / 'frames.jsonl', frames)
        write_rows(folder / 'hooks.jsonl', hooks)
        manifest = {'schema': 'ao_ymir_capture_manifest_v1', 'inputs_unchanged': True,
                    'working_directory': str(self.root), 'build': copy.deepcopy(self.build),
                    'arguments': ['--ipl', str(self.bios), '--disc', str(self.cue), '--sequence', str(self.sequence),
                                  '--output', str(folder), '--sample-every', '1', '--trace-function', '0x060AB61A'],
                    'inputs': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': hashed(p.read_bytes())}
                               for p in (self.bios, self.cue, self.track, self.sequence)], 'outputs': []}
        write_json(folder / 'manifest.json', manifest)
        self.reseal(folder)
        return folder

    def mutate_hooks(self, folder, change):
        rows = read_rows(folder / 'hooks.jsonl')
        change(rows)
        write_rows(folder / 'hooks.jsonl', rows)
        self.reseal(folder)

    def test_three_complete_identical_runs_pass_only_timing_gate(self):
        runs = [self.run_fixture(name) for name in ('a', 'b', 'c')]
        result = replay.verify(runs)
        self.assertTrue(result['passed'])
        self.assertTrue(result['timing_evidence_passed'])
        self.assertFalse(result['movement_model_evidence_passed'])
        comparison = movement.validate(runs[0])
        self.assertTrue(comparison['movement_model_evidence_passed'])
        self.assertFalse(comparison['player_identity_verified'])

    def test_declared_complete_without_hooks_cannot_pass(self):
        folder = self.run_fixture()
        (folder / 'hooks.jsonl').write_text('', encoding='utf-8')
        self.reseal(folder)
        with self.assertRaisesRegex(ValueError, 'invented completed'):
            replay.inspect(folder)

    def test_missing_hook_file_or_frame_evidence_is_rejected(self):
        for filename in ('hooks.jsonl', 'frames.jsonl', 'frame-000001/sample.json'):
            folder = self.run_fixture(filename.replace('/', '-').replace('.', '-'))
            (folder / filename).unlink()
            self.reseal(folder)
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                replay.inspect(folder)

    def test_missing_frame_even_with_matching_output_hashes_is_rejected(self):
        folder = self.run_fixture()
        write_rows(folder / 'frames.jsonl', read_rows(folder / 'frames.jsonl')[:1])
        self.reseal(folder)
        with self.assertRaisesRegex(ValueError, 'per-frame'):
            replay.inspect(folder)

    def test_raw_output_change_cannot_reach_movement_comparison(self):
        folder = self.run_fixture()
        (folder / 'hooks.jsonl').write_text('{}\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'output changed'):
            movement.validate(folder)

    def test_current_source_and_executable_changes_are_rejected(self):
        folder = self.run_fixture()
        for path in (self.track, self.bios, self.sequence, self.executable):
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'changed'):
                replay.inspect(folder)
            path.write_bytes(original)

    def test_disc_track_pin_cannot_be_omitted(self):
        folder = self.run_fixture()
        self.reseal(folder, lambda m: m.update(inputs=[r for r in m['inputs'] if r['path'] != str(self.track)]))
        with self.assertRaisesRegex(ValueError, 'Missing or unlisted'):
            replay.inspect(folder)

    def test_different_build_cannot_count_as_same_replay(self):
        runs = [self.run_fixture(name) for name in ('a', 'b', 'c')]
        self.reseal(runs[-1], lambda m: m['build'].update(configuration='different synthetic build'))
        with self.assertRaisesRegex(ValueError, 'build differs'):
            replay.verify(runs)

    def test_same_directory_cannot_count_as_three_runs(self):
        folder = self.run_fixture()
        with self.assertRaisesRegex(ValueError, 'distinct'):
            replay.verify([folder, folder, folder])

    def test_unpaired_hook_and_wrong_actor_or_return_pc_are_rejected(self):
        cases = {'missing_return': lambda rows: rows.pop(1),
                 'wrong_actor': lambda rows: rows[1].update(actor_address=0x060c87c8),
                 'wrong_pc': lambda rows: rows[1].update(pc=0x060aae44),
                 'reused_call': lambda rows: rows[2].update(function_call_index=1),
                 'outside_frame': lambda rows: rows[0].update(frame=100),
                 'wrong_input': lambda rows: rows[0].update(input='right')}
        for name, change in cases.items():
            folder = self.run_fixture(name)
            self.mutate_hooks(folder, change)
            with self.subTest(name=name), self.assertRaises(ValueError):
                replay.inspect(folder)

    def test_invented_frame_function_counts_are_rejected(self):
        folder = self.run_fixture()
        rows = read_rows(folder / 'frames.jsonl')
        rows[0]['function_calls'] = 0
        write_rows(folder / 'frames.jsonl', rows)
        sample = json.loads((folder / 'frame-000001/sample.json').read_text())
        sample['function_calls'] = 0
        write_json(folder / 'frame-000001/sample.json', sample)
        self.reseal(folder)
        with self.assertRaisesRegex(ValueError, 'counter differs from hook'):
            replay.inspect(folder)

    def test_unlisted_extra_file_and_traversal_are_rejected(self):
        folder = self.run_fixture()
        (folder / 'unlisted.bin').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'Unlisted'):
            replay.inspect(folder)
        (folder / 'unlisted.bin').unlink()
        path = folder / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['outputs'][0]['path'] = '../sources/track.bin'
        write_json(path, manifest)
        with self.assertRaisesRegex(ValueError, 'output path'):
            replay.inspect(folder)

    def test_missing_hash_and_wrong_initial_boundary_are_rejected(self):
        folder = self.run_fixture()
        self.mutate_hooks(folder, lambda rows: rows[0].pop('flags_sha256'))
        with self.assertRaisesRegex(ValueError, 'hook flags'):
            replay.inspect(folder)
        other = self.run_fixture('other')
        path = other / 'frame-000000/sample.json'
        sample = json.loads(path.read_text())
        sample['boundary'] = 'after_RunFrame_return'
        write_json(path, sample)
        self.reseal(other)
        with self.assertRaisesRegex(ValueError, 'sample boundary'):
            replay.inspect(other)

    def test_saved_state_and_memory_dump_must_share_boundary(self):
        folder = self.run_fixture()
        path = folder / 'frame-000002/wram-high.bin'
        raw = bytearray(path.read_bytes())
        raw[123] = 9
        path.write_bytes(raw)
        self.reseal(folder)
        with self.assertRaisesRegex(ValueError, 'same-boundary memory'):
            replay.inspect(folder)

    def test_video_outputs_cannot_disagree_even_if_manifest_hashes_match(self):
        folder = self.run_fixture()
        path = folder / 'frame-000001/video.ppm'
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + b'\x01')
        self.reseal(folder)
        with self.assertRaisesRegex(ValueError, 'PPM and RGBA pixels differ'):
            replay.inspect(folder)

    def test_watch_notes_cannot_override_same_boundary_memory(self):
        folder = self.run_fixture()
        watch = {'address': 0x06000000, 'bytes': 1, 'hex': '00'}
        for filename in ('frames.jsonl', 'hooks.jsonl'):
            rows = read_rows(folder / filename)
            for row in rows:
                row['watches'] = [dict(watch)]
                if filename == 'frames.jsonl' and row['frame'] == 1:
                    row['watches'][0]['hex'] = '01'
            write_rows(folder / filename, rows)
        for frame in range(3):
            path = folder / f'frame-{frame:06d}/sample.json'
            sample = json.loads(path.read_text())
            sample['watches'] = [dict(watch, hex='01' if frame == 1 else '00')]
            write_json(path, sample)
        self.reseal(folder, lambda m: m['arguments'].extend(['--watch-range', '0x06000000:1']))
        with self.assertRaisesRegex(ValueError, 'watch differs from same-boundary WRAM'):
            replay.inspect(folder)

    def test_boolean_counters_cannot_impersonate_frame_numbers(self):
        folder = self.run_fixture()
        rows = read_rows(folder / 'frames.jsonl')
        rows[0]['frame'] = True
        write_rows(folder / 'frames.jsonl', rows)
        self.reseal(folder)
        with self.assertRaisesRegex(ValueError, 'Invalid frame index'):
            replay.inspect(folder)

    def test_flag_changes_within_call_are_not_hidden_by_frame_zero(self):
        folder = self.run_fixture()
        self.mutate_hooks(folder, lambda rows: rows[1].update(flags_sha256='a' * 64))
        self.assertTrue(replay.inspect(folder)['timing_evidence_passed'])
        with self.assertRaisesRegex(ValueError, 'changed during'):
            movement.validate(folder)

    def test_unknown_table_hash_cannot_reuse_initial_table(self):
        folder = self.run_fixture()
        self.mutate_hooks(folder, lambda rows: [rows[i].update(flags_sha256='a' * 64) for i in (0, 1)])
        with self.assertRaisesRegex(ValueError, 'no matching archived'):
            movement.validate(folder)

    def test_each_call_uses_its_own_archived_flag_table_version(self):
        folder = self.run_fixture(alternate_table=True)
        result = movement.validate(folder)
        self.assertTrue(result['passed'])
        self.assertEqual(result['calls_compared'], 2)
        self.assertEqual(len(result['flag_table_calls']), 2)
        self.assertIsNone(result['flags_sha256'])

    def test_actor_change_reports_model_failure_not_timing_failure(self):
        folder = self.run_fixture()
        def alter(rows):
            actor = bytearray.fromhex(rows[1]['actor_hex'])
            actor[1] += 1
            rows[1]['actor_hex'] = actor.hex()
        self.mutate_hooks(folder, alter)
        self.assertTrue(replay.inspect(folder)['timing_evidence_passed'])
        result = movement.validate(folder)
        self.assertFalse(result['passed'])
        self.assertEqual(result['mismatched_calls'], 1)
        self.assertFalse(result['movement_model_evidence_passed'])


if __name__ == '__main__':
    unittest.main()
