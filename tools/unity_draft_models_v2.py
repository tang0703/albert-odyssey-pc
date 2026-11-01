"""Blender U3 editable geometric drafts. No final rig/animation before approval.
Run with locked Blender --background --factory-startup --python this_file.
All coordinates are geometry; approved 2D images are references, never billboards.
"""
from pathlib import Path
import bpy, math, random, json, hashlib, sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'art/unity/startroom-v2'
OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'review-lock.json').exists() and json.loads((OUT/'review-lock.json').read_bytes()).get('approved'):
 raise RuntimeError('Approved U3 assets are immutable; use a new version directory')
random.seed(2701)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.context.preferences.filepaths.save_version=0
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=1600;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.world.color=(.12,.15,.18)
scene.view_settings.view_transform='AgX'
scene.render.image_settings.file_format='PNG'

def mat(name,color,rough=.6,metal=0,wood=False,cloth=False):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 n=m.node_tree.nodes;p=n.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
 if wood or cloth:
  tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=6 if wood else 140;tex.inputs['Detail'].default_value=3
  coord=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(3,70,5) if wood else (1,1,1)
  m.node_tree.links.new(coord.outputs['Generated'],mapping.inputs[0]);m.node_tree.links.new(mapping.outputs[0],tex.inputs['Vector'])
  ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(*[c*.55 for c in color],1);ramp.color_ramp.elements[1].color=(*[min(1,c*1.3) for c in color],1)
  m.node_tree.links.new(tex.outputs['Fac'],ramp.inputs[0]);m.node_tree.links.new(ramp.outputs[0],p.inputs['Base Color'])
  bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15 if wood else .09;bump.inputs['Distance'].default_value=.012 if wood else .002
  m.node_tree.links.new(tex.outputs['Fac'],bump.inputs['Height']);m.node_tree.links.new(bump.outputs[0],p.inputs['Normal'])
 return m
M={
 'wood':mat('Honey oak',(.29,.105,.032),.38,wood=True),'darkwood':mat('Dark walnut',(.115,.037,.012),.45,wood=True),
 'floor':mat('Warm floorboards',(.28,.12,.045),.52,wood=True),'gold':mat('Brass fittings',(.65,.36,.085),.3,.7),
 'cream':mat('Ivory linen',(.79,.7,.5),.82,cloth=True),'red':mat('Wool crimson',(.39,.027,.028),.75,cloth=True),
 'black':mat('Dark check',(.035,.022,.018),.75,cloth=True),'blue':mat('Sapphire carpet',(.025,.075,.24),.85,cloth=True),
 'greenrug':mat('Forest carpet',(.025,.11,.067),.85,cloth=True),'skin':mat('Warm skin',(.68,.35,.18),.55),
 'tunic':mat('Olive tunic',(.19,.29,.055),.78,cloth=True),'pants':mat('Ochre olive trousers',(.27,.27,.07),.78,cloth=True),
 'leather':mat('Boot leather',(.105,.037,.015),.36),'hair':mat('Chestnut hair',(.19,.065,.016),.37),
 'hairlight':mat('Hair warm highlights',(.29,.115,.027),.4),'white':mat('Eye ivory',(.93,.9,.8),.3),
 'iris':mat('Brown eyes',(.12,.037,.009),.25),'pupil':mat('Pupil',(.008,.005,.003),.25),
 'mouth':mat('Face details',(.13,.035,.02),.65),'ear':mat('Inner ear',(.49,.21,.105),.65),'feather':mat('Ivory feather',(.89,.78,.57),.58),
 'glass':mat('Window amber',(.85,.48,.13),.25),'ceramic':mat('Green ceramic',(.035,.17,.13),.25),
 'paper':mat('Book paper',(.73,.6,.36),.8), 'steel':mat('Cirrus cool metal',(.2,.25,.3),.23,.75)
}

def assign(o,m):o.data.materials.append(M[m] if isinstance(m,str) else m);return o
def smooth(o):
 if o.type=='MESH':
  for p in o.data.polygons:p.use_smooth=True
 return o
def cube(name,loc,scale,m,bevel=.025):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.scale=scale;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);assign(o,m)
 if bevel:
  mod=o.modifiers.new('Soft crafted edges','BEVEL');mod.width=bevel;mod.segments=3;o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
 return o
def ellipsoid(name,loc,scale,m):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=28,ring_count=16,radius=1,location=loc);o=bpy.context.object;o.name=name;o.scale=scale;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);assign(o,m);return smooth(o)
def cyl(name,loc,radius,depth,m,vertices=32):
 bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc);o=bpy.context.object;o.name=name;assign(o,m);mod=o.modifiers.new('Rounded lip','BEVEL');mod.width=min(.015,radius*.15);mod.segments=3;return smooth(o)
