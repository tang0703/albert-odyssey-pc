"""Extract a completed Tripo body GLB's PBR data for local Unity review. No API."""
from pathlib import Path
from io import BytesIO
import hashlib,json,struct
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-body-v1';OUT=BASE/'textures-01'
result=json.loads((BASE/'result.json').read_text().strip().splitlines()[-1]);assert result['status']=='success'
raw=Path(result['model_file']);data=raw.read_bytes();assert data[:4]==b'glTF'
n,kind=struct.unpack_from('<I4s',data,12);assert kind==b'JSON';g=json.loads(data[20:20+n]);size,kind=struct.unpack_from('<I4s',data,20+n);assert kind==b'BIN\0';blob=data[28+n:28+n+size]
OUT.mkdir(exist_ok=False)
images=[]
for i,entry in enumerate(g['images']):
    v=g['bufferViews'][entry['bufferView']];b=blob[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
    ext='jpg' if entry['mimeType']=='image/jpeg' else 'png';(OUT/f'raw-{i:02d}.{ext}').write_bytes(b)
    images.append(Image.open(BytesIO(b)).convert('RGB'))
def image_at(t):return images[g['textures'][t['index']]['source']]
palette={};sizes={}
for i,mat in enumerate(g['materials']):
    name=f'TripoBody_{i:02d}';pbr=mat['pbrMetallicRoughness'];entry={'source_material':mat['name'],'linear_color':pbr.get('baseColorFactor',[1,1,1,1]),'roughness':pbr.get('roughnessFactor',1),'double_sided':mat.get('doubleSided',False)}
    for src,label in [(pbr['baseColorTexture'],'basecolor'),(mat.get('normalTexture'),'normal')]:
        if src is None:continue
        filename=f'body-{i:02d}-{label}.png';im=image_at(src);im.save(OUT/filename);sizes[filename]=list(im.size)
        entry['base_texture' if label=='basecolor' else 'normal_texture']=filename
    if 'normalTexture' in mat:entry['normal_scale']=mat['normalTexture'].get('scale',1)
    if 'metallicRoughnessTexture' in pbr:
        orm=np.asarray(image_at(pbr['metallicRoughnessTexture']),np.float32)/255;mask=np.zeros((*orm.shape[:2],4),np.uint8)
        mask[:,:,0]=np.rint(orm[:,:,2]*pbr.get('metallicFactor',1)*255).astype(np.uint8);mask[:,:,1]=255
        mask[:,:,3]=np.rint((1-orm[:,:,1]*pbr.get('roughnessFactor',1))*255).astype(np.uint8)
        if 'occlusionTexture' in mat:
            ao=np.asarray(image_at(mat['occlusionTexture']),np.float32)/255
            assert ao.shape==orm.shape
            mask[:,:,1]=np.rint((1-mat['occlusionTexture'].get('strength',1)*(1-ao[:,:,0]))*255).astype(np.uint8);entry['occlusion_in_mask']=True
        filename=f'body-{i:02d}-metallic-smoothness.png';Image.fromarray(mask).save(OUT/filename);sizes[filename]=[mask.shape[1],mask.shape[0]];entry['metallic_gloss_texture']=filename
    palette[name]=entry
(OUT/'palette.json').write_text(json.dumps(palette,indent=2)+'\n');(OUT/'texture-sizes.json').write_text(json.dumps(sizes,indent=2)+'\n')
report={'task_id':result['task_id'],'raw':str(raw),'raw_sha256':hashlib.sha256(data).hexdigest(),'materials':list(palette),'texture_sizes':sizes,'triangles':sum(g['accessors'][p['indices']]['count']//3 for m in g['meshes'] for p in m['primitives']),
 'conversion':'original base/normal decoded to PNG; ORM repacked into metallic R, occlusion G, smoothness A; no creative repaint','api_tasks':0}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
