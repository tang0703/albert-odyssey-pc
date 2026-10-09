"""Source-bound MAP001 marker movement, independent of rendering and wall time.

Only the captured controlled actor and zero-displacement animation root are
accepted. Unknown regions reject a whole proposed update, not fake a contact.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

import probe_movement as p

SCHEMA = 'ao_pc_exploration_movement_v1'
ANIMATION_ROOT_SHA256 = 'e316125b1d085bdf18b62401bcf5b8fcb976f79827d2176a98c284ba30f9e99a'
FLAGS_SHA256 = '78863dedbf02a07158821486a059af56f31a0b18d11a9eee6a7986dd10943e5b'
PAD_WORDS = {'none': 0, 'up': 0x1000, 'down': 0x2000, 'left': 0x4000, 'right': 0x8000}
DISPATCH_RANGES = ((0x1580, 0x159e), (0x1a0de, 0x1a18c), (0x1ae20, 0x1b61a),
                   (0x1c0b6, 0x1c360), (0x2675c, 0x2678c))
FIELDS = {
    'x_word': (0, 2), 'y_word': (2, 2), 'status_word': (6, 2), 'flags_word': (8, 2),
    'selector_word': (0xa, 2), 'mode_word': (0x16, 2), 'dx_word': (0x18, 2), 'dy_word': (0x1a, 2),
    'slide_x_word': (0x1e, 2), 'slide_y_word': (0x20, 2), 'speed_index': (0x24, 2),
    'heading': (0x26, 2), 'shape_index': (0x29, 1), 'animation_index': (0x36, 2),
    'free_direction': (0x48, 1), 'center_flag': (0x4a, 1), 'contact_bits': (0x4b, 1),
}


def state_from_actor(actor: bytes) -> dict:
    if len(actor) != 0x70:
        raise ValueError('Expected a complete 112-byte actor record')
    return {key: int.from_bytes(actor[offset:offset+size], 'big') for key,(offset,size) in FIELDS.items()}


def actor_from_state(state: dict) -> bytes:
    if set(state) != set(FIELDS):
        raise ValueError('Movement state fields differ from versioned contract')
    actor = bytearray(0x70)
    for key,(offset,size) in FIELDS.items():
        value = state[key]
        if type(value) is not int or not 0 <= value < (1 << (size*8)):
            raise ValueError(f'Invalid raw field: {key}')
        actor[offset:offset+size] = value.to_bytes(size,'big')
    if state['shape_index'] != 1 or state['flags_word'] != 9 or state['heading'] >= 8 or state['speed_index'] != 3:
        raise ValueError('Unsupported controlled actor configuration')
    if state['status_word'] & ~(2 | 0x200) != 0x8180:
        raise ValueError('Unsupported actor dispatch/status mode')
    return bytes(actor)


@dataclass(frozen=True)
class MovementProfile:
    flags: bytes
    initial_state: dict
    animation_root_sha256: str
    verified_query_indices: frozenset[int] | None = None
    control_word: int = 3
    disabled_byte: int = 0
    actor_address: int = 0x060c8758

    def __post_init__(self):
        if len(self.flags) != 65536 or hashlib.sha256(self.flags).hexdigest() != FLAGS_SHA256:
            raise ValueError('Unsupported scene flags')
        if self.animation_root_sha256 != ANIMATION_ROOT_SHA256:
            raise ValueError('Unsupported animation root; motion side effects are not optional')
        if (self.control_word,self.disabled_byte,self.actor_address) != (3,0,0x060c8758):
            raise ValueError('Unsupported controlled slot or control gates')
        actor_from_state(self.initial_state)
        if self.verified_query_indices is not None and (not self.verified_query_indices or any(
                type(i) is not int or not 0 <= i < 65536 for i in self.verified_query_indices)):
            raise ValueError('Invalid verified flag-query domain')

    def metadata(self) -> dict:
        return {'schema':SCHEMA,'actor_address':self.actor_address,'control_word':self.control_word,
                'disabled_byte':self.disabled_byte,'initial_state':dict(self.initial_state),
                'flags_sha256':FLAGS_SHA256,'animation_root_sha256':self.animation_root_sha256,
                'source_hashes':{'TWN.BIN':p.TWN_HASH,'0':p.CORE_HASH},
                'shape_raw':list(p.APPROVED_SHAPES[1]),
                'verified_query_indices':None if self.verified_query_indices is None else sorted(self.verified_query_indices),
                'logical_tick_seconds':{'numerator':176473,'denominator':10546875},
                'comparison_fields':{k:{'offset':v[0],'bytes':v[1],'mask':(1<<(v[1]*8))-1} for k,v in FIELDS.items()}}


def profile_from_snapshot(high: bytes, low: bytes, verified_query_indices=None) -> MovementProfile:
    if len(high) != 0x100000 or len(low) != 0x100000:
        raise ValueError('Expected complete synchronous WRAM snapshots')
    twn=(p.WORKSPACE/'work/extract/TWN.BIN').read_bytes()
    core=(p.WORKSPACE/'work/extract/0').read_bytes()
    p.verify_code(twn,core)
    for start,end,_ in p.TWN_RANGES:
        if high[0x90000+start:0x90000+end] != twn[start:end]:
            raise ValueError(f'Runtime TWN source changed at {start:#x}')
    for start,end,_ in p.CORE_RANGES:
        if high[0x10000+start:0x10000+end] != core[start:end]:
            raise ValueError(f'Runtime compiler helper changed at {start:#x}')
    for start,end in DISPATCH_RANGES:
        if high[0x90000+start:0x90000+end] != twn[start:end]:
            raise ValueError('Runtime actor/input/animation dispatcher changed')
    slot=high[0xc27ae]
    actor=high[0xc8758+slot*0x70:0xc8758+(slot+1)*0x70]
    if slot != 0 or int.from_bytes(actor[0x2a:0x2c],'big') != 0 or int.from_bytes(actor[0xc:0xe],'big') & 0x8000:
        raise ValueError('Unsupported controlled actor dispatch')
    root=int.from_bytes(actor[0x60:0x64],'big')
    if root != 0x20220010:
        raise ValueError('Unsupported animation root pointer')
    table=low[0x20010:0x20050]
    chunks=[]
    for i in range(16):
        pointer=int.from_bytes(table[i*4:i*4+4],'big')
        if not 0x20220050 <= pointer < 0x20220158:
            raise ValueError('Animation pointer outside captured source record bank')
        start=cursor=pointer-0x20200000
        while cursor < 0x20158 and low[cursor]:
            if low[cursor+2] & 0x80:
                raise ValueError('Animation changes movement; profile not supported')
            cursor+=3
        if cursor >= 0x20158 or cursor-start > 255:
            raise ValueError('Animation record is unterminated')
        chunks.append(low[start:cursor+1])
    digest=hashlib.sha256(table+b''.join(chunks)).hexdigest()
    return MovementProfile(low[0x10000:0x20000],state_from_actor(actor),digest,
        None if verified_query_indices is None else frozenset(verified_query_indices),
        int.from_bytes(high[0xc27aa:0xc27ac],'big'),high[0xc41ec],0x060c8758+slot*0x70)


def step_game_input(state: dict, pad_word: int, profile: MovementProfile) -> tuple[dict,dict]:
    """One original game update. Captured game input is already transport-aligned.

    No observed per-frame actor bytes enter this function. The state rolls
    forward from its own previous result. Multi-key behavior belongs to the UI.
    """
    if type(pad_word) is not int or pad_word not in PAD_WORDS.values():
        raise ValueError('Only one cardinal direction or no input is supported')
    actor=actor_from_state(state)
    actor,_=p.replay_input_gate(actor,pad_word,profile.control_word,profile.disabled_byte)
    actor=bytearray(actor)
    word=lambda offset: int.from_bytes(actor[offset:offset+2],'big')
    if word(6)&2:
        actor=bytearray(p.replay_velocity(actor))
    else:
        struct.pack_into('>H',actor,0x36,word(0x26) if word(8)&1 else word(0x26)>>1)
    struct.pack_into('>HH',actor,0x18,(word(0x18)+word(0x1e))&65535,(word(0x1a)+word(0x20))&65535)
    struct.pack_into('>HH',actor,0x1e,0,0)
    updated,diagnostics=p.replay_step(actor,profile.flags,p.APPROVED_SHAPES)
    proposed=state_from_actor(updated)
    indices={item['index'] for item in diagnostics['lookups']}
    outside=sorted(indices-profile.verified_query_indices) if profile.verified_query_indices is not None else []
    if outside:
        return dict(state), {'applied':False,'reason':'test_boundary','unverified_query_indices':outside,
                             'lookups':diagnostics['lookups']}
    diagnostics.update({'applied':True,'reason':None,'game_pad_word':pad_word})
    return proposed,diagnostics


def step(state: dict, direction: str, profile: MovementProfile) -> tuple[dict,dict]:
    if direction not in PAD_WORDS:
        raise ValueError('Unknown direction')
    return step_game_input(state,PAD_WORDS[direction],profile)
