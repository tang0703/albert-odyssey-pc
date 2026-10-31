"""Bounded resource-50 animation arithmetic for landing-event source research.

The old landing profile deliberately remains limited to its arrival pose.
TWN C034/C08C select four-direction tables when actor +08 bit 0 is clear.
"""
import probe_movement as movement
from event_actor_reference import word, put, decode


class Profile:
    def __init__(self, resources):
        self.resources = resources
        _, _, self.asset = resources.prototype(50)
        self.sequences = {i: resources.sequence(self.asset['animation'], i) for i in (0, 3, 4, 6, 7)}
        self.images = {image for seq in self.sequences.values() for image in seq[1:-1:3]}
        if resources.twn[0x2688c:0x26894] != bytes.fromhex('0004000500060007'):
            raise ValueError('NPC walking selector table changed')
        if resources.twn[0x268d4:0x268dc] != bytes.fromhex('0000000100020003'):
            raise ValueError('NPC pose selector table changed')

    def read_record(self, animation, cursor):
        seq = self.sequences.get(animation)
        if seq is None or type(cursor) is not int or cursor < 0 or cursor % 3 or cursor >= len(seq):
            raise ValueError('Unverified landing-event actor record')
        return (0, 0, 0) if seq[cursor] == 0 else tuple(seq[cursor:cursor+3])

    def image_pointer(self, image):
        if image not in self.images:
            raise ValueError('Unverified landing-event actor image')
        return self.resources.pointer(self.asset['images']+4*image)


def check(raw):
    if len(raw) != 112 or word(raw, 0x3a) != 50 or word(raw, 8)&1:
        raise ValueError('Unexpected landing-event actor class')


def pose(raw, heading, profile):
    check(raw)
    if heading not in (0, 6):
        raise ValueError('Unverified NPC pose')
    raw = bytearray(raw)
    for offset in (0x30, 0x2c, 0x18, 0x1a): put(raw, offset, 0)
    put(raw, 0x26, heading)
    put(raw, 0x36, heading//2)
    decode(raw, profile, False)
    return raw


def forced_step(raw, axis, target, profile):
    check(raw)
    if (axis, target) not in ((0, 0x2c00), (1, 0x7780), (0, 0x2360), (1, 0x7760), (0, 0x2680)):
        raise ValueError('Unverified NPC forced destination')
    raw = bytearray(raw)
    position = word(raw, axis*2)
    delta = movement.signed16(target-position)
    speed = movement.SPEED_COMPONENTS[word(raw, 0x24)][0]
    heading = (4 if axis == 0 else 6) if delta < 0 else (0 if axis == 0 else 2)
    amount = max(delta, -speed) if delta < 0 else min(delta, speed)
    put(raw, 0x26, heading)
    put(raw, 0x18, amount if axis == 0 else 0)
    put(raw, 0x1a, amount if axis == 1 else 0)
    put(raw, 0x36, 4+heading//2)
    decode(raw, profile, True)
    put(raw, axis*2, position+amount)
    done = word(raw, axis*2)&0xfff0 == target&0xfff0
    if done:
        put(raw, 6, word(raw, 6)&0xfeff)
        put(raw, 0x18+axis*2, 0)
    return raw, done
