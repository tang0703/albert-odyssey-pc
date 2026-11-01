"""Static body fitting to the approved head. Local Blender work, no API/animation.

Preserve approved head vertex data/materials; reuse explicitly named editable
body surfaces from the earlier unapproved study, reshape only those surfaces.
"""
from pathlib import Path
import argparse,hashlib,json,math,shutil,sys
import bpy,numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--version',default='body-fit-01');a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
OUT=BASE/a.version;OUT.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
approval=json.loads((ROOT/'docs/tripo-head-cloud-texture-approval.json').read_bytes())
for file,h in approval['files'].items():assert sha(ROOT/file)==h,file
HEAD=BASE/'cloud-ready-01';BODY=ROOT/'art/unity/player-refined-v2/player-refined.blend'
bpy.ops.wm.open_mainfile(filepath=str(HEAD/'head-editable.blend'))
head=list(bpy.context.scene.objects)
def mesh_digest(o):
    m=o.data;v=np.empty((len(m.vertices),3),np.float32);m.vertices.foreach_get('co',v.ravel())
    loops=np.empty(len(m.loops),np.int32);m.loops.foreach_get('vertex_index',loops)
    uv=np.empty((len(m.loops),2),np.float32);m.uv_layers.active.data.foreach_get('uv',uv.ravel())
    n=np.empty((len(m.loops),3),np.float32);m.corner_normals.foreach_get('vector',n.ravel())
    return hashlib.sha256(v.tobytes()+loops.tobytes()+uv.tobytes()+n.tobytes()).hexdigest()
original={o.name:mesh_digest(o) for o in head}
# Uniform presentation transform only; head/scarf geometry remains unchanged.
head_scale=.545;head_base=.580
for o in head:o.scale*=head_scale;o.location=o.location*head_scale+Vector((0,0,head_base))

# The approved asset is a bust. Hide only its lower green/linen clothing in this
# fitting copy; preserve the face, neck, red scarf, mesh data and original file.
# Classification uses source texture plus a small lower-bust region, not height alone.
retained=bpy.data.objects['HeadRetainedSurface'];m=retained.data
co=np.empty((len(m.vertices),3),np.float32);m.vertices.foreach_get('co',co.ravel())
indices=np.empty(len(m.loops),np.int32);m.loops.foreach_get('vertex_index',indices);indices=indices.reshape(-1,3)
original_z=co[:,2]+.5;face_z=original_z[indices].max(axis=1)
uvs=np.empty((len(m.loops),2),np.float32);m.uv_layers.active.data.foreach_get('uv',uvs.ravel())
uvs=uvs.reshape(-1,3,2).mean(axis=1)
im=bpy.data.images['HeadRetainedSurface_base_color'];w,h=im.size
pixels=np.empty(w*h*4,np.float32);im.pixels.foreach_get(pixels);pixels=pixels.reshape(h,w,4)
rgb=pixels[np.clip((uvs[:,1]*h).astype(int),0,h-1),np.clip((uvs[:,0]*w).astype(int),0,w-1),:3]
r,g,b=rgb.T
green=(g>r*.94)&(g>b*1.25)
linen=(r>g)&(r<g*1.22)&(g>b*1.15)
hide=(face_z<.155)&(green|linen)
assert 1000<int(hide.sum())<200000,int(hide.sum())
hidden=bpy.data.materials.new('SourceBustHidden');hidden.use_nodes=True;hidden.diffuse_color=(0,0,0,0)
hidden.node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value=0
m.materials.append(hidden);mi=np.zeros(len(m.polygons),np.int32);mi[hide]=len(m.materials)-1;m.polygons.foreach_set('material_index',mi)

prefixes=('Tunic torso','Open V linen','Tailored sleeve','Rolled linen','Sleeve leather','Sleeve brass',
 'Split tunic panel','Flat woven tunic','Waist leather','Belt edge','Square rounded belt','Buckle pin','Belt punched',
 'Gathered trouser','Forearm surface','Boot continuous','Stacked boot','Boot turned','Boot toe','Boot instep','Boot cuff','Boot soft')
with bpy.data.libraries.load(str(BODY),link=False) as (source,target):
    # Only editable counterparts: .001 or higher; the merged model is excluded.
    target.collections=['EDITABLE - unrigged reference surfaces']
