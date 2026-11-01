"""Second U3 geometric character study: proportions, sculpted face, swept hair.
Not a finished animation asset. Called by the Blender draft scene generator.
"""
import bpy,math
from mathutils import Vector

def build_player(api):
    M=api['M'];mat=api['mat'];ellipsoid=api['ellipsoid'];cube=api['cube'];tube=api['tube'];rings=api['rings'];limb=api['limb'];tapered=api['tapered'];cyl=api['cyl'];assign=api['assign'];smooth=api['smooth']
    before=set(bpy.data.objects)
    M['stitch']=mat('Linen stitching',(.53,.37,.17),.85)
    M['cuff']=mat('Warm folded leather',(.26,.105,.026),.58)
    M['hairgroove']=mat('Hair carved strand',(.105,.029,.006),.44)
    M['hairshine']=mat('Hair fine strand light',(.34,.13,.03),.38)
    M['lip']=mat('Soft lip',(.31,.11,.065),.7)
    M['skin'].node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.72,.40,.235,1)
    M['skin'].diffuse_color=(.72,.40,.235,1)

    def head_y(x,z):
        # Front facial surface; eyes lie in the surface, not on spherical buttons.
        v=max(.01,1-(x/.151)**2-((z-.755)/.161)**2)
        return -.125*math.sqrt(v)
    head=ellipsoid('Sculpted tapered face',(0,0,.755),(.151,.125,.161),'skin')
    subdivision=head.modifiers.new('Smooth sculpting base','SUBSURF');subdivision.levels=2;bpy.context.view_layer.objects.active=head;bpy.ops.object.modifier_apply(modifier=subdivision.name)
    for v in head.data.vertices:
        if v.co.z<-.025:v.co.x*=1-.17*min(1,(-v.co.z-.025)/.13)
    face_parts=[head]
    for side in [-1,1]:
        face_parts.append(ellipsoid('Ear base',(side*.145,.005,.753),(.025,.018,.039),'skin'))
    face_parts.append(ellipsoid('Small integrated nose',(0,-.126,.728),(.012,.012,.013),'skin'))
    face_parts.append(limb('Nose bridge',(0,-.12,.753),(0,-.133,.73),(.009,.009),'skin'))
    # Merge facial volumes before adding eyes, avoiding a separate chin/ball seam.
    bpy.ops.object.select_all(action='DESELECT')
    for o in face_parts:o.select_set(True)
    bpy.context.view_layer.objects.active=head;bpy.ops.object.join()
    mod=head.modifiers.new('Unified facial surface','REMESH');mod.mode='VOXEL';mod.voxel_size=.0022;mod.use_smooth_shade=True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=head.modifiers.new('Soft facial transitions','SMOOTH');mod.factor=.65;mod.iterations=3;bpy.ops.object.modifier_apply(modifier=mod.name)
    smooth(head)
    for side in [-1,1]:
        tube('Ear inner fold',[(side*.157,-.009,.773),(side*.16,-.012,.757),(side*.153,-.012,.743)],.0025,'ear')

    def patch(name,cx,cz,rx,rz,m,depth=.001,almond=False):
        n=48;rings_count=7;verts=[(cx,head_y(cx,cz)-depth,cz)];faces=[]
        for j in range(1,rings_count+1):
            r=j/rings_count
            for i in range(n):
                t=2*math.pi*i/n;x=cx+rx*r*math.cos(t);z=cz+rz*r*math.sin(t)*(abs(math.sin(t))**.35 if almond else 1)
                verts.append((x,head_y(x,z)-.0008-depth*(1-.25*r*r),z))
        for i in range(n):faces.append((0,1+i,1+(i+1)%n))
        for j in range(rings_count-1):
            for i in range(n):a=1+j*n+i;b=1+j*n+(i+1)%n;faces.append((a,a+n,b+n,b))
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);assign(o,m);smooth(o);return o
    for side in [-1,1]:
        x=side*.059;z=.774
        patch('Almond sclera',x,z,.037,.031,'white',.003,True)
        patch('Brown iris',x,z-.001,.021,.026,'iris',.006)
        patch('Deep pupil',x,z,.0085,.017,'pupil',.008)
        ellipsoid('Eye highlight',(x-.005,head_y(x-.005,z+.011)-.010,z+.011),(.005,.0015,.006),'white')
        points=[]
        for i in range(13):
            t=math.pi*i/12;xx=x+.037*math.cos(t);zz=z+.031*math.sin(t)**1.35;points.append((xx,head_y(xx,zz)-.002,zz))
        tube('Upper lash',points,.0026,'hair')
        points=[]
        for i in range(9):
            xx=x-.033+i*.066/8;zz=.826+.009*math.sin(i*math.pi/8);points.append((xx,head_y(xx,zz)-.003,zz))
        tapered('Tapered brow',[points[0],points[4],points[-1]],.0055,'hair',.22)
    tube('Small soft smile',[(-.022,head_y(-.022,.697)-.002,.697),(0,head_y(0,.692)-.003,.692),(.023,head_y(.023,.699)-.002,.699)],.0018,'lip')
    cyl('Neck',(0,0,.61),.047,.10,'skin')

    # Slimmer shoulder/arm silhouette and individually modelled relaxed fingers.
    for side in [-1,1]:
        limb('Olive sleeve',(side*.112,0,.567),(side*.153,-.003,.50),(.057,.057),'tunic')
        limb('Rolled linen cuff',(side*.146,-.004,.509),(side*.161,-.006,.481),(.055,.055),'cream')
        arm=limb('Upper forearm',(side*.159,-.006,.479),(side*.174,-.017,.402),(.035,.033),'skin')
        lower_arm=limb('Lower forearm',(side*.174,-.017,.412),(side*.187,-.033,.348),(.029,.027),'skin')
        palm=ellipsoid('Palm',(side*.187,-.032,.327),(.030,.024,.037),'skin');hand=[palm]
        for i in range(4):
            xx=side*(.168+i*.012);length=[.039,.047,.045,.034][i]
            a=(xx,-.04,.319);b=(xx+side*.003,-.049,.319-length)
            hand.append(limb('Finger %d'%i,a,b,(.0075,.007),'skin'))
            tube('Knuckle fold',[(xx-.004,-.054,.310),(xx+.004,-.054,.310)],.0008,'ear')
        hand.append(limb('Thumb',(side*.165,-.047,.344),(side*.152,-.054,.318),(.010,.009),'skin'))
        bpy.ops.object.select_all(action='DESELECT')
        for o in hand:o.select_set(True)
        bpy.context.view_layer.objects.active=palm;bpy.ops.object.join();mod=palm.modifiers.new('Connected hand','REMESH');mod.mode='VOXEL';mod.voxel_size=.0018;mod.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=mod.name)
        mod=palm.modifiers.new('Hand smoothing','SMOOTH');mod.factor=.5;mod.iterations=2;bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.ops.object.select_all(action='DESELECT')
        for o in [palm,arm,lower_arm]:o.select_set(True)
        bpy.context.view_layer.objects.active=palm;bpy.ops.object.join();mod=palm.modifiers.new('Continuous arm anatomy','REMESH');mod.mode='VOXEL';mod.voxel_size=.0018;mod.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=mod.name)
        mod=palm.modifiers.new('Elbow and wrist blending','SMOOTH');mod.factor=.5;mod.iterations=3;bpy.ops.object.modifier_apply(modifier=mod.name);smooth(palm)
        cube('Sleeve small brass clasp',(side*.161,-.052,.499),(.020,.009,.026),'gold',.004)

    torso=rings('Layered split tunic',[(.303,.133,.082,0,0),(.35,.139,.086,0,0),(.4,.106,.075,0,0),(.47,.116,.079,0,0),(.54,.126,.081,0,0),(.586,.084,.058,0,0)],'tunic',64)
    # Lift the front-center hem into two tailored flaps, instead of a toy ring.
    for v in torso.data.vertices:
        if v.co.y<0 and v.co.z<.36:v.co.z+=.042*math.exp(-(v.co.x/.028)**2)*max(0,(.36-v.co.z)/.057)
        if v.co.z>.36:v.co.y+=.0025*math.sin(v.co.x*93)*math.sin((v.co.z-.36)*19)
    for side in [-1,1]:
        tube('Coat lapel piping',[(side*.052,-.054,.586),(side*.034,-.079,.54),(0,-.083,.494)],.0035,'stitch')
        tube('Tailored front opening',[(0,-.081,.397),(side*.008,-.083,.36),(side*.027,-.086,.311)],.0027,'stitch')
        points=[]
        for i in range(20):
            t=math.pi+i*math.pi/19;xx=.133*math.cos(t);yy=.082*math.sin(t);zz=.305+.042*math.exp(-(xx/.028)**2)
            points.append((xx,yy,zz))
        tube('Fine stitched hem',points,.003,'stitch')
        for i in range(5):
            x=side*(.038+i*.016);tube('Short waist fold',[(x,-.078,.398),(x*1.1,-.088,.361),(x*1.2,-.083,.328)],.0009,'pants')
    rings('Belt fitted leather',[(.391,.111,.080,0,0),(.423,.109,.080,0,0)],'leather',48)
    cube('Belt buckle outer',(0,-.086,.406),(.041,.010,.031),'gold',.005);cube('Belt buckle leather inset',(0,-.093,.406),(.027,.008,.018),'leather',.002)
    tube('Buckle tongue',[(0,-.100,.416),(0,-.100,.398)],.0018,'gold')
    for x in [.042,.06,.077]:ellipsoid('Belt punched hole',(x,-.073,.406),(.0015,.001,.0015),'black')
    for side in [-1,1]:
        x=side*.061
        leg=rings('Baggy trouser leg',[(.18,.046,.046,x,0),(.22,.052,.051,x,0),(.27,.063,.063,x,0),(.32,.064,.065,x,0),(.355,.058,.059,x,0)],'pants',40)
        for v in leg.data.vertices:
            v.co.y+=.003*math.sin(v.co.x*140+v.co.z*55)
        for k in range(3):tube('Trouser knee crease',[(x-.032,-.047,.213+k*.017),(x,-.057,.217+k*.017),(x+.025,-.049,.209+k*.017)],.0012,'tunic')
        ellipsoid('Shaped boot sole',(x,-.026,.023),(.057,.088,.021),'darkwood')
        ellipsoid('Leather boot vamp',(x,-.035,.057),(.055,.081,.045),'leather')
        rings('Fitted boot shaft',[(.058,.048,.05,x,.005),(.13,.044,.047,x,.008),(.188,.05,.05,x,.008)],'leather',36)
        rings('Folded matte leather cuff',[(.169,.056,.058,x,.007),(.201,.058,.058,x,.007)],'cuff',36)
        tube('Boot front seam',[(x-.045,-.037,.065),(x,-.083,.077),(x+.045,-.037,.065)],.0018,'cuff')
        for z in [.093,.12]:
            tube('Boot ankle strap',[(x-.045,-.012,z),(x,-.05,z-.006),(x+.045,-.012,z)],.006,'cuff')
        cube('Boot buckle',(x+side*.044,-.02,.117),(.013,.013,.017),'gold',.003)
        for k in range(4):tube('Boot stitching',[(x-.032+k*.02,-.061,.074),(x-.029+k*.02,-.062,.076)],.0007,'cream')

    rings('Red scarf neck folds',[(.568,.069,.057,0,0),(.596,.088,.073,0,0),(.624,.069,.058,0,0)],'red')
    for k in range(3):tube('Scarf draped fold',[(-.069,-.04,.61-k*.007),(0,-.085,.578-k*.007),(.069,-.04,.605-k*.007)],.006,'red')
    tapered('Scarf front point',[(-.018,-.075,.588),(-.04,-.088,.526),(-.025,-.075,.481)],.024,'red',.16)
    ellipsoid('Scarf rear knot',(.035,.07,.597),(.027,.025,.029),'red')
    tapered('Scarf tail upper',[(.03,.08,.598),(.117,.1,.63),(.16,.13,.58)],.026,'red',.14)
    tapered('Scarf tail lower',[(.03,.08,.586),(.079,.12,.539),(.10,.13,.489)],.025,'red',.14)

    ellipsoid('Hair fitted base',(0,.018,.862),(.157,.131,.113),'hair')
    ellipsoid('Hair nape volume',(0,.047,.776),(.142,.107,.112),'hair')
    band=rings('Woven green headband',[(.831,.156,.132,0,.004),(.865,.155,.132,0,.004)],'tunic',64)
    for v in band.data.vertices:
        if v.co.y>0:v.co.y*=1.22
    ellipsoid('Headband rear knot',(.026,.167,.848),(.028,.018,.021),'tunic')
    tapered('Headband tie one',[(.025,.174,.842),(.025,.176,.805),(.008,.173,.777)],.018,'tunic',.15)
    tapered('Headband tie two',[(.029,.174,.842),(.055,.176,.815),(.063,.17,.786)],.017,'tunic',.15)

    def hairlock(name,points,width,light=False,strands=4):
        tapered(name,points,width,'hairlight' if light else 'hair',.65)
        a,b,c=map(Vector,points)
        for strand in range(strands):
            off=(strand-(strands-1)/2)*width*.27;path=[]
            for j in range(10):
                t=.08+j*.084;p=(1-t)**2*a+2*t*(1-t)*b+t*t*c
                tangent=(2*(1-t)*(b-a)+2*t*(c-b)).normalized();normal=tangent.cross(Vector((0,1,0)))
                if normal.length<.1:normal=tangent.cross(Vector((1,0,0)))
                normal.normalize();p+=normal*off*(1-t)**.6;p.y-=width*.29*(1-t)**.6;path.append(tuple(p))
            tube(name+' strand',path,.0009,'hairshine' if strand%3==0 else 'hairgroove')
    # Broad, swept groups point across the silhouette rather than radial spikes.
    locks=[
      ([(.04,.025,.928),(-.105,.015,1.105),(-.235,.01,1.035)],.049),
      ([(.065,.065,.93),(-.05,.10,1.10),(-.205,.125,1.04)],.046),
      ([(.075,.085,.90),(-.01,.17,1.02),(-.175,.20,.98)],.045),
      ([(.035,.09,.89),(-.08,.18,.96),(-.23,.18,.91)],.042),
      ([(.04,-.025,.934),(-.10,-.066,1.02),(-.245,-.06,.965)],.046),
      ([(.03,-.055,.91),(-.11,-.11,.967),(-.23,-.11,.902)],.045),
      ([(.075,-.03,.94),(.075,-.01,1.07),(.018,0,1.125)],.038),
      ([(.095,.01,.92),(.19,.035,1.02),(.17,.06,1.08)],.037),
      ([(.11,.055,.895),(.215,.11,.97),(.222,.13,1.02)],.037),
      ([(.11,.10,.87),(.21,.16,.90),(.245,.19,.93)],.034),
    ]
    for i,(points,w) in enumerate(locks):hairlock('Swept crown %02d'%i,points,w,i%3==0,5)
    for k in range(9):
        angle=math.pi*k/8
        hairlock('Layered rear crown %02d'%k,[(.07*math.cos(angle),.08+.05*math.sin(angle),.91),(.15*math.cos(angle)-.03,.14+.07*math.sin(angle),.993),(.22*math.cos(angle)-.04,.17+.075*math.sin(angle),.94+(k%3)*.022)],.039,k%3==1,4)
    for i,(x,tipx,z) in enumerate([(-.095,-.158,.79),(-.055,-.119,.77),(-.005,-.069,.755),(.045,-.005,.773),(.083,.05,.807),(.115,.115,.82)]):
        hairlock('Layered fringe %02d'%i,[(x+.03,-.065,.938),(x-.025,-.142,.90),(tipx,-.142,z)],.030 if i<4 else .024,i%2==0,4)
    for side in [-1,1]:
        hairlock('Temple side lock',[(side*.13,-.025,.87),(side*.17,-.026,.80),(side*.151,-.036,.715)],.025,False,3)
        for k in range(5):
            x=side*(.019+k*.028);hairlock('Layered nape',[(x*.8,.132,.833),(x,.174,.755),(x*1.13,.145,.639+(k%2)*.024)],.029,k%3==0,3)
    # Pale, veined feather with thin physical volume and a curved quill.
    tapered('Light feather blade',[(-.144,-.008,.842),(-.213,.015,.961),(-.198,.018,1.067)],.031,'feather',.095)
    tube('Feather curved quill',[(-.144,-.017,.842),(-.19,.004,.963),(-.198,.008,1.067)],.0017,'cream')
    for k in range(11):
        z=.867+k*.016;x=-.155-.042*math.sin((z-.84)/.23*math.pi)
        tube('Feather fine vein',[(x+.015,-.008,z+.009),(x,-.010,z),(x-.021,-.006,z+.021)],.0007,'cream')

    objects=[o for o in bpy.data.objects if o not in before];root=bpy.data.objects.new('MAP001_PLAYER_U3_REFINED_DRAFT',None);bpy.context.collection.objects.link(root)
    for o in objects:o.parent=root
    return root,objects
