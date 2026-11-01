"""C1 restart: reference-led static surface modelling, not the old player base.

Blender Z-up, face towards -Y. No armature, animation, gameplay or physics.
Named separate surfaces are retained in the editable source collection.
"""
from pathlib import Path
import bpy, math, json, random, bisect
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'art/unity/player-refined-v2'
OUT.mkdir(parents=True, exist_ok=True)
if (OUT / 'review-lock.json').exists():
    raise RuntimeError('Frozen review; create another version')
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
bpy.context.preferences.filepaths.save_version = 0
random.seed(117)
M = {}
def material(key, color, rough=.65, metal=0):
    m = bpy.data.materials.new(key); m.diffuse_color = (*color, 1); m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough; p.inputs['Metallic'].default_value = metal
    M[key] = m
for key, color, rough, metal in [
    ('Warm skin',(.80,.46,.25),.68,0), ('Inner ear',(.50,.21,.10),.7,0),
    ('Chestnut',(.22,.072,.018),.64,0), ('Chestnut light',(.28,.103,.026),.64,0),
    ('Hair groove',(.13,.035,.008),.6,0), ('Hair strand',(.32,.125,.035),.5,0),
    ('Olive cloth',(.20,.30,.055),.85,0), ('Olive shade',(.16,.23,.038),.85,0),
    ('Trousers',(.29,.31,.09),.87,0), ('Linen',(.68,.58,.34),.9,0),
    ('Crimson',(.46,.022,.018),.83,0), ('Crimson fold',(.32,.012,.011),.85,0),
    ('Leather',(.14,.048,.018),.58,0), ('Leather edge',(.24,.092,.027),.6,0),
    ('Boot turn',(.43,.22,.060),.65,0), ('Brass',(.62,.34,.085),.35,.6),
    ('Sole',(.045,.023,.012),.8,0), ('Ivory feather',(.85,.75,.53),.72,0),
    ('Eye white',(.93,.87,.70),.30,0), ('Iris',(.20,.062,.012),.35,0),
    ('Pupil',(.009,.005,.003),.28,0), ('Mouth',(.24,.062,.026),.8,0)]:
    material(key,color,rough,metal)

def mesh(name, vertices, faces, mat):
    data=bpy.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
    data.materials.append(M[mat])
    for p in data.polygons:p.use_smooth=True
    return obj

def tube(name, points, radius, mat):
    data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.resolution_u=10
    data.bevel_depth=radius;data.bevel_resolution=2
    spline=data.splines.new('BEZIER');spline.bezier_points.add(len(points)-1)
    for p,co in zip(spline.bezier_points,points):p.co=co;p.handle_left_type='AUTO';p.handle_right_type='AUTO'
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);data.materials.append(M[mat]);return obj

def sphere(name, center, size, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=20,location=center)
    obj=bpy.context.object;obj.name=name;obj.scale=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(M[mat])
    for p in obj.data.polygons:p.use_smooth=True
    return obj

def catmull(values, t):
    u=t*(len(values)-1);i=min(len(values)-2,int(u));f=u-i
    a=Vector(values[max(0,i-1)]);b=Vector(values[i]);c=Vector(values[i+1]);d=Vector(values[min(len(values)-1,i+2)])
    return .5*((2*b)+(-a+c)*f+(2*a-5*b+4*c-d)*f*f+(-a+3*b-3*c+d)*f*f*f)

def loft(name, rows, mat, sides=48, steps=50, deform=None, cap=True):
    # rows: z, rx, ry, cx, cy. Continuous shaped cross-sections, not beads.
    vertices=[];faces=[]
    for j in range(steps):
        t=j/(steps-1);z,rx,ry,cx,cy=catmull(rows,t)
        for i in range(sides):
            a=2*math.pi*i/sides
            p=(cx+rx*math.cos(a),cy+ry*math.sin(a),z)
            vertices.append(deform(p,a,t) if deform else p)
    for j in range(steps-1):
        for i in range(sides):
            k=j*sides+i;l=j*sides+(i+1)%sides;faces.append((k,l,l+sides,k+sides))
    if cap:faces.extend([tuple(range(sides-1,-1,-1)),tuple((steps-1)*sides+i for i in range(sides))])
    return mesh(name,vertices,faces,mat)

