"""Source-world pixel comparison linked by completed VDP framebuffer identity.

Only source UI palette banks and the already documented player shadow are
excluded. No actor/camera state is read from later RAM to render the prediction.
"""
import hashlib
import json
import struct
from pathlib import Path
import numpy as np
from PIL import Image
from character_graphics import (PlayerResource, MAP_V1N_SHA256, sha, sprite_code_rgba)
from character_draw_order import _matches
from export_character_scene_props import decode_piece
from pipeline import parse_v1n
from verify_character_capture import VDP2_ADDRESSES


def registers(row):
    raw=bytes.fromhex(row['vdp2_registers_be_hex'])
    return {key:int.from_bytes(raw[offset:offset+2],'big') for key,offset in VDP2_ADDRESSES.items()}


def dialogue_window(table):
    """Pinned NBG3 line-window 0, normal horizontal resolution (X divided by 2)."""
    if len(table)!=224*4:raise ValueError('Incomplete dialogue line window')
    mask=np.zeros((224,320),dtype=bool)
    for y in range(224):
        left,right=struct.unpack_from('>HH',table,y*4)
        if (left,right)==(640,642):continue
        if (left,right)!=(56,584) or not 12<=y<=83:raise ValueError('Unverified dialogue window extent')
        mask[y,left//2:right//2+1]=True
    return mask


class Pixels:
    def __init__(self,folder):
        self.folder=Path(folder)
        self.manifest_raw=(self.folder/'manifest.json').read_bytes()
        manifest=json.loads(self.manifest_raw.decode('utf-8-sig'))
        self.records={r['path']:r for r in manifest['outputs']}
        self.identities={}
        for name,r in self.records.items():
            if name.endswith(('/vdp1-fb0.bin','/vdp1-fb1.bin','/cram.bin')):
                self.identities.setdefault(r['sha256'],name)
        root=Path(__file__).resolve().parents[1]
        sources={name:(root.parent/'work/extract'/name).read_bytes() for name in ('PARTY0.PTY','TWN.BIN','MAP001.TWN','MAP001.V1N')}
        player=PlayerResource(sources['PARTY0.PTY'],sources['MAP001.TWN'],sources['TWN.BIN'])
        if sha(sources['MAP001.V1N'])!=MAP_V1N_SHA256:raise ValueError('Texture source changed')
        self.textures={r['packed_sha256']:r['payload'] for r in parse_v1n(sources['MAP001.V1N'])}
        self.textures.update({sha(t.indices):t.indices for t in player.textures.values()})
        # These existing atlases already have their own source-pixel gate. Bind
        # their bytes to the immutable fourth package before using the cache.
        package=root/'exploration-demo/generated/room'
        manifest_bytes=(package/'package.json').read_bytes()
        if sha(manifest_bytes)!='4f5871775e4ff5de364cb78ed6aab695bcca5e60b57be4977d01270c7ed3e8d2':raise ValueError('Room package changed')
        files=json.loads(manifest_bytes)['files']
        for name in ('background.png','foreground.png'):
            if sha((package/name).read_bytes())!=files[name]['sha256']:raise ValueError('Source atlas changed')
        self.bg=np.array(Image.open(package/'background.png'))
        self.fg=np.array(Image.open(package/'foreground.png'))
        self.seed_cram=self.read('frame-000000/cram.bin')
        self.cache={};self.window_cache={};self.draws={};self.videos=[];self.frames=[];self.errors=[];self.texture_checks=0

    def read(self,name):
        raw=(self.folder/name).read_bytes()
        record=self.records[name]
        if len(raw)!=record['bytes'] or sha(raw)!=record['sha256']:raise ValueError('Changed pixel evidence: '+name)
        return raw

    def by_hash(self,digest):
        if digest not in self.identities:raise ValueError('No synchronized full-sample payload for '+digest)
        return self.read(self.identities[digest])

    def add_draw(self,current,commands,end):
        if end is None:raise ValueError('World draw lacks VDP completion')
        regs=registers(end);cram=self.by_hash(end['cram_sha256'])
        cam=[n//16 for n in current['camera_raw']]
        x,y=cam[0]-512,cam[1]-1536
        if not 0<=x<=128 or not 0<=y<=32:raise ValueError('World camera outside verified atlas')
        predicted=self.bg[y:y+224,x:x+320].copy();front=self.fg[y:y+224,x:x+320]
        for piece in current['ordered_pieces']:
            match=[row for row in commands if _matches(piece,bytes.fromhex(row['command_hex']))]
            if len(match)!=1:raise ValueError('Ambiguous predicted texture command')
            digest=match[0]['texture']['sha256']
            if digest not in self.textures:raise ValueError('Texture not bound to original resource')
            bits=4 if piece['color_mode']==0 else 6
            offset=(1024+(piece['colr']&1023))*2;size=(1<<bits)*2
            if cram[offset:offset+size]!=self.seed_cram[offset:offset+size]:raise ValueError('World palette changed')
            key=(digest,piece['colr'],piece['flip_x'])
            if key not in self.cache:
                self.cache[key]=np.array(decode_piece(self.textures[digest],piece['width'],piece['height'],bits,piece['colr'],cram,regs,piece['flip_x']))
            image=self.cache[key];self.texture_checks+=1
            sx,sy=piece['screen_origin'];w,h=piece['width'],piece['height']
            l,t,r,b=max(0,sx),max(0,sy),min(320,sx+w),min(224,sy+h)
            if l>=r or t>=b:continue
            clipped=image[t-sy:b-sy,l-sx:r-sx];mask=clipped[:,:,3]!=0
            target=predicted[t:b,l:r];target[mask]=clipped[mask]
            if sprite_code_rgba(piece['colr']|1,cram,regs)[1]==2:
                cover=mask & (front[t:b,l:r,3]!=0);target[cover]=front[t:b,l:r][cover]
        digest=end['framebuffer_sha256'][end['draw_bank']]
        key=(digest,*cam)
        borders=[]
        for row in commands:
            words=struct.unpack('>16H',bytes.fromhex(row['command_hex']))
            if words[0]&15==2 and words[3]==0x72e0:borders.append(words[6:14])
        ui_bounds=None
        if borders:
            if len(borders)!=8:raise ValueError('Unknown original dialogue border population')
            xs=[v for q in borders for v in q[::2]];ys=[v for q in borders for v in q[1::2]]
            ui_bounds=[min(xs),min(ys),max(xs)+1,max(ys)+1]
            if ui_bounds[0]!=24 or ui_bounds[2]!=296 or not 8<=ui_bounds[1]<=ui_bounds[3]<=88:
                raise ValueError('Original dialogue border outside confirmed screen region')
        if key in self.draws and not np.array_equal(self.draws[key]['image'],predicted):raise ValueError('Ambiguous completed framebuffer projection')
        self.draws.setdefault(key,{'image':predicted,'ui_bounds':ui_bounds,'presented_at':end['event_index']})

    def finish(self):
        excluded=[];pixels=0;shadow_count=0;ui_count=0
        for video in self.videos:
            if video['frame']<=2:
                excluded.append({'frame':video['frame'],'reason':'Inherited source framebuffer before captured prediction'});continue
            regs=registers(video);cam=[regs[k] for k in ('SCXIN0','SCYIN0')]
            if cam!=[regs[k] for k in ('SCXIN1','SCYIN1')]:raise ValueError('World layers use different cameras')
            digest=video['framebuffer_sha256'][video['display_bank']]
            key=(digest,*cam)
            if key not in self.draws or self.draws[key]['presented_at']>video['event_index']:
                self.errors.append({'frame':video['frame'],'reason':'No predicted completed world framebuffer at scanout camera','camera':cam});continue
            codes=np.frombuffer(self.by_hash(digest),dtype='>u2').reshape(256,512)[:224,:320]
            shadow=(codes&0xffc0)==0x27c0
            ui=np.isin(codes&0xfff0,[0x72d0,0x72e0,0x72f0])
            if regs['WCTLB'] not in (0x308,0xa0a) or any(regs[k]!=v for k,v in {'LWTA0U':0x8000,'LWTA0L':0x2000,'WPSY0':0,'WPEY0':223}.items()):
                raise ValueError('Unverified source UI window configuration: '+str((video['frame'],{k:regs[k] for k in ('WCTLB','LWTA0U','LWTA0L','WPSY0','WPEY0')})))
            # Unlike VDP1 borders, the NBG3 fill is already present on the first
            # opening frame. Its exact scanline extent is in source VRAM2.
            name=f"frame-{video['frame']-1:06d}/vram2.bin";identity=self.records[name]['sha256']
            if identity not in self.window_cache:
                raw=self.read(name);self.window_cache[identity]=dialogue_window(raw[0x4000:0x4000+224*4])
            if self.window_cache[identity].any() and regs['WCTLB']!=0x308:raise ValueError('Dialogue mask lacks enabled source window')
            ui|=self.window_cache[identity]
            actual_raw=self.read(f"frame-{video['frame']:06d}/video-rgba.bin")
            if sha(actual_raw)!=video['video_sha256']:raise ValueError('Source video changed between observers')
            actual=np.frombuffer(actual_raw,dtype=np.uint8).reshape(224,320,4)
            predicted=self.draws[key]['image']
            bad=np.any(predicted!=actual,axis=2)&~(shadow|ui)
            count=int(np.count_nonzero(bad))
            if count:
                yy,xx=map(int,np.argwhere(bad)[0])
                self.errors.append({'frame':video['frame'],'pixels':count,'first':[xx,yy],'expected':predicted[yy,xx].tolist(),'actual':actual[yy,xx].tolist(),'code':int(codes[yy,xx])})
            compared=int(np.count_nonzero(~(shadow|ui)));pixels+=compared
            shadow_count+=int(np.count_nonzero(shadow));ui_count+=int(np.count_nonzero(ui))
            self.frames.append({'frame':video['frame'],'camera':cam,'compared_pixels':compared,'unexplained_pixels':count})
        if (self.folder/'manifest.json').read_bytes()!=self.manifest_raw:raise ValueError('Pixel manifest changed during validation')
        return {'schema':'ao_pc_event_world_pixels_v1','passed':not self.errors and bool(self.frames),
            'capture_manifest_sha256':sha(self.manifest_raw),'frames':self.frames,'errors':self.errors,'inherited_frames':excluded,
            'compared_world_pixels':pixels,'excluded_shadow_pixels':shadow_count,'excluded_source_ui_pixels':ui_count,
            'source_texture_checks':self.texture_checks,'scope':'Predicted world composition only. Exact NBG3 dialogue line-window pixels, source UI palette banks and shadow explicitly excluded.'}
