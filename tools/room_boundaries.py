"""Source-bound test boundaries before MAP001 stair event/scene consumers.

The room workbench does not execute these events. Intersecting their source
rectangles rejects the entire proposed update and labels it a test boundary.
"""
import hashlib
import struct

MAP_SHA256 = '8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9'
TWN_SHA256 = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
RECORDS = ((0x1580, 0, 0x060cb55a), (0x1590, 2, 0x060cb57a))
RANGES = ((0x1c360, 0x1c4e8), (0x114de, 0x11526))


def read_boundaries(high: bytes, source: bytes, twn: bytes) -> list[dict]:
    if len(high) != 0x100000 or hashlib.sha256(source).hexdigest() != MAP_SHA256 or hashlib.sha256(twn).hexdigest() != TWN_SHA256:
        raise ValueError('Changed boundary source or incomplete snapshot')
    if struct.unpack_from('>h', high, 0xc41ee)[0] != 2:
        raise ValueError('Trigger count changed')
    for start, end in RANGES:
        if high[0x90000+start:0x90000+end] != twn[start:end]:
            raise ValueError('Runtime boundary consumer differs from source')
    records = []
    for offset, kind, address in RECORDS:
        runtime = high[address & 0xfffff:(address & 0xfffff)+32]
        if source[offset] != kind or runtime[:8] != source[offset+1:offset+9] or runtime[8] != kind:
            raise ValueError('Source boundary record differs from loaded record')
        bounds = list(struct.unpack_from('>hhhh', runtime))
        item = {'id': 'stair_scene_boundary' if kind == 0 else 'stair_script_boundary',
                'type': kind, 'raw_bounds_inclusive': bounds, 'source_offset': offset,
                'runtime_address': address, 'source_sha256': MAP_SHA256}
        if kind == 2:
            pointer = struct.unpack_from('>I', runtime, 9)[0]
            if runtime[9:13] != source[offset+9:offset+13] or pointer != 0x260e2f1a:
                raise ValueError('Stair event pointer changed')
            file_offset = pointer-0x260e0000+8
            if high[pointer & 0xfffff:(pointer & 0xfffff)+32] != source[file_offset:file_offset+32]:
                raise ValueError('Stair event source is not loaded at the observed pointer')
            item.update(event_pointer=pointer, event_file_offset=file_offset)
        records.append(item)
    return records


def contacts(records: list[dict], x_raw: int, y_raw: int) -> list[str]:
    if any(type(v) is not int or not -32768 <= v <= 32767 for v in (x_raw, y_raw)):
        raise ValueError('Invalid signed raw position')
    matches = []
    for item in records:
        left, top, right, bottom = item['raw_bounds_inclusive']
        if left > right or top > bottom:
            raise ValueError('Invalid source boundary rectangle')
        if left <= x_raw <= right and top <= y_raw <= bottom:
            matches.append(item['id'])
    return matches
