"""Compare packaged native art against captured video, then export GPU fixtures.

Expected pixels come directly from sealed original video. The package renderer
is independently reconstructed and compared before it can supply GPU inputs.
Only opaque player-body pixels are in scope; shadows/decorations are excluded.
"""
from __future__ import annotations

import argparse
from collections import Counter
import io
import json
from pathlib import Path

from PIL import Image

import character_bundle as bundle
import character_draw_order as ordering
import character_graphics as graphics
from exploration_capture import stable_read
from verify_character_capture import inspect

ROOT = Path(__file__).resolve().parents[1]
SIZE = (320, 224)
CAMERA = (544, 1536)
SCHEMA = 'ao_character_compositor_fixtures_v1'


def read_pinned(path: Path, digest: str) -> bytes:
    raw = stable_read(path)
    if graphics.sha(raw) != digest:
        raise ValueError('Pinned evidence changed: ' + str(path))
    return raw


def binary_image(image: Image.Image) -> None:
    if image.mode != 'RGBA' or any(a not in (0, 255) for a in image.getchannel('A').getdata()):
        raise ValueError('Native source composition requires RGBA and binary alpha')


def load_png(raw: bytes) -> Image.Image:
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'PNG':
            raise ValueError('Expected PNG')
        image.load()
        result = image.copy()
    binary_image(result)
    return result


def compose(background: Image.Image, foreground: Image.Image, layers: list[dict]) -> Image.Image:
    """VDP1 last writer first, then VDP2 priority; never group by priority."""
    binary_image(background)
    binary_image(foreground)
    if background.size != foreground.size:
        raise ValueError('Background and foreground dimensions differ')
    serials = [r['order'] for r in layers]
    if any(type(v) is not int or v < 1 for v in serials) or len(set(serials)) != len(serials):
        raise ValueError('Invalid or duplicate draw order')
    result = background.copy()
    for layer in sorted(layers, key=lambda r: r['order']):
        image = layer['image']
        binary_image(image)
        if layer['priority'] not in (2, 3) or type(layer['priority']) is not int:
            raise ValueError('Unsupported source sprite priority')
        rect = layer['rect']
        if len(rect) != 4 or any(type(v) is not int for v in rect) or tuple(rect[2:]) != image.size:
            raise ValueError('Source geometry must preserve integer native dimensions')
        for y in range(image.height):
            for x in range(image.width):
                color = image.getpixel((x, y))
                sx, sy = x + rect[0], y + rect[1]
                if color[3] == 0 or not (0 <= sx < result.width and 0 <= sy < result.height):
                    continue
                fg = foreground.getpixel((sx, sy))
                if layer['priority'] == 2 and fg[3]:
                    color = fg
                result.putpixel((sx, sy), color)
    return result


def project_video(video: bytes, body: Image.Image, origin: list[int], source_camera: list[int],
                  size: tuple[int, int] = SIZE, fixed_camera: tuple[int, int] = CAMERA) -> tuple[Image.Image, Image.Image]:
    """Copy observed video pixels; never derive expected RGB from package art."""
    binary_image(body)
    if len(video) != size[0] * size[1] * 4:
        raise ValueError('Truncated original video')
    if any(len(v) != 2 or any(type(n) is not int for n in v) for v in (origin, source_camera, fixed_camera)):
        raise ValueError('Invalid camera/origin')
    expected, mask = Image.new('RGBA', size), Image.new('RGBA', size)
    for y in range(body.height):
        for x in range(body.width):
            if body.getpixel((x, y))[3] == 0:
                continue
            sx, sy = origin[0] + x, origin[1] + y
            dx, dy = sx + source_camera[0] - fixed_camera[0], sy + source_camera[1] - fixed_camera[1]
            if not (0 <= sx < size[0] and 0 <= sy < size[1] and 0 <= dx < size[0] and 0 <= dy < size[1]):
                raise ValueError('Body extends beyond the bounded original/fixed-camera viewport')
            offset = (sy * size[0] + sx) * 4
            color = tuple(video[offset:offset + 4])
            if color[3] != 255:
                raise ValueError('Original displayed body pixel is not opaque')
            expected.putpixel((dx, dy), color)
            mask.putpixel((dx, dy), (255, 255, 255, 255))
    if not mask.getbbox():
        raise ValueError('An empty player mask cannot pass pixel validation')
    return expected, mask


