"""Bind one captured MAP001 player pose to source bytes and visible pixels."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from character_graphics import (ROOT, WORKSPACE, PlayerResource, bind_command, compare_visible,
                                oriented_image, rgba_texture, sha, word, PALETTE_CRAM_OFFSET,
                                PALETTE_SOURCE_OFFSET, RESOURCE_FILE_OFFSET, RESOURCE_BYTES,
                                executed_command, compare_framebuffer, BackgroundSource,
                                rectangular_code, sprite_code_rgba, MAP_V1N_SHA256, span)
from exploration_capture import inspect_snapshot, read_json_bytes, stable_read
from read_ymir_state import extract
from trace_vdp1 import trace, TraceError


def validate_capture(folder: Path, output: Path | None = None, workspace: Path = WORKSPACE) -> dict:
    """Validate actual body draws and delayed presentation; visibility is separate.

    This bounded observed profile uses previous-two-sample body state and the
    current-sample camera. Every frame must demonstrate it; it is not a general
    Saturn timing assumption. The seed body's inherited pixels stay explicit.
    """
    from verify_character_capture import inspect, VDP2_ADDRESSES
    from pipeline import parse_v1n
    from decode_background import parameters
    from decode_source_scene import pattern_word
    capture = inspect(folder)
    def read(name):
        raw = stable_read(folder / name)
        if sha(raw) != capture['outputs'][name]:
            raise ValueError('Capture changed after integrity gate: ' + name)
        return raw
    sources = {name: stable_read(workspace / 'work/extract' / name) for name in ['PARTY0.PTY', 'MAP001.TWN', 'TWN.BIN']}
    resource = PlayerResource(sources['PARTY0.PTY'], sources['MAP001.TWN'], sources['TWN.BIN'])
    background = BackgroundSource(sources['MAP001.TWN'])
    source_v1n = stable_read(workspace / 'work/extract/MAP001.V1N')
    if sha(source_v1n) != MAP_V1N_SHA256:
        raise ValueError('Changed MAP001 prop source')
    prop_sources = {r['packed_sha256']: r for r in parse_v1n(source_v1n)}
    samples, events = capture['samples'], capture['vdp_events']
    events_by_frame = {}
    for event in events:
        events_by_frame.setdefault(event['frame'], []).append(event)
    low = read('frame-000000/wram-low.bin')
    actors = {f: bytes.fromhex(s['player_actor_hex']) for f, s in samples.items()}
    source_images = {f: resource.bind_actor(a, low) for f, a in actors.items()}
    # Subsequent low RAM must retain the exact source resource, not only roots.
    for frame in samples:
        if read(f'frame-{frame:06d}/wram-low.bin')[0x20000:0x20000 + RESOURCE_BYTES] != resource.bank:
            raise ValueError('Runtime character source bank changed')
    by_texture_hash = {sha(t.indices): t for t in resource.textures.values()}
    draws, lines, videos, all_draws, starts = {}, {}, {}, {}, {}
    local = None
    image_outputs = {}
    for event in events:
        kind, frame = event['kind'], event['frame']
        if kind == 'vdp1_begin':
            local = None
            if frame in starts:
                raise ValueError('Multiple draw begins per bounded presentation frame')
            starts[frame] = event
        elif kind == 'vdp2_render_line':
            lines.setdefault(frame, []).append(event)
        elif kind == 'software_video_complete':
            videos[frame] = event
        elif kind == 'command_execute_before':
            raw = bytes.fromhex(event['command_hex'])
            row = executed_command(raw, event['command_address'], tuple(local or (0, 0)))
            if row['command'] == 10:
                local = row['signed_coordinates'][:2]
                continue
            if row['command'] in (0, 1, 2, 3) and 'texture' in event:
                texture_hash = event['texture']['sha256']
                payload = read('blobs/' + texture_hash + '.bin')
                prop = prop_sources.get(texture_hash)
                if prop is not None and span(source_v1n, prop['payload_offset'], len(payload)) != payload:
                    raise ValueError('Captured prop differs from source bytes')
                all_draws.setdefault(frame, []).append({'event_index': event['event_index'], 'command': row,
                    'payload': payload, 'source': prop, 'texture_sha256': texture_hash})
            texture = by_texture_hash.get(event.get('texture', {}).get('sha256'))
            if texture is None or row['colr'] != 0x2000:
                continue
            if local is None or row['command'] != 2:
                raise ValueError('Body draw lacks observed local coordinates/known geometry')
            if event['player_actor_hex'] != samples[frame - 1]['player_actor_hex']:
                raise ValueError('Command-time actor differs from previous sample')
            source_frame = max(0, frame - 2)
            image_record = source_images[source_frame]
            if len(image_record['pieces']) != 1:
                raise ValueError('Multi-piece presentation profile remains unverified')
            piece = image_record['pieces'][0]
            if texture.index != piece['texture_index']:
                raise ValueError('Draw texture differs from previous-two-sample image')
            payload = read('blobs/' + event['texture']['sha256'] + '.bin')
            if payload != texture.indices:
                raise ValueError('Command-time texture differs from source decode')
            camera = tuple(samples[frame]['vdp2'][key] for key in ['SCXIN0', 'SCYIN0'])
            command = bind_command(piece, texture, actors[source_frame], camera, [row], bytes(row['texture_offset']) + payload)
            if command['flip_x'] != bool(word(actors[source_frame], 0x14) & 1) or command['flip_y']:
                raise ValueError('Mirror differs from observed actor flag profile')
            cram = read('blobs/' + event['cram_sha256'] + '.bin')
            if cram[PALETTE_CRAM_OFFSET:PALETTE_CRAM_OFFSET + 128] != resource.palette:
                raise ValueError('Command-time palette differs from source')
            # Final pixel conversion uses the presented frame's registers later.
            if frame in draws:
                raise ValueError('More than one source-bound body per frame')
            draws[frame] = {'frame': frame, 'event_index': event['event_index'], 'draw_bank': event['draw_bank'],
                            'command': command, 'command_hex': event['command_hex'], 'source_state_frame': source_frame,
                            'image_index': image_record['image_index'], 'texture_index': texture.index,
                            'texture_sha256': sha(payload), 'cram_sha256': event['cram_sha256'],
                            'camera_at_command_target': list(camera), 'observed_actor_matches_previous_sample': True,
                            'source_actor_hex': actors[source_frame].hex()}
    count = capture['capture']['frames']
    if set(draws) != set(range(1, count + 1)):
        raise ValueError('Missing source-bound body draw')
    # Build inherited seed body from exact source/RAM geometry; never assign an
    # uncaptured execution event to it.
    seed_vram = read('frame-000000/vram1.bin')
    try:
        seed_rows = trace(seed_vram)
    except TraceError as exc:
        seed_rows = exc.rows
    seed_piece = source_images[0]['pieces'][0]
    seed_texture = resource.textures[seed_piece['texture_index']]
    seed_camera = tuple(samples[0]['vdp2'][key] for key in ['SCXIN0', 'SCYIN0'])
    seed_command = bind_command(seed_piece, seed_texture, actors[0], seed_camera, seed_rows, seed_vram)
    presented = []
    bg_pixel_cache = {}
    def bg_pixel(layer, wx, wy):
        key = layer, wx, wy
        if key not in bg_pixel_cache:
            bg_pixel_cache[key] = background.pixel(layer, wx, wy)
        return bg_pixel_cache[key]
    for frame in range(1, count + 1):
        inherited = frame == 1
        draw = draws[frame - 1] if not inherited else {'frame': None, 'event_index': None,
            'draw_bank': lines[frame][0]['display_bank'], 'command': seed_command,
            'source_state_frame': 0, 'image_index': source_images[0]['image_index'],
            'texture_index': seed_texture.index, 'cram_sha256': sha(read('frame-000000/cram.bin'))}
        bank = draw['draw_bank']
        if len(lines.get(frame, [])) != 224 or any(e['display_bank'] != bank for e in lines[frame]):
            raise ValueError('Body bank was not consumed on all 224 rendered lines')
        if not inherited and draw['event_index'] >= min(e['event_index'] for e in lines[frame]):
            raise ValueError('Body execution does not precede video composition')
        texture, command = resource.textures[draw['texture_index']], draw['command']
        video_event = videos[frame]
        cram = read(f'frame-{frame:06d}/cram.bin')
        if sha(cram) != video_event['cram_sha256'] or sha(cram) != draw['cram_sha256']:
            raise ValueError('Palette changed between body draw and presentation')
        rgba = oriented_image(rgba_texture(texture, cram, samples[frame]['vdp1'], samples[frame]['vdp2'], command['colr'], command['pmod']), command)
        image_name = f'player-texture-{texture.index:02d}-flip-{int(command["flip_x"])}.png'
        image_outputs[image_name] = rgba
        # Vblank erases the just-displayed bank before after_RunFrame sample.
        # The previous sample's completed draw must match the FULL bank hash
        # observed at software_video_complete, otherwise this profile fails.
        framebuffer_sample = frame - 1
        fb = read(f'frame-{framebuffer_sample:06d}/vdp1-fb{bank}.bin')
        if sha(fb) != video_event['framebuffer_sha256'][bank]:
            raise ValueError(f'Presented bank has no exact previous-sample payload at frame {frame}')
        if inherited and sha(fb) != sha(read(f'frame-000000/vdp1-fb{bank}.bin')):
            raise ValueError('Inherited first video differs from seed framebuffer')
        framebuffer = compare_framebuffer(texture, command, fb)
        video = read(f'frame-{frame:06d}/video-rgba.bin')
        visible = compare_visible(rgba, tuple(command['screen_origin']), video, 320, 224)
        # The CPU changes scroll registers after the visible scanlines but
        # before software_video_complete. Read frame-start values, and require
        # every complete observation during active scanout to retain them.
        register_bytes = bytes.fromhex(starts[frame]['vdp2_registers_be_hex'])
        regs = {name: word(register_bytes, offset) for name, offset in VDP2_ADDRESSES.items()}
        relevant = ['SCXIN0', 'SCYIN0', 'SCXIN1', 'SCYIN1', 'PRINA', 'PRISA', 'PRISB', 'PRISC', 'PRISD',
                    'SFPRMD', 'CLOFEN', 'CLOFSL', 'COAR', 'COAG', 'COAB', 'CRAOFA', 'CRAOFB', 'SPCTL', 'CCCTL']
        for observed in events_by_frame[frame]:
            if starts[frame]['event_index'] <= observed['event_index'] <= lines[frame][-1]['event_index'] and 'vdp2_registers_be_hex' in observed:
                raw_regs = bytes.fromhex(observed['vdp2_registers_be_hex'])
                if any(word(raw_regs, VDP2_ADDRESSES[name]) != regs[name] for name in relevant):
                    raise ValueError('Active-scanout registers change within bounded profile')
        background.check_registers(regs)
        if cram[2:512] != background.palette[2:]:
            raise ValueError('Presented background palette differs from source')
        vram2 = read(f'frame-{frame-1:06d}/vram2.bin')
        if vram2[0x40000:] != background.tiles:
            raise ValueError('Presented background tiles differ from source')
        params = [parameters(regs, layer) for layer in (0, 1)]
        later = [] if inherited else [d for d in all_draws[draw['frame']] if d['event_index'] > draw['event_index']]
        explained = Counter()
        unexplained, prop_evidence, bg_evidence = [], {}, {}
        for y in range(texture.height):
            for x in range(texture.width):
                if rgba.getpixel((x, y))[3] == 0:
                    continue
                sx, sy = x + command['screen_origin'][0], y + command['screen_origin'][1]
                if not 0 <= sx < 320 or not 0 <= sy < 224:
                    raise ValueError('Body outside source viewport')
                code = rectangular_code(command, texture.indices, sx, sy)
                occluder = None
                for candidate in later:
                    value = rectangular_code(candidate['command'], candidate['payload'], sx, sy)
                    if value is None:
                        continue
                    source = candidate['source']
                    if source is None:
                        raise ValueError('Overlapping sprite is not bound to MAP001.V1N source')
                    code, occluder = value, candidate
                actual_code = word(fb, (sy * 512 + sx) * 2)
                color, priority = sprite_code_rgba(code, cram, regs)
                # Bind the actually used prop palette, not a guessed generic bank.
                if occluder is not None:
                    colr = occluder['command']['colr']
                    palette_offset = (1024 + (colr & 1023)) * 2
                    palette_bytes = 32 if occluder['command']['color_mode'] == 0 else 128
                    source_offset = PALETTE_SOURCE_OFFSET + palette_offset - PALETTE_CRAM_OFFSET
                    if cram[palette_offset:palette_offset + palette_bytes] != span(sources['MAP001.TWN'], source_offset, palette_bytes):
                        raise ValueError('Occluder palette differs from source')
                    key = occluder['event_index']
                    prop_evidence[key] = {'event_index': key, 'command': occluder['command'],
                        'texture_sha256': occluder['texture_sha256'],
                        'source_record': {k: v for k, v in occluder['source'].items() if k != 'payload'},
                        'palette_source_offset': source_offset, 'palette_cram_offset': palette_offset}
                front = None
                # NBG1 is beneath NBG0 at equal priority. Sprite wins priority ties.
                for layer in (1, 0):
                    wx, wy = sx + params[layer]['scroll_x'], sy + params[layer]['scroll_y']
                    bg = bg_pixel(layer, wx, wy)
                    page = ((wx % 1024) // 512) + ((wy % 1024) // 512) * 2
                    pattern_offset = params[layer]['plane_offsets'][page] + (((wy // 16) % 32) * 32 + (wx // 16) % 32) * 4
                    if int.from_bytes(span(vram2, pattern_offset, 4), 'big') != pattern_word(bg['compact_pattern']):
                        raise ValueError('Presented background pattern differs from source layout')
                    if bg['index'] and bg['priority'] > priority:
                        color, front = bg['rgba'], bg
                if front:
                    key = front['layer'], front['layout_offset']
                    bg_evidence[key] = front | {'world_pixel_example': [sx + params[front['layer']]['scroll_x'], sy + params[front['layer']]['scroll_y']]}
                actual = tuple(video[(sy * 320 + sx) * 4:(sy * 320 + sx) * 4 + 4])
                if actual_code != code or actual != color:
                    unexplained.append({'screen_pixel': [sx, sy], 'predicted_code': code, 'actual_code': actual_code,
                                        'predicted_rgba': color, 'actual_rgba': actual})
                else:
                    explained['nbg_foreground' if front else 'vdp1_prop' if occluder else 'body'] += 1
        composition = {'passed': not unexplained, 'explained_pixels': dict(explained),
                       'unexplained_pixels': len(unexplained), 'differences': unexplained,
                       'prop_occluders': list(prop_evidence.values()), 'foreground_patterns': list(bg_evidence.values())}
        presented.append({'video_frame': frame, 'draw_frame': draw['frame'], 'draw_event_index': draw['event_index'],
                          'inherited_seed': inherited, 'source_state_frame': draw['source_state_frame'],
                          'image_index': draw['image_index'], 'texture_index': texture.index, 'image': image_name,
                          'compose_bank': bank, 'line_event_first': lines[frame][0]['event_index'],
                          'framebuffer_payload_sample': framebuffer_sample, 'framebuffer_sha256': sha(fb),
                          'scanout_register_event_index': starts[frame]['event_index'],
                          'scanout_camera': [regs['SCXIN0'], regs['SCYIN0']],
                          'line_event_last': lines[frame][-1]['event_index'], 'video_event_index': video_event['event_index'],
                          'command_origin': command['screen_origin'], 'command_anchor': command['screen_anchor'],
                          'framebuffer': framebuffer, 'visible': visible, 'composition': composition})
    counts = Counter()
    for item in presented:
        counts['opaque_pixels'] += item['visible']['matching_opaque_pixels'] + item['visible']['mismatched_opaque_pixels']
        counts['visible_matches'] += item['visible']['matching_opaque_pixels']
        counts['visible_mismatches'] += item['visible']['mismatched_opaque_pixels']
        counts['framebuffer_mismatches'] += item['framebuffer']['mismatched_opaque_codes']
        counts['unexplained_pixels'] += item['composition']['unexplained_pixels']
        for key, value in item['composition']['explained_pixels'].items():
            counts['explained_' + key] += value
    result = {'schema': 'ao_pc_character_presentation_v1', 'identity': 'MAP001 player',
              'capture': str(folder.resolve()), 'capture_manifest_sha256': capture['manifest_sha256'],
              'source_hashes': resource.source_hashes, 'frames': count,
              'passed': all(p['composition']['passed'] for p in presented),
              'source_command_binding_passed': True, 'command_execution_verified': True,
              'observed_delay_profile_passed': True, 'delay_profile': {
                  'executed_actor_sample_lag': 1, 'executed_body_source_sample_lag': 2,
                  'executed_body_camera_sample_lag': 0, 'draw_to_presented_video_lag': 1,
                  'presented_body_source_sample_lag': 3,
                  'scanout_camera': 'vdp1_begin observation, stable in all complete active-scanout observations',
                  'presented_framebuffer_payload': 'previous sample same bank; full hash must equal software_video_complete bank hash',
                  'initial_history': 'Sample 0 repeats only while the required pre-capture history is inherited.'},
              'all_opaque_pixels_match': all(p['visible']['passed'] for p in presented),
              'all_opaque_framebuffer_codes_match': all(p['framebuffer']['passed'] for p in presented),
              'visible_composition_passed': all(p['composition']['passed'] for p in presented),
              'foreground_source': {'map001_v1n_sha256': MAP_V1N_SHA256, 'map001_twn_sha256': resource.source_hashes['MAP001.TWN'],
                  'rule': 'Actual source-bound VDP1 commands after body, then source NBG0/1 opaque special-priority 3 pixels above priority-2 sprite'},
              'counts': dict(counts), 'draws': list(draws.values()), 'presentation': presented,
              'limits': ['Three-sample displayed-body delay is an observed bounded profile; every new capture must pass it.',
                         'First video is seed framebuffer inheritance, not a recorded body execution.',
                         'Raw body-only visibility differences remain explicit; independently predicted source composition is a separate gate.',
                         'Observed camera scroll is retained for source comparison; fixed-camera PC reprojection uses source world anchor.',
                         'Only body opaque pixels are tested. Shadow-only and all other scene pixels are outside this gate.',
                         'No generic VDP1 distortion/shadow or complete VDP2 compositor is claimed.']}
    if sha(stable_read(folder / 'manifest.json')) != capture['manifest_sha256']:
        raise ValueError('Capture manifest changed during presentation verification')
    for name, raw in sources.items():
        if stable_read(workspace / 'work/extract' / name) != raw:
            raise ValueError('Source changed during presentation verification')
    if output is not None:
        output = output.resolve()
        if not output.is_relative_to((ROOT / 'reports').resolve()):
            raise ValueError('Original-derived output must remain in ignored local reports')
        output.mkdir(parents=True, exist_ok=False)
        for name, image in image_outputs.items():
            image.save(output / name)
        (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def export_foreground(index_path: Path, output: Path, workspace: Path = WORKSPACE) -> dict:
    index_raw = stable_read(index_path)
    index = read_json_bytes(index_raw)
    if index.get('schema') != 'ao_pc_character_presentation_index_v1' or index.get('passed') is not True or set(index.get('reports', {})) != {'cardinal', 'corners', 'open', 'release'}:
        raise ValueError('Four approved presentation reports are required')
    for record in index['reports'].values():
        raw = stable_read(Path(record['path']))
        if sha(raw) != record['sha256']:
            raise ValueError('Approved presentation report changed')
        report = read_json_bytes(raw)
        if not report.get('visible_composition_passed') or report.get('counts', {}).get('unexplained_pixels') != 0:
            raise ValueError('Unexplained visibility cannot approve foreground')
    raw = stable_read(workspace / 'work/extract/MAP001.TWN')
    source = BackgroundSource(raw)
    image = source.foreground()
    output = output.resolve()
    if not output.is_relative_to((ROOT / 'reports').resolve()):
        raise ValueError('Original-derived output must remain in ignored local reports')
    output.mkdir(parents=True, exist_ok=False)
    path = output / 'nbg-priority-foreground.png'
    image.save(path)
    manifest = {'schema': 'ao_pc_character_foreground_v1', 'source_local_only': True,
                'camera': [544, 1536], 'viewport': [320, 224],
                'rule': {'sprite_priority': 2, 'foreground_priority': 3, 'layers': [0, 1], 'equal_background_priority_winner': 0},
                'source_hashes': {'MAP001.TWN': sha(raw)}, 'presentation_index_sha256': sha(index_raw),
                'files': {path.name: {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes()),
                                     'rgba_sha256': sha(image.tobytes()), 'width': 320, 'height': 224}},
                'limits': ['This static layer encodes only NBG0/1 priority above the priority-2 player.',
                           'VDP1 furniture uses separate conditional order; no shadow or full-scene claim.']}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def validate(frame: Path, expected_snapshot_sha256: str, output: Path | None = None,
             workspace: Path = WORKSPACE) -> dict:
    names = ['state.savestate', 'wram-low.bin', 'wram-high.bin', 'vram1.bin', 'vram2.bin', 'cram.bin', 'video-rgba.bin', 'sample.json']
    inputs = {name: stable_read(frame / name) for name in names}
    if sha(inputs['state.savestate']) != expected_snapshot_sha256:
        raise ValueError('Snapshot differs from the requested reference pin')
    snapshot_info = inspect_snapshot(inputs['state.savestate'])
    parsed = extract(inputs['state.savestate'], snapshot_info['parser_lock'])
    for name in ['vram1', 'vram2', 'cram']:
        if inputs[name + '.bin'] != parsed['blocks'][name]:
            raise ValueError('Snapshot/dump coherence failed: ' + name)
    for name in ['wram-low.bin', 'wram-high.bin']:
        if len(inputs[name]) != 0x100000:
            raise ValueError('Incomplete synchronized RAM: ' + name)
    regions = snapshot_info['regions']
    for name, region in [('wram-low.bin', 'wram_low'), ('wram-high.bin', 'wram_high')]:
        identity = regions.get(region)
        if identity is None:
            raise ValueError('Snapshot reader lacks RAM region identity: ' + region)
        if sha(inputs[name]) != identity['sha256']:
            raise ValueError('Snapshot/RAM coherence failed: ' + name)
    sample = read_json_bytes(inputs['sample.json'])
    if sample.get('schema') not in ['ao_ymir_frame_sample_v1', 'ao_ymir_frame_sample_v2']:
        raise ValueError('Unsupported synchronized sample format')
    if sample.get('boundary') != 'after_RunFrame_return' or (sample.get('video_width'), sample.get('video_height')) != (320, 224):
        raise ValueError('Unsupported video dimensions or capture boundary')
    high, low = inputs['wram-high.bin'], inputs['wram-low.bin']
    if high[0xc27ae] != 0 or word(high, 0xc27aa) != 3 or high[0xc41ec] != 0:
        raise ValueError('Controlled actor/gate differs from verified MAP001 slot')
    actor = high[0xc8758:0xc87c8]
    paths = {name: workspace / 'work/extract' / name for name in ['PARTY0.PTY', 'MAP001.TWN', 'TWN.BIN']}
    sources = {name: stable_read(path) for name, path in paths.items()}
    resource = PlayerResource(sources['PARTY0.PTY'], sources['MAP001.TWN'], sources['TWN.BIN'])
    image_record = resource.bind_actor(actor, low)
    if inputs['cram.bin'][PALETTE_CRAM_OFFSET:PALETTE_CRAM_OFFSET + 128] != resource.palette:
        raise ValueError('Runtime character palette differs from MAP001.TWN source')
    camera = tuple(parsed['regs2'][key] for key in ['SCXIN0', 'SCYIN0'])
    if camera != (544, 1536):
        raise ValueError('Camera differs from validated fixed MAP001 viewport')
    failure = None
    try:
        rows = trace(inputs['vram1.bin'])
    except TraceError as error:
        rows = error.rows
        failure = {'offset': error.offset, 'error': str(error)}
    images, components = [], []
    for piece in image_record['pieces']:
        texture = resource.textures[piece['texture_index']]
        command = bind_command(piece, texture, actor, camera, rows, inputs['vram1.bin'])
        intrinsic = rgba_texture(texture, inputs['cram.bin'], parsed['regs1'], parsed['regs2'], command['colr'], command['pmod'])
        oriented = oriented_image(intrinsic, command)
        comparison = compare_visible(oriented, tuple(command['screen_origin']), inputs['video-rgba.bin'], 320, 224)
        bank_matches = []
        for bank in range(2):
            framebuffer = parsed['blocks']['framebuffers'][bank * 0x40000:(bank + 1) * 0x40000]
            matching = opaque = 0
            for y in range(oriented.height):
                for x in range(oriented.width):
                    if oriented.getpixel((x, y))[3] == 0:
                        continue
                    sx, sy = x + command['screen_origin'][0], y + command['screen_origin'][1]
                    if not 0 <= sx < 512 or not 0 <= sy < 256:
                        continue
                    tx = texture.width - 1 - x if command['flip_x'] else x
                    ty = texture.height - 1 - y if command['flip_y'] else y
                    raw_code = (command['colr'] & 0xffc0) | texture.indices[ty * texture.width + tx]
                    opaque += 1
                    matching += word(framebuffer, (sy * 512 + sx) * 2) == raw_code
            bank_matches.append({'bank': bank, 'matching_opaque_codes': matching, 'tested_opaque_codes': opaque, 'all_match': opaque > 0 and matching == opaque})
        name = f'player-image-{image_record["image_index"]:02d}-piece-{piece["slot"]}.png'
        images.append((name, oriented))
        components.append({'piece': piece, 'texture': texture.metadata(), 'command': command,
                           'command_hex': inputs['vram1.bin'][command['offset']:command['offset'] + 32].hex(),
                           'rgba_sha256': sha(oriented.tobytes()), 'image': name,
                           'visible_comparison': comparison, 'framebuffer_code_comparisons': bank_matches})
    report = {'schema': 'ao_pc_character_graphics_v1', 'identity': 'MAP001 player',
              'actor_address': 0x060c8758, 'actor_hex': actor.hex(), 'frame': sample['frame'],
              'sample_boundary': sample['boundary'], 'scheduler_count': sample['scheduler_count'],
              'camera': list(camera), 'snapshot_sha256': expected_snapshot_sha256,
              'capture_files': {name: {'path': str((frame / name).resolve()), 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in inputs.items()},
              'source_files': {name: {'path': str(paths[name].resolve()), 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sources.items()},
              'source_code_ranges': resource.code_ranges,
              'source_resource': {'file_offset': RESOURCE_FILE_OFFSET, 'bytes': RESOURCE_BYTES, 'runtime_address': 0x20220000, 'sha256': sha(resource.bank), 'whole_bank_matches_runtime': True},
              'palette': {'source_file': 'MAP001.TWN', 'source_offset': PALETTE_SOURCE_OFFSET,
                          'cram_offset': PALETTE_CRAM_OFFSET, 'bytes': 128, 'sha256': sha(resource.palette),
                          'rgba_convention': 'Ymir ConvertRGB555to888: component << 3; source index 0 is transparent'},
              'image_record': image_record, 'components': components,
              'registers1': parsed['regs1'], 'registers2': parsed['regs2'],
              'snapshot_display_bank': parsed['display_framebuffer'], 'snapshot_drawing': parsed['drawing'],
              'ram_list_failure': failure, 'command_execution_verified': False,
              'source_decode_passed': True, 'visible_pixels_passed': all(c['visible_comparison']['passed'] for c in components),
              'limits': ['RAM-list reachability does not prove command execution; v2 execution/compose-bank events are required.',
                         'Frame-end display bank can differ from the bank that produced this video; both banks are reported without guessing.',
                         'Only opaque body pixels and one-to-one geometry are compared; no generic shadow, distortion, clipping or complete VDP composition.',
                         'Current command mirror bits are preserved; animation-to-mirror rules and multi-piece attributes remain unverified.',
                         'The same first resource is present in PARTY2.PTY; choosing PARTY0 as an exact source does not establish which loader read it.']}
    # Re-read before publication, preserving read-only, synchronous input identity.
    for name, raw in inputs.items():
        if stable_read(frame / name) != raw:
            raise ValueError('Capture changed during graphics verification: ' + name)
    for name, raw in sources.items():
        if stable_read(paths[name]) != raw:
            raise ValueError('Source changed during graphics verification: ' + name)
    if output is not None:
        output = output.resolve()
        if not output.is_relative_to((ROOT / 'reports').resolve()):
            raise ValueError('Original-derived output must remain in ignored local reports')
        output.mkdir(parents=True, exist_ok=False)
        for name, image in images:
            image.save(output / name)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--frame', type=Path)
    group.add_argument('--capture', type=Path)
    parser.add_argument('--snapshot-sha256')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.capture:
        result = validate_capture(args.capture, args.out)
        print(json.dumps({key: result[key] for key in ['passed', 'frames', 'source_command_binding_passed', 'visible_composition_passed', 'counts']}))
        if not result['passed']:
            raise SystemExit(1)
    else:
        if not args.snapshot_sha256:
            parser.error('--frame requires an explicit --snapshot-sha256')
        result = validate(args.frame, args.snapshot_sha256, args.out)
        print(json.dumps({key: result[key] for key in ['source_decode_passed', 'visible_pixels_passed', 'command_execution_verified', 'image_record']}))


if __name__ == '__main__':
    main()
