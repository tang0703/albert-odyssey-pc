"""Export original-source pose references, never guessed HD or rasterized gameplay.

Runtime execution, mirror/anchor parity and occlusion remain separate A1 gates.
All extracted originals and the resulting art stay in ignored local reports.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw
import character_animation as animation
import character_graphics as graphics
from exploration_capture import stable_read
from validate_character_graphics import validate

SEED_SHA = '72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54'
DIRECTIONS = [('down', 2), ('left', 4), ('right', 0), ('up', 6)]


def export(output: Path) -> dict:
    if output.exists():
        raise ValueError('Reference-art output must be a new directory')
    seed = graphics.ROOT / 'reports/exploration/e1-nav-05/frame-000600'
    proof = validate(seed, SEED_SHA)
    if not proof['source_decode_passed'] or not proof['visible_pixels_passed']:
        raise ValueError('Seed source/pixel binding failed')
    high, low, cram = [stable_read(seed / name) for name in ('wram-high.bin', 'wram-low.bin', 'cram.bin')]
    profile = animation.profile_from_snapshot(high, low)
    source = graphics.WORKSPACE / 'work/extract'
    resource = graphics.PlayerResource(*[stable_read(source / name) for name in ('PARTY0.PTY', 'MAP001.TWN', 'TWN.BIN')])
    command = proof['components'][0]['command']
    contact = Image.new('RGB', (1280, 1024), '#14222a')
    draw = ImageDraw.Draw(contact)
    rows, files = [], {}
    output.mkdir(parents=True)
    for row, (direction, heading) in enumerate(DIRECTIONS):
        for column in range(5):
            walking = column > 0
            cursor = (column - 1) * 3 if walking else 0
            selected = heading + (8 if walking else 0)
            duration, image_index, flags = profile.read_record(selected, cursor)
            record = resource.image(image_index)
            if len(record['pieces']) != 1 or record['pieces'][0]['attributes'] != 0:
                raise ValueError('Reference export requires a proven single-piece player image')
            piece = record['pieces'][0]
            texture = resource.textures[piece['texture_index']]
            image = graphics.rgba_texture(texture, cram, proof['registers1'], proof['registers2'], command['colr'], command['pmod'])
            mirrored = bool(flags & 4)
            if mirrored:
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            action = f'walk-{column-1:02d}' if walking else 'idle'
            name = direction + '-' + action + '.png'
            path = output / name
            image.save(path)
            raw = stable_read(path)
            files[name] = {'bytes': len(raw), 'sha256': graphics.sha(raw)}
            anchor = [-piece['offset'][0], -piece['offset'][1]]
            rows.append({'id': 'map001_player/' + direction + '/' + action, 'direction': direction,
                'heading': heading, 'action': 'walk' if walking else 'idle', 'primary_index': column-1 if walking else None,
                'animation_index': selected, 'animation_cursor': cursor, 'duration_updates': duration,
                'source_record_flags': flags, 'baked_mirror_x': mirrored, 'image_index': image_index,
                'anchor': anchor, 'dimensions': list(image.size), 'file': name,
                'image_record': record, 'texture': texture.metadata()})
            x, y = column * 256, row * 256
            draw.text((x + 10, y + 10), f'{direction.upper()} / {action}', fill='#ecf2e8')
            draw.text((x + 10, y + 28), f'image {image_index:02d} | anchor {anchor} | mirror {mirrored}', fill='#9fb7be')
            draw.line((x + 20, y + 200, x + 236, y + 200), fill='#446c71')
            enlarged = image.resize((image.width * 4, image.height * 4), Image.Resampling.NEAREST)
            contact.paste(enlarged, (x + 128 - anchor[0] * 4, y + 200 - anchor[1] * 4), enlarged)
            draw.ellipse((x + 125, y + 197, x + 131, y + 203), fill='#fff1b3')
            draw.text((x + 10, y + 232), 'Dot = original actor origin (not sole)', fill='#9fb7be')
    contact.save(output / 'contact.png')
    manifest = {'schema': 'ao_pc_character_reference_art_v1', 'character_id': 'map001_player',
        'source_local_only': True, 'seed_sha256': SEED_SHA, 'source_files': proof['source_files'],
        'source_palette': proof['palette'], 'animation_profile': profile.metadata(), 'frames': rows,
        'files': files, 'frame_count': len(rows), 'runtime_execution_accepted': False,
        'scope': 'Source-decoded primary pose references. Runtime timing, mirror mapping and occlusion need the separate execution report; no HD art.'}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if len(rows) != 20:
        raise ValueError('Expected four directions, one idle and four original major poses each')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = export(args.output)
    print(json.dumps({'frames': result['frame_count'], 'source_decode': True, 'runtime_execution_accepted': False}))
