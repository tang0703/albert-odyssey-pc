"""Local static head study: replace eye patches, retain source geometry/normals elsewhere.

Runs in Blender. No cloud calls, rig, animation or gameplay changes.
"""
from pathlib import Path
import argparse, hashlib, json, math, shutil, sys
import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--no-render',action='store_true')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=BASE/a.out;out.mkdir(exist_ok=False)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
source=BASE/'refined-08/head-editable.blend';source_sha=sha(source)
assert source_sha=='9bd38493e34f3b3ec979f3b6617f5475b3bd50265fab61fae44d81d199dd14e5','Baseline changed'
bpy.ops.wm.open_mainfile(filepath=str(source));bpy.context.preferences.filepaths.save_version=0
old=bpy.data.objects['TRIPO_HEAD_LOCAL_REFINED_STATIC'];dg=bpy.context.evaluated_depsgraph_get()
m=bpy.data.meshes.new_from_object(old.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
v=np.empty((len(m.vertices),3),np.float32);m.vertices.foreach_get('co',v.ravel())
f=np.empty(len(m.loops),np.int32);m.loops.foreach_get('vertex_index',f);f=f.reshape(-1,3)
norm=np.empty((len(m.loops),3),np.float32);m.corner_normals.foreach_get('vector',norm.ravel())
source_edges=np.empty((len(m.edges),2),np.int32);m.edges.foreach_get('vertices',source_edges.ravel())
source_edge_keys=np.sort(source_edges,axis=1).astype(np.int64);source_edge_keys=source_edge_keys[:,0]*len(v)+source_edge_keys[:,1]
edge_order=np.argsort(source_edge_keys);source_sharp=np.zeros(len(m.edges),bool)
if m.attributes.get('sharp_edge'):m.attributes['sharp_edge'].data.foreach_get('value',source_sharp)
centers=v[f].mean(1);remove=np.zeros(len(f),bool);eye_specs=[]

def make_mesh(name,verts,faces,normals=None):
    verts=np.asarray(verts,dtype=np.float32);faces=np.asarray(faces,dtype=np.int32)
    mesh=bpy.data.meshes.new(name);mesh.vertices.add(len(verts));mesh.vertices.foreach_set('co',verts.ravel())
    mesh.loops.add(faces.size);mesh.loops.foreach_set('vertex_index',faces.ravel())
    mesh.polygons.add(len(faces));mesh.polygons.foreach_set('loop_start',np.arange(len(faces),dtype=np.int32)*3)
    mesh.polygons.foreach_set('loop_total',np.full(len(faces),3,dtype=np.int32));mesh.update()
    mesh.polygons.foreach_set('use_smooth',np.ones(len(faces),dtype=bool))
    if normals is not None:
        new_edges=np.empty((len(mesh.edges),2),np.int32);mesh.edges.foreach_get('vertices',new_edges.ravel())
        new_keys=np.sort(new_edges,axis=1).astype(np.int64);new_keys=new_keys[:,0]*len(v)+new_keys[:,1]
        edge_indices=edge_order[np.searchsorted(source_edge_keys[edge_order],new_keys)]
        assert np.array_equal(source_edge_keys[edge_indices],new_keys)
        sharp=mesh.attributes.new('sharp_edge','BOOLEAN','EDGE')
        sharp.data.foreach_set('value',source_sharp[edge_indices])
        mesh.normals_split_custom_set(normals)
        # Preserve the exact source vectors as editable evidence. Blender's INT16
        # custom-normal encoding can quantize them on a rebuilt mesh.
        source_normal=mesh.attributes.new('protected_source_normal','FLOAT_VECTOR','CORNER')
        source_normal.data.foreach_set('vector',np.asarray(normals,np.float32).ravel())
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);return obj

