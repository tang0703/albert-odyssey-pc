"""C1/C2 static player sculpt and editable UV source. No rig before review.
Reuse established primitive helpers without executing the old room generator.
"""
from pathlib import Path
import ast,bpy,math,json,hashlib,sys
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'art/unity/player-refined-v1'
OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'review-lock.json').exists():raise RuntimeError('Frozen review: make a new version')
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.context.preferences.filepaths.save_version=0
tree=ast.parse((ROOT/'tools/unity_draft_models_v2.py').read_text(encoding='utf-8'))
helpers={'mat','assign','smooth','cube','ellipsoid','cyl','tube','limb','rings','tapered'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in helpers or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='M' for t in n.targets)]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'primitive_helpers','exec'),globals())
sys.path.insert(0,str(ROOT/'tools'));from unity_player_v2 import build_player
root,parts=build_player(globals())
remove=('Sculpted tapered face','Ear inner fold','Almond sclera','Brown iris','Deep pupil','Eye highlight','Upper lash','Tapered brow','Small soft smile','Hair fitted base','Hair nape volume','Woven green headband','Headband rear knot','Headband tie','Swept crown','Layered rear crown','Layered fringe','Temple side lock','Layered nape','Light feather','Feather curved','Feather fine','Short waist fold','Trouser knee crease','Boot stitching','Palm','Knuckle fold','Scarf draped fold','Red scarf neck folds')
for o in list(parts):
    if any(o.name.startswith(n) for n in remove):bpy.data.objects.remove(o,do_unlink=True)

# The old body remains the editable starting point; remove hard crease tubes.
# Colour is linear, converted to sRGB by Blender's bake output, not hand lit.
palette={'skin':(.76,.46,.27),'hair':(.24,.087,.021),'hairlight':(.34,.14,.038),'tunic':(.22,.32,.075),'pants':(.29,.30,.092),'red':(.47,.035,.026),'leather':(.16,.065,.025),'cuff':(.39,.20,.065),'cream':(.78,.69,.49),'iris':(.22,.085,.018),'white':(.91,.86,.72),'pupil':(.012,.007,.004),'feather':(.88,.78,.57),'gold':(.55,.29,.065),'stitch':(.60,.43,.19),'ear':(.54,.25,.15),'lip':(.37,.12,.074)}
for key,color in palette.items():
    m=M[key];m.diffuse_color=(*color,1);n=m.node_tree.nodes;n.clear()
    out=n.new('ShaderNodeOutputMaterial');bs=n.new('ShaderNodeBsdfPrincipled');m.node_tree.links.new(bs.outputs['BSDF'],out.inputs['Surface']);bs.inputs['Base Color'].default_value=(*color,1)
    rough=.78 if key in ('tunic','pants','red','cream','stitch') else .62 if key in ('hair','hairlight','leather','cuff') else .65
    bs.inputs['Roughness'].default_value=rough
    if key in ('white','iris','pupil'):bs.inputs['Roughness'].default_value=.26
    if key=='gold':bs.inputs['Metallic'].default_value=.7;bs.inputs['Roughness'].default_value=.34
    if key in ('tunic','pants','red','cream','leather','cuff','hair','hairlight'):
        coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=170 if key in ('tunic','pants','red','cream') else 80
        noise.inputs['Detail'].default_value=2;m.node_tree.links.new(coord.outputs['Object'],noise.inputs['Vector'])
        ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(*[c*.88 for c in color],1);ramp.color_ramp.elements[1].color=(*[c*1.08 for c in color],1)
        m.node_tree.links.new(noise.outputs['Fac'],ramp.inputs[0]);m.node_tree.links.new(ramp.outputs[0],bs.inputs['Base Color'])
        bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.0006
        m.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);m.node_tree.links.new(bump.outputs[0],bs.inputs['Normal'])

def mesh_object(name,verts,faces,material):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);assign(o,material);smooth(o);return o