def ribbon(name, points, widths, mat, normal=(0,-1,0), thick=.002):
    vertices=[];faces=[];n=Vector(normal).normalized();steps=48
    for j in range(steps):
        t=j/(steps-1);p=catmull(points,t)
        tangent=(catmull(points,min(1,t+.002))-catmull(points,max(0,t-.002))).normalized()
        axis=tangent.cross(n).normalized();w=catmull([(v,0,0) for v in widths],t).x
        for k in range(9):
            u=k/4-1;vertices.append(tuple(p+axis*w*u+n*thick*(1-u*u)))
    for j in range(steps-1):
        for k in range(8):a=j*9+k;faces.append((a,a+1,a+10,a+9))
    obj=mesh(name,vertices,faces,mat);s=obj.modifiers.new('Fabric thickness','SOLIDIFY');s.thickness=thick;return obj

# Face: flatter upper plane, tapering cheek/jaw; independent nose bridge surface.
profile=[(.620,.025,.038,0,-.018),(.638,.066,.067,0,-.007),(.660,.095,.083,0,0),
         (.691,.118,.091,0,.005),(.727,.124,.093,0,.008),(.765,.123,.096,0,.010),
         (.803,.118,.100,0,.012),(.842,.086,.081,0,.015),(.859,.010,.014,0,.015)]
face_samples=[catmull(profile,j/2048) for j in range(2049)]
face_heights=[p[0] for p in face_samples]
def face_params(z):
    # Invert the SAME smooth loft used by the head, including between control rows.
    i=max(0,min(len(face_samples)-2,bisect.bisect_right(face_heights,z)-1))
    a,b=face_samples[i],face_samples[i+1];t=max(0,min(1,(z-a[0])/max(1e-8,b[0]-a[0])))
    return tuple(a[k]*(1-t)+b[k]*t for k in (1,2,4))
def face_y(x,z):
    rx,ry,cy=face_params(z)
    y=cy-ry*max(.001,1-(x/max(rx,.001))**2)**.43
    y-=.006*math.exp(-((abs(x)-.075)/.028)**2-((z-.684)/.023)**2)
    y+=.003*math.exp(-((abs(x)-.049)/.027)**2-((z-.724)/.022)**2)
    y-=.004*math.exp(-(x/.015)**2-((z-.680)/.020)**2)
    y-=.006*math.exp(-(x/.014)**2-((z-.703)/.028)**2)
    return y
def face_deform(p,a,t):
    x,y,z=p
    if math.sin(a)<0:y=face_y(x,z)
    return x,y,z
face=loft('Face - defined cheek jaw and nose',profile,'Warm skin',96,100,face_deform)
loft('Neck',[(.570,.041,.037,0,.008),(.645,.039,.035,0,.008)],'Warm skin',32,12)
for s in [-1,1]:
    sphere('Ear rooted pinna',(s*.122,.003,.701),(.023,.017,.030),'Warm skin')
    sphere('Ear concha',(s*.132,-.011,.701),(.012,.004,.019),'Inner ear')
    tube('Ear helix',[(s*.123,-.015,.726),(s*.142,-.012,.710),(s*.139,-.013,.689),(s*.128,-.012,.681)],.0035,'Warm skin')

def almond(t,cx,cz,rx,rz):
    u=math.cos(t);v=math.sin(t)
    return cx+rx*u,cz+rz*v*(abs(v)**.35)+.004*u*(1 if cx>0 else -1)
