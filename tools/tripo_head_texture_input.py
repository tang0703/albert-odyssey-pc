"""Build a neutral GLB of the visible eye-color-18 surfaces, without cloud calls.

Run inside Blender. Export arrays directly to retain source corner normals rather
than re-encoding them through a rebuilt Blender mesh. Never edits the source.
"""
from pathlib import Path
import hashlib, json, struct
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'art/local/tripo-head-v1/eye-color-18'
OUT=ROOT/'art/local/tripo-head-v1/texture-input-01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source_sha=sha(SOURCE/'head-editable.blend')
lock=json.loads((ROOT/'art/local/tripo-head-v1/review-eye-color-02/bundle-lock.json').read_bytes())
assert source_sha==lock['files'][str((SOURCE/'head-editable.blend').relative_to(ROOT)).replace('\\','/')]['sha256']
OUT.mkdir(exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(SOURCE/'head-editable.blend'))
blob=bytearray();views=[];accessors=[];meshes=[];nodes=[];stats=[]

def append_array(array,kind,target,bounds=False):
    array=np.ascontiguousarray(array)
    while len(blob)%4:blob.append(0)
    offset=len(blob);blob.extend(array.tobytes())
    views.append({'buffer':0,'byteOffset':offset,'byteLength':array.nbytes,'target':target})
    entry={'bufferView':len(views)-1,'componentType':5125 if array.dtype==np.uint32 else 5126,'count':len(array),'type':kind}
    if bounds:entry.update(min=array.min(axis=0).tolist(),max=array.max(axis=0).tolist())
    accessors.append(entry);return len(accessors)-1

for name in ('HeadRetainedSurface','EyeSurface_Left','EyeSurface_Right'):
    obj=bpy.data.objects[name];m=obj.data
    v=np.empty((len(m.vertices),3),np.float32);m.vertices.foreach_get('co',v.ravel())
    ids=np.empty(len(m.loops),np.int32);m.loops.foreach_get('vertex_index',ids)
    n=np.empty((len(m.loops),3),np.float32);m.corner_normals.foreach_get('vector',n.ravel())
    uv=np.empty((len(m.loops),2),np.float32);m.uv_layers.active.data.foreach_get('uv',uv.ravel())
    keep=np.ones(len(m.polygons),bool)
    if name=='HeadRetainedSurface':
        hidden=np.empty(len(m.polygons),bool);m.attributes['source_eye_hidden'].data.foreach_get('value',hidden);keep=~hidden
        assert int(hidden.sum())==5316
    keep=np.repeat(keep,3);ids=ids[keep];n=n[keep];uv=uv[keep]
    # Exact corner tuple deduplication preserves UV seams and authored normals.
    corners=np.column_stack([ids.astype(np.float32),n,uv]).astype(np.float32)
    keys=np.ascontiguousarray(corners).view(np.dtype((np.void,corners.dtype.itemsize*6))).ravel()
    _,first,index=np.unique(keys,return_index=True,return_inverse=True)
    assert np.array_equal(corners[first][index],corners)
    position=v[ids[first]][:,[0,2,1]].copy();position[:,2]*=-1
    normal=n[first][:,[0,2,1]].copy();normal[:,2]*=-1
    texcoord=uv[first].copy();texcoord[:,1]=1-texcoord[:,1]
    assert np.isfinite(position).all() and np.isfinite(normal).all() and np.isfinite(texcoord).all()
    attrs={'POSITION':append_array(position,'VEC3',34962,True),'NORMAL':append_array(normal,'VEC3',34962),'TEXCOORD_0':append_array(texcoord,'VEC2',34962)}
    primitive={'attributes':attrs,'indices':append_array(index.astype(np.uint32),'SCALAR',34963),'material':0,'mode':4}
    meshes.append({'name':name,'primitives':[primitive]});nodes.append({'name':name,'mesh':len(meshes)-1})
    stats.append({'object':name,'vertices':len(first),'triangles':len(index)//3,'coordinates_and_corner_normals_preserved':True})

document={'asset':{'version':'2.0','generator':'Local visible-head export; no simplification'},'scene':0,'scenes':[{'nodes':list(range(len(nodes)))}],
 'nodes':nodes,'meshes':meshes,'materials':[{'name':'NeutralRetextureInput','pbrMetallicRoughness':{'baseColorFactor':[.5,.5,.5,1],'metallicFactor':0,'roughnessFactor':.8}}],
 'buffers':[{'byteLength':len(blob)}],'bufferViews':views,'accessors':accessors}
raw=json.dumps(document,separators=(',',':')).encode();raw+=b' '*((-len(raw))%4);blob+=b'\0'*((-len(blob))%4)
glb=struct.pack('<4sII',b'glTF',2,12+8+len(raw)+8+len(blob))+struct.pack('<I4s',len(raw),b'JSON')+raw+struct.pack('<I4s',len(blob),b'BIN\0')+blob
path=OUT/'head-visible-neutral.glb';path.write_bytes(glb)
assert len(glb)<150_000_000 and sha(SOURCE/'head-editable.blend')==source_sha
record={'source':str(SOURCE/'head-editable.blend'),'source_sha256':source_sha,'model':path.name,'sha256':sha(path),'bytes':len(glb),'meshes':stats,
 'old_eye_faces_excluded':5316,'archived_model_excluded':True,'existing_color_textures_excluded':True,'triangle_total':sum(item['triangles'] for item in stats),
 'axis':'Blender XYZ to glTF X,Z,-Y; front +Z','api_tasks':0,'credits':0,'status':'prepared_local_input_not_uploaded'}
(OUT/'input-lock.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
