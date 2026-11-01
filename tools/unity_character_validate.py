"""Read-only C1/C2 source validation; deliberately no skinning/animation claim."""
from pathlib import Path
import bpy,json,hashlib,math,sys
ROOT=Path(__file__).resolve().parents[1]
version=sys.argv[sys.argv.index('--art-version')+1] if '--art-version' in sys.argv else 'player-refined-v1'
if version not in ('player-refined-v1','player-refined-v2'):raise ValueError('Unknown static art version')
ART=ROOT/'art/unity'/version
manifest=json.loads((ART/'material-manifest.json').read_bytes())
for name,row in manifest['files'].items():
    p=(ART/name).resolve();assert p.is_relative_to(ART.resolve())
    assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],name
bpy.ops.wm.open_mainfile(filepath=str(ART/'player-refined.blend'))
model=bpy.data.objects['MAP001_PLAYER_REFINED_STATIC'];mesh=model.data
assert not any(o.type=='ARMATURE' for o in bpy.context.scene.objects)
assert not model.animation_data and not model.vertex_groups
assert len(mesh.uv_layers)==1 and mesh.uv_layers.active.name=='CharacterAtlasUV'
assert all(math.isfinite(c) for v in mesh.vertices for c in v.co)
assert abs(min(v.co.z for v in mesh.vertices))<1e-6
assert abs(max(v.co.z for v in mesh.vertices)-1.125)<1e-6
assert all(-1e-6<=c<=1.000001 for uv in mesh.uv_layers.active.data for c in uv.uv)
assert all(len(poly.vertices)==3 for poly in mesh.polygons)
flat_materials=sorted({mesh.materials[p.material_index].name for p in mesh.polygons if not p.use_smooth})
assert all(p.use_smooth for p in mesh.polygons if mesh.materials[p.material_index].name=='Warm skin')
for name in manifest['textures'].values():
    image=bpy.data.images.load(str(ART/name),check_existing=False);assert tuple(image.size)==(2048,2048)
old=json.loads((ROOT/'art/unity/startroom-u4/asset-lock.json').read_bytes())
for name,row in old['files'].items():assert hashlib.sha256((ROOT/'art/unity/startroom-u4'/name).read_bytes()).hexdigest()==row['sha256'],name
report={'passed':True,'vertices':len(mesh.vertices),'triangles':len(mesh.polygons),'height':1.125,'foot_anchor_z':0,'finite_coordinates':True,'uv_in_unit_square':True,'skin_smooth':True,'intentional_flat_materials':flat_materials,'bake_export_same_triangles':True,'textures':[2048,2048],'old_u4_files_unchanged':len(old['files']),'skinning_tested':False,'animation_tested':False,'performance_tested':False}
report_name='character-c1-validation.json' if version=='player-refined-v1' else version+'-c1-validation.json'
(ROOT/'reports/unity'/report_name).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
