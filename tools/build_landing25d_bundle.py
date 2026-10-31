"""Build an isolated eleventh appearance bundle from approved imagegen art."""
from pathlib import Path
import argparse
import json
import hashlib
from PIL import Image
from character_hd_art import clean_alpha
from enhanced25d_projection import validate_art_grid

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'art/enhanced25d-landing/v1'
PROJECT=ROOT/'exploration-demo'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build(animation,output):
    if output.exists(): raise ValueError('Use a new output directory')
    approval=read(ART/'approval.json'); art=read(animation/'animation.json')
    if not approval['approved'] or art['frame_count']!=52 or art['approval_sha256']!=sha(ART/'approval.json'): raise ValueError('Approval identity differs')
    for name,row in art['files'].items():
        if sha(animation/name)!=row['sha256']: raise ValueError('Animation changed: '+name)
    pin=read(PROJECT/'enhanced25d-pin.json');dependencies=pin['dependencies']|{'enhanced25d':pin['manifest_sha256']}
    for name,value in dependencies.items():
        if sha(PROJECT/'generated'/name/'package.json')!=value: raise ValueError('Old bundle changed: '+name)
    layout=read(ART/'layout.json')
    if sha(ART/'layout.json')!=approval['layout_sha256']: raise ValueError('Approved composition changed')
    for axis,size in [('x',448),('y',256)]: validate_art_grid(layout['shell']['source_'+axis],layout['shell']['art_'+axis],size)
    layout['schema']='ao_pc_landing25d_layout_v1';layout['pending']=[]
    layout['foreground_rects']=[[0,228,448,28]]
    # Source-bound objects use source position + approved art offset, not fixed
    # screen coordinates. Absent objects cannot remain baked into the room.
    feet={'0':[272,160],'2':[256,192],'3':[256,112],'4':[288,112],'5':[288,192],'6':[144,112],'7':[320,80]}
    layout['dynamic_props']={};static=[]
    for row in layout['layers']:
        if row['file']=='chair-back-01.png': row['file']='chair-back-03.png'
        if row['source'].startswith('object:'):
            _,slot,index=row['source'].split(':');foot=feet[slot]
            layout['dynamic_props']['object_'+slot]={'file':row['file'],'offset':[row['rect'][0]-foot[0],row['rect'][1]-foot[1]],'size':row['rect'][2:],'preserve':row['preserve'],'image_index':int(index)}
        else: static.append(row)
    layout['layers']=static
    names={layout['shell']['file']}|{r['file'] for r in static}|{r['file'] for r in layout['dynamic_props'].values()}
    output.mkdir(parents=True);textures={};provenance={}
    for name in sorted(names):
        source=ART/'drafts'/name;im=Image.open(source).convert('RGBA')
        if name==layout['shell']['file']: cleanup={'enabled':False}
        else: im,cleanup=clean_alpha(im,{'min_alpha':16,'min_component_pixels':16})
        im.save(output/name);textures[name]={'dimensions':list(im.size),'visible_box':list(im.getchannel('A').getbbox())}
        provenance[name]={'source_file':source.relative_to(ART).as_posix(),'source_sha256':sha(source),'cleanup':cleanup}
    source=ART/'drafts/steam-eight-02.png';sheet=Image.open(source).convert('RGBA')
    for i in range(8):
        x,y=i%4,i//4;box=[round(x*sheet.width/4),round(y*sheet.height/2),round((x+1)*sheet.width/4),round((y+1)*sheet.height/2)]
        im,cleanup=clean_alpha(sheet.crop(box),{'min_alpha':16,'min_component_pixels':16})
        b=im.getchannel('A').getbbox()
        if not b or min(b[0],b[1],im.width-b[2],im.height-b[3])<3: raise ValueError('Steam crosses cell boundary')
        # Preserve relative size across phases, common base; never silhouette-fit.
        canvas=Image.new('RGBA',(512,512));canvas.paste(im,(round(256-im.width/2),round(448-400 if y==0 else 448-(818-box[1]))))
        name=f'steam-{i}.png';canvas.save(output/name)
        textures[name]={'dimensions':[512,512],'visible_box':[0,0,512,512]}
        provenance[name]={'source_file':source.relative_to(ART).as_posix(),'source_sha256':sha(source),'source_rect':box,'cleanup':cleanup}
    for d in ['down','left','right','up']:
        name=f'laia-{d}.png';(output/name).write_bytes((animation/f'atlases/{d}.png').read_bytes())
        textures[name]={'dimensions':[2048,2048],'visible_box':[0,0,2048,2048]}
    source_core=read(PROJECT/'generated/landing-event/core.json')
    selectors=source_core['actor_program']['sequences']
    if selectors!={'0':[1,3,4,0],'3':[1,6,0,0],'4':[12,3,4,12,4,4,12,3,4,12,5,4,0],'6':[12,3,0,12,4,0,12,3,0,12,5,0,0],'7':[12,6,0,12,7,0,12,6,0,12,8,0,0]}: raise ValueError('Unknown LAIA animation program')
    data={'schema':'ao_pc_landing25d_appearance_v1','scene_id':7,'layout':layout,'textures':textures,'frames':art['frames'],'phase':art['phase'],
      'source_sequences':selectors,'pose_mapping':{'3:0':'left','4:0':'left','5:0':'left','3:1':'right','4:1':'right','5:1':'right','6:0':'up','7:0':'up','8:0':'up'},
      'special_poses':[],'special_pose_evidence':'All nine observed image/mirror combinations are mapped; selector 7 remains animated even without translation.',
      'preload_required':True,'missing_policy':'reject','scene_policy':{'8':'enhanced25d','7':'enhanced25d-landing'},
      'approval_sha256':sha(ART/'approval.json'),'animation_manifest_sha256':sha(animation/'animation.json'),'provenance':provenance,'performance_tested':False}
    write(output/'appearance.json',data)
    files={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.iterdir())}
    write(output/'package.json',{'schema':'ao_pc_landing25d_bundle_v1','dependencies':dependencies,'files':files,'performance_tested':False})
    write(PROJECT/'landing25d-pin.json',{'schema':'ao_pc_landing25d_pin_v1','manifest_sha256':sha(output/'package.json'),'dependencies':dependencies,'files':sorted(files)})
    print(json.dumps({'frames':52,'textures':len(textures),'dependencies':len(dependencies),'performance_tested':False}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--animation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.animation,a.output)
