"""Roll the bounded MAP001 player model forward from one captured initial state.

Only input words are consumed from later hooks; observed actor fields are
comparison targets, never injected into the prediction. Raw source artifacts
remain local. This does not certify unvisited map cells or other actor modes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from exploration_capture import stable_read
import exploration_movement as m
from verify_exploration_replay import inspect


def _watch(row: dict, address: int, size: int) -> bytes:
    matches = [w for w in row['watches'] if w['address'] == address and w['bytes'] == size]
    if len(matches) != 1:
        raise ValueError(f'Missing or duplicate synchronous watch at {address:#x}')
    return bytes.fromhex(matches[0]['hex'])


def _differences(expected: dict, observed: dict) -> dict:
    return {k: {'predicted': expected[k], 'observed': observed[k]}
            for k in m.FIELDS if expected[k] != observed[k]}


def validate(folder: Path) -> tuple[dict, dict]:
    evidence = inspect(folder)
    folder = Path(evidence['folder'])
    if dict(evidence['arguments'])['--trace-function'] != 0x060ab61a:
        raise ValueError('Capture does not bind collision entry to its actual caller return')

    def read_output(name: str) -> bytes:
        raw = stable_read(folder / name)
        if hashlib.sha256(raw).hexdigest() != evidence['outputs'][name]:
            raise ValueError(f'Capture changed after integrity verification: {name}')
        return raw

    initial = m.profile_from_snapshot(read_output('frame-000000/wram-high.bin'),
                                      read_output('frame-000000/wram-low.bin'))
    snapshots = {}
    for frame in evidence['samples']:
        profile = m.profile_from_snapshot(read_output(f'frame-{frame:06d}/wram-high.bin'),
                                          read_output(f'frame-{frame:06d}/wram-low.bin'))
        if profile.flags != initial.flags:
            raise ValueError('Scene flags changed within capture')
        snapshots[frame] = profile.initial_state
    frames = defaultdict(list)
    for row in evidence['hooks']:
        if row['flags_sha256'] != m.FLAGS_SHA256:
            raise ValueError('A hook uses a different scene flag table')
        control = _watch(row, 0x060c27aa, 8)
        if int.from_bytes(control[:2], 'big') != 3 or control[4] != 0 or _watch(row, 0x060c41ec, 1) != b'\0':
            raise ValueError('Controller gate or selected actor changed within capture')
        frames[row['frame']].append(row)
    count = evidence['capture']['frames']
    if sorted(frames) != list(range(1, count + 1)):
        raise ValueError('Expected exactly one observed player update per captured frame')

    state = dict(initial.initial_state)
    failures, records, queried = [], [], set()
    contacts, directions = Counter(), Counter()
    coverage = {direction: Counter() for direction in m.PAD_WORDS}
    crossing_count = queued_count = consumed_count = neutral_slide_count = 0
    xs, ys = [state['x_word']], [state['y_word']]
    inverse_pad = {v: k for k, v in m.PAD_WORDS.items()}
    previous_pad = 0
    release_count = turn_count = 0
    for frame in range(1, count + 1):
        rows = frames[frame]
        gates = [r for r in rows if r['pc'] == 0x06094afc and r['kind'] == 'pc']
        if len(gates) != 1:
            raise ValueError('Missing or duplicate original input-gate call')
        pad = int.from_bytes(_watch(gates[0], 0x06036642, 2), 'big')
        if pad not in inverse_pad:
            raise ValueError('Capture includes unsupported non-cardinal input')
        expected_pcs = [0x06094afc, 0x060aa0de, 0x060aae20]
        if pad:
            expected_pcs.append(0x060abfc8)
        expected_pcs += [0x060ac20c, 0x060ab61a, 0x060aaeb0]
        if [r['pc'] for r in rows] != expected_pcs or rows[-2]['kind'] != 'entry' or rows[-1]['kind'] != 'return':
            raise ValueError(f'Unsupported actor call order or update count at frame {frame}')
        for row in rows[2:]:
            actor = bytes.fromhex(row['actor_hex'])
            if (row['actor_address'] != initial.actor_address or len(actor) != 112 or
                    int.from_bytes(actor[0x60:0x64], 'big') != 0x20220010 or
                    actor[0x2a:0x2c] != b'\0\0' or int.from_bytes(actor[0xc:0xe], 'big') & 0x8000):
                raise ValueError('Observed actor identity, dispatch or animation root changed')

        # The next dispatch also checks the effect of the previous caller tail:
        # a position/status adjustment after collision cannot hide in the gap.
        gated, _ = m.p.replay_input_gate(m.actor_from_state(state), pad, 3, 0)
        gate_delta = _differences(m.state_from_actor(gated), m.state_from_actor(bytes.fromhex(rows[2]['actor_hex'])))
        before = dict(state)
        state, diagnostics = m.step_game_input(state, pad, initial)
        actual = m.state_from_actor(bytes.fromhex(rows[-1]['actor_hex']))
        delta = _differences(state, actual)
        expected_oldxy = before['x_word'].to_bytes(2, 'big') + before['y_word'].to_bytes(2, 'big')
        oldxy_matches = _watch(rows[-1], 0x060dddc4, 4) == expected_oldxy
        snapshot_delta = _differences(state, snapshots[frame]) if frame in snapshots else {}
        if delta or gate_delta or not oldxy_matches or snapshot_delta:
            failures.append({'frame': frame, 'collision_return': delta, 'next_dispatch': gate_delta,
                             'snapshot': snapshot_delta, 'old_xy_global_matches': oldxy_matches})
        queried.update(item['index'] for item in diagnostics['lookups'])
        direction = inverse_pad[pad]
        directions[direction] += 1
        contacts[str(actual['contact_bits'])] += 1
        moved = (state['x_word'], state['y_word']) != (before['x_word'], before['y_word'])
        coverage[direction]['updates'] += 1
        coverage[direction]['contact_updates' if actual['contact_bits'] else 'free_updates'] += 1
        coverage[direction]['moved_updates' if moved else 'stationary_updates'] += 1
        crossing_count += (before['x_word']//128, before['y_word']//128) != (state['x_word']//128, state['y_word']//128)
        queued = bool(state['slide_x_word'] or state['slide_y_word'])
        consumed = bool(before['slide_x_word'] or before['slide_y_word'])
        queued_count += queued
        consumed_count += consumed
        neutral_slide_count += consumed and not pad and moved
        release_count += bool(previous_pad and not pad)
        turn_count += bool(previous_pad and pad and previous_pad != pad)
        previous_pad = pad
        xs.append(state['x_word']); ys.append(state['y_word'])
        records.append({'frame': frame, 'game_pad_word': pad, 'expected': actual,
                        'query_indices': sorted({item['index'] for item in diagnostics['lookups']})})

    profile = initial.metadata()
    profile['verified_query_indices'] = sorted(queried) if not failures else None
    report = {'schema': 'ao_pc_player_trace_comparison_v1', 'capture': str(folder),
        'manifest_sha256': evidence['manifest_sha256'], 'timing_evidence_passed': True,
        'controlled_actor_identity_verified': True, 'updates_compared': count,
        'mismatched_updates': len(failures), 'passed': not failures,
        'prediction': 'initial state plus original game input words only; no later actor-state injection',
        'comparison_fields': profile['comparison_fields'], 'profile': profile,
        'coverage': {'direction_updates': dict(directions), 'contacts': dict(contacts),
            'directions': {k: dict(v) for k, v in coverage.items()},
            'cell_crossing_updates': crossing_count, 'queued_slide_updates': queued_count,
            'consumed_slide_updates': consumed_count, 'neutral_slide_updates': neutral_slide_count,
            'release_transitions': release_count, 'direct_turn_transitions': turn_count,
            'raw_xy_bounds': [min(xs), max(xs), min(ys), max(ys)],
            'verified_query_count': len(queried)},
        'limits': ['Only listed state fields and old-xy globals are modeled; animation drawing/counters are excluded.',
                   'Animation motion is absent only in the pinned source root; other roots are rejected.',
                   'Evidence covers sampled cell queries, not a rectangular whole room or all combinations.',
                   'No NPC collision, triggers, scrolling or input modes beyond the recorded controlled slot are certified.'],
        'failures': failures}
    fixture = {'capture': str(folder), 'manifest_sha256': evidence['manifest_sha256'],
               'initial_state': initial.initial_state, 'updates': records}
    return report, fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--profile', type=Path)
    args = parser.parse_args()
    try:
        pairs = [validate(folder) for folder in args.captures]
        reports, fixtures = zip(*pairs)
        passed = all(report['passed'] for report in reports)
        profile = dict(reports[0]['profile'])
        comparable = {k: v for k, v in profile.items() if k != 'verified_query_indices'}
        if any({k: v for k, v in report['profile'].items() if k != 'verified_query_indices'} != comparable for report in reports):
            raise ValueError('Cannot merge different initial scene/actor profiles')
        profile['verified_query_indices'] = sorted(set().union(*(report['profile']['verified_query_indices'] or [] for report in reports))) if passed else None
        output = {'schema': 'ao_pc_player_trace_suite_v1', 'passed': passed,
                  'updates_compared': sum(r['updates_compared'] for r in reports),
                  'mismatched_updates': sum(r['mismatched_updates'] for r in reports), 'captures': reports}
        for path, value in [(args.out, output), (args.fixtures, {'schema':m.SCHEMA, 'passed':passed, 'profile':profile, 'traces':fixtures}), (args.profile, profile)]:
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'Player trace evidence rejected: {exc}\n')
    print(json.dumps({k:output[k] for k in ('passed','updates_compared','mismatched_updates')}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
