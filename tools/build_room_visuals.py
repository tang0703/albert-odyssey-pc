"""Export the new room atlas/decorations after R3 source gates, locally only."""
from __future__ import annotations
import json
from pathlib import Path
import room_graphics
import room_decoration
from character_graphics import sha

ROOT=Path(__file__).resolve().parents[1]

def build() -> dict:
    reports={n:(ROOT/'reports/room'/n).read_bytes() for n in ('graphics-validation.json','decoration-validation.json')}
    for name,raw in reports.items():
        r=json.loads(raw)
        if not r.get('passed'): raise ValueError('R3 source gate did not pass: '+name)
    proof=json.loads(reports['graphics-validation.json'])
    if len(proof['captures'])!=3 or any(r['unexplained_pixels'] for r in proof['captures']):
        raise ValueError('Incomplete R3 scene proof')
    folder=ROOT/'reports/room/decor-east-a'
    manifest_raw=(folder/'manifest.json').read_bytes();manifest=json.loads(manifest_raw)
    matches=[r for r in proof['captures'] if Path(r['folder']).resolve()==folder.resolve()]
    if len(matches)!=1 or matches[0]['manifest_sha256']!=sha(manifest_raw):
        raise ValueError('R3 proof is not bound to this capture')
    outputs={r['path']:r['sha256'] for r in manifest['outputs']}
    def read(name):
        raw=(folder/'frame-000000'/name).read_bytes()
        if sha(raw)!=outputs['frame-000000/'+name]: raise ValueError('Capture changed')
        return raw
    high,low=read('wram-high.bin'),read('wram-low.bin')
    sources={n:(ROOT.parent/'work/extract'/n).read_bytes() for n in ('TWN.BIN','MAP001.TWN','MAP001.V1N','0')}
    props,images=room_graphics.decorations(high,low,read('vram1.bin'),read('cram.bin'),json.loads(read('sample.json'))['vdp2'],sources)
    bg,fg=room_graphics.atlases(sources['MAP001.TWN'])
    images.update({'background.png':bg,'foreground.png':fg})
    output=ROOT/'reports/room/visuals'
    output.mkdir(parents=True,exist_ok=False)
    files={}
    for name,image in images.items():
        path=output/name;image.save(path)
        files[name]={'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size,
                     'dimensions':list(image.size),'rgba_sha256':sha(image.tobytes())}
    result={'schema':'ao_room_visuals_v1','source_local_only':True,'atlas_origin':list(room_graphics.ORIGIN),
            'atlas_dimensions':list(room_graphics.SIZE),'viewport':[320,224],
            'source_files':{n:sha(raw) for n,raw in sources.items()},
            'evidence':{n:sha(raw) for n,raw in reports.items()},
            'delays':{'actor':3,'camera':3,'decorations':3},
            'decorations':props,'programs':[p.metadata() for p in room_decoration.profiles(high,sources['TWN.BIN'],sources['MAP001.TWN'])],
            'files':files,'limits':['Original shadow omitted; decorations 6/7 now included.']}
    (output/'visuals.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'images':len(images),'manifest_sha256':sha((output/'visuals.json').read_bytes())}))
    return result
if __name__=='__main__': build()
