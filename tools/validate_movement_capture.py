"""Compare original SH-2 entry/return observations with the bounded Python model."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from probe_movement import load_shapes, replay_step, WORKSPACE
from exploration_capture import stable_read
from verify_exploration_replay import inspect


def validate(folder: Path, actor_address: int | None = None) -> dict:
    evidence = inspect(folder)
    folder = Path(evidence['folder'])
    options = dict(evidence['arguments'])
    if options['--trace-function'] != 0x060ab61a:
        raise ValueError('Capture does not trace the source-bound collision routine')
    shapes = load_shapes((WORKSPACE / 'work/extract/TWN.BIN').read_bytes(),
                         (WORKSPACE / 'work/extract/0').read_bytes())
    # A capture may contain multiple table versions. Every call must bind to
    # bytes actually archived with its hash; never assume frame-zero persists.
    tables = {}
    for frame, sample in evidence['samples'].items():
        name = f'frame-{frame:06d}/wram-low.bin'
        low = stable_read(folder / name)
        if hashlib.sha256(low).hexdigest() != evidence['outputs'][name]:
            raise ValueError('Captured flag source changed after integrity validation')
        flags = low[0x10000:0x20000]
        if hashlib.sha256(flags).hexdigest() != sample['flags_sha256']:
            raise ValueError('Captured flag table identity mismatch')
        tables[sample['flags_sha256']] = flags
    pending, actors, failures = {}, {}, []
    compared = 0
    inputs = Counter()
    used_tables = Counter()
    for row in evidence['hooks']:
        if row['kind'] not in ('entry', 'return'):
            continue
        address = row['actor_address']
        address = int(address, 0) if isinstance(address, str) else address
        if actor_address is not None and address != actor_address:
            continue
        identity = row['function_call_index']
        if row['kind'] == 'entry':
            if identity in pending:
                raise ValueError('Duplicate function entry')
            pending[identity] = row
            continue
        if identity not in pending:
            raise ValueError('Return without captured entry')
        before = pending.pop(identity)
        flag_hash = before['flags_sha256']
        if row['flags_sha256'] != flag_hash:
            raise ValueError('Flag table changed during the observed function call')
        if flag_hash not in tables:
            raise ValueError('Hook flag table has no matching archived bytes; capture more often')
        if before['actor_hex'] is None or row['actor_hex'] is None:
            raise ValueError('Movement call lacks an observed actor prefix')
        raw = bytes.fromhex(before['actor_hex'])
        actual = bytes.fromhex(row['actor_hex'])
        predicted, diagnostics = replay_step(raw, tables[flag_hash], shapes)
        differences = [{'offset': i, 'expected': a, 'observed': b}
                       for i, (a, b) in enumerate(zip(predicted, actual)) if a != b]
        if len(predicted) != len(actual):
            raise ValueError('Actor prefix length changed')
        if differences:
            failures.append({'call': identity, 'frame': row['frame'], 'actor': address,
                             'input': before['input'], 'differences': differences,
                             'diagnostics': diagnostics})
        compared += 1
        used_tables[flag_hash] += 1
        inputs[str(before['input'])] += 1
        summary = actors.setdefault(str(address), {'calls': 0, 'moved_calls': 0,
            'shape_indices': set(), 'delta_words': set(), 'positions': set(), 'contact_bits': Counter()})
        summary['calls'] += 1
        summary['moved_calls'] += raw[:4] != actual[:4]
        summary['shape_indices'].add(raw[0x29])
        summary['delta_words'].add(struct.unpack_from('>hh', raw, 0x18))
        summary['positions'].add(struct.unpack_from('>HH', actual))
        summary['contact_bits'][str(actual[0x4b])] += 1
    if pending:
        raise ValueError('Capture ended inside an unfinished movement call')
    if not compared:
        raise ValueError('No original movement calls captured')
    for value in actors.values():
        for key in ('shape_indices', 'delta_words', 'positions'):
            value[key] = sorted(value[key])
        value['contact_bits'] = dict(value['contact_bits'])
    return {'schema': 'ao_pc_movement_capture_comparison_v1',
            'scope': 'Observed actor prefix at SH-2 collision entry/return with hook-bound flags; not whole player control or global side effects',
            'capture': str(folder), 'manifest_sha256': evidence['manifest_sha256'],
            'flags_sha256': next(iter(used_tables)) if len(used_tables) == 1 else None,
            'flag_table_calls': dict(used_tables), 'timing_evidence_passed': True,
            'movement_model_evidence_passed': not failures, 'player_identity_verified': False,
            'calls_compared': compared, 'mismatched_calls': len(failures),
            'passed': not failures, 'inputs': dict(inputs), 'actors': actors, 'failures': failures}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--actor', type=lambda s: int(s, 0))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(args.capture, args.actor)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'Movement evidence rejected: {exc}\n')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('calls_compared', 'mismatched_calls', 'passed', 'inputs')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
