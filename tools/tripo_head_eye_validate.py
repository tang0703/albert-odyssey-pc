"""Re-open and validate a local static head bundle inside Blender."""
from pathlib import Path
import argparse,hashlib,json,sys
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--art',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);art=BASE/a.art
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
report=json.loads((art/'geometry-report.json').read_bytes());manifest=json.loads((art/'unity-inputs.json').read_bytes());palette=json.loads((art/'palette.json').read_bytes())
assert manifest['require_textures'] and report['source_sha256']=='9bd38493e34f3b3ec979f3b6617f5475b3bd50265fab61fae44d81d199dd14e5'
assert {'old-head.fbx','head-palette.fbx','palette.json','head-basecolor.png','eye-basecolor.png'}<=set(manifest['files'])
for name,expected in manifest['files'].items():
    assert Path(name).name==name and sha(art/name)==expected
assert sha(BASE/'refined-08/head-editable.blend')==report['source_sha256']
assert sha(BASE/'tripo-out/player-head-tripo-01-890ddc6a/model.glb')=='e3abeabdca43b6d232cd5728fccd8f6b2b0f7f4712de83b7d5817619d61e0b7b'
for path,expected in json.loads((BASE/'review-01/report.json').read_bytes())['previous_sources_unchanged'].items():assert sha(ROOT/path)==expected

def coords(collection):
    v=np.empty((len(collection),3),np.float32);collection.foreach_get('co',v.ravel());return v
def triangles(mesh):
    v=np.empty(len(mesh.loops),np.int32);mesh.loops.foreach_get('vertex_index',v);return v.reshape(-1,3)
bpy.ops.wm.open_mainfile(filepath=str(BASE/'refined-08/head-editable.blend'))
source=bpy.data.objects['TRIPO_HEAD_LOCAL_REFINED_STATIC'];dg=bpy.context.evaluated_depsgraph_get();m=bpy.data.meshes.new_from_object(source.evaluated_get(dg),depsgraph=dg)
sv=coords(m.vertices);sf=triangles(m);sn=np.empty((len(m.loops),3),np.float32);m.corner_normals.foreach_get('vector',sn.ravel())
removed=np.zeros(len(sf),bool)
for eye in report['eyes']:
    assert not set(eye['removed_source_face_ids']).intersection(eye['protected_eyelid_face_ids']), 'Protected eyelid removed'
    removed[eye['removed_source_face_ids']]=True
bpy.ops.wm.open_mainfile(filepath=str(art/'head-editable.blend'));body=bpy.data.objects['HeadRetainedSurface'];bm=body.data
assert np.array_equal(coords(bm.vertices),sv)
assert np.array_equal(triangles(bm),sf)
mask=np.empty(len(bm.polygons),bool);bm.attributes['source_eye_hidden'].data.foreach_get('value',mask)
assert np.array_equal(mask,removed)
material_indices=np.empty(len(bm.polygons),np.int32);bm.polygons.foreach_get('material_index',material_indices)
hidden_index=list(mat.name for mat in bm.materials).index('SourceEyeHidden')
assert np.array_equal(material_indices==hidden_index,removed)
assert palette['SourceEyeHidden']['alpha_clip'] and palette['SourceEyeHidden']['linear_color'][3]==0
preserved=np.empty((len(bm.loops),3),np.float32);bm.attributes['protected_source_normal'].data.foreach_get('vector',preserved.ravel())
assert np.array_equal(preserved,sn)
rendered=np.empty_like(sn);bm.corner_normals.foreach_get('vector',rendered.ravel());assert np.array_equal(rendered,sn)
assert bpy.data.collections['Archive_original_head'].hide_render
eye_results=[]
for eye in report['eyes']:
    mesh=bpy.data.objects[eye['name']].data;v=coords(mesh.vertices);f=triangles(mesh);t=v[f]
    cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);areas=np.linalg.norm(cross,axis=1)*.5
    assert np.isfinite(v).all() and areas.min()>1e-14 and np.all(cross[:,1]<0),'Degenerate or reversed eye face'
    assert len(np.unique(np.sort(f,axis=1),axis=0))==len(f),'Duplicate eye faces'
    edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1);ed,count=np.unique(edges,axis=0,return_counts=True)
    assert count.max()==2 and int((count==1).sum())==eye['boundary_vertices']
    boundary_ids=np.unique(ed[count==1]);boundary=v[boundary_ids]
    source_ids=np.unique(sf[eye['removed_source_face_ids']]);source_vertices=sv[source_ids]
    # Exact boundary positions were copied from the retained source cut.
    source_set=set(map(tuple,source_vertices.tolist()));assert all(tuple(point) in source_set for point in boundary.tolist())
    eye_results.append({'name':eye['name'],'vertices':len(v),'triangles':len(f),'minimum_triangle_area':float(areas.min()),'boundary_vertices':len(boundary_ids),'duplicate_faces':0,'reversed_faces':0,'boundary_coordinates_exact':True})
for obj in [body]+[bpy.data.objects[e['name']] for e in report['eyes']]:
    mesh=obj.data;uv=np.empty((len(mesh.loops),2),np.float32);mesh.uv_layers.active.data.foreach_get('uv',uv.ravel())
    assert np.isfinite(uv).all() and uv.min()>=0 and uv.max()<=1
    assert not obj.animation_data and not obj.modifiers
    for mat in mesh.materials:
        entry=palette[mat.name];assert entry['base_texture'] in manifest['files']
        assert 0<=entry['roughness']<=1
for name in ('head-basecolor.png','eye-basecolor.png'):
    image=bpy.data.images.load(str(art/name),check_existing=False);assert tuple(image.size)==(2048,2048)
result={'passed':True,'source_hashes_unchanged':True,'retained_coordinates_exact':True,'source_faces_exact_with_explicit_eye_render_mask':True,'source_normal_attribute_exact':True,'rendered_blender_corner_normals_exact':True,'protected_eyelid_faces_retained':True,'blender_normal_encoding_max_angle_degrees':report['retained_normal_max_angle_degrees'],'eyes':eye_results,'texture_size':[2048,2048],'finite_uvs_in_range':True,'required_materials_and_hashes_present':True,'archive_retained_hidden':True,'animation_added':False,'performance_tested':False,'art_approved':False}
result.update({'scope':'source preservation, explicit eye render mask, mesh/UV/texture integrity only','visual_acceptance_passed':False})
(art/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
