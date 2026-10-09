"""Export only source-bound MAP001 furniture; no screenshot cropping or NPC art."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from character_graphics import (ROOT, WORKSPACE, MAP_SHA256, MAP_V1N_SHA256, PALETTE_SOURCE_OFFSET,
                                PALETTE_CRAM_OFFSET, sprite_code_rgba, sha, span, word, longword)
from exploration_capture import read_json_bytes, stable_read


def decode_piece(indices: bytes, width: int, height: int, bits: int, colr: int,
                 cram: bytes, regs: dict, flip_x: bool = False, flip_y: bool = False) -> Image.Image:
    """Convert fully unpacked original source texels, then apply known mirrors."""
    if (type(width) is not int or type(height) is not int or not 0 < width <= 504
            or not 0 < height <= 255 or len(indices) != width * height or bits not in (4, 6)):
        raise ValueError('Furniture source dimensions or pixel format are unsupported')
    mask = (1 << bits) - 1
    if any(value & ~mask for value in indices):
        raise ValueError('Furniture source texel exceeds its color bank')
    if len(cram) != 4096 or colr & mask:
        raise ValueError('Furniture palette is incomplete or misaligned')
    pixels = []
    for value in indices:
        if value == 0:
            pixels.append((0, 0, 0, 0))
        else:
            pixels.append(sprite_code_rgba(colr | value, cram, regs)[0])
    result = Image.new('RGBA', (width, height))
    result.putdata(pixels)
    if flip_x:
        result = result.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_y:
        result = result.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return result


def compose_pieces(pieces: list[tuple[Image.Image, tuple[int, int]]]) -> tuple[Image.Image, list[int]]:
    """Preserve signed source offsets; return image and original object's anchor."""
    if not pieces or len(pieces) > 32:
        raise ValueError('Furniture requires a nonempty bounded source piece list')
    for image, offset in pieces:
        if image.mode != 'RGBA' or len(offset) != 2 or any(type(v) is not int or abs(v) > 2048 for v in offset):
            raise ValueError('Invalid furniture piece or source offset')
    left, top = min(x for _, (x, _) in pieces), min(y for _, (_, y) in pieces)
    right = max(x + image.width for image, (x, _) in pieces)
    bottom = max(y + image.height for image, (_, y) in pieces)
    if right - left > 2048 or bottom - top > 2048:
        raise ValueError('Furniture composition is outside source profile')
    result = Image.new('RGBA', (right - left, bottom - top))
    for image, (x, y) in pieces:
        result.alpha_composite(image, (x - left, y - top))
    return result, [-left, -top]


