"""Check the source interaction consumer against its shape/rectangle model.

This component check does not certify event semantics or a PC implementation.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from inspect_event_capture import watched
import interaction_trigger as trigger
import probe_movement


def validate(folder):
    manifest_raw = (folder/'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw.decode('utf-8-sig'))
    if manifest.get('inputs_unchanged') is not True:
        raise ValueError('Capture inputs were not verified')
    records = {r['path']: r for r in manifest['outputs']}
    high = (folder/'frame-000000/wram-high.bin').read_bytes()
    if hashlib.sha256(high).hexdigest() != records['frame-000000/wram-high.bin']['sha256']:
        raise ValueError('Initial RAM changed')
    root = Path(__file__).resolve().parents[2]
    record = trigger.source_record(high, (root/'work/extract/MAP001.TWN').read_bytes(),
                                   (root/'work/extract/TWN.BIN').read_bytes())
    errors, attempts = [], []
    pending = None
    digest = hashlib.sha256()
    for line in (folder/'hooks.jsonl').open('rb'):
        digest.update(line)
        row = json.loads(line)
        pc = row['pc']
        if pc == 0x060ac698:
            if pending is not None:
                raise ValueError('Unclosed interaction consumer')
            raw = watched(row, 0x060c8758, 112)
            shape = probe_movement.APPROVED_SHAPES[int.from_bytes(raw[0x28:0x2a], 'big')]
            pos = trigger.point(*struct.unpack_from('>hh', raw), int.from_bytes(raw[0x26:0x28], 'big'), shape)
            pending = {'frame': row['frame'], 'actor_xy': list(struct.unpack_from('>hh', raw)),
                       'heading': int.from_bytes(raw[0x26:0x28], 'big'), 'point': list(pos),
                       'predicted_hit': trigger.hit(record, pos), 'actual_hit': False,
                       'point_checked': False}
        elif pc == 0x060ac776 and pending is not None:
            actual = [trigger.signed(row['r'][i]) for i in (10, 11)]
            pending['point_checked'] = True
            if actual != pending['point']:
                errors.append({'frame': row['frame'], 'actual_point': actual, 'predicted_point': pending['point']})
        elif pc == 0x060ac81a and pending is not None:
            pending['actual_hit'] = True
        elif pc == 0x060acbea and pending is not None:
            if not pending['point_checked'] or pending['actual_hit'] != pending['predicted_hit']:
                errors.append(dict(pending))
            attempts.append(pending)
            pending = None
    if digest.hexdigest() != records['hooks.jsonl']['sha256']:
        raise ValueError('Hook stream changed')
    if pending is not None:
        raise ValueError('Incomplete interaction consumer')
    return {'schema': 'ao_pc_interaction_trigger_comparison_v1', 'passed': not errors and bool(attempts),
            'full_interaction_acceptance': False, 'capture_manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
            'record': record, 'attempts': attempts, 'errors': errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.capture)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
