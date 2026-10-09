"""Scene failure probes use constructed v13 regions, never the lost old fixture."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import exploration_capture as capture
import validate_exploration_scene as scene

PROJECT = Path(__file__).resolve().parents[1]


class SceneValidationTests(unittest.TestCase):
    def setUp(self):
        temporary_root = PROJECT / 'reports/tmp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='scene-failures-', dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'pc'
        self.project.mkdir()
        extract = self.root / 'work/extract'
        extract.mkdir(parents=True)
        self.map = extract / 'MAP001.TWN'
        self.code = extract / 'TWN.BIN'
        self.payload = b'\0\1' + bytes([1, 1, 1, 1]) + b'\0\0' * 7
        self.map.write_bytes(self.payload)
        self.code.write_bytes(b'synthetic reader input; source hash checks remain real')
        source_lock = {'sources': {'work/extract/MAP001.TWN': capture.digest(self.payload),
                                  'work/extract/TWN.BIN': capture.digest(self.code.read_bytes())}}
        (self.project / 'source-lock.json').write_bytes(capture.json_bytes(source_lock))
        self.tiles = bytes([1]) * 0x40000
        self.layout = bytes(0x10000)
        self.palette = b'\0\0\0\x1f' + bytes(508)
        self.flags = scene.decode_flags(self.payload)[0]
        self.low = bytearray(0x100000)
        self.low[0x10000:0x20000] = self.flags
        self.high = bytearray(0x100000)
        self.high[0xf4000:0xf4000 + len(self.payload)] = self.payload
        prefix = b'\x01\x0d\0\0\0Syst' + bytes(25)
        self.low_offset = len(prefix)
        self.vdp_offset = len(prefix) + 0x200000 + 4 + 256 + 4
        self.regs_offset = self.vdp_offset + 0x181000 + 16 + 20
        vram2 = struct.pack('>I', 0x2000) * (0x40000 // 4) + self.tiles
        cram = self.palette + bytes(0x1000 - 512)
        raw = bytearray(prefix + self.low + self.high + b'MSH2' + bytes(256) + b'VDP#'
                        + bytes(0x80000) + vram2 + cram + bytes(0x80000)
                        + bytes(16 + 20 + 284 + 8 + 14 + 8 + 3))
        regs = {name: 0 for name in capture.REGISTERS2}
        regs.update(TVMD=0x8000, RAMCTL=0x1000, CHCTLA=0x1111, BGON=3)
        for layer in (0, 1):
            regs.update({f'SCXIN{layer}': scene.CAMERA[0], f'SCYIN{layer}': scene.CAMERA[1],
                         f'ZMXIN{layer}': 1, f'ZMYIN{layer}': 1})
        struct.pack_into('<142H', raw, self.regs_offset, *(regs[name] for name in capture.REGISTERS2))
        self.raw = bytes(raw)
        self.snapshot = self.root / 'new-named-state.savestate'
        self.snapshot.write_bytes(self.raw)
        self.output = self.root / 'scene-output'
        blocks = [{}, {}, {'payload_offset': 0, 'size': len(self.payload)}]
        for mocker in (patch.object(scene, 'PROJECT', self.project), patch.object(scene, 'WORKSPACE', self.root),
                       patch.object(scene, 'source_data', return_value=(self.tiles, self.layout, self.palette, blocks)),
                       patch.object(scene, 'verify_reader', return_value=[{'synthetic_decoder_boundary': True}])):
            mocker.start()
            self.addCleanup(mocker.stop)

    def assert_rejected_without_output(self, expected=None):
        with self.assertRaises((ValueError, OSError)):
            scene.validate(self.snapshot, self.output, expected)
        self.assertFalse(self.output.exists())

    def test_valid_source_pixels_memory_and_output_hashes_agree(self):
        result = scene.validate(self.snapshot, self.output, capture.digest(self.raw))
        self.assertTrue(result['passed'])
        self.assertEqual(result['flag_bytes_matched'], 65536)
        self.assertEqual([layer['patterns'] for layer in result['layers']], [280, 280])
        self.assertEqual((self.output / 'flags.bin').read_bytes(), self.flags)
        for name, record in result['outputs'].items():
            self.assertEqual(record['sha256'], capture.digest((self.output / name).read_bytes()))
        with Image.open(self.output / 'nbg0.png') as image:
            self.assertEqual(image.size, (320, 224))
            self.assertEqual(image.convert('RGBA').getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(result['source_code_sha256'], capture.digest(self.code.read_bytes()))

    def test_changed_or_truncated_source_is_rejected(self):
        for path in (self.map, self.code):
            original = path.read_bytes()
            for raw in (original[:-1], original + b'changed'):
                path.write_bytes(raw)
                self.assert_rejected_without_output()
            path.write_bytes(original)

    def test_snapshot_truncation_version_and_expected_identity_rejected(self):
        for raw in (self.raw[:-1], b'\x01\x0e' + self.raw[2:], self.raw[:100]):
            self.snapshot.write_bytes(raw)
            self.assert_rejected_without_output()
        self.snapshot.write_bytes(self.raw)
        self.assert_rejected_without_output('0' * 64)

    def test_tile_palette_metadata_and_flag_mismatches_rejected(self):
        offsets = [self.vdp_offset + 0x80000 + 0x40000,
                   self.vdp_offset + 0x100000 + 2,
                   self.low_offset + 0x100000 + 0xf4000,
                   self.low_offset + 0x10000]
        for offset in offsets:
            raw = bytearray(self.raw)
            raw[offset] ^= 1
            self.snapshot.write_bytes(raw)
            self.assert_rejected_without_output()

    def test_wrong_camera_or_visible_pattern_is_not_accepted(self):
        raw = bytearray(self.raw)
        index = capture.REGISTERS2.index('SCXIN0')
        struct.pack_into('<H', raw, self.regs_offset + index * 2, scene.CAMERA[0] + 16)
        self.snapshot.write_bytes(raw)
        self.assert_rejected_without_output()
        raw = bytearray(self.raw)
        # The fixed viewport's first world tile maps to page row 0, column 2.
        raw[self.vdp_offset + 0x80000 + 2 * 4 + 3] ^= 1
        self.snapshot.write_bytes(raw)
        self.assert_rejected_without_output()

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        marker = self.output / 'keep.txt'
        marker.write_text('existing review evidence', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'new scene validation output'):
            scene.validate(self.snapshot, self.output)
        self.assertEqual(marker.read_text(), 'existing review evidence')

    def test_source_write_during_render_cannot_publish_success(self):
        original_render = scene.render_view
        def changed_render(*args, **kwargs):
            result = original_render(*args, **kwargs)
            self.code.write_bytes(b'changed after initial source verification')
            return result
        with patch.object(scene, 'render_view', side_effect=changed_render):
            self.assert_rejected_without_output()

    def test_snapshot_write_during_render_cannot_publish_success(self):
        original_render = scene.render_view
        def changed_render(*args, **kwargs):
            result = original_render(*args, **kwargs)
            self.snapshot.write_bytes(self.raw + b'later generation')
            return result
        with patch.object(scene, 'render_view', side_effect=changed_render):
            self.assert_rejected_without_output()


@unittest.skipUnless(shutil.which('pwsh'), 'PowerShell 7 is required for profile isolation checks')
class ProfileIsolationTests(unittest.TestCase):
    def setUp(self):
        temporary_root = PROJECT / 'reports/tmp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='profile-isolation-', dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / 'pc-remake'
        tools = self.project / 'tools'
        tools.mkdir(parents=True)
        self.script = tools / 'exploration_profile.ps1'
        shutil.copyfile(PROJECT / 'tools/exploration_profile.ps1', self.script)
        self.legacy = self.project / 'savestate-lock.json'
        self.legacy.write_text('{"preserve":"historical fixture"}\n', encoding='utf-8')
        exe = self.root / 'tools/ymir/v0.3.3/ymir-sdl3.exe'
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b'never run: profile tests omit -Launch')
        disc = self.root / 'Albert Odyssey - Legend of Eldean (USA) (RE)'
        disc.mkdir()
        (disc / (disc.name + '.cue')).write_text('fixture only', encoding='utf-8')
        (self.root / 'EMU/yabause-0.9.15-win64/Bios').mkdir(parents=True)
        self.template = self.root / 'work/ymir/dialogue-trace/Ymir.toml'
        self.template.parent.mkdir(parents=True)
        self.template.write_text("[Audio]\nMute = false\n[General]\nStartPaused = false\n"
                                 "[General.PathOverrides]\nIPLROMImages = ''\n"
                                 + ''.join(f"{key} = 'G:/shared-old-profile/{key}'\n"
                                           for key in ('BackupMemory', 'Dumps', 'ExportedBackups', 'PersistentState', 'SaveStates', 'Screenshots'))
                                 + "[Cartridge.BackupRAM]\nCapacity = '32Mbit'\nImagePath = 'G:/shared-old-profile/cart.ram'\n",
                                 encoding='utf-8')
        self.profile = self.project / 'reports/exploration/ymir-profile'

    def run_script(self):
        return subprocess.run([shutil.which('pwsh'), '-NoProfile', '-File', str(self.script)],
                              cwd=self.project, text=True, capture_output=True, encoding='utf-8', timeout=30)

    def test_new_profile_redirects_writes_and_preserves_original_inputs(self):
        before = self.template.read_bytes(), self.legacy.read_bytes()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = (self.profile / 'Ymir.toml').read_text()
        self.assertNotIn('G:/shared-old-profile/', generated)
        self.assertIn('StartPaused = true', generated)
        self.assertIn('Mute = true', generated)
        self.assertEqual((self.template.read_bytes(), self.legacy.read_bytes()), before)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest['template_sha256'], hashlib.sha256(before[0]).hexdigest())
        self.assertFalse(manifest['old_profile_modified'])

    def test_existing_private_config_is_never_overwritten(self):
        first = self.run_script()
        self.assertEqual(first.returncode, 0, first.stderr)
        config = self.profile / 'Ymir.toml'
        config.write_text(config.read_text() + '# user customization must survive\n', encoding='utf-8')
        before = config.read_bytes()
        second = self.run_script()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(config.read_bytes(), before)

    def test_existing_shared_write_path_is_refused_without_rewriting_it(self):
        first = self.run_script()
        self.assertEqual(first.returncode, 0, first.stderr)
        config = self.profile / 'Ymir.toml'
        text = config.read_text()
        lines = ["SaveStates = 'G:/shared-old-profile/states'" if line.startswith('SaveStates =') else line
                 for line in text.splitlines()]
        config.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        before = config.read_bytes()
        second = self.run_script()
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('shares writable path', second.stderr)
        self.assertEqual(config.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
