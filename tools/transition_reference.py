"""Continuous scene transfer reference, independent of Nodes and wall time.

The original-room model remains strict and unchanged. The new controller owns
the transfer and accepts a named scene-resource completion, never later RAM.
"""
from event_actor_reference import word,decode,free_step
from equipment_sequence_reference import Model as OriginalRoom
from transition_initialization import initialize_player,initialize_camera,camera_profile,camera_step,fade_step
from transition_objects import Resources,initialize_objects,initialize_actor,step_object
from transition_source import destination,landing_contacts
import probe_movement
import event_camera_reference


class Model:
    def __init__(self,high,low,source,twn):
        self.seed=(bytes(high),bytes(low),bytes(source),bytes(twn))
        self.generation=0
        self.reset()

    def reset(self):
        self.generation+=1
        high,low,source,twn=self.seed
        self.room=OriginalRoom(high,low,source,twn)
        self.stage='original_room';self.fade=2;self.rgb=(0,0,0)
        self.scene=8;self.pending=None;self.requests=[];self.commands=[]
        self.objects=[];self.programs=[];self.arrival_actor=None;self.arrival_profile=None
        self.boundaries=landing_contacts(source)
        self.landing_queries=set();self.landing_updates=0;self.transition_updates=0
        self.boundary=None;self.destination=destination(twn,source)
        self.music_id=30
        self.presentation_generation=self.generation

    @property
    def player(self):return self.room.player

    @property
    def cameras(self):return self.room.cameras

    def equipment(self,action):
        if self.stage not in ('original_room','landing'):
            raise ValueError('Equipment disabled during scene transfer')
        return self.room.equipment(action)

    def _old_presentation(self):
        self.room.player,_=free_step(self.player,self.room.profile,self.room.flags,255)
        xy=tuple(probe_movement.signed16(word(self.player,i)) for i in (0,2))
        self.room.cameras=[event_camera_reference.step(c,xy,128,False) for c in self.cameras]

    def _landing_update(self,pad):
        self.room.player=bytearray(probe_movement.replay_input_gate(self.player,pad,self.fade,0)[0])
        self.room.player,diag=free_step(self.player,self.room.profile,self.room.flags,0)
        self.landing_queries.update(d['index'] for d in diag['lookups'])
        self.room.cameras=[camera_step(c,tuple(probe_movement.signed16(word(self.player,i)) for i in (0,2)),self.camera_rules) for c in self.cameras]
        decode(self.arrival_actor,self.arrival_profile,True)
        self.objects=[step_object(o,p) for o,p in zip(self.objects,self.programs)]
        self.landing_updates+=1

    def step(self,pad,signals=None,pressed=0,*,source_replay=False):
        if type(pad) is not int or not 0<=pad<=65535:raise ValueError('Invalid pad input')
        self.requests=[];self.commands=[]
        if self.stage=='original_room':
            if signals is None:raise ValueError('Original-room device replies required')
            self.room.step(pad,signals,pressed)
            self.commands=list(self.room.commands);self.requests=list(self.room.requests)
            if self.room.transition_pending:
                self.stage='fade_out';self.fade=1;self.room.disabled=255
                self.requests.append({'type':'transition_begin','generation':self.generation,'destination':7})
                # Contact dispatch occurs after the input gate, before actor
                # animation in the same source update.
                self._old_presentation();self.transition_updates+=1
            return
        if self.stage in ('loading','boundary'):return
        if self.stage=='fade_out':
            self.fade,self.rgb=fade_step(self.fade,self.rgb)
            if self.fade==2:
                self.stage='loading'
                self.pending={'generation':self.generation,'id':'map001_scene7_resources'}
                self.requests=[{'type':'load_scene',**self.pending}]
                return
            self.room.player=bytearray(probe_movement.replay_input_gate(self.player,pad,self.fade,255)[0])
            self._old_presentation();self.transition_updates+=1
            return
        if self.stage=='arrival_first_update':
            self.stage='fade_in'
            self._landing_update(pad)
            return
        if self.stage=='fade_in':
            self.fade,self.rgb=fade_step(self.fade,self.rgb)
            if self.fade==2:
                self.stage='landing'
                self.requests=[{'type':'control_restored','generation':self.generation}]
        elif self.stage!='landing':raise ValueError('Unknown transition phase')
        if self.stage=='landing':
            x,y=(word(self.player,i) for i in (0,2))
            hit=[b for b in self.boundaries if b['bounds_raw'][0]<=x<=b['bounds_raw'][2] and b['bounds_raw'][1]<=y<=b['bounds_raw'][3]]
            if hit:
                if source_replay:raise ValueError('Reference route entered an unimplemented landing event/exit')
                self.boundary=hit[0]['policy'];self.stage='boundary'
                self.requests=[{'type':'test_boundary','reason':self.boundary}]
                return
        self._landing_update(pad)

    def scene_resources_ready(self,generation,request_id):
        if type(generation) is not int or generation!=self.generation:return False
        if self.stage!='loading' or self.pending!={'generation':generation,'id':request_id}:return False
        high,low,source,twn=self.seed
        story=self.room.story+high[0x36939:0x369b8]
        resources=Resources(story)
        # This is a semantic initialization transaction; source CPU decompression
        # and VDP upload video waits are not fabricated logical actor ticks.
        self.room.player=initialize_player(high,low,self.room.profile)
        self.camera_rules=camera_profile(story)
        self.room.cameras=[initialize_camera(self.destination['spawn_raw'],self.camera_rules) for _ in range(2)]
        self.objects,self.programs=initialize_objects(resources)
        self.arrival_actor,self.arrival_profile=initialize_actor(resources)
        self.room.root=None;self.room.child=None;self.room.spark=None;self.room.spark_child=None
        self.room.effect=None;self.room.effect_xy=None;self.room.temp={}
        self.room.decor=bytearray(60);self.room.ambient=bytearray(60)
        self.room.fixed=False;self.room.target=None;self.room.speed=128;self.room.disabled=0
        self.room.transition_pending=False
        self.scene=7;self.fade=0;self.stage='arrival_first_update';self.pending=None
        self.commands=[dict(row) for row in resources.operations]
        self.requests=[{'type':'scene_initialized','generation':self.generation,'scene':7},
                       {'type':'retain_source_music','id':self.music_id}]
        return True
