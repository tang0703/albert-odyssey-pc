"""Extend the approved U3 mesh into an editable, source-sampled skeletal asset.

No source gameplay state is authored here. Clips are presentation poses only.
"""
import bpy, math, json, hashlib
from pathlib import Path
from mathutils import Vector,Matrix

ROOT=Path(__file__).resolve().parents[1]
APPROVED=ROOT/'art/unity/startroom-v2'
OUT=ROOT/'art/unity/startroom-u4'
approval=json.loads((APPROVED/'review-lock.json').read_bytes())
assert approval['approved'] and approval['status']=='approved_direction'
for name,identity in approval['files'].items():
    assert hashlib.sha256((APPROVED/name).read_bytes()).hexdigest()==identity['sha256'],name
OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'accepted.json').exists():raise RuntimeError('Accepted art cannot be overwritten')
bpy.ops.wm.open_mainfile(filepath=str(APPROVED/'startroom-draft.blend'))
bpy.context.preferences.filepaths.save_version=0
for material in bpy.data.materials:
    if not material.use_nodes:continue
    bs=material.node_tree.nodes.get('Principled BSDF')
    if bs is None:continue
    if any(word in material.name.lower() for word in ('hair','leather','skin')):bs.inputs['Roughness'].default_value=.72
hero=bpy.data.objects['MAP001_PLAYER_U3_REFINED_DRAFT'];hero.location=(0,0,0);hero.rotation_euler=(0,0,0)
parts=list(hero.children)
# Keep the room unchanged except the explicitly provisional Cirrus lamp mass.
for o in list(bpy.data.objects):
    if o.get('source_actor'):bpy.data.objects.remove(o,do_unlink=True)
room=[o for o in bpy.data.objects if o not in parts and o!=hero and o.type in ('MESH','CURVE')]
# U3 used the source's projected sprite rectangle as a temporary volume. In
# 3D its top is elevated, so use the observed table contact footprint instead:
# x 688..783, y 1712..1759 (room-local x176..271, y176..223).
# The source actor/mask stays immutable; this only reshapes the furniture.
table_projection=Matrix.Diagonal(Vector((1,48/63,.58/.9,1)))
table_projection.translation=Vector((0,-(176-160*48/63)/32,0))
for o in room:
    if any(o.name.startswith(n) for n in ('Writing table','Book leather','Open book','Page ink','Ink jar','Ink rim')):
        o.matrix_world=table_projection@o.matrix_world
    elif o.name.startswith('Chair'):
        # These chairs are new art, not source obstacles. Tuck them into the
        # already blocked table footprint instead of occupying the free approach.
        o.location.y-=42/32

armdata=bpy.data.armatures.new('MAP001 deform skeleton')
rig=bpy.data.objects.new('MAP001_RIG',armdata);bpy.context.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
def bone(name,head,tail,parent=None):
    b=armdata.edit_bones.new(name);b.head=head;b.tail=tail
    if parent:b.parent=armdata.edit_bones[parent]
    return b
bone('root',(0,0,0),(0,0,.1))
bone('hips',(0,0,.31),(0,0,.42),'root')
bone('chest',(0,0,.42),(0,0,.59),'hips')
bone('head',(0,0,.59),(0,0,.84),'chest')
for side,s in [('L',1),('R',-1)]:
    bone('upperarm.'+side,(s*.12,0,.565),(s*.174,-.017,.407),'chest')
    bone('forearm.'+side,(s*.174,-.017,.407),(s*.187,-.033,.348),'upperarm.'+side)
    bone('hand.'+side,(s*.187,-.033,.348),(s*.187,-.04,.30),'forearm.'+side)
    bone('thigh.'+side,(s*.061,0,.338),(s*.061,0,.20),'hips')
    bone('shin.'+side,(s*.061,0,.20),(s*.061,.005,.078),'thigh.'+side)
    bone('foot.'+side,(s*.061,.005,.078),(s*.061,-.07,.03),'shin.'+side)
for i,length in enumerate([.039,.047,.045,.034]):
    x=-(.168+i*.012);bone('finger%d.R'%i,(x,-.04,.319),(x-.003,-.049,.319-length),'hand.R')
bone('thumb.R',(-.165,-.047,.344),(-.152,-.054,.318),'hand.R')
bone('scarf',(0,.07,.59),(.08,.11,.54),'chest')
bpy.ops.object.mode_set(mode='OBJECT')

