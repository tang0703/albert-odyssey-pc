"""Trace block-3 placement and exclude a palette queue from coordinate candidates."""
import json
import struct

from pipeline import PROJECT, WORKSPACE, digest, read_json, verify_source, write_json
from decode_map_graphics import map001_blocks


def system_ram(data: bytes, lock: dict) -> tuple[bytes,bytes,dict]:
    if len(data)!=lock['size'] or digest(data)!=lock['sha256'] or data[:5]!=b'\x01\x0d\0\0\0':
        raise ValueError('Pinned little-endian v13 state required')
    # Ymir cereal SystemSaveState: two 32-bit enums, bool, 16-byte IPL hash,
    # then raw 1 MiB WRAMLow and WRAMHigh; following section is MSH2.
    if data.count(b'Syst')!=1:
        raise ValueError('Ambiguous system boundary')
    start=data.index(b'Syst')+4+25
    end=start+0x200000
    if data[end:end+4]!=b'MSH2':
        raise ValueError('System RAM end marker mismatch')
    low,high=data[start:start+0x100000],data[start+0x100000:end]
    return low,high,{'low_state_offset':start,'high_state_offset':start+0x100000,
                     'low_sha256':digest(low),'high_sha256':digest(high)}


def counted_runs(data: bytes) -> list[dict]:
    """Structural candidate only: zero counts may instead be alignment words."""
    pos,runs=0,[]
    while pos<len(data):
        if pos+2>len(data):raise ValueError('Truncated count')
        count=struct.unpack_from('>H',data,pos)[0]
        end=pos+2+count*4
        if end>len(data):raise ValueError('Run exceeds block')
        records=[list(data[o:o+4]) for o in range(pos+2,end,4)]
        runs.append({'offset':pos,'count':count,'records':records,
                     'zero_c_or_d':sum(r[2]==0 or r[3]==0 for r in records),
                     'role':'unassigned','zero_count_or_alignment_ambiguous':count==0})
        pos=end
    return runs


def palette_queue_evidence(code: bytes) -> dict:
    # Ghidra range export confirmed these instructions. Require exact source
    # opcodes and literal values before reporting this bounded interpretation.
    expected={0xac3e:0xd42a,0xac40:0xd82a,0xac42:0xd92b,0xac44:0xda2b,0xac46:0xdb2c,
              0xac4c:0x8542,0xac50:0x6041,0xac52:0x4700,0xac56:0x35bc,
              0xac78:0x6365,0xac7c:0x2531,0xad0e:0x7406,0xad1c:0x2ae1}
    for offset,word in expected.items():
        if struct.unpack_from('>H',code,offset)[0]!=word:raise ValueError('Palette queue code changed')
    literals={0xace8:0x060d41a4,0xacec:0x060ce1a4,0xacf0:0x060cf1a4,
              0xacf4:0x060d41d4,0xacf8:0x25f00000}
    for offset,value in literals.items():
        if struct.unpack_from('>I',code,offset)[0]!=value:raise ValueError('Palette queue literal changed')
    return {'code_sha256':digest(code),'module_runtime_base':0x06090000,'code_range':[0xac3e,0xad1e],
            'queue_runtime':literals[0xace8],'queue_count_runtime':literals[0xacf4],
            'color_ram_runtime':literals[0xacf8],'record_bytes':6,
            'record_words':['operation','word_count','color_word_offset'],
            'verified_opcodes':{f'{k:05x}':f'{v:04x}' for k,v in expected.items()},
            'scope':'static queue reader; no dynamic trace or collision claim'}


def run() -> dict:
    sources=read_json(PROJECT/'source-lock.json')['sources']
    path='work/extract/MAP001.TWN'
    raw=verify_source(WORKSPACE,path,sources[path])
    block=map001_blocks(raw)[2]
    payload=raw[block['payload_offset']:block['payload_offset']+block['size']]
    lock=read_json(PROJECT/'savestate-lock.json')
    state=verify_source(WORKSPACE,lock['path'],lock['sha256'])
    low,high,spans=system_ram(state,lock)
    location=high.find(payload)
    if location<0 or high.find(payload,location+1)>=0:raise ValueError('Block-3 RAM match missing or ambiguous')
    code=verify_source(WORKSPACE,'work/extract/TWN.BIN',sources['work/extract/TWN.BIN'])
    queue=palette_queue_evidence(code)
    queue['captured_active_count']=struct.unpack_from('>H',high,queue['queue_count_runtime']-0x06000000)[0]
    # Do not label stale queue storage as live records when captured count is 0.
    report={'schema':'ao_pc_scene_metadata_probe_v1','source_sha256':digest(raw),'snapshot_sha256':digest(state),
            'block':block,'work_ram':spans,'block_runtime':0x06000000+location,
            'block_exact_match_bytes':len(payload),'structural_runs':counted_runs(payload),
            'palette_queue':queue,'player_coordinate_verified':False,'collision_verified':False,
            'limits':['Block 3 is loaded data; its exact consumer and gameplay meaning remain unknown.',
                      'Four-byte records are opaque. Do not infer walls, event triggers or spawn points.',
                      'Zero-count runs may be alignment; no semantic grouping claimed.',
                      'Palette queue storage is not player/camera coordinates.']}
    write_json(PROJECT/'reports/scene-metadata.json',report)
    return report


if __name__=='__main__':
    r=run()
    print(json.dumps({'runtime':hex(r['block_runtime']),'exact_bytes':r['block_exact_match_bytes'],
                      'run_counts':[x['count'] for x in r['structural_runs']],
                      'palette_queue_active':r['palette_queue']['captured_active_count']},indent=2))
