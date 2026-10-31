"""Landing-event source pixel proof with exact source dialogue window exclusion."""
import numpy as np
import json
from pathlib import Path
from event_pixel_reference import Pixels as Base,registers,sha,sprite_code_rgba,dialogue_window
from character_draw_order import _matches
from export_character_scene_props import decode_piece
from transition_graphics import atlases

class Pixels(Base):
    def __init__(self,folder):
        super().__init__(folder)
        self.projections=[]
        self.bg,self.fg=map(np.array,atlases((Path(__file__).resolve().parents[2]/'work/extract/MAP001.TWN').read_bytes()))

    def add_draw(self,current,commands,end):
        if end is None:raise ValueError('World draw lacks VDP completion')
        regs=registers(end);cram=self.by_hash(end['cram_sha256'])
        # Decode unmodulated source colours; video scanout applies the source
        # RGB offset after composition, independently of sprite state delay.
        if regs['CLOFSL'] or regs['CCCTL'] & 67:raise ValueError('Unverified landing colour calculation')
        for key in ('COAR','COAG','COAB'):regs[key]=0
        cam=[n//16 for n in current['camera_raw']]
        x,y=cam[0]-512,cam[1]-1792
        if not 0<=x<=128 or not 0<=y<=32:raise ValueError('World camera outside verified atlas')
        predicted=self.bg[y:y+224,x:x+320].copy();front=self.fg[y:y+224,x:x+320]
        for piece in current['ordered_pieces']:
            match=[row for row in commands if _matches(piece,bytes.fromhex(row['command_hex']))]
            if len(match)!=1:raise ValueError('Ambiguous predicted texture command')
            digest=match[0]['texture']['sha256']
            if 'expected_texture_sha256' in piece and digest!=piece['expected_texture_sha256']:
                raise ValueError('Predicted landing player texture differs')
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
        if key in self.draws and not np.array_equal(self.draws[key]['image'],predicted):raise ValueError('Ambiguous landing framebuffer projection')
        self.draws.setdefault(key,{'image':predicted,'presented_at':end['event_index']})
        self.projections.append({'key':key,'presented_at':end['event_index'],'model_frame':current['model_frame'],'model_update':current['model_update']})

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
            config={k:regs[k] for k in ('WCTLB','LWTA0U','LWTA0L','WPSY0','WPEY0')}
            if regs['WCTLB'] in (0x308,0xa0a) and all(regs[k]==v for k,v in {'LWTA0U':0x8000,'LWTA0L':0x2000,'WPSY0':0,'WPEY0':223}.items()):
                name=f"frame-{video['frame']-1:06d}/vram2.bin"
                identity=self.records[name]['sha256']
                if identity not in self.window_cache:
                    self.window_cache[identity]=dialogue_window(self.read(name)[0x4000:0x4000+224*4])
                if self.window_cache[identity].any() and regs['WCTLB']!=0x308:
                    raise ValueError('Dialogue window pixels without enabled source window')
                ui|=self.window_cache[identity]
            elif any(config.values()):raise ValueError('Unknown landing-event window registers')
            actual_raw=self.read(f"frame-{video['frame']:06d}/video-rgba.bin")
            if sha(actual_raw)!=video['video_sha256']:raise ValueError('Source video changed between observers')
            actual=np.frombuffer(actual_raw,dtype=np.uint8).reshape(224,320,4)
            predicted=self.draws[key]['image'].copy()
            colour=json.loads(self.read(f"frame-{video['frame']-1:06d}/sample.json"))['vdp2']
            if colour['CLOFEN']!=95 or colour['CLOFSL']:raise ValueError('Unverified landing colour offset selection')
            rgb=[colour[k]-512 if colour[k]&256 else colour[k] for k in ('COAR','COAG','COAB')]
            if len(set(rgb))!=1 or not -255<=rgb[0]<=0:raise ValueError('Unknown landing fade colour')
            predicted[:,:,:3]=np.clip(predicted[:,:,:3].astype(np.int16)+rgb,0,255).astype(np.uint8)
            bad=np.any(predicted!=actual,axis=2)&~(shadow|ui)
            count=int(np.count_nonzero(bad))
            if count:
                yy,xx=map(int,np.argwhere(bad)[0])
                self.errors.append({'frame':video['frame'],'pixels':count,'first':[xx,yy],'expected':predicted[yy,xx].tolist(),'actual':actual[yy,xx].tolist(),'code':int(codes[yy,xx])})
            compared=int(np.count_nonzero(~(shadow|ui)));pixels+=compared
            shadow_count+=int(np.count_nonzero(shadow));ui_count+=int(np.count_nonzero(ui))
            candidates=[p for p in self.projections if p['key']==key and p['presented_at']<=video['event_index']]
            if not candidates:raise ValueError('No causal landing projection')
            projection=max(candidates,key=lambda p:p['presented_at'])
            self.frames.append({'frame':video['frame'],'camera':cam,'compared_pixels':compared,'unexplained_pixels':count,
                                'model_frame':projection['model_frame'],'model_update':projection['model_update'],
                                'display_delay_frames':video['frame']-projection['model_frame'],'rgb_offset':rgb})
        if (self.folder/'manifest.json').read_bytes()!=self.manifest_raw:raise ValueError('Pixel manifest changed during validation')
        return {'schema':'ao_pc_event_world_pixels_v1','passed':not self.errors and bool(self.frames),
            'capture_manifest_sha256':sha(self.manifest_raw),'frames':self.frames,'errors':self.errors,'inherited_frames':excluded,
            'compared_world_pixels':pixels,'excluded_shadow_pixels':shadow_count,'excluded_source_ui_pixels':ui_count,
            'source_texture_checks':self.texture_checks,'scope':'Continuously predicted landing world. Documented original shadow and exact source dialogue pixels excluded. No world region masking.'}
