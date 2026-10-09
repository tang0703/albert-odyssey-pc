"""Integrity and synchronized VDP observation gate for the separate v2 capture backend.

The v1 verifier is deliberately unchanged. This gate is not proof that an
animation/display or movement reconstruction matches the game.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from PIL import Image
from exploration_capture import REGISTERS2, inspect_snapshot, read_json_bytes, stable_read
from verify_exploration_replay import (BOUNDARY, MEMORY as BASE_MEMORY, arguments,
    digest, integer, output_path, pinned_inputs, sha, watches)

MEMORY = {**BASE_MEMORY, 'vdp1-fb0.bin': 0x40000, 'vdp1-fb1.bin': 0x40000}
PROJECT = Path(__file__).resolve().parents[1]
CAPTURE_SOURCE = PROJECT / 'tools/ymir_character_capture'
YMIR_REVISION = '54fead6a0001d3e4b6741a8d095ee8342266c3dc'
CEREAL_REVISION = 'ebef1e929807629befafbb2918ea1a08c7194554'
ORIGINAL_VDP_SHA256 = 'ab9cfce4c31f81e80874579779d8eefa976113a34a159036600fc4d9118e1202'
V1_PATHS = {PROJECT / ('tools/ymir_capture/' + name) for name in
            ('main.cpp', 'CMakeLists.txt', 'build.ps1', 'capture.ps1', 'README.md', 'verify_backend.py')} | {
    PROJECT / 'reports/exploration/ymir-capture-build/Release/ao-ymir-capture.exe',
    PROJECT / 'reports/exploration/ymir-capture-build/build-manifest.json'}
# Pinned Ymir VDP2Regs::Read<true> address order: two reserved holes.
VDP2_ADDRESSES = dict(zip(REGISTERS2, (a for a in range(0, 0x120, 2) if a not in (0x00c, 0x0fe))))

def validate_build(build: dict) -> None:
    if build.get('ymir_revision') != YMIR_REVISION or build.get('cereal_revision') != CEREAL_REVISION:
        raise ValueError('Unsupported pinned Ymir/serializer revision')
    required = {'main.cpp', 'CMakeLists.txt', 'build.ps1', 'capture.ps1',
                'instrument.cmake', 'observer_bridge.hpp', 'vdp2_register_names.inc', 'README.md'}
    records = build.get('sources', [])
    names = [record['path'] for record in records]
    if len(names) != len(set(names)) or set(names) != required:
        raise ValueError('Incomplete v2 capture source identities')
    for record in records:
        if digest(CAPTURE_SOURCE / record['path']) != sha(record['sha256'], 'build source'):
            raise ValueError('Frozen v2 capture source changed')
    instrumentation = build.get('instrumentation', {})
    if instrumentation.get('original_sha256') != ORIGINAL_VDP_SHA256:
        raise ValueError('Unsupported upstream VDP source identity')
    for key in ('original', 'generated'):
        path = Path(instrumentation.get(key + '_path', ''))
        if not path.is_absolute() or digest(path) != sha(instrumentation.get(key + '_sha256'), key):
            raise ValueError('Observed VDP translation unit changed')
    patch = instrumentation.get('patch_text')
    patch_sha = next(record['sha256'] for record in records if record['path'] == 'instrument.cmake')
    if (instrumentation.get('patch') != 'instrument.cmake' or not isinstance(patch, str)
            or hashlib.sha256(patch.encode('utf-8')).hexdigest() != patch_sha):
        raise ValueError('Instrumentation patch text differs from pinned build source')
    if build.get('preserved_v1_unchanged') is not True or not build.get('preserved_v1'):
        raise ValueError('Missing sealed v1 preservation evidence')
    preservation = build['preserved_v1']
    paths = [Path(record['path']) for record in preservation]
    if len(paths) != len(set(paths)) or set(paths) != V1_PATHS:
        raise ValueError('Incomplete sealed v1 preservation identities')
    for record in preservation:
        if digest(Path(record['path'])) != sha(record['sha256'], 'preserved v1'):
            raise ValueError('Sealed v1 evidence changed')


def hex_bytes(value, length: int, name: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{' + str(length * 2) + '}', value):
        raise ValueError('Truncated or invalid ' + name)
    return bytes.fromhex(value)


def validate_vdp(capture, frames, hooks, samples, events, records, read) -> set[str]:
    """Cross-check time, execution, payloads and framebuffer state, fail closed."""
    extra, referenced_blobs = set(), set()
    for key in ('event_count', 'fetched_commands', 'executed_commands', 'blob_count'):
        integer(capture.get(key), key, 0, 1 << 53)
    kinds = {'command_fetch', 'command_execute_before', 'command_execute_after',
             'vdp1_begin', 'vdp1_end', 'vdp1_swap_after_flip', 'public_vdp1_swap_before_flip',
             'public_vdp1_draw_finished', 'public_vdp2_draw_finished', 'software_video_complete',
             'vdp2_render_line', 'vdp1_end_requested', 'sample_boundary', 'command_fetch_repeat'}
    count = len(frames)
    for stream in (frames, hooks, events):
        last = 0
        for row in stream:
            index = integer(row.get('event_index'), 'event index', 1, 1 << 53)
            if index <= last:
                raise ValueError('Evidence stream is not in emission order')
            last = integer(row.get('event_index_last', index), 'event span end', index, 1 << 53)
    merged = sorted([*frames, *hooks, *events], key=lambda row: row.get('event_index', -1))
    previous_tick, previous_frame = samples[0]['scheduler_count'], 0
    serial = 1
    for row in merged:
        tick = integer(row.get('scheduler_count'), 'event scheduler', 0, 1 << 64)
        frame = integer(row.get('frame'), 'event frame', 0, count)
        if frame == 0 and row.get('kind') != 'sample_boundary':
            raise ValueError('Only the initial sample may precede RunFrame')
        if row.get('event_index') != serial or tick < previous_tick or frame < previous_frame:
            raise ValueError('Duplicate, missing or reversed global event order')
        final_tick = tick
        if row.get('kind') == 'command_fetch_repeat':
            repetitions = integer(row.get('repeat_count'), 'repeat count', 1, 1 << 53)
            final_tick = integer(row.get('scheduler_count_last'), 'last repeat scheduler', tick, 1 << 64)
            if row.get('event_index_last') != serial + repetitions - 1:
                raise ValueError('Invalid repeated-fetch event span')
            serial += repetitions
        else:
            serial += 1
        if final_tick > (frames[frame - 1]['scheduler_count'] if frame else samples[0]['scheduler_count']):
            raise ValueError('Event exceeds completed frame time')
        previous_tick, previous_frame = final_tick, frame
        for watch in row.get('watches', []):
            if hashlib.sha256(bytes.fromhex(watch['hex'])).hexdigest() != sha(watch.get('sha256'), 'watch'):
                raise ValueError('Hook/frame watch digest mismatch')
    if serial - 1 != capture.get('event_count'):
        raise ValueError('Missing global event evidence')
    completed, fetched, before, after = {}, 0, 0, 0
    boundaries, invalid_fetches, render_lines = {}, {}, {}
    pending, latest_fetch, swap = None, None, None
    current_bank = integer(samples[0].get('vdp1', {}).get('display_bank'), 'initial display bank', 0, 1)
    public_video_end, draw_end = None, None
    last_event = None

    def blob(identity, size):
        identity = sha(identity, 'VDP payload')
        name = f'blobs/{identity}.bin'
        if records.get(name, {}).get('bytes') != size or records[name]['sha256'] != identity:
            raise ValueError('Missing or truncated command-time payload')
        referenced_blobs.add(name)

    for row in events:
        kind = row.get('kind')
        if row.get('schema') != 'ao_ymir_vdp_event_v2' or kind not in kinds:
            raise ValueError('Unknown VDP event schema/kind')
        frame = row['frame']
        display = integer(row.get('display_bank'), 'display bank', 0, 1)
        if row.get('draw_bank') != display ^ 1:
            raise ValueError('Invalid VDP framebuffer/drawing state')
        if kind == 'vdp1_swap_after_flip':
            if (swap is None or display != current_bank ^ 1
                    or row['event_index'] != swap['event_index'] + 1
                    or row['scheduler_count'] != swap['scheduler_count']):
                raise ValueError('Unpaired framebuffer swap')
            current_bank = display
        elif display != current_bank:
            raise ValueError('Framebuffer bank changed without observed swap')
        if latest_fetch is not None and kind != 'command_execute_before':
            raise ValueError('Executable command fetch lacks immediate execution')
        if pending is not None and kind != 'command_execute_after':
            raise ValueError('Executed command lacks immediate completion')
        if public_video_end is not None and kind != 'software_video_complete':
            raise ValueError('Public video completion lacks immediate software callback')
        if draw_end is not None and kind != 'public_vdp1_draw_finished':
            raise ValueError('VDP1 end lacks public completion callback')
        if kind == 'command_fetch_repeat':
            allowed_repeat = {'schema', 'kind', 'frame', 'scheduler_count', 'scheduler_count_last',
                'event_index', 'event_index_last', 'repeat_count', 'repeats_event_index',
                'command_address', 'command_hex', 'display_bank', 'draw_bank', 'valid_opcode', 'skip', 'end'}
            first = invalid_fetches.get(row.get('repeats_event_index'))
            if (first is None or any(row.get(key) != first.get(key) for key in
                    ('frame', 'command_address', 'command_hex', 'display_bank', 'draw_bank', 'valid_opcode', 'skip', 'end'))
                    or row.get('event_index') != first['event_index'] + 1
                    or last_event is not first):
                raise ValueError('Repeated-fetch span lacks matching adjacent invalid command')
            if set(row) != allowed_repeat or any(row.get(key) is not False for key in ('valid_opcode', 'skip', 'end')):
                raise ValueError('Repeated-fetch record invents unrecorded context')
            fetched += row['repeat_count']
            last_event = row
            continue
        if kind == 'vdp2_render_line':
            line = integer(row.get('line'), 'render line', 0, 1023)
            if row.get('compose_video_serial') != frame or frame != len(completed) + 1:
                raise ValueError('Render line is attributed to the wrong completed video')
            lines = render_lines.setdefault(frame, [])
            if line != len(lines):
                raise ValueError('Missing, duplicate or reordered VDP2 render line')
            lines.append(row)
            last_event = row
            continue
        if type(row.get('drawing')) is not bool:
            raise ValueError('Invalid VDP drawing flag')
        expected_video = len(completed) + (kind == 'software_video_complete')
        if row.get('video_serial') != expected_video:
            raise ValueError('VDP event video serial lies outside active frame')
        for name in ('EDSR', 'COPR', 'LOPR', 'TVMR', 'FBCR', 'PTMR'):
            integer(row.get(name), name, 0, 65535)
        hex_bytes(row.get('vdp2_registers_be_hex'), 512, 'VDP2 address-ordered registers')
        slot = integer(row.get('player_slot'), 'player slot', 0, 31)
        if row.get('player_actor_address') != 0x060c8758 + slot * 112:
            raise ValueError('Player slot/address mismatch')
        hex_bytes(row.get('player_actor_hex'), 112, 'observed player actor')
        blob(row.get('cram_sha256'), 4096)
        if kind.startswith('command_'):
            address = integer(row.get('command_address'), 'VDP1 command address', 0, 0x7ffff)
            if address % 8:
                raise ValueError('Unaligned executed VDP command')
            raw = hex_bytes(row.get('command_hex'), 32, 'VDP1 command')
            words = [int.from_bytes(raw[i:i+2], 'big') for i in range(0, 32, 2)]
            control, pmod = words[0], words[2]
            if (row.get('end') is not bool(control & 0x8000) or
                    row.get('skip') is not bool(control & 0x4000) or
                    row.get('valid_opcode') is not ((control & 15) <= 11)):
                raise ValueError('Decoded command control differs from fetched bytes')
            identity = (frame, address, row['command_hex'], display)
            if kind == 'command_fetch':
                if pending is not None:
                    raise ValueError('Command fetched before previous execute returned')
                fetched += 1
                if not row['end'] and not row['skip'] and row['valid_opcode']:
                    latest_fetch = row
                if not row['valid_opcode'] and not row['skip'] and not row['end']:
                    invalid_fetches[row['event_index']] = row
            elif kind == 'command_execute_before':
                if (pending is not None or latest_fetch is None
                        or identity != (latest_fetch['frame'], latest_fetch['command_address'], latest_fetch['command_hex'], latest_fetch['display_bank'])
                        or row['event_index'] != latest_fetch['event_index'] + 1
                        or row['scheduler_count'] != latest_fetch['scheduler_count']
                        or row['end'] or row['skip'] or not row['valid_opcode']):
                    raise ValueError('Execution lacks matching executable fetched command')
                before += 1; pending = row; latest_fetch = None
                mode = (pmod >> 3) & 7
                if (control & 15) <= 3 and mode <= 5:
                    width, height = ((words[5] >> 8) & 63) * 8, words[5] & 255
                    size = width * height // 2 if mode <= 1 else width * height * (2 if mode == 5 else 1)
                    texture = row.get('texture', {})
                    if any(texture.get(key) != value for key, value in (
                            ('vram_address', words[4] * 8), ('bytes', size), ('width', width),
                            ('height', height), ('color_mode', mode))):
                        raise ValueError('Command-time texture identity differs from command')
                    blob(texture.get('sha256'), size)
                elif 'texture' in row:
                    raise ValueError('Unexpected command-time texture')
                for name, enabled, address, size in (
                        ('lut', (control & 15) <= 3 and mode == 1, words[3] * 8, 32),
                        ('gouraud', bool(pmod & 4), words[14] * 8, 8)):
                    if enabled:
                        value = row.get(name, {})
                        if value.get('vram_address') != address or value.get('bytes') != size:
                            raise ValueError('Missing command-time ' + name)
                        blob(value.get('sha256'), size)
                    elif name in row:
                        raise ValueError('Unexpected command-time ' + name)
            else:
                if (pending is None or identity != (pending['frame'], pending['command_address'], pending['command_hex'], pending['display_bank'])
                        or row['event_index'] != pending['event_index'] + 1
                        or row['scheduler_count'] != pending['scheduler_count']):
                    raise ValueError('Command completion differs from execution entry')
                after += 1; pending = None
            if kind != 'command_execute_before' and any(key in row for key in ('texture', 'lut', 'gouraud')):
                raise ValueError('Payload attributed outside command execution')
        else:
            hashes = row.get('framebuffer_sha256')
            if not isinstance(hashes, list) or len(hashes) != 2:
                raise ValueError('Missing event framebuffer hashes')
            for value in hashes:
                sha(value, 'event framebuffer')
            if kind == 'public_vdp1_swap_before_flip':
                if swap is not None:
                    raise ValueError('Overlapping framebuffer swaps')
                swap = row
            elif kind == 'vdp1_swap_after_flip':
                if swap is None or display != swap['display_bank'] ^ 1 or row['scheduler_count'] != swap['scheduler_count']:
                    raise ValueError('Unpaired framebuffer swap')
                swap = None
            elif kind == 'software_video_complete':
                if frame in completed or row['video_serial'] != frame:
                    raise ValueError('Duplicate or mistimed completed video')
                sha(row.get('video_sha256'), 'completed video')
                if (public_video_end is None or row['event_index'] != public_video_end['event_index'] + 1
                        or row['scheduler_count'] != public_video_end['scheduler_count']
                        or hashes != public_video_end['framebuffer_sha256']):
                    raise ValueError('Software video is not paired with public completion')
                public_video_end = None
                lines = render_lines.get(frame, [])
                if not lines or (frame in samples and len(lines) != samples[frame].get('video_height')):
                    raise ValueError('Missing or incomplete rendered scanlines for video')
                completed[frame] = row
            elif kind == 'public_vdp2_draw_finished':
                public_video_end = row
            elif kind == 'vdp1_end':
                if row['drawing'] or not row['EDSR'] & 2:
                    raise ValueError('VDP1 completed-end state is inconsistent')
                draw_end = row
            elif kind == 'public_vdp1_draw_finished':
                if (draw_end is None or row['event_index'] != draw_end['event_index'] + 1
                        or row['scheduler_count'] != draw_end['scheduler_count'] or row['drawing']):
                    raise ValueError('Public VDP1 completion lacks observed end')
                draw_end = None
            elif kind == 'sample_boundary':
                if frame in boundaries:
                    raise ValueError('Duplicate sample observation')
                boundaries[frame] = row
        last_event = row
    if pending or latest_fetch or swap or public_video_end or draw_end or set(completed) != set(range(1, count + 1)):
        raise ValueError('Unfinished draw/swap or missing completed video')
    if (fetched != capture.get('fetched_commands') or before != after or
            before != capture.get('executed_commands') or len(referenced_blobs) != capture.get('blob_count')):
        raise ValueError('VDP execution/payload counters differ from event evidence')
    extra.update(referenced_blobs)
    if set(boundaries) != set(samples):
        raise ValueError('Sample observation schedule differs from saved samples')
    for index, sample in samples.items():
        vdp1, vdp2 = sample.get('vdp1', {}), sample.get('vdp2', {})
        display = integer(vdp1.get('display_bank'), 'sample display bank', 0, 1)
        if vdp1.get('draw_bank') != display ^ 1 or vdp1.get('renderer_display_bank') != display:
            raise ValueError('Sample framebuffer bank mismatch')
        for name in REGISTERS2:
            integer(vdp2.get(name), 'sample VDP2 ' + name, 0, 65535)
        prefix = f'frame-{index:06d}/'
        boundary = boundaries[index]
        if (any(sample.get(key) != boundary.get(key) for key in ('event_index', 'scheduler_count', 'video_serial')) or
                boundary['display_bank'] != display or boundary['cram_sha256'] != records[prefix + 'cram.bin']['sha256']):
            raise ValueError('Sample metadata differs from its observation event')
        if any(vdp1.get(key) != boundary.get(key) for key in
                ('TVMR', 'FBCR', 'PTMR', 'EDSR', 'COPR', 'LOPR', 'next_command', 'drawing', 'framebuffer_width', 'framebuffer_height')):
            raise ValueError('Sample VDP1 registers differ from boundary observation')
        raw_regs = bytes.fromhex(boundary['vdp2_registers_be_hex'])
        for name, address in VDP2_ADDRESSES.items():
            # SaveState stores internal VCNT, while hardware ReadVCNT returns the external latch.
            value = vdp2.get('VCNTLatch') if name == 'VCNT' else vdp2[name]
            if value != int.from_bytes(raw_regs[address:address + 2], 'big'):
                raise ValueError('Sample VDP2 registers differ from boundary observation: ' + name)
        if vdp2['VCNT'] != boundary.get('VCNT') or vdp2['HCNT'] != boundary.get('HCNT'):
            raise ValueError('Sample scan counters differ from boundary observation')
        for bank in (0, 1):
            if boundary['framebuffer_sha256'][bank] != records[prefix + f'vdp1-fb{bank}.bin']['sha256']:
                raise ValueError('Sample framebuffer differs from observation event')
        if index:
            row = frames[index - 1]
            if sample.get('event_index') != row.get('event_index') + 1 or sample.get('scheduler_count') != row.get('scheduler_count'):
                raise ValueError('Snapshot did not occur at completed frame boundary')
            if completed[index]['video_sha256'] != records[prefix + 'video-rgba.bin']['sha256']:
                raise ValueError('Completed callback video differs from sampled video')
        else:
            if sample.get('event_index') != 1:
                raise ValueError('Initial sample contains later events')
        if index in (0, count):
            raw = read(prefix + 'state.savestate')
            decoded = inspect_snapshot(raw)
            vdp = decoded['vdp_state']
            if (any(vdp1.get(key) != value for key, value in vdp['regs1'].items()) or
                    any(vdp2.get(key) != value for key, value in vdp['regs2'].items()) or
                    vdp['display_framebuffer'] != display or vdp['drawing'] != vdp1.get('drawing') or
                    vdp['next_command_address'] != vdp1.get('next_command')):
                raise ValueError('Sample registers differ from same-boundary saved state')
            offset = decoded['regions']['framebuffers']['offset']
            for bank in (0, 1):
                actual = hashlib.sha256(raw[offset + bank*0x40000:offset + (bank+1)*0x40000]).hexdigest()
                if actual != records[prefix + f'vdp1-fb{bank}.bin']['sha256']:
                    raise ValueError('Framebuffer differs from same-boundary saved state')
    return extra

def inspect(folder: Path) -> dict:
    folder = folder.resolve()
    manifest_raw = stable_read(folder / 'manifest.json')
    manifest = read_json_bytes(manifest_raw)
    if manifest.get('schema') != 'ao_ymir_character_capture_manifest_v2' or manifest.get('inputs_unchanged') is not True:
        raise ValueError('Capture needs a completed source/hash manifest')
    options, normalized_args = arguments(manifest, folder)
    inputs, sequence = pinned_inputs(manifest, options)
    build = manifest.get('build', {})
    if build.get('schema') != 'ao_ymir_character_capture_build_v2' or not re.fullmatch(r'[0-9a-f]{40}', build.get('ymir_revision', '')):
        raise ValueError('Missing pinned Ymir build identity')
    if not re.fullmatch(r'[0-9a-f]{40}', build.get('cereal_revision', '')) or not build.get('configuration'):
        raise ValueError('Missing serializer or build configuration identity')
    executable = Path(build.get('executable', ''))
    if not executable.is_absolute() or digest(executable) != sha(build.get('executable_sha256'), 'harness executable'):
        raise ValueError('Harness executable changed from pinned build')
    validate_build(build)
    records = {}
    for record in manifest.get('outputs', []):
        name = record['path']
        if name == 'manifest.json' or name in records:
            raise ValueError('Duplicate or recursive capture output')
        path = output_path(folder, name)
        integer(record['bytes'], 'output size', 0, 1 << 40)
        if path.stat().st_size != record['bytes'] or digest(path) != sha(record['sha256'], 'output'):
            raise ValueError(f'Captured output changed: {name}')
        records[name] = record
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != records.keys() | {'manifest.json'}:
        raise ValueError('Unlisted or missing capture output')
    if not {'capture.json', 'frames.jsonl', 'hooks.jsonl', 'vdp-events.jsonl'} <= records.keys():
        raise ValueError('Missing mandatory capture/frame/hook evidence')

    def read(name: str) -> bytes:
        if name not in records:
            raise ValueError(f'Missing required captured file: {name}')
        raw = stable_read(output_path(folder, name))
        if hashlib.sha256(raw).hexdigest() != records[name]['sha256']:
            raise ValueError('Capture changed during validation')
        return raw

    capture = read_json_bytes(read('capture.json'))
    count = integer(capture.get('frames'), 'frame count', 1, 1000000)
    integer(capture.get('video_serial'), 'completed video serial', 1, 1000000)
    function_count = integer(capture.get('function_calls'), 'function call count', 0, 1 << 53)
    if (capture.get('schema') != 'ao_ymir_character_capture_v2' or capture.get('status') != 'complete'
            or capture.get('ymir_revision') != build['ymir_revision'] or count != len(sequence) or capture.get('video_serial') != count):
        raise ValueError('RunFrame/video/sequence/build completion mismatch')
    if (capture.get('render_threads') != 0 or capture.get('pending_calls') != 0
            or capture.get('sh2_cache') is not False or capture.get('rtc') != 'virtual_fixed_1994_or_loaded_state'
            or capture.get('hook_boundary') != BOUNDARY):
        raise ValueError('Unfinished hook or unsupported execution boundary/configuration')
    frames = [read_json_bytes(line.encode()) for line in read('frames.jsonl').decode().splitlines()]
    hooks = [read_json_bytes(line.encode()) for line in read('hooks.jsonl').decode().splitlines()]
    if len(frames) != count:
        raise ValueError('Missing per-frame evidence')
    previous_polls = previous_calls = 0
    for index, row in enumerate(frames, 1):
        integer(row.get('frame'), 'frame index', 1, count)
        integer(row.get('video_serial'), 'frame video serial', 1, count)
        polls = integer(row.get('input_polls'), 'input poll count', 0, 1 << 53)
        calls = integer(row.get('function_calls'), 'frame function count', 0, 1 << 53)
        if (row.get('frame') != index or row.get('video_serial') != index or row.get('input') != sequence[index - 1]
                or polls < previous_polls or calls < previous_calls):
            raise ValueError('Nonsequential emulation or input/function counters')
        watches(row, options['--watch-range'])
        previous_polls, previous_calls = polls, calls
    if previous_calls != function_count:
        raise ValueError('Final function counter differs from completed capture')

    samples = {}
    indices = {0, count, *range(options['--sample-every'], count + 1, options['--sample-every'])}
    expected_names = {'capture.json', 'frames.jsonl', 'hooks.jsonl', 'vdp-events.jsonl'}
    previous_scheduler = None
    for index in sorted(indices):
        prefix = f'frame-{index:06d}/'
        sample = read_json_bytes(read(prefix + 'sample.json'))
        for key in ('frame', 'video_serial', 'input_polls', 'function_calls'):
            integer(sample.get(key), f'sample {key}', 0, 1 << 53)
        boundary = 'initial_before_RunFrame' if index == 0 else 'after_RunFrame_return'
        scheduler = integer(sample.get('scheduler_count'), 'scheduler counter', 0, 1 << 64)
        if (sample.get('schema') != 'ao_ymir_frame_sample_v2' or sample.get('frame') != index
                or sample.get('boundary') != boundary or sample.get('video_serial') != index
                or (previous_scheduler is not None and scheduler <= previous_scheduler)):
            raise ValueError('Unsynchronized or nonsequential sample boundary')
        previous_scheduler = scheduler
        expected_names.add(prefix + 'sample.json')
        for filename, size in MEMORY.items():
            name = prefix + filename
            if name not in records or records[name]['bytes'] != size:
                raise ValueError(f'Missing or truncated memory sample: {name}')
            expected_names.add(name)
        memory = {'wram-low.bin': read(prefix + 'wram-low.bin')}
        flags = memory['wram-low.bin'][0x10000:0x20000]
        if hashlib.sha256(flags).hexdigest() != sha(sample.get('flags_sha256'), 'sample flags'):
            raise ValueError('Sample flag table bytes/hash mismatch')
        watches(sample, options['--watch-range'])
        for watch in sample['watches']:
            address = watch['address'] & 0x1fffffff
            filename, base = ('wram-high.bin', 0x06000000) if address >= 0x06000000 else ('wram-low.bin', 0x00200000)
            if filename not in memory:
                memory[filename] = read(prefix + filename)
            actual_watch = memory[filename][address - base:address - base + watch['bytes']].hex()
            if actual_watch != watch['hex']:
                raise ValueError('Sample watch differs from same-boundary WRAM bytes')
            if hashlib.sha256(bytes.fromhex(watch['hex'])).hexdigest() != sha(watch.get('sha256'), 'sample watch'):
                raise ValueError('Sample watch digest differs from its bytes')
        if 'wram-high.bin' not in memory:
            memory['wram-high.bin'] = read(prefix + 'wram-high.bin')
        high = memory['wram-high.bin']
        slot = high[0xc27ae]
        address = 0x060c8758 + slot * 112
        if (slot >= 32 or sample.get('player_slot') != slot or sample.get('player_actor_address') != address
                or sample.get('player_actor_hex') != high[address - 0x06000000:address - 0x06000000 + 112].hex()):
            raise ValueError('Sample selected actor differs from same-boundary WRAM')
        if index == 0:
            if sample.get('input_polls') != 0 or sample.get('function_calls') != 0 or sample.get('input') != 'none':
                raise ValueError('Initial sample contains later-frame counters')
        else:
            row = frames[index - 1]
            if any(sample.get(key) != row.get(key) for key in ('input', 'input_polls', 'function_calls', 'watches')):
                raise ValueError('Sample differs from its completed-frame evidence')
            width = integer(sample.get('video_width'), 'video width', 1, 2048)
            height = integer(sample.get('video_height'), 'video height', 1, 2048)
            if records.get(prefix + 'video-rgba.bin', {}).get('bytes') != width * height * 4:
                raise ValueError('Missing or truncated completed video frame')
            ppm = read(prefix + 'video.ppm'); header = f'P6\n{width} {height}\n255\n'.encode()
            if not ppm.startswith(header) or len(ppm) != len(header) + width * height * 3:
                raise ValueError('Invalid completed PPM frame')
            rgba = read(prefix + 'video-rgba.bin')
            if Image.frombytes('RGBA', (width, height), rgba).convert('RGB').tobytes() != ppm[len(header):]:
                raise ValueError('PPM and RGBA pixels differ at the same video boundary')
            expected_names.update({prefix + 'video-rgba.bin', prefix + 'video.ppm'})
        if index in (0, count):
            name = prefix + 'state.savestate'
            decoded = inspect_snapshot(read(name))
            for region, filename in (('wram_low', 'wram-low.bin'), ('wram_high', 'wram-high.bin'),
                                     ('vram1', 'vram1.bin'), ('vram2', 'vram2.bin'), ('cram', 'cram.bin')):
                if decoded['regions'][region]['sha256'] != records[prefix + filename]['sha256']:
                    raise ValueError('Saved state and same-boundary memory dump differ')
            expected_names.add(name)
        samples[index] = sample
    vdp_events = [read_json_bytes(line.encode()) for line in read('vdp-events.jsonl').decode().splitlines()]
    expected_names.update(validate_vdp(capture, frames, hooks, samples, vdp_events, records, read))
    if set(records) != expected_names:
        raise ValueError('Capture file set does not match declared sampling schedule')

    pending, calls_by_frame = [], Counter()
    seen_calls = last_frame = last_polls = 0
    for serial, row in enumerate(hooks, 1):
        frame = integer(row.get('frame'), 'hook frame', 1, count)
        polls = integer(row.get('input_polls'), 'hook poll count', 0, 1 << 53)
        call_id = integer(row.get('function_call_index'), 'hook call id', 0, 1 << 53)
        integer(row.get('actor_address'), 'actor address')
        pc = integer(row.get('pc'), 'hook PC'); integer(row.get('pr'), 'hook PR')
        if (row.get('hook_index') != serial or frame < last_frame or polls < last_polls
                or polls > frames[frame - 1]['input_polls'] or (frame > 1 and polls < frames[frame - 2]['input_polls'])
                or row.get('input') != sequence[frame - 1]):
            raise ValueError('Nonsequential hook/frame/input evidence')
        last_frame, last_polls = frame, polls
        if not isinstance(row.get('r'), list) or len(row['r']) != 16:
            raise ValueError('Missing hook registers')
        for value in row['r']:
            integer(value, 'SH-2 register')
        actor = row.get('actor_hex')
        if actor is not None and (not isinstance(actor, str) or not re.fullmatch(r'[0-9a-f]{224}', actor)):
            raise ValueError('Truncated actor prefix')
        sha(row.get('flags_sha256'), 'hook flags'); watches(row, options['--watch-range'])
        kind = row.get('kind')
        if kind == 'entry':
            seen_calls += 1
            if not options['--trace-function'] or pc != options['--trace-function'] or call_id != seen_calls or row['r'][4] != row['actor_address']:
                raise ValueError('Invalid or reused function entry identity')
            pending.append(row); calls_by_frame[frame] += 1
        elif kind == 'return':
            if not pending:
                raise ValueError('Return without captured entry')
            entry = pending.pop()
            if call_id != entry['function_call_index'] or row['actor_address'] != entry['actor_address'] or pc != entry['pr']:
                raise ValueError('Return does not match entry actor, PR or nested call order')
        elif kind == 'pc':
            if pc not in options['--hook-pc'] or call_id != (pending[-1]['function_call_index'] if pending else 0):
                raise ValueError('Unconfigured or misattributed PC hook')
        else:
            raise ValueError('Unknown hook kind')
    if pending or seen_calls != function_count:
        raise ValueError('Unpaired hooks or invented completed function count')
    cumulative = 0
    for index, row in enumerate(frames, 1):
        cumulative += calls_by_frame[index]
        if row['function_calls'] != cumulative:
            raise ValueError('Frame function counter differs from hook entries')
    if stable_read(folder / 'manifest.json') != manifest_raw:
        raise ValueError('Manifest changed during validation')
    return {'folder': str(folder), 'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
            'inputs': inputs, 'build': build, 'capture': capture, 'arguments': normalized_args,
            'outputs': {name: record['sha256'] for name, record in records.items()},
            'frames': frames, 'hooks': hooks, 'samples': samples, 'vdp_events': vdp_events, 'timing_evidence_passed': True}


def verify(folders: list[Path]) -> dict:
    if len(folders) < 3 or len({path.resolve() for path in folders}) != len(folders):
        raise ValueError('At least three distinct v2 replays are required')
    # Full per-command evidence can exceed hundreds of MiB for each route.
    # inspect still performs every check, but replay comparison retains only identities.
    runs = []
    for folder in folders:
        evidence = inspect(folder)
        runs.append({key: evidence[key] for key in
                     ('folder', 'manifest_sha256', 'inputs', 'build', 'arguments', 'outputs', 'capture')})
        del evidence
    baseline, differences = runs[0], []
    for run in runs[1:]:
        if any(run[key] != baseline[key] for key in ('inputs', 'build', 'arguments')):
            raise ValueError('Replay source, sequence, arguments or build differs')
        keys = set(baseline['outputs']) | set(run['outputs'])
        differences.extend({'run': run['folder'], 'file': key} for key in sorted(keys)
                           if run['outputs'].get(key) != baseline['outputs'].get(key))
    return {'schema': 'ao_pc_character_capture_replay_v2', 'passed': not differences,
            'timing_evidence_passed': True, 'animation_model_evidence_passed': False,
            'replays': len(runs), 'frames_per_replay': baseline['capture']['frames'],
            'function_calls_per_replay': baseline['capture']['function_calls'],
            'executed_commands_per_replay': baseline['capture']['executed_commands'],
            'captures': [{'folder': r['folder'], 'manifest_sha256': r['manifest_sha256']} for r in runs],
            'differing_outputs': differences,
            'scope': 'Identical sources and synchronized CPU/VDP evidence; model and pixel parity are separate gates'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path, nargs='+')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.captures)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'Character capture rejected: {exc}\n')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
