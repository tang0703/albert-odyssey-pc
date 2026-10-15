"""Decode source event sprites to a local diagnostic set, never screenshot crops."""
import argparse
import json
from pathlib import Path
from event_draw_order import scene
from inspect_event_capture import watched
from character_graphics import sha,MAP_SHA256,MAP_V1N_SHA256,PALETTE_SOURCE_OFFSET,PALETTE_CRAM_OFFSET
from character_draw_order import verify_source
from export_character_scene_props import decode_piece,compose_pieces
from pipeline import parse_v1n


def export(capture,output):
    workspace=Path(__file__).resolve().parents[2]
    sources={n:(workspace/'work/extract'/n).read_bytes() for n in ('MAP001.TWN','MAP001.V1N','TWN.BIN','0')}
    verify_source(sources['TWN.BIN'],sources['0'])
    if sha(sources['MAP001.TWN'])!=MAP_SHA256 or sha(sources['MAP001.V1N'])!=MAP_V1N_SHA256:raise ValueError('Changed event art source')
    manifest=json.loads((capture/'manifest.json').read_text(encoding='utf-8-sig'))
    records={r['path']:r for r in manifest['outputs']}
    def read(name):
        raw=(capture/name).read_bytes()
        if len(raw)!=records[name]['bytes'] or sha(raw)!=records[name]['sha256']:raise ValueError('Capture changed: '+name)
        return raw
    selected={}
    for line in read('frames.jsonl').decode().splitlines():
        row=json.loads(line)
        for kind,address,active_offset,image_offset in (('expression',0x060c87c8,6,0x34),('cirrus',0x060ca4c0,10,0x22)):
            raw=watched(row,address,112 if kind=='expression' else 60)
            index=int.from_bytes(raw[image_offset:image_offset+2],'big')
            if int.from_bytes(raw[active_offset:active_offset+2],'big')&0x8000 and (kind=='expression' or index==71):
                selected.setdefault((kind,index),row['frame'])
    if set(selected)!={('expression',n) for n in (0,1,2,14,15)}|{('cirrus',71)}:raise ValueError('Incomplete expression/Cirrus image coverage')
    textures=parse_v1n(sources['MAP001.V1N']);rows=[]
    output.mkdir(parents=True,exist_ok=True)
    for (kind,index),frame in sorted(selected.items()):
        prefix=f'frame-{frame:06d}/'
        high,low,vram,cram=(read(prefix+n) for n in ('wram-high.bin','wram-low.bin','vram1.bin','cram.bin'))
        regs=json.loads(read(prefix+'sample.json'))['vdp2'];snapshot=scene(high,low)
        obj=next(r for r in snapshot['actors' if kind=='expression' else 'objects'] if r['slot']==(1 if kind=='expression' else 6))
        pointer=obj['record_address']-0x260e0000+8;size=2+6*len(obj['pieces'])
        source_record=sources['MAP001.TWN'][pointer:pointer+size]
        if source_record!=high[obj['record_address']&0xfffff:(obj['record_address']&0xfffff)+size]:raise ValueError('Runtime image differs from MAP')
        pieces=[];bindings=[]
        for p in obj['pieces']:
            if p['color_mode']!=0 or p['flip_x']:raise ValueError('Unverified event texel mode')
            packed=vram[p['texture_offset']:p['texture_offset']+p['width']*p['height']//2]
            matches=[t for t in textures if t['width']==p['width'] and t['height']==p['height'] and t['bits_per_pixel']==4 and t['packed_sha256']==sha(packed)]
            if not matches:raise ValueError('Event texture has no source match')
            palette_offset=(1024+(p['colr']&1023))*2
            source_offset=PALETTE_SOURCE_OFFSET+palette_offset-PALETTE_CRAM_OFFSET
            if cram[palette_offset:palette_offset+32]!=sources['MAP001.TWN'][source_offset:source_offset+32]:raise ValueError('Event palette has no source match')
            image=decode_piece(matches[0]['payload'],p['width'],p['height'],4,p['colr'],cram,regs)
            pieces.append((image,tuple(p['offset'])))
            bindings.append({**p,'texture_sha256':sha(packed),'source_texture_offsets':[t['payload_offset'] for t in matches],
                'source_palette_offset':source_offset,'palette_sha256':sha(cram[palette_offset:palette_offset+32])})
        image,anchor=compose_pieces(pieces);name=f'{kind}-{index:02d}.png';image.save(output/name)
        rows.append({'id':f'{kind}_{index}','file':name,'sha256':sha((output/name).read_bytes()),'dimensions':list(image.size),
            'anchor':anchor,'sample_frame':frame,'source_record_offset':pointer,'source_record_sha256':sha(source_record),'pieces':bindings})
    result={'schema':'ao_pc_event_source_sprites_v1','source_binding_passed':True,'render_order_acceptance':False,
        'capture_manifest_sha256':sha((capture/'manifest.json').read_bytes()),'sources':{n:sha(b) for n,b in sources.items()},'sprites':rows}
    (output/'source-sprites.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=export(a.capture,a.out);print(json.dumps({'source_binding_passed':r['source_binding_passed'],'sprites':len(r['sprites'])}))
