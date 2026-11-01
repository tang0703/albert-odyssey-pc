"""Deterministic ROI preprocessing of approved images for shape inference.

This does not redraw references. Original pixels/alpha remain untouched in
their source files. Crops and inference-size resampling are recorded locally.
"""
from pathlib import Path
import hashlib,json
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'art/enhanced25d/v1'
OUT=ROOT/'art/local/hunyuan-head-v1/inputs'
if OUT.exists():raise RuntimeError('Preserve existing input preparation')
OUT.mkdir(parents=True)
approval=json.loads((SOURCE/'approval.json').read_bytes())
assert approval['approved']
regions={'front':('down',(320,20,910,568)),
         'left':('left',(340,0,910,510)),
         'back':('up',(350,30,930,512)),
         'right':('right',(310,0,930,540))}
record={'schema':'ao_multiview_head_inputs_v1','source_approval_sha256':hashlib.sha256((SOURCE/'approval.json').read_bytes()).hexdigest(),
        'purpose':'head and hair shape pilot, not new concept artwork','pixels_redrawn':False,'references':{},
        'limitations':['Approved views have illustrative perspective and are not calibrated orthographic scans.','Cut at neck; small scarf portions can remain at the crop boundary.'],
        'upload_performed':False}
for view,(direction,roi) in regions.items():
    source=SOURCE/approval['references'][direction]['file'];raw=source.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==approval['references'][direction]['sha256']
    image=Image.open(source).convert('RGBA');crop=image.crop(roi)
    crop.save(OUT/f'{view}-roi.png')
    factor=448/max(crop.size);size=tuple(round(v*factor) for v in crop.size)
    resized=crop.resize(size,Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(512,512),(0,0,0,0));offset=((512-size[0])//2,(512-size[1])//2)
    canvas.paste(resized,offset);canvas.save(OUT/f'{view}.png')
    record['references'][view]={'source':source.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(raw).hexdigest(),
        'roi':roi,'resampled_size':size,'offset':offset,'prepared_sha256':hashlib.sha256((OUT/f'{view}.png').read_bytes()).hexdigest()}
(OUT/'input-lock.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,indent=2))
