"""Fault injection for the v2 CPU/VDP evidence gate; no original assets needed."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from exploration_capture import REGISTERS2
import verify_character_capture as verifier


class CharacterCaptureGateTests(unittest.TestCase):
    def setUp(self):
        digest = lambda raw: hashlib.sha256(raw).hexdigest()
        framebuffer = digest(bytes(0x40000))
        cram, texture, video = digest(bytes(4096)), digest(bytes(8)), digest(b'video')
        self.records = {f'blobs/{cram}.bin': {'bytes': 4096, 'sha256': cram},
                        f'blobs/{texture}.bin': {'bytes': 8, 'sha256': texture}}
        self.raw = {}
        regs1 = {key: 0 for key in 'TVMR FBCR PTMR EWDR EWLR EWRR EDSR LOPR COPR MODR'.split()}
        regs2 = dict.fromkeys([*REGISTERS2, 'VCNTLatch'], 0)
        self.samples = {}
        for index in (0, 1):
            prefix = f'frame-{index:06d}/'
            self.raw[prefix + 'state.savestate'] = bytes(0x80000)
            self.records[prefix + 'cram.bin'] = {'sha256': cram}
            for bank in (0, 1):
                self.records[prefix + f'vdp1-fb{bank}.bin'] = {'sha256': framebuffer, 'bytes': 0x40000}
            self.samples[index] = {'video_serial': index, 'video_height': 1, 'scheduler_count': index * 10, 'event_index': 9 if index else 1,
                'vdp1': {**regs1, 'display_bank': 0, 'draw_bank': 1, 'renderer_display_bank': 0,
                         'drawing': False, 'next_command': 0}, 'vdp2': regs2}
        self.records['frame-000001/video-rgba.bin'] = {'sha256': video}
        self.decoded = {'vdp_state': {'regs1': regs1, 'regs2': regs2, 'display_framebuffer': 0,
            'drawing': False, 'next_command_address': 0}, 'regions': {'framebuffers': {'offset': 0}}}
        # 8x1, 8 bpp bank mode; command-time bytes bound independently of frame-end RAM.
        words = [0, 0, 16, 0, 0, 0x0101] + [0] * 10
        command = b''.join(word.to_bytes(2, 'big') for word in words).hex()
        common = {'schema': 'ao_ymir_vdp_event_v2', 'frame': 1, 'scheduler_count': 5,
            'video_serial': 0, 'display_bank': 0, 'draw_bank': 1, 'drawing': True,
            'EDSR': 0, 'COPR': 0, 'LOPR': 0, 'TVMR': 0, 'FBCR': 0, 'PTMR': 0, 'next_command': 0, 'VCNT': 0, 'HCNT': 0,
            'vdp2_registers_be_hex': bytes(512).hex(), 'cram_sha256': cram,
            'player_slot': 0, 'player_actor_address': 0x060c8758, 'player_actor_hex': bytes(112).hex()}
        self.events = []
        for serial, kind in enumerate(('command_fetch', 'command_execute_before', 'command_execute_after'), 1):
            self.events.append({**common, 'event_index': serial + 1, 'kind': kind,
                'command_address': 0, 'command_hex': command, 'end': False, 'skip': False, 'valid_opcode': True})
        self.events[1]['texture'] = {'vram_address': 0, 'bytes': 8, 'width': 8, 'height': 1,
                                     'color_mode': 2, 'sha256': texture}
        self.events.append({'schema': 'ao_ymir_vdp_event_v2', 'event_index': 5, 'frame': 1,
            'scheduler_count': 5, 'kind': 'vdp2_render_line', 'line': 0, 'display_bank': 0,
            'draw_bank': 1, 'compose_video_serial': 1})
        self.events.append({**common, 'event_index': 6, 'kind': 'public_vdp2_draw_finished',
            'framebuffer_sha256': [framebuffer] * 2})
        self.events.append({**common, 'event_index': 7, 'kind': 'software_video_complete',
            'video_serial': 1, 'framebuffer_sha256': [framebuffer] * 2, 'video_sha256': video})
        self.events.insert(0, {**common, 'event_index': 1, 'frame': 0, 'scheduler_count': 0,
            'kind': 'sample_boundary', 'drawing': False, 'framebuffer_sha256': [framebuffer] * 2})
        self.events.append({**common, 'event_index': 9, 'scheduler_count': 10, 'video_serial': 1,
            'kind': 'sample_boundary', 'drawing': False, 'framebuffer_sha256': [framebuffer] * 2})
        self.frames = [{'event_index': 8, 'frame': 1, 'scheduler_count': 10}]
        self.capture = {'event_count': 9, 'fetched_commands': 1, 'executed_commands': 1, 'blob_count': 2}

    def validate(self):
        with patch.object(verifier, 'inspect_snapshot', return_value=self.decoded):
            return verifier.validate_vdp(self.capture, self.frames, [], self.samples,
                                         self.events, self.records, self.raw.__getitem__)

    def test_consistent_independent_payloads(self):
        self.assertEqual(len(self.validate()), 2)

    def test_bad_event_order(self):
        self.events[2]['event_index'] = 1
        with self.assertRaisesRegex(ValueError, 'event order|emission order'): self.validate()

    def test_exec_without_matching_fetch(self):
        self.events[2]['command_address'] = 32
        with self.assertRaisesRegex(ValueError, 'matching executable'): self.validate()

    def test_exec_without_completion(self):
        self.events[3]['command_address'] = 32
        with self.assertRaisesRegex(ValueError, 'completion differs'): self.validate()

    def test_missing_texture_blob(self):
        del self.records['blobs/' + self.events[2]['texture']['sha256'] + '.bin']
        with self.assertRaisesRegex(ValueError, 'payload'): self.validate()

    def test_command_extent_disagrees_with_payload(self):
        self.events[2]['texture']['width'] = 16
        with self.assertRaisesRegex(ValueError, 'texture identity'): self.validate()

    def test_actor_identity_not_guessed(self):
        self.events[1]['player_actor_address'] += 112
        with self.assertRaisesRegex(ValueError, 'slot/address'): self.validate()

    def test_bank_pair_rejected(self):
        self.events[1]['draw_bank'] = 0
        with self.assertRaisesRegex(ValueError, 'framebuffer'): self.validate()

    def test_completed_pixels_bound_to_callback(self):
        self.events[6]['video_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'callback video'): self.validate()

    def test_snapshot_register_mismatch(self):
        self.samples[1] = copy.deepcopy(self.samples[1])
        self.samples[1]['vdp2']['SPCTL'] = 6
        with self.assertRaisesRegex(ValueError, 'registers differ'): self.validate()

    def test_snapshot_framebuffer_mismatch(self):
        self.records['frame-000001/vdp1-fb1.bin']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '[Ff]ramebuffer differs'): self.validate()

    def test_saved_state_framebuffer_mismatch(self):
        raw = bytearray(self.raw['frame-000001/state.savestate'])
        raw[0] = 1
        self.raw['frame-000001/state.savestate'] = bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Framebuffer differs'): self.validate()

    def test_render_line_cannot_claim_other_video(self):
        self.events[4]['compose_video_serial'] = 2
        with self.assertRaisesRegex(ValueError, 'wrong completed video'): self.validate()

    def test_render_lines_must_cover_sample_height(self):
        self.samples[1]['video_height'] = 2
        with self.assertRaisesRegex(ValueError, 'incomplete rendered'): self.validate()

    def test_reordered_render_line(self):
        self.events[4]['line'] = 1
        with self.assertRaisesRegex(ValueError, 'reordered VDP2 render line'): self.validate()

    def test_bank_cannot_change_without_swap(self):
        for row in self.events[1:4]:
            row.update(display_bank=1, draw_bank=0)
        with self.assertRaisesRegex(ValueError, 'without observed swap'): self.validate()

    def test_sample_renderer_bank_must_match_controller(self):
        self.samples[1]['vdp1']['renderer_display_bank'] = 1
        with self.assertRaisesRegex(ValueError, 'bank mismatch'): self.validate()

    def test_command_cannot_execute_twice_from_one_fetch(self):
        before, after = copy.deepcopy(self.events[2:4])
        before['event_index'], after['event_index'] = 5, 6
        for row in self.events[4:]: row['event_index'] += 2
        self.frames[0]['event_index'] += 2
        self.samples[1]['event_index'] += 2
        self.capture.update(event_count=11, executed_commands=2)
        self.events[4:4] = [before, after]
        with self.assertRaisesRegex(ValueError, 'matching executable'): self.validate()

    def test_executable_fetch_must_dispatch_immediately(self):
        self.events[2]['kind'] = 'command_fetch'
        with self.assertRaisesRegex(ValueError, 'immediate execution'): self.validate()

    def test_fetch_count_cannot_be_self_reported(self):
        self.capture['fetched_commands'] = 9
        with self.assertRaisesRegex(ValueError, 'counters differ'): self.validate()

    def test_public_video_finish_required(self):
        self.events[5]['kind'] = 'vdp1_begin'
        with self.assertRaisesRegex(ValueError, 'paired with public completion'): self.validate()

    def test_intermediate_register_observation_is_bound(self):
        self.events[7]['vdp2_registers_be_hex'] = (
            bytes(0xe0) + b'\x00\x06' + bytes(512 - 0xe2)).hex()
        with self.assertRaisesRegex(ValueError, 'registers differ from boundary'): self.validate()

    def invalid_repeat_fixture(self):
        first = self.events[1]
        first['command_hex'] = '000f' + first['command_hex'][4:]
        first['valid_opcode'] = False
        repeated = {key: first[key] for key in ('schema', 'frame', 'command_address',
            'command_hex', 'display_bank', 'draw_bank', 'valid_opcode', 'skip', 'end')}
        repeated.update(kind='command_fetch_repeat', event_index=3, event_index_last=4,
            repeat_count=2, repeats_event_index=2, scheduler_count=5, scheduler_count_last=5)
        self.events[2:4] = [repeated]
        self.capture.update(fetched_commands=3, executed_commands=0, blob_count=1)

    def test_invalid_fetch_rle_is_explicit(self):
        self.invalid_repeat_fixture()
        self.assertEqual(len(self.validate()), 1)

    def test_invalid_fetch_rle_cannot_omit_observations(self):
        self.invalid_repeat_fixture()
        self.events[2]['repeat_count'] = 1
        with self.assertRaisesRegex(ValueError, 'event span'): self.validate()

    def test_invalid_fetch_rle_cannot_cover_different_commands(self):
        self.invalid_repeat_fixture()
        self.events[2]['command_address'] = 32
        with self.assertRaisesRegex(ValueError, 'matching adjacent invalid'): self.validate()

    def test_rle_cannot_claim_unrecorded_context(self):
        self.invalid_repeat_fixture()
        self.events[2]['player_actor_hex'] = '00' * 112
        with self.assertRaisesRegex(ValueError, 'unrecorded context'): self.validate()

    def test_rle_time_range_cannot_cross_next_event(self):
        self.invalid_repeat_fixture()
        self.events[2]['scheduler_count_last'] = 6
        with self.assertRaisesRegex(ValueError, 'global event order'): self.validate()

    def test_rle_cannot_compress_a_valid_command(self):
        self.invalid_repeat_fixture()
        for row in self.events[1:3]:
            row.update(valid_opcode=True, command_hex='0000' + row['command_hex'][4:])
        with self.assertRaisesRegex(ValueError, 'immediate execution'): self.validate()

    def test_rle_cannot_cover_a_hook(self):
        self.invalid_repeat_fixture()
        hook = {'frame': 1, 'event_index': 4, 'scheduler_count': 5}
        with patch.object(verifier, 'inspect_snapshot', return_value=self.decoded):
            with self.assertRaisesRegex(ValueError, 'global event order'):
                verifier.validate_vdp(self.capture, self.frames, [hook], self.samples,
                                      self.events, self.records, self.raw.__getitem__)


class CharacterCaptureBuildGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / 'source'; self.source.mkdir()
        self.names = ('main.cpp', 'CMakeLists.txt', 'build.ps1', 'capture.ps1', 'instrument.cmake',
                      'observer_bridge.hpp', 'vdp2_register_names.inc', 'README.md')
        for name in self.names: (self.source / name).write_text(name, encoding='utf-8')
        self.original, self.generated = root / 'original.cpp', root / 'generated.cpp'
        self.original.write_text('original', encoding='utf-8')
        self.generated.write_text('observed', encoding='utf-8')
        self.v1 = root / 'v1'; self.v1.write_bytes(b'sealed')
        pin = lambda path: {'path': str(path), 'sha256': verifier.digest(path)}
        self.build = {'ymir_revision': verifier.YMIR_REVISION, 'cereal_revision': verifier.CEREAL_REVISION,
            'sources': [{'path': name, 'sha256': verifier.digest(self.source / name)} for name in self.names],
            'instrumentation': {'original_path': str(self.original), 'original_sha256': verifier.digest(self.original),
                'generated_path': str(self.generated), 'generated_sha256': verifier.digest(self.generated),
                'patch': 'instrument.cmake', 'patch_text': 'instrument.cmake'},
            'preserved_v1_unchanged': True, 'preserved_v1': [pin(self.v1)]}

    def validate(self):
        with patch.object(verifier, 'CAPTURE_SOURCE', self.source), patch.object(verifier, 'V1_PATHS', {self.v1}), \
                patch.object(verifier, 'ORIGINAL_VDP_SHA256', verifier.digest(self.original)):
            verifier.validate_build(self.build)

    def test_valid_local_frozen_sources(self):
        self.validate()

    def test_changed_backend_source_rejected(self):
        (self.source / 'main.cpp').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source changed'): self.validate()

    def test_unknown_revision_rejected(self):
        self.build['ymir_revision'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'Unsupported pinned'): self.validate()

    def test_unknown_original_vdp_hash_rejected(self):
        self.build['instrumentation']['original_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'upstream VDP'): self.validate()

    def test_instrumentation_patch_changed(self):
        self.build['instrumentation']['patch_text'] = 'other code'
        with self.assertRaisesRegex(ValueError, 'patch text'): self.validate()

    def test_incomplete_preserved_v1_rejected(self):
        self.build['preserved_v1'] *= 2
        with self.assertRaisesRegex(ValueError, 'preservation identities'): self.validate()

    def test_changed_generated_observer_rejected(self):
        self.generated.write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'translation unit changed'): self.validate()


if __name__ == '__main__': unittest.main()