def blend(a,b,t):return {a:1-max(0,min(1,t)),b:max(0,min(1,t))}
weight_vertices=0
for o in parts:
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    if o.type!='MESH':bpy.ops.object.convert(target='MESH')
    # Apply modelling modifiers before weights so the bind mesh is deterministic.
    for mod in list(o.modifiers):bpy.ops.object.modifier_apply(modifier=mod.name)
    name=o.name.lower();local=o.matrix_local.copy();o.parent=None;o.matrix_world=local
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    for v in o.data.vertices:
        x,y,z=v.co;s='L' if x>=0 else 'R'
        if any(k in name for k in ('sleeve','cuff','clasp')) and 'boot' not in name and 'leather' not in name:
            weights={'upperarm.'+s:1}
        elif 'palm' in name or 'knuckle' in name:
            weights=blend('forearm.'+s,'upperarm.'+s,(z-.391)/.032) if z>.39 else blend('hand.'+s,'forearm.'+s,(z-.332)/.027)
            if s=='R' and abs(x)<.164 and z<.342:
                weights=blend('hand.R','thumb.R',(.342-z)/.015)
            elif s=='R' and z<.322:
                finger=min(range(4),key=lambda i:abs(abs(x)-(.168+i*.012)))
                weights=blend('hand.R','finger%d.R'%finger,(.322-z)/.012)
        elif any(k in name for k in ('boot','sole','vamp','leather cuff')):
            weights=blend('foot.'+s,'shin.'+s,(z-.09)/.045)
        elif 'trouser' in name:
            weights=blend('shin.'+s,'thigh.'+s,(z-.185)/.045)
        elif any(k in name for k in ('scarf tail','scarf rear')):weights={'scarf':1}
        elif any(k in name for k in ('tunic','coat','lapel','hem','waist','belt','buckle','opening')):
            weights=blend('hips','chest',(z-.40)/.14)
        elif 'scarf' in name or name.startswith('neck'):weights={'chest':1}
        else:weights={'head':1}
        for n,w in weights.items():
            if w>0:(o.vertex_groups.get(n) or o.vertex_groups.new(name=n)).add([v.index],w,'REPLACE')
        weight_vertices+=1
    mod=o.modifiers.new('Source sampled skeletal deformation','ARMATURE');mod.object=rig
    o.parent=rig
    # Give every mesh editable UVs, including procedurally built rings and tubes.
    if not o.data.uv_layers:
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=1.15192,island_margin=.015);bpy.ops.object.mode_set(mode='OBJECT')

# Join compatible skinned components: one renderer, multiple material slots.
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join();skin=bpy.context.object;skin.name='Player_SkinnedMesh'
bpy.data.objects.remove(hero,do_unlink=True)

def reset():
    for b in rig.pose.bones:b.rotation_mode='XYZ';b.rotation_euler=(0,0,0);b.location=(0,0,0);b.scale=(1,1,1)
def rotate(name,x=0,y=0,z=0):rig.pose.bones[name].rotation_euler=tuple(math.radians(v) for v in (x,y,z))
def key(frame):
    for b in rig.pose.bones:
        b.keyframe_insert('rotation_euler',frame=frame,group=b.name)
        b.keyframe_insert('location',frame=frame,group=b.name)

scene=bpy.context.scene;scene.render.fps=40
actions={}
for name in ['idle','walk','pickup_35','pickup_36','pickup_37','pickup_38']:
    rig.animation_data_create();rig.animation_data.action=None
    length=40 if name in ('walk','idle') else 1
    for f in range(length+1):
        reset();phase=f/40*2*math.pi
        if name=='idle':
            rotate('chest',.5*math.sin(phase));rotate('head',-.5*math.sin(phase))
        elif name=='walk':
            # In-place gait; the source core supplies the ground translation.
            for side,sign in [('L',1),('R',-1)]:
                swing=math.sin(phase)*sign
                rotate('thigh.'+side,22*swing)
                rotate('shin.'+side,-max(0,-swing)*29)
                rotate('foot.'+side,-10*swing+max(0,-swing)*15)
                rotate('upperarm.'+side,-17*swing,0,sign*3)
                rotate('forearm.'+side,-7-max(0,swing)*8)
            rotate('chest',0,0,2*math.sin(phase));rotate('head',0,0,-2*math.sin(phase))
            rotate('scarf',5*math.sin(phase),0,3*math.cos(phase))
        elif name.startswith('pickup'):
            pose=int(name[-2:])
            # Source 35..37: successive front reach/bend; 38: raised sword.
            if pose!=38:
                bend={35:12,36:25,37:35}[pose];rotate('chest',bend);rotate('head',-bend*.45)
                for side in ['L','R']:
                    rotate('upperarm.'+side,-20-bend*.6);rotate('forearm.'+side,-22)
                    rotate('thigh.'+side,8);rotate('shin.'+side,-12)
            else:
                # Raise outward beside the head, keeping the blade out of the hair.
                rest=rig.data.bones['upperarm.R'].matrix_local.to_quaternion()
                local_direction=rest.inverted()@Vector((-.12,-.025,.16))
                rig.pose.bones['upperarm.R'].rotation_euler=Vector((0,1,0)).rotation_difference(local_direction.normalized()).to_euler('XYZ')
                rotate('forearm.R',-12);rotate('hand.R',0,0,8)
                for finger in range(4):rotate('finger%d.R'%finger,-75)
                rotate('thumb.R',-35,0,25)
                rotate('upperarm.L',-12,0,12);rotate('head',-8);rotate('chest',-4)
        key(f)
    action=rig.animation_data.action;action.name=name;action.use_fake_user=True;actions[name]=action
