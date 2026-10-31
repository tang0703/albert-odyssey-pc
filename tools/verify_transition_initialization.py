"""Detailed T1 initializer/fade component proof; not a complete runtime gate."""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path

import character_animation
import event_actor_reference as actor
import probe_movement
import room_camera
from inspect_event_capture import watched
from transition_initialization import initialize_player, initialize_camera, camera_profile, camera_step, fade_step
from transition_source import ROOT, sha
from verify_transition_capture import verify_files


def validate(folder):
    manifest, entries, manifest_sha=verify_files(folder)
    original=ROOT/'reports/exploration/e1-nav-05/frame-000600'
    high=(original/'wram-high.bin').read_bytes()
    low=(original/'wram-low.bin').read_bytes()
    profile=character_animation.profile_from_snapshot(high,low)
    story=bytes([7])+high[0x36939:0x369b8]
    camera_rules=camera_profile(story)
    player=initialize_player(high,low,profile)
    initial_player=bytes(player)
    cameras=[initialize_camera((0x3880,0x7780),camera_rules) for _ in range(2)]
    initialized=False; pending=False; updates=0;checks=0;errors=[];queries=set()
    init_frame=None; first_move=None
    for line in (folder/'hooks.jsonl').open(encoding='utf-8'):
        row=json.loads(line);pc=row['pc']
        if pc==0x06093a50:
            if initialized:raise ValueError('Unexpected second scene initialization')
            actual=watched(row,0x060c8758,112)
            if actual!=player:errors.append({'frame':row['frame'],'player_initialization':'mismatch'})
            checks+=112;initialized=True;init_frame=row['frame']
        if not initialized:continue
        if pc==0x06091594:
            if pending:raise ValueError('Actor update overlap')
            phase=int.from_bytes(watched(row,0x060c27aa,2),'big')
            pad=int.from_bytes(watched(row,0x06036642,2),'big')
            # This component checks the source input gate with the observed
            # phase, separately proved by the independent fade recurrence.
            player=bytearray(probe_movement.replay_input_gate(player,pad,phase,0)[0])
            pending=True
        if pc==0x0609159a:
            if not pending:raise ValueError('Actor update without input gate')
            player,diag=actor.free_step(player,profile,low[0x10000:0x20000],0)
            queries.update(d['index'] for d in diag['lookups'])
        if pc==0x060915a0:
            actual=watched(row,0x060c8758,112)
            if actual!=player:
                errors.append({'frame':row['frame'],'actor':{hex(i):[actual[i],player[i]] for i in range(112) if actual[i]!=player[i]}})
            checks+=112
            xy=tuple(probe_movement.signed16(actor.word(player,i)) for i in (0,2))
            cameras=[camera_step(c,xy,camera_rules) for c in cameras]
            if first_move is None and tuple(xy)!=(0x3880,0x7780):first_move=row['frame']
        if pc==0x060915a6:
            for slot in range(2):
                actual=room_camera.state_from_bytes(watched(row,0x060c4288+slot*60,60))
                if actual!=cameras[slot]:errors.append({'frame':row['frame'],'camera':slot,'actual':actual,'predicted':cameras[slot]})
                checks+=8
            updates+=1;pending=False
    frames=[json.loads(line) for line in (folder/'frames.jsonl').open(encoding='utf-8')]
    start=None;fade_in=None;rgb=(0,0,0);phase=2;first_visible=None;black=False;previous_rgb=rgb
    samples=[]
    for frame in range(1,len(frames)+1):
        snap=folder/f'frame-{frame:06}'
        if not snap.is_dir():raise ValueError('Detailed display proof requires every video frame')
        sample=json.loads((snap/'sample.json').read_text())
        memory=(snap/'wram-high.bin').read_bytes()
        actual_phase,main=struct.unpack_from('>HH',memory,0xc27aa)
        actual_rgb=struct.unpack_from('>hhh',memory,0xce172)
        # Source blocks scene teardown/upload without invoking a fade tick.
        # The model records those waits as display scheduling, not player ticks.
        if start is None and actual_phase==1:
            start=frame;phase=1
        elif start is not None and frame<init_frame:
            if phase==1:phase,rgb=fade_step(phase,rgb)
        elif frame==init_frame:
            phase=0
        elif frame>init_frame and main==2:
            if fade_in is None:fade_in=frame
            else:phase,rgb=fade_step(phase,rgb)
        if (phase,rgb)!=(actual_phase,actual_rgb):
            errors.append({'frame':frame,'fade_actual':[actual_phase,actual_rgb],'predicted':[phase,rgb]})
        regs=sample['vdp2']
        if tuple(regs[k] for k in ('COAR','COAG','COAB'))!=tuple(v&511 for v in rgb):
            errors.append({'frame':frame,'colour_registers':'mismatch'})
        video=(snap/'video-rgba.bin').read_bytes()
        if len(video)!=320*224*4:raise ValueError('Unexpected display extent')
        maximum=max(max(video[0::4]),max(video[1::4]),max(video[2::4]))
        if frame>init_frame and maximum and first_visible is None:first_visible=frame
        if start is not None and frame>start and maximum==0:black=True
        if frame>=init_frame and frame<=len(frames) and frame<first_move:
            # First post-upload image has an 8-bit source maximum of 248.
            # Displayed colour offset comes from the preceding video frame.
            expected_max=max(0,248+previous_rgb[0])
            if fade_in is not None and frame>fade_in:
                if maximum!=expected_max:errors.append({'frame':frame,'visible_max':[maximum,expected_max]})
        checks+=7
        samples.append({'frame':frame,'fade':phase,'main':main,'colour_offset':list(rgb),
                        'visible_max_rgb':maximum,'display_camera':[regs['SCXIN0'],regs['SCYIN0']]})
        previous_rgb=rgb
    if not initialized or not updates or first_move is None or not black or first_visible is None:
        raise ValueError('Missing complete initialization/control/display evidence')
    return {'schema':'ao_pc_transition_initialization_component_proof_v1',
            'passed':not errors,'checks':checks,'actor_camera_updates':updates,'errors':errors,
            'initial_player_hex':initial_player.hex(),'query_indices':sorted(queries),
            'capture_manifest_sha256':manifest_sha,'capture':folder.relative_to(ROOT).as_posix(),
            'fade_out_begin_frame':start,'initialization_frame':init_frame,'fade_in_begin_frame':fade_in,
            'first_visible_destination_frame':first_visible,'first_accepted_movement_frame':first_move,
            'display_samples':samples,'full_runtime_passed':False,'performance_tested':False,
            'scope':'Independent initial player, subsequent 112-byte actor updates, camera and fade components. Source pad/phase are component inputs; full scheduler gate is separate.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=validate(a.capture.resolve())
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('display_samples','initial_player_hex','query_indices','errors')}))
    print(json.dumps(result['errors'][:5]))
    raise SystemExit(0 if result['passed'] else 1)