v=[];f=[]
for j in range(64):
    t=2*math.pi*j/64
    for k in range(16):
        s=2*math.pi*k/16;r=.069+.018*math.cos(s)
        v.append((r*math.cos(t),r*.85*math.sin(t),.622+.026*math.sin(s)-.009*max(0,-math.sin(t))+.0018*math.sin(3*s+t)))
for j in range(64):
    for k in range(16):f.append((j*16+k,((j+1)%64)*16+k,((j+1)%64)*16+(k+1)%16,j*16+(k+1)%16))
mesh_object('Soft folded scarf collar',v,f,'red')

# A shared continuous facial surface puts the eyes inside the same cheek plane.
zc=.774;rz=.139
def radii(z):
    t=(z-zc)/rz;s=math.sqrt(max(.00001,1-t*t))
    return .151*s*(1-.27*max(0,-t)),.121*s
def front(x,z):
    rx,ry=radii(z);y=-ry*math.sqrt(max(.001,1-(x/rx)**2))
    # cheek softness, a shallow socket, nasal bridge and tip all on one mesh
    y-=.006*math.exp(-((abs(x)-.071)/.04)**2-((z-.728)/.037)**2)
    y+=.005*math.exp(-((abs(x)-.058)/.035)**2-((z-.781)/.031)**2)
    y-=.006*math.exp(-(x/.015)**2-((z-.739)/.018)**2)
    y-=.006*math.exp(-(x/.012)**2-((z-.762)/.030)**2)
    y-=.003*math.exp(-(x/.033)**2-((z-.702)/.013)**2)
    return y
v=[];f=[];nr=64;ns=96
for j in range(nr+1):
    z=zc-rz+.0001+(2*rz-.0002)*j/nr;rx,ry=radii(z)
    for i in range(ns):
        t=2*math.pi*i/ns;x=rx*math.cos(t);y=ry*math.sin(t)
        if y<0:y=front(x,z)
        v.append((x,y,z))
for j in range(nr):
    for i in range(ns):a=j*ns+i;b=j*ns+(i+1)%ns;f.append((a,b,b+ns,a+ns))
f.extend([tuple(range(ns-1,-1,-1)),tuple(nr*ns+i for i in range(ns))])
head=mesh_object('Face continuous quad surface',v,f,'skin')
for side in [-1,1]:
    ear=ellipsoid('Ear attached base',(side*.140,.003,.752),(.025,.017,.035),'skin')
    ellipsoid('Ear inner concha',(side*.148,-.012,.754),(.013,.004,.022),'ear')
    tube('Ear soft helix',[(side*.145,-.016,.779),(side*.159,-.013,.761),(side*.148,-.015,.730)],.003,'skin')

def eye_outline(t,cx,cz,rx,rz):
    return cx+rx*math.cos(t),cz+rz*math.sin(t)*(abs(math.sin(t))**.25)+.004*math.cos(t)*(1 if cx>0 else -1)
def eye_disk(name,cx,cz,rx,rz,material,offset,almond=False):
    v=[(cx,front(cx,cz)-offset,cz)];f=[];n=64;rr=8
    for j in range(1,rr+1):
        r=j/rr
        for i in range(n):
            t=2*math.pi*i/n
            x,z=eye_outline(t,cx,cz,rx*r,rz*r) if almond else (cx+rx*r*math.cos(t),cz+rz*r*math.sin(t))
            v.append((x,front(x,z)-offset-.0012*(1-r*r),z))
    for i in range(n):f.append((0,1+i,1+(i+1)%n))
    for j in range(rr-1):
        for i in range(n):a=1+j*n+i;b=1+j*n+(i+1)%n;f.append((a,a+n,b+n,b))
    return mesh_object(name,v,f,material)
