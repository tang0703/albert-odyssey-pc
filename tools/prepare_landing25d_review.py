"""Source inventory and diagnostic contact sheets; never modifies source/art images."""
import base64
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'exploration-demo/generated'
OUT = ROOT / 'reports/enhanced25d-landing'
ART = ROOT / 'art/enhanced25d-landing/v1'


def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, d): p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def word(raw, offset): return int.from_bytes(bytes.fromhex(raw)[offset:offset+2], 'big')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    pin = read(ROOT/'exploration-demo/enhanced25d-pin.json')
    identities = dict(pin['dependencies'], enhanced25d=pin['manifest_sha256'])
    checked = 0
    for name, identity in identities.items():
        folder = LOCAL/name
        assert sha(folder/'package.json') == identity, name
        for file, row in read(folder/'package.json')['files'].items():
            assert sha(folder/file) == row['sha256'], (name, file)
            checked += 1
    core = read(LOCAL/'landing-event/core.json')
    visuals = read(LOCAL/'landing-event/visuals.json')
    props = read(LOCAL/'transition/visuals.json')
    assert visuals['origin'] == [512,1792] and visuals['size'] == [448,256]
    assert len(core['landing_query_indices']) == 98
    sequences = core['actor_program']['sequences']
    assert all(sum(sequences[k][:-1:3]) == 48 for k in ['4','6','7'])
    actors = defaultdict(Counter)
    object_images = defaultdict(set)
    routes = []
    projection_checks = 0
    for file in sorted((LOCAL/'landing-event').glob('reference-*.json')):
        points, npc_points = [], []
        reference = read(file)
        for row in reference['post_commit']:
            state = row['expected']
            if int(state['scene']) != 7: continue
            npc = state['arrival_actor']
            if not npc: continue
            key = f"{word(npc,0x34)}:{word(npc,0x14)&1}"
            actors[key][str(word(npc,0x36))] += 1
            for slot, raw in enumerate(state['objects']): object_images[slot].add(word(raw,0x22))
            for raw, target in [(state['player'], points),(npc,npc_points)]:
                point = [word(raw,0)/16-512,word(raw,2)/16-1792]
                if not target or target[-1] != point: target.append(point)
                for width,height in [(1920,1080),(2560,1440),(3840,2160)]:
                    scale = min(width/448,height/256)
                    offset = [(width-448*scale)/2,(height-256*scale)/2]
                    mapped = [point[i]*scale+offset[i] for i in range(2)]
                    recovered = [(mapped[i]-offset[i])/scale for i in range(2)]
                    assert max(abs(a-b) for a,b in zip(point,recovered)) < 1e-8
                    projection_checks += 1
        routes.append({'id':file.stem, 'sha256':sha(file), 'player':points,'laia':npc_points})
    inventory = []
    for folder, data in [('transition',props),('landing-event',visuals)]:
        for frame in data['frames']:
            if folder == 'transition' and frame['kind'] != 'prop': continue
            if folder == 'transition' and frame['source_kind'] != 'object': continue
            point = [frame['world_xy_raw'][i]/16-[512,1792][i] for i in range(2)]
            inventory.append({'id':frame['id'],'source_file':folder+'/'+frame['file'],
                'sha256':sha(LOCAL/folder/frame['file']),'image_index':frame['image_index'],
                'flip_x':frame.get('flip_x',False),'anchor':frame['anchor'],
                'dimensions':frame['dimensions'],'local_foot':point,
                'source_priority':frame['sprite_priority'],'replacement_status':'pending_W2_W3'})
    # Diagnostic inspection only: nearest-neighbour enlarged original pixels, labelled.
    board = Image.new('RGB',(1200,((len(inventory)+5)//6)*230),(30,39,43))
    draw = ImageDraw.Draw(board)
    for i,frame in enumerate(inventory):
        x,y=(i%6)*200,(i//6)*230
        image = Image.open(LOCAL/frame['source_file']).convert('RGBA')
        image = image.resize((image.width*4,image.height*4),Image.Resampling.NEAREST)
        # Keep complete large furniture within its cell; never alter the source file.
        if image.width>190 or image.height>180: image.thumbnail((190,180),Image.Resampling.NEAREST)
        board.paste(image,(x+(200-image.width)//2,y+8),image)
        draw.text((x+4,y+190),frame['source_file'].split('/')[-1],fill='white')
        draw.text((x+4,y+206),str(frame['local_foot']),fill='lightgray')
    board.save(OUT/'source-contact.png')
    bg=Image.open(LOCAL/'transition/background.png').convert('RGBA')
    for frame in props['frames']:
        if frame['source_kind']!='object' or frame['image_index']!=min(object_images[frame['slot']]): continue
        image=Image.open(LOCAL/'transition'/frame['file']).convert('RGBA')
        point=[int(frame['world_xy_raw'][i]/16-[512,1792][i]-frame['anchor'][i]) for i in range(2)]
        bg.alpha_composite(image,tuple(point))
    bg.save(OUT/'source-room-objects.png')
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1792" height="1024" viewBox="0 0 448 256">',
         '<image width="448" height="256" href="data:image/png;base64,'+base64.b64encode((OUT/'source-room-objects.png').read_bytes()).decode()+'"/>']
    for index in core['landing_query_indices']:
        x,y=(index%256)*8-512,(index//256)*8-1792
        svg.append(f'<rect x="{x}" y="{y}" width="8" height="8" fill="none" stroke="#37dcc1" stroke-width=".4"/>')
    for route in routes:
        for key,color in [('player','#ffd863'),('laia','#e998fc')]:
            svg.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in route[key])+f'" stroke="{color}" fill="none" stroke-width=".65"/>')
    svg.append('</svg>')
    (OUT/'source-coverage.svg').write_text('\n'.join(svg),encoding='utf-8')
    result={'schema':'ao_pc_landing25d_w1_v1','source_identities':identities,'source_files_verified':checked,
        'origin':[512,1792],'size':[448,256],'verified_query_count':98,
        'projection_checks':projection_checks,'source_sequences':sequences,'walk_cycle_updates':48,
        'observed_actor_keys':dict(actors),'observed_object_images':{str(k):sorted(v) for k,v in object_images.items()},
        'inventory':inventory,'routes':routes,'performance_tested':False,
        'scope':'Existing source inventory and coordinate precision only; no new source capture or runtime acceptance.',
        'art_approved':False,'animation_production_started':False}
    write(OUT/'w1-inventory.json',result)
    write(ART/'source-binding.json',{k:result[k] for k in ['schema','source_identities','origin','size','verified_query_count','walk_cycle_updates','source_sequences','observed_actor_keys','observed_object_images','inventory','performance_tested','scope']})
    print(json.dumps({k:result[k] for k in ['source_files_verified','projection_checks','verified_query_count','walk_cycle_updates','observed_actor_keys','observed_object_images']}))


if __name__=='__main__': main()