def eye_patch(name,cx,cz,rx,rz,mat,offset,shaped=False):
    vertices=[(cx,face_y(cx,cz)-offset,cz)];faces=[];sides=64;rings=10
    for j in range(1,rings+1):
        r=j/rings
        for i in range(sides):
            t=2*math.pi*i/sides
            x,z=almond(t,cx,cz,rx*r,rz*r) if shaped else (cx+rx*r*math.cos(t),cz+rz*r*math.sin(t))
            vertices.append((x,face_y(x,z)-offset-.001*(1-r*r),z))
    for i in range(sides):faces.append((0,i+1,(i+1)%sides+1))
    for j in range(rings-1):
        for i in range(sides):a=1+j*sides+i;b=1+j*sides+(i+1)%sides;faces.append((a,b,b+sides,a+sides))
    return mesh(name,vertices,faces,mat)
for s in [-1,1]:
    x=s*.052;z=.722
    eye_patch('Almond eye opening',x,z,.030,.016,'Eye white',.001,True)
    eye_patch('Chestnut iris',x-s*.002,z,.0125,.0145,'Iris',.0028)
    eye_patch('Pupil',x-s*.002,z+.001,.0065,.0115,'Pupil',.0037)
    sphere('Eye catchlight',(x-.005,face_y(x-.005,z+.006)-.005,z+.006),(.003,.001,.0038),'Eye white')
    for top in [True,False]:
        pts=[]
        for k in range(23):
            t=(0 if top else math.pi)+math.pi*k/22;xx,zz=almond(t,x,z,.0305,.0165)
            pts.append((xx,face_y(xx,zz)-.002,zz))
        tube('Upper shaped lash' if top else 'Lower lid',pts,.0023 if top else .0011,'Chestnut' if top else 'Warm skin')
    # A tapered brow plane; inner brow lower gives the reference's alert expression.
    pts=[(s*.022,0,.749),(s*.044,0,.758),(s*.065,0,.762),(s*.084,0,.753)]
    ribbon('Tapered expressive eyebrow',[(xx,face_y(xx,zz)-.003,zz) for xx,_,zz in pts],[.002,.0045,.0035,.0004],'Chestnut',thick=.0008)
tube('Small mouth',[(x,face_y(x,z)-.001,z) for x,z in [(-.018,.651),(-.008,.648),(0,.648),(.010,.650),(.018,.654)]],.0011,'Mouth')

# Tailored torso: shoulders flow into the body, sleeves are conical cloth forms.
def cloth(p,a,t):
    x,y,z=p;front=max(0,-math.sin(a))
    y+=.0025*math.sin(a*7+t*4)*math.sin(math.pi*t)
    y+=.003*front*math.sin(a*12+t*5)*math.exp(-((z-.47)/.065)**2)
    return x,y,z
loft('Tunic torso shoulder waist',[(.376,.106,.065,0,.004),(.410,.103,.065,0,.004),
    (.455,.092,.058,0,.004),(.500,.104,.064,0,.005),(.545,.127,.067,0,.006),
    (.575,.134,.063,0,.010),(.597,.092,.045,0,.008),(.610,.045,.033,0,.008)],'Olive cloth',64,60,cloth)
# Neck opening is a sewn V panel with cream binding, not a solid cylindrical collar.
ribbon('Open V linen facing',[(-.044,-.037,.595),(-.026,-.063,.560),(0,-.070,.534),(.026,-.063,.560),(.044,-.037,.595)],[.006]*5,'Linen',thick=.002)
for s in [-1,1]:
    rows=[(.479,.046,.044,s*.156,.001),(.498,.051,.046,s*.154,.002),(.528,.052,.049,s*.143,.005),(.557,.048,.047,s*.126,.009),(.578,.033,.033,s*.113,.010)]
    loft('Tailored sleeve',rows,'Olive cloth',48,36,cloth)
    loft('Rolled linen sleeve',[(.471,.047,.045,s*.158,0),(.480,.055,.052,s*.158,0),(.501,.056,.053,s*.154,0),(.510,.052,.049,s*.151,0)],'Linen',48,20)
    ribbon('Sleeve leather tab',[(s*.191,-.024,.529),(s*.199,-.025,.503),(s*.198,-.026,.486)],[.009,.009,.008],'Leather edge',normal=(s,-1,0),thick=.002)
    tube('Sleeve brass clasp',[(s*.194,-.032,.506),(s*.204,-.032,.508),(s*.207,-.032,.497),(s*.197,-.032,.495),(s*.194,-.032,.506)],.0017,'Brass')

