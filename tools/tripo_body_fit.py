"""Fit a completed Tripo body beneath the approved head; no network or animation.

Keep raw meshes intact. Explicit render masks hide the generated head and the
approved bust's lower clothing, so both inputs remain recoverable in Blender.
"""
from pathlib import Path
import argparse,hashlib,json,math,shutil,sys
import bpy,numpy as np
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-body-v1';HEAD=ROOT/'art/local/tripo-head-v1/cloud-ready-01'
p=argparse.ArgumentParser();p.add_argument('--version',default='body-fit-01');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);OUT=BASE/a.version;OUT.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
approval=json.loads((ROOT/'docs/tripo-head-cloud-texture-approval.json').read_bytes())
for name,expected in approval['files'].items():assert sha(ROOT/name)==expected,name
source=json.loads((BASE/'textures-01/report.json').read_bytes());assert sha(Path(source['raw']))==source['raw_sha256']
def mesh_digest(m):
    v=np.empty((len(m.vertices),3),np.float32);m.vertices.foreach_get('co',v.ravel())
    idx=np.empty(len(m.loops),np.int32);m.loops.foreach_get('vertex_index',idx)
    uv=np.empty((len(m.loops),2),np.float32);m.uv_layers.active.data.foreach_get('uv',uv.ravel())
    n=np.empty((len(m.loops),3),np.float32);m.corner_normals.foreach_get('vector',n.ravel())
    return hashlib.sha256(v.tobytes()+idx.tobytes()+uv.tobytes()+n.tobytes()).hexdigest()
def hidden_material(name):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=(0,0,0,0);mat.node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value=0;return mat
def apply_mask(obj,mask,name):
    obj.data.materials.append(hidden_material(name));indices=np.zeros(len(obj.data.polygons),np.int32);indices[mask]=len(obj.data.materials)-1;obj.data.polygons.foreach_set('material_index',indices)
def coordinates(m):
    p=np.empty((len(m.vertices),3),np.float32);m.vertices.foreach_get('co',p.ravel());idx=np.empty(len(m.loops),np.int32);m.loops.foreach_get('vertex_index',idx);return p,idx.reshape(-1,3)
bpy.ops.wm.open_mainfile(filepath=str(HEAD/'head-editable.blend'));heads=list(bpy.context.scene.objects)
head_hashes={o.name:mesh_digest(o.data) for o in heads}
bodyhead=bpy.data.objects['HeadRetainedSurface'];m=bodyhead.data;p,idx=coordinates(m);source_z=p[:,2]+.5
# Restrict the render mask to lower bust green/linen clothing. Preserve the
# approved face, ears, neck and scarf; height-only cuts removed the chin in v01.
uv=np.empty((len(m.loops),2),np.float32);m.uv_layers.active.data.foreach_get('uv',uv.ravel());uv=uv.reshape(-1,3,2).mean(1)
im=bpy.data.images['HeadRetainedSurface_base_color'];w,h=im.size;px=np.empty(w*h*4,np.float32);im.pixels.foreach_get(px);px=px.reshape(h,w,4)
rgb=px[np.clip((uv[:,1]*h).astype(int),0,h-1),np.clip((uv[:,0]*w).astype(int),0,w-1),:3];r,g,b=rgb.T
green=(g>r*.94)&(g>b*1.25);linen=(r>g)&(r<g*1.22)&(g>b*1.15)
mask=(source_z[idx].max(1)<.155)&(green|linen)
apply_mask(bodyhead,mask,'ApprovedBustClothingHidden')
head_scale=.510;head_base=.615
for o in heads:o.scale*=head_scale;o.location=o.location*head_scale+Vector((0,-.008,head_base))
assert all(mesh_digest(o.data)==head_hashes[o.name] for o in heads)

bpy.ops.import_scene.gltf(filepath=source['raw']);bodies=[o for o in bpy.context.scene.objects if o not in heads and o.type=='MESH'];assert len(bodies)==1
body=bodies[0];body.name='TRIPO_BODY_WITH_GENERATED_HEAD_MASKED';m=body.data
raw_digest=mesh_digest(m);p,idx=coordinates(m);floor=float(p[:,2].min());height=float(np.ptp(p[:,2]));scale=1.125/height
z=(p[:,2]-floor)*scale;generated_head_mask=z[idx].max(1)>.690
palette={k:v for k,v in json.loads((HEAD/'palette.json').read_bytes()).items() if k.startswith('CloudMaterial_')}
bp=json.loads((BASE/'textures-01/palette.json').read_bytes());mapping={v['source_material']:k for k,v in bp.items()}
for slot in body.material_slots:slot.material.name=mapping[slot.material.name]
apply_mask(body,generated_head_mask,'GeneratedHeadHidden')
# Tripo result faces +X in Blender; rotate into the approved head's -Y forward.
body.matrix_world=Matrix.Translation((0,0,-floor*scale))@Matrix.Rotation(-math.pi/2,4,'Z')@Matrix.Scale(scale,4)
assert mesh_digest(m)==raw_digest
palette.update(bp)
for name in ('ApprovedBustClothingHidden','GeneratedHeadHidden'):palette[name]={'linear_color':[0,0,0,0],'roughness':1,'alpha_clip':True}
sizes={k:v for k,v in json.loads((HEAD/'texture-sizes.json').read_bytes()).items() if k.startswith('cloud-')}
for filename in sizes:shutil.copyfile(HEAD/filename,OUT/filename)
bs=json.loads((BASE/'textures-01/texture-sizes.json').read_bytes())
for filename in bs:shutil.copyfile(BASE/'textures-01'/filename,OUT/filename)
sizes.update(bs)
bpy.context.view_layer.update();objects=heads+bodies
bpy.ops.object.select_all(action='DESELECT')
for o in objects:o.select_set(True)
bpy.context.view_layer.objects.active=body;bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'player-body-preview.blend'))
bpy.ops.export_scene.fbx(filepath=str(OUT/'player-static.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,axis_forward='-Z',axis_up='Y',path_mode='STRIP',use_mesh_modifiers=False)
(OUT/'palette.json').write_text(json.dumps(palette,indent=2)+'\n')
manifest={'schema':'ao_approved_head_body_static_v1','files':{f:sha(OUT/f) for f in ['player-static.fbx','palette.json',*sizes]},'texture_sizes':sizes,'height':1.125,'head_approval_sha256':sha(ROOT/'docs/tripo-head-cloud-texture-approval.json'),'body_task_id':source['task_id']}
(OUT/'unity-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
report={'schema':'ao_tripo_body_fitting_v1','version':a.version,'raw_body_sha256':source['raw_sha256'],'head_source_sha256':sha(HEAD/'head-editable.blend'),
 'head_mesh_uv_normal_hashes':head_hashes,'raw_body_mesh_uv_normal_hash':raw_digest,'raw_body_triangles':len(m.polygons),'visible_body_triangles':int((~generated_head_mask).sum()),
 'head_render_mask_faces':np.flatnonzero(mask).tolist(),'body_render_mask_faces':np.flatnonzero(generated_head_mask).tolist(),
 'head_uniform_scale':head_scale,'head_base_z':head_base,'body_scale':scale,'body_rotation_z_degrees':-90,'body_cut_world_z':.690,
 'original_inputs_unchanged':True,'body_approved':False,'animation_created':False,'performance_tested':False,'local_api_tasks':0}
(OUT/'fitting-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if not k.endswith('_faces')}))
