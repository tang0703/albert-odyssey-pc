"""Integrity/timing gate and three-run comparison; not movement-model validation."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import stat

from PIL import Image

from exploration_capture import cue_tracks, inspect_snapshot, read_json_bytes, stable_fingerprint, stable_read

HASH = re.compile(r'[0-9a-f]{64}\Z')
BUTTONS = {'none', 'up', 'down', 'left', 'right', 'start', 'a', 'b', 'c'}
MEMORY = {'wram-low.bin': 0x100000, 'wram-high.bin': 0x100000,
          'vram1.bin': 0x80000, 'vram2.bin': 0x80000, 'cram.bin': 0x1000}
BOUNDARY = 'before_instruction; return uses entry PR after delay slot'


def digest(path: Path) -> str:
    return stable_fingerprint(path)['sha256']


def integer(value, name: str, minimum=0, maximum=0xffffffff) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'Invalid {name}')
    return value


def sha(value, name: str) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError(f'Missing or invalid {name} SHA256')
    return value


def output_path(folder: Path, name: str) -> Path:
    if not isinstance(name, str) or '\\' in name or ':' in name or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Invalid capture output path')
    path = folder
    for part in name.split('/'):
        path = path / part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Capture outputs cannot use links or junctions')
    if not path.is_file():
        raise ValueError('Capture output must be a regular file')
    return path


def arguments(manifest: dict, folder: Path) -> tuple[dict, list]:
    argv, cwd = manifest.get('arguments'), Path(manifest.get('working_directory', ''))
    if not cwd.is_absolute() or not isinstance(argv, list) or len(argv) % 2:
        raise ValueError('Capture arguments and absolute working_directory are required')
    allowed = {'--ipl', '--disc', '--sequence', '--output', '--sample-every', '--load-state',
               '--trace-function', '--hook-pc', '--watch-range'}
    options = {}
    for key, value in zip(argv[::2], argv[1::2]):
        if key not in allowed or not isinstance(value, str) or (key in options and key not in {'--hook-pc', '--watch-range'}):
            raise ValueError('Unknown, duplicate or malformed capture argument')
        options.setdefault(key, []).append(value)
    if not {'--ipl', '--disc', '--sequence', '--output', '--sample-every'} <= options.keys():
        raise ValueError('Missing capture source or sampling argument')
    for key in ('--ipl', '--disc', '--sequence', '--output', '--load-state'):
        if key in options:
            path = Path(options[key][0])
            options[key] = (path if path.is_absolute() else cwd / path).resolve()
    if options['--output'] != folder:
        raise ValueError('Capture output argument does not identify this directory')
    options['--sample-every'] = integer(int(options['--sample-every'][0], 0), 'sample interval', 1, 1000000)
    options['--trace-function'] = integer(int(options.get('--trace-function', ['0'])[0], 0), 'trace function')
    options['--hook-pc'] = {integer(int(v, 0), 'hook PC') for v in options.get('--hook-pc', [])}
    watches = []
    for value in options.get('--watch-range', []):
        address, length = (int(v, 0) for v in value.split(':'))
        integer(address, 'watch address'); integer(length, 'watch length', 1, 0x10000)
        physical = address & 0x1fffffff
        if not (0x06000000 <= physical < physical + length <= 0x06100000 or 0x00200000 <= physical < physical + length <= 0x00300000):
            raise ValueError('Watch range is outside captured WRAM')
        watches.append((address, length))
    options['--watch-range'] = watches
    normalized = [(key, str(value) if isinstance(value, Path) else sorted(value) if isinstance(value, set) else value)
                  for key, value in sorted(options.items()) if key != '--output']
    return options, normalized


def pinned_inputs(manifest: dict, options: dict) -> tuple[list, list[str]]:
    records = manifest.get('inputs')
    if not isinstance(records, list) or not records:
        raise ValueError('Missing pinned capture sources')
    expected = {str(options[key]) for key in ('--ipl', '--disc', '--sequence', '--load-state') if key in options}
    cue = options['--disc']
    if cue.suffix.lower() != '.cue':
        raise ValueError('Formal verification requires a source-bound CUE/BIN disc')
    expected.update(str(path) for _, path in cue_tracks(cue, stable_read(cue)))
    observed, identities = set(), []
    for record in records:
        path = Path(record['path'])
        if not path.is_absolute() or str(path.resolve()) != record['path'] or record['path'] in observed:
            raise ValueError('Invalid or duplicate pinned source path')
        observed.add(record['path'])
        integer(record['bytes'], 'source size', 1, 1 << 40); sha(record['sha256'], 'source')
        now = stable_fingerprint(path)
        if (now['size'], now['sha256']) != (record['bytes'], record['sha256']):
            raise ValueError(f'Pinned source changed: {path}')
        identities.append((record['path'], record['bytes'], record['sha256']))
    if observed != expected:
        raise ValueError('Missing or unlisted BIOS, disc track, sequence or initial state pin')
    if options['--ipl'].stat().st_size != 0x80000:
        raise ValueError('Pinned BIOS must be exactly 512 KiB')
    sequence = []
    for line in stable_read(options['--sequence']).decode('utf-8-sig').splitlines():
        words = line.split('#', 1)[0].split()
        if not words:
            continue
        if len(words) != 2 or words[0] not in BUTTONS:
            raise ValueError('Malformed pinned input sequence')
        count = integer(int(words[1], 0), 'sequence count', 1, 1000000)
        if len(sequence) + count > 1000000:
            raise ValueError('Input sequence exceeds supported frame count')
        sequence.extend([words[0]] * count)
    if not sequence:
        raise ValueError('Empty pinned sequence')
    return sorted(identities), sequence


def watches(row: dict, expected: list[tuple]) -> None:
    records = row.get('watches')
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError('Missing configured watch evidence')
    for record, (address, length) in zip(records, expected):
        if record.get('address') != address or record.get('bytes') != length:
            raise ValueError('Watch identity differs from capture arguments')
        if not isinstance(record.get('hex'), str) or not re.fullmatch(r'[0-9a-f]{' + str(length * 2) + '}', record['hex']):
            raise ValueError('Truncated or invalid watch bytes')


def inspect(folder: Path) -> dict:
    folder = folder.resolve()
    manifest_raw = stable_read(folder / 'manifest.json')
    manifest = read_json_bytes(manifest_raw)
    if manifest.get('schema') != 'ao_ymir_capture_manifest_v1' or manifest.get('inputs_unchanged') is not True:
        raise ValueError('Capture needs a completed source/hash manifest')
    options, normalized_args = arguments(manifest, folder)
    inputs, sequence = pinned_inputs(manifest, options)
    build = manifest.get('build', {})
    if build.get('schema') != 'ao_ymir_capture_build_v1' or not re.fullmatch(r'[0-9a-f]{40}', build.get('ymir_revision', '')):
        raise ValueError('Missing pinned Ymir build identity')
    if not re.fullmatch(r'[0-9a-f]{40}', build.get('cereal_revision', '')) or not build.get('configuration'):
        raise ValueError('Missing serializer or build configuration identity')
    executable = Path(build.get('executable', ''))
    if not executable.is_absolute() or digest(executable) != sha(build.get('executable_sha256'), 'harness executable'):
        raise ValueError('Harness executable changed from pinned build')
    source_names = set()
    for source in build.get('sources', []):
        if source['path'] in source_names:
            raise ValueError('Duplicate build source identity')
        source_names.add(source['path']); sha(source['sha256'], 'build source')
    if source_names != {'main.cpp', 'CMakeLists.txt', 'build.ps1'}:
        raise ValueError('Incomplete harness build source identities')
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
    if not {'capture.json', 'frames.jsonl', 'hooks.jsonl'} <= records.keys():
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
    if (capture.get('schema') != 'ao_ymir_capture_v1' or capture.get('status') != 'complete'
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
    expected_names = {'capture.json', 'frames.jsonl', 'hooks.jsonl'}
    previous_scheduler = None
    for index in sorted(indices):
        prefix = f'frame-{index:06d}/'
        sample = read_json_bytes(read(prefix + 'sample.json'))
        for key in ('frame', 'video_serial', 'input_polls', 'function_calls'):
            integer(sample.get(key), f'sample {key}', 0, 1 << 53)
        boundary = 'initial_before_RunFrame' if index == 0 else 'after_RunFrame_return'
        scheduler = integer(sample.get('scheduler_count'), 'scheduler counter', 0, 1 << 64)
        if (sample.get('schema') != 'ao_ymir_frame_sample_v1' or sample.get('frame') != index
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
            'frames': frames, 'hooks': hooks, 'samples': samples, 'timing_evidence_passed': True}


def verify(folders: list[Path]) -> dict:
    if len(folders) < 3 or len({p.resolve() for p in folders}) != len(folders):
        raise ValueError('At least three distinct replays are required')
    runs = [inspect(folder) for folder in folders]
    baseline, differences = runs[0], []
    for run in runs[1:]:
        if any(run[key] != baseline[key] for key in ('inputs', 'build', 'arguments')):
            raise ValueError('Replay source, sequence, execution arguments or build differs')
        keys = set(baseline['outputs']) | set(run['outputs'])
        differences.extend({'run': run['folder'], 'file': key} for key in sorted(keys)
                           if run['outputs'].get(key) != baseline['outputs'].get(key))
    return {'schema': 'ao_pc_exploration_replay_v1', 'passed': not differences,
            'timing_evidence_passed': True, 'movement_model_evidence_passed': False,
            'replays': len(runs), 'frames_per_replay': baseline['capture']['frames'],
            'function_calls_per_replay': baseline['capture']['function_calls'],
            'captures': [{'folder': r['folder'], 'manifest_sha256': r['manifest_sha256']} for r in runs],
            'differing_outputs': differences,
            'scope': 'Integrity/timing and identical replay outputs; not proof of player identity, collision model or coverage'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path, nargs='+'); parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.captures)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'Replay rejected: {exc}\n')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
