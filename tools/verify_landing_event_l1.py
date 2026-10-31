"""L1 capture gate. Repeated source evidence cannot approve a PC runtime."""
import argparse
import json
from pathlib import Path
from inspect_event_capture import inspect, watched
from landing_event_source import programs, text_records, ROOT, sha
from verify_landing_event_sequence import validate
from verify_transition_capture import verify_files
from verify_event_text_input import verify as verify_text_input

SEED_SHA = '72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54'
HISTORIES = ('equip', 'remove', 'reequip')


def waiting_page(raw, pages):
    if len(raw) != 64: raise ValueError('Incomplete source text device')
    if int.from_bytes(raw[:2], 'big') != 17 or raw[25] not in (8, 9): return None
    pointer = int.from_bytes(raw[28:32], 'big')-0x260e0000+8
    matches = [p for p in pages if pointer == p['offset']+p['span']+1]
    if len(matches) > 1: raise ValueError('Ambiguous source page delimiter')
    return matches[0] if matches else None


def review(folder):
    proof = validate(folder)
    if not proof['passed'] or proof['event_runs'] != 1 or not proof['event_completed'] or proof['ambient_loops'] < 1:
        raise ValueError('Continuous landing-event prediction failed or endpoint not demonstrated')
    inventory = inspect(folder)
    program = {row['offset']: row for rows in programs().values() for row in rows}
    calls = [row for row in inventory['calls'] if int(row['offset'], 16) in program]
    observed = {int(row['offset'], 16) for row in calls}
    if observed != set(program):
        raise ValueError('Not all necessary event/ambient instructions observed')
    for row in calls:
        op = program[int(row['offset'], 16)]
        if int(row['opcode'], 16) != op['opcode'] or int(row['handler'], 16) != op['handler']:
            raise ValueError('Source dispatch differs from bounded programs')
    records = text_records()
    pages = [page for record in records.values() for page in record['pages']]
    begin = calls[0]['frame']
    seen = []
    states = []
    previous = None
    for line in (folder/'frames.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        if row['frame'] < begin: continue
        text_raw = watched(row, 0x060c51d4, 64)
        # At F6/FA wait the parser has consumed the delimiter. A cursor
        # inside the next span alone does NOT prove display.
        page = waiting_page(text_raw, pages)
        if page is not None and (not seen or seen[-1]['id'] != page['id']):
            seen.append({'id': page['id'], 'first_wait_frame': row['frame'], 'source_wait_phase': text_raw[25]})
        state = (watched(row, 0x060c41ec, 1).hex(), watched(row, 0x06036938, 1).hex())
        if state != previous:
            states.append({'frame': row['frame'], 'disabled': state[0], 'story': state[1]})
            previous = state
    if [p['id'] for p in seen] != [p['id'] for p in pages]:
        raise ValueError('Source did not display all eight pages in order')
    if states[-1]['disabled'] != '00' or states[-1]['story'] != '0f':
        raise ValueError('Source control/story endpoint differs')
    confirmation = verify_text_input(folder)
    accepted = [r for r in confirmation['accepted_confirmations'] if r['frame'] >= begin]
    if not confirmation['passed'] or len(accepted) != 8:
        raise ValueError('Source page/end confirmation gates differ')
    # Full comparison also covers each actor byte, both cameras, all eight
    # objects, equipment persistence, command sequence and active/wait/cursor.
    summary = {k: proof[k] for k in ('checks', 'prefix_updates', 'transfer_and_landing_updates',
                                    'landing_updates', 'event_runs', 'event_completed', 'ambient_loops', 'query_indices')}
    summary.update(instructions_observed=len(observed), source_pages=seen,
                   control_story_transitions=states, accepted_confirmations=accepted,
                   confirmation_checks=confirmation['checks'], performance_tested=False,
                   godot_passed=False, graphics_passed=False)
    return summary


def run():
    base = ROOT/'reports/landing-event'
    replays = []
    for history in HISTORIES:
        baseline = None
        for repeat in range(1, 4):
            folder = base/f'l1-{history}-{repeat}'
            manifest, files, digest = verify_files(folder)
            if not any(Path(row['path']).suffix == '.savestate' and row['sha256'] == SEED_SHA for row in manifest['inputs']):
                raise ValueError('Formal source replay lost named original-room seed')
            if baseline is None:
                baseline = files
                summary = review(folder)
            elif files != baseline:
                raise ValueError(f'Non-identical source repeat: {history}/{repeat}')
            replays.append({'history': history, 'repeat': repeat, 'manifest_sha256': digest,
                            'all_capture_payloads_identical': True, 'review': summary if repeat == 1 else None})
            print(f'Verified {history} {repeat}', flush=True)
    result = {'schema': 'ao_pc_landing_event_l1_review_v1', 'formal_replays_passed': True,
              'l1_complete': False, 'runtime_approved': False, 'performance_tested': False,
              'replays': replays, 'remaining_source_gates': ['Trigger-edge, held and rapid confirm sequence, three repeats'],
              'remaining_downstream_gates': ['Godot parity and ninth bundle', 'Source pixel/presentation validation',
                                           'Interactive UI/input/reset tests', 'Short screenshots and Windows package']}
    path = base/'l1-formal-review.json'
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path)
    args = parser.parse_args()
    print(json.dumps(review(args.capture) if args.capture else run(), ensure_ascii=True))
