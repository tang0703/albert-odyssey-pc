"""Post-menu world: a disabled line window excludes no NBG3 pixels."""
import numpy as np
from event_pixel_reference import registers, dialogue_window, sha
from interaction_pixel_reference import Pixels as Previous

class Pixels(Previous):
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
            zero_window=all(regs[k]==0 for k in ('WCTLB','LWTA0U','LWTA0L','WPSY0','WPEY0'))
            if not zero_window:
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
