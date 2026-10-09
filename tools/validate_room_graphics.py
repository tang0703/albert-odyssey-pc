"""Continuous source scene projection and full non-shadow pixel comparison.

Actor, camera and decoration states advance from the seed only. Source PNG
generation is independent of screenshots. Shadow bank pixels remain explicit.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
import character_animation as actor_model
import room_camera
import room_decoration
import room_graphics
from character_draw_order import scene_from_snapshot, compare_commands, _matches, verify_source
from character_graphics import (BackgroundSource, PlayerResource, sha, PALETTE_SOURCE_OFFSET,
                               PALETTE_CRAM_OFFSET, sprite_code_rgba)
from export_character_scene_props import decode_piece
from pipeline import parse_v1n
from verify_character_capture import inspect, VDP2_ADDRESSES
from decode_background import parameters
from decode_source_scene import pattern_word

ROOT=Path(__file__).resolve().parents[1]

def validate(folder: Path, fixture: dict, background: Image.Image, foreground: Image.Image) -> dict:
    evidence=inspect(folder)
    def read(name):
        raw=(folder/name).read_bytes()
        if sha(raw)!=evidence['outputs'][name]: raise ValueError('Capture changed after integrity gate')
        return raw
    high,low=read('frame-000000/wram-high.bin'),read('frame-000000/wram-low.bin')
    sources={n:(ROOT.parent/'work/extract'/n).read_bytes() for n in ('TWN.BIN','MAP001.TWN','MAP001.V1N','PARTY0.PTY','0')}
    verify_source(sources['TWN.BIN'],sources['0'])
    resource=PlayerResource(sources['PARTY0.PTY'],sources['MAP001.TWN'],sources['TWN.BIN'])
    texture_sources={r['packed_sha256']:r['payload'] for r in parse_v1n(sources['MAP001.V1N'])}
    texture_sources.update({sha(t.indices):t.indices for t in resource.textures.values()})
    ap=actor_model.profile_from_snapshot(high,low)
    cp=room_camera.profile_from_snapshot(high,sources['TWN.BIN'])
    dp=room_decoration.profiles(high,sources['TWN.BIN'],sources['MAP001.TWN'])
    actors=[dict(ap.initial_state)];cameras=[room_camera.state_from_bytes(high,0xc4288)]
    decorations=[[p.initial for p in dp]]
    for update in fixture['actor_fixture']['updates']:
        state,_=actor_model.step_game_input(actors[-1],update['game_pad_word'],ap)
        if state!=update['expected']: raise ValueError('Continuous actor fixture mismatch')
        actors.append(state)
        cameras.append(room_camera.step(cameras[-1],(state['x_word'],state['y_word']),cp))
        decorations.append([room_decoration.step(s,p) for s,p in zip(decorations[-1],dp)])
    if len(actors)!=evidence['capture']['frames']+1: raise ValueError('Route fixture length changed')
    # Use only the seed bytes, replacing fields produced by our pure models.
    def scene(update,cam):
        mem=bytearray(high)
        for name,(offset,size) in actor_model.FIELDS.items():
            mem[0xc8758+offset:0xc8758+offset+size]=actors[update][name].to_bytes(size,'big')
        mem[room_decoration.BASE:room_decoration.BASE+120]=b''.join(decorations[update])
        return scene_from_snapshot(bytes(mem),low,camera_at_command_target=[n*16 for n in cam],room_camera_scope=True)
    grouped={}
    for e in evidence['vdp_events']: grouped.setdefault(e['frame'],[]).append(e)
    bg=np.array(background);fg=np.array(foreground)
    source_bg=BackgroundSource(sources['MAP001.TWN'])
    rows=[];checked=0;shadow_pixels=0;pattern_checks=0;texture_checks=0;image_cache={}
    prior_image=None
    for frame,events in grouped.items():
        if frame<1: continue
        start=next(e for e in events if e['kind']=='vdp1_begin')
        video=next(e for e in events if e['kind']=='software_video_complete')
        commands=[e for e in events if e['kind']=='command_execute_before']
        draw_cam=[cameras[max(0,frame-2)][n]//16 for n in ('x','y')]
        shown_cam=[cameras[max(0,frame-3)][n]//16 for n in ('x','y')]
        regs_raw=bytes.fromhex(start['vdp2_registers_be_hex'])
        regs={n:int.from_bytes(regs_raw[o:o+2],'big') for n,o in VDP2_ADDRESSES.items()}
        if [regs[n] for n in ('SCXIN0','SCYIN0')]!=shown_cam or [regs[n] for n in ('SCXIN1','SCYIN1')]!=shown_cam:
            raise ValueError(f'Independent camera scanout delay mismatch at {frame}')
        source_bg.check_registers(regs)
        # Validate each visible source pattern, including partial edge tiles.
        vram2=read(f'frame-{frame-1:06d}/vram2.bin')
        if vram2[0x40000:]!=source_bg.tiles: raise ValueError('Source tiles changed')
        for layer in (0,1):
            param=parameters(regs,layer)
            for ty in range(shown_cam[1]//16,(shown_cam[1]+223)//16+1):
                for tx in range(shown_cam[0]//16,(shown_cam[0]+319)//16+1):
                    wx,wy=tx*16,ty*16;value=source_bg.pixel(layer,wx,wy)
                    page=((wx%1024)//512)+((wy%1024)//512)*2
                    offset=param['plane_offsets'][page]+(((wy//16)%32)*32+(wx//16)%32)*4
                    if int.from_bytes(vram2[offset:offset+4],'big')!=pattern_word(value['compact_pattern']):
                        raise ValueError('Visible source pattern mismatch')
                    pattern_checks+=1
        current=scene(max(0,frame-2),draw_cam)
        order=compare_commands(current,commands)
        cram=read(f'frame-{frame:06d}/cram.bin')
        if cram[2:512]!=source_bg.palette[2:]: raise ValueError('Background palette mismatch')
        if sha(cram)!=video['cram_sha256']: raise ValueError('Scanout palette changed')
        x,y=draw_cam[0]-512,draw_cam[1]-1536
        predicted=bg[y:y+224,x:x+320].copy()
        front=fg[y:y+224,x:x+320]
        for piece in current['ordered_pieces']:
            matches=[e for e in commands if _matches(piece,bytes.fromhex(e['command_hex']))]
            if len(matches)!=1: raise ValueError('Ambiguous piece command')
            event=matches[0];digest=event['texture']['sha256']
            if digest not in texture_sources: raise ValueError('Unbound texture payload')
            packed=read('blobs/'+digest+'.bin')
            # 4-bit parser expands nibbles; 8-bit character source is direct.
            indices=texture_sources[digest]
            if sha(packed)!=digest: raise ValueError('Texture payload changed')
            bits=4 if piece['color_mode']==0 else 6
            palette_offset=(1024+(piece['colr']&1023))*2
            src_offset=PALETTE_SOURCE_OFFSET+palette_offset-PALETTE_CRAM_OFFSET
            size=(1<<bits)*2
            # Player palettes are already bound by the source character gate;
            # props use the original map palette.
            if piece['id'].startswith('object_') and cram[palette_offset:palette_offset+size]!=sources['MAP001.TWN'][src_offset:src_offset+size]:
                raise ValueError('Source prop palette mismatch')
            cache_key=(digest,piece['colr'],piece['flip_x'])
            if cache_key not in image_cache:
                image_cache[cache_key]=np.array(decode_piece(indices,piece['width'],piece['height'],bits,piece['colr'],cram,regs,piece['flip_x']))
            image=image_cache[cache_key];texture_checks+=1
            sx,sy=piece['screen_origin'];w,h=piece['width'],piece['height']
            l,t,r,b=max(0,sx),max(0,sy),min(320,sx+w),min(224,sy+h)
            if l>=r or t>=b: continue
            clipped=image[t-sy:b-sy,l-sx:r-sx];mask=clipped[:,:,3]!=0
            target=predicted[t:b,l:r];target[mask]=clipped[mask]
            priority=sprite_code_rgba(piece['colr']|1,cram,regs)[1]
            if priority==2:
                cover=mask & (front[t:b,l:r,3]!=0);target[cover]=front[t:b,l:r][cover]
        # Draw f is shown at f+1. First image is inherited from the seed;
        # its player/shadow source validation remains the earlier A1 gate.
        if prior_image is not None:
            bank=video['display_bank']
            fb=read(f'frame-{frame-1:06d}/vdp1-fb{bank}.bin')
            if sha(fb)!=video['framebuffer_sha256'][bank]: raise ValueError('Presented framebuffer payload changed')
            codes=np.frombuffer(fb,dtype='>u2').reshape(256,512)[:224,:320]
            # Source shadow command is 6-bit bank 0x27c0 (64 codes).
            shadow=(codes&0xffc0)==0x27c0
            actual=np.frombuffer(read(f'frame-{frame:06d}/video-rgba.bin'),dtype=np.uint8).reshape(224,320,4)
            bad=np.any(prior_image!=actual,axis=2)&~shadow
            count=int(np.count_nonzero(bad))
            if count:
                first=np.argwhere(bad)[0];yy,xx=map(int,first)
                raise ValueError(f'Frame {frame}: {count} unexplained pixels; {xx},{yy} expected {prior_image[yy,xx]} actual {actual[yy,xx]} code {codes[yy,xx]:04x}')
            checked+=int(np.count_nonzero(~shadow));shadow_pixels+=int(np.count_nonzero(shadow))
        prior_image=predicted
        rows.append({'frame':frame,'draw_camera':draw_cam,'scanout_camera':shown_cam,'order':order['observed_order']})
    return {'folder':str(folder.resolve()),'manifest_sha256':evidence['manifest_sha256'],'frames':len(rows),
            'compared_non_shadow_pixels':checked,'excluded_shadow_pixels':shadow_pixels,
            'source_pattern_checks':pattern_checks,'source_texture_checks':texture_checks,
            'unexplained_pixels':0,'frames_detail':rows,'passed':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    fixture=json.loads((ROOT/'reports/room/reference.json').read_text())
    bg,fg=room_graphics.atlases((ROOT.parent/'work/extract/MAP001.TWN').read_bytes())
    reports=[]
    for name,route in [('visual-west-a','visual-west'),('visual-east-a','visual-east'),('decor-east-a','visual-east')]:
        trace=next(t for t in fixture['traces'] if t['id']==route)
        reports.append(validate(ROOT/'reports/room'/name,trace,bg,fg))
        print(name,'passed',flush=True)
    result={'schema':'ao_room_graphics_validation_v1','passed':True,'camera_video_delay_updates':3,
            'decoration_video_delay_updates':3,'actor_video_delay_updates':3,'captures':reports,
            'limits':['Player shadow pixels excluded explicitly. First video inherits seed framebuffer.']}
    a.out.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__': main()
