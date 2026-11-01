"""Reversible, face-local static refinement of the direction-approved Tripo sample.

No Tripo calls, no retopology, no textures, no rigging or animation.
"""
from pathlib import Path
import argparse, hashlib, json, math, shutil, sys
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--out',default='refined-08')
p.add_argument('--experimental-eyes',action='store_true',help='Rejected eye cleanup experiment; not approved for review delivery')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=BASE/a.out
out.mkdir(exist_ok=False)
source=BASE/'prepared-02/head-editable.blend'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source_hash=sha(source)
bpy.ops.wm.open_mainfile(filepath=str(source));bpy.context.preferences.filepaths.save_version=0
obj=bpy.data.objects['TRIPO_HEAD_STATIC_REVIEW'];data=obj.data
had_custom_normals=data.has_custom_normals
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
if had_custom_normals and a.experimental_eyes:
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
n=len(data.vertices);original=np.empty((n,3),dtype=np.float32);data.vertices.foreach_get('co',original.ravel())
xyz=original.astype(np.float64);x,y,z=xyz.T
report={'schema':'ao_tripo_head_local_refine_v1','source_sha256':source_hash,
    'direction_approval':'user: 接近我要的方向; not final art approval',
    'api_tasks_submitted':0,'credits_consumed':0,'regions':{},
    'animation_tested':False,'performance_tested':False,'final_topology':False,'gameplay_replaced':False,
    'imported_custom_normals_cleared':had_custom_normals and a.experimental_eyes,
    'eye_cleanup_applied':a.experimental_eyes,'eye_cleanup_status':'experimental, not accepted' if a.experimental_eyes else 'deferred; original eye coordinates preserved',
    'normals_policy':'recalculate experimental eye normals' if a.experimental_eyes else 'retain source custom normals for small static nose and mouth adjustment; eye shading unchanged'}
def falloff(radius,start=.6):
    t=np.clip((radius-start)/(1-start),0,1)
    return 1-t*t*(3-2*t)
region_weights={}
all_edges=np.empty((len(data.edges),2),dtype=np.int32);data.edges.foreach_get('vertices',all_edges.ravel())
# A robust local quadratic preserves the eye dome and removes reconstructed iris grooves.
for tag,cx,cz,rx,rz in ([('left',-.085,.278,.049,.045),('right',.131,.280,.055,.046)] if a.experimental_eyes else []):
    u=(x-cx)/rx;v=(z-cz)/rz;r=np.sqrt(u*u+v*v)
    indices=np.flatnonzero((r<1)&(y<-.155)&(y>-.28))
    uu=u[indices];vv=v[indices]
    A=np.column_stack([np.ones(len(indices)),uu,vv,uu*uu,uu*vv,vv*vv])
    target=y[indices].copy();robust=np.ones(len(indices))
    for _ in range(8):
        coeff=np.linalg.lstsq(A*robust[:,None]**.5,target*robust**.5,rcond=None)[0]
        residual=target-A@coeff
        sigma=max(.0003,1.4826*np.median(np.abs(residual-np.median(residual))))
        robust=np.minimum(1,(1.5*sigma)/(np.abs(residual)+1e-12))
    weights=falloff(r[indices],.90)
    # Relax the projected triangulation: groove walls otherwise fold over themselves
    # when only their depth is flattened. Keep the support boundary fixed.
    selected_eye=np.zeros(n,dtype=bool);selected_eye[indices]=True
    eye_edges=all_edges[selected_eye[all_edges[:,0]]|selected_eye[all_edges[:,1]]]
    et=np.concatenate([eye_edges[:,0],eye_edges[:,1]]);en=np.concatenate([eye_edges[:,1],eye_edges[:,0]])
    ek=selected_eye[et];et=et[ek];en=en[ek]
    el=np.full(n,-1,dtype=np.int32);el[indices]=np.arange(len(indices));et=el[et]
    ec=np.bincount(et,minlength=len(indices))
    for _ in range(60):
        avg=np.column_stack([np.bincount(et,weights=xyz[en,k],minlength=len(indices))/np.maximum(ec,1) for k in (0,2)])
        xyz[np.ix_(indices,[0,2])]+=(avg-xyz[np.ix_(indices,[0,2])])*(.5*weights[:,None])
    uu=(xyz[indices,0]-cx)/rx;vv=(xyz[indices,2]-cz)/rz
    A=np.column_stack([np.ones(len(indices)),uu,vv,uu*uu,uu*vv,vv*vv])
    delta=np.clip(A@coeff-target,-.025,.025)*weights
    xyz[indices,1]+=delta
    mask=np.zeros(n);mask[indices]=weights;region_weights[tag+'_eye_surface']=mask
    report['regions'][tag+'_eye_surface']={'vertices':len(indices),'center':[cx,cz],
        'radii':[rx,rz],'max_depth_change':float(np.max(np.abs(delta))),
        'method':'projected triangle relaxation and robust quadratic eye dome, blended to original boundary; no eye-color painting'}
