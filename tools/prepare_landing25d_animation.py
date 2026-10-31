"""Register complete imagegen drawings; never synthesize poses or alter anatomy."""
from pathlib import Path
import argparse
import hashlib
import json
from PIL import Image
from character_hd_art import clean_alpha, components, canonical_pose, normalize, preview, NAMES

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'art/enhanced25d-landing/v1'
DIRECTIONS = ['down', 'left', 'right', 'up']
ORDER = {
 'left': [('keys',0),('t2',0),('keys',1),('t2',1),('passing',0),('passing',1),('keys',2),('t2',2),('keys',3),('t2',3),('passing',2),('passing',3)],
 'right': [('keys',0),('t2',0),('keys',1),('t2',1),('passing',0),('passing',1),('keys',2),('t2',2),('keys',3),('t2',3),('passing',2),('passing',3)],
 'down': [('keys',0),('keys',1),('t2',0),('passing',2),('passing',3),('t2',3),('keys',2),('keys',3),('t2',2),('passing',0),('passing',1),('t2',1)],
 'up': [('keys',0),('keys',3),('t2',0),('passing',2),('passing',3),('t2',3),('keys',2),('keys',1),('t2',1),('passing',0),('passing',1),('t2',2)],
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def head_anchor(im):
    b=im.getchannel('A').getbbox(); h=b[3]-b[1]
    # Register the head, not a changing wing span or alternating leading toe.
    top=im.getchannel('A').crop((0,b[1],im.width,b[1]+round(h*.22))).getbbox()
    return (top[0]+top[2])/2,b,h

def prepare(output):
    if output.exists(): raise ValueError('Use a new candidate directory')
    approval=json.loads((ART/'approval.json').read_text(encoding='utf-8'))
    if approval['approved'] is not True: raise ValueError('W2 approval required')
    records=[]; images={}; cache={}; identities=set();sources={}
    for d in DIRECTIONS:
        idle_path=ART/approval['references'][d]['file']
        if sha(idle_path)!=approval['references'][d]['sha256']: raise ValueError('Approved idle changed')
        idle,ic=clean_alpha(Image.open(idle_path).convert('RGBA'),{'min_alpha':16,'min_component_pixels':16})
        hx,b,h=head_anchor(idle)
        feet=idle.getchannel('A').crop((0,b[3]-round(h*.06),idle.width,b[3])).getbbox()
        head_to_ground=((feet[0]+feet[2])/2-hx)/h
        for i in range(13):
            if i==12:
                path=idle_path; im=idle;cleanup=ic; rect=[0,0,im.width,im.height];cell=None
            else:
                kind,cell=ORDER[d][i];path=ART/'animation-sources'/f'{d}-{kind}.png'
                if path not in cache:
                    raw,cleanup=clean_alpha(Image.open(path).convert('RGBA'),{'min_alpha':16,'min_component_pixels':16})
                    figures=components(raw)
                    if len(figures)!=4: raise ValueError(f'Expected four separate figures: {path}: {len(figures)}')
                    figures.sort(key=lambda f:(int((f['bbox'][1]+f['bbox'][3])/2>=raw.height/2),f['bbox'][0]))
                    cache[path]=(raw,figures,cleanup)
                raw,figures,cleanup=cache[path];box=figures[cell]['bbox'];im=raw.crop(box)
                rect=[box[0],box[1],box[2]-box[0],box[3]-box[1]]
            hx,b,h=head_anchor(im);anchor=[hx+head_to_ground*h,b[3]]
            identity=canonical_pose(im)
            if identity in identities: raise ValueError('Repeated or reflected drawing')
            identities.add(identity)
            frame=normalize(im,anchor,400/h)
            name=f'frames/{d}-{NAMES[i]}.png';images[name]=frame
            source=path.relative_to(ART).as_posix();sources[source]={'sha256':sha(path)}
            records.append({'id':f'laia_25d/{d}/{NAMES[i]}','direction':d,'cell':i,
                'action':'idle' if i==12 else 'walk','kind':'idle' if i==12 else 'primary' if i%3==0 else 'transition',
                'file':name,'atlas':f'atlases/{d}.png','rect':[i%4*512,i//4*512,512,512],
                'ground_anchor':[256,448],'display_scale':.09,'source_file':source,'source_sha256':sha(path),
                'source_rect':rect,'source_pose_cell':cell,'source_anchor':anchor,'uniform_pose_scale':400/h,
                'alpha_cleanup':cleanup,'canonical_pose_sha256':identity,'anchor_reviewed':False,
                'registration':'Whole-pose uniform scaling; head registration with approved idle head-to-ground offset; no limb deformation'})
    output.mkdir(parents=True)
    for n in ['frames','atlases','previews']: (output/n).mkdir()
    for name,im in images.items(): im.save(output/name)
    for d in DIRECTIONS:
        frames=[images[f'frames/{d}-{n}.png'] for n in NAMES]
        atlas=Image.new('RGBA',(2048,2048))
        for i,im in enumerate(frames): atlas.paste(im,(i%4*512,i//4*512))
        atlas.save(output/f'atlases/{d}.png');preview(frames,d,output)
        gif=[]
        for im in frames[:12]:
            bg=Image.new('RGBA',(512,512),(24,28,34,255));bg.alpha_composite(im);gif.append(bg.convert('RGB'))
        gif[0].save(output/f'previews/{d}-walk.gif',save_all=True,append_images=gif[1:],duration=[70,60,70]*4,loop=0,disposal=2,optimize=False)
    files={p.relative_to(output).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file()}
    write(output/'animation.json',{'schema':'ao_pc_landing25d_animation_v1','approved':False,'runtime_ready':False,
       'approval_sha256':sha(ART/'approval.json'),'frame_count':52,'canvas':[512,512],
       'phase':{'cycle_updates':48,'source_pose_updates':12,'subpose_updates':4,'driver':'LAIA own selector/cursor/timer'},
       'sources':sources,'frames':records,'files':files,'pending':['visual loop review','runtime integration'],
       'down_direction':'art preview only; not observed in this event','performance_tested':False})
    print(json.dumps({'frames':52,'unique_drawings':len(identities),'output':str(output)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);prepare(p.parse_args().output)
