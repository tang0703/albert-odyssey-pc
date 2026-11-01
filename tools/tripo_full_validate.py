"""Independently reopen the full Tripo conversion and compare with raw GLB."""
from pathlib import Path
import argparse,hashlib,json,sys
import bpy,numpy as np
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-body-v1'
p=argparse.ArgumentParser();p.add_argument('--version',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);art=BASE/a.version
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def digest(m):
    data=[]
    for collection,attribute,n,dtype in [(m.vertices,'co',3,np.float32),(m.loops,'vertex_index',1,np.int32),(m.uv_layers.active.data,'uv',2,np.float32),(m.corner_normals,'vector',3,np.float32)]:
        arr=np.empty(len(collection)*n,dtype);collection.foreach_get(attribute,arr)
        assert np.isfinite(arr).all();data.append(arr.tobytes())
    return hashlib.sha256(b''.join(data)).hexdigest()
approval=json.loads((ROOT/'docs/tripo-head-cloud-texture-approval.json').read_bytes())
for f,h in approval['files'].items():assert sha(ROOT/f)==h,f
source=json.loads((BASE/'textures-01/report.json').read_bytes());assert sha(Path(source['raw']))==source['raw_sha256']
manifest=json.loads((art/'unity-inputs.json').read_bytes())
for f,h in manifest['files'].items():assert Path(f).name==f and sha(art/f)==h,f
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=source['raw'])
raw=next(o for o in bpy.context.scene.objects if o.type=='MESH');expected=digest(raw.data)
bpy.ops.wm.open_mainfile(filepath=str(art/'player-body-preview.blend'))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(meshes)==1
obj=meshes[0];assert digest(obj.data)==expected
assert len(obj.data.polygons)==79434 and len(obj.data.vertices)==47498
assert set(p.material_index for p in obj.data.polygons)=={0} and len(obj.material_slots)==1
assert not bpy.data.actions and not bpy.data.armatures and obj.animation_data is None
z=[(obj.matrix_world@v.co).z for v in obj.data.vertices];assert abs(min(z))<1e-6 and abs(max(z)-1.125)<1e-6
for im in bpy.data.images:
    if im.users:assert im.packed_file and len(im.pixels)>0 and im.has_data,im.name
result={'passed':True,'scope':'complete static Tripo model; exact geometry/UV/normals preservation','mesh_digest':expected,'raw_sha256':source['raw_sha256'],'vertices':47498,'triangles':79434,'head_replaced':False,'faces_hidden':0,'height':1.125,'old_head_source_hashes_unchanged':True,'animation_tested':False,'performance_tested':False}
(art/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
