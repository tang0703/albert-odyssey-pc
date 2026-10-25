"""Diagnostic Cirrus pickup scheduler under explicit resource/text acknowledgements.

Diagnostic source model, not a release gate. External inputs are input-pad and
resource/text-device readiness only; commands, actors and cameras are predicted.
No raw Saturn bytes are accepted from a runtime client.
"""
from dataclasses import dataclass
import struct
import event_actor_reference as actor
import event_camera_reference as camera
import event_effect_reference as effect
import event_decoration_reference as decoration
import character_animation
import room_decoration
import room_boundaries
import probe_movement
import interaction_trigger
import interaction_animation


@dataclass
class Slot:
    pc:int
    owner:str
    wait:int|None=None
    arg:int=0
    target:int=0
    active:bool=True


class Model:
    def __init__(self,high,low,source,twn):
        self.programs=effect.sequences(source)
        self.source=source
        self.profile=character_animation.profile_from_snapshot(high,low)
        self.high,self.low=bytes(high),bytes(low)
        self.profile=interaction_animation.Profile(high,low,self.profile)
        self.interaction=interaction_trigger.source_record(high,source,twn)
        self.spark=None;self.spark_profile=None;self.spark_child=None;self.temp={}
        self.item_count=high[0x367cf]
        if self.item_count!=0:raise ValueError('Unverified initial Cirrus item count')
        self.resource='IVENT041.AIF'
        self.player=bytearray(high[0xc8758:0xc87c8])
        self.flags=low[0x10000:0x20000]
        self.boundaries=room_boundaries.read_boundaries(high,source,twn)
        self.cameras=[camera.state_from_bytes(high,0xc4288+i*60) for i in range(2)]
        self.decor_profile,self.ambient_profile=room_decoration.profiles(high,twn,source)
        self.decor=bytearray(self.decor_profile.initial)
        self.ambient=bytearray(self.ambient_profile.initial)
        self.decor_sequence=decoration.program(source)
        # This branch reads bit 1 of this byte only. The larger observation
        # range also contains unrelated live counters (e.g. 0603699B).
        self.story=high[0x36938:0x36939]
        if self.story[0]!=1:raise ValueError('Unverified initial story branch')
        self.disabled=0;self.fixed=False;self.target=None;self.speed=128
        self.root=None;self.child=None;self.effect=None;self.effect_xy=None;self.update=0;self.runs=0
        self.commands=[];self.requests=[];self.checkpoints={};self.queries=set()

    def attach(self,offset,owner):
        if owner=='spark':
            if self.spark is None or (self.spark_child and self.spark_child.active):raise ValueError('Invalid spark attachment')
            self.spark_child=Slot(offset,owner)
            actor.put(self.spark,6,actor.word(self.spark,6)|4)
            actor.put(self.spark,0x38,2)
            return
        if self.child is not None and self.child.active:raise ValueError('Occupied child slot')
        self.child=Slot(offset,owner)
        if owner=='actor':
            actor.put(self.player,6,actor.word(self.player,6)|4)
            actor.put(self.player,0x38,1)
        elif owner=='decoration':
            actor.put(self.decor,10,actor.word(self.decor,10)|4);actor.put(self.decor,0x26,1)
        else:raise ValueError('Unknown attached owner')

    def wait(self,s,signals):
        if s.wait==4:
            raw,profile=(self.spark,self.spark_profile) if s.owner=='spark' else (self.player,self.profile)
            return interaction_animation.wait_step(raw,profile)
        if s.wait==0:
            old=s.arg;s.arg=(old-1)&65535;return old==0
        if s.wait in (1,2):
            self.player,done=actor.forced_step(self.player,s.wait-1,s.target,self.profile)
            return done
        if s.wait==8:return not signals['text_active']
        if s.wait==9:
            raw=self.player if s.target==0 else self.spark
            if raw is None:raise ValueError('Missing waited actor')
            return not actor.word(raw,6)&4
        if s.wait==11:
            done=not self.cameras[0]['dx'] and not self.cameras[0]['dy']
            if done and s.arg==2:self.fixed=False;self.speed=128
            return done
        if s.wait==15:
            if signals['resource_loaded']==1 or s.arg>300:return True
            s.arg+=1;return False
        if s.wait==16:
            actor.put(self.decor,6,0);actor.put(self.decor,8,0)
            self.decor,done=decoration.event_step(self.decor,self.decor_sequence,self.decor_profile.image_pointers)
            if done:
                actor.put(self.decor,10,actor.word(self.decor,10)&0xfeff);actor.put(self.decor,0x1a,0)
            return done
        if s.wait==19:return bool(signals['resource_playing'])
        if s.wait==23:
            self.effect=effect.step(self.effect,self.programs)
            return self.effect.ended
        raise ValueError(f'Unknown wait {s.wait}')

    def dispatch(self,s,signals):
        if s is None or not s.active:return
        if s.wait is not None:
            if self.wait(s,signals):s.wait=None
            return
        for _ in range(32):
            offset=s.pc
            lengths={0:2,1:3,2:2,6:3,7:3,9:13,0x1d:7,0x24:7,0x25:1,0x26:1,
                     0x28:3,0x29:2,0x2d:4,0x2e:3,0x3a:2,0x43:5,0x44:1,
                     0x45:1,0x46:7,0x47:3,0x4d:6,0x51:1,0x5d:4,
                     0x1f:3,0x30:3,0x37:3,0x4c:3,0x57:2,0x5f:2,0x60:5,0x61:2,
                     0x6b:4,0x6c:9,0x72:7,0x81:4}
            if not 0<=offset<len(self.source):raise ValueError('Event cursor outside source')
            op=self.source[offset]
            if op not in lengths:raise ValueError(f'Unknown opcode {op:02x} at {offset:04x}')
            length=lengths[op];data=self.source[offset+1:offset+length]
            if len(data)!=length-1:raise ValueError('Truncated event')
            s.pc+=length;self.commands.append((s.owner,offset,op))
            u16=lambda i=0:int.from_bytes(data[i:i+2],'big')
            pointer=lambda i=0:int.from_bytes(data[i:i+4],'big')-0x260e0000+8
            if op==0:
                if data!=b'\0':raise ValueError('Unknown termination mode')
                s.active=False
                if s.owner=='actor':actor.put(self.player,6,actor.word(self.player,6)&0xfffb)
                elif s.owner=='spark':
                    actor.put(self.spark,6,actor.word(self.spark,6)&0xfffb)
                    actor.put(self.spark,0x2a,2)
                elif s.owner=='decoration':actor.put(self.decor,10,actor.word(self.decor,10)&0xfffb)
                return
            if op==9:
                bit={0x2f22:1,0x2f2f:2,0x2fb4:1}.get(offset)
                if bit is None or data[8:]!=bytes((2,0,bit,0)) or self.story[0] not in (1,3):
                    raise ValueError('Unverified story condition')
                s.pc=pointer(4 if self.story[0]&(1<<bit) else 0)
            elif op==0x37:
                if u16()!=1 or self.story!=b'\x01':raise ValueError('Unverified story mutation')
                self.story=b'\x03'
            elif op==0x4c:
                if u16() not in (0x30,0x31):raise ValueError('Unverified hidden decoration')
                actor.put(self.decor if u16()==0x30 else self.ambient,10,0)
            elif op==0x57:
                if data!=b'\x1b' or self.item_count:raise ValueError('Unverified item grant')
                self.item_count+=1
            elif op==0x5f:
                if data[0] not in (18,19):raise ValueError('Unverified actor mode')
                actor.put(self.player,0x16,(actor.word(self.player,0x16)&0xff00)|data[0])
            elif op==0x60:
                if data!=bytes.fromhex('fff06a70'):raise ValueError('Unverified pickup position')
                actor.put(self.player,2,u16(2))
            elif op==0x61:
                if data[0] not in (0,255):raise ValueError('Unverified player palette selector')
                actor.put(self.player,0x12,data[0])
            elif op==0x81:
                if u16()!=0 or data[2] not in (0,1):raise ValueError('Unverified actor input state')
                self.player[0x49]=data[2]
            elif op==0x1f:
                raw,profile=(self.spark,self.spark_profile) if s.owner=='spark' else (self.player,self.profile)
                interaction_animation.select(raw,profile,u16());s.wait=4
            elif op==0x6b:
                if data!=bytes.fromhex('070000'):raise ValueError('Unverified coordinate source')
                self.temp[7]=[actor.word(self.player,i) for i in (0,2,4)]
            elif op==0x6c:
                if data!=bytes.fromhex('0007ffa000a00000') or 7 not in self.temp:raise ValueError('Unverified coordinate offset')
                self.temp[7]=[(v+u16(2+i*2))&65535 for i,v in enumerate(self.temp[7])]
            elif op==0x72:
                if data!=bytes.fromhex('003107000001'):raise ValueError('Unverified spawn')
                self.spark,self.spark_profile=interaction_animation.spawn_spark(self.high,self.low,self.profile.base,self.temp[7][:2])
                self.effect=None;self.effect_xy=None
            elif op==0x30:
                if u16()!=49 or self.spark is None:raise ValueError('Unverified actor removal')
                actor.put(self.spark,6,0)
            elif op==0x25:
                self.disabled=255;actor.put(self.player,0x2c,0);actor.put(self.player,0x36,actor.word(self.player,0x26))
            elif op==0x26:self.disabled=0
            elif op==0x1d:
                if u16() not in (0,49):raise ValueError('Unknown attached actor')
                self.attach(pointer(2),'actor' if u16()==0 else 'spark')
            elif op==0x2e:
                if u16() not in (0,49):raise ValueError('Unknown actor wait')
                target=self.player if u16()==0 else self.spark
                s.target=u16()
                if actor.word(target,6)&4:s.wait=9
            elif op==0x5d:
                if data!=bytes.fromhex('03001e'):raise ValueError('Unknown expression')
                self.spark=None
                self.effect=effect.Effect();s.wait=23
                self.effect_xy=tuple(actor.word(self.player,i) for i in (0,2))
            elif op==2:
                if data[0] not in (0,2,4):raise ValueError('Unknown pose')
                self.player=actor.pose(self.player,data[0],self.profile);s.wait=0;s.arg=1
            elif op==0x24:
                if data!=bytes.fromhex('26b060700010'):raise ValueError('Unknown camera target')
                self.target=(u16(),u16(2));self.speed=u16(4);self.fixed=True
            elif op==0x28:
                if data!=b'\0\0':raise ValueError('Unknown camera actor')
                self.fixed=False
            elif op==0x3a:
                if data[0] not in (0,2):raise ValueError('Unknown camera wait')
                s.wait=11;s.arg=data[0]
            elif op==0x43:
                resources={0xefd2:'IVENT041.AIF',0xefb8:'IVENT176.AIF'}
                if pointer() not in resources:raise ValueError('Unknown resource')
                self.resource=resources[pointer()]
                self.requests.append({'type':'load_original_resource','id':self.resource})
            elif op==0x44:s.wait=15;s.arg=0
            elif op==0x45:self.requests.append({'type':'play_original_resource','id':self.resource})
            elif op==0x51:s.wait=19
            elif op==0x46:
                if u16()!=0x30:raise ValueError('Unknown decoration')
                self.attach(pointer(2),'decoration')
            elif op==0x47:
                if u16()!=5:raise ValueError('Unknown decoration animation')
                actor.put(self.decor,0x24,5);actor.put(self.decor,0x1e,0);actor.put(self.decor,0x1c,0)
                actor.put(self.decor,0x20,8);actor.put(self.decor,0x22,46)
                actor.put(self.decor,0x14,actor.word(self.decor,0x14)&0xfffe)
                actor.put(self.decor,10,actor.word(self.decor,10)&0xfeff)
                struct.pack_into('>I',self.decor,0x30,self.decor_profile.image_pointers[46]);s.wait=16
            elif op==1:s.wait=0;s.arg=u16()
            elif op==0x4d:
                if data!=bytes.fromhex('ffffff0010'):raise ValueError('Unknown text layout')
                self.requests.append({'type':'source_text_layout','y':16})
            elif op==0x2d:
                ids={1:'map001_00afe2',2:'map001_00b061',3:'map001_00b0b5'}
                if data[:2]!=b'\0\0' or data[2] not in ids:raise ValueError('Unknown text request')
                self.requests.append({'type':'dialogue','id':ids[data[2]]});s.wait=8
            elif op==0x29:
                if data!=b'\1':raise ValueError('Unknown forced speed')
                actor.put(self.player,0x24,1)
            elif op in (6,7):
                axis=op-6;target=u16()
                if (axis,target) not in ((0,0x3320),(1,0x6940)):raise ValueError('Unknown forced destination')
                if actor.word(self.player,axis*2)&0xfff0!=target&0xfff0:
                    actor.put(self.player,0x2c,0);actor.put(self.player,0x30,0)
                    s.wait=axis+1;s.target=target
                    if self.wait(s,signals):s.wait=None
                    return
            if s.wait is not None:return
        raise ValueError('Event instruction budget exhausted')

    def step(self,pad,signals,pressed=0):
        if set(signals)!={'resource_loaded','resource_playing','text_active'}:raise ValueError('Incomplete device signals')
        self.update+=1;self.commands=[];self.requests=[]
        self.player=bytearray(probe_movement.replay_input_gate(self.player,pad,3,self.disabled)[0])
        hit=room_boundaries.contacts(self.boundaries,probe_movement.signed16(actor.word(self.player,0)),probe_movement.signed16(actor.word(self.player,2)))
        if 'stair_scene_boundary' in hit:raise ValueError('Scene transition is outside event scope')
        if not (self.root and self.root.active) and 'stair_script_boundary' in hit:
            self.root=Slot(0x2f22,'root');self.runs+=1
        elif not (self.root and self.root.active) and interaction_trigger.requested(
                self.interaction,self.player,probe_movement.APPROVED_SHAPES[actor.word(self.player,0x28)],pressed,self.disabled):
            self.root=Slot(0x2fb4,'root');self.runs+=1
        self.dispatch(self.root,signals)
        if actor.word(self.player,6)&4:self.dispatch(self.child,signals)
        else:
            self.player,diag=actor.free_step(self.player,self.profile,self.flags,self.disabled)
            self.queries.update(r['index'] for r in diag['lookups'])
        if self.spark is not None and actor.word(self.spark,6)&0x8000:
            if actor.word(self.spark,6)&4:self.dispatch(self.spark_child,signals)
            else:actor.decode(self.spark,self.spark_profile,False)
        xy=self.target if self.fixed else [probe_movement.signed16(actor.word(self.player,i)) for i in (0,2)]
        self.cameras=[camera.step(s,xy,self.speed,self.fixed) for s in self.cameras]
        if actor.word(self.decor,10)&4:self.dispatch(self.child,signals)
        elif actor.word(self.decor,10)&0x8000 and actor.word(self.decor,0x1a):self.decor=bytearray(room_decoration.step(self.decor,self.decor_profile))
        if actor.word(self.ambient,10)&0x8000:self.ambient=bytearray(room_decoration.step(self.ambient,self.ambient_profile))
        return self.commands