# Split four-panel tunic skirt. Borders follow panel edges instead of floating lines.
for quadrant in range(4):
    a0=-math.pi/2+quadrant*math.pi/2+.035;a1=a0+math.pi/2-.07
    vertices=[];faces=[];ns=32;nr=25
    def panel(u,t):
        a=a0+(a1-a0)*u
        rx=.103+.024*t;ry=.067+.017*t
        z=.425-.097*t+.020*t*(abs(2*u-1)**1.2)
        return (rx*math.cos(a),ry*math.sin(a)+.004+.002*math.sin(u*12)*t,z)
    for j in range(nr):
        for i in range(ns):vertices.append(panel(i/(ns-1),j/(nr-1)))
    for j in range(nr-1):
        for i in range(ns-1):a=j*ns+i;faces.append((a,a+1,a+1+ns,a+ns))
    o=mesh('Split tunic panel %d'%quadrant,vertices,faces,'Olive cloth');o.modifiers.new('Cloth edge thickness','SOLIDIFY').thickness=.0025
    # Broad flat sewn border along the hem and open edges.
    for edge in ['left','hem','right']:
        pts=[panel(0,k/20) if edge=='left' else panel(k/20,1) if edge=='hem' else panel(1,k/20) for k in range(21)]
        pts=[(x*1.013,y*1.013,z) for x,y,z in pts]
        ribbon('Flat woven tunic border',pts,[.004]*len(pts),'Linen',normal=(math.cos((a0+a1)/2),math.sin((a0+a1)/2),0),thick=.0008)
loft('Waist leather belt',[(.412,.108,.070,0,.003),(.438,.107,.069,0,.003)],'Leather',64,12)
for z in [.414,.436]:tube('Belt edge stitch',[(.109*math.cos(t),.071*math.sin(t)+.003,z) for t in [2*math.pi*k/64 for k in range(65)]],.0008,'Leather edge')
tube('Square rounded belt buckle',[(-.019,-.074,.412),(-.023,-.075,.419),(-.022,-.075,.438),(-.015,-.075,.441),(.020,-.075,.441),(.024,-.075,.436),(.024,-.075,.417),(.018,-.075,.411),(-.019,-.074,.412)],.0038,'Brass')
tube('Buckle pin',[(0,-.079,.415),(0,-.079,.436)],.0018,'Brass')
for i in range(3):sphere('Belt punched hole',(.034+i*.016,-.072,.425),(.0017,.0007,.0017),'Sole')

