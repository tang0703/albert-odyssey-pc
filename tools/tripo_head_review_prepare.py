"""Prepare an approved single Tripo result for static review; never submit a task.

Run inside Blender. Raw GLB remains immutable. Orientation/scale and a neutral
material are presentation transforms, not a claim of sculpting or retopology.
"""
from pathlib import Path
import argparse, hashlib, json, math, sys
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'art/local/tripo-head-v1'
p = argparse.ArgumentParser()
p.add_argument('--source', required=True)
p.add_argument('--out', default='prepared-01')
p.add_argument('--yaw', type=float, default=0)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
source = Path(a.source).resolve()
out = BASE / a.out
out.mkdir(parents=True, exist_ok=False)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
raw_hash = sha(source)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.import_scene.gltf(filepath=str(source))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not meshes:
    raise RuntimeError('Generated model has no mesh')
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.join()
model = bpy.context.object
model.name = 'TRIPO_HEAD_STATIC_REVIEW'
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
rotation = Matrix.Rotation(math.radians(a.yaw), 4, 'Z')
for v in model.data.vertices:
    v.co = rotation @ v.co
lo = Vector(tuple(min(v.co[i] for v in model.data.vertices) for i in range(3)))
hi = Vector(tuple(max(v.co[i] for v in model.data.vertices) for i in range(3)))
center = (lo + hi) / 2
scale = 1 / (hi.z - lo.z)
for v in model.data.vertices:
    v.co = Vector(((v.co.x-center.x)*scale, (v.co.y-center.y)*scale, (v.co.z-lo.z)*scale))
mat = bpy.data.materials.new('FaceStudyClay')
mat.use_nodes = True
srgb = (.66, .64, .59)
linear = [((c+.055)/1.055)**2.4 for c in srgb]
mat.diffuse_color = (*linear, 1)
bsdf = mat.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = mat.diffuse_color
bsdf.inputs['Roughness'].default_value = .75
def materialize(obj):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.material_index = 0
        poly.use_smooth = True
materialize(model)
def export(obj, name):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(out/name), use_selection=True,
        object_types={'MESH'}, bake_anim=False, add_leaf_bones=False,
        axis_forward='-Z', axis_up='Y', apply_scale_options='FBX_SCALE_ALL')
export(model, 'head-palette.fbx')
old_source = ROOT / 'art/local/hunyuan-head-v1/refined-02/head-refined.blend'
assert sha(old_source) == 'a0f3b01b9db877860b1541ee6f5fddbf12ffa38d15527929bfc898924e7d0b22'
with bpy.data.libraries.load(str(old_source), link=False) as (src, dst):
    dst.objects = ['HEAD_PILOT_REFINED_STATIC']
old = dst.objects[0]
bpy.context.scene.collection.objects.link(old)
materialize(old)
export(old, 'old-head.fbx')
bpy.data.objects.remove(old, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
model.select_set(True)
bpy.context.view_layer.objects.active = model
bpy.ops.wm.save_as_mainfile(filepath=str(out/'head-editable.blend'))
palette = {'FaceStudyClay': {'linear_color': list(mat.diffuse_color), 'roughness': .75}}
(out/'palette.json').write_text(json.dumps(palette, indent=2)+'\n', encoding='utf-8')
(out/'unity-inputs.json').write_text(json.dumps({'files': {name: sha(out/name) for name in
    ('head-palette.fbx', 'old-head.fbx', 'palette.json')}}, indent=2)+'\n', encoding='utf-8')
report = {'schema':'ao_tripo_static_head_review_v1', 'raw_file':str(source),
    'raw_sha256':raw_hash, 'previous_blend_sha256':sha(old_source), 'yaw_degrees':a.yaw,
    'original_bounds':[list(lo),list(hi)], 'review_height':1,
    'vertices':len(model.data.vertices), 'polygons':len(model.data.polygons),
    'triangles':sum(len(f.vertices)-2 for f in model.data.polygons),
    'geometry_sculpted':False, 'topology_recovered_from_screenshots':False,
    'animation_tested':False, 'performance_tested':False, 'gameplay_replaced':False}
(out/'preparation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
assert sha(source) == raw_hash
# Four short Blender diagnostics establish orientation; Unity is the review renderer.
scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=12
scene.render.resolution_x=720
scene.render.resolution_y=720
scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Diagnostic world')
scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.09,.09,.09,1)
for name,loc,power in [('Key',(-3,-4,5),450),('Fill',(3,-2,2),180)]:
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.size=4
    light=bpy.data.objects.new(name,data);scene.collection.objects.link(light)
    light.location=loc;light.rotation_euler=(Vector((0,0,.5))-light.location).to_track_quat('-Z','Y').to_euler()
cam=bpy.data.objects.new('Diagnostic camera',bpy.data.cameras.new('Camera'))
scene.collection.objects.link(cam);scene.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=1.25
for name,loc in [('front',(0,-4,.55)),('left',(4,0,.55)),('back',(0,4,.55)),('right',(-4,0,.55))]:
    cam.location=loc;cam.rotation_euler=(Vector((0,0,.5))-cam.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(out/f'diagnostic-{name}.png')
    bpy.ops.render.render(write_still=True)
print(json.dumps(report, indent=2))
