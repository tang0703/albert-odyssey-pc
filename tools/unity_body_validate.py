"""Reopen static body preview and verify approved head data, textures and scope."""
from pathlib import Path
import argparse,hashlib,json,sys
import bpy,numpy as np
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--version',required=True);p.add_argument('--tripo-body',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);BASE=ROOT/'art/local/tripo-body-v1' if a.tripo_body else BASE;art=BASE/a.version
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
approval=json.loads((ROOT/'docs/tripo-head-cloud-texture-approval.json').read_bytes())
for path,h in approval['files'].items():assert sha(ROOT/path)==h,path
manifest=json.loads((art/'unity-inputs.json').read_bytes())
for file,h in manifest['files'].items():assert Path(file).name==file and sha(art/file)==h,file
geometry=json.loads((art/('fitting-report.json' if a.tripo_body else 'geometry-report.json')).read_bytes())
if a.tripo_body:
    raw=json.loads((BASE/'textures-01/report.json').read_bytes())
    assert sha(Path(raw['raw']))==geometry['raw_body_sha256']
    geometry['head_mesh_uv_normals_unchanged']={**geometry['head_mesh_uv_normal_hashes'],'TRIPO_BODY_WITH_GENERATED_HEAD_MASKED':geometry['raw_body_mesh_uv_normal_hash']}
    geometry['body_parts']=1
bpy.ops.wm.open_mainfile(filepath=str(art/'player-body-preview.blend'))
assert not bpy.data.actions and not bpy.data.armatures
for name,expected in geometry['head_mesh_uv_normals_unchanged'].items():
    m=bpy.data.objects[name].data
    v=np.empty((len(m.vertices),3),np.float32);m.vertices.foreach_get('co',v.ravel())
    loops=np.empty(len(m.loops),np.int32);m.loops.foreach_get('vertex_index',loops)
    uv=np.empty((len(m.loops),2),np.float32);m.uv_layers.active.data.foreach_get('uv',uv.ravel())
    n=np.empty((len(m.loops),3),np.float32);m.corner_normals.foreach_get('vector',n.ravel())
    assert hashlib.sha256(v.tobytes()+loops.tobytes()+uv.tobytes()+n.tobytes()).hexdigest()==expected,name
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(meshes)==geometry['body_parts']+3
if a.tripo_body:
    for obj,slot,key in [('HeadRetainedSurface','ApprovedBustClothingHidden','head_render_mask_faces'),('TRIPO_BODY_WITH_GENERATED_HEAD_MASKED','GeneratedHeadHidden','body_render_mask_faces')]:
        m=bpy.data.objects[obj].data;index=[x.name for x in m.materials].index(slot)
        indices=np.empty(len(m.polygons),np.int32);m.polygons.foreach_get('material_index',indices)
        assert np.array_equal(np.flatnonzero(indices==index),geometry[key])
if 'hidden_face_ids' in geometry:
    mesh=bpy.data.objects['HeadRetainedSurface'].data
    slots=[m.name for m in mesh.materials];hidden_index=slots.index('SourceBustHidden')
    indices=np.empty(len(mesh.polygons),np.int32);mesh.polygons.foreach_get('material_index',indices)
    assert np.array_equal(np.flatnonzero(indices==hidden_index),geometry['hidden_face_ids'])
    for face_id in geometry['hidden_face_ids']:
        assert max(mesh.vertices[i].co.z+.5 for i in mesh.polygons[face_id].vertices)<.155
for o in meshes:
    assert o.animation_data is None and len(o.data.uv_layers)>0
    assert all(s.material and s.material.use_nodes for s in o.material_slots)
for im in bpy.data.images:
    if im.users:
        assert im.packed_file and len(im.pixels)>0 and im.has_data,im.name
result={'passed':True,'scope':'static model integrity and approved head preservation',
 'head_source_and_approval_hashes_unchanged':True,'head_mesh_coordinates_normals_uv_exact':True,
 'meshes':len(meshes),'packed_images_verified':len([im for im in bpy.data.images if im.users]),
 'lower_bust_render_mask_faces':len(geometry.get('hidden_face_ids',[])),
 'no_skeleton_or_animation':True,'body_approved':False,'performance_tested':False}
(art/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
