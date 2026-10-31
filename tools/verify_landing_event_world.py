"""Predicted world commands versus executed VDP commands, with explicit UI scope."""
import argparse
import bisect
import hashlib
import json
import struct
from pathlib import Path
from verify_landing_event_sequence import validate
from landing_event_draw_order import scene
from character_draw_order import _matches,verify_source
from inspect_event_capture import watched
from functools import lru_cache
from character_graphics import PlayerResource, sha


@lru_cache(maxsize=1)
def player_resource():
    extracted=Path(__file__).resolve().parents[2]/'work/extract'
    return PlayerResource(*[(extracted/name).read_bytes() for name in ('PARTY0.PTY','MAP001.TWN','TWN.BIN')])


def predicted_scene(high,low,source,state):
    if state.get('initial_submission_empty'):
        return {'camera_raw':[state['cameras'][0]['x'],state['cameras'][0]['y']],
                'ordered_pieces':[],'body_and_prop_order':[],'model_frame':state['frame'],'model_update':state['update']}
    mem=bytearray(high)
    mem[0xc8758:0xc87c8]=bytes.fromhex(state['player'])
    # The source player uploader keeps allocated VRAM origins and updates the
    # descriptor dimensions from the selected PARTY0 texture group.
    resource=player_resource()
    image=resource.image(int.from_bytes(mem[0xc878c:0xc878e],'big'))
    table=int.from_bytes(mem[0x741e0:0x741e4],'big')&0xfffff
    for piece in image['pieces']:
        texture=resource.textures[piece['texture_index']]
        struct.pack_into('>H',mem,table+(piece['attributes']&255)*10+2,(texture.width//8)<<8|texture.height)
    mem[0xca358:0xca358+64*60]=bytes(64*60)
    mem[0xc87c8:0xc8758+32*112]=bytes(31*112)
    for slot,raw in enumerate(state['objects']):
        mem[0xca358+slot*60:0xca358+(slot+1)*60]=bytes.fromhex(raw)
    mem[0xc87c8:0xc8838]=bytes.fromhex(state['arrival_actor'])
    for i,c in enumerate(state['cameras']):
        for key,offset in (('x',10),('y',12),('display_x',14),('display_y',16),('dx',24),('dy',26),('offset_x',28),('offset_y',30)):
            struct.pack_into('>h',mem,0xc4288+i*60+offset,c[key])
    result=scene(bytes(mem),low,room_camera_scope=True)
    result['model_frame']=state['frame'];result['model_update']=state['update']
    for piece in result['ordered_pieces']:
        if piece['id'].startswith('actor_0:'):
            texture=resource.textures[image['pieces'][piece['piece']]['texture_index']]
            piece['expected_texture_sha256']=sha(texture.indices)
    return result


def check(folder,pixel_folder=None):
    pixels=None
    if pixel_folder is not None:
        from landing_event_pixel_reference import Pixels
        pixels=Pixels(pixel_folder)
    reference=validate(folder,collect=True)
    if not reference['passed']:raise ValueError('Event core failed before world comparison')
    high=(folder/'frame-000000/wram-high.bin').read_bytes();low=(folder/'frame-000000/wram-low.bin').read_bytes()
    source=(Path(__file__).resolve().parents[2]/'work/extract/MAP001.TWN').read_bytes()
    extracted=Path(__file__).resolve().parents[2]/'work/extract'
    core=(extracted/'0').read_bytes()
    source_ranges=verify_source((extracted/'TWN.BIN').read_bytes(),core)
    actor_render=(extracted/'TWN.BIN').read_bytes()[0x7400:0x7aec]
    if sha(actor_render)!='0f8a509b74ef5325030f4c1014500c5a28854db5cb6ff23768913399de70efdd':raise ValueError('Landing actor culling routine changed')
    source_ranges.append({'file':'work/extract/TWN.BIN','start':0x7400,'end_exclusive':0x7aec,'sha256':sha(actor_render)})
    if high[0x86f90:0x8705c]!=core[0x76f90:0x7705c]:raise ValueError('Runtime command submission code changed')
    states=[s for s in reference.pop('predictions') if s['scene']==7]
    first_world=states[0]['frame']+1;last_world=states[-1]['frame']-2
    states.insert(0,reference['initialization_state'])
    indices=[s['event_index'] for s in states]
    submissions=[];pending=None
    for line in (folder/'hooks.jsonl').open('rb'):
        row=json.loads(line)
        if row['pc']==0x06086fca:
            if pending is not None:raise ValueError('Overlapping priority-chain submission')
            bank=int.from_bytes(watched(row,0x06074208,4),'big')&0x7ffff
            if bank not in (0x20,0x2a20) or row['r'][9]&0x7ffff!=bank or row['r'][10]*8!=bank:
                raise ValueError('Unknown source command buffer')
            index=bisect.bisect_left(indices,row['event_index'])-1
            if index<0:
                pending={'ignore':True};continue
            pending={'bank':bank,'state_index':index,'entry':row['event_index'],'update':states[index]['update']}
        elif row['pc']==0x06087050:
            if pending and pending.get('ignore'):
                pending=None;continue
            if pending is None or row['r'][10]*8!=pending['bank']:raise ValueError('Unpaired command submission')
            end=(row['r'][9]&0x7ffff)+32
            if not pending['bank']<end<=pending['bank']+0x2a00:raise ValueError('Command buffer overflow')
            submissions.append(pending|{'end':end,'complete':row['event_index']});pending=None
    if pending is not None or not submissions:raise ValueError('Incomplete command buffer evidence')
    manifest_raw=(folder/'manifest.json').read_bytes();manifest=json.loads(manifest_raw.decode('utf-8-sig'))
    expected=next(r['sha256'] for r in manifest['outputs'] if r['path']=='vdp-events.jsonl')
    digest=hashlib.sha256();frames=[];errors=[];start=None;commands=[];skipped=[];draw_end=None
    def finish(final=False):
        if start is None:return
        if not first_world<=start['frame']<=last_world:return
        if not commands:raise ValueError('Source draw contains no executed commands')
        first=commands[0]['event_index']
        candidates=[s for s in submissions if s['complete']<first and
                    all(s['bank']<=e['command_address']<s['end'] for e in commands)]
        if not candidates:
            if frames or skipped:raise ValueError('Executed list has no prior completed submission')
            skipped.append({'frame':start['frame'],'reason':'Inherited command list before first captured submission'})
            return
        submission=candidates[-1];index=submission['state_index']
        current=predicted_scene(high,low,source,states[index]);observed=[];ui=0;shadow=0;unbound=[]
        for event in commands:
            raw=bytes.fromhex(event['command_hex']);words=struct.unpack('>16H',raw)
            matches=[p for p in current['ordered_pieces'] if _matches(p,raw)]
            if len(matches)>1:raise ValueError('Ambiguous event world command')
            if matches:observed.append(matches[0]['id']);continue
            opcode=words[0]&15
            if opcode in (9,10):continue
            if opcode==2 and words[3]==0x27c0:shadow+=1;continue
            indicator=(opcode==0 and words[3]==0x72d0 and words[5]==0x210 and words[6:8]==(0x110,0x40))
            if opcode==8 or (opcode==0 and words[3]==0x72f0) or (opcode==2 and words[3]==0x72e0) or indicator:
                ui+=1;continue
            unbound.append({'address':event['command_address'],'raw':event['command_hex']})
        if observed!=current['body_and_prop_order'] or unbound:
            errors.append({'frame':start['frame'],'predicted_update':states[index]['update'],
                'missing':[p for p in current['body_and_prop_order'] if p not in observed],
                'order_matches':observed==current['body_and_prop_order'],'unbound':unbound})
        frames.append({'frame':start['frame'],'update':states[index]['update'],'submission_complete':submission['complete'],
            'command_bank':submission['bank'],'world_pieces':len(observed),'source_ui_commands':ui,'shadow_commands':shadow})
        if pixels is not None:
            if draw_end is None and not final:raise ValueError('Draw has no observed presentation swap')
            if draw_end is not None:pixels.add_draw(current,commands,draw_end)
    for line in (folder/'vdp-events.jsonl').open('rb'):
        digest.update(line);row=json.loads(line)
        if row['kind']=='vdp1_begin':finish();start=row;commands=[];draw_end=None
        elif row['kind']=='command_execute_before':commands.append(row)
        elif row['kind']=='vdp1_swap_after_flip':
            # The source can poll an invalid next command until the scheduled
            # framebuffer swap. The newly displayed bank is the final image of
            # this draw even when there was no END command.
            draw_end=dict(row);draw_end['draw_bank']=row['display_bank']
        elif row['kind']=='software_video_complete' and pixels is not None and first_world+1<=row['frame']<=last_world:
            # Scroll values at the draw boundary precede preparation of the
            # next video. Keep the active video UI configuration separate.
            from verify_character_capture import VDP2_ADDRESSES
            video=dict(row);regs=bytearray.fromhex(row['vdp2_registers_be_hex'])
            old=bytes.fromhex(start['vdp2_registers_be_hex'])
            for name in ('SCXIN0','SCYIN0','SCXIN1','SCYIN1'):
                offset=VDP2_ADDRESSES[name];regs[offset:offset+2]=old[offset:offset+2]
            video['vdp2_registers_be_hex']=regs.hex()
            pixels.videos.append(video)
    finish(final=True)
    if digest.hexdigest()!=expected:raise ValueError('Changed VDP command evidence')
    pixel_report=pixels.finish() if pixels is not None else None
    return {'schema':'ao_pc_event_predicted_world_diagnostic_v1','passed':not errors and bool(frames) and (pixel_report is None or pixel_report['passed']),
        'pixels':pixel_report,
        'source_world_interval':[first_world,last_world],'full_event_acceptance':False,'capture_integrity_required':True,'capture_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),
        'core_checks':reference['checks'],'render_phase':'Latest completed priority-chain submission for the consumed command bank; no fixed video-frame subtraction.',
        'source_ranges':source_ranges,
        'frames':frames,'errors':errors,'inherited_frames':skipped,
        'limits':['Only the source dialogue UI command classes excluded; HD dialogue has its own acceptance.','Original player shadow omitted.','Pixel composition is a separate gate.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--pixel-capture',type=Path)
    a=p.parse_args();r=check(a.capture,a.pixel_capture);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'frames':len(r['frames']),'errors':r['errors'][:5],'error_count':len(r['errors'])}))
    raise SystemExit(0 if r['passed'] else 1)