def compare(actual: Image.Image, expected: Image.Image, mask: Image.Image) -> dict:
    binary_image(mask)
    if actual.size != expected.size or actual.size != mask.size:
        raise ValueError('Comparison dimensions differ')
    count, differences = 0, []
    for y in range(mask.height):
        for x in range(mask.width):
            if not mask.getpixel((x, y))[3]:
                continue
            count += 1
            if actual.getpixel((x, y)) != expected.getpixel((x, y)):
                differences.append({'pixel': [x, y], 'actual': actual.getpixel((x, y)), 'expected': expected.getpixel((x, y))})
    if count == 0:
        raise ValueError('An empty comparison mask cannot pass')
    return {'passed': not differences, 'pixels': count, 'mismatches': len(differences), 'examples': differences[:8]}


def layer_order(props: list[dict], actor_xy_raw: list[int]) -> list[str]:
    objects = [dict(row, y_raw=row['world_xy_raw'][1], camera_y_raw=CAMERA[1] * 16) for row in props]
    actor = {'slot': 0, 'y_sorted': True, 'y_raw': actor_xy_raw[1], 'camera_y_raw': CAMERA[1] * 16}
    result = ordering.bucket_order(objects, [actor])
    if result['unsorted']:
        raise ValueError('Unverified direct-priority package objects')
    return [f"{r['kind']}_{r['slot']}:0" for r in result['sorted']]


def background_image(source: graphics.BackgroundSource) -> Image.Image:
    result = Image.new('RGBA', SIZE, (0, 0, 0, 255))
    for y in range(SIZE[1]):
        for x in range(SIZE[0]):
            best = -1
            for layer in (1, 0):
                pixel = source.pixel(layer, CAMERA[0] + x, CAMERA[1] + y)
                if pixel['index'] and pixel['priority'] >= best:
                    best = pixel['priority']
                    result.putpixel((x, y), tuple(pixel['rgba']))
    return result


def relation_counts(layers: list[dict], body: dict) -> dict:
    """Coverage labels distinguish a player in front of/behind alpha furniture."""
    counts = Counter()
    image, bx, by = body['image'], body['rect'][0], body['rect'][1]
    for prop in layers:
        if prop is body:
            continue
        for y in range(image.height):
            for x in range(image.width):
                px, py = bx + x - prop['rect'][0], by + y - prop['rect'][1]
                if (image.getpixel((x, y))[3] and 0 <= px < prop['image'].width and 0 <= py < prop['image'].height
                        and prop['image'].getpixel((px, py))[3]):
                    key = 'body_in_front_of_' if body['order'] > prop['order'] else 'body_behind_'
                    counts[key + prop['id']] += 1
    return dict(counts)


