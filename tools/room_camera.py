"""MAP001 camera arithmetic transcribed from TWN.BIN 0609B028..0609B290.

This module does not certify room coverage. Its source-bound comparison gate
must pass before any generated camera configuration is used by an entry point.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

TWN_SHA256 = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
CAMERA_PCS = frozenset((0x060915a0, 0x0609ae32, 0x0609b028, 0x0609b254, 0x060915a6))


def signed16(value: int) -> int:
    value &= 65535
    return value if value < 32768 else value - 65536


@dataclass(frozen=True)
class CameraProfile:
    speed_limit: int
    limits: tuple[int, int, int, int]
    actor_slot: int

    def __post_init__(self):
        if (type(self.speed_limit) is not int or type(self.actor_slot) is not int
                or type(self.limits) is not tuple or any(type(v) is not int for v in self.limits)
                or self.speed_limit != 128 or self.limits != (8192, 24576, 10240, 25088) or self.actor_slot != 0):
            raise ValueError('Unverified MAP001 camera parameters')

    def metadata(self) -> dict:
        return {'speed_limit_raw': self.speed_limit, 'limits_raw': list(self.limits),
                'actor_slot': self.actor_slot, 'deadzone_raw': [2176, 1408, 3200, 2432],
                'source_sha256': TWN_SHA256,
                'order': 'actor update; copy old camera to display fields; follow and clamp',
                'ranges': [[0x1580, 0x15ac], [0xae32, 0xaec4], [0xb028, 0xb2ac]]}


def profile_from_snapshot(high: bytes, twn: bytes) -> CameraProfile:
    if len(high) != 0x100000 or hashlib.sha256(twn).hexdigest() != TWN_SHA256:
        raise ValueError('Camera source identity or snapshot length differs')
    for start, end in ((0x1580, 0x15ac), (0xae32, 0xaec4), (0xb028, 0xb2ac)):
        if high[0x90000+start:0x90000+end] != twn[start:end]:
            raise ValueError('Runtime camera instructions differ from pinned source')
    values = struct.unpack_from('>hhhhhh', high, 0xc426c)
    return CameraProfile(values[0], tuple(values[1:5]), values[5])


def state_from_bytes(raw: bytes, base: int = 0) -> dict:
    if type(base) is not int or base < 0 or len(raw) < base + 0x20:
        raise ValueError('Truncated camera record')
    word = lambda offset: struct.unpack_from('>h', raw, base + offset)[0]
    return {name: word(offset) for name, offset in
            [('x', 0xa), ('y', 0xc), ('display_x', 0xe), ('display_y', 0x10),
             ('dx', 0x18), ('dy', 0x1a), ('offset_x', 0x1c), ('offset_y', 0x1e)]}


def step(state: dict, actor_xy: tuple[int, int], profile: CameraProfile) -> dict:
    if set(state) != {'x', 'y', 'display_x', 'display_y', 'dx', 'dy', 'offset_x', 'offset_y'}:
        raise ValueError('Camera state fields differ')
    if any(type(v) is not int or not -32768 <= v <= 32767 for v in state.values()):
        raise ValueError('Invalid camera raw word')
    if state['offset_x'] or state['offset_y']:
        raise ValueError('Camera displacement has not been verified')
    if len(actor_xy) != 2 or any(type(v) is not int or not -32768 <= v <= 32767 for v in actor_xy):
        raise ValueError('Invalid actor raw coordinates')
    result = dict(state)
    result.update(display_x=state['x'], display_y=state['y'], dx=0, dy=0)
    for axis, target, center, minimum, maximum in (
        ('x', actor_xy[0], 0xa80, profile.limits[0], profile.limits[2]),
        ('y', actor_xy[1], 0x780, profile.limits[1], profile.limits[3]),
    ):
        original = state[axis]
        upper, lower = signed16(original + center + 0x200), signed16(original + center - 0x200)
        if target > upper:
            delta = min(profile.speed_limit, signed16(target-upper))
            proposed = signed16(original + delta)
            if proposed > maximum:
                proposed, delta = maximum, 0
            result[axis], result['d'+axis] = proposed, delta
        if target < lower:
            delta = min(profile.speed_limit, signed16(lower-target))
            proposed = signed16(result[axis] - delta)
            if proposed < minimum:
                proposed, delta = minimum, 0
            result[axis], result['d'+axis] = proposed, -delta
    return result
