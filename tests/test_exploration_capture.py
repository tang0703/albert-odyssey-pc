"""Synthetic section fixtures: archival integrity is not emulator fidelity."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import exploration_capture as capture


def synthetic_state():
    prefix = b"\x01\x0d\0\0\0Syst" + bytes(25)
    data = bytearray(prefix + bytes(0x200000) + b"MSH2" + bytes(256) + b"VDP#")
    offset = len(data)
    data.extend(bytes(0x181000 + 16 + 20 + 284 + 8 + 14 + 8 + 3))
    data[len(prefix)] = 17
    data[len(prefix) + 0x100000] = 29
    data[offset] = 50
    return bytes(data)


def observations():
    return {"schema": capture.METADATA_SCHEMA, "profile": "synthetic-profile",
            "tool": {"name": "Ymir", "version": "synthetic-v13", "executable_sha256": "0" * 64},
            "observations": {"paused": {"status": "observed", "value": True, "evidence": "fixture note only"},
                             **{key: {"status": "unknown", "value": None, "reason": "no live emulator"}
                                for key in ("emulator_frame", "player_update", "synchronization")}}}


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = synthetic_state()
        image = Image.new("RGB", (320, 224), "black")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        cls.png = buffer.getvalue()
        temporary_root = capture.PROJECT / "reports/tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="exploration-capture-tests-", dir=temporary_root)
        cls.root = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.path = self.root / self._testMethodName
        self.path.mkdir()
        self.snapshot = self.path / "source.savestate"
        self.screen = self.path / "source.png"
        self.metadata = self.path / "metadata.json"
        self.output = self.path / "captures"
        self.snapshot.write_bytes(self.raw)
        self.screen.write_bytes(self.png)
        self.metadata.write_bytes(capture.json_bytes(observations()))

    def ingest(self, capture_id="map001-test-01"):
        return capture.ingest(capture_id, self.snapshot, self.screen, self.metadata, self.output)

    def archive(self):
        result = self.ingest()
        return Path(result["capture_directory"]), result

    def rewrite_manifest(self, directory, change):
        path = directory / capture.LOCK_NAME
        lock = capture.read_json_bytes(path.read_bytes())
        change(lock)
        raw = capture.json_bytes(lock)
        path.write_bytes(raw)
        (directory / "capture-lock.sha256").write_text(capture.digest(raw) + "\n", encoding="ascii")

    def test_roundtrip_is_independent_and_preserves_input_bytes(self):
        directory, result = self.archive()
        self.assertEqual((directory / "snapshot.savestate").read_bytes(), self.raw)
        self.assertEqual((directory / "screen.png").read_bytes(), self.png)
        lock = capture.read_json_bytes((directory / capture.LOCK_NAME).read_bytes())
        self.assertEqual(lock["snapshot"]["regions"]["wram_low"]["size"], 0x100000)
        self.assertEqual(lock["snapshot"]["regions"]["vram1"]["sha256"], capture.digest(bytes([50]) + bytes(0x7ffff)))
        self.assertEqual(lock["screenshot"], {"width": 320, "height": 224, "mode": "RGB"})
        self.snapshot.unlink()
        self.screen.unlink()
        self.metadata.unlink()
        self.assertEqual(capture.verify(directory, result["manifest_sha256"]), result)
        self.assertEqual(result["archive_integrity"], "passed")
        self.assertFalse(result["e1_passed"])

    def test_observed_frames_never_fabricate_synchronization_or_replay(self):
        metadata = observations()
        for key, value in (("emulator_frame", 124), ("player_update", 53), ("synchronization", "same paused screen")):
            metadata["observations"][key] = {"status": "observed", "value": value, "evidence": "operator note"}
        self.metadata.write_bytes(capture.json_bytes(metadata))
        result = self.ingest()
        self.assertEqual(result["observations"]["emulator_frame"], "observed")
        self.assertEqual(result["synchronized_sampling"], "unknown")
        self.assertEqual(result["repeatable_replay"], "unknown")
        self.assertFalse(result["e1_passed"])

    def test_existing_capture_is_never_overwritten(self):
        directory, result = self.archive()
        with self.assertRaisesRegex(ValueError, "cannot be overwritten"):
            self.ingest()
        self.assertEqual(capture.verify(directory), result)

    def test_changed_or_truncated_snapshot_and_png_are_rejected(self):
        directory, _ = self.archive()
        for filename in ("snapshot.savestate", "screen.png", "observations.json"):
            path = directory / filename
            original = path.read_bytes()
            for changed in (original[:-1], original[:-1] + bytes([original[-1] ^ 1])):
                path.write_bytes(changed)
                with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, "identity changed"):
                    capture.verify(directory)
            path.write_bytes(original)

    def test_manifest_change_requires_both_seal_and_external_pin(self):
        directory, result = self.archive()
        path = directory / capture.LOCK_NAME
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            capture.verify(directory)
        (directory / "capture-lock.sha256").write_text(capture.digest(path.read_bytes()) + "\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            capture.verify(directory, result["manifest_sha256"])

    def test_old_fixture_lock_cannot_replace_independent_capture_lock(self):
        directory, _ = self.archive()
        self.rewrite_manifest(directory, lambda lock: lock.update(schema="ao_pc_ymir_v13_fixture_v1"))
        with self.assertRaisesRegex(ValueError, "independent exploration capture"):
            capture.verify(directory)

    def test_recomputed_seal_cannot_promote_assessment(self):
        directory, _ = self.archive()
        self.rewrite_manifest(directory, lambda lock: lock["assessment"].update(e1_passed=True))
        with self.assertRaisesRegex(ValueError, "promoted"):
            capture.verify(directory)

    def test_recomputed_seal_cannot_change_parser_lock(self):
        directory, _ = self.archive()
        self.rewrite_manifest(directory, lambda lock: lock["snapshot"]["parser_lock"].update(vdp_payload_offset=20))
        with self.assertRaisesRegex(ValueError, "parser lock"):
            capture.verify(directory)

    def test_capture_rename_missing_and_unlisted_files_rejected(self):
        directory, _ = self.archive()
        extra = directory / "extra.bin"
        extra.write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "file set changed"):
            capture.verify(directory)
        extra.unlink()
        moved = directory.with_name("renamed")
        directory.rename(moved)
        with self.assertRaisesRegex(ValueError, "independent exploration capture"):
            capture.verify(moved)
        (moved / "screen.png").unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            capture.verify(moved)

    def test_invalid_input_never_publishes_a_capture(self):
        for raw in (self.raw[:-1], b"\x01\x0e" + self.raw[2:], self.raw + b"VDP#", b"invalid"):
            self.snapshot.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.ingest()
            self.assertFalse((self.output / "map001-test-01").exists())

    def test_ram_boundary_and_renderer_values_checked(self):
        for marker, delta in ((b"MSH2", 0), (b"Syst", 0)):
            broken = bytearray(self.raw)
            broken[broken.index(marker) + delta] ^= 1
            with self.assertRaises(ValueError):
                capture.inspect_snapshot(bytes(broken))
        broken = bytearray(self.raw)
        broken[-3] = 2
        with self.assertRaisesRegex(ValueError, "renderer Boolean"):
            capture.inspect_snapshot(bytes(broken))
        broken = bytearray(self.raw)
        broken[broken.index(b"VDP#") + 4 + 0x181000] = 2
        with self.assertRaisesRegex(ValueError, "framebuffer index"):
            capture.inspect_snapshot(bytes(broken))

    def test_png_corruption_and_non_png_rejected(self):
        for raw in (b"not-png", self.png[:40], self.png[:-20]):
            self.screen.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.ingest()

    def test_bad_observation_and_missing_tool_provenance_rejected(self):
        cases = []
        for change in (lambda m: m["observations"]["paused"].update(status="passed"),
                       lambda m: m["observations"]["paused"].update(value="true"),
                       lambda m: m["observations"]["emulator_frame"].update(value=2),
                       lambda m: m["observations"]["paused"].pop("evidence"),
                       lambda m: m["observations"].pop("player_update"),
                       lambda m: m["tool"].update(executable_sha256="unknown"),
                       lambda m: m.update(schema="ao_pc_ymir_v13_fixture_v1")):
            value = observations()
            change(value)
            cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                capture.validate_metadata(value)

    def test_capture_ids_cannot_escape_root(self):
        for capture_id in ("../escape", "a/b", "a\\b", "", "a" * 81, "BadName", ".."):
            with self.subTest(capture_id=capture_id), self.assertRaises(ValueError):
                self.ingest(capture_id)

    def test_live_source_changes_during_intake_are_rejected(self):
        real_read = capture.stable_read
        calls = {}
        def changing_read(path):
            calls[path] = calls.get(path, 0) + 1
            raw = real_read(path)
            if path == self.snapshot and calls[path] > 1:
                return raw + b"changed"
            return raw
        with patch.object(capture, "stable_read", side_effect=changing_read):
            with self.assertRaisesRegex(ValueError, "changed during capture intake"):
                self.ingest()
        self.assertFalse((self.output / "map001-test-01").exists())

    def test_legacy_lock_is_not_modified_or_used_as_new_identity(self):
        legacy = capture.PROJECT / "savestate-lock.json"
        before = legacy.read_bytes()
        directory, result = self.archive()
        self.assertNotEqual(capture.read_json_bytes(before)["sha256"], result["snapshot_sha256"])
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(capture.verify(directory), result)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            capture.read_json_bytes(b'{"schema":"new", "schema":"old"}')

    def test_register_schema_matches_existing_reader_contract(self):
        legacy = capture.read_json_bytes((capture.PROJECT / "savestate-lock.json").read_bytes())
        self.assertEqual(capture.REGISTERS2, legacy["registers2"])
        self.assertEqual(len(capture.REGISTERS2), 142)


class SourcePinTests(unittest.TestCase):
    def setUp(self):
        temporary_root = capture.PROJECT / "reports/tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="exploration-sources-tests-", dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.disc = self.root / "disc"
        self.disc.mkdir()
        (self.disc / "audio").mkdir()
        self.cue = self.disc / "game.cue"
        self.cue.write_text('FILE "track 01.bin" BINARY\n  TRACK 01 MODE1/2352\n'
                            'FILE "audio/track02.bin" BINARY\n  TRACK 02 AUDIO\n', encoding="utf-8")
        (self.disc / "track 01.bin").write_bytes(b"synthetic sector data")
        (self.disc / "audio/track02.bin").write_bytes(b"synthetic audio sectors")
        self.bios = self.root / "bios.bin"
        self.ymir = self.root / "ymir.exe"
        self.harness = self.root / "harness.exe"
        self.config = self.root / "Ymir.toml"
        self.build = self.root / "build.json"
        for path in (self.bios, self.ymir, self.harness):
            path.write_bytes(("synthetic " + path.name).encode())
        self.config.write_text("StartPaused = true\n", encoding="utf-8")
        self.build.write_bytes(capture.json_bytes({"ymir_commit": "synthetic", "compiler": "fixture"}))
        self.out = self.root / "sources.json"

    def pin(self, with_build=True):
        return capture.pin_sources(self.cue, self.bios, self.ymir, self.config, self.out,
                                   self.harness if with_build else None, self.build if with_build else None)

    def test_multitrack_pin_and_online_source_reverification(self):
        result = self.pin()
        self.assertEqual(result["disc_files"], 2)
        self.assertTrue(result["harness_pinned"])
        self.assertTrue(result["build_metadata_pinned"])
        self.assertFalse(result["e1_passed"])
        self.assertEqual(capture.verify_sources(self.out, result["manifest_sha256"]), result)
        manifest = capture.read_json_bytes(self.out.read_bytes())
        self.assertEqual(manifest["disc_files"][1]["cue_reference"], "audio/track02.bin")
        self.assertEqual(manifest["build_metadata"]["compiler"], "fixture")
        self.assertEqual(set(manifest["inputs"]), {"cue", "bios", "ymir", "config", "harness", "source_manifest"})

    def test_optional_harness_is_explicit_and_existing_pin_is_immutable(self):
        result = self.pin(with_build=False)
        self.assertFalse(result["harness_pinned"])
        self.assertFalse(result["build_metadata_pinned"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.pin()
        self.assertEqual(capture.verify_sources(self.out), result)

    def test_each_source_role_and_track_changes_are_rejected(self):
        self.pin()
        for path in (self.cue, self.bios, self.ymir, self.config, self.harness, self.build,
                     self.disc / "track 01.bin", self.disc / "audio/track02.bin"):
            original = path.read_bytes()
            # Keep JSON/CUE parseable while changing identity.
            path.write_bytes(original + b" ")
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, "changed"):
                capture.verify_sources(self.out)
            path.write_bytes(original)

    def test_missing_track_and_bios_rejected_before_output(self):
        track = self.disc / "track 01.bin"
        original = track.read_bytes()
        track.unlink()
        with self.assertRaises(FileNotFoundError):
            self.pin()
        self.assertFalse(self.out.exists())
        track.write_bytes(original)
        self.bios.unlink()
        with self.assertRaises(FileNotFoundError):
            self.pin()
        self.assertFalse(self.out.exists())

    def test_cue_references_cannot_escape_or_use_absolute_and_alternate_paths(self):
        cases = ["../bios.bin", "audio/../../bios.bin", "C:/bios.bin", "C:relative.bin",
                 "//server/share/track.bin", "/absolute.bin", "audio//track02.bin", "./track 01.bin",
                 "track.bin:stream.bin", "audio\\..\\track01.bin"]
        for reference in cases:
            self.cue.write_text(f'FILE "{reference}" BINARY\n', encoding="utf-8")
            with self.subTest(reference=reference), self.assertRaisesRegex(ValueError, "CUE path"):
                self.pin()
            self.assertFalse(self.out.exists())

    def test_unsupported_or_empty_cue_cannot_omit_disc_sources(self):
        for contents in ('REM empty\n', 'FILE "track 01.bin" WAVE\n', 'FILE "broken.bin"\n',
                         'FILE "audio.wav" BINARY\n'):
            self.cue.write_text(contents, encoding="utf-8")
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                self.pin()
            self.assertFalse(self.out.exists())

    def test_source_mutation_during_two_pass_intake_is_rejected(self):
        original = capture.stable_fingerprint
        track = self.disc / "track 01.bin"
        mutated = False
        def changing_fingerprint(path):
            nonlocal mutated
            result = original(path)
            if path == track and not mutated:
                mutated = True
                track.write_bytes(b"later generation of this track")
            return result
        with patch.object(capture, "stable_fingerprint", side_effect=changing_fingerprint):
            with self.assertRaisesRegex(ValueError, "changed during provenance"):
                self.pin()
        self.assertFalse(self.out.exists())

    def test_source_write_during_stream_hash_is_rejected(self):
        hasher = capture.hashlib.sha256()
        class MutatingHash:
            changed = False
            def update(inner, block):
                hasher.update(block)
                if not inner.changed:
                    inner.changed = True
                    with self.bios.open("ab") as handle:
                        handle.write(b"changed during read")
            def hexdigest(inner):
                return hasher.hexdigest()
        with patch.object(capture.hashlib, "sha256", return_value=MutatingHash()):
            with self.assertRaisesRegex(ValueError, "changed while hashing"):
                capture.stable_fingerprint(self.bios)

    def test_manifest_external_pin_and_source_roles_are_checked(self):
        result = self.pin()
        original = self.out.read_bytes()
        self.out.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "manifest SHA256 mismatch"):
            capture.verify_sources(self.out, result["manifest_sha256"])
        manifest = capture.read_json_bytes(original)
        manifest["inputs"].pop("bios")
        self.out.write_bytes(capture.json_bytes(manifest))
        with self.assertRaisesRegex(ValueError, "roles"):
            capture.verify_sources(self.out)

    def test_tampered_disc_list_and_relative_manifest_path_are_rejected(self):
        self.pin()
        original = capture.read_json_bytes(self.out.read_bytes())
        changed = dict(original)
        changed["disc_files"] = original["disc_files"][:-1]
        self.out.write_bytes(capture.json_bytes(changed))
        with self.assertRaisesRegex(ValueError, "changed"):
            capture.verify_sources(self.out)
        original["inputs"]["bios"]["path"] = "bios.bin"
        self.out.write_bytes(capture.json_bytes(original))
        with self.assertRaisesRegex(ValueError, "must be absolute"):
            capture.verify_sources(self.out)


if __name__ == "__main__":
    unittest.main()