def eye_patch(side,cx,cz,rx,rz):
    u=(centers[:,0]-cx)/rx;w=(centers[:,2]-cz)/rz
    rr=np.hypot(u,w)
    initial=np.flatnonzero((rr<.87)&(centers[:,1]<-.155)&(centers[:,1]>-.28))
    # Independently identify eyelid undersides in the original, smaller region.
    # Enlarging the surface must never absorb those protected faces.
    ii=np.unique(f[initial]);pp,iv=np.unique(np.round(v[ii],6),axis=0,return_inverse=True)
    ll=np.full(len(v),-1,dtype=np.int32);ll[ii]=iv;tt=ll[f[initial]];par=list(range(len(pp)))
    def find(k):
        while par[k]!=k:par[k]=par[par[k]];k=par[k]
        return k
    for t in tt:
        for j in (1,2):par[find(int(t[j]))]=find(int(t[0]))
    roots0=np.array([find(int(k)) for k in tt[:,0]]);labs,cnts=np.unique(roots0,return_counts=True)
    protected_ids=initial[roots0!=labs[np.argmax(cnts)]]
    # Retain the safe eye opening. Expanded cuts were rejected because they
    # absorbed eyelid undersides or produced a pinched boundary.
    candidate_mask=(rr<.87)&(centers[:,1]<-.155)&(centers[:,1]>-.28)
    candidate_mask[protected_ids]=False
    candidates=np.flatnonzero(candidate_mask)
    ids=np.unique(f[candidates]);points,inv=np.unique(np.round(v[ids],6),axis=0,return_inverse=True)
    lookup=np.full(len(v),-1,dtype=np.int32);lookup[ids]=inv;tri=lookup[f[candidates]]
    # Select the main connected eye surface, excluding separate eyelid underside patches.
    parent=list(range(len(points)))
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for t in tri:
        for j in (1,2):
            aa,bb=root(int(t[0])),root(int(t[j]));parent[bb]=aa
    roots=np.array([root(int(i)) for i in tri[:,0]]);labels,counts=np.unique(roots,return_counts=True)
    selected=roots==labels[np.argmax(counts)];tri=tri[selected];face_ids=candidates[selected]
    remove[face_ids]=True
    edges=np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]);edges=np.sort(edges,axis=1)
    edges,c=np.unique(edges,axis=0,return_counts=True);boundary=edges[c==1]
    adj={int(k):[] for k in boundary.ravel()}
    for aa,bb in boundary:adj[int(aa)].append(int(bb));adj[int(bb)].append(int(aa))
    assert all(len(ns)==2 for ns in adj.values()),'Eye boundary is not a simple cycle'
    first=min(adj);ring_ids=[first];prev=-1;current=first
    while True:
        nxt=next(k for k in adj[current] if k!=prev)
        if nxt==first:break
        assert nxt not in ring_ids
        ring_ids.append(nxt);prev,current=current,nxt
    assert len(ring_ids)==len(adj),'Multiple holes require inspection'
    # Use exact source positions at the seam (quantization only identified welded vertices).
    representatives=np.full(len(points),-1,dtype=np.int32);representatives[inv]=ids
    ring=v[representatives[ring_ids]].astype(np.float64)
    area=np.sum(ring[:,0]*np.roll(ring[:,2],-1)-np.roll(ring[:,0],-1)*ring[:,2])
    if area<0:ring=ring[::-1]
    sample=v[np.unique(f[face_ids])];su=(sample[:,0]-cx)/rx;sw=(sample[:,2]-cz)/rz
    A=np.column_stack([np.ones(len(su)),su,sw,su*su,su*sw,sw*sw]);target=sample[:,1];weights=np.ones(len(su))
    for _ in range(10):
        coeff=np.linalg.lstsq(A*np.sqrt(weights[:,None]),target*np.sqrt(weights),rcond=None)[0]
        res=target-A@coeff;sig=max(.0002,1.4826*np.median(np.abs(res-np.median(res))))
        weights=np.minimum(1,1.5*sig/(np.abs(res)+1e-12))
    def depth(xx,zz):
        uu=(xx-cx)/rx;ww=(zz-cz)/rz
        return coeff[0]+coeff[1]*uu+coeff[2]*ww+coeff[3]*uu*uu+coeff[4]*uu*ww+coeff[5]*ww*ww
    nt=len(ring);coords2=[Vector((point[0],point[2])) for point in ring]
    for xx in np.linspace(cx-rx,cx+rx,45):
        for zz in np.linspace(cz-rz,cz+rz,45):
            if np.hypot((xx-cx)/rx,(zz-cz)/rz)<1.02:coords2.append(Vector((xx,zz)))
    xy,ed,ff,orig,_,_=delaunay_2d_cdt(coords2,[],[list(range(nt))],1,1e-8,True)
    verts=[];boundary_error=[];boundary_indices=[]
    for point,ids in zip(xy,orig):
        boundary_ids=[i for i in ids if i<nt]
        xx,zz=point;rr=float(np.hypot((xx-cx)/rx,(zz-cz)/rz))
        if boundary_ids:
            coord=ring[boundary_ids[0]].copy();boundary_error.append(0.);boundary_indices.append(len(verts))
        else:
            coord=[xx,float(depth(xx,zz)),zz]
        verts.append(coord)
    faces=[list(t) for t in ff]
    assert all(len(t)==3 for t in faces)
    verts=np.asarray(verts,dtype=np.float64);tri=np.asarray(faces,dtype=np.int32)
    edges=np.unique(np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1),axis=0)
    dst=np.r_[edges[:,0],edges[:,1]];src=np.r_[edges[:,1],edges[:,0]]
    weight=1/np.maximum(np.linalg.norm(verts[dst][:,[0,2]]-verts[src][:,[0,2]],axis=1),1e-7)
    denom=np.bincount(dst,weights=weight,minlength=len(verts));fixed=np.zeros(len(verts),bool);fixed[boundary_indices]=True
    delta=verts[:,1]-depth(verts[:,0],verts[:,2]);target_delta=delta.copy()
    for _ in range(250):
        averaged=np.bincount(dst,weights=weight*delta[src],minlength=len(verts))/np.maximum(denom,1e-12)
        delta[~fixed]=averaged[~fixed];delta[fixed]=target_delta[fixed]
    verts[~fixed,1]=depth(verts[~fixed,0],verts[~fixed,2])+delta[~fixed]
    obj=make_mesh('EyeSurface_'+side,verts,faces)
    uv=obj.data.uv_layers.new(name='EyeUV');cv=np.asarray(verts)[np.asarray(faces).ravel()]
    coords=np.column_stack([.5+(cv[:,0]-cx)/(rx*2),.5+(cv[:,2]-cz)/(rz*2)]).astype(np.float32)
    uv.data.foreach_set('uv',coords.ravel())
    eye_specs.append({'name':obj.name,'removed_faces':len(face_ids),'boundary_vertices':nt,'triangulation':'constrained Delaunay, source boundary',
        'center':[cx,cz],'radii':[rx,rz],'patch_vertices':len(verts),'patch_triangles':len(faces),
        'boundary_max_error':max(boundary_error),
        'protected_eyelid_face_ids':protected_ids.tolist(),
        'dome_coefficients':coeff.tolist(),
        'removed_source_face_ids':face_ids.tolist()})
    return obj

