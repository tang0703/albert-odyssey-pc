"""Synthetic geometry, phase, closure and review tests; no original artwork."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import character_hd_art as art


def figure(color=(80, 120, 160, 255)):
    image = Image.new('RGBA', (64, 64))
    ImageDraw.Draw(image).rectangle((24, 16, 39, 55), fill=color)
    return image


class GeometryTests(unittest.TestCase):
    def test_8_connected_alpha_preserves_faint_edge(self):
        image = figure()
        image.putpixel((23, 15), (40, 60, 80, 1))
        result = art.inspect_cell(image)
        self.assertEqual(len(result['components']), 1)
        self.assertEqual(result['alpha_bbox'], [23, 15, 40, 56])

    def test_disconnected_second_figure_rejected(self):
        image = figure()
        ImageDraw.Draw(image).rectangle((4, 20, 12, 40), fill='red')
        with self.assertRaisesRegex(ValueError, 'Multiple'):
            art.inspect_cell(image)

    def test_small_detached_detail_is_retained(self):
        image = figure()
        image.putpixel((20, 20), (40, 80, 120, 255))
        details = art.inspect_cell(image)
        self.assertEqual(len(details['components']), 2)
        normalized = art.normalize(image, [32, 56], 5)
        self.assertGreater(normalized.getpixel((196, 268))[3], 0)

    def test_empty_and_cross_cell_figures_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Empty'):
            art.inspect_cell(Image.new('RGBA', (64, 64)))
        image = figure(); image.putpixel((0, 30), (1, 2, 3, 255))
        with self.assertRaisesRegex(ValueError, 'edge'):
            art.inspect_cell(image)

    def test_variable_size_sheet_and_unused_cells(self):
        sheet = Image.new('RGBA', (256, 256))
        for n in range(13):
            sheet.paste(figure(), (n % 4 * 64, n // 4 * 64))
        frames = art.split_sheet(sheet)
        self.assertEqual(len(frames), 13)
        self.assertEqual(frames[12][1], [0, 192, 64, 256])
        sheet.putpixel((250, 250), (10, 20, 30, 1))
        with self.assertRaisesRegex(ValueError, 'Unused'):
            art.split_sheet(sheet)

    def test_non_integral_sheet_grid_rejected(self):
        with self.assertRaisesRegex(ValueError, 'integral'):
            art.split_sheet(Image.new('RGBA', (1254, 1254)))

    def test_duplicate_detector_ignores_padding_mirror_and_transparent_rgb(self):
        base = figure()
        ImageDraw.Draw(base).rectangle((40, 30, 43, 35), fill=(80, 120, 160, 255))
        shifted = Image.new('RGBA', (100, 100), (200, 200, 0, 0))
        shifted.paste(base.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (15, 7))
        self.assertEqual(art.canonical_pose(base), art.canonical_pose(shifted))

    def test_body_canvas_keeps_ground_anchor_and_never_clips(self):
        normalized = art.normalize(figure(), [32, 56], 10)
        self.assertEqual(normalized.size, (512, 512))
        self.assertEqual(normalized.getchannel('A').getbbox(), (176, 48, 336, 448))
        with self.assertRaisesRegex(ValueError, 'clip'):
            art.normalize(figure(), [32, 56], 12)

    def test_phase_partition_covers_exact_40_updates(self):
        values = [art.frame_contract('left', n) for n in range(12)]
        self.assertEqual([len(v['integer_update_phases']) for v in values], [4, 3, 3] * 4)
        self.assertEqual([p for row in values for p in row['integer_update_phases']], list(range(40)))
        self.assertEqual(values[11]['next_primary_source_index'], 0)
        self.assertEqual(values[11]['phase_interval_numerators'], [110, 120])
        self.assertEqual(art.frame_contract('left', 12)['kind'], 'idle')

    def test_fractional_phase_boundary_is_not_integer_hold_four(self):
        # A render at timer 3 + phase 0.5 has already reached transition 1,
        # although integer samples 0,1,2,3 all belong to primary frame 0.
        self.assertEqual(int((3 + .2) * 3 // 10), 0)
        self.assertEqual(int((3 + .5) * 3 // 10), 1)
        self.assertEqual(art.PHASE['phase_interval_denominator'], 3)

    def test_explicit_noise_cleanup_reduces_alpha_only_and_records_extent(self):
        image = figure(); image.putpixel((0, 0), (123, 45, 67, 2)); image.putpixel((8, 9), (90, 80, 70, 255))
        result, report = art.clean_alpha(image, {'min_alpha': 16, 'min_component_pixels': 16})
        self.assertEqual(report['removed_low_alpha_pixels'], 1)
        self.assertEqual(report['removed_small_component_pixels'], 1)
        self.assertEqual(result.getpixel((0, 0)), (123, 45, 67, 0))
        self.assertEqual(result.getpixel((8, 9)), (90, 80, 70, 0))
        self.assertEqual(result.getpixel((24, 16)), image.getpixel((24, 16)))
        self.assertEqual(report['input_bbox'], [0, 0, 40, 56])
        self.assertEqual(report['output_bbox'], [24, 16, 40, 56])
        art.inspect_cell(result)

    def test_cleanup_disabled_preserves_every_pixel(self):
        image = figure(); image.putpixel((0, 0), (1, 2, 3, 1))
        result, report = art.clean_alpha(image, None)
        self.assertEqual(result.tobytes(), image.tobytes())
        self.assertFalse(report['enabled'])
        with self.assertRaisesRegex(ValueError, 'edge'):
            art.inspect_cell(result)

    def test_cleanup_cannot_remove_large_second_component_or_clipped_body(self):
        image = figure(); ImageDraw.Draw(image).rectangle((0, 20, 6, 30), fill=(20, 30, 40, 255))
        result, report = art.clean_alpha(image, {'min_alpha': 16, 'min_component_pixels': 16})
        self.assertEqual(report['removed_small_component_pixels'], 0)
        with self.assertRaisesRegex(ValueError, 'edge'):
            art.inspect_cell(result)
        with self.assertRaisesRegex(ValueError, 'bounded'):
            art.clean_alpha(image, {'min_alpha': 128, 'min_component_pixels': 200})


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1] / 'reports/tmp'
        root.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=root)
        cls.root = Path(cls.temporary.name)
        refs, directions = {}, {}
        approval = cls.root / 'approval.json'; approval.write_text('{"approved":true}', encoding='utf-8')
        for d, direction in enumerate(art.DIRECTIONS):
            files = {}
            for index, name in enumerate(art.NAMES):
                # Synthetic colored geometry exercises packaging; it is not
                # used as animation artwork or evidence of distinct poses.
                path = cls.root / f'{direction}-{name}.png'
                figure((30 + d * 40, 40 + index * 8, 180, 255)).save(path)
                files[name] = {'path': str(path.resolve()), 'sha256': art.sha(path.read_bytes())}
            refs[direction] = files['idle']
            directions[direction] = {'kind': 'frames', 'files': files,
                'anchors': [{'point': [32, 56], 'confirmed': True, 'evidence': 'Known synthetic rectangle edge'}] * 13}
        spec = {'schema': art.INPUT_SCHEMA, 'character_id': 'map001_player',
            'source_character_manifest_sha256': 'a' * 64, 'scene_manifest_sha256': 'b' * 64,
            'draft_approval': {'approved': True, 'evidence': 'Synthetic test only', 'references': refs,
                'approval_record': {'path': str(approval.resolve()), 'sha256': art.sha(approval.read_bytes())}},
            'normalization': {'maximum_alpha_height': 400,
                'display_scale_by_direction': {d: .0875 for d in art.DIRECTIONS},
                'actor_anchor_by_direction': {d: [256, 460] for d in art.DIRECTIONS}},
            'directions': directions}
        cls.spec = cls.root / 'input.json'; cls.spec.write_bytes(art.encoded(spec))
        cls.folder = cls.root / 'prepared'
        art.prepare(cls.spec, cls.folder)
        cls.manifest_path = cls.folder / 'manifest.json'
        cls.manifest_raw = cls.manifest_path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        self.manifest_path.write_bytes(self.manifest_raw)

    def test_roundtrip_has_52_frames_four_atlases_and_distinct_actor_ground(self):
        result = art.verify(self.folder)
        self.assertEqual((result['frames'], result['atlases'], result['payloads']), (52, 4, 64))
        manifest = json.loads(self.manifest_raw)
        self.assertEqual(manifest['frames'][0]['ground_anchor'], [256, 448])
        self.assertEqual(manifest['frames'][0]['actor_anchor'], [256, 460])

    def test_unreviewed_art_cannot_be_called_approved(self):
        with self.assertRaisesRegex(ValueError, 'review'):
            art.verify(self.folder, require_review=True)

    def test_opt_in_cleanup_keeps_full_resolution_review_artifact_closure(self):
        spec = json.loads(self.spec.read_bytes())
        spec['normalization']['alpha_cleanup'] = {'min_alpha': 16, 'min_component_pixels': 16}
        spec_path = self.root / 'cleanup-input.json'; spec_path.write_bytes(art.encoded(spec))
        output = self.root / 'cleanup-prepared'
        manifest = art.prepare(spec_path, output)
        self.assertEqual(art.verify(output)['payloads'], 116)
        row = manifest['frames'][0]
        cleaned = art.png((output / row['source']['cleaned_source_file']).read_bytes())
        self.assertEqual(cleaned.size, (64, 64))
        self.assertTrue(row['source']['alpha_cleanup']['enabled'])

    def test_changed_png_and_extra_file_are_rejected(self):
        path = self.folder / 'frames/down-idle.png'; original = path.read_bytes()
        try:
            path.write_bytes(original[:-4])
            with self.assertRaises((ValueError, OSError)):
                art.verify(self.folder)
        finally:
            path.write_bytes(original)
        extra = self.folder / 'extra.txt'; extra.write_text('unapproved')
        try:
            with self.assertRaisesRegex(ValueError, 'closure'):
                art.verify(self.folder)
        finally:
            extra.unlink()

    def test_atlas_cannot_differ_even_with_its_hash_updated(self):
        path = self.folder / 'atlases/down.png'; raw = path.read_bytes()
        try:
            image = art.png(raw); image.putpixel((256, 256), (248, 0, 0, 255)); image.save(path)
            manifest = json.loads(self.manifest_raw)
            record = art.file_record(path)
            manifest['files']['atlases/down.png'] = record
            manifest['atlases'][0].update(record)
            self.manifest_path.write_bytes(art.encoded(manifest))
            with self.assertRaisesRegex(ValueError, 'Atlas pixels'):
                art.verify(self.folder)
        finally:
            path.write_bytes(raw)

    def test_frame_phase_metadata_tampering_is_rejected(self):
        manifest = json.loads(self.manifest_raw)
        manifest['frames'][1]['primary_source_index'] = 3
        self.manifest_path.write_bytes(art.encoded(manifest))
        with self.assertRaisesRegex(ValueError, 'mapping'):
            art.verify(self.folder)

    def test_review_bound_to_exact_manifest_and_all_frames(self):
        manifest = json.loads(self.manifest_raw)
        ids = [r['id'] for r in manifest['frames']]
        review = {'schema': art.REVIEW_SCHEMA, 'manifest_sha256': art.sha(self.manifest_raw),
            'approved': True, 'reviewer': 'synthetic test', 'notes': 'Testing review binding only',
            'frames': ids, 'checks': {key: True for key in art.REVIEW_CHECKS}}
        art.validate_review(review, set(ids), art.sha(self.manifest_raw))
        review['frames'] = ids[:-1]
        with self.assertRaisesRegex(ValueError, '52'):
            art.validate_review(review, set(ids), art.sha(self.manifest_raw))
        review['frames'] = ids
        with self.assertRaisesRegex(ValueError, 'exact'):
            art.validate_review(review, set(ids), '0' * 64)

    def test_finalize_preserves_pixels_and_requires_fresh_output(self):
        manifest = json.loads(self.manifest_raw)
        review = {'schema': art.REVIEW_SCHEMA, 'manifest_sha256': art.sha(self.manifest_raw),
            'approved': True, 'reviewer': 'synthetic test', 'notes': 'Testing closure, not real art approval',
            'frames': [r['id'] for r in manifest['frames']], 'checks': {key: True for key in art.REVIEW_CHECKS}}
        review_path = self.root / 'review.json'; review_path.write_bytes(art.encoded(review))
        output = self.root / 'final'
        result = art.finalize(self.folder, review_path, output)
        self.assertEqual(result['review_status'], 'approved')
        self.assertEqual((output / 'frames/left-idle.png').read_bytes(), (self.folder / 'frames/left-idle.png').read_bytes())
        with self.assertRaisesRegex(ValueError, 'fresh'):
            art.finalize(self.folder, review_path, output)


if __name__ == '__main__':
    unittest.main()
