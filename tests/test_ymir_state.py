import copy
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import read_ymir_state as y


class StateTests(unittest.TestCase):
    def test_pinned_region_registers_and_memory(self):
        lock = y.read_json(y.PROJECT / "savestate-lock.json")
        data = (y.WORKSPACE / lock["path"]).read_bytes()
        state = y.extract(data, lock)
        self.assertEqual(state["regs1"]["COPR"] * 8, 0x400)
        self.assertEqual(state["next_command_address"], 0x400)
        self.assertEqual(state["regs2"]["SPCTL"], 0x36)
        self.assertEqual(state["regs2"]["RAMCTL"], 0x1100)
        self.assertEqual(state["regs2"]["CRAOFB"], 0x40)
        self.assertTrue(state["drawing"])
        self.assertEqual(state["blocks"]["vram1"][:2], b"\x50\0")
        self.assertEqual(len(state["blocks"]["cram"]), 4096)

    def test_rejects_changed_truncated_version_and_boundary(self):
        lock = y.read_json(y.PROJECT / "savestate-lock.json")
        data = (y.WORKSPACE / lock["path"]).read_bytes()
        for broken in [data[:-1], data[:-1] + bytes([data[-1] ^ 1])]:
            with self.assertRaises(ValueError):
                y.extract(broken, lock)
        for key, value in [("version", 14), ("vdp_payload_offset", 100)]:
            changed = copy.deepcopy(lock)
            changed[key] = value
            with self.assertRaises(ValueError):
                y.extract(data, changed)

    def fixture(self):
        row = {"color_mode": 0, "pmod": 128, "width": 8, "height": 1,
               "texture_offset": 0, "colr": 0x3010}
        regs1 = {"TVMR": 0}
        regs2 = {"RAMCTL": 0x1000, "SPCTL": 6, "CRAOFB": 0x40, "CLOFEN": 0, "CLOFSL": 0}
        cram = bytearray(4096)
        # Sprite type 6 strips priority bits 12..14; bank 0x3010 -> index 0x410.
        struct.pack_into(">H", cram, 0x411*2, 0x001f)
        struct.pack_into(">H", cram, 0x412*2, 0x03e0)
        struct.pack_into(">H", cram, 0x413*2, 0x7c00)
        struct.pack_into(">H", cram, 0x414*2, 0x4210)
        return row, bytes([0x01, 0x23, 0x40, 0x00]), cram, regs1, regs2

    def test_bank_priority_mask_rgb_and_transparency(self):
        image = y.palette_texture(*self.fixture())
        self.assertEqual(list(image.getdata())[:4], [(0, 0, 0, 0), (255, 0, 0, 255),
                                                      (0, 255, 0, 255), (0, 0, 255, 255)])
        self.assertEqual(image.getpixel((4, 0)), (132, 132, 132, 255))
        row, _, cram, r1, r2 = self.fixture()
        row["color_mode"] = 2
        image8 = y.palette_texture(row, bytes([0x11, 0x51, 0, 0, 0, 0, 0, 0]), cram, r1, r2)
        self.assertEqual(image8.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(image8.getpixel((1, 0)), (255, 0, 0, 255))

    def test_signed_color_offsets_and_clamp(self):
        row, ram, cram, r1, r2 = self.fixture()
        r2.update(CLOFEN=64, COAR=0x1f0, COAG=20, COAB=0)
        image = y.palette_texture(row, ram, cram, r1, r2)
        self.assertEqual(image.getpixel((1, 0)), (239, 20, 0, 255))
        self.assertEqual(image.getpixel((2, 0)), (0, 255, 0, 255))

    def test_unsupported_modes_and_bounds_do_not_fallback(self):
        for field, value in [("color_mode", 1), ("pmod", 0), ("pmod", 0x180), ("colr", 0x8000),
                             ("texture_offset", 100)]:
            args = list(self.fixture())
            args[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                y.palette_texture(*args)
        args = list(self.fixture())
        args[4]["SPCTL"] = 5
        with self.assertRaises(ValueError):
            y.palette_texture(*args)

    def test_real_palette_samples_remain_diagnostic(self):
        report = y.run()
        self.assertEqual(report["summary"]["palette_samples"], 6)
        self.assertEqual(report["trace_failure"]["offset"], 0x2e00)
        self.assertTrue(all(s["palette_status"] == "decoded_intrinsic_texture" for s in report["samples"]))


if __name__ == "__main__":
    unittest.main()
