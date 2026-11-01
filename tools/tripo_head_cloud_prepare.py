"""Blender-only conversion of a completed, locally pinned Tripo texture result.

No network, geometry generation, rigging or animation. Keep the raw GLB intact.
"""
from pathlib import Path
import hashlib,json
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'art/local/tripo-head-v1/cloud-ready-01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((ART/'preparation.json').read_bytes())
raw=Path(report['raw_model']);assert sha(raw)==report['raw_sha256']
assert not (ART/'head-editable.blend').exists(),'Preserve previous conversion'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(raw))
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
assert len(objects)==3
palette=json.loads((ART/'palette.json').read_bytes())
mapping={v['source_material']:k for k,v in palette.items() if 'source_material' in v}
for material in bpy.data.materials:
    assert material.name in mapping,material.name
    material.name=mapping[material.name]
for obj in objects:
    obj.location.z+=.5  # observed glTF Y translation, imported into Blender Z
    assert len(obj.data.uv_layers)>0
    assert all(len(p.vertices)==3 for p in obj.data.polygons)
    assert all(len(slot.material.name)>0 for slot in obj.material_slots)
bpy.context.view_layer.update()
bounds=[tuple(min((o.matrix_world@Vector(c))[axis] for o in objects for c in o.bound_box) for axis in range(3)),
        tuple(max((o.matrix_world@Vector(c))[axis] for o in objects for c in o.bound_box) for axis in range(3))]
assert abs(bounds[0][2])<1e-6 and abs(bounds[1][2]-1)<1e-6,bounds
bpy.ops.object.select_all(action='DESELECT')
for obj in objects:obj.select_set(True)
bpy.context.view_layer.objects.active=objects[0]
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(ART/'head-editable.blend'))
bpy.ops.export_scene.fbx(filepath=str(ART/'head-palette.fbx'),use_selection=True,object_types={'MESH'},
    axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False,path_mode='STRIP',use_mesh_modifiers=False)
sizes=json.loads((ART/'texture-sizes.json').read_bytes())
files=['head-palette.fbx','old-head.fbx','palette.json',*sizes.keys()]
manifest={'schema':'ao_head_cloud_texture_inputs_v1','require_textures':True,'texture_sizes':sizes,
    'files':{name:sha(ART/name) for name in files},'cloud_task_id':'39e6ab01-c274-49e6-9043-d4dcd81144c1'}
(ART/'unity-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
result={'bounds_blender':bounds,'objects':[{ 'name':o.name,'vertices':len(o.data.vertices),
    'triangles':len(o.data.polygons),'materials':[s.material.name for s in o.material_slots]} for o in objects],
    'source_raw_sha256':sha(raw),'blend_sha256':sha(ART/'head-editable.blend'),
    'fbx_sha256':sha(ART/'head-palette.fbx'),'packed_images':len(bpy.data.images),
    'animation_exported':False,'performance_tested':False}
(ART/'blender-conversion.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
