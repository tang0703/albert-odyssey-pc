"""Reproduce refined-02 geometry study; palette attempt is NOT art approved.

Run with Blender. The original generated mesh and previous v2 stay unchanged.
Constant material labels are retained as diagnostics, not final UV materials.
"""
from pathlib import Path
import bpy,bmesh,math,json,hashlib,sys,argparse
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/hunyuan-head-v1'
parser=argparse.ArgumentParser();parser.add_argument('--out',default='refined-02');args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
OUT=BASE/args.out
if OUT.exists():raise RuntimeError('Preserve previous refinement')
OUT.mkdir()
bpy.ops.wm.open_mainfile(filepath=str(BASE/'prepared-01/head-editable.blend'))
bpy.context.preferences.filepaths.save_version=0
model=bpy.data.objects['HUNYUAN_HEAD_CLEAN_STATIC']
bpy.ops.object.select_all(action='DESELECT');model.select_set(True);bpy.context.view_layer.objects.active=model
# Remove isolated fragments, keeping the connected head. The archive is hidden.
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.separate(type='LOOSE');bpy.ops.object.mode_set(mode='OBJECT')
parts=[o for o in bpy.context.selected_objects if o.type=='MESH'];model=max(parts,key=lambda o:len(o.data.vertices))
removed=sum(len(o.data.vertices) for o in parts if o!=model)
for o in parts:
    if o!=model:bpy.data.objects.remove(o,do_unlink=True)
bpy.context.view_layer.objects.active=model;model.select_set(True)
model.name='HEAD_PILOT_REFINED_STATIC'
# Close tiny reconstruction perforations; keep the raw mesh in its archive.
model.data.remesh_voxel_size=.0045;model.data.use_remesh_preserve_volume=True
bpy.ops.object.voxel_remesh()
smooth=model.modifiers.new('Small reconstruction noise only','SMOOTH');smooth.factor=.45;smooth.iterations=4;bpy.ops.object.modifier_apply(modifier=smooth.name)
# Soft-selection edits: compress the duplicate feather-like rear protrusion
# into the surrounding hair volume; soften the inflated lip ridge.
weights=model.vertex_groups.new(name='Secondary feather ridge smoothing')
for v in model.data.vertices:
    x,y,z=v.co
    w=math.exp(-(((x-.37)/.18)**2+((y-.13)/.095)**2+((z-.65)/.17)**2))
    if w>.005:
        v.co.x-=.145*w;v.co.y+=.018*w;weights.add([v.index],w,'REPLACE')
    mouth=math.exp(-((x/.075)**2+((z-.13)/.035)**2)*2)
    if y<-.25:v.co.y+=.013*mouth
smooth=model.modifiers.new('Secondary ridge local smoothing','SMOOTH');smooth.factor=.8;smooth.iterations=22;smooth.vertex_group=weights.name;bpy.ops.object.modifier_apply(modifier=smooth.name)
dec=model.modifiers.new('Static review mesh reduction','DECIMATE');dec.ratio=.5;bpy.ops.object.modifier_apply(modifier=dec.name)
for p in model.data.polygons:p.use_smooth=True
materials={}
def make(name,srgb,rough=.75):
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in srgb]
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*linear,1)
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=m.diffuse_color;bs.inputs['Roughness'].default_value=rough
    materials[name]=m;return m
for name,color in [('PilotHair',(.43,.21,.075)),('PilotSkin',(.96,.69,.43)),('PilotBand',(.38,.46,.17)),('PilotScarf',(.59,.10,.08)),('PilotIvory',(.9,.85,.68)),('PilotEyeWhite',(.96,.94,.85)),('PilotIris',(.31,.13,.035)),('PilotPupil',(.035,.018,.008))]:make(name,color)
model.data.materials.clear()
for m in materials.values():model.data.materials.append(m)
indices={k:i for i,k in enumerate(materials)}
verts=np.array([v.co[:] for v in model.data.vertices]);lo=verts.min(0);hi=verts.max(0)
for p in model.data.polygons:
    x,y,z=p.center
    name='PilotHair'
    # Deliberately simple flat study colors. No source lighting or shadow pixels
    # are painted onto the mesh. Final UV/material boundaries remain pending.
    if z<.14:name='PilotScarf'
    if .10<z<.37 and y<.12 and abs(x)<.36:name='PilotSkin'
    if .365<z<.475 and -.43<y<.18 and abs(x)<.36:name='PilotBand'
    if z>.30 and y<-.455:name='PilotHair'
    if ((x-.35)/.12)**2+((y+.11)/.105)**2+((z-.65)/.22)**2<1 and x>.255:name='PilotIvory'
    if y<-.25:
        for cx in (-.125,.125):
            if ((x-cx)/.061)**2+((z-.242)/.048)**2<1:
                name='PilotEyeWhite'
                if ((x-cx)/.027)**2+((z-.24)/.038)**2<1:name='PilotIris'
                if ((x-cx)/.012)**2+((z-.24)/.029)**2<1:name='PilotPupil'
    p.material_index=indices[name]
bpy.ops.object.select_all(action='DESELECT');model.select_set(True);bpy.context.view_layer.objects.active=model
bpy.ops.export_scene.fbx(filepath=str(OUT/'head-palette.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
# Import old static v2 mesh solely for an equal-height head comparison.
oldsource=ROOT/'art/unity/player-refined-v2/player-refined.blend'
with bpy.data.libraries.load(str(oldsource),link=False) as (available,target):
    target.objects=['MAP001_PLAYER_REFINED_STATIC']
old=target.objects[0];collection=bpy.data.collections.new('V2_HEAD_COMPARISON_ONLY');bpy.context.scene.collection.children.link(collection);collection.objects.link(old)
bm=bmesh.new();bm.from_mesh(old.data);bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.co.z<.635],context='VERTS');bm.to_mesh(old.data);bm.free()
lower=min(v.co.z for v in old.data.vertices);upper=max(v.co.z for v in old.data.vertices)
for v in old.data.vertices:v.co=Vector((v.co.x/(upper-lower),v.co.y/(upper-lower),(v.co.z-lower)/(upper-lower)))
bpy.ops.object.select_all(action='DESELECT');old.select_set(True);bpy.context.view_layer.objects.active=old
bpy.ops.export_scene.fbx(filepath=str(OUT/'old-head.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
palette={m.name:{'linear_color':list(m.diffuse_color),'roughness':float(m.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value)} for m in list(materials.values())+list(old.data.materials)}
(OUT/'palette.json').write_text(json.dumps(palette,indent=2)+'\n',encoding='utf-8')
collection.hide_render=True;collection.hide_viewport=True
bpy.ops.object.select_all(action='DESELECT');model.select_set(True);bpy.context.view_layer.objects.active=model
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'head-refined.blend'))
report={'scope':'head-only static geometry pilot, not approved final art','removed_fragment_vertices':removed,'vertices':len(model.data.vertices),'faces':len(model.data.polygons),'voxel_size':.0045,'changes':['removed disconnected reconstruction fragments','closed small holes and smoothed reconstruction noise','softened duplicate rear ridge into hair volume','reduced exaggerated mouth ridge','flat semantic palette, not texture projection lighting'],'limitations':['eyes and palette boundaries are preliminary','no production retopology or UV textures','rear hair and feather junction require visual review'],'old_geometry_source_sha256':hashlib.sha256(oldsource.read_bytes()).hexdigest(),'animation_created':False,'performance_tested':False}
(OUT/'refinement.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(OUT/'unity-inputs.json').write_text(json.dumps({'files':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in ('head-palette.fbx','old-head.fbx','palette.json')}},indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
