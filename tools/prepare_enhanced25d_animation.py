"""Mechanical extraction of imagegen-drawn poses; never synthesizes inbetweens.

The raw 2x2 sheets and approved idle remain immutable. Each whole pose is uniformly
scaled to the approved visible height; no limb deformation or pose synthesis. Review output is
explicitly a candidate, not a visual or gameplay acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from character_hd_art import (DIRECTIONS, NAMES, ANCHOR, PHASE, clean_alpha, components,
                              inspect_cell, canonical_pose, normalize, preview)

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'art/enhanced25d/v1'
ORDER = {
    'down': [('keys',0),('t2',3),('t1',3),('keys',3),('t2',0),('t1',1),('keys',2),('t2',1),('t1',0),('keys',1),('t2',2),('t1',2)],
    'up': [('keys',0),('t2',1),('t2',2),('keys',3),('t1',3),('t1',2),('keys',2),('t2',3),('t1',1),('keys',1),('t2',0),('t1',0)],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def prepare(output: Path):
    if output.exists():
        raise ValueError('Use a new output directory; candidates are immutable')
    approval = json.loads((ART/'approval.json').read_text(encoding='utf-8'))
    if approval['approved'] is not True:
        raise ValueError('Four-direction approval is required')
    records, images, identities, sources, sheets = [], {}, {}, {}, {}
    for direction in DIRECTIONS:
        cells = []
        for index in range(13):
            if index == 12:
                path = ART/approval['references'][direction]['file']
                if sha(path) != approval['references'][direction]['sha256']:
                    raise ValueError('Approved idle changed')
                with Image.open(path) as raw:
                    image = raw.convert('RGBA')
                rect = [0, 0, image.width, image.height]
                # The idle is a full sheet-sized single figure; walk cells use
                # half-sheet resolution. This is not per-pose silhouette fit.
                resolution_scale = 627 / image.width
                image = image.resize((627, round(image.height*resolution_scale)), Image.Resampling.LANCZOS)
            else:
                key, sub = divmod(index, 3)
                kind = ['keys','t1','t2'][sub]
                kind,key = ORDER.get(direction, [(['keys','t1','t2'][i%3],i//3) for i in range(12)])[index]
                path = ART/'animation-sources'/f'{direction}-{kind}.png'
                if path not in sheets:
                    with Image.open(path) as raw:
                        if raw.mode != 'RGBA' or raw.width % 2 or raw.height % 2:
                            raise ValueError('Expected even RGBA 2x2 sheet: '+str(path))
                        clean, sheet_cleanup = clean_alpha(raw, {'min_alpha':16,'min_component_pixels':16})
                    figures = components(clean)
                    if len(figures) != 4:
                        raise ValueError('Exactly four separate drawn silhouettes required: '+str(path))
                    figures.sort(key=lambda f: (int((f['bbox'][1]+f['bbox'][3])/2 >= clean.height/2),f['bbox'][0]))
                    sheets[path] = (clean,figures,sheet_cleanup)
                clean,figures,sheet_cleanup = sheets[path]
                box = figures[key]['bbox']
                # Generated figures may extend across the mathematical halfway
                # line. Extract their complete disconnected silhouettes, never
                # slice a boot to force the production sheet onto a rigid grid.
                image = clean.crop(box)
                rect = [box[0],box[1],box[2]-box[0],box[3]-box[1]]
                resolution_scale = 1254 / clean.width
                if resolution_scale != 1:
                    image = image.resize(tuple(round(n*resolution_scale) for n in image.size),Image.Resampling.LANCZOS)
                padded = Image.new('RGBA',(image.width+16,image.height+16))
                padded.paste(image,(8,8)); image = padded
            image, cleanup = clean_alpha(image, {'min_alpha':16,'min_component_pixels':16})
            details = inspect_cell(image)
            identity = canonical_pose(image)
            if identity in identities:
                raise ValueError('Copied or reflected pose: '+str(identities[identity]))
            identities[identity] = [direction,index]
            box = details['alpha_bbox']
            # Body-center registration avoids following the alternating toe.
            # It remains a measured candidate pending animation inspection.
            source_anchor = [(box[0]+box[2])/2, box[3]]
            head_box = image.getchannel('A').crop((0,box[1],image.width,box[1]+round((box[3]-box[1])*0.35))).getbbox()
            record = {'id':f'map001_player_25d/{direction}/{NAMES[index]}',
                      'direction':direction,'cell':index,'action':'idle' if index==12 else 'walk',
                      'kind':'idle' if index==12 else 'primary' if index%3==0 else 'transition',
                      'file':f'frames/{direction}-{NAMES[index]}.png',
                      'atlas':f'atlases/{direction}.png','rect':[index%4*512,index//4*512,512,512],
                      'ground_anchor':ANCHOR,'source_file':path.relative_to(ART).as_posix(),
                      'source_sha256':sha(path),'source_rect':rect,'resolution_scale':resolution_scale,
                      'source_anchor':source_anchor,'alpha_cleanup':cleanup,
                      'head_width':head_box[2]-head_box[0],
                      'source_pose_cell':key if index != 12 else None,
                      'sheet_alpha_cleanup':sheet_cleanup if index != 12 else None,
                      'anchor_reviewed':False,'canonical_pose_sha256':identity}
            sources[record['source_file']] = {'sha256':sha(path)}
            cells.append((image,record,details))
        for image,record,detail in cells:
            scale = 400/(detail['alpha_bbox'][3]-detail['alpha_bbox'][1])
            rendered = normalize(image,record['source_anchor'],scale)
            record['uniform_pose_scale'] = scale
            record['registration'] = 'Whole-pose uniform scale to 36 world units, bbox-center ground anchor; no anatomical warp'
            record['display_scale'] = 36/400
            record['sha256_rgba'] = hashlib.sha256(rendered.tobytes()).hexdigest()
            images[record['file']] = rendered
            records.append(record)
    output.mkdir(parents=True)
    for name in ['frames','atlases','previews']:
        (output/name).mkdir()
    for name,image in images.items():
        image.save(output/name)
    for direction in DIRECTIONS:
        frames = [images[f'frames/{direction}-{name}.png'] for name in NAMES]
        atlas = Image.new('RGBA',(2048,2048))
        for index,frame in enumerate(frames):
            atlas.paste(frame,(index%4*512,index//4*512))
        atlas.save(output/f'atlases/{direction}.png')
        preview(frames,direction,output)
    files = {p.relative_to(output).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size}
             for p in sorted(output.rglob('*')) if p.is_file()}
    result = {'schema':'ao_pc_25d_animation_candidate_v1','approved':False,
              'approval_sha256':sha(ART/'approval.json'),'generation_method':'built-in imagegen',
              'phase':PHASE,'frame_count':len(records),'canvas':[512,512],
              'runtime_ready':False,'pending':['loop continuity','anchor review','runtime integration'],
              'sources':sources,'frames':records,'files':files}
    write(output/'animation.json',result)
    return {'output':str(output),'frames':len(records),'unique_drawings':len(identities),
            'atlases':4,'visual_acceptance':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(prepare(parser.parse_args().output),ensure_ascii=False))
