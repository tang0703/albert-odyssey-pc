"""Source inventory for the bounded MAP001 landing event, not acceptance.

The old eight contracts stay immutable. Dynamic capture verification must bind
these programs and dialogue requests before any runtime package is approved.
"""
import hashlib
import json
from pathlib import Path
from interaction_contract import LENGTHS as PREVIOUS_LENGTHS
from pipeline import import_dialogue
from transition_source import ROOT, sources, pointer

PROGRAMS = {
    'entry': (0x2c17, 0x2c26),
    'main': (0x2c26, 0x2c69),
    'player_look': (0x1b21, 0x1b25),
    'laia_approach': (0x1c92, 0x1c9e),
    'laia_return': (0x2ccc, 0x2cd6),
    'laia_ambient': (0x2cd6, 0x2d05),
}
LENGTHS = {**PREVIOUS_LENGTHS, 0x20: 5}
TEXT_IDS = {4: 'map001_00b141', 5: 'map001_00b2e2'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def programs():
    twn, source = sources()
    result = {}
    starts = {bounds[0]: name for name, bounds in PROGRAMS.items()}
    for name, (begin, end) in PROGRAMS.items():
        cursor = begin
        rows = []
        while cursor < end:
            op = source[cursor]
            size = LENGTHS.get(op)
            if size is None or cursor + size > end:
                raise ValueError(f'Unknown/truncated landing instruction {cursor:04x}')
            raw = source[cursor:cursor+size]
            word = lambda i=1: int.from_bytes(raw[i:i+2], 'big')
            args = {}
            if op == 0:
                if raw != b'\0\0': raise ValueError('Unknown termination')
                action = 'end'
            elif op == 9:
                if cursor != 0x2c17 or raw[9:] != bytes.fromhex('02000300'):
                    raise ValueError('Unverified landing branch')
                action = 'branch_story'
                args = {'bit': 3, 'if_clear': pointer(source,cursor+1),
                        'if_set': pointer(source,cursor+5)}
            elif op == 0x25: action = 'lock_control'
            elif op == 0x26: action = 'unlock_control'
            elif op == 0x37:
                if word() != 3: raise ValueError('Unknown landing flag mutation')
                action = 'set_story_bit'; args = {'bit': 3}
            elif op == 0x1d:
                target = pointer(source,cursor+3)
                if word() not in (0,50) or target not in starts:
                    raise ValueError('Unknown landing actor program')
                action = 'attach_actor'; args = {'actor_id': word(),'program': starts[target]}
            elif op == 0x2e:
                if word() != 50: raise ValueError('Unknown actor wait')
                action = 'wait_actor'; args = {'actor_id': 50}
            elif op == 0x24:
                if raw[1:] != bytes.fromhex('24b070000010'):
                    raise ValueError('Unknown event camera target')
                action = 'camera_target'; args = {'x_raw':word(),'y_raw':word(3),'speed_raw':word(5)}
            elif op == 0x28:
                if word() != 0: raise ValueError('Unknown camera follow actor')
                action = 'camera_follow_player'
            elif op == 0x3a:
                if raw[1] != 2: raise ValueError('Unknown camera wait')
                action = 'wait_camera'; args = {'restore_speed': True}
            elif op == 0x2d:
                if raw[1:3] != b'\0\0' or raw[3] not in TEXT_IDS:
                    raise ValueError('Unknown landing dialogue')
                action = 'dialogue'; args = {'id': TEXT_IDS[raw[3]]}
            elif op == 1: action = 'wait_updates'; args = {'count':word()}
            elif op == 2: action = 'actor_pose'; args = {'heading':raw[1]}
            elif op == 0x29: action = 'actor_speed'; args = {'index':raw[1]}
            elif op in (6,7): action = 'actor_move_axis'; args = {'axis':op-6,'target_raw':word()}
            elif op == 0x1f:
                if word() != 7: raise ValueError('Unknown ambient actor animation')
                action = 'actor_animation'; args = {'index':7}
            elif op == 0x20:
                target = pointer(source,cursor+1)
                if name != 'laia_ambient' or target != begin:
                    raise ValueError('Unverified ambient loop')
                action = 'jump'; args = {'target':target}
            else: raise ValueError(f'No bounded interpretation for {op:02x}')
            rows.append({'offset':cursor,'opcode':op,'span':size,'sha256':sha(raw),
                         'handler':int.from_bytes(twn[0x262f8+op*4:0x262fc+op*4],'big'),
                         'action':action,'args':args})
            cursor += size
        result[name] = rows
    return result


def text_records():
    lock = json.loads((ROOT/'source-lock.json').read_text(encoding='utf-8'))['sources']
    names = ('work/extract/MAP001.TWN','work/analysis/dialogue_twn_all_descriptors.json',
             'translation/zh-TW/dialogue_twn_all.tsv')
    raw = {name:(ROOT.parent/name).read_bytes() for name in names}
    if any(sha(value) != lock[name] for name,value in raw.items()):
        raise ValueError('Locked landing text or translation changed')
    records = import_dialogue(raw[names[0]],json.loads(raw[names[1]].decode('utf-8-sig')),
                              raw[names[2]].decode('utf-8-sig'))
    selected = {r['id']:r for r in records if r['id'] in TEXT_IDS.values()}
    if set(selected) != set(TEXT_IDS.values()): raise ValueError('Missing required landing dialogue')
    if [len(selected[TEXT_IDS[i]]['pages']) for i in (4,5)] != [5,3]:
        raise ValueError('Landing page sequence changed')
    if any(not p['playback_allowed'] or '\ufffd' in p['zh_tw'] for r in selected.values() for p in r['pages']):
        raise ValueError('Unsupported source text control or invalid translation')
    return selected


if __name__ == '__main__':
    result = {'schema':'ao_pc_landing_event_source_inventory_v1','source_acceptance':False,
              'programs':programs(),'dialogues':text_records()}
    folder = ROOT/'generated/landing-event'; folder.mkdir(exist_ok=True,parents=True)
    (folder/'source-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'programs':len(result['programs']),
                      'instructions':sum(map(len,result['programs'].values())),
                      'pages':sum(len(t['pages']) for t in result['dialogues'].values()),
                      'source_acceptance':False}))
