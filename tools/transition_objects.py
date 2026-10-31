"""MAP001 landing objects/actor derived from original prototypes and programs.

No post-transfer RAM is used to initialize or advance these objects.
"""
import struct
from dataclasses import dataclass
from event_actor_reference import word,put,decode
from transition_source import sources,initialization


class Resources:
    def __init__(self,story):
        self.twn,self.source=sources()
        self.operations=initialization(self.source,self.twn,story)
        self.actor_table=next(r['table_offsets'][0] for r in self.operations if r['action']=='set_actor_resource_tables')
        command=next(r for r in self.operations if r['action']=='set_object_resource_tables')
        count=int.from_bytes(self.source[command['offset']+1:command['offset']+3],'big')
        sizes,images,animations=command['table_offsets']
        if count!=30:raise ValueError('Unverified landing resource count')
        self.assets=[];texture=32
        for i in range(count):
            size=word(self.source,sizes+i*2)
            self.assets.append({'texture':texture,'count':size,
                'images':int.from_bytes(self.source[images+4*i:images+4*i+4],'big'),
                'animation':int.from_bytes(self.source[animations+4*i:animations+4*i+4],'big')})
            texture+=size

    def read(self,address,size):
        start=address-0x260e0000+8
        if size<1 or start<8 or start+size>0xf230:raise ValueError('Landing resource pointer outside source segment')
        return self.source[start:start+size]

    def pointer(self,address):return int.from_bytes(self.read(address,4),'big')

    def prototype(self,resource):
        if resource not in (*range(32,40),50):raise ValueError('Unverified landing prototype')
        raw=self.source[self.actor_table+resource*11:self.actor_table+(resource+1)*11]
        asset=word(raw,0)
        if asset>=len(self.assets):raise ValueError('Invalid landing resource index')
        return raw,asset,self.assets[asset]

    def sequence(self,root,selector):
        address=self.pointer(root+4*selector)
        raw=bytearray()
        for cursor in range(0,256,3):
            duration=self.read(address+cursor,1)[0]
            if duration==0:return bytes(raw)+b'\0'
            record=self.read(address+cursor,3)
            if record[2] not in (0,4):raise ValueError('Unknown landing animation side effect')
            raw.extend(record)
        raise ValueError('Unterminated landing animation')


@dataclass
class ObjectProgram:
    sequence:bytes
    images:dict


def initialize_objects(resources):
    objects=[];programs=[]
    for operation in resources.operations:
        if operation['action']!='spawn_scene_object':continue
        rid=operation['resource_id'];proto,asset_id,asset=resources.prototype(rid)
        opts=operation['options']
        if opts[:3]!=[0,0,1] or len(opts)!=4 or opts[3] not in (0,1,2):
            raise ValueError('Unknown landing object motion mode')
        sequence=resources.sequence(asset['animation'],opts[3])
        if any(sequence[i+2] for i in range(0,len(sequence)-1,3)):
            raise ValueError('Unverified object reflection or movement')
        indices={0,*sequence[1:-1:3]}
        images={i:resources.pointer(asset['images']+4*i) for i in indices}
        raw=bytearray(60)
        values={0:operation['world_xy_raw'][0],2:operation['world_xy_raw'][1],
                0xa:0x8000,0xe:asset['texture'],0x10:proto[2]<<3,0x12:proto[3],
                0x16:word(proto,4),0x18:asset_id,0x1a:opts[2],0x24:opts[3],0x28:rid}
        for offset,value in values.items():put(raw,offset,value)
        struct.pack_into('>III',raw,0x30,images[0],asset['images'],asset['animation'])
        objects.append(raw);programs.append(ObjectProgram(sequence,images))
    if len(objects)!=8:raise ValueError('Incomplete landing population')
    return objects,programs


def step_object(raw,program):
    raw=bytearray(raw);seq=program.sequence;cursor=word(raw,0x1c);timer=word(raw,0x1e)
    if len(raw)!=60 or cursor%3 or cursor>=len(seq)-1 or timer>seq[cursor]:
        raise ValueError('Invalid landing object animation state')
    if timer>=seq[cursor]:
        timer=0;cursor+=3;put(raw,0xa,word(raw,0xa)|0x80)
    timer+=1
    if not seq[cursor]:cursor=0;put(raw,0xa,word(raw,0xa)|0x100)
    duration,image,flags=seq[cursor:cursor+3]
    if flags:raise ValueError('Unverified landing object side effect')
    for offset,value in ((0x1c,cursor),(0x1e,timer),(0x20,duration),(0x22,image)):
        put(raw,offset,value)
    struct.pack_into('>I',raw,0x30,program.images[image])
    return raw


class LandingActorProfile:
    def __init__(self,resources,asset):
        self.resources=resources;self.asset=asset
        self.seq=resources.sequence(asset['animation'],0)
        if self.seq!=bytes.fromhex('01030400'):raise ValueError('Unknown arrival actor pose')

    def read_record(self,animation,cursor):
        if animation!=0 or cursor not in (0,3):raise ValueError('Unverified landing actor animation')
        return tuple(self.seq[:3]) if cursor==0 else (0,0,0)

    def image_pointer(self,image):
        if image!=3:raise ValueError('Unverified landing actor image')
        return self.resources.pointer(self.asset['images']+4*image)


def initialize_actor(resources):
    operation=next(r for r in resources.operations if r['action']=='spawn_scene_actor')
    rid=operation['resource_id'];proto,asset_id,asset=resources.prototype(rid)
    if proto!=bytes.fromhex('00000208001212260e4513') or operation['options']!=[0,0,1]:
        raise ValueError('Unverified landing actor initializer')
    profile=LandingActorProfile(resources,asset)
    raw=bytearray(112)
    values={0:operation['world_xy_raw'][0],2:operation['world_xy_raw'][1],6:0x8000,
            0xe:asset['texture'],0x10:proto[2]<<3,0x12:proto[3],0x16:word(proto,4),
            0x22:asset_id,0x28:proto[6]&15,0x2a:operation['options'][2],
            0x3a:rid,0x3e:256,0x40:256}
    for offset,value in values.items():put(raw,offset,value)
    raw[0x44]=1;raw[0x45:0x47]=b'\xff\xff';raw[0x49]=1
    struct.pack_into('>I',raw,0x58,asset['images']);struct.pack_into('>I',raw,0x60,asset['animation'])
    raw[0x64:0x6c]=b'\xff'*8
    decode(raw,profile,False)
    return raw,profile