def export(output: Path, package_folder: Path = bundle.DEFAULT_OUT, pin_path: Path = bundle.DEFAULT_PIN) -> dict:
    output = output.resolve()
    image_folder = output.with_suffix('')
    if not output.is_relative_to((ROOT / 'reports').resolve()) or output.exists() or image_folder.exists():
        raise ValueError('Use a fresh ignored-local reports output; never replace evidence')
    pin_raw = stable_read(pin_path)
    pin = json.loads(pin_raw)
    bundle.verify(package_folder, pin['manifest_sha256'], expected_scene_sha=pin['scene_manifest_sha256'])
    package_raw = read_pinned(package_folder / 'package.json', pin['manifest_sha256'])
    package = json.loads(package_raw)
    payload = {name: read_pinned(package_folder / name, row['sha256']) for name, row in package['files'].items()}
    appearance = json.loads(payload['appearances.json'])['frames']
    layer_data = json.loads(payload['layers.json'])
    props = layer_data['props']
    images = {name: load_png(raw) for name, raw in payload.items() if name.endswith('.png')}
    foreground = images['nbg-priority-foreground.png']
    source_raw = {name: stable_read(ROOT.parent / 'work/extract' / name) for name in ('PARTY0.PTY', 'MAP001.TWN', 'TWN.BIN')}
    resource = graphics.PlayerResource(source_raw['PARTY0.PTY'], source_raw['MAP001.TWN'], source_raw['TWN.BIN'])
    background = background_image(graphics.BackgroundSource(source_raw['MAP001.TWN']))
    index_raw = read_pinned(bundle.PRESENTATION_INDEX, package['source']['presentation_index_sha256'])
    index = json.loads(index_raw)
    order_raw = read_pinned(bundle.ORDER_REPORT, package['source']['draw_order_validation_sha256'])
    order_proof = json.loads(order_raw)
    observed_orders = {Path(c['folder']).name: {f['frame']: f for f in c['frames']} for c in order_proof['captures']}
    records, candidates, selected, total_pixels = [], {}, set(), 0
    capture_pins = {}
    for route in bundle.ROUTES:
        ref = index['reports'][route]
        report = json.loads(read_pinned(Path(ref['path']), package['source']['presentation_reports'][route]))
        if not report['passed'] or not report['visible_composition_passed'] or report['counts']['unexplained_pixels']:
            raise ValueError('Unverified presentation reference')
        capture_folder = Path(report['capture'])
        captured = inspect(capture_folder)
        capture_pins[route] = captured['manifest_sha256']
        if captured['manifest_sha256'] != package['source']['capture_manifests'][route + '-a']:
            raise ValueError('Capture differs from package lineage')
        def read_capture(name):
            return read_pinned(capture_folder / name, captured['outputs'][name])
        draws = {row['event_index']: row for row in report['draws']}
        for presented in report['presentation']:
            if presented['inherited_seed']:
                # Its pre-capture command execution was not recorded. Keep this
                # out of an end-to-end executed-order GPU fixture claim.
                continue
            draw = draws[presented['draw_event_index']]
            actor = bytes.fromhex(draw['source_actor_hex'])
            source_frame = presented['source_state_frame']
            if captured['samples'][source_frame]['player_actor_hex'] != actor.hex():
                raise ValueError('Presentation source actor does not match sealed sample')
            command = draw['command']
            matches = [row for row in appearance if row['image_index'] == draw['image_index'] and row['baked_mirror_x'] == command['flip_x']]
            if len(matches) != 1:
                raise ValueError('Package cannot uniquely represent observed player pose')
            pose = matches[0]
            body_image = images[pose['file']]
            sample = captured['samples'][presented['video_frame']]
            cram = read_capture('blobs/' + draw['cram_sha256'] + '.bin')
            native = graphics.oriented_image(graphics.rgba_texture(resource.textures[draw['texture_index']], cram,
                sample['vdp1'], sample['vdp2'], command['colr'], command['pmod']), command)
            if native.size != body_image.size or native.tobytes() != body_image.tobytes():
                raise ValueError('Packaged body/mask differs from source texture decode')
            actor_xy = [ordering.s16(actor, offset) for offset in (0, 2)]
            ids = layer_order(props, actor_xy)
            observed = observed_orders[route + '-a'][draw['frame']]
            allowed = {'actor_0:0', *(f'object_{slot}:0' for slot in range(6))}
            if ids != [item for item in observed['observed_order'] if item in allowed]:
                raise ValueError('Fixed-camera package order differs from observed execution')
            layers = []
            for number, identity in enumerate(ids, 1):
                if identity == 'actor_0:0':
                    meta, xy, priority = pose, actor_xy, 2
                else:
                    meta = props[int(identity.split('_')[1].split(':')[0])]
                    xy, priority = meta['world_xy_raw'], meta['sprite_priority']
                image = images[meta['file']]
                origin = [xy[i] // 16 - CAMERA[i] - meta['anchor'][i] for i in (0, 1)]
                layer = {'id': identity, 'texture_png': str((package_folder / meta['file']).resolve()),
                         'rect': origin + list(image.size), 'priority': priority, 'order': number, 'image': image}
                layers.append(layer)
                if identity == 'actor_0:0':
                    body = layer
            source_camera = presented['scanout_camera']
            fixed_origin = [presented['command_origin'][i] + source_camera[i] - CAMERA[i] for i in (0, 1)]
            if body['rect'][:2] != fixed_origin:
                raise ValueError('Packaged anchor/world projection differs from captured command')
            video_name = f"frame-{presented['video_frame']:06d}/video-rgba.bin"
            expected, mask = project_video(read_capture(video_name), native, presented['command_origin'], source_camera)
            rendered = compose(background, foreground, layers)
            result = compare(rendered, expected, mask)
            identity = f"{route}-{presented['video_frame']:06d}"
            relations = relation_counts(layers, body)
            summary = {'id': identity, 'route': route, 'video_frame': presented['video_frame'], 'source_state_frame': source_frame,
                'draw_frame': draw['frame'], 'draw_event_index': draw['event_index'], 'pose': pose['id'], 'direction': pose['direction'],
                'scanout_camera': source_camera, 'fixed_camera': list(CAMERA), 'source_video_sha256': captured['outputs'][video_name],
                'capture_manifest_sha256': captured['manifest_sha256'], 'comparison': result,
                'original_composition': presented['composition']['explained_pixels'], 'furniture_relations': relations}
            records.append(summary)
            total_pixels += result['pixels']
            if not result['passed']:
                raise ValueError('Package/source pixel difference: ' + json.dumps(summary))
            categories = {pose['id']: result['pixels'], 'route/' + route: result['pixels']}
            categories.update({'relation/' + k: n for k, n in relations.items()})
            categories.update({'occlusion/' + k: n for k, n in summary['original_composition'].items() if k != 'body'})
            for key, score in categories.items():
                if score > candidates.get(key, {}).get('score', -1):
                    candidates[key] = {'score': score, 'id': identity, 'expected': expected, 'mask': mask,
                        'layers': [{k: v for k, v in row.items() if k != 'image'} for row in layers], 'summary': summary}
        if graphics.sha(stable_read(capture_folder / 'manifest.json')) != captured['manifest_sha256']:
            raise ValueError('Capture changed during verification')
    if len(records) != sum(bundle.COUNTS.values()) - 4:
        raise ValueError('Incomplete non-inherited source coverage')
    if set(row['pose'] for row in records) != {row['id'] for row in appearance}:
        raise ValueError('The four source routes do not cover every packaged player pose')
    bundle.verify(package_folder, pin['manifest_sha256'], expected_scene_sha=pin['scene_manifest_sha256'])
    if stable_read(pin_path) != pin_raw:
        raise ValueError('Character pin changed during verification')
    image_folder.mkdir(parents=True, exist_ok=False)
    background_path = image_folder / 'source-background.png'
    background.save(background_path)
    cases = []
    for candidate in candidates.values():
        identity = candidate['id']
        if identity in selected:
            continue
        selected.add(identity)
        expected_path, mask_path = image_folder / (identity + '-expected.png'), image_folder / (identity + '-mask.png')
        candidate['expected'].save(expected_path)
        candidate['mask'].save(mask_path)
        cases.append({'id': identity, 'canvas_size': list(SIZE), 'background_png': str(background_path),
            'foreground_png': str((package_folder / 'nbg-priority-foreground.png').resolve()),
            'expected_png': str(expected_path), 'compare_mask_png': str(mask_path), 'layers': candidate['layers'],
            'scales': [1, 2], 'source': candidate['summary'],
            'coverage_categories': [key for key, row in candidates.items() if row['id'] == identity]})
    fixture = {'schema': SCHEMA, 'source_local_only': True, 'passed': True,
        'expected_pixel_origin': 'Sealed original video-rgba.bin, copied only at source-decoded opaque body pixels and reprojected by observed scanout camera',
        'character_manifest_sha256': pin['manifest_sha256'], 'scene_manifest_sha256': pin['scene_manifest_sha256'],
        'capture_manifests': capture_pins, 'presentation_index_sha256': graphics.sha(index_raw),
        'draw_order_validation_sha256': graphics.sha(order_raw), 'cases': cases,
        'cpu_validation': {'passed': True, 'frames': len(records), 'pixels': total_pixels, 'mismatches': 0,
            'source_pose_count': len(appearance), 'directions': sorted({row['direction'] for row in records}),
            'frames_detail': records, 'excluded_initial_inherited_videos': 4},
        'limits': ['Comparison covers opaque player-body pixels only; mask is independently bound to original decoded texture.',
            'Shadow-only pixels, objects 6/7, complete-room equality and HD art are outside this gate.',
            'First video of each route is inherited seed history and has no pre-capture executed-order proof.',
            'CPU source comparison does not replace the separate actual Godot GPU fixture run.']}
    output.write_text(json.dumps(fixture, indent=2) + '\n', encoding='utf-8')
    return fixture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'reports/character/runtime-pixel-fixtures.json')
    parser.add_argument('--package', type=Path, default=bundle.DEFAULT_OUT)
    parser.add_argument('--pin', type=Path, default=bundle.DEFAULT_PIN)
    args = parser.parse_args()
    result = export(args.out, args.package, args.pin)
    print(json.dumps({'passed': result['passed'], 'cases': len(result['cases']),
        **{k: v for k, v in result['cpu_validation'].items() if k != 'frames_detail'}}, indent=2))


if __name__ == '__main__':
    main()
