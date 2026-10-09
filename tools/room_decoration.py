"""Source-bound MAP001 decoration 6/7 animation, without rendering or time.

TWN 0609DDB4 dispatches timer DE2C, decode DE9C, image lookup E00A.
Only the two observed, stationary, unflipped, three-byte-record programs are
accepted. The full 60-byte object is retained for checkpoint comparisons.
"""
from __future__ import annotations
import hashlib
import struct
from dataclasses import dataclass

TWN_SHA = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
MAP_SHA = '8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9'
BASE = 0xca4c0
PCS = frozenset((0x060915ac, 0x0609ddb4, 0x0609e00a, 0x0609ddc4))

def word(raw: bytes, offset: int) -> int:
    return struct.unpack_from('>H', raw, offset)[0]

@dataclass(frozen=True)
class Program:
    slot: int
    sequence: bytes
    image_pointers: tuple[int, ...]
    initial: bytes

    def metadata(self) -> dict:
        return {'slot': self.slot, 'sequence_hex': self.sequence.hex(),
                'image_pointers': list(self.image_pointers), 'initial_hex': self.initial.hex()}

def profiles(high: bytes, twn: bytes, source_map: bytes) -> tuple[Program, ...]:
    if (len(high) != 0x100000 or hashlib.sha256(twn).hexdigest() != TWN_SHA
            or hashlib.sha256(source_map).hexdigest() != MAP_SHA):
        raise ValueError('Decoration source identity changed')
    for start,end in ((0x15a6,0x15b2),(0xdd3c,0xdf36),(0xe00a,0xe01c),(0x2625c,0x26268)):
        if high[0x90000+start:0x90000+end] != twn[start:end]:
            raise ValueError('Runtime decoration instructions changed')
    def bound(address: int, size: int) -> bytes:
        offset = address - 0x260e0000
        if offset < 0 or offset+8+size > len(source_map):
            raise ValueError('Decoration pointer outside source MAP')
        raw = high[0xe0000+offset:0xe0000+offset+size]
        if raw != source_map[offset+8:offset+8+size]:
            raise ValueError('Runtime decoration data differs from source')
        return raw
    out=[]
    for slot,address,length,selector in ((6,0x260e8a21,4,3),(7,0x260e8a25,94,4)):
        raw=high[BASE+(slot-6)*60:BASE+(slot-5)*60]
        if (word(raw,0x1a)!=1 or word(raw,0x24)!=selector or raw[4:10]!=bytes(6)
                or word(raw,0x14)!=0 or word(raw,0x16)!=0x23
                or struct.unpack_from('>I',raw,0x38)[0]!=0x260e8b50):
            raise ValueError('Unverified decoration branch')
        if struct.unpack('>I',bound(0x260e8b50+selector*4,4))[0]!=address:
            raise ValueError('Decoration sequence selection changed')
        seq=bound(address,length)
        if seq[-1]!=0 or any(seq[n+2]!=0 for n in range(0,len(seq)-1,3)):
            raise ValueError('Unverified decoration sequence opcode')
        root=struct.unpack_from('>I',raw,0x34)[0]
        pointers=struct.unpack('>127I',bound(root,127*4))
        out.append(Program(slot,seq,pointers,raw))
    return tuple(out)

def step(raw: bytes, program: Program, *, before_pointer: bool=False) -> bytes:
    if len(raw)!=60:
        raise ValueError('Truncated decoration state')
    cursor,timer=word(raw,0x1c),word(raw,0x1e)
    seq=program.sequence
    if cursor%3 or cursor>=len(seq)-1 or not 1<=timer<=seq[cursor]:
        raise ValueError('Invalid decoration cursor/timer')
    result=bytearray(raw)
    def put(offset,value): struct.pack_into('>H',result,offset,value)
    status=word(raw,0xa)
    if timer>=seq[cursor]:
        timer=0;cursor+=3;status|=0x80
    timer+=1
    if seq[cursor]==0:
        cursor=0;status|=0x100
    duration,image=seq[cursor:cursor+2]
    put(0xa,status);put(0x1c,cursor);put(0x1e,timer)
    put(0x20,duration);put(0x22,image)
    if not before_pointer:
        struct.pack_into('>I',result,0x30,program.image_pointers[image])
    return bytes(result)
