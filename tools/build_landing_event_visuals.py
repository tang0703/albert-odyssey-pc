"""Export bounded event actor art from pinned original textures and records.

The capture supplies independently verified texture allocation and palette
observations. No screenshot is used as an asset and no actor state is inferred
from this exporter. The separate world/pixel gate is mandatory for packaging.
"""
import json
import struct
from pathlib import Path
from transition_source import ROOT,sources,sha
from transition_objects import Resources,initialize_objects,initialize_actor
from landing_event_draw_order import scene
from transition_graphics import atlases,ORIGIN,SIZE
from character_graphics import MAP_V1N_SHA256,PALETTE_SOURCE_OFFSET,PALETTE_CRAM_OFFSET,sprite_code_rgba
from export_character_scene_props import decode_piece,compose_pieces
from pipeline import parse_v1n
from equipment_contract import encoded
from verify_transition_capture import verify_files


def build():
    capture=ROOT/'reports/landing-event/l1-equip-1'
    _,files,digest=verify_files(capture)
    sample=capture/'frame-001200'
    high=bytearray((sample/'wram-high.bin').read_bytes());low=(sample/'wram-low.bin').read_bytes()
    vram=(sample/'vram1.bin').read_bytes();cram=(sample/'cram.bin').read_bytes()
    regs=json.loads((sample/'sample.json').read_bytes())['vdp2']
    _,source=sources();v1n=(ROOT.parent/'work/extract/MAP001.V1N').read_bytes()
    if sha(v1n)!=MAP_V1N_SHA256:raise ValueError('Destination texture source changed')
    records=parse_v1n(v1n)
    resources=Resources(bytes(high[0x36938:0x369b8]));objects,programs=initialize_objects(resources)
    npc,_=initialize_actor(resources)
    base=ROOT/'generated/landing-event';base.mkdir(exist_ok=True)
    output=[]
    from landing_event_actor import Profile
    profile=Profile(resources)
    variants=[(image,flip) for image in sorted(profile.images) for flip in ((0,1) if image in (3,4,5) else (0,))]
    for image_index,flip in variants:
        kind,slot='actor',1
        mem=bytearray(high)
        address=0xc87c8
        struct.pack_into('>H',mem,address+0x34,image_index)
        struct.pack_into('>H',mem,address+0x14,flip)
        struct.pack_into('>I',mem,address+0x5c,profile.image_pointer(image_index))
        current=scene(bytes(mem),low,room_camera_scope=True)
        row=next(r for r in current[kind+'s'] if r['slot']==slot)
        parts=[];evidence=[];priorities=set()
        source_offset=row['record_address']-0x260e0000+8
        count=2+6*len(row['pieces'])
        if source[source_offset:source_offset+count]!=mem[row['record_address']&0xfffff:(row['record_address']&0xfffff)+count]:
            raise ValueError('Destination image record is not source bound')
        for piece in row['pieces']:
            bits=4 if piece['color_mode']==0 else 6
            size=piece['width']*piece['height']//(2 if bits==4 else 1)
            packed=vram[piece['texture_offset']:piece['texture_offset']+size]
            matches=[r for r in records if r['width']==piece['width'] and r['height']==piece['height'] and r['bits_per_pixel']==(4 if bits==4 else 8) and r['packed_sha256']==sha(packed)]
            if not matches:raise ValueError('Destination texture is not source bound')
            offset=(1024+(piece['colr']&1023))*2;size=(1<<bits)*2
            source_palette=PALETTE_SOURCE_OFFSET+offset-PALETTE_CRAM_OFFSET
            if cram[offset:offset+size]!=source[source_palette:source_palette+size]:raise ValueError('Destination palette changed')
            img=decode_piece(matches[0]['payload'],piece['width'],piece['height'],bits,piece['colr'],cram,regs,piece['flip_x'])
            ox,oy=piece['offset']
            if piece['flip_x']:ox=-ox-piece['width']
            parts.append((img,(ox,oy)));priorities.add(sprite_code_rgba(piece['colr']|1,cram,regs)[1])
            evidence.append({**piece,'source_texture_offsets':[r['payload_offset'] for r in matches],
                             'texture_sha256':sha(packed),'palette_source_offset':source_palette,'palette_sha256':sha(cram[offset:offset+size])})
        if len(priorities)!=1:raise ValueError('Mixed sprite priority requires separate rendering')
        image,anchor=compose_pieces(parts)
        name=f'actor-50-{image_index:02d}-{flip}.png';image.save(base/name)
        output.append({'id':f'landing_event_actor_50', 'flip_x':bool(flip),'kind':'prop','source_kind':kind,'slot':slot,'image_index':image_index,
                       'file':name,'anchor':anchor,'dimensions':list(image.size),'world_xy_raw':row['world_xy_raw'],
                       'y_sorted':row['y_sorted'],'sprite_priority':priorities.pop(),'command_priority':row['pieces'][0]['effective_priority'],
                       'render_flags':row['render_flags'],'source_record_offset':source_offset,'source_record_sha256':sha(source[source_offset:source_offset+count]),'pieces':evidence})
    raw=encoded({'schema':'ao_pc_landing_event_visuals_v1','origin':list(ORIGIN),'size':list(SIZE),'frames':output,
                 'source_capture_manifest_sha256':digest,'source_frame':1200,'runtime_approved':False})
    (base/'visuals.json').write_bytes(raw)
    print(json.dumps({'frames':len(output),'visuals_sha256':sha(raw),'runtime_approved':False}))


if __name__=='__main__':build()