# Trousers taper to the gathered boot top; folds converge at knee and cuff.
for s in [-1,1]:
    def trouser(p,a,t):
        x,y,z=p;g=.0025*math.sin(a*7+t*4)*(.35+.65*abs(2*t-1))
        return x+g*math.cos(a),y+g*math.sin(a),z+.002*math.sin(a*3)*math.sin(math.pi*t)
    loft('Gathered trouser leg',[(.174,.038,.036,s*.066,.009),(.199,.044,.040,s*.066,.005),
        (.234,.058,.047,s*.065,.006),(.280,.064,.051,s*.062,.008),(.331,.066,.052,s*.058,.010),(.372,.063,.048,s*.054,.011)],'Trousers',48,50,trouser)
    # Anatomical arm with elbow taper, full palm and curled fingers; one merged skin volume.
    before=set(bpy.data.objects)
    arm=loft('Forearm surface',[(.299,.023,.021,s*.184,-.024),(.330,.024,.023,s*.184,-.012),(.371,.032,.027,s*.177,-.001),(.411,.035,.029,s*.166,.005),(.449,.036,.031,s*.159,.004),(.485,.035,.032,s*.154,.003)],'Warm skin',40,50)
    sphere('Palm volume',(s*.185,-.020,.290),(.031,.025,.034),'Warm skin')
    for k in range(4):
        xx=s*(.164+.012*k);zz=.273+[0,-.006,-.004,.003][k]
        sphere('Curled finger',(xx,-.034,zz),(.0087,.016,.017),'Warm skin')
    sphere('Resting thumb',(s*.160,-.042,.299),(.013,.015,.021),'Warm skin')
    bpy.ops.object.select_all(action='DESELECT')
    for o in set(bpy.data.objects)-before:o.select_set(True)
    bpy.context.view_layer.objects.active=arm;bpy.ops.object.join()
    mod=arm.modifiers.new('Continuous arm and hand','REMESH');mod.mode='VOXEL';mod.voxel_size=.0018;mod.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=arm.modifiers.new('Relax hand junctions','SMOOTH');mod.factor=.65;mod.iterations=5;bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=arm.modifiers.new('Static review surface reduction','DECIMATE');mod.ratio=.38;bpy.ops.object.modifier_apply(modifier=mod.name)

# Boots built as continuous sole-to-shaft sections, including the forward toe.
for s in [-1,1]:
    x=s*.068
    loft('Boot continuous vamp and shaft',[(.017,.049,.078,x,-.028),(.034,.052,.080,x,-.030),(.062,.050,.073,x,-.028),(.084,.044,.056,x,-.014),(.112,.035,.039,x,.006),(.159,.039,.040,x,.009),(.192,.043,.042,x,.009)],'Leather',64,60)
    loft('Stacked boot sole',[(.004,.048,.076,x,-.029),(.011,.054,.082,x,-.029),(.023,.054,.082,x,-.029),(.029,.051,.080,x,-.029)],'Sole',64,16)
    loft('Boot turned cuff',[(.160,.039,.041,x,.008),(.175,.050,.048,x,.009),(.205,.052,.047,x,.010),(.211,.046,.042,x,.010)],'Boot turn',64,25)
    tube('Boot toe panel seam',[(x+dx,-.085+.025*(dx/.044)**2,.063+.006*(1-(dx/.044)**2)) for dx in [(-.044+i*.0044) for i in range(21)]],.0011,'Leather edge')
    ribbon('Boot instep strap',[(x-.044,-.025,.083),(x-.024,-.065,.090),(x,-.071,.094),(x+.024,-.065,.090),(x+.044,-.025,.083)],[.007]*5,'Leather edge',normal=(0,-.7,1),thick=.0015)
    ribbon('Boot cuff flap',[(x+s*.040,-.006,.205),(x+s*.049,-.026,.189),(x+s*.039,-.044,.165)],[.015,.018,.011],'Boot turn',normal=(s,-1,0),thick=.002)
    for z in [.130,.147]:tube('Boot soft ankle fold',[(x-.033,-.017,z),(x,-.033,z+.003),(x+.033,-.017,z-.002)],.0018,'Leather edge')

# A draped, layered scarf: dipped front folds and a rear knot/tails.
vertices=[];faces=[];ns=96;nr=16
for j in range(nr):
    t=j/(nr-1)
    for i in range(ns):
        a=2*math.pi*i/ns;f=max(0,-math.sin(a));r=.051+.033*math.sin(math.pi*t*.85)
        z=.622-.048*t-.035*f*math.sin(math.pi*t/2)
        r+=.003*math.cos(t*math.pi*5)*(f*.6+.4)
        vertices.append((r*math.cos(a),r*.77*math.sin(a),z))
for j in range(nr-1):
    for i in range(ns):a=j*ns+i;b=j*ns+(i+1)%ns;faces.append((a,b,b+ns,a+ns))