eyes=[eye_patch('Left',-.085,.278,.049,.045),eye_patch('Right',.131,.280,.055,.046)]
# Copy the original mesh storage instead of rebuilding retained loops: rebuilding
# re-encodes Blender custom normals even on untouched faces. Old eye faces stay
# in the editable source but are explicitly clipped from every rendered view.
body_mesh=m.copy();body_mesh.name='HeadRetainedSurface';body_mesh.materials.clear()
body=bpy.data.objects.new('HeadRetainedSurface',body_mesh);bpy.context.scene.collection.objects.link(body)
source_normal=body_mesh.attributes.new('protected_source_normal','FLOAT_VECTOR','CORNER');source_normal.data.foreach_set('vector',norm.ravel())
source_eye_mask=body_mesh.attributes.new('source_eye_hidden','BOOLEAN','FACE');source_eye_mask.data.foreach_set('value',remove)
old.name='ARCHIVE_refined08_unchanged';archive=bpy.data.collections.new('Archive_original_head');bpy.context.scene.collection.children.link(archive)
for coll in list(old.users_collection):coll.objects.unlink(old)
archive.objects.link(old);archive.hide_render=True;archive.hide_viewport=True

# Material regions are a first pass with explicit editable overrides after visual inspection.
names=['Skin','Hair','Headband','Feather','Scarf','Brow','EyeWhite']
colors=[[.89,.66,.45],[.43,.23,.10],[.21,.36,.14],[.90,.86,.73],[.64,.075,.055],[.22,.105,.045],[.94,.91,.83]]
rough=[.60,.60,.85,.85,.88,.65,.35]
c=centers;x,y,z=c.T;material_ids=np.ones(len(c),dtype=np.int32)
def polygon_mask(poly):
    inside=np.zeros(len(x),bool)
    for j,(ax,az) in enumerate(poly):
        bx,bz=poly[(j+1)%len(poly)]
        if abs(bz-az)>1e-10:inside^=((az>z)!=(bz>z))&(x<(bx-ax)*(z-az)/(bz-az)+ax)
    return inside
