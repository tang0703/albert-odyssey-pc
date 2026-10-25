"""Decode pickup poses and sparkle from source texture records, never crops."""
import argparse
import json
from pathlib import Path
from interaction_draw_order import scene
from inspect_event_capture import watched
from character_graphics import PlayerResource, sha, MAP_V1N_SHA256, PALETTE_SOURCE_OFFSET, PALETTE_CRAM_OFFSET
from character_draw_order import verify_source
from export_character_scene_props import decode_piece, compose_pieces
from pipeline import parse_v1n


def export(capture, output):
    extracted=Path(__file__).resolve().parents[2]/'work/extract'
    sources={n:(extracted/n).read_bytes() for n in ('PARTY0.PTY','MAP001.TWN','MAP001.V1N','TWN.BIN','0')}
    player=PlayerResource(sources['PARTY0.PTY'],sources['MAP001.TWN'],sources['TWN.BIN'])
    verify_source(sources['TWN.BIN'],sources['0'])
    if sha(sources['MAP001.V1N'])!=MAP_V1N_SHA256:raise ValueError('Texture source changed')
    manifest_raw=(capture/'manifest.json').read_bytes()
    manifest=json.loads(manifest_raw.decode('utf-8-sig'))
    if manifest.get('inputs_unchanged') is not True:raise ValueError('Incomplete capture')
    records={r['path']:r for r in manifest['outputs']}
    def read(name):
        raw=(capture/name).read_bytes()
        if len(raw)!=records[name]['bytes'] or sha(raw)!=records[name]['sha256']:raise ValueError('Changed captured resource')
        return raw
    selected={}
    for line in read('frames.jsonl').decode().splitlines():
        row=json.loads(line)
        for kind,address in (('pickup',0x060c8758),('spark',0x060c87c8)):
            raw=watched(row,address,112)
            image=int.from_bytes(raw[0x34:0x36],'big')
            allowed=image in range(35,39) if kind=='pickup' else image in (*range(32,43),44) and int.from_bytes(raw[0x60:0x64],'big')==0x260e8b50
            if allowed and int.from_bytes(raw[6:8],'big')&0x8000:
                selected.setdefault((kind,image),[]).append(row['frame'])
    if set(selected)!={('pickup',i) for i in range(35,39)}|{('spark',i) for i in (*range(32,43),44)}:
        raise ValueError('Incomplete pickup/spark coverage')
    textures=parse_v1n(sources['MAP001.V1N'])
    rows=[];output.mkdir(parents=True,exist_ok=True)
    for (kind,index),candidates in sorted(selected.items()):
        frame=candidates[0]
        # An actor's cache can advance before its DMA texture upload. Choose
        # a source snapshot whose complete upload matches that source image.
        if kind=='pickup':
            matched=False
            for candidate in candidates:
                prefix=f'frame-{candidate:06d}/'
                if prefix+'wram-high.bin' not in records:continue
                high,low,vram=(read(prefix+n) for n in ('wram-high.bin','wram-low.bin','vram1.bin'))
                obj=next(a for a in scene(high,low,room_camera_scope=True)['actors'] if a['slot']==0)
                image=player.image(index)
                matches=[]
                for p in obj['pieces']:
                    texture=player.textures[image['pieces'][p['piece']]['texture_index']]
                    packed=vram[p['texture_offset']:p['texture_offset']+p['width']*p['height']]
                    matches.append((texture.width,texture.height,texture.indices)==(p['width'],p['height'],packed))
                if all(matches):frame=candidate;matched=True;break
            if not matched:raise ValueError('No completed source texture upload for pickup pose')
        prefix=f'frame-{frame:06d}/'
        high,low,vram,cram=(read(prefix+n) for n in ('wram-high.bin','wram-low.bin','vram1.bin','cram.bin'))
        regs=json.loads(read(prefix+'sample.json'))['vdp2']
        obj=next(a for a in scene(high,low,room_camera_scope=True)['actors'] if a['slot']==(0 if kind=='pickup' else 1))
        pointer=obj['record_address'];size=2+len(obj['pieces'])*6
        if kind=='pickup':
            source_record=player.at_pointer(pointer,size)
            actual=low[(pointer&0xfffff):(pointer&0xfffff)+size]
            image=player.image(index)
        else:
            offset=pointer-0x260e0000+8
            source_record=sources['MAP001.TWN'][offset:offset+size]
            actual=high[pointer&0xfffff:(pointer&0xfffff)+size]
        if source_record!=actual:raise ValueError('Runtime image differs from source record')
        pieces=[];bindings=[]
        for piece in obj['pieces']:
            bits=4 if piece['color_mode']==0 else 6
            byte_count=piece['width']*piece['height']//(2 if bits==4 else 1)
            packed=vram[piece['texture_offset']:piece['texture_offset']+byte_count]
            if kind=='pickup':
                texture=player.textures[image['pieces'][piece['piece']]['texture_index']]
                if (texture.width,texture.height,texture.indices)!=(piece['width'],piece['height'],packed):
                    raise ValueError('Pickup texture upload differs from source')
                indices=texture.indices;origins=[texture.source_offset]
            else:
                matches=[t for t in textures if t['width']==piece['width'] and t['height']==piece['height'] and t['bits_per_pixel']==4 and t['packed_sha256']==sha(packed)]
                if not matches:raise ValueError('Spark texture is not source-bound')
                indices=matches[0]['payload'];origins=[t['payload_offset'] for t in matches]
            palette_offset=(1024+(piece['colr']&1023))*2
            source_offset=PALETTE_SOURCE_OFFSET+palette_offset-PALETTE_CRAM_OFFSET
            palette=cram[palette_offset:palette_offset+(1<<bits)*2]
            if palette!=sources['MAP001.TWN'][source_offset:source_offset+len(palette)]:raise ValueError('Palette differs from source')
            decoded=decode_piece(indices,piece['width'],piece['height'],bits,piece['colr'],cram,regs,piece['flip_x'])
            pieces.append((decoded,tuple(piece['offset'])))
            bindings.append({**piece,'source_texture_offsets':origins,'texture_sha256':sha(packed),
                             'source_palette_offset':source_offset,'palette_sha256':sha(palette)})
        image,anchor=compose_pieces(pieces);name=f'{kind}-{index:02d}.png';image.save(output/name)
        rows.append({'id':f'{kind}_{index}','file':name,'sha256':sha((output/name).read_bytes()),
            'dimensions':list(image.size),'anchor':anchor,'sample_frame':frame,'source_record_address':pointer,
            'source_record_sha256':sha(source_record),'pieces':bindings})
    result={'schema':'ao_pc_interaction_source_sprites_v1','source_binding_passed':True,'render_order_acceptance':False,
            'capture_manifest_sha256':sha(manifest_raw),'sources':{n:sha(raw) for n,raw in sources.items()},'sprites':rows}
    (output/'source-sprites.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=export(a.capture,a.out);print(json.dumps({'sprites':len(r['sprites']),'source_binding_passed':r['source_binding_passed']}))