scarf=mesh('Draped scarf collar folds',vertices,faces,'Crimson');scarf.modifiers.new('Wool thickness','SOLIDIFY').thickness=.003
ribbon('Scarf front triangular fall',[(-.035,-.054,.579),(-.031,-.072,.548),(-.020,-.078,.502),(.004,-.079,.523)],[.020,.022,.004,.0005],'Crimson',thick=.003)
sphere('Rear scarf knot',(.018,.068,.598),(.024,.020,.022),'Crimson')
for k in range(2):ribbon('Scarf rear tail',[(.018,.080,.599),(.044+k*.024,.092,.570),(.061+k*.038,.084,.530-k*.013),(.084+k*.032,.072,.551-k*.022)],[.017,.021,.013,.0005],'Crimson',normal=(0,1,0),thick=.003)

# Fitted scalp plus overlapping swept locks; each lock has longitudinal relief.
sphere('Continuous hair foundation',(0,.048,.838),(.148,.130,.104),'Chestnut')
sphere('Occipital foundation',(0,.084,.790),(.134,.105,.109),'Chestnut')
loft('Cloth headband',[(.771,.129,.103,0,.010),(.811,.128,.105,0,.010)],'Olive cloth',80,15)
tube('Headband lower seam',[(.130*math.cos(a),.104*math.sin(a)+.010,.774) for a in [2*math.pi*i/80 for i in range(81)]],.0009,'Olive shade')
sphere('Headband rear knot',(.023,.115,.793),(.020,.013,.017),'Olive cloth')
for k in range(2):ribbon('Headband loose tie',[(.022,.122,.791),(.020+k*.025,.131,.756),(.003+k*.052,.116,.719)],[.012,.015,.001],'Olive cloth',normal=(0,1,0),thick=.0015)

def lock(name, points, width, normal, mat='Chestnut', detail=True):
    # A continuous curved leaf embedded at its root. Long narrow creases are actual geometry.
    steps=40;sides=40;vertices=[];faces=[];n=Vector(normal).normalized()
    def at(t,angle):
        p=catmull(points,t);d=(catmull(points,min(1,t+.001))-catmull(points,max(0,t-.001))).normalized()
        u=d.cross(n).normalized();v=u.cross(d).normalized()
        w=width*(.72+.42*math.sin(math.pi*t))*(1-t)**.70+.00012
        c=math.cos(angle);h=math.sin(angle)
        ridge=1+(.07 if detail else 0)*math.cos(c*math.pi*9+2*t)*max(0,h)
        return p+u*w*c+v*w*.47*h*ridge
    for j in range(steps):
        for i in range(sides):vertices.append(tuple(at(j/(steps-1),2*math.pi*i/sides)))
    for j in range(steps-1):
        for i in range(sides):a=j*sides+i;b=j*sides+(i+1)%sides;faces.append((a,b,b+sides,a+sides))
    faces.extend([tuple(range(sides-1,-1,-1)),tuple((steps-1)*sides+i for i in range(sides))])
    obj=mesh(name,vertices,faces,mat)
    return obj

# Crown flows up/back from a right-of-centre whorl, with layered lateral fans.
crown=[
    ([(.034,-.025,.847),(-.027,-.009,.939),(-.115,.010,1.025),(-.206,.018,1.018)],.045,(0,-1,.2)),
    ([(.040,.004,.853),(-.005,.046,.978),(-.076,.063,1.070),(-.133,.071,1.096)],.043,(0,-1,.5)),
    ([(.048,.035,.851),(.048,.056,.986),(.015,.071,1.094),(-.028,.077,1.125)],.040,(0,-1,.25)),
    ([(.061,.045,.849),(.106,.067,.970),(.101,.100,1.056),(.077,.130,1.089)],.040,(1,-.5,.2)),
    ([(.075,.047,.835),(.158,.074,.927),(.180,.106,1.008),(.167,.137,1.042)],.039,(1,-.5,.2)),
    ([(.068,.080,.828),(.156,.142,.893),(.216,.184,.939),(.235,.201,.979)],.040,(1,1,.2)),
    ([(.045,.091,.829),(.074,.173,.945),(.128,.222,.970),(.166,.243,.966)],.042,(0,1,.5)),
    ([(.006,.100,.830),(-.055,.167,.921),(-.128,.206,.951),(-.200,.222,.923)],.043,(0,1,.3))]
