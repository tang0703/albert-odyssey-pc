"""Recheck the bounded MAP001 background and flags against a newly named state."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
from pipeline import PROJECT, WORKSPACE, digest, verify_source
from exploration_capture import inspect_snapshot, read_json_bytes, stable_read
from read_ymir_state import extract
from probe_scene_metadata import system_ram
from decode_source_scene import source_data, render_view, CAMERA
from decode_scene_flags import decode_flags, verify_reader
from decode_background import parameters, decode_page, viewport


def validate(snapshot: Path, output: Path, expected_snapshot_sha256: str | None = None) -> dict:
    if output.exists():
        raise ValueError('Use a new scene validation output directory')
    raw_state = stable_read(snapshot)
    if expected_snapshot_sha256 is not None and digest(raw_state) != expected_snapshot_sha256:
        raise ValueError('Named snapshot SHA256 changed')
    inspection = inspect_snapshot(raw_state)
    lock = inspection['parser_lock']
    state = extract(raw_state, lock)
    low, high, _ = system_ram(raw_state, lock)
    source_lock_raw = stable_read(PROJECT / 'source-lock.json')
    sources = read_json_bytes(source_lock_raw)['sources']
    raw = verify_source(WORKSPACE, 'work/extract/MAP001.TWN', sources['work/extract/MAP001.TWN'])
    code = verify_source(WORKSPACE, 'work/extract/TWN.BIN', sources['work/extract/TWN.BIN'])
    reader_ranges = verify_reader(code)
    tiles, layout, palette, blocks = source_data(raw)
    if state['blocks']['vram2'][0x40000:0x80000] != tiles:
        raise ValueError('Source tiles differ from newly captured VRAM')
    if state['blocks']['cram'][2:512] != palette[2:]:
        raise ValueError('Nontransparent palette differs from new capture')
    block = blocks[2]
    payload = raw[block['payload_offset']:block['payload_offset'] + block['size']]
    flags, _ = decode_flags(payload)
    if high[0xf4000:0xf4000 + len(payload)] != payload or low[0x10000:0x20000] != flags:
        raise ValueError('MAP001 metadata or expanded flags differ from new state')
    images, layers = [], []
    for layer in (0, 1):
        params = parameters(state['regs2'], layer)
        if (params['scroll_x'], params['scroll_y']) != CAMERA:
            raise ValueError('New camera is outside the previously decoded fixed view')
        image, records = render_view(tiles, layout, palette, layer)
        for record in records:
            x, y = record['world_tile']
            # Validate using the captured plane map, not an assumed VRAM page.
            page = ((x * 16) % 1024) // 512 + (((y * 16) % 1024) // 512) * 2
            offset = params['plane_offsets'][page] + ((y % 32) * 32 + x % 32) * 4
            if offset < 0 or offset + 4 > len(state['blocks']['vram2']):
                raise ValueError('Captured pattern page exceeds VRAM')
            if struct.unpack_from('>I', state['blocks']['vram2'], offset)[0] != record['vdp2_pattern']:
                raise ValueError('Visible pattern differs from captured page')
        pages = [decode_page(state['blocks']['vram2'], state['blocks']['cram'], offset, params)[0]
                 for offset in params['plane_offsets']]
        actual = viewport(pages, *CAMERA)
        if actual.tobytes() != image.tobytes():
            raise ValueError('Source pixels differ from new VRAM rendering')
        images.append(image)
        layers.append({'layer': layer, 'patterns': len(records), 'rgba_sha256': digest(image.tobytes()),
                       'priority_register': state['regs2']['PRINA'], 'parameters': params})
    if (stable_read(snapshot) != raw_state or stable_read(PROJECT / 'source-lock.json') != source_lock_raw
            or stable_read(WORKSPACE / 'work/extract/MAP001.TWN') != raw
            or stable_read(WORKSPACE / 'work/extract/TWN.BIN') != code):
        raise ValueError('Snapshot or pinned source changed during scene validation')
    output.mkdir(parents=True)
    for layer, image in enumerate(images):
        image.save(output / f'nbg{layer}.png')
    (output / 'flags.bin').write_bytes(flags)
    report = {'schema': 'ao_pc_exploration_scene_v1', 'passed': True,
              'source_sha256': digest(raw), 'snapshot_sha256': digest(raw_state),
              'source_code_sha256': digest(code), 'source_lock_sha256': digest(source_lock_raw),
              'reader_ranges': reader_ranges,
              'camera': list(CAMERA), 'viewport': [320, 224], 'layers': layers,
              'flags_sha256': digest(flags), 'flag_bytes_matched': len(flags),
              'outputs': {name: {'bytes': (output / name).stat().st_size,
                                 'sha256': digest(stable_read(output / name))}
                          for name in ('nbg0.png', 'nbg1.png', 'flags.bin')},
              'limits': ['Only two background layers; no sprite/foreground/effect composition claim.',
                         'Fixed captured camera, not the full original camera controller.',
                         'Flag equality does not prove collision or player identity.']}
    (output / 'scene-validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--snapshot-sha256', help='Expected identity from the independent capture manifest')
    a = p.parse_args()
    try:
        r = validate(a.snapshot, a.out, a.snapshot_sha256)
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        p.exit(1, f'Scene validation rejected: {exc}\n')
    print(json.dumps({'passed': r['passed'], 'camera': r['camera'], 'flag_bytes_matched': r['flag_bytes_matched']}))
