"""Build a closed, source-bound presentation-only bundle, never modify nine inputs."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from character_hd_art import clean_alpha
from enhanced25d_projection import validate_art_grid

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'art/enhanced25d/v1'
PROJECT=ROOT/'exploration-demo'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build(animation,output):
    if output.exists(): raise ValueError('New bundle output required')
    approval=read(ART/'approval.json')
    if not approval['approved']: raise ValueError('Unapproved design')
    pin=read(PROJECT/'landing-event-pin.json')
    dependencies=pin['dependencies']|{'landing-event':pin['manifest_sha256']}
    for name,value in dependencies.items():
        if sha(PROJECT/'generated'/name/'package.json')!=value: raise ValueError('Changed source: '+name)
    art=read(animation/'animation.json')
    if art['frame_count']!=52 or art['approval_sha256']!=sha(ART/'approval.json'): raise ValueError('Wrong animation approval')
    for name,row in art['files'].items():
        if sha(animation/name)!=row['sha256']: raise ValueError('Changed animation: '+name)
    layout=read(ART/'layout.json')
    for axis,size in [('x',448),('y',256)]: validate_art_grid(layout['shell']['source_'+axis],layout['shell']['art_'+axis],size)
    # This is candidate registration data; acceptance is reported separately.
    layout['runtime_approved']=False
    layout['dynamic_props']={
        'object_0':{'file':'stool-01.png','offset':[2,5],'size':[22,19]},
        'object_4':{'file':'table-prop-04.png','offset':[1,5],'size':[11,19]},
        'object_5':{'file':'table-prop-05.png','offset':[0,4],'size':[14,12]},
    }
    layout['foreground_rects']=[[0,228,448,28]]
    layout['cirrus']={'file':'cirrus-46.png','image_index':46,'source_slot':6}
    names={layout['shell']['file'],'cirrus-46.png'}|{r['file'] for r in layout['layers']}|{r['file'] for r in layout['dynamic_props'].values()}
    output.mkdir(parents=True)
    textures={};provenance={}
    for name in sorted(names):
        source=ART/'drafts'/name
        with Image.open(source) as raw:
            image=raw.convert('RGBA')
        if name==layout['shell']['file']:
            cleaned=image;cleanup={'enabled':False}
        else: cleaned,cleanup=clean_alpha(image,{'min_alpha':16,'min_component_pixels':16})
        box=cleaned.getchannel('A').getbbox()
        if box is None: raise ValueError('Empty art')
        cleaned.save(output/name)
        textures[name]={'file':name,'dimensions':list(cleaned.size),'visible_box':list(box)}
        provenance[name]={'source_file':source.relative_to(ART).as_posix(),'source_sha256':sha(source),'cleanup':cleanup}
    for direction in ['down','left','right','up']:
        source=animation/'atlases'/f'{direction}.png';target=output/f'player-{direction}.png'
        target.write_bytes(source.read_bytes())
        textures[target.name]={'file':target.name,'dimensions':[2048,2048],'visible_box':[0,0,2048,2048]}
    data={'schema':'ao_pc_enhanced25d_appearance_v1','candidate':True,'scene_id':8,
          'fallback_policy':{'enhanced25d_scene7':'hd','missing_files':'reject'},
          'modes':['enhanced25d','hd','original','marker'],'layout':layout,'textures':textures,
          'frames':art['frames'],'phase':art['phase'],'provenance':provenance,
          'approval_sha256':sha(ART/'approval.json'),'animation_manifest_sha256':sha(animation/'animation.json'),
          'performance_tested':False,'special_poses':'verified_source_pixels',
          'contact_shadow':'new_artistic_effect_not_original_shadow_restoration'}
    write(output/'appearance.json',data)
    files={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.iterdir())}
    package={'schema':'ao_pc_enhanced25d_bundle_v1','dependencies':dependencies,'files':files,'candidate':True,'performance_tested':False}
    write(output/'package.json',package)
    write(PROJECT/'enhanced25d-pin.json',{'schema':'ao_pc_enhanced25d_pin_v1','manifest_sha256':sha(output/'package.json'),'dependencies':dependencies,'files':sorted(files),'candidate':True})
    return {'output':str(output),'textures':len(textures),'frames':len(art['frames']),'dependencies':len(dependencies),'performance_tested':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--animation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.animation,a.output)))