for side in [-1,1]:
    x=side*.060;z=.779
    eye_disk('Inset almond eye',x,z,.036,.024,'white',.001,True)
    eye_disk('Amber brown iris',x,z-.001,.020,.022,'iris',.0028)
    eye_disk('Deep round pupil',x,z,.0085,.015,'pupil',.0037)
    ellipsoid('Corneal small glint',(x-.006,front(x-.006,z+.009)-.005,z+.009),(.004,.001,.0048),'white')
    for top in [True,False]:
        points=[]
        for i in range(25):
            t=(0 if top else math.pi)+math.pi*i/24;xx,zz=eye_outline(t,x,z,.037,.025)
            points.append((xx,front(xx,zz)-.0006,zz))
        tube('Upper eyelid flesh' if top else 'Lower eyelid flesh',points,.0021 if top else .0012,'skin')
        if top:tube('Fine upper lash',[(xx,yy-.0018,zz-.001) for xx,yy,zz in points],.0018,'hair')
    brow=[(x-side*.033,0,.808),(x+side*.006,0,.819),(x+side*.036,0,.808)]
    tapered('Expressive brow',[(xx,front(xx,zz)-.002,zz) for xx,_,zz in brow],.0048,'hair',.30)
tube('Soft smiling mouth',[(x,front(x,z)-.0015,z) for x,z in [(-.021,.702),(-.010,.698),(0,.697),(.012,.699),(.022,.704)]],.0012,'lip')

# Broad overlapping swept locks. Cross sections have a shallow, carved ridge.
def leaf(name,points,width,material='hair',thickness=.35,out=(0,-1,0),grooves=True):
    a,b,c=map(Vector,points);out=Vector(out).normalized();v=[];f=[];rows=28;sides=16
    if material in ('hair','hairlight'):a.z-=.025;a.y*=.8
    for j in range(rows):
        t=j/(rows-1);p=(1-t)**2*a+2*t*(1-t)*b+t*t*c;d=(2*(1-t)*(b-a)+2*t*(c-b)).normalized()
        axis=d.cross(out).normalized();normal=axis.cross(d).normalized()
        w=width*(.45+.85*math.sin(math.pi*t))*(1-t)**.72+.0002
        for k in range(sides):
            ang=2*math.pi*k/sides;u=math.cos(ang);h=math.sin(ang)
            ridge=1+.05*math.cos(u*math.pi*6) if grooves else 1
            v.append(tuple(p+axis*w*u+normal*w*thickness*h*ridge))
    for j in range(rows-1):
        for k in range(sides):a0=j*sides+k;b0=j*sides+(k+1)%sides;f.append((a0,b0,b0+sides,a0+sides))
    f.extend([tuple(range(sides-1,-1,-1)),tuple((rows-1)*sides+k for k in range(sides))])
    return mesh_object(name,v,[tuple(reversed(face)) for face in f],material)
ellipsoid('Joined crown foundation',(0,.022,.869),(.153,.129,.102),'hair')
ellipsoid('Joined occipital hair',(0,.061,.801),(.138,.103,.106),'hair')
rings('Woven headband',[(.823,.154,.130,0,.008),(.858,.154,.130,0,.008)],'tunic',64)
ellipsoid('Headband rear knot',(.025,.145,.841),(.023,.014,.018),'tunic')
for i in range(2):leaf('Headband fabric tie',[(.02+i*.018,.15,.838),(.02+i*.025,.161,.795),(.008+i*.055,.15,.768)],.016,'tunic',.13,(0,1,0),False)
locks=[
 ([(.07,.015,.920),(-.065,-.005,1.063),(-.221,-.015,1.014)],.055,(0,-1,.25)),
 ([(.07,-.025,.914),(-.075,-.065,1.007),(-.224,-.086,.941)],.055,(0,-1,.1)),
 ([(.07,.065,.917),(-.075,.105,1.075),(-.198,.142,1.029)],.053,(0,.6,1)),
 ([(.055,.100,.886),(-.085,.196,1.009),(-.213,.198,.941)],.050,(0,1,.2)),
 ([(.089,.018,.926),(.110,.004,1.038),(.046,.003,1.105)],.048,(0,-1,.1)),
 ([(.11,.054,.906),(.202,.084,.999),(.180,.112,1.059)],.044,(1,0,.2)),
 ([(.116,.094,.880),(.219,.153,.936),(.232,.176,.983)],.044,(1,1,0)),
 ([(.06,.136,.866),(.126,.206,.924),(.203,.222,.901)],.044,(0,1,0))]
