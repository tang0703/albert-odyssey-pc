"""Import the complete approved-paid Tripo result for static Unity review.

No new cloud request, head replacement, shape edits, skeleton or animation.
"""
from pathlib import Path
import argparse,hashlib,json,math,shutil,sys
import bpy
from mathutils import Matrix
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-body-v1'
p=argparse.ArgumentParser();p.add_argument('--version',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
out=BASE/a.version;out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=json.loads((BASE/'textures-01/report.json').read_bytes())
assert sha(Path(source['raw']))==source['raw_sha256']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=source['raw'])
objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(objects)==1
obj=objects[0];obj.name='Complete_Tripo_Character'
floor=min(v.co.z for v in obj.data.vertices);top=max(v.co.z for v in obj.data.vertices);scale=1.125/(top-floor)
obj.matrix_world=Matrix.Translation((0,0,-floor*scale))@Matrix.Rotation(-math.pi/2,4,'Z')@Matrix.Scale(scale,4)
palette=json.loads((BASE/'textures-01/palette.json').read_bytes())
mapping={v['source_material']:k for k,v in palette.items()}
for slot in obj.material_slots:slot.material.name=mapping[slot.material.name]
sizes=json.loads((BASE/'textures-01/texture-sizes.json').read_bytes())
for f in sizes:shutil.copyfile(BASE/'textures-01'/f,out/f)
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'player-body-preview.blend'))
bpy.ops.export_scene.fbx(filepath=str(out/'player-static.fbx'),use_selection=False,object_types={'MESH'},bake_anim=False,axis_forward='-Z',axis_up='Y',path_mode='STRIP',use_mesh_modifiers=False)
(out/'palette.json').write_text(json.dumps(palette,indent=2)+'\n')
manifest={'schema':'ao_approved_head_body_static_v1','scope':'complete Tripo character; no head replacement','files':{f:sha(out/f) for f in ['player-static.fbx','palette.json',*sizes]},'texture_sizes':sizes,'height':1.125,'head_approval_sha256':sha(ROOT/'docs/tripo-head-cloud-texture-approval.json'),'body_task_id':source['task_id']}
(out/'unity-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
report={'scope':'complete Tripo result, static presentation only','task_id':source['task_id'],'raw_sha256':source['raw_sha256'],'triangles':len(obj.data.polygons),'vertices':len(obj.data.vertices),'height':1.125,'uniform_scale':scale,'orientation_z_degrees':-90,'head_replaced':False,'faces_hidden':0,'geometry_edited':False,'new_api_tasks':0,'animation_tested':False,'performance_tested':False}
(out/'full-model-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