collection=target.collections[0];bpy.context.scene.collection.children.link(collection)
collection.hide_render=False;collection.hide_viewport=False;collection.name='Body - editable static fitting'
parts=[]
for o in list(collection.objects):
    if not o.name.startswith(prefixes):bpy.data.objects.remove(o,do_unlink=True);continue
    parts.append(o);o.hide_set(False);o.hide_render=False;o.hide_viewport=False
    for v in o.data.vertices:
        x,y,z=v.co
        # Taller torso, wider relaxed arm stance; no skeleton/root motion involved.
        x*=1.10;y*=1.12;z*=1.07
        if o.name.startswith('Tunic torso') and z<.49:
            z=.447+(z-.399)*(.49-.447)/(.49-.399)
        if z>.54:z=.54+(z-.54)*.55
        if o.name.startswith('Gathered trouser'):
            side=1 if x>0 else -1;center=side*.065
            x=center+(x-center)*1.12;y*=1.08
        if o.name.startswith(('Boot','Stacked boot')):
            side=1 if x>0 else -1;center=side*.076
            x=center+(x-center)*1.06
        v.co=(x,y,z)
    o.data.update()
assert len(parts)>35
# A new body-side scarf underlap covers the original bust's planar cut. It does
# not edit the approved scarf. Keep it named separately for the user's review.
def cloth_mesh(name,vertices,faces):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);collection.objects.link(obj)
    mat=bpy.data.materials.get('Underlap red') or bpy.data.materials.new('Underlap red');mesh.materials.append(mat)
    for poly in mesh.polygons:poly.use_smooth=True
    parts.append(obj);return obj
vertices=[];faces=[];ns=96;nt=20
for j in range(ns):
    theta=math.tau*j/ns;front=max(0,-math.sin(theta))
    for k in range(nt):
        phi=math.tau*k/nt
        vertices.append(((.109+.015*math.cos(phi))*math.cos(theta),(.085+.012*math.cos(phi))*math.sin(theta),.600-.035*front+.025*math.sin(phi)))
for j in range(ns):
    for k in range(nt):faces.append((j*nt+k,((j+1)%ns)*nt+k,((j+1)%ns)*nt+(k+1)%nt,j*nt+(k+1)%nt))
cloth_mesh('New scarf lower underlap',vertices,faces)
vertices=[];faces=[]
for j in range(24):
    t=j/23;z=.572-.078*t;x=-.033+.025*t;width=.029*(1-t)+.001
    for k in range(9):
        u=k/4-1;vertices.append((x+u*width,-.100+.015*t-.005*(1-u*u),z+.003*math.sin(u*math.pi)*t))
for j in range(23):
    for k in range(8):i=j*9+k;faces.append((i,i+9,i+10,i+1))
fall=cloth_mesh('New scarf tapered underlap',vertices,faces)
sol=fall.modifiers.new('Cloth thickness','SOLIDIFY');sol.thickness=.002
bpy.context.view_layer.objects.active=fall;fall.select_set(True);bpy.ops.object.modifier_apply(modifier=sol.name)
# Remove old baked shadow/tone materials; retain separable silhouette components.
palette={k:v for k,v in json.loads((HEAD/'palette.json').read_bytes()).items() if k.startswith('CloudMaterial_')}
palette['SourceBustHidden']={'linear_color':[0,0,0,0],'roughness':1,'alpha_clip':True}
sizes={k:v for k,v in json.loads((HEAD/'texture-sizes.json').read_bytes()).items() if k.startswith('cloud-')}
for name in sizes:shutil.copyfile(HEAD/name,OUT/name)
colors={'Warm skin':(.73,.40,.20),'Olive cloth':(.26,.32,.085),'Olive shade':(.19,.24,.055),
 'Trousers':(.32,.34,.105),'Linen':(.68,.57,.36),'Leather':(.18,.069,.027),
 'Leather edge':(.28,.115,.041),'Boot turn':(.43,.23,.085),'Brass':(.58,.32,.085),'Sole':(.055,.029,.014),'Underlap red':(.43,.029,.024)}
