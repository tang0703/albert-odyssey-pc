"""Reopen the local cloud head bundle in Blender; never calls Tripo."""
from pathlib import Path
import hashlib,json
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1';ART=BASE/'cloud-ready-01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pins={BASE/'eye-color-18/head-editable.blend':'0a7422ec9708091a33a2ee422d79b58da1e6cc2c0c63e649f71d12d338e4c21b',
 BASE/'refined-08/head-editable.blend':'9bd38493e34f3b3ec979f3b6617f5475b3bd50265fab61fae44d81d199dd14e5',
 BASE/'tripo-out/player-head-tripo-01-890ddc6a/model.glb':'e3abeabdca43b6d232cd5728fccd8f6b2b0f7f4712de83b7d5817619d61e0b7b',
 BASE/'texture-input-01/head-visible-neutral.glb':'bd0dda2f958685c00539b591ca54f2ef1da72a4aca41f3b98c0772a70917bbc6'}
for path,expected in pins.items():assert sha(path)==expected,path
manifest=json.loads((ART/'unity-inputs.json').read_bytes())
for name,expected in manifest['files'].items():assert Path(name).name==name and sha(ART/name)==expected,name
conversion=json.loads((ART/'blender-conversion.json').read_bytes())
assert sha(ART/'head-editable.blend')==conversion['blend_sha256']
bpy.ops.wm.open_mainfile(filepath=str(ART/'head-editable.blend'))
assert len(bpy.data.actions)==0
assert len(bpy.data.images)==9
for image in bpy.data.images:
    assert image.packed_file
    # Reopened packed images are lazily decoded; accessing pixels tests the data.
    assert len(image.pixels)>0 and np.isfinite(image.pixels[0]) and image.has_data
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
assert len(objects)==3 and sum(len(o.data.polygons) for o in objects)==1888196
for obj in objects:
    assert obj.animation_data is None and len(obj.modifiers)==0
    mesh=obj.data;assert len(mesh.uv_layers)==1
    uv=np.empty((len(mesh.loops),2),np.float32);mesh.uv_layers.active.data.foreach_get('uv',uv.ravel())
    assert np.isfinite(uv).all()
    assert all(s.material and s.material.name.startswith('CloudMaterial_') for s in obj.material_slots)
    for slot in obj.material_slots:
        nodes=slot.material.node_tree.nodes
        assert any(n.type=='BSDF_PRINCIPLED' for n in nodes)
        assert len([n for n in nodes if n.type=='TEX_IMAGE' and n.image])>=3
result={'passed':True,'scope':'local asset integrity and source preservation, not art acceptance',
 'source_hashes_unchanged':{str(p.relative_to(ROOT)):v for p,v in pins.items()},'unity_files_verified':len(manifest['files']),
 'blend_reopened':True,'packed_textures':9,'meshes':3,'triangles':1888196,'finite_uvs':True,
 'no_animations':True,'art_approved':False,'performance_tested':False}
(ART/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
