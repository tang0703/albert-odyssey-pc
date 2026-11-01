"""Bake editable Blender procedural material swatches for Unity Lit.
Offline asset creation, not a runtime performance measurement.
"""
from pathlib import Path
import bpy,json,hashlib,re
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'art/unity/startroom-u4'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'startroom-rig.blend'))
bpy.context.preferences.filepaths.save_version=0
materials=list(bpy.data.materials)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=2);plane=bpy.context.object
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=1
scene.render.bake.use_pass_direct=False;scene.render.bake.use_pass_indirect=False;scene.render.bake.use_pass_color=True
folder=OUT/'textures';folder.mkdir(exist_ok=True)
rows=[]
for material in materials:
    if not material.use_nodes:continue
    bs=material.node_tree.nodes.get('Principled BSDF')
    if bs is None:continue
    row={'name':material.name,'base_color':list(material.diffuse_color),'roughness':float(bs.inputs['Roughness'].default_value),'metallic':float(bs.inputs['Metallic'].default_value)}
    if bs.inputs['Base Color'].is_linked:
        safe=re.sub(r'[^a-z0-9]+','-',material.name.lower()).strip('-')
        image=bpy.data.images.new('Bake '+safe,512,512,alpha=False)
        node=material.node_tree.nodes.new('ShaderNodeTexImage');node.image=image;material.node_tree.nodes.active=node
        plane.data.materials.clear();plane.data.materials.append(material)
        bpy.ops.object.bake(type='DIFFUSE')
        path=folder/(safe+'.png');image.filepath_raw=str(path);image.file_format='PNG';image.save()
        row['albedo']='textures/'+path.name;row['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        material.node_tree.nodes.remove(node)
    rows.append(row)
(OUT/'materials.json').write_text(json.dumps({'schema':'ao_unity_lit_materials_v1','materials':rows,'performance_tested':False,'notes':['512px diffuse color swatches baked from editable Blender procedural materials.','Unity applies metallic/roughness separately; lighting is not baked into albedo.']},indent=2)+'\n',encoding='utf-8')
print('MATERIAL_BAKE_DONE',len(rows))