skin=(z<.403)&(y<.035)&(np.abs(x)<.23)
skin|=(((np.abs(x)-.25)/.065)**2+((z-.265)/.085)**2+((y+.04)/.085)**2<1)
material_ids[skin]=0
material_ids[(z<.145)]=4
neck=(z<.16)&(z>.04)&(np.abs(x)<.12)&(y>-.105)&(y<.145);material_ids[neck]=0
material_ids[(z>.09)&(z<.15)&(y<-.105)&(np.abs(x)<.21)]=0
bangs=(y<-.285)&(z>.25);material_ids[bangs]=1
band=(z>.375)&(z<.533)&(y>-.335+1.8*x*x)&(y<.03)&(np.abs(x)<.31);material_ids[band]=2
feather_outline=[(.3167,.375),(.3194,.4444),(.343,.511),(.382,.582),(.431,.643),(.4875,.6944),(.4917,.639),(.4764,.5597),(.4444,.4917),(.4,.4375),(.3528,.393)]
# Manually traced barbs from the inspected orthographic front capture. The
# depth gate excludes the hair behind the feather; this is not a height fill.
feather_outline=[((px-450)*1.25/900,.5+(450-py)*1.25/900) for px,py in
    [(676,550),(682,498),(700,453),(728,410),(762,360),(802,306),
     (803,358),(790,399),(793,416),(780,438),(790,448),(769,472),
     (781,477),(756,499),(762,507),(733,526),(739,535),(706,550),(694,557)]]
feather=polygon_mask(feather_outline)&(np.abs(y-(.642588*x-.05156*z-.18212))<.025)
material_ids[feather]=3
# Explicit landmark selections are recorded and visually reviewed in all directions.
# Original GLB components cross semantic boundaries, so do not majority-paint them.
parents=list(range(len(v)));sizes=[1]*len(v)
def component_root(i):
    while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
    return i
for aa,bb in source_edges:
    aa,bb=component_root(int(aa)),component_root(int(bb))
    if aa!=bb:
        if sizes[aa]<sizes[bb]:aa,bb=bb,aa
        parents[bb]=aa;sizes[aa]+=sizes[bb]
component_ids=np.array([component_root(i) for i in range(len(v))],np.int32)
comp=component_ids[f[:,0]]
overrides={603844:0,100276:0,701216:0,123788:0}
for label,value in overrides.items():material_ids[comp==label]=value
material_ids[(z>.085)&(z<.145)&(y>.20)&(np.abs(x)<.16)]=1
brow_polys=[[(.050,.315),(.072,.348),(.12,.370),(.15,.377),(.187,.370),(.210,.357),(.196,.354),(.160,.354),(.105,.337),(.060,.312)],
    [(-.155,.326),(-.145,.343),(-.115,.356),(-.085,.354),(-.055,.343),(-.04,.329),(-.07,.338),(-.11,.341),(-.145,.331)]]
