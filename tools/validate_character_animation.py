"""Validate continuous controlled-actor animation against source-bound hooks.

No captured later actor state is used to advance the model. v1 proves state at
its existing hooks; per-hook source bank custody and presentation need v2.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import character_animation as animation
from exploration_capture import read_json_bytes, stable_read
from verify_exploration_replay import inspect


def watch(row: dict, address: int, size: int) -> bytes:
    matches = [w for w in row['watches'] if w['address'] == address and w['bytes'] == size]
    if len(matches) != 1:
        raise ValueError(f'Missing synchronous watch at {address:#x}')
    value = bytes.fromhex(matches[0]['hex'])
    if len(value) != size:
        raise ValueError('Synchronous watch truncated')
    if 'sha256' in matches[0] and hashlib.sha256(value).hexdigest() != matches[0]['sha256']:
        raise ValueError('Synchronous watch hash differs from its bytes')
    return value


def differences(expected: dict, observed: dict) -> dict:
    return {key:{'predicted':expected[key],'observed':observed[key]}
            for key in animation.FIELDS if expected[key] != observed[key]}


def validate_evidence(evidence: dict) -> tuple[dict,dict]:
    """Consume evidence already accepted by its versioned capture verifier."""
    folder = Path(evidence['folder'])
    def read(name: str) -> bytes:
        raw = stable_read(folder/name)
        if hashlib.sha256(raw).hexdigest() != evidence['outputs'][name]:
            raise ValueError('Capture changed after source validation')
        return raw
    high,low = read('frame-000000/wram-high.bin'),read('frame-000000/wram-low.bin')
    profile = animation.profile_from_snapshot(high,low)
    full_animation_hooks = evidence['capture']['schema'] == 'ao_ymir_character_capture_v2'
    expected_bank = low[0x20010:0x20350]
    snapshots = {}
    for frame in evidence['samples']:
        sampled_high = read(f'frame-{frame:06d}/wram-high.bin')
        sampled_low = read(f'frame-{frame:06d}/wram-low.bin')
        sampled_profile = animation.profile_from_snapshot(sampled_high,sampled_low)
        if sampled_low[0x20010:0x20350] != expected_bank:
            raise ValueError('Source animation/image bank changed between sampled frames')
        snapshots[frame] = sampled_profile.initial_state
    rows_by_frame = defaultdict(list)
    each_hook_bank = True
    bank_hook_count = 0
    for row in evidence['hooks']:
        if row['flags_sha256'] != animation.movement.FLAGS_SHA256:
            raise ValueError('Hook uses a different movement flag table')
        control = watch(row,0x060c27aa,8)
        if control[:2] != b'\x00\x03' or control[4] != 0 or watch(row,0x060c41ec,1) != b'\0':
            raise ValueError('Controlled slot or input gate changed')
        banks = [w for w in row['watches'] if (w['address']&0x1fffffff) == 0x00220010 and w['bytes'] == 0x340]
        if not banks:
            if full_animation_hooks:
                raise ValueError('v2 animation validation requires a source bank watch at every hook')
            each_hook_bank = False
        elif len(banks) != 1 or watch(row,banks[0]['address'],0x340) != expected_bank:
            raise ValueError('Hook animation/image bank differs from the initial pinned source')
        else:
            bank_hook_count += 1
        rows_by_frame[row['frame']].append(row)
    count = evidence['capture']['frames']
    if sorted(rows_by_frame) != list(range(1,count+1)):
        raise ValueError('Animation capture has missing or extra update frames')
    state = dict(profile.initial_state)
    failures,updates = [],[]
    comparisons,images,mirrors,timers = Counter(),Counter(),Counter(),Counter()
    starts=second_pose_starts=stops=retained_stop_timers=turns=walking_wraps=0
    turn_examples,stop_examples = [],[]
    for frame in range(1,count+1):
        rows = rows_by_frame[frame]
        at = defaultdict(list)
        for row in rows:
            at[row['pc']].append(row)
        required = [0x06094afc,0x060aa0de,0x060aae20,0x060ac20c,0x060ab61a,0x060aaeb0]
        if full_animation_hooks:
            required.extend([0x060ac0b6,0x060ac34a])
        for pc in required:
            if len(at[pc]) != 1:
                raise ValueError(f'Expected one animation/control update at {pc:#x}, frame {frame}')
        if at[0x060ab61a][0]['kind'] != 'entry' or at[0x060aaeb0][0]['kind'] != 'return':
            raise ValueError('Missing collision entry/actual caller return boundary')
        pad = int.from_bytes(watch(at[0x06094afc][0],0x06036642,2),'big')
        if len(at[0x060abfc8]) != (1 if pad else 0):
            raise ValueError('Velocity invocation disagrees with the observed game input')
        ordered = [0x06094afc,0x060aa0de,0x060aae20]
        if pad:
            ordered.append(0x060abfc8)
        if at[0x060ac0b6]:
            ordered.append(0x060ac0b6)
        ordered.append(0x060ac20c)
        if at[0x060ac34a]:
            ordered.append(0x060ac34a)
        ordered.extend([0x060ab61a,0x060aaeb0])
        if [row['pc'] for row in rows if row['pc'] in ordered] != ordered:
            raise ValueError('Animation stage execution order differs from source')
        before = dict(state)
        gated,_ = animation.movement.p.replay_input_gate(animation.actor_from_state(state),pad,3,0)
        state,diagnostic = animation.step_game_input(state,pad,profile)
        expected_hooks = {0x060aae20:animation.state_from_actor(gated),
            0x060abfc8:animation.state_from_actor(gated),
            0x060ac0b6:diagnostic['checkpoints']['before_timer'],
            0x060ac20c:diagnostic['checkpoints']['before_decode'],
            0x060ac34a:diagnostic['checkpoints']['before_image_pointer'],
            0x060ab61a:diagnostic['checkpoints']['before_collision'],0x060aaeb0:state}
        for pc,expected in expected_hooks.items():
            if len(at[pc]) > 1:
                raise ValueError('Duplicate animation stage hook')
            for row in at[pc]:
                if row['actor_address'] != animation.ACTOR_ADDRESS or row.get('actor_hex') is None:
                    raise ValueError('Animation hook does not identify the controlled actor')
                actual = animation.state_from_actor(bytes.fromhex(row['actor_hex']))
                delta = differences(expected,actual)
                if delta:
                    failures.append({'frame':frame,'pc':hex(pc),'fields':delta})
                comparisons[hex(pc)] += 1
        if frame in snapshots:
            delta = differences(state,snapshots[frame])
            if delta:
                failures.append({'frame':frame,'boundary':'end_of_frame_snapshot','fields':delta})
            comparisons['end_of_frame_snapshot'] += 1
        moving = bool(state['status_word']&2)
        was_moving = bool(before['status_word']&2)
        if moving and not was_moving:
            starts += 1
            second_pose_starts += state['animation_cursor'] == 3
        if not moving and was_moving:
            stops += 1
            retained_stop_timers += state['animation_timer'] != 0
            stop_examples.append({'frame':frame,'previous_timer':before['animation_timer'],
                'previous_duration':before['animation_duration'],'timer':state['animation_timer'],
                'duration':state['animation_duration'],'cursor':state['animation_cursor']})
        if moving and was_moving and state['heading'] != before['heading']:
            turns += 1
            turn_examples.append({'frame':frame,'before_heading':before['heading'],'heading':state['heading'],
                'before_cursor':before['animation_cursor'],'cursor':state['animation_cursor'],
                'before_timer':before['animation_timer'],'timer':state['animation_timer']})
        walking_wraps += moving and diagnostic['wrapped']
        images[str(state['image_index'])] += 1
        mirrors[str(state['render_flags_word']&1)] += 1
        timers[str(state['animation_timer'])] += 1
        updates.append({'frame':frame,'game_pad_word':pad,'expected':state,
            'advanced':diagnostic['advanced'],'wrapped':diagnostic['wrapped']})
    mismatched_frames = len({item['frame'] for item in failures})
    report = {'schema':'ao_pc_character_animation_validation_v1','capture':str(folder),
        'manifest_sha256':evidence['manifest_sha256'],'passed':not failures,
        'updates_compared':count,'mismatched_updates':mismatched_frames,'hook_comparisons':dict(comparisons),
        'profile':profile.metadata(),'continuous_prediction':True,'later_actor_state_injection':False,
        'source_bank_each_hook_verified':each_hook_bank,'source_bank_hooks_compared':bank_hook_count,
        'presentation_verified':False,'coverage':{'starts':starts,'starts_at_second_pose':second_pose_starts,
            'stops':stops,'stops_with_retained_timer':retained_stop_timers,'moving_turns':turns,
            'walking_wraps':walking_wraps,'image_indices':dict(images),'mirror_bits':dict(mirrors),
            'timers':dict(timers),'turn_examples':turn_examples,'stop_examples':stop_examples},
        'failures':failures,'limits':['Controlled cardinal movement animation only; no character name inferred.',
            'State/image pointer agreement does not prove the final visible VDP1 draw command.',
            'HD frames and interpolation are presentation work; original tick counters remain unchanged.']}
    fixture = {'initial_state':profile.initial_state,'updates':updates,'manifest_sha256':evidence['manifest_sha256']}
    return report,fixture


def validate(folder: Path) -> tuple[dict,dict]:
    manifest = read_json_bytes(stable_read(folder/'manifest.json'))
    if manifest.get('schema') == 'ao_ymir_capture_manifest_v1':
        evidence = inspect(folder)
    elif manifest.get('schema') == 'ao_ymir_character_capture_manifest_v2':
        from verify_character_capture import inspect as inspect_v2
        evidence = inspect_v2(folder)
    else:
        raise ValueError('Unsupported versioned capture manifest')
    return validate_evidence(evidence)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures',nargs='+',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--fixtures',type=Path)
    args = parser.parse_args()
    try:
        pairs = [validate(folder) for folder in args.captures]
        reports,fixtures = zip(*pairs)
        result = {'schema':'ao_pc_character_animation_suite_v1','passed':all(r['passed'] for r in reports),
            'updates_compared':sum(r['updates_compared'] for r in reports),
            'mismatched_updates':sum(r['mismatched_updates'] for r in reports),'captures':reports}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if args.fixtures:
            args.fixtures.parent.mkdir(parents=True,exist_ok=True)
            profiles = [report['profile'] for report in reports]
            if any(profile != profiles[0] for profile in profiles[1:]):
                raise ValueError('Animation fixture sequences use different initial profiles')
            args.fixtures.write_text(json.dumps({'schema':animation.SCHEMA,'passed':result['passed'],
                'profile':profiles[0],'traces':fixtures},indent=2)+'\n',encoding='utf-8')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.exit(1,f'Character animation evidence rejected: {exc}\n')
    print(json.dumps({k:result[k] for k in ('passed','updates_compared','mismatched_updates')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
