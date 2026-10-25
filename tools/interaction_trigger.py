"""Source-bound interaction point/rectangle consumer; not full event acceptance."""
import hashlib
import struct

MAP_SHA = '8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9'
TWN_SHA = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
RECORD_ADDRESS = 0x060cc55a
SCRIPT_POINTER = 0x260e2fac


def signed(value):
    return (value + 32768) % 65536 - 32768


def source_record(high, source, twn):
    if len(high) != 0x100000 or hashlib.sha256(source).hexdigest() != MAP_SHA or hashlib.sha256(twn).hexdigest() != TWN_SHA:
        raise ValueError('Changed interaction source')
    if high[0xc41f2:0xc41f4] != b'\x00\x01':
        raise ValueError('Unverified interaction record count')
    raw = high[0xcc55a:0xcc55a+13]
    if source[0x159f] != 2 or raw[:8] != source[0x15a0:0x15a8] or raw[8] != 2 or raw[9:13] != source[0x15a8:0x15ac]:
        raise ValueError('Source and loaded interaction record differ')
    if int.from_bytes(raw[9:13], 'big') != SCRIPT_POINTER:
        raise ValueError('Interaction script differs')
    if high[0xac688:0xac828] != twn[0x1c688:0x1c828]:
        raise ValueError('Interaction consumer differs from source')
    return {'bounds': list(struct.unpack('>4h', raw[:8])), 'kind': 2,
            'script_pointer': SCRIPT_POINTER, 'script_offset': 0x2fb4,
            'source_offset': 0x159f, 'runtime_address': RECORD_ADDRESS,
            'source_sha256': MAP_SHA,
            'consumer_sha256': hashlib.sha256(twn[0x1c688:0x1c828]).hexdigest()}


def point(x, y, heading, shape):
    if heading not in (0, 2, 4, 6) or len(shape) != 5:
        raise ValueError('Only verified cardinal interaction points supported')
    left, top, _, width, height = shape
    if heading == 0: x += left + width + 32
    elif heading == 2: y += top + height + 32
    elif heading == 4: x += left - 32
    else: y += top - 32
    return signed(x), signed(y)


def hit(record, position):
    left, top, right, bottom = record['bounds']
    x, y = position
    return left <= x <= right and top <= y <= bottom


def requested(record, player, shape, pressed, disabled):
    if type(pressed) is not int or not 0 <= pressed <= 0xffff:
        raise ValueError('Invalid pressed word')
    if disabled == 255 or not pressed & 0x0600:
        return False
    x, y = struct.unpack_from('>hh', player)
    heading = int.from_bytes(player[0x26:0x28], 'big')
    return hit(record, point(x, y, heading, shape))
