"""Furniture alpha, color and source-anchor tests use no original files."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from export_character_scene_props import decode_piece, compose_pieces, export


class FurniturePixelsTests(unittest.TestCase):
    def setUp(self):
        self.cram = bytearray(4096)
        struct.pack_into('>3H', self.cram, 0xe40, 0, 31, 31 << 5)
        self.regs = {'SPCTL': 0x36, 'RAMCTL': 0x1100, 'CCCTL': 8, 'CLOFEN': 95,
                     'COAR': 0, 'COAG': 0, 'COAB': 0, 'CLOFSL': 0, 'CRAOFB': 0x40,
                     'PRISA': 0x0107, 'PRISB': 0x0302, 'PRISC': 0x0504, 'PRISD': 0x0706}

    def test_source_palette_transparency_and_mirror(self):
        image = decode_piece(b'\0\1\2\0', 2, 2, 4, 0x2720, self.cram, self.regs)
        self.assertEqual(list(image.getdata()), [(0, 0, 0, 0), (248, 0, 0, 255), (0, 248, 0, 255), (0, 0, 0, 0)])
        mirrored = decode_piece(b'\0\1\2\0', 2, 2, 4, 0x2720, self.cram, self.regs, True)
        self.assertEqual(mirrored.getpixel((0, 0)), (248, 0, 0, 255))

    def test_invalid_sizes_indices_and_palette(self):
        for indices, width, height, bits, colr in [(b'', 0, 1, 4, 0x2720), (b'\1', 2, 1, 4, 0x2720),
                                                 (b'\x10', 1, 1, 4, 0x2720), (b'\1', 1, 1, 8, 0x2720),
                                                 (b'\1', 1, 1, 4, 0x2721)]:
            with self.subTest(width=width, bits=bits), self.assertRaises(ValueError):
                decode_piece(indices, width, height, bits, colr, self.cram, self.regs)

    def test_negative_source_offsets_preserve_object_anchor(self):
        red = Image.new('RGBA', (2, 3), (248, 0, 0, 255))
        green = Image.new('RGBA', (1, 1), (0, 248, 0, 255))
        image, anchor = compose_pieces([(red, (-2, -3)), (green, (1, -1))])
        self.assertEqual(anchor, [2, 3])
        self.assertEqual(image.size, (4, 3))
        self.assertEqual(image.getpixel((3, 2)), (0, 248, 0, 255))
        self.assertEqual(image.getpixel((2, 0))[3], 0)

    def test_source_piece_order_overwrites_only_opaque_pixels(self):
        red = Image.new('RGBA', (2, 1), (248, 0, 0, 255))
        overlay = Image.new('RGBA', (2, 1))
        overlay.putpixel((1, 0), (0, 248, 0, 255))
        result, _ = compose_pieces([(red, (-1, 0)), (overlay, (-1, 0))])
        self.assertEqual(list(result.getdata()), [(248, 0, 0, 255), (0, 248, 0, 255)])

    def test_empty_and_excessive_composition_rejected(self):
        with self.assertRaises(ValueError):
            compose_pieces([])
        with self.assertRaises(ValueError):
            compose_pieces([(Image.new('RGBA', (1, 1)), (2049, 0))])

    def test_incomplete_order_proof_rejected_without_output(self):
        root = Path(__file__).resolve().parents[1] / 'reports/tmp'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            path = Path(folder)
            proof = path / 'order.json'
            proof.write_text('{"schema":"ao_character_draw_order_validation_v1","passed":true,"frame_count":32}', encoding='utf-8')
            out = path / 'export'
            with self.assertRaisesRegex(ValueError, '684-frame'):
                export(path / 'absent-capture', proof, out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
