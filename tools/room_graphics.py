"""Source-only scrolling atlas and previously omitted room decorations."""
from __future__ import annotations
import struct
from pathlib import Path
from PIL import Image
from character_graphics import (BackgroundSource, MAP_V1N_SHA256, PALETTE_SOURCE_OFFSET,
                               PALETTE_CRAM_OFFSET, sha, sprite_code_rgba)
from character_draw_order import scene_from_snapshot, verify_source
from export_character_scene_props import decode_piece, compose_pieces
from pipeline import parse_v1n
import room_decoration

ORIGIN=(512,1536)
SIZE=(448,256)

def atlases(source_map: bytes) -> tuple[Image.Image,Image.Image]:
    source=BackgroundSource(source_map)
    background=Image.new('RGBA',SIZE,(0,0,0,255))
    foreground=Image.new('RGBA',SIZE)
    for y in range(SIZE[1]):
        for x in range(SIZE[0]):
            candidates=[source.pixel(layer,x+ORIGIN[0],y+ORIGIN[1]) for layer in (0,1)]
            opaque=[r for r in candidates if r['index']]
            if opaque:
                winner=max(opaque,key=lambda r:(r['priority'],-r['layer']))
                background.putpixel((x,y),winner['rgba'])
                if winner['priority']==3: foreground.putpixel((x,y),winner['rgba'])
    return background,foreground

def decorations(high: bytes,low: bytes,vram: bytes,cram: bytes,regs: dict,sources: dict) -> tuple[list[dict],dict[str,Image.Image]]:
    verify_source(sources['TWN.BIN'],sources['0'])
    programs=room_decoration.profiles(high,sources['TWN.BIN'],sources['MAP001.TWN'])
    if sha(sources['MAP001.V1N'])!=MAP_V1N_SHA256:
        raise ValueError('Decoration texture source changed')
    records=parse_v1n(sources['MAP001.V1N'])
    rows=[];images={}
    for program in programs:
        for image_index in sorted(set(program.sequence[1:-1:3])):
            mem=bytearray(high);base=0xca358+program.slot*60
            struct.pack_into('>H',mem,base+0x22,image_index)
            struct.pack_into('>I',mem,base+0x30,program.image_pointers[image_index])
            scene=scene_from_snapshot(bytes(mem),low,room_camera_scope=True)
            obj=scene['objects'][program.slot]
            parts=[];evidence=[]
            pointer=obj['record_address']-0x260e0000+8
            count=2+6*len(obj['pieces'])
            record_raw=sources['MAP001.TWN'][pointer:pointer+count]
            if record_raw!=bytes(mem)[obj['record_address']&0xfffff:(obj['record_address']&0xfffff)+count]:
                raise ValueError('Decoration image record differs from source')
            for piece in obj['pieces']:
                if piece['color_mode']!=0 or piece['effective_priority']!=255:
                    raise ValueError('Unverified decoration render mode')
                size=piece['width']*piece['height']//2
                packed=vram[piece['texture_offset']:piece['texture_offset']+size]
                matches=[r for r in records if r['width']==piece['width'] and r['height']==piece['height']
                         and r['bits_per_pixel']==4 and r['packed_sha256']==sha(packed)]
                if not matches: raise ValueError('Decoration texture is not bound to source')
                palette_offset=(1024+(piece['colr']&1023))*2
                source_offset=PALETTE_SOURCE_OFFSET+palette_offset-PALETTE_CRAM_OFFSET
                if cram[palette_offset:palette_offset+32]!=sources['MAP001.TWN'][source_offset:source_offset+32]:
                    raise ValueError('Decoration palette differs from source')
                if sprite_code_rgba(piece['colr']|1,cram,regs)[1]!=3:
                    raise ValueError('Decoration sprite priority changed')
                image=decode_piece(matches[0]['payload'],piece['width'],piece['height'],4,piece['colr'],cram,regs)
                parts.append((image,tuple(piece['offset'])))
                evidence.append({**piece,'source_texture_offsets':[r['payload_offset'] for r in matches],
                                 'texture_sha256':sha(packed),'palette_source_offset':source_offset,
                                 'palette_cram_offset':palette_offset,'palette_sha256':sha(cram[palette_offset:palette_offset+32])})
            image,anchor=compose_pieces(parts)
            name=f'decoration-{program.slot}-{image_index:02d}.png';images[name]=image
            rows.append({'id':f'object_{program.slot}','slot':program.slot,'image_index':image_index,'file':name,
                         'world_xy_raw':obj['world_xy_raw'],'anchor':anchor,'dimensions':list(image.size),
                         'y_sorted':False,'command_priority':255,'sprite_priority':3,'render_flags':35,
                         'source_record_offset':pointer,'source_record_sha256':sha(record_raw),'pieces':evidence})
    if len(rows)!=17: raise ValueError('Incomplete decoration frame set')
    return rows,images