# Narrow only the nose alae and slightly reduce their projection.
r=np.sqrt(((x-.02)/.046)**2+((z-.207)/.032)**2)
w=falloff(r,.15)*((y<-.235)&(y>-.31))
xyz[:,0]+=-.12*(x-.02)*w
xyz[:,1]+=.004*w
region_weights['nose_alae']=w
# Short-range tangential smoothing at the two deep mouth corners; center smile preserved.
corners=np.maximum(falloff(np.sqrt(((x+.037)/.020)**2+((z-.174)/.013)**2),.2),
                   falloff(np.sqrt(((x-.083)/.020)**2+((z-.176)/.013)**2),.2))
corners*=((y<-.19)&(y>-.28))
indices=np.flatnonzero(corners>0)
edges=np.empty((len(data.edges),2),dtype=np.int32);data.edges.foreach_get('vertices',edges.ravel())
selected=np.zeros(n,dtype=bool);selected[indices]=True
edges=edges[selected[edges[:,0]]|selected[edges[:,1]]]
targets=np.concatenate([edges[:,0],edges[:,1]]);neighbors=np.concatenate([edges[:,1],edges[:,0]])
keep=selected[targets];targets=targets[keep];neighbors=neighbors[keep]
local=np.full(n,-1,dtype=np.int32);local[indices]=np.arange(len(indices))
local_targets=local[targets];counts=np.bincount(local_targets,minlength=len(indices))
for _ in range(18):
    averaged=np.column_stack([np.bincount(local_targets,weights=xyz[neighbors,k],minlength=len(indices))/np.maximum(counts,1) for k in range(3)])
    xyz[indices]+=(averaged-xyz[indices])*(.45*corners[indices,None])
mouth_delta=xyz[indices]-original[indices]
length=np.linalg.norm(mouth_delta,axis=1)
xyz[indices]=original[indices]+mouth_delta*np.minimum(1,.0025/np.maximum(length,1e-12))[:,None]
region_weights['mouth_corners']=corners
changed=xyz.astype(np.float32)
union=np.maximum.reduce(list(region_weights.values()))>0
assert np.array_equal(changed[~union],original[~union])
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
obj.shape_key_add(name='Approved_Tripo_Sample')
refine=obj.shape_key_add(name='Local_Face_Refine_01');refine.data.foreach_set('co',changed.ravel());refine.value=1
for name,w in region_weights.items():
    group=obj.vertex_groups.new(name=name)
    # Groups show editable support. Shape-key displacement carries the smooth falloff.
    group.add(np.flatnonzero(w>0).tolist(),1,'REPLACE')
obj.name='TRIPO_HEAD_LOCAL_REFINED_STATIC'
dg=bpy.context.evaluated_depsgraph_get();bpy.context.view_layer.update()
baked=bpy.data.meshes.new_from_object(obj.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
temp=bpy.data.objects.new('STATIC_BAKED_FACE_REVIEW',baked);bpy.context.scene.collection.objects.link(temp)
bpy.ops.object.select_all(action='DESELECT');temp.select_set(True);bpy.context.view_layer.objects.active=temp
bpy.ops.export_scene.fbx(filepath=str(out/'head-palette.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
bpy.data.objects.remove(temp,do_unlink=True);bpy.data.meshes.remove(baked)
shutil.copyfile(BASE/'prepared-02/head-palette.fbx',out/'old-head.fbx')
shutil.copyfile(BASE/'prepared-02/palette.json',out/'palette.json')
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
bpy.ops.wm.save_as_mainfile(filepath=str(out/'head-editable.blend'))
report.update({'vertices':n,'faces':len(data.polygons),'edited_vertices':int(np.count_nonzero(np.any(changed!=original,axis=1))),
    'protected_vertices_unchanged':int(np.count_nonzero(~union)),
    'max_displacement':float(np.max(np.linalg.norm(changed-original,axis=1))),
    'topology_unchanged':True,'reversible_shape_key':refine.name,
    'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()}})
(out/'refinement.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(out/'unity-inputs.json').write_text(json.dumps({'files':{name:sha(out/name) for name in ['head-palette.fbx','old-head.fbx','palette.json']}},indent=2)+'\n',encoding='utf-8')
assert sha(source)==source_hash
# Blender diagnostic only, same neutral illumination as previous diagnostics.
sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=12;sc.cycles.device='CPU'
sc.render.resolution_x=900;sc.render.resolution_y=900;sc.render.resolution_percentage=100
sc.world=bpy.data.worlds.new('Diagnostic world');sc.world.use_nodes=True;sc.world.node_tree.nodes['Background'].inputs[0].default_value=(.1,.1,.1,1)
for name,loc,power in [('Key',(-3,-4,5),450),('Fill',(3,-2,2),180)]:
    d=bpy.data.lights.new(name,'AREA');d.energy=power;d.size=4;o=bpy.data.objects.new(name,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,.25))-o.location).to_track_quat('-Z','Y').to_euler()
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));sc.collection.objects.link(cam);sc.camera=cam;cam.data.type='ORTHO'
for name,loc,target,scale in [('face',(0,-4,.245),(0,0,.245),.48),('front',(0,-4,.55),(0,0,.5),1.25),('side',(4,0,.245),(0,0,.245),.6)]:
    cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
    sc.render.filepath=str(out/f'diagnostic-{name}.png');bpy.ops.render.render(write_still=True)
print(json.dumps(report,indent=2))
