"""Read-only image inspection + local review data. Does not edit artwork pixels."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from enhanced25d_projection import project_raw, inverse_raw, validate_art_grid

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'art/enhanced25d/v1'
LOCAL = ROOT / 'exploration-demo/generated'
OUT = ROOT / 'reports/enhanced25d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def inspect(path):
    with Image.open(path) as image:
        result = {'file':str(path), 'sha256':sha(path), 'dimensions':list(image.size)}
        if image.mode == 'RGBA':
            alpha = image.getchannel('A')
            # Ignore faint generation noise for measurement only. The image is
            # retained byte-identically; V3 owns final transparent-edge cleanup.
            box = alpha.point(lambda value:255 if value >= 128 else 0).getbbox()
            if box is None:
                raise ValueError('Missing character/furniture alpha: '+str(path))
            result['visible_box'] = list(box)
            result['transparent_pixels'] = alpha.histogram()[0]
        else:
            result['visible_box'] = [0,0,image.width,image.height]
        return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pins = read(ROOT/'exploration-demo/landing-event-pin.json')
    expected = dict(pins['dependencies'])
    expected['landing-event'] = pins['manifest_sha256']
    verified = {}
    for name, identity in expected.items():
        actual = sha(LOCAL/name/'package.json')
        if actual != identity: raise ValueError('Changed old source package: '+name)
        verified[name] = actual
    room = read(LOCAL/'room/room.json')
    layout = read(ART/'layout.json')
    assert layout['origin'] == [512,1536] and layout['dimensions'] == [448,256]
    assert layout['runtime_approved'] is False
    for axis, extent in [('x',448),('y',256)]:
        validate_art_grid(layout['shell']['source_'+axis],layout['shell']['art_'+axis],extent)
    textures = {p.name:inspect(p) for p in sorted((ART/'drafts').glob('*.png'))}
    for name in [layout['shell']['file']] + [row['file'] for row in layout['layers']] + [d+'-idle-01.png' for d in ['down','left','right','up']]:
        if name not in textures: raise ValueError('Missing review art: '+name)
        if name != layout['shell']['file'] and textures[name].get('transparent_pixels',0) == 0:
            raise ValueError('Missing transparent art background: '+name)
    props = read(LOCAL/'character/layers.json')['props']
    for prop in props:
        prop['texture'] = inspect(LOCAL/'character'/prop['file'])
    routes=[]; comparisons=0; max_error=0.0
    for trace in room['traces']:
        points=[]
        for update in trace['updates']:
            state=update['expected']; raw=(state['x_word'],state['y_word'])
            # These room coordinates are positive signed 12.4 fixed-point.
            for width,height in [(1920,1080),(2560,1440),(3840,2160)]:
                point=project_raw(*raw,width,height)
                recovered=inverse_raw(*point,width,height)
                error=max(abs(a-b) for a,b in zip(raw,recovered))
                max_error=max(max_error,error); comparisons+=1
                if error > 1e-8: raise ValueError('Projection lost source precision')
            local=[raw[0]/16-512,raw[1]/16-1536]
            if not points or local != points[-1]: points.append(local)
        routes.append({'id':trace['id'],'points':points})
    data={'schema':'ao_pc_25d_art_review_v1','runtime_approved':False,
          'layout':layout,'textures':textures,'source_background':inspect(LOCAL/'room/background.png'),
          'source_props':props,'routes':routes,'verified_query_indices':room['movement_profile']['verified_query_indices'],
          'source_package_hashes':verified,'review_height_world':layout['character_height_world']}
    (OUT/'review-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'schema':'ao_pc_25d_registration_checks_v1','projection_checks_passed':True,
            'source_package_hashes_unchanged':verified,'projection_roundtrips':comparisons,
            'maximum_fixed_point_error':max_error,'verified_cells':len(data['verified_query_indices']),
            'art_visual_alignment_passed':False,'occlusion_passed':False,'four_direction_approval':'pending',
            'runtime_approved':False,'performance_tested':False,
            'scope':'Coordinate precision and immutable old package pins only; not movement, art or gameplay acceptance.'}
    (OUT/'v1-registration-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_package_hashes_unchanged'}))


if __name__=='__main__': main()
