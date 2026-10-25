"""Bounded source animation readers for the Cirrus pickup, separate from walking.

Only the pinned player's 24/25 and spawned prototype 49 animation 2 are added.
No observed later actor record is accepted as a model state.
"""
import struct
from event_actor_reference import word, put


class Profile:
    def __init__(self, high, low, base, root=None, images=None):
        self.high, self.low, self.base = high, low, base
        self.root = root if root is not None else 0x20220010
        self.images = images if images is not None else 0x20220158

    def read(self, address, size):
        physical = address & 0x1fffffff
        if 0x06000000 <= physical and physical+size <= 0x06100000:
            return self.high[physical-0x06000000:physical-0x06000000+size]
        if 0x00200000 <= physical and physical+size <= 0x00300000:
            return self.low[physical-0x00200000:physical-0x00200000+size]
        raise ValueError('Animation address outside pinned initial memory')

    def read_record(self, animation, cursor):
        if self.root == 0x20220010 and animation < 16:
            return self.base.read_record(animation, cursor)
        if ((self.root == 0x20220010 and animation not in (24, 25)) or
                (self.root != 0x20220010 and (self.root != 0x260e8b50 or animation != 2)) or
                cursor < 0 or cursor > 192 or cursor % 3):
            raise ValueError('Unverified pickup animation')
        start = int.from_bytes(self.read(self.root+animation*4, 4), 'big')
        duration = self.read(start+cursor, 1)[0]
        if not duration:
            return 0, 0, 0
        raw = self.read(start+cursor, 3)
        if raw[2] not in (0, 4):
            raise ValueError('Unknown pickup animation side effect')
        return tuple(raw)

    def image_pointer(self, image):
        if self.root == 0x20220010:
            return self.base.image_pointer(image)
        if image == 127:
            return 0xffc00007
        if image not in (*range(32, 43), 44):
            raise ValueError('Unknown spark image')
        return int.from_bytes(self.read(self.images+image*4, 4), 'big')


def decode(raw, profile):
    duration, image, flags = profile.read_record(word(raw, 0x36), word(raw, 0x2c))
    if not duration:
        put(raw, 0x2c, 0)
        put(raw, 6, word(raw, 6)|0x100)
        return True
    put(raw, 0x32, duration)
    put(raw, 0x34, image)
    put(raw, 0x14, (word(raw, 0x14)&0xfffe) | bool(flags&4))
    struct.pack_into('>I', raw, 0x5c, profile.image_pointer(image))
    return False


def select(raw, profile, animation):
    put(raw, 0x36, animation)
    put(raw, 0x30, 0)
    put(raw, 0x2c, 0)
    put(raw, 6, word(raw, 6)&0xfeff)
    if decode(raw, profile):
        raise ValueError('Empty required animation')


def wait_step(raw, profile):
    put(raw, 0x30, word(raw, 0x30)+1)
    if word(raw, 0x30) >= word(raw, 0x32):
        put(raw, 0x30, 0)
        put(raw, 0x2c, word(raw, 0x2c)+3)
        put(raw, 6, word(raw, 6)|0x80)
    done = decode(raw, profile)
    if done:
        put(raw, 6, word(raw, 6)&0xfeff)
    return done


def spawn_spark(high, low, base, xy):
    """Source 72 -> A954C/A964A initializer for stable object 49 only."""
    profile = Profile(high, low, base, 0x260e8b50, 0x260e5748)
    prototype_root = int.from_bytes(high[0xc384c:0xc3850], 'big')
    prototype = profile.read(prototype_root+49*11, 11)
    if prototype != bytes.fromhex('000c000e002300260e487a'):
        raise ValueError('Spark prototype changed')
    asset = high[0xcd95c+12*16:0xcd95c+13*16]
    if asset != bytes.fromhex('0026009f06070606260e8b50260e5748'):
        raise ValueError('Spark asset references changed')
    # A99E4 writes these defaults. Stale image pointer is immediately decoded.
    raw = bytearray(112)
    # A99E4 intentionally preserves byte +44 of the first free actor slot.
    raw[0x44] = high[0xc87c8+0x44]
    for offset, value in {0:xy[0], 2:xy[1], 6:0x8000, 0xe:0x9f, 0x12:14,
                          0x16:0x23, 0x22:12, 0x2a:1, 0x3a:49, 0x3e:256, 0x40:256}.items():
        put(raw, offset, value)
    raw[0x45:0x47] = b'\xff\xff'
    struct.pack_into('>I', raw, 0x58, profile.images)
    struct.pack_into('>I', raw, 0x60, profile.root)
    raw[0x64:0x6c] = b'\xff'*8
    select(raw, profile, 2)
    return raw, profile
