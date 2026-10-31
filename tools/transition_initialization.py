"""Source arithmetic for the bounded scene 8 -> 7 initialization.

Operands are read from the pinned original program, never from arrival RAM.
This component alone does not certify the complete PC transition.
"""
from dataclasses import dataclass
import struct

import event_actor_reference as actor
import room_camera
from transition_source import destination, initialization, sources


def initialize_player(high, low, profile):
    """060A99E4 + 06094728 slot zero, followed by C20C/C34A decode."""
    if len(high) != 0x100000 or len(low) != 0x100000:
        raise ValueError('Truncated original initialization resources')
    twn, source = sources()
    landing = destination(twn, source)
    resource = int.from_bytes(high[0x36680:0x36682], 'big')
    header = 0xb5e70 + resource*8
    root, palette, texture = struct.unpack_from('>IHH', high, header)
    if resource != 0 or root != 0x20220000 or palette or texture:
        raise ValueError('Unverified party resource for landing')
    pointers = struct.unpack_from('>4I', low, root-0x20200000)
    if pointers != (0x20220498, 0x20220010, 0x20220158, 0x20220350):
        raise ValueError('Changed player resource header')
    # Slot zero is cleared by base initialization; +5C is then overwritten
    # by the source image-table lookup. No old pose or speed survives.
    raw = bytearray(112)
    for offset, value in {0:landing['spawn_raw'][0],2:landing['spawn_raw'][1],
                          6:0x8000,8:9,0xe:texture,0x10:0x10,0x12:palette,
                          0x16:0x12,0x24:1,0x26:landing['heading']&7,
                          0x28:1,0x32:4,0x3a:resource,0x3e:256,0x40:256}.items():
        actor.put(raw,offset,value)
    raw[0x45:0x47] = b'\xff\xff'
    raw[0x49] = 1
    for offset, value in zip((0x68,0x60,0x58,0x64),pointers):
        struct.pack_into('>I',raw,offset,value)
    actor.decode(raw,profile,False)
    return raw


@dataclass(frozen=True)
class LandingCameraProfile:
    limits: tuple[int,int,int,int]
    speed_limit: int = 128

    def __post_init__(self):
        if self.limits != (0x2000,0x7000,0x2800,0x7200) or self.speed_limit != 128:
            raise ValueError('Unverified landing camera profile')


def camera_profile(story):
    twn,source=sources()
    operations=initialization(source,twn,story)
    values=next(row['limits_raw'] for row in operations if row['action']=='set_camera_limits')
    return LandingCameraProfile(tuple(values))


def initialize_camera(xy, profile):
    """0609AEC4 centers at 128/96 pixels, then applies source limits."""
    if tuple(xy) != (0x3880,0x7780):
        raise ValueError('Unverified camera landing')
    x=max(profile.limits[0],min(profile.limits[2],xy[0]-0x800))
    y=max(profile.limits[1],min(profile.limits[3],xy[1]-0x600))
    return dict(x=x,y=y,display_x=-1,display_y=-1,dx=0,dy=0,offset_x=0,offset_y=0)


def camera_step(state, xy, profile):
    # Reuse verified arithmetic, with a separate strict landing profile. Old
    # room validators and their permitted limits are not broadened.
    return room_camera.step(state,tuple(xy),profile)


def fade_step(phase, rgb):
    """06092A18 source tick. Completion tests happen before +/-8/clamp."""
    if phase not in (0,1,2) or len(rgb)!=3 or any(type(v) is not int or not -255<=v<=0 for v in rgb):
        raise ValueError('Unverified fade state')
    if phase==0:
        return (2 if all(v==0 for v in rgb) else 0),tuple(min(0,v+8) for v in rgb)
    if phase==1:
        return (2 if all(v==-255 for v in rgb) else 1),tuple(max(-255,v-8) for v in rgb)
    # Only stable terminal waits are observed in this path. Intermediate
    # phase-2 colour recovery is a different source mode, deliberately rejected.
    if tuple(rgb) not in ((0,0,0),(-255,-255,-255)):
        raise ValueError('Unverified phase-2 colour recovery')
    return phase,tuple(rgb)