for i,(points,w,n) in enumerate(crown):
    points=[(x,y+.015*j,z-.028*(j/3)) for j,(x,y,z) in enumerate(points)]
    lock('Crown flowing layer %02d'%i,points,w*1.48,n,'Chestnut light' if i%3==0 else 'Chestnut')
# Successive front layers cover the parting-to-crown surface. Their roots run
# underneath the fringe and tips overlap the upper fan, closing the bald cap.
for k in range(5):
    lock('Continuous swept crown front %02d'%k,
         [(.045+k*.007,-.074+k*.011,.869+k*.014),
          (-.008+k*.005,-.112+k*.013,.940+k*.016),
          (-.105+k*.012,-.092+k*.017,.977+k*.016),
          (-.209+k*.018,-.057+k*.022,.957+k*.025)],
         .041,(0,-1,.12),'Chestnut light' if k%3==0 else 'Chestnut')
# Interleaving mid layers cover the cap in profile and rear views. They follow
# the crown surface before ending outside it, instead of radiating from a pole.
for k in range(15):
    a=2*math.pi*k/15
    if math.sin(a)<-.55:continue
    ca,sa=math.cos(a),math.sin(a)
    pts=[(.025+ca*.040,.055+sa*.025,.945),
         (ca*.125,.055+sa*.120,.950),
         (ca*.175,.055+sa*.155,.879),
         (ca*.201,.055+sa*.156,.811+(k%3)*.012)]
    lock('Interleaved crown mantle %02d'%k,pts,.050,(ca,sa,.25),'Chestnut light' if k%4==0 else 'Chestnut')
for s in [-1,1]:
    for k in range(3):
        lock('Side swept root bridge',[(s*.055,-.015,.902+k*.010),
             (s*.126,-.044+k*.020,.925),(s*.169,-.037+k*.025,.885),
             (s*.183,-.017+k*.030,.817-k*.015)],.038,(s,-.7,0),'Chestnut')
# Front fans connect to a common parting and divide into slender tips, avoiding a crown of cones.
fronts=[
    ([(.028,-.050,.861),(-.067,-.090,.949),(-.162,-.077,.949),(-.239,-.065,.913)],.044),
    ([(.025,-.068,.856),(-.075,-.117,.908),(-.167,-.114,.890),(-.224,-.094,.844)],.043),
    ([(.020,-.079,.848),(-.073,-.137,.872),(-.150,-.137,.828),(-.180,-.115,.758)],.038),
    ([(.027,-.083,.849),(-.031,-.147,.839),(-.074,-.146,.780),(-.091,-.115,.711)],.032),
    ([(.036,-.080,.852),(.005,-.151,.830),(-.016,-.143,.773),(-.022,-.113,.721)],.028),
    ([(.044,-.073,.852),(.071,-.132,.844),(.092,-.130,.811),(.082,-.106,.778)],.025),
    ([(.047,-.057,.855),(.107,-.095,.894),(.157,-.083,.882),(.201,-.056,.848)],.034)]
