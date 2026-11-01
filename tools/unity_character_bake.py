"""Bake the character's own UV atlas, without light/shadow in its albedo."""
from pathlib import Path
import bpy,json,hashlib,numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'art/unity/player-refined-v1';TEX=OUT/'textures'
if (OUT/'review-lock.json').exists():raise RuntimeError('Frozen review')
TEX.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(OUT/'player-refined.blend'))
bpy.context.preferences.filepaths.save_version=0
model=bpy.data.objects['MAP001_PLAYER_REFINED_STATIC'];bpy.context.view_layer.objects.active=model;model.select_set(True)
materials=list(model.data.materials)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=8;scene.render.bake.margin=8
scene.render.bake.use_pass_direct=False;scene.render.bake.use_pass_indirect=False;scene.render.bake.use_pass_color=True
def target(name,noncolor=False):
    image=bpy.data.images.new(name,2048,2048,alpha=True,float_buffer=False)
    if noncolor:image.colorspace_settings.name='Non-Color'
    for mat in materials:
        mat.use_fake_user=True;n=mat.node_tree.nodes.new('ShaderNodeTexImage');n.name='C2 bake destination';n.image=image;mat.node_tree.nodes.active=n
    return image
def bake(name,kind,noncolor=False):
    image=target(name,noncolor);bpy.ops.object.bake(type=kind)
    path=TEX/(name+'.png');image.filepath_raw=str(path);image.file_format='PNG';image.save()
    for mat in materials:mat.node_tree.nodes.remove(mat.node_tree.nodes['C2 bake destination'])
    return image
albedo=bake('character-albedo','DIFFUSE')
normal=bake('character-normal','NORMAL',True)
ao=bake('character-occlusion','AO',True)
# Parameter-only emission yields per-texel material values, not scene lighting.
connections=[]
for mat in materials:
    n=mat.node_tree.nodes;bs=n.get('Principled BSDF');out=next(o for o in n if o.type=='OUTPUT_MATERIAL');em=n.new('ShaderNodeEmission');em.inputs['Color'].default_value=(bs.inputs['Metallic'].default_value,bs.inputs['Roughness'].default_value,0,1);mat.node_tree.links.new(em.outputs[0],out.inputs['Surface']);connections.append((mat,out,bs,em))
params=bake('character-parameters','EMIT',True)
for mat,out,bs,em in connections:mat.node_tree.links.new(bs.outputs['BSDF'],out.inputs['Surface']);mat.node_tree.nodes.remove(em)
pixels=np.empty(2048*2048*4,dtype=np.float32);params.pixels.foreach_get(pixels);pixels=pixels.reshape(-1,4)
ambient=np.empty(2048*2048*4,dtype=np.float32);ao.pixels.foreach_get(ambient);ambient=ambient.reshape(-1,4)
rough=pixels[:,1].copy();pixels[:,1]=ambient[:,0];pixels[:,2]=rough;pixels[:,3]=1-rough
mask=bpy.data.images.new('character-mask',2048,2048,alpha=True);mask.colorspace_settings.name='Non-Color';mask.pixels.foreach_set(pixels.ravel());mask.filepath_raw=str(TEX/'character-mask.png');mask.file_format='PNG';mask.save()
mat=bpy.data.materials.new('MAP001 Refined Atlas');mat.use_nodes=True;n=mat.node_tree.nodes;bs=n.get('Principled BSDF')
for image in [albedo,normal,mask]:image.pack()
color=n.new('ShaderNodeTexImage');color.image=albedo;mat.node_tree.links.new(color.outputs['Color'],bs.inputs['Base Color'])
norm=n.new('ShaderNodeTexImage');norm.image=normal;mapnode=n.new('ShaderNodeNormalMap');mat.node_tree.links.new(norm.outputs['Color'],mapnode.inputs['Color']);mat.node_tree.links.new(mapnode.outputs[0],bs.inputs['Normal'])
masknode=n.new('ShaderNodeTexImage');masknode.image=mask;channels=n.new('ShaderNodeSeparateColor');mat.node_tree.links.new(masknode.outputs[0],channels.inputs[0]);mat.node_tree.links.new(channels.outputs['Red'],bs.inputs['Metallic']);mat.node_tree.links.new(channels.outputs['Blue'],bs.inputs['Roughness'])
model.data.materials.clear();model.data.materials.append(mat)
for poly in model.data.polygons:poly.material_index=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'player-textured.blend'))
bpy.ops.export_scene.fbx(filepath=str(OUT/'player-static.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
files={p.relative_to(OUT).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.rglob('*') if p.is_file() and p.suffix in ('.png','.fbx','.blend')}
record={'schema':'ao_character_static_review_v1','status':'pending_user_review','height':1.125,'camera_pitch':45,'files':files,'textures':{'albedo':'textures/character-albedo.png','normal':'textures/character-normal.png','mask':'textures/character-mask.png'},'mask_channels':{'r':'metallic','g':'ambient_occlusion','b':'roughness','a':'smoothness'},'normal_space':'tangent OpenGL','albedo_lighting_baked':False,'rig_finalized':False,'animation_finalized':False,'performance_tested':False}
(OUT/'material-manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('CHARACTER_BAKE_DONE')