def tube(name,points,radius,m):
 c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.resolution_u=12;c.bevel_depth=radius;c.bevel_resolution=3;s=c.splines.new('BEZIER');s.bezier_points.add(len(points)-1)
 for p,co in zip(s.bezier_points,points):p.co=co;p.handle_left_type='AUTO';p.handle_right_type='AUTO'
 o=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(o);assign(o,m);return o
def limb(name,a,b,radii,m):
 mid=(Vector(a)+Vector(b))*.5;o=ellipsoid(name,mid,(radii[0],radii[1],(Vector(a)-Vector(b)).length/2+radii[0]*.5),m);o.rotation_mode='QUATERNION';o.rotation_quaternion=(Vector(b)-Vector(a)).to_track_quat('Z','Y');return o
def rings(name,rows,m,sides=40):
 v=[];f=[]
 for z,rx,ry,cx,cy in rows:
  for i in range(sides):t=2*math.pi*i/sides;v.append((cx+rx*math.cos(t),cy+ry*math.sin(t),z))
 for j in range(len(rows)-1):
  for i in range(sides):a=j*sides+i;b=j*sides+(i+1)%sides;f.append((a,b,b+sides,a+sides))
 f.append(tuple(range(sides-1,-1,-1)));f.append(tuple((len(rows)-1)*sides+i for i in range(sides)))
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(v,[],f);mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);assign(o,m);return smooth(o)
def tapered(name,points,width,m,flat=.55):
 # Curved, closed sculptural clump, not a texture plane.
 a,b,c=map(Vector,points);rows=[];verts=[];faces=[];n=12;sides=10
 for j in range(n):
  t=j/(n-1);p=(1-t)**2*a+2*t*(1-t)*b+t*t*c;tangent=(2*(1-t)*(b-a)+2*t*(c-b)).normalized();normal=tangent.cross(Vector((0,1,0)))
  if normal.length<.1:normal=tangent.cross(Vector((1,0,0)))
  normal.normalize();other=tangent.cross(normal).normalized();r=width*(.6+math.sin(math.pi*t)*.5)*(1-t)**.6+.0005
  for i in range(sides):ang=2*math.pi*i/sides;verts.append(tuple(p+r*math.cos(ang)*normal+r*flat*math.sin(ang)*other))
 for j in range(n-1):
  for i in range(sides):a0=j*sides+i;b0=j*sides+(i+1)%sides;faces.append((a0,b0,b0+sides,a0+sides))
 faces.append(tuple(range(sides-1,-1,-1)));faces.append(tuple((n-1)*sides+i for i in range(sides)))
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);assign(o,m);return smooth(o)