def export(capture_folder: Path, order_report: Path, output: Path, workspace: Path = WORKSPACE) -> dict:
    """Export six immutable scene props after source-order and capture gates."""
    from verify_character_capture import inspect
    from character_draw_order import scene_from_snapshot, verify_source
    from pipeline import parse_v1n

    report_raw = stable_read(order_report)
    proof = read_json_bytes(report_raw)
    if proof.get('schema') != 'ao_character_draw_order_validation_v1' or proof.get('passed') is not True or proof.get('frame_count') != 684:
        raise ValueError('The complete approved 684-frame draw-order proof is required')
    sources = {name: stable_read(workspace / 'work/extract' / name) for name in ('MAP001.TWN', 'MAP001.V1N', 'TWN.BIN', '0')}
    if sha(sources['MAP001.TWN']) != MAP_SHA256 or sha(sources['MAP001.V1N']) != MAP_V1N_SHA256:
        raise ValueError('Furniture source file changed')
    ranges = verify_source(sources['TWN.BIN'], sources['0'])
    if ranges != proof.get('source_ranges'):
        raise ValueError('Approved source-order routine identities changed')
    capture = inspect(capture_folder)
    matching = [r for r in proof.get('captures', []) if Path(r['folder']).resolve() == capture_folder.resolve()]
    if len(matching) != 1 or matching[0]['manifest_sha256'] != capture['manifest_sha256']:
        raise ValueError('Furniture capture is not part of the approved order proof')

    def read(name):
        raw = stable_read(capture_folder / name)
        if sha(raw) != capture['outputs'][name]:
            raise ValueError('Furniture capture changed after its integrity gate')
        return raw

    high, low = read('frame-000000/wram-high.bin'), read('frame-000000/wram-low.bin')
    scene = scene_from_snapshot(high, low)
    if scene != matching[0]['initial_scene']:
        raise ValueError('Furniture extraction differs from the approved source-order scene')
    # The first MAP001.TWN block is the complete source object/image region.
    raw_map = sources['MAP001.TWN']
    region_size = longword(raw_map, 4)
    if longword(raw_map, 0) != 1 or region_size != 0xf228 or high[0xe0000:0xe0000 + region_size] != span(raw_map, 8, region_size):
        raise ValueError('Source image-record region differs from runtime')
    vram, cram = read('frame-000000/vram1.bin'), read('frame-000000/cram.bin')
    regs = capture['samples'][0]['vdp2']
    records = parse_v1n(sources['MAP001.V1N'])
    images, props = [], []
    for obj in scene['objects']:
        slot = obj['slot']
        if slot not in range(6):
            continue
        if not obj['y_sorted']:
            raise ValueError('Static furniture lost its source Y sorting flag')
        pointer = (obj['record_address'] & 0xfffff) - 0xe0000
        if pointer < 0 or pointer + 2 + 6 * len(obj['pieces']) > region_size:
            raise ValueError('Furniture image record lies outside the source region')
        record_raw = span(raw_map, 8 + pointer, 2 + 6 * len(obj['pieces']))
        if word(record_raw, 0) != len(obj['pieces']):
            raise ValueError('Source furniture piece count changed')
        parts, metadata = [], []
        color_mode = word(high, 0xca358 + slot * 60 + 0x10) >> 3
        if color_mode not in (0, 2):
            raise ValueError('Unverified furniture color mode')
        storage_bits = 4 if color_mode == 0 else 8
        for piece in obj['pieces']:
            candidates = []
            for record in records:
                if (record['width'], record['height'], record['bits_per_pixel']) != (piece['width'], piece['height'], storage_bits):
                    continue
                count = record['width'] * record['height'] * record['bits_per_pixel'] // 8
                packed = span(sources['MAP001.V1N'], record['payload_offset'], count)
                if span(vram, piece['texture_offset'], count) == packed:
                    candidates.append(record)
            if not candidates:
                raise ValueError('Furniture texture has no exact source record')
            # Repeated animation records contain byte-identical prop textures.
            # Preserve every possible source record; do not infer loader base
            # indices merely to select one of these equally exact matches.
            record = candidates[0]
            if any(candidate['payload'] != record['payload'] for candidate in candidates):
                raise ValueError('Furniture source candidates have different decoded pixels')
            bits = 4 if record['bits_per_pixel'] == 4 else 6
            palette_bytes = (1 << bits) * 2
            palette_cram = (1024 + (piece['colr'] & 1023)) * 2
            palette_source = PALETTE_SOURCE_OFFSET + palette_cram - PALETTE_CRAM_OFFSET
            if span(cram, palette_cram, palette_bytes) != span(raw_map, palette_source, palette_bytes):
                raise ValueError('Furniture palette differs from its source')
            image = decode_piece(record['payload'], piece['width'], piece['height'], bits,
                                 piece['colr'], cram, regs, piece['flip_x'])
            parts.append((image, tuple(piece['offset'])))
            sprite_priority = sprite_code_rgba(piece['colr'] | 1, cram, regs)[1]
            metadata.append({**piece, 'source_texture': {k: v for k, v in record.items() if k != 'payload'},
                             'identical_source_records': [{k: v for k, v in candidate.items() if k != 'payload'} for candidate in candidates],
                             'runtime_to_unique_source_record_verified': len(candidates) == 1,
                             'source_selection': 'canonical byte-identical record; aliases retained without asserting loader base',
                             'color_mode': color_mode,
                             'palette_source_offset': palette_source, 'palette_cram_offset': palette_cram,
                             'palette_bytes': palette_bytes, 'sprite_priority': sprite_priority})
        image, anchor = compose_pieces(parts)
        name = f'prop-{slot:02d}.png'
        images.append((name, image))
        props.append({'id': obj['id'], 'slot': slot, 'file': name,
                      'world_xy_raw': obj['world_xy_raw'], 'world_anchor': [n / 16 for n in obj['world_xy_raw']],
                      'anchor': anchor, 'width': image.width, 'height': image.height,
                      'render_flags': obj['render_flags'], 'y_sorted': obj['y_sorted'],
                      'source_image_offset': 8 + pointer, 'source_image_bytes': len(record_raw),
                      'source_image_sha256': sha(record_raw), 'record_address': obj['record_address'],
                      'pieces': metadata})
    if [p['slot'] for p in props] != list(range(6)):
        raise ValueError('The six source furniture slots are incomplete')
    # A valid order at each frame alone would not prove that freezing an image
    # is safe. Recheck the exact graphics-affecting object fields and texels in
    # EVERY sealed sample, including release and turn transitions.
    immutable = []
    fields = [(0, 4), (0xa, 2), (0xe, 8), (0x16, 2), (0x22, 2), (0x30, 4)]
    table = longword(high, 0x741e0) & 0xfffff
    for run in proof['captures']:
        folder = Path(run['folder'])
        checked = capture if folder.resolve() == capture_folder.resolve() else inspect(folder)
        if checked['manifest_sha256'] != run['manifest_sha256']:
            raise ValueError('A furniture reference capture changed')
        samples_checked = 0
        for frame in checked['samples']:
            content = {}
            for name in ('wram-high.bin', 'vram1.bin', 'cram.bin'):
                relative = f'frame-{frame:06d}/' + name
                value = stable_read(folder / relative)
                if sha(value) != checked['outputs'][relative]:
                    raise ValueError('Furniture immutability sample changed after its gate')
                content[name] = value
            current = content['wram-high.bin']
            if longword(current, 0x741e0) != longword(high, 0x741e0):
                raise ValueError('Furniture texture table moved')
            for prop in props:
                start = 0xca358 + prop['slot'] * 60
                if any(current[start + offset:start + offset + count] != high[start + offset:start + offset + count] for offset, count in fields):
                    raise ValueError('Furniture graphics state is animated or moved')
                source_offset = prop['source_image_offset']
                ram_offset = 0xe0000 + source_offset - 8
                size = prop['source_image_bytes']
                if current[ram_offset:ram_offset + size] != raw_map[source_offset:source_offset + size]:
                    raise ValueError('Furniture source image record changed')
                for piece in prop['pieces']:
                    record = piece['source_texture']
                    address = table + piece['runtime_texture_id'] * 10
                    if current[address:address + 10] != high[address:address + 10]:
                        raise ValueError('Furniture texture mapping changed')
                    size = record['width'] * record['height'] * record['bits_per_pixel'] // 8
                    if span(content['vram1.bin'], piece['texture_offset'], size) != span(sources['MAP001.V1N'], record['payload_offset'], size):
                        raise ValueError('Furniture runtime texels changed')
                    if span(content['cram.bin'], piece['palette_cram_offset'], piece['palette_bytes']) != span(raw_map, piece['palette_source_offset'], piece['palette_bytes']):
                        raise ValueError('Furniture palette changed')
            samples_checked += 1
        immutable.append({'capture': str(folder.resolve()), 'manifest_sha256': run['manifest_sha256'],
                          'samples': samples_checked, 'slots_per_sample': 6, 'passed': True})
    if len(immutable) != 4 or sum(r['samples'] for r in immutable) != 688:
        raise ValueError('Furniture immutability lacks all four complete capture sequences')
    if stable_read(order_report) != report_raw:
        raise ValueError('Order proof changed during furniture export')
    output = output.resolve()
    if not output.is_relative_to((ROOT / 'reports').resolve()):
        raise ValueError('Original furniture must remain in ignored local reports')
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, image in images:
        path = output / name
        image.save(path)
        files[name] = {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes()), 'rgba_sha256': sha(image.tobytes()),
                       'width': image.width, 'height': image.height}
    result = {'schema': 'ao_pc_character_scene_props_v1', 'source_local_only': True, 'passed': True,
              'camera': [544, 1536], 'viewport': [320, 224], 'props': props, 'files': files,
              'source_files': {name: {'path': str((workspace / 'work/extract' / name).resolve()), 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sources.items()},
              'source_region': {'file': 'MAP001.TWN', 'offset': 8, 'bytes': region_size, 'runtime_address': 0x060e0000, 'sha256': sha(raw_map[8:8+region_size])},
              'order_proof': {'path': str(order_report.resolve()), 'sha256': sha(report_raw)},
              'immutable_prop_evidence': {'passed': True, 'samples_compared': 688, 'slots': list(range(6)),
                  'capture_manifests': {Path(r['capture']).name: r['manifest_sha256'] for r in immutable}, 'runs': immutable},
              'capture': {'path': str(capture_folder.resolve()), 'manifest_sha256': capture['manifest_sha256']},
              'limits': ['Six static furniture slots only; original NPC/direct-list animated objects 6/7 are omitted.',
                         'Furniture must follow the verified bucket/priority model, not unconditional foreground.',
                         'No shadow, NPC animation or complete scene-composition claim.']}
    (output / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--order-report', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = export(args.capture, args.order_report, args.out)
    print(json.dumps({'passed': result['passed'], 'props': len(result['props']), 'out': str(args.out)}))


if __name__ == '__main__':
    main()