for poly in brow_polys:
    brow=polygon_mask(poly)&(y<-.17)&(y>-.29)&(material_ids==0)
    material_ids[brow]=5
# Side-view ray landmarks locate protruding locks beyond the cheek envelope.
cheek_radius=.221+(z-.28)*.33
cheek_x=np.sqrt(np.maximum(0,cheek_radius**2-(y+.015)**2))
sideburn=(np.abs(x-.02)>cheek_x+.008)&(z>.22)&(z<.38)&(y>-.18)&(y<-.035)&((y>-.11)|(z>.285))
material_ids[sideburn]=1
for spec in eye_specs:
    cx,cz=spec['center'];rx,rz=spec['radii'];coeff=spec['dome_coefficients'];uu=(x-cx)/rx;ww=(z-cz)/rz
    dep=coeff[0]+coeff[1]*uu+coeff[2]*ww+coeff[3]*uu*uu+coeff[4]*uu*ww+coeff[5]*ww*ww
    white=(np.hypot(uu,ww)<1.08)&(y>dep-.003)&(y<dep+.012)
    material_ids[white]=6

# A UV atlas with color-only swatches. No lighting/highlight is painted into it.
size=2048;atlas=np.ones((size,size,4),np.float32)
for i,col in enumerate(colors):
    row=i//4;column=i%4;atlas[row*512:(row+1)*512,column*512:(column+1)*512,:3]=col
def save_texture(name,pixels):
    image=bpy.data.images.new(name,width=size,height=size,alpha=True);image.colorspace_settings.name='sRGB';image.pixels.foreach_set(pixels.ravel())
    image.filepath_raw=str(out/(name+'.png'));image.file_format='PNG';image.save();return image
atlas_image=save_texture('head-basecolor',atlas)
# Shared front-facing eye UV; neutral forward gaze, brown iris without baked catchlights.
yy,xx=np.mgrid[0:size,0:size]/(size-1);rr=np.sqrt(((xx-.50)/.285)**2+((yy-.51)/.43)**2)
eye=np.ones((size,size,4),np.float32);eye[:,:,:3]=[.94,.91,.83]
angle=np.arctan2((yy-.51)/.43,(xx-.50)/.285)
grain=.5+.5*np.sin(angle*67+rr*17)*np.sin(angle*31-rr*9)
iris=np.stack([.31+.13*grain,.15+.07*grain,.055+.035*grain],axis=-1)
eye[:,:,:3]=np.where((rr<1)[:,:,None],iris,eye[:,:,:3]);eye[:,:,:3]=np.where(((rr>.92)&(rr<1))[:,:,None],[.12,.065,.025],eye[:,:,:3]);eye[:,:,:3]=np.where((rr<.43)[:,:,None],[.035,.023,.015],eye[:,:,:3])
eye_image=save_texture('eye-basecolor',eye)
palette={}
def material(name,image,roughness):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(1,1,1,1);bsdf.inputs['Roughness'].default_value=roughness
    node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image;mat.node_tree.links.new(node.outputs['Color'],bsdf.inputs['Base Color']);return mat
for i,name in enumerate(names):
    mat=material(name,atlas_image,rough[i]);body.data.materials.append(mat);palette[name]={'linear_color':[1,1,1,1],'roughness':rough[i],'base_texture':'head-basecolor.png'}
