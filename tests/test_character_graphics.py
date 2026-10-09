"""Independent small pixel/stream oracles; no old savestate fixture required."""
from __future__ import annotations

import copy
from pathlib import Path
import struct
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import character_graphics as graphics


class DecoderTests(unittest.TestCase):
    def test_literal_and_control_bit_order(self):
        self.assertEqual(graphics.decompress_texture(b'\x05A\0\0Z', 5), (b'A\0\0\0Z', 5))

    def test_overlapping_copy(self):
        self.assertEqual(graphics.decompress_texture(b'\x01A\x01\x02', 6), (b'AAAAAA', 4))

    def test_distance_high_nibble_is_not_length(self):
        encoded = (b'\xff' + b'X' * 8) * 32 + b'\x01Z\x01\x10'
        self.assertEqual(graphics.decompress_texture(encoded, 260)[0], b'X' * 256 + b'ZXXX')

    def test_copy_returns_immediately_at_output_length(self):
        self.assertEqual(graphics.decompress_texture(b'\x00\x00\x0f', 2), (b'\0\0', 3))

    def test_uninitialized_stack_tail_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'uninitialized'):
            graphics.decompress_texture(b'\0\1\0', 3)

    def test_truncated_control_literal_and_reference_rejected(self):
        for stream in (b'', b'\1', b'\0', b'\0\1'):
            with self.subTest(stream=stream), self.assertRaises(ValueError):
                graphics.decompress_texture(stream, 3)

    def test_output_bounds(self):
        for count in (0, -1, 0x80001, True, 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                graphics.decompress_texture(b'\1A', count)

    def test_ring_wrap_uses_recent_output(self):
        stream = (b'\xff' + b'A' * 8) * 512 + b'\x01Z\1\0'
        self.assertEqual(graphics.decompress_texture(stream, 4100)[0], b'A' * 4096 + b'ZZZZ')


class PixelTests(unittest.TestCase):
    def setUp(self):
        self.texture = graphics.Texture(4, 2, 2, 123, 7, bytes([0, 1, 2, 3]))
        self.cram = bytearray(4096)
        struct.pack_into('>4H', self.cram, 0x800, 0x7fff, 31, 31 << 5, 31 << 10)
        self.r1 = {'TVMR': 0}
        self.r2 = {'RAMCTL': 0x1100, 'SPCTL': 0x36, 'CRAOFB': 0x40,
                   'CLOFEN': 64, 'CLOFSL': 0, 'COAR': 0, 'COAG': 0, 'COAB': 0}

    def image(self, **kwargs):
        return graphics.rgba_texture(self.texture, bytes(self.cram), self.r1, self.r2,
                                     kwargs.get('colr', 0x2000), kwargs.get('pmod', 0x1090))

    def test_known_palette_rgb_and_transparency(self):
        self.assertEqual(list(self.image().getdata()), [(0, 0, 0, 0), (248, 0, 0, 255),
                                                       (0, 248, 0, 255), (0, 0, 248, 255)])

    def test_signed_color_offset_and_clamp(self):
        self.r2.update(COAR=0x1f8, COAG=16)
        self.assertEqual(self.image().getpixel((1, 0)), (240, 16, 0, 255))
        self.assertEqual(self.image().getpixel((0, 1)), (0, 255, 0, 255))

    def test_unsupported_hardware_modes_rejected(self):
        for register, value in [('RAMCTL', 0x2000), ('SPCTL', 0x35)]:
            with self.subTest(register=register), self.assertRaises(ValueError):
                graphics.rgba_texture(self.texture, self.cram, self.r1, self.r2 | {register: value}, 0x2000, 0x1090)
        for pmod in (0x1010, 0x1190, 0x9090, 0x1091):
            with self.subTest(pmod=pmod), self.assertRaises(ValueError):
                self.image(pmod=pmod)

    def test_truncated_palette_rejected(self):
        with self.assertRaises(ValueError):
            graphics.rgba_texture(self.texture, self.cram[:-1], self.r1, self.r2, 0x2000, 0x1090)

    def test_both_mirror_axes_preserve_exact_pixels(self):
        source = self.image()
        horizontal = graphics.oriented_image(source, {'flip_x': True, 'flip_y': False})
        both = graphics.oriented_image(source, {'flip_x': True, 'flip_y': True})
        self.assertEqual(horizontal.getpixel((0, 0)), source.getpixel((1, 0)))
        self.assertEqual(both.getpixel((0, 0)), source.getpixel((1, 1)))
        self.assertEqual(source.getpixel((0, 0)), (0, 0, 0, 0))

    def test_visible_oracle_ignores_only_transparent_pixels(self):
        image = self.image()
        video = bytearray(image.tobytes())
        video[:4] = b'\1\2\3\xff'
        result = graphics.compare_visible(image, (0, 0), bytes(video), 2, 2)
        self.assertTrue(result['passed'])
        self.assertEqual(result['matching_opaque_pixels'], 3)
        video[4] = 247
        result = graphics.compare_visible(image, (0, 0), bytes(video), 2, 2)
        self.assertFalse(result['passed'])
        self.assertEqual(result['mismatched_opaque_pixels'], 1)

    def test_clipping_and_empty_images_cannot_claim_pass(self):
        self.assertFalse(graphics.compare_visible(self.image(), (1, 0), self.image().tobytes(), 2, 2)['passed'])
        empty = Image.new('RGBA', (2, 2))
        self.assertFalse(graphics.compare_visible(empty, (0, 0), bytes(16), 2, 2)['passed'])
        with self.assertRaises(ValueError):
            graphics.compare_visible(self.image(), (0, 0), bytes(15), 2, 2)


class CommandBindingTests(unittest.TestCase):
    def setUp(self):
        self.actor = bytearray(112)
        struct.pack_into('>hh', self.actor, 0, 100 * 16, 60 * 16)
        self.texture = graphics.Texture(4, 8, 3, 123, 7, bytes(range(24)))
        self.piece = {'offset': [-4, -2], 'attributes': 0}
        self.row = {'kind': 'command', 'command': 2, 'color_mode': 2, 'width': 8, 'height': 3,
                    'local_coordinate': [10, 10], 'signed_coordinates': [86, 48, 93, 48, 93, 50, 86, 50],
                    'texture_offset': 32, 'flip_x': False, 'flip_y': False}
        self.vram = bytes(32) + self.texture.indices

    def bind(self, rows=None, vram=None, piece=None):
        return graphics.bind_command(piece or self.piece, self.texture, self.actor, (0, 0),
                                     rows if rows is not None else [self.row], self.vram if vram is None else vram)

    def test_source_anchor_and_local_coordinates(self):
        result = self.bind()
        self.assertEqual(result['screen_anchor'], [100, 60])
        self.assertEqual(result['screen_origin'], [96, 58])
        self.assertEqual(result['source_anchor'], [4, 2])

    def test_ambiguous_or_absent_commands_rejected(self):
        for rows in ([], [self.row, self.row], [self.row | {'kind': 'skip'}]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                self.bind(rows=rows)

    def test_shadow_and_wrong_anchor_not_body(self):
        shadow = copy.deepcopy(self.row)
        shadow['signed_coordinates'][5] -= 1
        with self.assertRaises(ValueError):
            self.bind(rows=[shadow])

    def test_changed_texture_or_truncation_rejected(self):
        for vram in (self.vram[:-1], self.vram[:-1] + b'\xff'):
            with self.assertRaises(ValueError):
                self.bind(vram=vram)

    def test_unknown_piece_attributes_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unverified'):
            self.bind(piece=self.piece | {'attributes': 0x301})

    def test_negative_coordinates_truncate_towards_zero(self):
        self.assertEqual([graphics.divide16(v) for v in [-17, -15, 15, 17]], [-1, 0, 0, 1])


class SourceGuardTests(unittest.TestCase):
    def test_changed_or_truncated_sources_rejected(self):
        for raw in (b'', b'synthetic source', bytes(12)):
            with self.subTest(raw=len(raw)), self.assertRaisesRegex(ValueError, 'Changed source'):
                graphics.PlayerResource(raw, b'', b'')

    def test_invalid_span_rejected(self):
        for start, count in [(-1, 1), (1, 2), (0, 0), (0, 1.0)]:
            with self.subTest(start=start, count=count), self.assertRaises(ValueError):
                graphics.span(b'ab', start, count)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        raw = struct.pack('>16H', 0x1002, 0, 0x1080, 0x2720, 0, 0x0102,
                          10, 20, 17, 20, 17, 21, 10, 21, 0, 0)
        self.row = graphics.executed_command(raw, 32, (0, 0))

    def test_four_bit_nibble_and_transparent_texel(self):
        pixels = bytes.fromhex('0123456789abcdef')
        self.assertIsNone(graphics.rectangular_code(self.row, pixels, 10, 20))
        self.assertEqual(graphics.rectangular_code(self.row, pixels, 11, 20), 0x2721)
        self.assertEqual(graphics.rectangular_code(self.row, pixels, 17, 21), 0x272f)
        self.assertIsNone(graphics.rectangular_code(self.row, pixels, 18, 21))

    def test_four_bit_mirrored_source_index(self):
        row = self.row | {'flip_x': True, 'flip_y': True}
        self.assertEqual(graphics.rectangular_code(row, bytes.fromhex('0123456789abcdef'), 10, 20), 0x272f)

    def test_distortion_and_incomplete_overlap_rejected(self):
        row = copy.deepcopy(self.row)
        row['signed_coordinates'][2] -= 1
        with self.assertRaisesRegex(ValueError, 'distortion'):
            graphics.rectangular_code(row, bytes(8), 11, 20)
        with self.assertRaisesRegex(ValueError, 'truncated'):
            graphics.rectangular_code(self.row, bytes(7), 11, 20)

    def test_executed_end_skip_truncation_rejected(self):
        for raw in (bytes(31), b'\x80\0' + bytes(30), b'\x40\0' + bytes(30)):
            with self.assertRaises(ValueError):
                graphics.executed_command(raw, 32, (0, 0))

    def test_framebuffer_comparison_catches_other_sprite_code(self):
        texture = graphics.Texture(0, 2, 1, 0, 0, b'\1\0')
        command = self.row | {'screen_origin': [0, 0], 'colr': 0x2000, 'pmod': 0x1090}
        fb = bytearray(0x40000)
        struct.pack_into('>H', fb, 0, 0x2001)
        self.assertTrue(graphics.compare_framebuffer(texture, command, fb)['passed'])
        struct.pack_into('>H', fb, 0, 0x2721)
        self.assertFalse(graphics.compare_framebuffer(texture, command, fb)['passed'])
        with self.assertRaises(ValueError):
            graphics.compare_framebuffer(texture, command, fb[:-1])

    def test_source_pattern_priority_and_mirror(self):
        bg = graphics.BackgroundSource.__new__(graphics.BackgroundSource)
        bg.layout = bytearray(65536)
        struct.pack_into('>H', bg.layout, 0, 0x6000)
        bg.tiles = bytearray(256)
        bg.tiles[64 + 7] = 1  # reflected (15,0), second 8x8 cell
        bg.palette = b'\0\0\0\x1f' + bytes(508)
        result = bg.pixel(0, 0, 0)
        self.assertEqual(result['rgba'], (248, 0, 0, 255))
        self.assertEqual(result['priority'], 3)
        self.assertEqual(bg.pixel(0, 1, 0)['rgba'][3], 0)
        with self.assertRaises(ValueError):
            bg.pixel(0, 2048, 0)


if __name__ == '__main__':
    unittest.main()