for i,(p,w,o) in enumerate(locks):leaf('Swept layered crown %02d'%i,p,w,'hairlight' if i%3==0 else 'hair',.34,o)
for i,(x,endx,z) in enumerate([(-.085,-.151,.790),(-.043,-.115,.795),(.003,-.042,.795),(.049,.025,.832),(.096,.100,.849)]):
    leaf('Overlapping fringe %02d'%i,[(x+.04,-.064,.930),(x-.016,-.145,.882),(endx,-.132,z)],.040 if i<3 else .031,'hairlight' if i%2==0 else 'hair',.27)
for side in [-1,1]:
    for k in range(3):
        leaf('Swept side crown',[(side*.055,.03+k*.027,.940-k*.012),(side*.165,.015+k*.055,.964-k*.026),(side*(.206-k*.008),.05+k*.07,.871-k*.030)],.048,'hairlight' if k==0 else 'hair',.38,(side,.35,0))
    leaf('Temple hair',[(side*.12,-.02,.862),(side*.158,-.03,.796),(side*.142,-.030,.716)],.026,'hair',.28,(side,-.5,0))
    for k in range(4):
        x=side*(.018+k*.034)
        leaf('Overlapping rear hair',[(x*.75,.105,.870),(x,.182,.792),(x*1.16,.145,.701+(k%2)*.021)],.037,'hairlight' if k==1 else 'hair',.35,(0,1,0))
leaf('Feather ivory vane',[(-.144,-.021,.841),(-.218,-.006,.951),(-.211,.004,1.039)],.032,'feather',.10,(-.2,-1,0),False)
tube('Feather quill',[(-.143,-.025,.841),(-.194,-.016,.940),(-.211,-.002,1.039)],.0017,'cream')
for k in range(10):
    t=k/10;x=-.149-.062*t;z=.853+.174*t
    tube('Feather barb',[(x+.012,-.019,z+.005),(x,-.021,z),(x-.018,-.017,z+.020)],.0007,'cream')

# Continuous tapered forearms with a relaxed hand, rather than overlapping beads.
for side in [-1,1]:
    start=set(bpy.data.objects);rows=[]
    for j in range(25):
        t=j/24;z=.481-.142*t;x=side*(.157+.029*t);y=-.006-.025*t
        radius=.036-.011*t+.002*math.sin(math.pi*t)
        rows.append((z,radius,radius*.86,x,y))
    arm=rings('Continuous relaxed arm',list(reversed(rows)),'skin',32)
    ellipsoid('Relaxed palm',(side*.187,-.031,.329),(.029,.021,.033),'skin')
    for i in range(4):
        x=side*(.167+i*.012);length=[.031,.040,.038,.029][i]
        limb('Relaxed finger upper',(x,-.032,.317),(x,-.043,.317-length*.62),(.008,.0075),'skin')
        limb('Relaxed finger tip',(x,-.043,.317-length*.62),(x,-.055,.317-length),(.007,.0065),'skin')
    limb('Resting thumb',(side*.165,-.041,.342),(side*.153,-.050,.319),(.011,.010),'skin')
    bpy.ops.object.select_all(action='DESELECT')
    for o in set(bpy.data.objects)-start:o.select_set(True)
    bpy.context.view_layer.objects.active=arm;bpy.ops.object.join()
    remesh=arm.modifiers.new('Continuous wrist and fingers','REMESH');remesh.mode='VOXEL';remesh.voxel_size=.0016;remesh.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=remesh.name)
    mod=arm.modifiers.new('Soften wrist transitions','SMOOTH');mod.factor=.7;mod.iterations=5;bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.quadriflow_remesh(target_faces=1800,use_mesh_symmetry=False,use_preserve_sharp=False,use_preserve_boundary=True);smooth(arm)

