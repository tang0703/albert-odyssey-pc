"""Prepare measured art-review metadata; no image pixel rewriting or game mutation."""
import json
from pathlib import Path
from PIL import Image
from prepare_landing25d_review import ROOT, LOCAL, OUT, ART, read, sha, write, word
from enhanced25d_projection import validate_art_grid


def inspect(path, transparent=False):
    with Image.open(path) as image:
        box=(0,0,image.width,image.height)
        if image.mode=='RGBA':
            alpha=image.getchannel('A')
            box=alpha.point(lambda x:255 if x>=128 else 0).getbbox()
            assert box, path
            if transparent: assert alpha.histogram()[0]>0, path
        elif transparent: raise ValueError('Required transparent artwork: '+str(path))
        foot=[(box[0]+box[2])/2,box[3]]
        if transparent and ('laia-' in path.name or 'idle' in path.name):
            bottom=alpha.crop((box[0],box[3]-max(1,int((box[3]-box[1])*0.06)),box[2],box[3]))
            feet=bottom.point(lambda x:255 if x>=128 else 0).getbbox()
            assert feet,path
            foot[0]=box[0]+(feet[0]+feet[2])/2
        return {'path':str(path),'sha256':sha(path),'size':list(image.size),'box':list(box),'foot':foot}


def main():
    data=read(OUT/'w1-inventory.json')
    layout=read(ART/'layout.json')
    for axis,extent in [('x',448),('y',256)]:
        validate_art_grid(layout['shell']['source_'+axis],layout['shell']['art_'+axis],extent)
    art={p.name:inspect(p,transparent=p.name!='room-shell-01.png') for p in sorted((ART/'drafts').glob('*.png'))}
    for name in [layout['shell']['file'],*[r['file'] for r in layout['layers']],*['laia-'+d+'-01.png' for d in ['down','left','right','up']]]:
        assert name in art,name
    for name,row in art.items():
        prompt=ART/'drafts'/(Path(name).stem+'.prompt.txt')
        assert prompt.is_file(),name
        row['prompt_sha256']=sha(prompt)
    sample=read(LOCAL/'landing-event/reference-equip.json')['post_commit'][600]['expected']
    positions={name:[word(sample[key],0)/16-512,word(sample[key],2)/16-1792] for name,key in [('player','player'),('laia','arrival_actor')]}
    result={'schema':'ao_pc_landing25d_review_v1','runtime_approved':False,'layout':layout,'art':art,
        'player':inspect(ROOT/'art/enhanced25d/v1/animation-candidate-03/frames/down-idle.png',True),
        'player_room':inspect(ROOT/'art/enhanced25d/v1/animation-candidate-03/frames/left-idle.png',True),
        'source_background':inspect(OUT/'source-room-objects.png'),'source_contact':inspect(OUT/'source-contact.png'),
        'source_laia':inspect(LOCAL/'landing-event/actor-50-03-1.png'),
        'routes':data['routes'],'cells':read(LOCAL/'landing-event/core.json')['landing_query_indices'],
        'sample_positions':positions,'sample_reference':'reference-equip.json post_commit[600]',
        'performance_tested':False}
    write(OUT/'review-data.json',result)
    provenance={'schema':'ao_pc_landing25d_art_provenance_v1','tool':'built-in image_gen','review_status':'pending_user_W2',
        'art_files':{name:{k:v for k,v in row.items() if k!='path'} for name,row in art.items()},
        'layout_sha256':sha(ART/'layout.json'),'reference_sources':['local source-contact.png','transition/background.png','enhanced25d/v1/references/approved-room.png','enhanced25d/v1/drafts/down-idle-01.png'],
        'pixel_editing':'None: raw outputs retained; Godot crops and scales for review only.',
        'performance_tested':False,'animation_production_started':False}
    write(ART/'provenance.json',provenance)
    print(json.dumps({'art_files':len(art),'positions':positions,'source_bindings':len(data['source_identities']),'runtime_approved':False}))


if __name__=='__main__': main()