body.data.polygons.foreach_set('material_index',material_ids)
uv=body.data.uv_layers.new(name='HeadStudyUV');source_uv=np.empty((len(m.loops),2),np.float32);m.uv_layers[0].data.foreach_get('uv',source_uv.ravel())
uv.data.foreach_set('uv',source_uv.ravel());body.data.uv_layers.active=uv;uv.active_render=True
# Paint at shared spatial vertices, then bake color-only through the source UVs.
# This antialiases material boundaries without smoothing the geometry or normals.
_,weld=np.unique(np.round(v,6),axis=0,return_inverse=True);loop_vertices=f.ravel();wids=weld[loop_vertices]
srgb=np.array(colors)[np.repeat(material_ids,3)];linear=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)
counts=np.bincount(wids);paint=np.column_stack([np.bincount(wids,weights=linear[:,k],minlength=len(counts))/np.maximum(counts,1) for k in range(3)])
rgba=np.column_stack([paint[wids],np.ones(len(wids))]).astype(np.float32)
attribute=body.data.color_attributes.new(name='HeadPaint',type='FLOAT_COLOR',domain='CORNER');attribute.data.foreach_set('color',rgba.ravel())
baked=bpy.data.images.new('head-basecolor-baked',width=size,height=size,alpha=True);baked.colorspace_settings.name='sRGB'
for mat in body.data.materials:
    nodes=mat.node_tree.nodes;em=nodes.new('ShaderNodeEmission');attr=nodes.new('ShaderNodeAttribute');attr.attribute_name='HeadPaint'
    mat.node_tree.links.new(attr.outputs['Color'],em.inputs['Color']);mat.node_tree.links.new(em.outputs[0],nodes.get('Material Output').inputs['Surface'])
    target=nodes.new('ShaderNodeTexImage');target.image=baked;nodes.active=target
sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.device='CPU';sc.cycles.samples=1;sc.render.bake.margin=4;sc.render.bake.use_selected_to_active=False
bpy.ops.object.select_all(action='DESELECT');body.select_set(True);bpy.context.view_layer.objects.active=body
bpy.ops.object.bake(type='EMIT')
baked.filepath_raw=str(out/'head-basecolor.png');baked.file_format='PNG';baked.save()
for mat in body.data.materials:
    nodes=mat.node_tree.nodes
    for node in list(nodes):
        if node.type in {'EMISSION','ATTRIBUTE'}:nodes.remove(node)
    bsdf=nodes.get('Principled BSDF');mat.node_tree.links.new(bsdf.outputs[0],nodes.get('Material Output').inputs['Surface'])
    for node in nodes:
        if node.type=='TEX_IMAGE':node.image=baked
