"""Source-bound animation state for controlled MAP001 actor 0x060C8758.

This models raw animation selection, phase, image index and mirror bits. It
does not identify the character by name or decode/render an image descriptor.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

import exploration_movement as movement

SCHEMA = 'ao_pc_character_animation_model_v1'
ACTOR_ADDRESS = 0x060c8758
ANIMATION_ROOT = 0x20220010
IMAGE_TABLE_ROOT = 0x20220158
ANIMATION_BANK_SHA256 = 'ed78a1ab97ce9f799c3ae52c1b87920027b6ae15f893d26ec65511c534858d46'
IMAGE_TABLE_SHA256 = '308a402aaa5b8c848569c7c29010a2790f7230be16c7f64f3bc21c36eafd12f0'
CODE_RANGES = (
    (0x1c0b6,0x1c10a,'45b95eb4242c9b38f7c1ffedf1cf333c73cb270c890c42b9b932117714dea97a'),
    (0x1c20c,0x1c2aa,'57d18d5609a29bdb8a011485c20b96cf3f9f4662e3383ae3543e0351c4fe3c1d'),
    (0x1c346,0x1c360,'1ae720ecb293f7e88cad227bafc3ec4fb6725715ba6da49d2c9c494524040374'),
    (0x1ae20,0x1af74,'f0f579cc93d30f64091196c0f966a95d195ad4e6e819c741ee85e1095a54b0bd'),
    (0x268ac,0x268bc,'a9cc43c295192add1af80a40c98eee57f915f01cc68eef459c14e18dae61d94b'),
)
EXTRA_FIELDS = {
    'render_flags_word':(0x14,2), 'animation_cursor':(0x2c,2),
    'animation_timer':(0x30,2), 'animation_duration':(0x32,2), 'image_index':(0x34,2),
    'image_table_root':(0x58,4), 'image_pointer':(0x5c,4), 'animation_root':(0x60,4),
}
FIELDS = {**movement.FIELDS, **EXTRA_FIELDS}
ANIMATION_COMPARISON_FIELDS = {key:FIELDS[key] for key in (
    'status_word','flags_word','heading','animation_index',*EXTRA_FIELDS)}


def state_from_actor(actor: bytes) -> dict:
    if len(actor) != 112:
        raise ValueError('Expected complete 112-byte controlled actor')
    return {key:int.from_bytes(actor[offset:offset+size],'big') for key,(offset,size) in FIELDS.items()}


def movement_state(state: dict) -> dict:
    return {key:state[key] for key in movement.FIELDS}


def actor_from_state(state: dict) -> bytes:
    if set(state) != set(FIELDS):
        raise ValueError('Character state fields differ from versioned contract')
    actor = bytearray(movement.actor_from_state(movement_state(state)))
    for key,(offset,size) in EXTRA_FIELDS.items():
        value = state[key]
        if type(value) is not int or not 0 <= value < 1 << (size*8):
            raise ValueError(f'Invalid raw animation field: {key}')
        actor[offset:offset+size] = value.to_bytes(size,'big')
    if state['animation_root'] != ANIMATION_ROOT or state['image_table_root'] != IMAGE_TABLE_ROOT:
        raise ValueError('Unsupported animation or image-pointer root')
    if (state['heading'] not in (0,2,4,6) or state['animation_index'] not in (0,2,4,6,8,10,12,14) or
            state['animation_cursor'] not in (0,3,6,9) or state['animation_timer'] > 9 or
            state['animation_duration'] not in (1,10) or state['image_index'] > 20):
        raise ValueError('Unsupported cardinal-animation state')
    return bytes(actor)


@dataclass(frozen=True)
class CharacterProfile:
    movement_profile: movement.MovementProfile
    animation_bank: bytes
    image_table: bytes
    initial_state: dict

    def __post_init__(self):
        if (len(self.animation_bank) != 0x148 or hashlib.sha256(self.animation_bank).hexdigest() != ANIMATION_BANK_SHA256 or
                len(self.image_table) != 160 or hashlib.sha256(self.image_table).hexdigest() != IMAGE_TABLE_SHA256):
            raise ValueError('Animation records or image-pointer table changed')
        actor_from_state(self.initial_state)
        if movement_state(self.initial_state) != self.movement_profile.initial_state:
            raise ValueError('Animation and movement initial states differ')
        self.validate_state(self.initial_state)

    def read_record(self, animation: int, cursor: int) -> tuple[int,int,int]:
        if not 0 <= animation < 16 or cursor not in ((0,3) if animation < 8 else (0,3,6,9,12)):
            raise ValueError('Unsupported animation record access')
        pointer = int.from_bytes(self.animation_bank[animation*4:animation*4+4],'big')
        offset = pointer - ANIMATION_ROOT + cursor
        if not 0 <= offset < len(self.animation_bank):
            raise ValueError('Animation record outside pinned bank')
        duration = self.animation_bank[offset]
        if duration == 0:
            return 0,0,0
        if offset+3 > len(self.animation_bank):
            raise ValueError('Animation record truncated')
        image,flags = self.animation_bank[offset+1:offset+3]
        if flags not in (0,4):
            raise ValueError('Unsupported animation side effect')
        return duration,image,flags

    def image_pointer(self, image: int) -> int:
        if type(image) is not int or not 0 <= image < 40:
            raise ValueError('Image index outside pinned pointer table')
        return int.from_bytes(self.image_table[image*4:image*4+4],'big')

    def validate_state(self, state: dict) -> None:
        actor_from_state(state)
        selected = state['heading'] + (8 if state['status_word']&2 else 0)
        if state['animation_index'] != selected:
            raise ValueError('Animation selection differs from heading and moving state')
        duration,image,flags = self.read_record(state['animation_index'],state['animation_cursor'])
        if (duration != state['animation_duration'] or image != state['image_index'] or
                bool(flags&4) != bool(state['render_flags_word']&1) or
                self.image_pointer(image) != state['image_pointer']):
            raise ValueError('Animation state cache does not match its source record')

    def metadata(self) -> dict:
        return {'schema':SCHEMA,'actor_address':ACTOR_ADDRESS,'animation_root':ANIMATION_ROOT,
            'image_table_root':IMAGE_TABLE_ROOT,'initial_state':dict(self.initial_state),
            'animation_bank_sha256':ANIMATION_BANK_SHA256,'image_table_sha256':IMAGE_TABLE_SHA256,
            'active_records_sha256':movement.ANIMATION_ROOT_SHA256,'source_code_sha256':movement.p.TWN_HASH,
            'comparison_fields':{key:{'offset':offset,'bytes':size,'mask':(1<<(size*8))-1}
                for key,(offset,size) in ANIMATION_COMPARISON_FIELDS.items()},
            'code_ranges':[{'offset':start,'end_exclusive':end,'sha256':sha} for start,end,sha in CODE_RANGES],
            'logical_tick_seconds':{'numerator':176473,'denominator':10546875},
            'supported_headings':[0,2,4,6],'hd_interpolation':'Not part of original animation state model'}


def profile_from_snapshot(high: bytes, low: bytes, verified_query_indices=None) -> CharacterProfile:
    base = movement.profile_from_snapshot(high,low,verified_query_indices)
    source = (movement.p.WORKSPACE/'work/extract/TWN.BIN').read_bytes()
    for start,end,expected in CODE_RANGES:
        if (hashlib.sha256(source[start:end]).hexdigest() != expected or
                high[0x90000+start:0x90000+end] != source[start:end]):
            raise ValueError('Original animation code changed')
    actor = high[0xc8758:0xc87c8]
    return CharacterProfile(base,bytes(low[0x20010:0x20158]),bytes(low[0x20158:0x201f8]),state_from_actor(actor))


def step_game_input(state: dict, pad_word: int, profile: CharacterProfile) -> tuple[dict,dict]:
    """One continuous original update; never accepts an observed later state.

    The old cached duration controls advancement even after a new direction or
    idle action has been selected. Only idle selection resets the cursor, not
    the timer. The source record is decoded after the timer decision.
    """
    profile.validate_state(state)
    next_movement, movement_diagnostics = movement.step_game_input(movement_state(state),pad_word,profile.movement_profile)
    if not movement_diagnostics['applied']:
        return dict(state),{'applied':False,'reason':'test_boundary','movement':movement_diagnostics}
    actor,_ = movement.p.replay_input_gate(actor_from_state(state),pad_word,3,0)
    actor = bytearray(actor)
    word = lambda offset:int.from_bytes(actor[offset:offset+2],'big')
    def put(offset,value):
        struct.pack_into('>H',actor,offset,value&65535)
    if word(6)&2:
        actor = bytearray(movement.p.replay_velocity(actor))
    else:
        put(0x2c,0)
        put(0x36,word(0x26))
    put(0x18,word(0x18)+word(0x1e))
    put(0x1a,word(0x1a)+word(0x20))
    put(0x1e,0); put(0x20,0)
    checkpoints = {'before_timer':state_from_actor(actor)}
    timer = (word(0x30)+1)&65535
    put(0x30,timer)
    advanced = timer >= word(0x32)
    if advanced:
        put(0x30,0)
        _,_,old_flags = profile.read_record(word(0x36),word(0x2c))
        if old_flags&0x80:
            raise ValueError('Motion records are not supported by this profile')
        put(0x2c,word(0x2c)+3)
        put(6,word(6)|0x80)
    checkpoints['before_decode'] = state_from_actor(actor)
    duration,image,flags = profile.read_record(word(0x36),word(0x2c))
    wrapped = duration == 0
    if wrapped:
        put(0x2c,0)
        put(6,word(6)|0x100)
        duration,image,flags = profile.read_record(word(0x36),0)
    put(0x32,duration)
    put(0x34,image)
    put(0x14,(word(0x14)&~1)|(1 if flags&4 else 0))
    checkpoints['before_image_pointer'] = state_from_actor(actor)
    struct.pack_into('>I',actor,0x5c,profile.image_pointer(image))
    checkpoints['before_collision'] = state_from_actor(actor)
    result = state_from_actor(actor)
    animation_status = result['status_word']&0x180
    result.update(next_movement)
    result['status_word'] |= animation_status
    profile.validate_state(result)
    return result,{'applied':True,'advanced':advanced,'wrapped':wrapped,'mirror_x':bool(result['render_flags_word']&1),
        'image_index':image,'image_pointer':result['image_pointer'],'checkpoints':checkpoints,'movement':movement_diagnostics}


def step(state: dict, direction: str, profile: CharacterProfile) -> tuple[dict,dict]:
    if direction not in movement.PAD_WORDS:
        raise ValueError('Unknown cardinal direction')
    return step_game_input(state,movement.PAD_WORDS[direction],profile)