reset();rig.animation_data.action=actions['idle'];scene.frame_set(0)

# Cirrus source sprite is a curved blade with a gold hilt, not a lamp.
def simplemat(name,color,metal=0,rough=.5):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Metallic'].default_value=metal;bs.inputs['Roughness'].default_value=rough;return m
steel=simplemat('Cirrus blue steel',(.27,.48,.66),.8,.24);gold=bpy.data.materials['Brass fittings'];grip=bpy.data.materials['Boot leather']
verts=[]
for z,x,w in [(0,0,.023),(.11,.005,.037),(.24,.025,.031),(.36,.074,.020),(.43,.113,0)]:
    verts.extend([(x-w,-.012,z),(x+w,-.012,z),(x+w,.012,z),(x-w,.012,z)])
faces=[(0,3,2,1)]
for r in range(4):
    for j in range(4):a=r*4+j;b=r*4+(j+1)%4;faces.append((a,b,b+4,a+4))
mesh=bpy.data.meshes.new('Curved Cirrus blade');mesh.from_pydata(verts,[],faces);mesh.update()
blade=bpy.data.objects.new('Cirrus blade',mesh);bpy.context.collection.objects.link(blade);blade.data.materials.append(steel)
sword=[blade]
for name,loc,scale,material in [('Crossguard',(0,0,0),(.18,.04,.026),gold),('Grip',(0,0,-.08),(.033,.033,.14),grip),('Pommel',(0,0,-.155),(.052,.05,.04),gold)]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.scale=scale;o.data.materials.append(material);mod=o.modifiers.new('Beveled edges','BEVEL');mod.width=.006;mod.segments=3;sword.append(o)
bpy.ops.object.select_all(action='DESELECT')
for o in sword:o.select_set(True)
bpy.context.view_layer.objects.active=blade;bpy.ops.object.convert(target='MESH');bpy.ops.object.join();blade=bpy.context.object;blade.name='Cirrus_Independent'

def export(objects,path,animate=False):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH','ARMATURE'},bake_anim=animate,bake_anim_use_all_actions=animate,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
export([rig,skin],OUT/'player-rig.fbx',True)
export(room,OUT/'room.fbx')
export([blade],OUT/'cirrus.fbx')
blade.location=((755-512)/32,-(1709-1536)/32,.96);blade.rotation_euler=(0,math.pi/2,0)
rig.location=((718-512)/32,-(1626-1536)/32,0)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'startroom-rig.blend'))
report={'schema':'ao_unity_u4_rig_v1','approval_sha256':hashlib.sha256((APPROVED/'review-lock.json').read_bytes()).hexdigest(),'bones':list(armdata.bones.keys()),'weighted_vertices':weight_vertices,'clips':{k:{'frames':list(a.frame_range),'source_driven':True} for k,a in actions.items()},'root_motion':False,'performance_tested':False,'source_pose_images':[35,36,37,38],'notes':['New interpolated 3D poses preserve source image selection and timing, not source pixels.','Cirrus source silhouette replaces the provisional U3 lamp mass.','UVs are editable; material refinement follows.']}
report['files']={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.iterdir() if p.suffix in ('.blend','.fbx')}
(OUT/'rig.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('U4_RIG_DONE',len(armdata.bones),weight_vertices)