atlas_image=baked
hidden=bpy.data.materials.new('SourceEyeHidden');hidden.use_nodes=True
hidden_nodes=hidden.node_tree.nodes;hidden_nodes.clear();hidden_out=hidden_nodes.new('ShaderNodeOutputMaterial');transparent=hidden_nodes.new('ShaderNodeBsdfTransparent');hidden.node_tree.links.new(transparent.outputs[0],hidden_out.inputs['Surface'])
body.data.materials.append(hidden);material_ids[remove]=len(body.data.materials)-1;body.data.polygons.foreach_set('material_index',material_ids)
palette['SourceEyeHidden']={'linear_color':[1,1,1,0],'roughness':1,'base_texture':'head-basecolor.png','alpha_clip':True}
eye_mat=material('Eye',eye_image,.35);palette['Eye']={'linear_color':[1,1,1,1],'roughness':.35,'base_texture':'eye-basecolor.png'}
for obj in eyes:obj.data.materials.append(eye_mat)
palette['FaceStudyClay']=json.loads((BASE/'refined-08/palette.json').read_bytes())['FaceStudyClay']
assets=[body]+eyes
bpy.ops.object.select_all(action='DESELECT')
for obj in assets:obj.select_set(True)
bpy.context.view_layer.objects.active=body
bpy.ops.export_scene.fbx(filepath=str(out/'head-palette.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL',path_mode='STRIP')
shutil.copyfile(BASE/'refined-08/head-palette.fbx',out/'old-head.fbx')
(out/'palette.json').write_text(json.dumps(palette,indent=2)+'\n')
(out/'color-source.json').write_text(json.dumps({'colors_srgb':dict(zip(names,colors)),'roughness':dict(zip(names,rough)),'eye_iris':'brown, shared forward UV','texture_size':[2048,2048],'baked_lighting':False,'uv_status':'retained source head UV; dedicated new eye UV; HeadPaint editable color layer','method':'color-only EMIT bake, no lighting or AO'},indent=2)+'\n')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'head-editable.blend'))
retained_norm=np.empty((len(body.data.loops),3),np.float32);body.data.corner_normals.foreach_get('vector',retained_norm.ravel())
normal_error=float(np.abs(retained_norm-norm).max())
normal_delta=np.abs(retained_norm-norm).max(1)
print('NORMAL_CHECK',normal_error,np.percentile(normal_delta,[50,90,99,99.9,100]).tolist(),flush=True)
target_norm=norm.astype(np.float64);actual_norm=retained_norm.astype(np.float64)
cosine=np.sum(target_norm*actual_norm,axis=1)/(np.linalg.norm(target_norm,axis=1)*np.linalg.norm(actual_norm,axis=1))
normal_angle=float(np.degrees(np.arccos(np.clip(cosine,-1,1))).max())
report={'schema':'ao_head_eye_color_v1','source_sha256':source_sha,'eyes':eye_specs,'source_vertices':len(v),'source_triangles':len(f),'retained_triangles':int((~remove).sum()),'retained_coordinate_changes':0,'retained_normal_max_abs_error':normal_error,'retained_normal_max_angle_degrees':normal_angle,'source_normals_preserved_attribute':'protected_source_normal','normals_policy':'source vectors retained exactly; Blender INT16 re-encoding measured separately; no intentional normal edit outside eyes','material_face_counts':dict(zip(names,np.bincount(material_ids,minlength=len(names)).tolist())),'api_tasks':0,'credits':0,'animation_tested':False,'performance_tested':False,'gameplay_changed':False,'art_approved':False}
report.update({'source_eye_policy':'source faces retained in editable mesh, clipped from render; independent rebuilt visible eye surfaces','hidden_source_eye_faces':int(remove.sum()),'render_normals_bitwise_equal':bool(np.array_equal(retained_norm,norm)),'normals_policy':'original mesh storage copied; rendered Blender corner normals and preserved source vectors compared exactly'})
(out/'geometry-report.json').write_text(json.dumps(report,indent=2)+'\n')
assert np.array_equal(retained_norm,norm), 'Protected normals changed'
assert sha(source)==source_sha
(out/'geometry-report.json').write_text(json.dumps(report,indent=2)+'\n')
files=['head-palette.fbx','old-head.fbx','palette.json','head-basecolor.png','eye-basecolor.png']
(out/'unity-inputs.json').write_text(json.dumps({'schema':'ao_head_eye_color_inputs_v1','require_textures':True,'files':{name:sha(out/name) for name in files}},indent=2)+'\n')
if not a.no_render:
    sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=12;sc.cycles.device='CPU';sc.render.resolution_x=900;sc.render.resolution_y=900;sc.render.resolution_percentage=100
    sc.world=bpy.data.worlds.new('Head study world');sc.world.use_nodes=True;sc.world.node_tree.nodes['Background'].inputs[0].default_value=(.12,.12,.12,1)
    for name,loc,power in [('Key',(-3,-4,5),450),('Fill',(3,-2,2),180)]:
        light=bpy.data.lights.new(name,'AREA');light.energy=power;light.size=4;lo=bpy.data.objects.new(name,light);sc.collection.objects.link(lo);lo.location=loc;lo.rotation_euler=(Vector((0,0,.4))-lo.location).to_track_quat('-Z','Y').to_euler()
    cam=bpy.data.objects.new('Head study camera',bpy.data.cameras.new('Head study camera'));sc.collection.objects.link(cam);sc.camera=cam;cam.data.type='ORTHO'
    for name,loc,target,scale in [('front',(0,-4,.55),(0,0,.5),1.25),('face',(0,-4,.245),(0,0,.245),.48),('left',(4,0,.55),(0,0,.5),1.25),('right',(-4,0,.55),(0,0,.5),1.25),('back',(0,4,.55),(0,0,.5),1.25)]:
        cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale;sc.render.filepath=str(out/f'diagnostic-{name}.png');bpy.ops.render.render(write_still=True)
print(json.dumps({k:val for k,val in report.items() if k!='eyes'}))
