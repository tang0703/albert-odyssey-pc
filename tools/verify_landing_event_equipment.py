"""Source semantic equipment commits with landing story bit 3 set.

The full original menu and its navigation timing are not a PC interface model.
Only selected semantic requests are inputs; subsequent equipment/party/inventory
values are predictions, never copied back from the emulator.
"""
import json
from pathlib import Path
from inspect_event_capture import watched
from equipment_contract import source_contract, sha


def validate(folder):
    raw_manifest = (folder/'manifest.json').read_bytes()
    manifest = json.loads(raw_manifest.decode('utf-8-sig'))
    files = {row['path']: row for row in manifest['outputs']}
    high = (folder/'frame-000000/wram-high.bin').read_bytes()
    if sha(high) != files['frame-000000/wram-high.bin']['sha256']:
        raise ValueError('Equipment seed changed')
    contract = source_contract(high)
    state = {'weapon': high[0x366b7], 'count': high[0x367cf],
             'attack': int.from_bytes(high[0x366a0:0x366a2], 'big'), 'story': high[0x36938]}
    if state != {'weapon':27, 'count':0, 'attack':15, 'story':15}:
        raise ValueError('Unverified post-event equipment starting state')
    import hashlib
    digest = hashlib.sha256()
    actions = []; commits = []; checks = 0
    for line in (folder/'hooks.jsonl').open('rb'):
        digest.update(line)
        row = json.loads(line)
        if row['pc'] == 0x06017ede:
            selected = watched(row, 0x06036aac+4*row['r'][11]+row['r'][13], 1)[0]
            if selected == contract['remove_menu_id'] and state['weapon'] == 27 and state['count'] == 0:
                state.update(weapon=255, count=1, attack=contract['base_attack'])
                action = 'remove'
            elif selected == 27 and state['weapon'] == 255 and state['count'] == 1:
                state.update(weapon=27, count=0, attack=contract['base_attack']+contract['attack_bonus'])
                state['story'] |= contract['story_mask']
                action = 'equip'
            else: raise ValueError('Unexpected post-event equipment request')
            actions.append({'frame':row['frame'], 'action':action, 'predicted':dict(state)})
        if row['pc'] in (0x06018226, 0x06018248):
            actual = {'weapon':watched(row,0x060366b7,1)[0], 'count':watched(row,0x060367cf,1)[0],
                      'attack':int.from_bytes(watched(row,0x060366a0,2),'big'), 'story':watched(row,0x06036938,1)[0]}
            if state != actual: raise ValueError('Post-event equipment commit differs')
            inventory = bytearray(high[0x367b4:0x368b4]); inventory[27] = state['count']
            party = bytearray(high[0x3666c:0x367b4]); party[0x4b] = state['weapon']; party[0x34:0x36] = state['attack'].to_bytes(2,'big')
            if watched(row,0x060367b4,256) != inventory or watched(row,0x0603668c,260) != party[32:292]:
                raise ValueError('Unexpected party/inventory mutation after landing event')
            checks += 520
            commits.append({'frame':row['frame'],'pc':hex(row['pc']),'state':actual})
    if digest.hexdigest() != files['hooks.jsonl']['sha256'] or (folder/'manifest.json').read_bytes() != raw_manifest:
        raise ValueError('Post-event equipment evidence changed')
    if [r['action'] for r in actions] != ['remove','equip'] or not commits:
        raise ValueError('Required post-event remove/re-equip not observed')
    return {'passed':True, 'checks':checks, 'operations':actions, 'commits':commits,
            'capture_manifest_sha256':sha(raw_manifest), 'source_contract':contract,
            'performance_tested':False, 'world_navigation_model_passed':False,
            'scope':'Equipment semantic commits only; source menu cursor, fade and navigation timing are not the PC panel.'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.capture)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
