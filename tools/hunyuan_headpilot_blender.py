"""Prepare generated geometry for static review; preserve raw source and old v2."""
from pathlib import Path
import bpy, bmesh, json, math, hashlib, sys, argparse
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'art/local/hunyuan-head-v1'
parser=argparse.ArgumentParser();parser.add_argument('--run',default='run-04');parser.add_argument('--out',default='prepared-01')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
SOURCE=BASE/args.run/'raw-head.glb'
OUT=BASE/args.out
if OUT.exists():raise RuntimeError('Do not overwrite prepared geometry')
OUT.mkdir()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version=0
bpy.ops.import_scene.gltf(filepath=str(SOURCE))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:o.select_set(True)
bpy.context.view_layer.objects.active=meshes[0];bpy.ops.object.join()
model=bpy.context.object;model.name='HUNYUAN_HEAD_CLEAN_STATIC'
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
raw=model.copy();raw.data=model.data.copy()
archive=bpy.data.collections.new('RAW_GENERATION_UNMODIFIED');bpy.context.scene.collection.children.link(archive);archive.objects.link(raw)
archive.hide_render=True;archive.hide_viewport=True
# Very small weld / normal consistency, no invented facial anatomy.
bm=bmesh.new();bm.from_mesh(model.data)
weld=1e-6
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=weld)
bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(model.data);bm.free()
for p in model.data.polygons:p.use_smooth=True
lo=Vector(tuple(min(v.co[i] for v in model.data.vertices) for i in range(3)))
hi=Vector(tuple(max(v.co[i] for v in model.data.vertices) for i in range(3)))
center=(lo+hi)/2;scale=1/(hi.z-lo.z)
for v in model.data.vertices:v.co=Vector(((v.co.x-center.x)*scale,(v.co.y-center.y)*scale,(v.co.z-lo.z)*scale))
mat=bpy.data.materials.new('HeadClay');mat.diffuse_color=(.42,.38,.32,1);mat.use_nodes=True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=mat.diffuse_color
mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.7
model.data.materials.clear();model.data.materials.append(mat)
for p in model.data.polygons:p.material_index=0
bpy.ops.object.select_all(action='DESELECT');model.select_set(True);bpy.context.view_layer.objects.active=model
bpy.ops.export_scene.fbx(filepath=str(OUT/'head-clay.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'head-editable.blend'))
# Diagnostic Blender views only; final review must also use real Unity renders.
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=12
scene.render.resolution_x=720;scene.render.resolution_y=720;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Neutral');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.09,.09,.09,1)
for name,loc,power,size in [('Key',(-3,-4,5),450,4),('Fill',(3,-2,2),180,3)]:
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
    light=bpy.data.objects.new(name,data);scene.collection.objects.link(light);light.location=loc;light.rotation_euler=(Vector((0,0,.5))-light.location).to_track_quat('-Z','Y').to_euler()
camera=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));scene.collection.objects.link(camera);scene.camera=camera;camera.data.type='ORTHO';camera.data.ortho_scale=1.25
for name,loc in [('front',(0,-4,.65)),('left',(4,0,.65)),('back',(0,4,.65)),('right',(-4,0,.65))]:
    camera.location=loc;camera.rotation_euler=(Vector((0,0,.5))-camera.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(OUT/f'diagnostic-{name}.png');bpy.ops.render.render(write_still=True)
record={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'vertices':len(model.data.vertices),'triangles':len(model.data.polygons),'normalized_review_head_height':1,'actual_game_height_assigned':False,'changes':['merge duplicate vertices at 1e-6 source units','consistent normals and smooth shading','head-only review normalization; original archived'],'geometry_sculpted':False,'animation_created':False,'performance_tested':False,'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}}
(OUT/'preparation.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
