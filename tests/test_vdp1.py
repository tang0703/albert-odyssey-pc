import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import trace_vdp1 as v


def command(ctrl, link=0, pmod=0, colr=0, src=0, size=0, x=0, y=0):
    return struct.pack(">16H", ctrl, link, pmod, colr, src, size, x & 65535, y & 65535, *([0] * 8))


class CommandTests(unittest.TestCase):
    def test_end_overrides_invalid_command_and_jump(self):
        self.assertEqual(v.trace(command(0xffff))[0]["kind"], "end")

    def test_skip_assign_ignores_unreachable_invalid_command(self):
        rows = v.trace(command(0x500f, 8) + command(15) + command(0x8000))
        self.assertEqual([r["offset"] for r in rows], [0, 64])
        self.assertEqual(rows[0]["kind"], "skip")

    def test_call_return_and_skip_variants(self):
        for call, ret in [(0x200a, 0x300a), (0x600a, 0x700a)]:
            with self.subTest(call=call):
                rows = v.trace(command(call, 8) + command(0x8000) + command(ret))
                self.assertEqual([r["offset"] for r in rows], [0, 64, 32])

    def test_cycle_bounds_alignment_nested_and_orphan_return(self):
        cases = [command(0x1000), command(0x1000, 100), command(0x1000, 1),
                 command(0x2000, 4) + command(0x2000, 8), command(0x3000), command(15)]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(v.TraceError):
                v.trace(data)

    def test_budget_and_truncated(self):
        with self.assertRaisesRegex(v.TraceError, "budget"):
            v.trace(command(10) + command(0x8000), max_steps=1)
        with self.assertRaises(v.TraceError):
            v.trace(b"\0" * 31)

    def test_skipped_local_does_not_change_origin(self):
        rows = v.trace(command(10, x=-12, y=5) + command(0x400a, x=9, y=8)
                       + command(0x0032, pmod=0xc0) + command(0x8000))
        self.assertEqual(rows[2]["local_coordinate"], [-12, 5])
        self.assertTrue(rows[2]["flip_x"] and rows[2]["flip_y"])
        self.assertTrue(rows[2]["transparent_pixel_disabled"])
        self.assertTrue(rows[2]["end_code_disabled"])

    def test_binding_requires_bytes_dimensions_depth_and_keeps_duplicates(self):
        pixels = bytes(range(32))
        source = b"".join(struct.pack(">4H", 1, i, 0, 0x0108) + pixels for i in [2, 3]) + b"\0"*4
        ram = command(0, src=8, size=0x0108) + command(0x8000) + pixels
        binding = v.bind_textures(v.trace(ram), ram, source)[0]
        self.assertEqual(binding["source_ids"], ["map001_v1n_0002", "map001_v1n_0003"])
        changed = ram[:-1] + b"\xff"
        self.assertEqual(v.bind_textures(v.trace(changed), changed, source)[0]["source_ids"], [])
        # Same bytes and area with a different shape must not bind.
        reshaped = command(0, src=8, size=0x0204) + ram[32:]
        self.assertEqual(v.bind_textures(v.trace(reshaped), reshaped, source)[0]["source_ids"], [])
        with self.assertRaises(ValueError):
            v.bind_textures(v.trace(ram), ram[:-1], source)

    def test_reference_is_rejected_and_keeps_partial_evidence(self):
        report = v.run()
        self.assertEqual(report["summary"]["list_status"], "rejected_incomplete")
        self.assertIsNone(report["summary"]["end_offset"])
        self.assertEqual(report["failure"]["offset"], 0x2e60)
        self.assertEqual(report["summary"]["bound_texture_commands"], 9)
        self.assertEqual(report["commands"][1]["offset"], 0x2aa0)

    def test_locked_capture_inventory(self):
        report = v.audit_captures()
        self.assertEqual(report["summary"], {"rejected_incomplete": 8, "inventory_only": 3})
        self.assertTrue(all(not c["synchronization_verified"] for c in report["captures"]
                            if c["status"] == "inventory_only"))


if __name__ == "__main__":
    unittest.main()