materials={};rng=np.random.default_rng(174)
for name,color in colors.items():
    mat=bpy.data.materials.new('Body_'+name.replace(' ','_'));mat.use_nodes=True
    rough=.82 if name in ('Olive cloth','Olive shade','Trousers','Linen') else .55 if name in ('Leather','Leather edge','Boot turn') else .66
    metal=.65 if name=='Brass' else 0
    bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal
    mat.diffuse_color=(*color,1);materials[name]=mat
    entry={'linear_color':[*color,1],'roughness':rough,'metallic':metal}
    if name not in ('Brass','Warm skin'):
        # Parametric neutral weave/grain, no lighting or projected concept image.
        n=512;yy,xx=np.mgrid[:n,:n];grain=rng.normal(0,.009,(n,n))
        weave=(.024*np.sin(xx*math.pi/2)*np.cos(yy*math.pi/2)) if name in ('Olive cloth','Olive shade','Trousers','Linen') else .004*np.sin(xx*.2+yy*.4)
        variation=1+grain+weave
        linear=np.clip(np.asarray(color)[None,None,:]*variation[:,:,None],0,1)
        pixels=np.ones((n,n,4),np.float32);pixels[:,:,:3]=np.where(linear<=.0031308,linear*12.92,1.055*linear**(1/2.4)-.055)
        image=bpy.data.images.new(mat.name+'_albedo',n,n,alpha=True);image.pixels.foreach_set(pixels.ravel())
        file=mat.name+'-basecolor.png';image.filepath_raw=str(OUT/file);image.file_format='PNG';image.save();image.pack()
        node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image;mat.node_tree.links.new(node.outputs['Color'],bs.inputs['Base Color'])
        entry['base_texture']=file;entry['linear_color']=[1,1,1,1];sizes[file]=[n,n]
    palette[mat.name]=entry
for o in parts:
    for slot in o.material_slots:
        key=slot.material.name.split('.')[0];assert key in materials,(o.name,key);slot.material=materials[key]
    # New per-part UVs for the repeating cloth/leather pattern; the head UV is untouched.
    mesh=o.data
    if not mesh.uv_layers:mesh.uv_layers.new(name='BodyPreviewUV')
    uv=mesh.uv_layers.active
    for poly in mesh.polygons:
        normal=poly.normal;axis=max(range(3),key=lambda i:abs(normal[i]));axes=[i for i in range(3) if i!=axis]
        for li in poly.loop_indices:
            co=mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv=((co[axes[0]]*3)%1,(co[axes[1]]*3)%1)
    for slot in o.material_slots:
        palette[slot.material.name]['wrap']='repeat'
# Preserve exact head mesh/normal/UV data after positioning.
assert all(mesh_digest(o)==original[o.name] for o in head)
bpy.context.view_layer.update()
objects=head+parts
floor=min((o.matrix_world@Vector(c)).z for o in objects for c in o.bound_box)
top=max((o.matrix_world@Vector(c)).z for o in objects for c in o.bound_box)
assert abs(top-1.125)<1e-5 and abs(floor)<.01,(floor,top)
bpy.ops.object.select_all(action='DESELECT')
for o in objects:o.select_set(True)
bpy.context.view_layer.objects.active=head[0]
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'player-body-preview.blend'))
bpy.ops.export_scene.fbx(filepath=str(OUT/'player-static.fbx'),use_selection=True,object_types={'MESH'},
    axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False,use_mesh_modifiers=False,path_mode='STRIP')
(OUT/'palette.json').write_text(json.dumps(palette,indent=2)+'\n')
files=['player-static.fbx','palette.json',*sizes]
manifest={'schema':'ao_approved_head_body_static_v1','files':{f:sha(OUT/f) for f in files},'texture_sizes':sizes,
 'height':1.125,'head_approval_sha256':sha(ROOT/'docs/tripo-head-cloud-texture-approval.json')}
(OUT/'unity-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
report={'version':a.version,'height':top-floor,'floor':floor,'head_uniform_scale':head_scale,'head_base_z':head_base,
 'head_mesh_uv_normals_unchanged':original,'head_source_sha256':sha(HEAD/'head-editable.blend'),
 'body_source_sha256':sha(BODY),'body_source':'editable body parts from player-refined-v2, no old head/scarf',
 'body_parts':len(parts),'body_changes':['wider silhouette','lowered neckline fitted below scarf','fuller trouser legs','broader boot toe','cloth and leather parameter textures'],
 'head_and_scarf_local_sculpting':False,'lower_bust_clothing_faces_hidden_in_fitting_copy':int(hide.sum()),
 'hidden_face_ids':np.flatnonzero(hide).tolist(),'body_approved':False,'animation_created':False,'gameplay_changed':False,'performance_tested':False,'api_tasks':0}
(OUT/'geometry-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='hidden_face_ids'}))