for i,(p,w) in enumerate(fronts):lock('Parted fringe %02d'%i,p,w,(0,-1,0),'Chestnut light' if i in [1,3] else 'Chestnut')
for s in [-1,1]:
    for k in range(4):
        lock('Layered temple and side',[(s*.069,.013+k*.026,.888-k*.008),(s*.145,.015+k*.036,.875-k*.022),(s*.178,.032+k*.040,.802-k*.018),(s*(.168-k*.005),.053+k*.030,.718-k*.006)],.041,(s,-.25 if k<2 else .5,0),'Chestnut light' if k==1 else 'Chestnut')
    for k in range(4):
        x=s*(.018+k*.030)
        lock('Nape interlocking layer',[(x*.65,.112,.857),(x,.182,.808),(x*1.18,.174,.752),(x*1.25,.137,.694+(k%2)*.019)],.036,(0,1,0))

# A thin ivory feather at the character's left temple, with a visible vane edge.
lock('Ivory feather vane',[(.133,-.116,.793),(.170,-.123,.849),(.202,-.117,.915),(.225,-.103,.976)],.026,(0,-1,.1),'Ivory feather',False)
tube('Feather shaft',[(.134,-.128,.791),(.170,-.135,.849),(.201,-.129,.915),(.225,-.111,.976)],.0012,'Linen')
for k in range(12):
    t=k/12;x=.137+.088*t;z=.800+.168*t
    tube('Feather branching barb',[(x-.015*(1-t),-.135+.018*t,z+.013),(x,-.137+.020*t,z),(x+.015*(1-t),-.135+.020*t,z+.025)],.00065,'Linen')

# Preserve separate editable surfaces, then make an identical joined export mesh.
editable=bpy.data.collections.new('EDITABLE - unrigged reference surfaces');bpy.context.scene.collection.children.link(editable)
objects=[o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE')]
for o in objects:
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    bpy.ops.object.convert(target='MESH')
    for mod in list(o.modifiers):bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
floor=min(v.co.z for o in objects for v in o.data.vertices);top=max(v.co.z for o in objects for v in o.data.vertices)
scale=1.125/(top-floor)
for o in objects:
    for v in o.data.vertices:v.co=Vector((v.co.x*scale,v.co.y*scale,(v.co.z-floor)*scale))
    o['stage']='C1 static silhouette; no skinning or animation'
    copy=o.copy();copy.data=o.data.copy();editable.objects.link(copy)
editable.hide_render=True;editable.hide_viewport=True
bpy.ops.object.select_all(action='DESELECT')
for o in objects:o.select_set(True)
bpy.context.view_layer.objects.active=face;bpy.ops.object.join();model=bpy.context.object;model.name='MAP001_PLAYER_REFINED_STATIC'
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY',ngon_method='BEAUTY');bpy.ops.object.mode_set(mode='OBJECT')
while len(model.data.uv_layers):model.data.uv_layers.remove(model.data.uv_layers[0])
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.002,correct_aspect=True);bpy.ops.object.mode_set(mode='OBJECT')
model.data.uv_layers.active.name='CharacterAtlasUV'
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=8;scene.world.color=(.1,.1,.1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'player-refined.blend'))
bpy.ops.export_scene.fbx(filepath=str(OUT/'player-static.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
bpy.ops.export_scene.fbx(filepath=str(OUT/'player-surface.fbx'),use_selection=True,object_types={'MESH'},bake_anim=False,add_leaf_bones=False,axis_forward='-Z',axis_up='Y',apply_scale_options='FBX_SCALE_ALL')
palette={m.name:{'linear_color':list(m.diffuse_color),'roughness':m.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value,'metallic':m.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value} for m in model.data.materials}
(OUT/'surface-materials.json').write_text(json.dumps(palette,indent=2)+'\n',encoding='utf-8')
(OUT/'geometry.json').write_text(json.dumps({'stage':'C1 reference-led rebuild, static C2 review pending','height':1.125,'vertices':len(model.data.vertices),'triangles':len(model.data.polygons),'editable_surface_count':len(objects),'previous_player_geometry_reused':False,'skinning_complete':False,'animation_complete':False,'performance_tested':False},indent=2)+'\n',encoding='utf-8')
print('STATIC_REBUILD_DONE',OUT)
