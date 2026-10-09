"""Independent pixel expectations and rejection tests without original art."""
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from validate_character_runtime_pixels import compose, project_video, compare, read_pinned, layer_order
from character_graphics import sha


class RuntimePixelTests(unittest.TestCase):
    def setUp(self):
        self.bg = Image.new('RGBA', (3, 1), (8, 16, 24, 255))
        self.fg = Image.new('RGBA', (3, 1))
        self.fg.putpixel((1, 0), (24, 32, 40, 255))

    def layer(self, color, priority, serial, x=0, width=3):
        return {'image': Image.new('RGBA', (width, 1), color), 'priority': priority,
                'order': serial, 'rect': [x, 0, width, 1]}

    def test_late_low_priority_replaces_earlier_high_with_background(self):
        high = self.layer((248, 0, 0, 255), 3, 1)
        low = self.layer((0, 248, 0, 255), 2, 2)
        actual = compose(self.bg, self.fg, [low, high])
        self.assertEqual(list(actual.getdata()), [(0, 248, 0, 255), (24, 32, 40, 255), (0, 248, 0, 255)])

    def test_late_high_priority_wins_foreground_tie(self):
        high = self.layer((248, 0, 0, 255), 3, 2)
        low = self.layer((0, 248, 0, 255), 2, 1)
        self.assertEqual(list(compose(self.bg, self.fg, [high, low]).getdata()), [(248, 0, 0, 255)] * 3)

    def test_transparent_late_pixel_preserves_earlier_sprite(self):
        high = self.layer((248, 0, 0, 255), 3, 1)
        low = self.layer((0, 248, 0, 255), 2, 2)
        low['image'].putpixel((1, 0), (0, 0, 0, 0))
        self.assertEqual(compose(self.bg, self.fg, [high, low]).getpixel((1, 0)), (248, 0, 0, 255))

    def test_offscreen_sprite_clips_without_moving_source_pixels(self):
        layer = self.layer((248, 0, 0, 255), 3, 1, x=-1, width=2)
        actual = compose(self.bg, self.fg, [layer])
        self.assertEqual(actual.getpixel((0, 0)), (248, 0, 0, 255))
        self.assertEqual(actual.getpixel((1, 0)), self.bg.getpixel((1, 0)))

    def test_invalid_order_alpha_priority_or_geometry_rejected(self):
        a = self.layer((248, 0, 0, 255), 2, 1)
        b = self.layer((0, 248, 0, 255), 2, 1)
        with self.assertRaisesRegex(ValueError, 'order'):
            compose(self.bg, self.fg, [a, b])
        for layer in [self.layer((1, 2, 3, 128), 2, 1), self.layer((1, 2, 3, 255), 4, 1)]:
            with self.assertRaises(ValueError):
                compose(self.bg, self.fg, [layer])
        a['rect'][2] = 2
        with self.assertRaisesRegex(ValueError, 'geometry'):
            compose(self.bg, self.fg, [a])

    def test_expected_colors_come_from_video_not_sprite_or_compositor(self):
        video = Image.new('RGBA', (4, 2), (0, 0, 0, 255))
        video.putpixel((1, 0), (80, 88, 96, 255))
        video.putpixel((2, 1), (104, 112, 120, 255))
        body = Image.new('RGBA', (2, 2), (248, 0, 0, 255))
        body.putpixel((0, 1), (0, 0, 0, 0))
        expected, mask = project_video(video.tobytes(), body, [1, 0], [11, 20], (4, 2), (10, 20))
        self.assertEqual(expected.getpixel((2, 0)), (80, 88, 96, 255))
        self.assertEqual(expected.getpixel((3, 1)), (104, 112, 120, 255))
        self.assertEqual(mask.getpixel((2, 1))[3], 0)
        self.assertEqual(sum(a > 0 for a in mask.getchannel('A').getdata()), 3)

    def test_expected_source_or_destination_clipping_is_rejected(self):
        body = Image.new('RGBA', (1, 1), (248, 0, 0, 255))
        video = Image.new('RGBA', (2, 1), (0, 0, 0, 255)).tobytes()
        for origin, camera in [([-1, 0], [0, 0]), ([1, 0], [1, 0])]:
            with self.assertRaisesRegex(ValueError, 'viewport'):
                project_video(video, body, origin, camera, (2, 1), (0, 0))

    def test_truncated_video_and_empty_mask_cannot_pass(self):
        body = Image.new('RGBA', (1, 1), (248, 0, 0, 255))
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            project_video(b'', body, [0, 0], [0, 0], (1, 1), (0, 0))
        blank = Image.new('RGBA', (1, 1))
        with self.assertRaisesRegex(ValueError, 'empty'):
            project_video(bytes([0, 0, 0, 255]), blank, [0, 0], [0, 0], (1, 1), (0, 0))
        with self.assertRaisesRegex(ValueError, 'empty'):
            compare(blank, blank, blank)

    def test_known_wrong_rgb_cannot_pass_comparison(self):
        actual = Image.new('RGBA', (2, 1), (8, 8, 8, 255))
        expected = actual.copy()
        expected.putpixel((0, 0), (16, 8, 8, 255))
        mask = Image.new('RGBA', (2, 1), (255, 255, 255, 255))
        result = compare(actual, expected, mask)
        self.assertFalse(result['passed'])
        self.assertEqual(result['mismatches'], 1)
        self.assertEqual(result['examples'][0]['pixel'], [0, 0])

    def test_modified_or_truncated_source_rejected(self):
        temporary_root = Path(__file__).resolve().parents[1] / 'reports/tmp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as folder:
            path = Path(folder) / 'video.bin'
            path.write_bytes(b'original')
            identity = sha(b'original')
            self.assertEqual(read_pinned(path, identity), b'original')
            for content in (b'originaX', b'orig'):
                path.write_bytes(content)
                with self.assertRaisesRegex(ValueError, 'changed'):
                    read_pinned(path, identity)

    def test_objects_before_actor_tie_and_bucket_collision(self):
        props = [{'slot': 0, 'world_xy_raw': [100, 1600 * 16], 'y_sorted': True},
                 {'slot': 1, 'world_xy_raw': [100, 1600 * 16 + 16], 'y_sorted': True}]
        self.assertEqual(layer_order(props, [100, 1600 * 16]), ['object_0:0', 'object_1:0', 'actor_0:0'])


if __name__ == '__main__':
    unittest.main()
