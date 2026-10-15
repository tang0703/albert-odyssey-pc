"""Extract observed dispatcher calls. This inventory does not certify semantics."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent


def watches(row):
    return {w['address'] & 0x1fffffff: bytes.fromhex(w['hex']) for w in row['watches']}


def watched(row, address, size):
    for start, data in watches(row).items():
        if start <= address and address + size <= start + len(data):
            return data[address-start:address-start+size]
    raise ValueError(f'Missing watch {address:08x}+{size}')


def inspect(capture):
    manifest = json.loads((capture/'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest.get('inputs_unchanged') is not True:
        raise ValueError('Unverified capture inputs')
    expected = {r['path']:r['sha256'] for r in manifest['outputs']}
    for name in ('hooks.jsonl', 'frames.jsonl'):
        if hashlib.sha256((capture/name).read_bytes()).hexdigest() != expected[name]:
            raise ValueError('Capture changed')
    twn = (WORKSPACE/'work/extract/TWN.BIN').read_bytes()
    data = (WORKSPACE/'work/extract/MAP001.TWN').read_bytes()
    if hashlib.sha256(twn).hexdigest() != 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6':
        raise ValueError('TWN identity differs')
    if hashlib.sha256(data).hexdigest() != '8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9':
        raise ValueError('MAP identity differs')
    calls=[]
    pending=None
    for line in (capture/'hooks.jsonl').open(encoding='utf-8'):
        row=json.loads(line)
        if row['pc']==0x0609e092:
            if pending is not None: raise ValueError('Unpaired dispatch')
            regs=row['r']; op=regs[11]; cursor=int.from_bytes(watched(row,0x060c66bc,4),'big')-1
            handler=int.from_bytes(twn[0x262f8+op*4:0x262fc+op*4],'big')
            if regs[3] != handler: raise ValueError('Handler table differs')
            offset=cursor-0x260e0000+8
            if not 8 <= offset < len(data) or data[offset]!=op:
                raise ValueError('Dispatch does not match MAP source')
            pending={'frame':row['frame'],'event_index':row['event_index'],'slot':hex(regs[14]),
                'offset':hex(offset),'opcode':hex(op),'handler':hex(handler),
                'source_next_16_bytes':data[offset:offset+16].hex()}
        elif row['pc']==0x0609e096:
            if pending is None: raise ValueError('Return without dispatch')
            pending.update(return_frame=row['frame'],result=row['r'][0],
                next_cursor=hex(int.from_bytes(watched(row,0x060c66bc,4),'big')))
            calls.append(pending);pending=None
    controls=[]; prior=None
    for line in (capture/'frames.jsonl').open(encoding='utf-8'):
        row=json.loads(line)
        state=(watched(row,0x060c41ec,1).hex(),watched(row,0x060c51d4,2).hex(),
               watched(row,0x060c51f0,4).hex())
        if state!=prior:
            controls.append({'frame':row['frame'],'input':row['input'],'control_disabled':state[0],
                'text_state_raw':state[1],'text_pointer':state[2]});prior=state
    return {'schema':'ao_pc_event_dispatch_inventory_v1','semantic_acceptance':False,
        'capture':str(capture.resolve()),'calls':calls,'incomplete_call':pending,'state_transitions':controls}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=inspect(args.capture)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'calls':len(result['calls']),'opcodes':sorted({c['opcode'] for c in result['calls']}),
        'incomplete_call':result['incomplete_call'],'last_state':result['state_transitions'][-1]},ensure_ascii=True))