def room():
 before=set(bpy.data.objects)
 # The visual stair opening is cut from the slab. No physics geometry is used.
 for x0,x1,y0,y1 in [(0,11.6,0,8),(13.2,14,0,8),(11.6,13.2,0,5.55),(11.6,13.2,7.4,8)]:
  cube('Room foundation',((x0+x1)/2,-(y0+y1)/2,-.15),(x1-x0,y1-y0,.3),'darkwood',.025)
 for y in range(24):
  for x in range(7):
   xx=x*2+1+(1 if y%2 else 0);left=max(0,xx-1);right=min(14,xx+1)
   spans=[(left,right)]
   if 5.55<(y+.5)/3<7.4:
    spans=[(left,min(right,11.6)),(max(left,13.2),right)]
   for a,b in spans:
    if b-a>.02:cube('Oak floor plank',((a+b)/2,-(y+.5)/3,-.012),(b-a-.016,.317,.06),'floor',.008)
  if y%2:cube('Oak half plank',(.5,-(y+.5)/3,-.012),(.985,.317,.06),'floor',.008)
 # Low front parapet, open ceiling, visible navigational silhouette.
 for y,h in [(0,1.65),(-8,.17)]:
  cube('Wall sill',(7,y,h/2),(14,.14,h),'wood',.025)
  cube('Wall cap',(7,y,h),(14.15,.23,.12),'darkwood',.035)
 for x in [0,14]:cube('Side wall',(x,-4,.35),(.16,8,.7),'wood');cube('Side wall cap',(x,-4,.73),(.23,8,.12),'darkwood')
 for x in range(0,15,2):cube('Timber upright',(x,0,.82),(.13,.22,1.72),'darkwood')
 for x in [4.4,6.4,8.4,10.4]:
  cube('Window golden pane',(x,-.085,1.05),(1.25,.035,.84),'glass',.15)
  for xx in [-.67,.67]:cube('Window jamb',(x+xx,-.14,1.04),(.1,.16,.98),'darkwood')
  for z in [.56,1.51]:cube('Window frame',(x,-.14,z),(1.42,.16,.1),'darkwood')
  cube('Window center',(x,-.15,1.04),(.06,.08,.9),'wood');cube('Window crossbar',(x,-.15,1.04),(1.3,.08,.055),'wood');cube('Window sill',(x,-.24,.54),(1.5,.42,.12),'wood')
 def rug(name,x,y,w,h,m):
  cube(name,((x+w/2)/32,-(y+h/2)/32,.035),(w/32,h/32,.035),m,.035)
  for z in [.08,.16]:
   xx=x/32;yy=-y/32;ww=w/32;hh=h/32
   border=tube(name+' gold border',[(xx+z,yy-z,.057),(xx+ww-z,yy-z,.057),(xx+ww-z,yy-hh+z,.057),(xx+z,yy-hh+z,.057),(xx+z,yy-z,.057)],.013,'gold')
   for p in border.data.splines[0].bezier_points:p.handle_left_type='VECTOR';p.handle_right_type='VECTOR'
 rug('Blue sleeping rug',144,73,144,86,'blue');rug('Green table rug',144,176,144,49,'greenrug')
 def bed(name,x,y,w,h):
  x=x/32;y=-y/32;w=w/32;h=h/32
  cube(name+' frame',(x+w/2,y-h/2,.35),(w,h,.2),'wood',.05)
  cube(name+' mattress',(x+w/2,y-h/2,.52),(w-.1,h-.14,.24),'cream',.12)
  cube(name+' blanket',(x+w/2,y-h*.69,.66),(w-.08,h*.51,.13),'red',.07)
  for ix in range(6):
   for iy in range(5):
    if (ix+iy)%2==0:cube(name+' woven check',(x+.04+(ix+.5)*(w-.08)/6,y-h*.435-(iy+.5)*h*.51/5,.731),((w-.08)/6-.005,h*.51/5-.005,.007),'black',.004)
  cube(name+' pillow',(x+w/2,y-h*.17,.72),(w*.75,h*.2,.19),'cream',.12)
  for xx in [x+.07,x+w-.07]:
   for yy in [y-.04,y-h+.04]:
    cyl(name+' turned post',(xx,yy,.56),.06,1.12,'wood');ellipsoid(name+' brass finial',(xx,yy,1.13),(.075,.075,.055),'gold')
  for yy,z in [(y-.03,.91),(y-h+.03,.71)]:
   cube(name+' carved board',(x+w/2,yy,z),(w-.18,.1,.28),'wood',.07)
   tube(name+' board trim',[(x+.18,yy-.065,z+.09),(x+w/2,yy-.065,z+.17),(x+w-.18,yy-.065,z+.09)],.02,'gold')
 bed('West bed',57,110,55,67);bed('Northwest bed',144,60,48,68);bed('Northeast bed',224,60,48,68)
 def table(name,x,y,w,h,z):
  x=x/32;y=-y/32;w=w/32;h=h/32
  cube(name+' top',(x+w/2,y-h/2,z),(w,h,.14),'wood',.06)
  for xx in [x+.13,x+w-.13]:
   for yy in [y-.13,y-h+.13]:
    cube(name+' leg',(xx,yy,z/2),(.12,.12,z),'darkwood');cyl(name+' foot',(xx,yy,.1),.09,.2,'wood')
  return (x+w/2,y-h/2,z+.09)
 center=table('Writing table',176,160,96,63,.9)
 for x in [182,220]:
  table('Chair',x,139,29,21,.43)
  for xx in [x+3,x+26]:cube('Chair rear upright',(xx/32,-142/32,.65),(.08,.08,.92),'wood')
  for z in [.67,.85]:cube('Chair back rail',((x+14.5)/32,-142/32,z),(.8,.07,.11),'wood')
 # Actual page volume and ceramic objects; no flat photographic prop.
 cx,cy,cz=center
 cube('Book leather cover',(cx-.45,cy+.3,cz+.035),(.75,.5,.05),'red',.025)
 for side in [-1,1]:
  p=cube('Open book pages',(cx-.45+side*.18,cy+.3,cz+.09),(.36,.46,.07),'paper',.02);p.rotation_euler.y=side*.12
  for i in range(6):tube('Page ink',[(cx-.45+side*.04,cy+.15+i*.05,cz+.13),(cx-.45+side*.29,cy+.15+i*.05,cz+.1)],.002,'darkwood')
 ellipsoid('Ink jar',(cx-.9,cy-.1,cz+.13),(.12,.12,.15),'ceramic');cyl('Ink rim',(cx-.9,cy-.1,cz+.26),.06,.04,'gold')
 # Cirrus is independent, using source anchor (755,1709), not baked into table.
 cirrus_before=set(bpy.data.objects);x=(755-512)/32;y=-(1709-1536)/32
 cyl('Cirrus pedestal',(x,y,.98),.14,.08,'steel');cyl('Cirrus stem',(x,y,1.12),.06,.24,'steel');ellipsoid('Cirrus housing',(x,y,1.28),(.12,.12,.14),'steel');cyl('Cirrus rim',(x,y,1.43),.07,.12,'gold')
 cirrus=[o for o in bpy.data.objects if o not in cirrus_before]
 for o in cirrus:o['source_actor']='Cirrus decor; exact silhouette refinement pending review'
 # Stair location is visual draft only. No new exit or collider is installed.
 for i in range(7):cube('Stair tread',(12.4,-5.7-i*.23,-i*.09+.02),(1.5,.25,.14),'darkwood')
 for x in [11.65,13.15]:
  cube('Stair newel',(x,-5.7,.43),(.13,.13,.86),'wood');tube('Stair rail',[(x,-5.7,.85),(x,-7.1,.31)],.045,'wood')
 return [o for o in bpy.data.objects if o not in before]

