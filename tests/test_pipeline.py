import copy
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pipeline as p


def texture(tag=0x11, index=0):
    return struct.pack(">4H", tag, index, 0, 0x0108) + bytes(range(64 if tag == 0x11 else 32))


class ImportTests(unittest.TestCase):
    def test_mixed_texture_depth_and_nibble_order(self):
        records = p.parse_v1n(texture() + texture(1, 1) + b"\0" * 4)
        self.assertEqual([r["bits_per_pixel"] for r in records], [8, 4])
        self.assertEqual(records[1]["payload"][:4], bytes([0, 0, 0, 1]))
        self.assertEqual(records[1]["offset"], 72)

    def test_texture_rejects_truncation_unknown_tag_duplicate_and_trailer(self):
        for data in [texture()[:-1], texture(9) + b"\0"*4,
                     texture()+texture()+b"\0"*4, texture()+b"\0"*8, texture()]:
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                p.parse_v1n(data)

    def test_bounds(self):
        for start, size in [(-1, 1), (0, 0), (1, 2), (False, 1)]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                p.checked_slice(b"ab", start, size)

    def test_lock_detects_mutation_and_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source").write_bytes(b"original")
            self.assertEqual(p.verify_source(root, "source", p.digest(b"original")), b"original")
            with self.assertRaises(ValueError):
                p.verify_source(root, "source", p.digest(b"changed"))
            with self.assertRaises(ValueError):
                p.verify_source(root, "../outside", "")

    def test_actual_sources_and_translation_alignment(self):
        lock = p.read_json(p.PROJECT / "source-lock.json")
        for name, expected in lock["sources"].items():
            p.verify_source(p.WORKSPACE, name, expected)
        source = (p.WORKSPACE / "work/extract/MAP001.TWN").read_bytes()
        descriptor = p.read_json(p.WORKSPACE / "work/analysis/dialogue_twn_all_descriptors.json")
        tsv = (p.WORKSPACE / "translation/zh-TW/dialogue_twn_all.tsv").read_text("utf-8-sig")
        records = p.import_dialogue(source, descriptor, tsv)
        self.assertEqual(len(records), 137)
        self.assertEqual(sum(len(r["pages"]) for r in records), 241)
        with self.assertRaises(ValueError):
            p.import_dialogue(source, descriptor, tsv.replace("It's been ten years, Pike.", "misaligned"))
        broken = copy.deepcopy(descriptor)
        record = next(r for r in broken["records"] if r["source_file"] == "/MAP001.TWN")
        record["pages"][0]["original_hex"] = "00"
        with self.assertRaises(ValueError):
            p.import_dialogue(source, broken, tsv)

    def test_real_v1n_round_trip(self):
        data = (p.WORKSPACE / "work/extract/MAP001.V1N").read_bytes()
        records = p.parse_v1n(data)
        self.assertEqual(len(records), 253)
        self.assertEqual(sum(r["span"] for r in records) + 4, len(data))
        for r in records:
            pixels = r["payload"]
            packed = pixels if r["bits_per_pixel"] == 8 else bytes((a << 4) | b for a, b in zip(pixels[::2], pixels[1::2]))
            self.assertEqual(p.digest(packed), r["packed_sha256"])

    def test_snf_boundary_and_corruption(self):
        data = (p.WORKSPACE / "work/extract/MAP001.SNF").read_bytes()
        self.assertEqual(len(p.parse_snf_directory(data)), 12)
        broken = bytearray(data)
        broken[8:12] = b"\xff"*4
        with self.assertRaises(ValueError):
            p.parse_snf_directory(broken)

    def test_aiff_real_header_and_truncation(self):
        data = (p.WORKSPACE / "work/extract/ACPAIK.AIF").read_bytes()
        result = p.parse_aiff(data)
        self.assertEqual((result["channels"], result["sample_rate"], result["bits"]), (1, 22050, 16))
        with self.assertRaises(ValueError):
            p.parse_aiff(data[:-2])


if __name__ == "__main__":
    unittest.main()