for side in [-1,1]:
    # Blend the ankle into a flatter shoe vamp. Soles and cuffs stay separate.
    shoe=[]
    for o in list(bpy.context.scene.objects):
        if not o.name.startswith(('Leather boot vamp','Fitted boot shaft')):continue
        center=sum((o.matrix_world@v.co).x for v in o.data.vertices)/len(o.data.vertices)
        if center*side<=0:continue
        if o.name.startswith('Leather boot vamp'):
            o.location.z-=.009;o.location.y-=.008
            for v in o.data.vertices:v.co.z*=.78
        shoe.append(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in shoe:o.select_set(True)
    bpy.context.view_layer.objects.active=shoe[0];bpy.ops.object.join();boot=bpy.context.object;boot.name='Continuous leather boot'
    mod=boot.modifiers.new('Joined ankle and vamp','REMESH');mod.mode='VOXEL';mod.voxel_size=.002;mod.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=boot.modifiers.new('Soft leather contours','SMOOTH');mod.factor=.65;mod.iterations=3;bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.quadriflow_remesh(target_faces=1400,use_mesh_symmetry=False,use_preserve_sharp=False,use_preserve_boundary=True);smooth(boot)

# Finish body surface and make the source UV edit friendly. No bone weights here.
objects=[o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE')]
for o in objects:
    o.parent=None
    if o.name.startswith('Red scarf neck folds'):
        for v in o.data.vertices:
            v.co.z+=.018
            if v.co.y<0:v.co.z-=.010*(1-abs(v.co.x)/.09)
    if o.name.startswith(('Fine stitched hem','Tailored front opening')):
        o.scale.x*=.94;o.scale.y*=.94;o.location.z+=.012
    if o.name.startswith('Belt fitted leather'):
        for v in o.data.vertices:v.co.x*=1.07;v.co.y*=1.07
    if o.name.startswith('Baggy trouser leg'):
        # Replace old high frequency corrugation with a gentle knee fold.
        for v in o.data.vertices:
            v.co.y-=.003*math.sin(v.co.x*140+v.co.z*55)
            v.co.y+=.002*math.sin((v.co.z-.19)*55)*max(0,1-abs(v.co.z-.25)/.10)
    if o.name.startswith(('Baggy trouser leg','Layered split tunic')):
        sub=o.modifiers.new('Continuous cloth surface','SUBSURF');sub.levels=2
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    bpy.ops.object.convert(target='MESH')
    for mod in list(o.modifiers):
        if mod.type in ('BEVEL','WEIGHTED_NORMAL','SUBSURF'):bpy.ops.object.modifier_apply(modifier=mod.name)
    o['authoring_stage']='C1 static geometry; final skinning pending C2 approval'
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.ops.object.select_all(action='DESELECT')
for o in objects:o.select_set(True)
bpy.context.view_layer.objects.active=head
bpy.ops.object.join();model=bpy.context.object;model.name='MAP001_PLAYER_REFINED_STATIC'
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
zs=[v.co.z for v in model.data.vertices];floor=min(zs);scale=1.125/(max(zs)-floor)
for v in model.data.vertices:v.co=Vector((v.co.x*scale,v.co.y*scale,(v.co.z-floor)*scale))
# Identical topology for tangent normal baking and Unity import.
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.normals_make_consistent(inside=False);bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY',ngon_method='BEAUTY');bpy.ops.object.mode_set(mode='OBJECT')
while len(model.data.uv_layers):model.data.uv_layers.remove(model.data.uv_layers[0])
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.003,correct_aspect=True);bpy.ops.object.mode_set(mode='OBJECT')
model.data.uv_layers.active.name='CharacterAtlasUV'
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16
scene.world.color=(.1,.1,.1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'player-refined.blend'))
bpy.ops.export_scene.fbx(filepath=str(OUT/'player-static.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
report={'stage':'C1 static mesh, C2 review pending','height':1.125,'vertices':len(model.data.vertices),'triangles':sum(len(p.vertices)-2 for p in model.data.polygons),'uv':'CharacterAtlasUV','skinning_complete':False,'animation_complete':False,'performance_tested':False,'old_art_unchanged':True}
(OUT/'geometry.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('REFINED_GEOMETRY',json.dumps(report))