def light(name,loc,power,color,size,target):
 d=bpy.data.lights.new(name,'AREA');d.energy=power;d.color=color;d.shape='DISK';d.size=size;o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();return o
def camera(name,loc,target,scale):
 d=bpy.data.cameras.new(name);d.type='ORTHO';d.ortho_scale=scale;o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();return o
def render(path,cam):scene.camera=cam;scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
def export(objects,path):
 bpy.ops.object.select_all(action='DESELECT')
 for o in objects:o.select_set(True)
 bpy.context.view_layer.objects.active=objects[0]
 bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'EMPTY','MESH','OTHER'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_unit_scale=True)

from unity_player_v2 import build_player
hero,hero_objects=build_player(globals())
room_objects=room()
hero.location=((718-512)/32,-(1626-1536)/32,0);hero.rotation_euler.z=0
key=light('Window warm key',(4,1,7),1500,(1,.70,.38),5,(7,-4,0));fill=light('Cool soft fill',(10,-9,6),650,(.63,.74,1),7,(7,-4,0));rim=light('Amber room bounce',(14,-1,4),500,(1,.48,.19),4,(7,-4,0))
room_cam=camera('Room camera fixed 45 degrees',(7,-16,12),(7,-4,0),17.5)
scene.camera=room_cam
for o in hero_objects:o['stage']='U3 geometric appearance draft; rig pending approval'
for o in room_objects:o['collision']='visual only; source collision unchanged'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'startroom-draft.blend'))
render(OUT/'room-warm-review.png',room_cam)
export(room_objects,OUT/'room-draft.fbx')
hero.location=(0,0,0);hero.rotation_euler.z=0
export([hero]+hero_objects,OUT/'player-draft.fbx')
for o in room_objects:o.hide_render=True
key.location=(-2,-3,4);key.rotation_euler=(Vector((0,0,.55))-key.location).to_track_quat('-Z','Y').to_euler();key.data.energy=140
fill.location=(2,-1,2);fill.rotation_euler=(Vector((0,0,.55))-fill.location).to_track_quat('-Z','Y').to_euler();fill.data.energy=65;fill.data.size=3
rim.location=(1,2,3);rim.rotation_euler=(Vector((0,0,.55))-rim.location).to_track_quat('-Z','Y').to_euler();rim.data.energy=180;rim.data.size=2
cube('Portrait ground',(0,0,-.028),(200,200,.05),mat('Portrait ground',(.055,.075,.08)),.005)
scene.render.resolution_x=800;scene.render.resolution_y=1000
portrait=camera('Portrait camera',(0,-3,1.6),(0,0,.56),1.4)
for label,angle in [('front',0),('left',math.pi/2),('right',-math.pi/2),('back',math.pi)]:
 hero.rotation_euler.z=angle;render(OUT/f'player-{label}.png',portrait)
record={'stage':'U3 draft pending user review','units':'32 source world units per Unity/Blender metre','room_origin':[512,1536],'source_size':[448,256],'camera_pitch_degrees':45,'player_height_target':1.125,'rig_complete':False,'animations_complete':False,'runtime_art_accepted':False,'performance_tested':False,'references':['art/enhanced25d/v1/review/directions-review.png','art/enhanced25d/v1/layout.json'],'notes':['Procedural Blender meshes are editable.','Furniture draft volumes derive from visual registration, not new collision shapes.','Cirrus appearance and material detail remain draft interpretations.','Blender procedural material preview is not a claim of Unity material parity.']}
record['files']={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.iterdir() if p.suffix in ('.blend','.fbx','.png')}
(OUT/'draft-manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
print('U3_DRAFT_DONE')
