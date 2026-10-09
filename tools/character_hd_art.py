"""Mechanical, fail-closed preparation of generated MAP001 HD character art.

This tool crops complete atlas cells, translates, uniformly scales and packages
already drawn poses. It never synthesizes a pose, skeleton, limb or transition.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import io
import json
import math
from pathlib import Path
import shutil

from PIL import Image, ImageDraw

from exploration_capture import stable_read

SCHEMA = 'ao_character_hd_art_v1'
INPUT_SCHEMA = 'ao_character_hd_art_input_v1'
REVIEW_SCHEMA = 'ao_character_hd_art_review_v1'
DIRECTIONS = ('down', 'left', 'right', 'up')
NAMES = tuple(f'walk-{i:02d}' for i in range(12)) + ('idle',)
ANCHOR = [256, 448]
CANVAS = (512, 512)
PHASE = {'cycle_updates': 40, 'source_primary_count': 4, 'updates_per_primary': 10,
         'walk_frame_count': 12, 'phase_interval_denominator': 3,
         'walk_index_formula': 'primary*3+floor((timer+render_phase)*3/10)',
         'integer_update_durations_per_primary': [4, 3, 3],
         'render_phase_range': '[0,1)', 'changes_logic_clock': False}
REVIEW_CHECKS = ('consistent_identity', 'distinct_drawn_poses', 'complete_silhouette',
                 'feet_and_anchor', 'limb_and_weapon_consistency', 'loop_continuity')


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def hash_valid(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def read_reference(record: dict) -> tuple[bytes, Path]:
    if not isinstance(record, dict) or not {'path', 'sha256'} <= set(record) or not hash_valid(record['sha256']):
        raise ValueError('An explicit source path and SHA256 are required')
    path = Path(record['path'])
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError('Source must be a direct absolute regular file')
    raw = stable_read(path)
    if sha(raw) != record['sha256']:
        raise ValueError('Source changed: ' + str(path))
    return raw, path


def png(raw: bytes) -> Image.Image:
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'PNG' or image.mode != 'RGBA' or not (1 <= image.width <= 8192 and 1 <= image.height <= 8192):
            raise ValueError('Source must be an RGBA PNG of supported size')
        image.load()
        return image.copy()


def components(image: Image.Image) -> list[dict]:
    """8-connected nonzero alpha, preserving every faint edge pixel."""
    if image.mode != 'RGBA':
        raise ValueError('RGBA input required')
    width, height = image.size
    remaining = bytearray(image.getchannel('A').tobytes())
    result = []
    for start in range(len(remaining)):
        if not remaining[start]:
            continue
        pending = deque([start])
        remaining[start] = 0
        count, left, top, right, bottom = 0, width, height, 0, 0
        while pending:
            position = pending.popleft()
            x, y = position % width, position // width
            count += 1
            left, top, right, bottom = min(left, x), min(top, y), max(right, x + 1), max(bottom, y + 1)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if (dx or dy) and 0 <= nx < width and 0 <= ny < height:
                        index = ny * width + nx
                        if remaining[index]:
                            remaining[index] = 0
                            pending.append(index)
        result.append({'pixels': count, 'bbox': [left, top, right, bottom]})
    return sorted(result, key=lambda r: r['pixels'], reverse=True)


def inspect_cell(image: Image.Image, minimum_margin: int = 2) -> dict:
    boxes = components(image)
    if not boxes:
        raise ValueError('Empty required pose')
    bounds = list(image.getchannel('A').getbbox())
    if min(bounds[0], bounds[1], image.width - bounds[2], image.height - bounds[3]) < minimum_margin:
        raise ValueError('Alpha reaches a cell edge: cropped/cross-cell silhouette is rejected')
    main = boxes[0]
    if main['pixels'] < 32:
        raise ValueError('Required pose has insufficient connected content')
    # Multiple substantial disconnected figures are rejected, but this is not
    # an anatomical classifier. Tiny detached details remain in the output.
    if any(row['pixels'] >= max(16, main['pixels'] * .02) for row in boxes[1:]):
        raise ValueError('Multiple substantial alpha components: separate characters/parts require review and regeneration')
    return {'alpha_bbox': bounds, 'components': boxes, 'opaque_support_pixels': sum(row['pixels'] for row in boxes)}


def clean_alpha(image: Image.Image, settings: dict | None) -> tuple[Image.Image, dict]:
    """Optional explicit alpha-only cleanup; never invent or repaint RGB."""
    before = list(image.getchannel('A').getbbox() or ())
    if settings is None:
        return image.copy(), {'enabled': False, 'input_bbox': before, 'output_bbox': before,
                              'removed_low_alpha_pixels': 0, 'removed_small_component_pixels': 0}
    if (not isinstance(settings, dict) or set(settings) != {'min_alpha', 'min_component_pixels'}
            or type(settings['min_alpha']) is not int or not 1 <= settings['min_alpha'] <= 16
            or type(settings['min_component_pixels']) is not int or not 1 <= settings['min_component_pixels'] <= 16):
        raise ValueError('Alpha cleanup is bounded to thresholds 1..16; larger removal needs explicit artwork repair')
    result = image.copy()
    low_removed, small_removed = 0, 0
    colors = list(result.getdata())
    for index, (r, g, b, a) in enumerate(colors):
        if 0 < a < settings['min_alpha']:
            colors[index] = (r, g, b, 0)
            low_removed += 1
    result.putdata(colors)
    # Component bounding boxes can overlap, so removal must traverse the exact
    # component, not clear every pixel in its rectangular bounds.
    width, height = result.size
    alpha = bytearray(result.getchannel('A').tobytes())
    for start in range(len(alpha)):
        if not alpha[start]:
            continue
        pending, positions = deque([start]), []
        alpha[start] = 0
        while pending:
            position = pending.popleft(); positions.append(position)
            x, y = position % width, position // width
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if (dx or dy) and 0 <= nx < width and 0 <= ny < height:
                        index = ny * width + nx
                        if alpha[index]:
                            alpha[index] = 0; pending.append(index)
        if len(positions) < settings['min_component_pixels']:
            for index in positions:
                r, g, b, _ = colors[index]
                colors[index] = (r, g, b, 0)
            small_removed += len(positions)
    result.putdata(colors)
    return result, {'enabled': True, 'parameters': settings.copy(), 'input_bbox': before,
        'output_bbox': list(result.getchannel('A').getbbox() or ()),
        'removed_low_alpha_pixels': low_removed, 'removed_small_component_pixels': small_removed,
        'rgb_unchanged': True}


def split_sheet(image: Image.Image, alpha_cleanup: dict | None = None,
                cleanup_reports: list | None = None) -> list[tuple[Image.Image, list[int]]]:
    if image.width % 4 or image.height % 4:
        raise ValueError('A 4x4 sheet must divide into integral cells')
    w, h = image.width // 4, image.height // 4
    if min(w, h) < 32:
        raise ValueError('Source atlas cells are too small')
    result = []
    for cell in range(16):
        rect = [cell % 4 * w, cell // 4 * h, (cell % 4 + 1) * w, (cell // 4 + 1) * h]
        cut, cleanup = clean_alpha(image.crop(rect), alpha_cleanup)
        if cleanup_reports is not None:
            cleanup_reports.append(cleanup)
        if cell >= 13:
            if cut.getchannel('A').getbbox():
                raise ValueError('Unused atlas cells 13..15 must be fully transparent')
        else:
            inspect_cell(cut)
            result.append((cut, rect))
    return result


def canonical_pose(image: Image.Image) -> str:
    """Detect exact copies despite padding/translation, reflection or 90deg turns.

    Does not claim to detect all affine, resized, recolored or near-copy poses.
    """
    box = image.getchannel('A').getbbox()
    if box is None:
        raise ValueError('Empty pose cannot have an identity')
    cropped = image.crop(box)
    # Hidden RGB is not evidence that transparent pixels form a new drawing.
    cropped.putdata([color if color[3] else (0, 0, 0, 0) for color in cropped.getdata()])
    variants = [cropped]
    for operation in (Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.FLIP_TOP_BOTTOM,
                      Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_180,
                      Image.Transpose.ROTATE_270, Image.Transpose.TRANSPOSE, Image.Transpose.TRANSVERSE):
        variants.append(cropped.transpose(operation))
    return min(sha(str(frame.size).encode() + frame.tobytes()) for frame in variants)


def estimate_anchor(image: Image.Image, details: dict) -> list[float]:
    """Geometric candidate only: bottom of main component, not claimed anatomy."""
    x0, _, x1, y1 = details['components'][0]['bbox']
    supported = [x for x in range(x0, x1) if image.getpixel((x, y1 - 1))[3]]
    if not supported:
        raise ValueError('No bottom support in main component')
    return [(supported[0] + supported[-1] + 1) / 2, float(y1)]


def normalize(image: Image.Image, source_anchor: list[float], scale: float) -> Image.Image:
    if (len(source_anchor) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in source_anchor)
            or not (0 < source_anchor[0] < image.width and 0 < source_anchor[1] <= image.height)
            or type(scale) not in (int, float) or not math.isfinite(scale) or not 0 < scale <= 16):
        raise ValueError('Invalid source anchor or uniform scale')
    box = image.getchannel('A').getbbox()
    if box is None:
        raise ValueError('Cannot normalize an empty pose')
    cut = image.crop(box)
    dimensions = [max(1, round(cut.size[i] * scale)) for i in (0, 1)]
    # One scale is shared by all thirteen poses of the direction. Rounding to
    # pixel dimensions is explicit; there is no per-frame fit/stretch.
    rendered = cut.resize(tuple(dimensions), Image.Resampling.LANCZOS)
    origin = [round(ANCHOR[i] - (source_anchor[i] - box[i]) * scale) for i in (0, 1)]
    if any(origin[i] < 8 or origin[i] + dimensions[i] > CANVAS[i] - 8 for i in (0, 1)):
        raise ValueError('Normalized silhouette would clip or violate the 8px transparent margin')
    canvas = Image.new('RGBA', CANVAS)
    canvas.paste(rendered, tuple(origin))
    return canvas


def frame_contract(direction: str, cell: int) -> dict:
    if direction not in DIRECTIONS or type(cell) is not int or not 0 <= cell < 13:
        raise ValueError('Unknown direction or animation cell')
    idle = cell == 12
    primary, sub = (None, None) if idle else divmod(cell, 3)
    return {'id': f'map001_player_hd/{direction}/{NAMES[cell]}', 'direction': direction,
        'action': 'idle' if idle else 'walk', 'kind': 'idle' if idle else 'primary' if sub == 0 else 'transition',
        'walk_index': -1 if idle else cell, 'primary_source_index': primary,
        'next_primary_source_index': (primary + 1) % 4 if not idle and sub else None,
        'transition_fraction': {'numerator': sub, 'denominator': 3} if not idle and sub else None,
        'phase_interval_numerators': None if idle else [cell * 10, (cell + 1) * 10],
        'integer_update_phases': [] if idle else [p for p in range(40) if p * 3 // 10 == cell],
        'cell': cell, 'rect': [cell % 4 * 512, cell // 4 * 512, 512, 512],
        'file': f'frames/{direction}-{NAMES[cell]}.png', 'atlas': f'atlases/{direction}.png',
        'ground_anchor': ANCHOR.copy(), 'dimensions': list(CANVAS)}


def file_record(path: Path) -> dict:
    raw = stable_read(path)
    result = {'bytes': len(raw), 'sha256': sha(raw)}
    if path.suffix == '.png':
        image = png(raw)
        result.update({'width': image.width, 'height': image.height, 'rgba_sha256': sha(image.tobytes())})
    return result


def preview(frames: list[Image.Image], direction: str, folder: Path) -> list[str]:
    # Preview grids and GIFs intentionally include a neutral backdrop; they are
    # review products, never runtime textures or additional claimed poses.
    contact = Image.new('RGBA', (1024, 4 * 276), (24, 28, 34, 255))
    painter = ImageDraw.Draw(contact)
    for index, frame in enumerate(frames):
        x, y = index % 4 * 256, index // 4 * 276
        contact.alpha_composite(frame.resize((256, 256), Image.Resampling.LANCZOS), (x, y))
        painter.text((x + 8, y + 257), NAMES[index], fill=(235, 240, 246, 255))
        painter.line((x + 123, y + 224, x + 133, y + 224), fill=(255, 200, 80, 255), width=1)
    contact_path = folder / f'previews/{direction}-contact.png'
    contact.save(contact_path)
    gif_frames = []
    for frame in frames[:12]:
        backdrop = Image.new('RGBA', CANVAS, (24, 28, 34, 255))
        backdrop.alpha_composite(frame)
        gif_frames.append(backdrop.convert('RGB'))
    gif_path = folder / f'previews/{direction}-walk.gif'
    # GIF hundredths cannot express 40/60s exactly. Use 60/50/60ms repeating:
    # visible review only; runtime timing always uses PHASE, never this GIF.
    gif_frames[0].save(gif_path, save_all=True, append_images=gif_frames[1:], duration=[60, 50, 60] * 4,
                       loop=0, disposal=2, optimize=False)
    return [contact_path.relative_to(folder).as_posix(), gif_path.relative_to(folder).as_posix()]


def prepare(spec_path: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError('Output already exists; keep prior generated art immutable')
    spec_raw = stable_read(spec_path)
    spec = json.loads(spec_raw)
    if spec.get('schema') != INPUT_SCHEMA or spec.get('character_id') != 'map001_player':
        raise ValueError('Unknown HD art input profile')
    for key in ('source_character_manifest_sha256', 'scene_manifest_sha256'):
        if not hash_valid(spec.get(key)):
            raise ValueError('Source character/scene manifest identities are required')
    approval = spec.get('draft_approval', {})
    if (approval.get('approved') is not True or not isinstance(approval.get('evidence'), str)
            or not approval['evidence'].strip() or set(approval.get('references', {})) != set(DIRECTIONS)):
        raise ValueError('The four approved A3 draft identities and approval evidence are required')
    checked_inputs = []
    references = {}
    for direction, record in approval['references'].items():
        raw, path = read_reference(record)
        png(raw)
        checked_inputs.append((path, sha(raw)))
        references[direction] = {'name': path.name, 'sha256': sha(raw)}
    settings = spec.get('normalization', {})
    cleanup_settings = settings.get('alpha_cleanup')
    clean_alpha(Image.new('RGBA', (1, 1)), cleanup_settings)
    height = settings.get('maximum_alpha_height', 400)
    display_scales = settings.get('display_scale_by_direction', {})
    actor_anchors = settings.get('actor_anchor_by_direction', {})
    if (type(height) is not int or not 64 <= height <= 416 or set(display_scales) != set(DIRECTIONS)
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 1 for v in display_scales.values())
            or set(actor_anchors) != set(DIRECTIONS) or any(not isinstance(v, list) or len(v) != 2
                or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 512 for n in v)
                for v in actor_anchors.values())):
        raise ValueError('Explicit per-direction display scales and actor anchors are required; art ground is not actor origin')
    approval_raw, approval_path = read_reference(approval.get('approval_record', {}))
    checked_inputs.append((approval_path, sha(approval_raw)))
    if set(spec.get('directions', {})) != set(DIRECTIONS):
        raise ValueError('Exactly four complete directions are required')
    sources, prepared, all_identities, scales, cleaned_images = {}, {}, {}, {}, {}
    for direction in DIRECTIONS:
        descriptor = spec['directions'][direction]
        if descriptor.get('kind') == 'sheet':
            raw, path = read_reference(descriptor)
            source_image = png(raw)
            cleanup_rows = []
            cells = split_sheet(source_image, cleanup_settings, cleanup_rows)
            origin = {'kind': 'sheet', 'name': path.name, 'sha256': sha(raw), 'dimensions': list(source_image.size),
                      'grid': [4, 4], 'walk_cells': list(range(12)), 'idle_cell': 12, 'unused_cells': [13, 14, 15],
                      'unused_cell_cleanup': cleanup_rows[13:]}
            source_for_cell = [{'input_sha256': sha(raw), 'source_rect': rect, 'alpha_cleanup': cleanup_rows[i]}
                               for i, (_, rect) in enumerate(cells)]
            checked_inputs.append((path, sha(raw)))
        elif descriptor.get('kind') == 'frames':
            if set(descriptor.get('files', {})) != set(NAMES):
                raise ValueError('Individual-frame input requires exactly walk-00..11 and idle')
            cells, source_for_cell, originals = [], [], {}
            for name in NAMES:
                raw, path = read_reference(descriptor['files'][name])
                image, cleanup = clean_alpha(png(raw), cleanup_settings)
                inspect_cell(image)
                rect = [0, 0, image.width, image.height]
                cells.append((image, rect))
                originals[name] = {'name': path.name, 'sha256': sha(raw), 'dimensions': list(image.size)}
                source_for_cell.append({'input_sha256': sha(raw), 'source_rect': rect, 'alpha_cleanup': cleanup})
                checked_inputs.append((path, sha(raw)))
            origin = {'kind': 'frames', 'files': originals}
        else:
            raise ValueError('Each direction must provide a generated sheet or thirteen drawn frames')
        anchors = descriptor.get('anchors')
        if anchors is not None and (not isinstance(anchors, list) or len(anchors) != 13):
            raise ValueError('Explicit source anchors must cover all thirteen cells')
        details = [inspect_cell(image) for image, _ in cells]
        scale = height / max(row['alpha_bbox'][3] - row['alpha_bbox'][1] for row in details)
        scales[direction] = scale
        rows = []
        for index, ((image, _), detail) in enumerate(zip(cells, details)):
            identity = canonical_pose(image)
            frame_id = frame_contract(direction, index)['id']
            if identity in all_identities:
                raise ValueError('Repeated/reflected/translated pose is not a new drawing: ' + frame_id + ' matches ' + all_identities[identity])
            all_identities[identity] = frame_id
            if anchors is not None:
                evidence = anchors[index]
                if (not isinstance(evidence, dict) or not isinstance(evidence.get('point'), list)
                        or evidence.get('confirmed') is not True or not isinstance(evidence.get('evidence'), str)
                        or not evidence['evidence'].strip()):
                    raise ValueError('Explicit foot points need point, confirmed:true and human review evidence')
                anchor = evidence['point']
            else:
                evidence = {'confirmed': False, 'evidence': 'Geometric estimate; requires final visual foot/anchor review'}
                anchor = estimate_anchor(image, detail)
            result = normalize(image, anchor, scale)
            source = source_for_cell[index] | detail | {'anchor': anchor,
                'anchor_method': 'explicit_input' if anchors is not None else 'mechanical_bottom_support_estimate',
                'anchor_confirmed': evidence['confirmed'], 'anchor_evidence': evidence['evidence'],
                'canonical_pose_sha256': identity, 'uniform_scale': scale}
            if cleanup_settings is not None:
                cleaned_file = f'cleaned-sources/{direction}-{NAMES[index]}.png'
                source['cleaned_source_file'] = cleaned_file
                cleaned_images[cleaned_file] = image
            rows.append((frame_contract(direction, index) | {'display_scale': display_scales[direction],
                'actor_anchor': actor_anchors[direction], 'anchor': actor_anchors[direction], 'source': source}, result))
        sources[direction], prepared[direction] = origin, rows
    # Finish all validation before creating output; failed source sheets leave
    # no partial package that can be mistaken for finished artwork.
    for path, digest in checked_inputs:
        if sha(stable_read(path)) != digest:
            raise ValueError('Input changed during HD normalization')
    if stable_read(spec_path) != spec_raw:
        raise ValueError('Input specification changed during normalization')
    output.mkdir(parents=True)
    for name in ('frames', 'atlases', 'previews'):
        (output / name).mkdir()
    rows, atlases, names = [], [], []
    if cleaned_images:
        (output / 'cleaned-sources').mkdir()
        for name, image in cleaned_images.items():
            image.save(output / name)
            names.append(name)
    for direction, values in prepared.items():
        atlas = Image.new('RGBA', (2048, 2048))
        direction_images = []
        for row, image in values:
            path = output / row['file']
            image.save(path)
            row.update(file_record(path))
            row['alpha_bbox'] = list(image.getchannel('A').getbbox())
            rows.append(row)
            names.append(row['file'])
            atlas.paste(image, tuple(row['rect'][:2]))
            direction_images.append(image)
        atlas_file = f'atlases/{direction}.png'
        atlas.save(output / atlas_file)
        atlases.append({'direction': direction, 'file': atlas_file} | file_record(output / atlas_file))
        names.append(atlas_file)
        names += preview(direction_images, direction, output)
    result = {'schema': SCHEMA, 'character_id': 'map001_player', 'review_status': 'pending',
        'source_character_manifest_sha256': spec['source_character_manifest_sha256'],
        'scene_manifest_sha256': spec['scene_manifest_sha256'], 'input_spec_sha256': sha(spec_raw),
        'draft_approval': {'status': 'approved', 'evidence': approval['evidence'],
            'reference_sha256': {d: row['sha256'] for d, row in references.items()}, 'approval_record_sha256': sha(approval_raw)},
        'source_inputs': sources, 'normalization': {'canvas': list(CANVAS), 'ground_anchor': ANCHOR.copy(),
            'maximum_alpha_height': height, 'display_scale_by_direction': display_scales,
            'actor_anchor_by_direction': actor_anchors, 'scale_by_direction': scales,
            'sampler': 'LANCZOS', 'transparent_margin_minimum': 8, 'per_frame_stretch': False,
            'alpha_cleanup': cleanup_settings},
        'phase_contract': PHASE, 'frames': rows, 'atlases': atlases,
        'files': {name: file_record(output / name) for name in sorted(names)},
        'mechanical_validation': {'frame_count': 52, 'atlas_count': 4, 'unique_canonical_source_poses': 52,
            'all_post_cleanup_alpha_components_preserved': True, 'atlas_exact_frame_pixels': True},
        'limits': ['Mechanical geometry and closure checks do not prove anatomy, identity, pose originality or animation quality.',
            'Automatic anchors are geometric estimates until visual review confirms feet and alignment.',
            'Exact translation/reflection/rotation duplicates are rejected; near-copies and arbitrary affine copies require visual review.',
            'GIF timing is a rounded review preview; runtime uses the exact 12/40 phase contract.',
            'Source draft files and generated sheets are references; only reviewed final HD art is eligible for publication.']}
    (output / 'manifest.json').write_bytes(encoded(result))
    verify(output)
    return result


def verify(folder: Path, require_review: bool = False) -> dict:
    manifest_raw = stable_read(folder / 'manifest.json')
    manifest = json.loads(manifest_raw)
    if manifest.get('schema') != SCHEMA or manifest.get('character_id') != 'map001_player' or manifest.get('phase_contract') != PHASE:
        raise ValueError('Unknown art package or phase mapping')
    if manifest.get('review_status') not in ('pending', 'approved'):
        raise ValueError('Unknown art review status')
    approval = manifest.get('draft_approval', {})
    if (approval.get('status') != 'approved' or set(approval.get('reference_sha256', {})) != set(DIRECTIONS)
            or not all(hash_valid(v) for v in approval['reference_sha256'].values())
            or not hash_valid(approval.get('approval_record_sha256'))):
        raise ValueError('Missing approved A3 draft identities')
    if require_review and manifest['review_status'] != 'approved':
        raise ValueError('HD art still requires explicit frame/animation review')
    names = {f'frames/{d}-{n}.png' for d in DIRECTIONS for n in NAMES}
    names |= {f'atlases/{d}.png' for d in DIRECTIONS}
    names |= {f'previews/{d}-{kind}.{extension}' for d in DIRECTIONS for kind, extension in [('contact', 'png'), ('walk', 'gif')]}
    cleanup_settings = manifest.get('normalization', {}).get('alpha_cleanup')
    clean_alpha(Image.new('RGBA', (1, 1)), cleanup_settings)
    if cleanup_settings is not None:
        names |= {f'cleaned-sources/{d}-{n}.png' for d in DIRECTIONS for n in NAMES}
    files = manifest.get('files', {})
    if set(files) != names:
        raise ValueError('HD package has an incomplete or extra payload list')
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != names | {'manifest.json'} or any(p.is_symlink() for p in folder.rglob('*')):
        raise ValueError('HD directory differs from its exact payload closure')
    for name, record in files.items():
        if file_record(folder / name) != record:
            raise ValueError('Changed or truncated HD payload: ' + name)
    frames = manifest.get('frames', [])
    if len(frames) != 52 or len({r['id'] for r in frames}) != 52:
        raise ValueError('Exactly 52 unique frame records are required')
    sources = set()
    by_id = {row['id']: row for row in frames}
    for direction in DIRECTIONS:
        atlas = png(stable_read(folder / f'atlases/{direction}.png'))
        if atlas.size != (2048, 2048):
            raise ValueError('HD atlas must be 2048x2048')
        for cell in range(16):
            x, y = cell % 4 * 512, cell // 4 * 512
            cut = atlas.crop((x, y, x + 512, y + 512))
            if cell >= 13:
                if cut.getchannel('A').getbbox():
                    raise ValueError('Unused atlas cells must remain transparent')
                continue
            expected = frame_contract(direction, cell)
            row = by_id.get(expected['id'])
            if row is None or any(row.get(k) != v for k, v in expected.items()):
                raise ValueError('Frame ID, phase, primary source, anchor or atlas mapping changed')
            normalization = manifest['normalization']
            if (row.get('actor_anchor') != normalization['actor_anchor_by_direction'][direction]
                    or row.get('anchor') != row['actor_anchor']
                    or row.get('display_scale') != normalization['display_scale_by_direction'][direction]):
                raise ValueError('Actor origin/display scale differs from the explicit direction contract')
            for key, value in files[row['file']].items():
                if row.get(key) != value:
                    raise ValueError('Frame identity differs from payload closure')
            frame = png(stable_read(folder / row['file']))
            if frame.size != CANVAS or frame.tobytes() != cut.tobytes():
                raise ValueError('Atlas pixels differ from individual frame')
            bounds = list(frame.getchannel('A').getbbox() or ())
            if bounds != row.get('alpha_bbox') or not bounds or min(bounds[0], bounds[1], 512 - bounds[2], 512 - bounds[3]) < 8:
                raise ValueError('Frame silhouette is empty, clipped or changed')
            identity = row.get('source', {}).get('canonical_pose_sha256')
            if not hash_valid(identity) or identity in sources:
                raise ValueError('Source pose is absent or duplicated')
            if cleanup_settings is not None:
                cleaned_name = f'cleaned-sources/{direction}-{NAMES[cell]}.png'
                if (row['source'].get('cleaned_source_file') != cleaned_name
                        or canonical_pose(png(stable_read(folder / cleaned_name))) != identity):
                    raise ValueError('Cleaned-source review artifact differs from normalized pose provenance')
            sources.add(identity)
        atlas_row = next((r for r in manifest.get('atlases', []) if r.get('direction') == direction), None)
        if atlas_row != {'direction': direction, 'file': f'atlases/{direction}.png'} | files[f'atlases/{direction}.png']:
            raise ValueError('Atlas record differs from payload identity')
    if len(manifest.get('atlases', [])) != 4:
        raise ValueError('Exactly four atlas records are required')
    if manifest['review_status'] == 'approved':
        validate_review(manifest.get('review', {}), set(by_id), manifest.get('prepared_manifest_sha256'))
    if stable_read(folder / 'manifest.json') != manifest_raw:
        raise ValueError('HD manifest changed during validation')
    return {'schema': 'ao_character_hd_art_verification_v1', 'passed': True, 'review_status': manifest['review_status'],
        'manifest_sha256': sha(manifest_raw), 'frames': 52, 'atlases': 4, 'payloads': len(names)}


def validate_review(review: dict, frame_ids: set[str], prepared_hash: str) -> None:
    if (not hash_valid(prepared_hash) or review.get('schema') != REVIEW_SCHEMA or review.get('manifest_sha256') != prepared_hash
            or review.get('approved') is not True or not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip()
            or not isinstance(review.get('notes'), str) or not review['notes'].strip()
            or not isinstance(review.get('frames'), list) or len(review['frames']) != 52 or set(review['frames']) != frame_ids
            or review.get('checks') != {key: True for key in REVIEW_CHECKS}):
        raise ValueError('Review must bind all 52 frames and all visual checks to the exact prepared manifest')


def finalize(prepared: Path, review_path: Path, output: Path) -> dict:
    result = verify(prepared)
    if output.exists() or result['review_status'] != 'pending':
        raise ValueError('Finalize a pending package into a fresh directory')
    manifest_raw = stable_read(prepared / 'manifest.json')
    manifest = json.loads(manifest_raw)
    review = json.loads(stable_read(review_path))
    validate_review(review, {r['id'] for r in manifest['frames']}, sha(manifest_raw))
    output.mkdir(parents=True)
    for name in manifest['files']:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(prepared / name, target)
    manifest.update({'review_status': 'approved', 'prepared_manifest_sha256': sha(manifest_raw), 'review': review})
    (output / 'manifest.json').write_bytes(encoded(manifest))
    return verify(output, require_review=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--spec', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('verify'); p.add_argument('folder', type=Path); p.add_argument('--require-review', action='store_true')
    p = sub.add_parser('finalize'); p.add_argument('--prepared', type=Path, required=True); p.add_argument('--review', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.spec, args.out)
        print(json.dumps({'review_status': result['review_status'], 'frames': len(result['frames']), 'atlases': len(result['atlases'])}))
    elif args.command == 'verify':
        print(json.dumps(verify(args.folder, args.require_review)))
    else:
        print(json.dumps(finalize(args.prepared, args.review, args.out)))


if __name__ == '__main__':
    main()
