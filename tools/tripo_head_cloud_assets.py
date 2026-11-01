"""Inspect a completed texture task and prepare local URP texture assets.

No API calls. Preserve the raw result, compare geometry after the observed
translation, and repack glTF metallic/roughness into Unity metallic/smoothness.
"""
from pathlib import Path
from io import BytesIO
import hashlib,json,struct,shutil
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
RAW=BASE/'cloud-texture-01/tripo-out/head-texture-01-39e6ab01/model.glb';OUT=BASE/'cloud-ready-01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read_glb(path):
    raw=path.read_bytes();magic,version,length=struct.unpack_from('<4sII',raw)
    assert magic==b'glTF' and version==2 and length==len(raw)
    n,kind=struct.unpack_from('<I4s',raw,12);assert kind==b'JSON';doc=json.loads(raw[20:20+n]);size,kind=struct.unpack_from('<I4s',raw,20+n);assert kind==b'BIN\0'
    return doc,raw[28+n:28+n+size]
def accessor(doc,blob,index):
    a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];assert not v.get('byteStride') and not a.get('sparse')
    count={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']];dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']]
    return np.frombuffer(blob,dtype=dtype,offset=v.get('byteOffset',0)+a.get('byteOffset',0),count=a['count']*count).reshape(-1,count)
def surfaces(doc,blob):
    assert all(not any(k in node for k in ('matrix','translation','rotation','scale')) for node in doc['nodes'])
    result={}
    for mesh in doc['meshes']:
        assert len(mesh['primitives'])==1;p=mesh['primitives'][0]
        result[mesh['name']]={k:accessor(doc,blob,v) for k,v in {**p['attributes'],'INDEX':p['indices']}.items()}
    return result

OUT.mkdir(exist_ok=False)
g,b=read_glb(RAW);sg,sb=read_glb(BASE/'texture-input-01/head-visible-neutral.glb')
source=surfaces(sg,sb);target=surfaces(g,b);assert set(source)==set(target)
geometry=[]
for name in source:
    a=source[name];c=target[name];p=a['POSITION'];q=c['POSITION'];assert p.shape==q.shape
    oi=np.lexsort((p[:,1],p[:,2],p[:,0]));ni=np.lexsort((q[:,1],q[:,2],q[:,0]))
    assert np.array_equal(p[oi][:,[0,2]],q[ni][:,[0,2]])
    delta=q[ni].astype(np.float64)-p[oi];error=float(np.abs(delta-[0,-.5,0]).max());assert error<5e-8
    # Shared geometric vertex IDs remove UV/normal splits when comparing faces.
    sorted_p=p[oi];starts=np.r_[True,np.any(sorted_p[1:]!=sorted_p[:-1],axis=1)];groups=np.cumsum(starts)-1
    old_ids=np.empty(len(p),np.int32);new_ids=np.empty(len(q),np.int32);old_ids[oi]=groups;new_ids[ni]=groups
    def canonical(data,ids):
        indices=data['INDEX'].reshape(-1,3);faces=ids[indices];first=faces.argmin(axis=1);corners=(first[:,None]+np.arange(3))%3
        faces=np.take_along_axis(faces,corners,axis=1);indices=np.take_along_axis(indices,corners,axis=1)
        order=np.lexsort((faces[:,2],faces[:,1],faces[:,0]));return faces[order],indices[order]
    of,oc=canonical(a,old_ids);nf,nc=canonical(c,new_ids);assert np.array_equal(of,nf),'Triangle topology or winding changed'
    normal_error=float(np.abs(a['NORMAL'][oc]-c['NORMAL'][nc]).max());uv_error=float(np.abs(a['TEXCOORD_0'][oc]-c['TEXCOORD_0'][nc]).max())
    geometry.append({'mesh':name,'vertices':len(p),'triangles':len(of),'translation':[0,-.5,0],'position_max_abs_error_after_translation':error,'oriented_triangles_equal':True,'normal_max_abs_difference':normal_error,'uv_max_abs_difference':uv_error})

raw_images=[]
for i,item in enumerate(g['images']):
    view=g['bufferViews'][item['bufferView']];data=b[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
    raw_images.append(Image.open(BytesIO(data)).convert('RGB'))
    ext='jpg' if item['mimeType']=='image/jpeg' else 'png';(OUT/f'raw-image-{i:02d}.{ext}').write_bytes(data)
def image_at(texture):return raw_images[g['textures'][texture['index']]['source']]
palette=json.loads((BASE/'eye-color-18/palette.json').read_bytes());sizes={}
for file in ('head-basecolor.png','eye-basecolor.png'):
    shutil.copyfile(BASE/'eye-color-18'/file,OUT/file)
    with Image.open(OUT/file) as im:sizes[file]=list(im.size)
shutil.copyfile(BASE/'eye-color-18/head-palette.fbx',OUT/'old-head.fbx')
for i,mat in enumerate(g['materials']):
    pbr=mat['pbrMetallicRoughness'];name=f'CloudMaterial_{i:02d}';base=f'cloud-{i:02d}-basecolor.png'
    im=image_at(pbr['baseColorTexture']);im.save(OUT/base);sizes[base]=list(im.size)
    entry={'linear_color':pbr.get('baseColorFactor',[1,1,1,1]),'roughness':pbr.get('roughnessFactor',1),'base_texture':base,'double_sided':mat.get('doubleSided',False),'source_material':mat['name']}
    if 'metallicRoughnessTexture' in pbr:
        orm=np.asarray(image_at(pbr['metallicRoughnessTexture']),np.float32)/255;mask=np.zeros((*orm.shape[:2],4),np.uint8)
        mask[:,:,0]=np.rint(orm[:,:,2]*pbr.get('metallicFactor',1)*255).astype(np.uint8)
        mask[:,:,1]=255;mask[:,:,3]=np.rint((1-orm[:,:,1]*pbr.get('roughnessFactor',1))*255).astype(np.uint8)
        if 'occlusionTexture' in mat:
            ao=np.asarray(image_at(mat['occlusionTexture']),np.float32)/255;assert ao.shape==orm.shape
            mask[:,:,1]=np.rint((1-mat['occlusionTexture'].get('strength',1)*(1-ao[:,:,0]))*255).astype(np.uint8);entry['occlusion_in_mask']=True
        filename=f'cloud-{i:02d}-metallic-smoothness.png';Image.fromarray(mask).save(OUT/filename);sizes[filename]=[mask.shape[1],mask.shape[0]];entry['metallic_gloss_texture']=filename
    if 'normalTexture' in mat:
        filename=f'cloud-{i:02d}-normal.png';im=image_at(mat['normalTexture']);im.save(OUT/filename);sizes[filename]=list(im.size);entry['normal_texture']=filename;entry['normal_scale']=mat['normalTexture'].get('scale',1)
    palette[name]=entry
(OUT/'palette.json').write_text(json.dumps(palette,indent=2)+'\n')
(OUT/'texture-sizes.json').write_text(json.dumps(sizes,indent=2)+'\n')
report={'raw_model':str(RAW),'raw_sha256':sha(RAW),'source_input_sha256':sha(BASE/'texture-input-01/head-visible-neutral.glb'),'geometry':geometry,
 'presentation_translation_glTF':[0,.5,0],'geometry_sculpted_locally':False,'textures':sizes,'source_material_order':[m['name'] for m in g['materials']],
 'texture_processing':'decode original images; lossless PNG output; linear ORM to URP metallic R / occlusion G / smoothness A; no creative repaint',
 'api_tasks_added':0,'animation_tested':False,'performance_tested':False,'art_approved':False}
(OUT/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
