"""Additional bounded source actor-1 expression graphics for the stair event.

The old room extractor remains unchanged. Only the verified expression slot is
separated before calling it; unknown additional actors still fail that gate.
"""
import struct
from character_draw_order import (scene_from_snapshot, _memory, u16, u32, s16,
                                  bucket_order, priority_order)


def scene(high,low,*,camera_at_command_target=None):
    if len(high)!=0x100000 or len(low)!=0x100000:raise ValueError('Truncated event scene')
    raw=high[0xc87c8:0xc8838]
    active=bool(u16(raw,6)&0x8000)
    effect=None
    if active:
        if (u16(raw,8)!=0x80 or u16(raw,0xe)!=217 or u16(raw,0x10)!=0 or u16(raw,0x12)!=2
                or u16(raw,0x14)!=0 or u16(raw,0x16)!=0x23 or s16(raw,4)!=0
                or u16(raw,0x56)!=0 or raw[0x45]!=255
                or u32(raw,0x58)!=0x260e5a24 or u32(raw,0x60)!=0x260e8c48
                or u16(raw,0x34) not in (0,1,2,14,15)):
            raise ValueError('Expression actor outside source-confirmed subtype 3')
        effect=raw
    stripped=bytearray(high)
    struct.pack_into('>H',stripped,0xc87c8+6,u16(raw,6)&0x7fff)
    result=scene_from_snapshot(bytes(stripped),low,camera_at_command_target=camera_at_command_target,room_camera_scope=True)
    if effect is None:return result
    raw=effect;cam=result['camera_raw'];pointer=u32(raw,0x5c)
    if pointer!=u32(_memory(high,low,0x260e5a24+u16(raw,0x34)*4,4),0):
        raise ValueError('Expression pointer differs from source image table')
    count=u16(_memory(high,low,pointer,2),0)
    if not 1<=count<=4:raise ValueError('Unknown expression piece count')
    obj={'kind':'actor','slot':1,'id':'actor_1','world_xy_raw':[s16(raw,0),s16(raw,2)],
         'y_raw':s16(raw,2),'camera_y_raw':cam[1],'y_sorted':False,
         'render_flags':0x23,'record_address':pointer,'pieces':[]}
    table=u32(high,0x741e0)
    for i in range(count):
        x,y,attr=struct.unpack('>hhH',_memory(high,low,pointer+2+i*6,6))
        if attr&0xc000:raise ValueError('Unverified expression mirror')
        texture_id=217+(attr&255);tex=_memory(high,low,table+texture_id*10,10)
        width,height=(u16(tex,2)>>8)*8,u16(tex,2)&255
        if not width or not height:raise ValueError('Empty expression texture')
        origin=[(obj['world_xy_raw'][0]&~15)//16-cam[0]//16+x,
                (obj['world_xy_raw'][1]&~15)//16-cam[1]//16+y]
        obj['pieces'].append({'piece':i,'id':f'actor_1:{i}','offset':[x,y],'source_anchor':[-x,-y],
            'attributes':attr,'runtime_texture_id':texture_id,'texture_offset':u16(tex,0)*8,
            'width':width,'height':height,'screen_origin':origin,'flip_x':False,
            'colr':0x3020,'color_mode':0,'priority':100,'effective_priority':100})
    result['actors'].append(obj)
    order=bucket_order(result['objects'],result['actors'])
    lookup={(r['kind'],r['slot']):r for r in result['objects']+result['actors']}
    pieces=[p for item in order['unsorted']+order['sorted'] for p in lookup[(item['kind'],item['slot'])]['pieces']]
    ordered=priority_order(pieces,256)
    result.update(buckets=order,body_and_prop_order=[p['id'] for p in ordered],ordered_pieces=ordered)
    return result
