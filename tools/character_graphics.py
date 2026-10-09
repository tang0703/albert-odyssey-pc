"""Source-bound MAP001 player graphics, not a screenshot crop or general rasterizer.

Character identity remains MAP001 player. A matching RAM command is only a
candidate until an independently pinned execution trace establishes consumption.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
PARTY_SHA256 = '1f34fb2ddfc726be55348241fe51703b28d752615c8405c18950d95add2e9dcb'
PARTY2_SHA256 = '3aa2f2a9bfd073f0719f0cae89ba9561193724c2b48e3b18e33b530f28ffa599'
MAP_SHA256 = '8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9'
TWN_SHA256 = 'fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6'
MAP_V1N_SHA256 = 'dcad16cc0fe4f843fbb3eba134adf264c66352ab590e4ace14381cd0b6fbf9a4'
RESOURCE_BASE = 0x20220000
RESOURCE_FILE_OFFSET = 12
RESOURCE_BYTES = 0x5b94
PALETTE_SOURCE_OFFSET = 0x652dc
PALETTE_CRAM_OFFSET = 0x800
# Full TWN identity binds these routines; reports also retain their exact slices.
ROUTINES = {'image_pointer': (0x1c34a, 0x1c360), 'texture_selection': (0x1af74, 0x1b04e),
            'lzss_decoder': (0x1ed8e, 0x1ee5c)}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def span(raw: bytes, start: int, length: int) -> bytes:
    if type(start) is not int or type(length) is not int or start < 0 or length <= 0 or start + length > len(raw):
        raise ValueError('Source span is truncated or out of bounds')
    return raw[start:start + length]


def word(raw: bytes, start: int) -> int:
    return int.from_bytes(span(raw, start, 2), 'big')


def longword(raw: bytes, start: int) -> int:
    return int.from_bytes(span(raw, start, 4), 'big')


def signed_word(value: int) -> int:
    return value - 65536 if value & 32768 else value


def divide16(value: int) -> int:
    return value // 16 if value >= 0 else -((-value) // 16)


def decompress_texture(source: bytes, output_bytes: int) -> tuple[bytes, int]:
    """TWN+1ED8E: LSB controls, distance=lo|((hi&F0)<<4), length=(hi&F)+3.

    The machine initializes only 0xFEE ring bytes. Reading the remaining bytes
    before writing them is rejected rather than inventing a zero-filled stack.
    The final copy may be clipped to the requested destination length, as DT R6
    exits the SH-2 routine immediately after writing that last byte.
    """
    if type(output_bytes) is not int or not 0 < output_bytes <= 0x80000:
        raise ValueError('Invalid decompression size')
    window = bytearray(4096)
    initialized = bytearray(b'\1' * 0xfee + b'\0' * 18)
    output = bytearray()
    cursor = position = 0
    while len(output) < output_bytes:
        control = span(source, position, 1)[0]
        position += 1
        for bit in range(8):
            if control & (1 << bit):
                literal = span(source, position, 1)[0]
                position += 1
                count, distance = 1, None
            else:
                lo, hi = span(source, position, 2)
                position += 2
                distance, count = lo | ((hi & 0xf0) << 4), (hi & 15) + 3
            for _ in range(count):
                if distance is None:
                    value = literal
                else:
                    address = (cursor - distance) & 4095
                    if not initialized[address]:
                        raise ValueError('Compressed stream reads uninitialized decoder stack')
                    value = window[address]
                output.append(value)
                window[cursor] = value
                initialized[cursor] = 1
                cursor = (cursor + 1) & 4095
                if len(output) == output_bytes:
                    break
            if len(output) == output_bytes:
                break
    return bytes(output), position


@dataclass(frozen=True)
class Texture:
    index: int
    width: int
    height: int
    source_offset: int
    compressed_bytes: int
    indices: bytes

    def metadata(self) -> dict:
        return {'texture_id': f'map001_player_texture_{self.index:02d}', 'index': self.index,
                'width': self.width, 'height': self.height, 'source_file': 'work/extract/PARTY0.PTY',
                'record_offset': self.source_offset, 'payload_offset': self.source_offset + 8,
                'compressed_bytes': self.compressed_bytes, 'decoded_bytes': len(self.indices),
                'decoded_sha256': sha(self.indices), 'color_mode': 2}


class PlayerResource:
    """The source-pinned first PARTY0 resource; all pointers are actual source data."""
    def __init__(self, party: bytes, map_source: bytes, twn: bytes):
        for data, expected, name in [(party, PARTY_SHA256, 'PARTY0.PTY'), (map_source, MAP_SHA256, 'MAP001.TWN'), (twn, TWN_SHA256, 'TWN.BIN')]:
            if sha(data) != expected:
                raise ValueError(f'Changed source: {name}')
        if longword(party, 8) != RESOURCE_BYTES:
            raise ValueError('Unsupported PARTY resource boundary')
        self.bank = span(party, RESOURCE_FILE_OFFSET, RESOURCE_BYTES)
        self.palette = span(map_source, PALETTE_SOURCE_OFFSET, 128)
        self.source_hashes = {'PARTY0.PTY': sha(party), 'MAP001.TWN': sha(map_source), 'TWN.BIN': sha(twn)}
        self.code_ranges = {name: {'offset': a, 'end': b, 'sha256': sha(span(twn, a, b - a))} for name, (a, b) in ROUTINES.items()}
        self.image_table = longword(self.bank, 8)
        self.texture_groups = longword(self.bank, 12)
        self.texture_table = longword(self.bank, 0)
        if (self.image_table, self.texture_groups, self.texture_table) != (0x20220158, 0x20220350, 0x20220498):
            raise ValueError('Unsupported player resource roots')
        self.textures: dict[int, Texture] = {}
        table = self.texture_table - RESOURCE_BASE
        table_bytes = longword(self.bank, table)
        if table_bytes != 43 * 4:
            raise ValueError('Texture index table size changed')
        offsets = [longword(self.bank, table + i * 4) for i in range(43)]
        if offsets != sorted(set(offsets)):
            raise ValueError('Texture record offsets overlap or repeat')
        for index, relative in enumerate(offsets):
            start = table + relative
            end = table + offsets[index + 1] if index + 1 < len(offsets) else len(self.bank)
            raw = span(self.bank, start, end - start)
            tag, record_id, attributes, size = struct.unpack('>4H', span(raw, 0, 8))
            if tag != 0x16 or record_id != index or attributes != 0 or size & 0xc000:
                raise ValueError('Unsupported player texture header')
            width, height = ((size >> 8) & 63) * 8, size & 255
            if width <= 0 or height <= 0:
                raise ValueError('Empty texture')
            decoded, consumed = decompress_texture(raw[8:], width * height)
            if any(value > 63 for value in decoded):
                raise ValueError('Texture uses codes outside the source 64-color bank')
            # The source-pinned final record ends with five zero bank-tail
            # bytes; ordinary records have at most three alignment bytes.
            padding = raw[8 + consumed:]
            allowed_padding = (b'', b'\0', b'\0\0', b'\0\0\0')
            if index == 42:
                allowed_padding += (b'\0' * 5,)
            if padding not in allowed_padding:
                raise ValueError('Unexpected trailing compressed record data')
            self.textures[index] = Texture(index, width, height, RESOURCE_FILE_OFFSET + start, consumed, decoded)

    def at_pointer(self, pointer: int, size: int) -> bytes:
        return span(self.bank, pointer - RESOURCE_BASE, size)

    def image(self, index: int) -> dict:
        if type(index) is not int or not 0 <= index < 40:
            raise ValueError('Image index outside source table')
        pointer = int.from_bytes(self.at_pointer(self.image_table + index * 4, 4), 'big')
        group = int.from_bytes(self.at_pointer(self.texture_groups + index * 4, 4), 'big')
        count = int.from_bytes(self.at_pointer(pointer, 2), 'big')
        texture_count = int.from_bytes(self.at_pointer(group, 2), 'big')
        if count not in (1, 2) or count != texture_count:
            raise ValueError('Image pieces do not agree with texture selection group')
        pieces = []
        for slot in range(count):
            x, y, attributes = struct.unpack('>hhH', self.at_pointer(pointer + 2 + slot * 6, 6))
            texture_id = int.from_bytes(self.at_pointer(group + 2 + slot * 2, 2), 'big')
            if texture_id not in self.textures:
                raise ValueError('Image references invalid texture')
            pieces.append({'slot': slot, 'offset': [x, y], 'attributes': attributes,
                           'texture_index': texture_id, 'record_address': pointer + 2 + slot * 6})
        return {'image_index': index, 'record_address': pointer, 'texture_group_address': group, 'pieces': pieces}

    def bind_actor(self, actor: bytes, low_ram: bytes) -> dict:
        if len(actor) != 112 or len(low_ram) != 0x100000:
            raise ValueError('Actor or low RAM is incomplete')
        if span(low_ram, 0x20000, RESOURCE_BYTES) != self.bank:
            raise ValueError('Runtime player resource differs from original source')
        if tuple(longword(actor, offset) for offset in (0x58, 0x64, 0x68)) != (self.image_table, self.texture_groups, self.texture_table):
            raise ValueError('Actor resource roots do not identify the source bank')
        image = self.image(word(actor, 0x34))
        if longword(actor, 0x5c) != image['record_address']:
            raise ValueError('Actor image pointer is stale or differs from current image index')
        return image


def rgba_texture(texture: Texture, cram: bytes, regs1: dict, regs2: dict, colr: int, pmod: int) -> Image.Image:
    """Intrinsic source texture in this capture's proven Ymir palette convention."""
    if len(cram) != 4096 or regs1.get('TVMR') != 0 or (regs2.get('RAMCTL', -1) >> 12) & 3 != 1 or regs2.get('SPCTL', -1) & 15 != 6:
        raise ValueError('Unsupported VDP1/CRAM/sprite mode')
    if ((pmod >> 3) & 7) != 2 or not pmod & 0x80 or pmod & (0x8000 | 0x100 | 7):
        raise ValueError('Unsupported color calculation, mesh, end codes or pixel mode')
    bank = colr & 0xffc0
    if bank & 0x8000:
        raise ValueError('RGB/shadow window bank is unsupported')
    base = ((regs2['CRAOFB'] >> 4) & 7) * 256
    which = 'B' if regs2['CLOFSL'] & 64 else 'A'
    offsets = [regs2[f'CO{which}{c}'] & 511 for c in 'RGB'] if regs2['CLOFEN'] & 64 else [0] * 3
    offsets = [n - 512 if n & 256 else n for n in offsets]
    pixels = []
    for value in texture.indices:
        if value == 0 and not pmod & 64:
            pixels.append((0, 0, 0, 0))
            continue
        code = (bank | value) & 1023
        if code in (0, 1022):
            raise ValueError('Special transparent/shadow code requires composition')
        color = word(cram, ((base + code) * 2) & 0xffe)
        # Ymir vdp_common_defs.hpp ConvertRGB555to888 shifts only, no bit replication.
        pixels.append(tuple(max(0, min(255, (((color >> shift) & 31) << 3) + offset)) for shift, offset in zip((0, 5, 10), offsets)) + (255,))
    result = Image.new('RGBA', (texture.width, texture.height))
    result.putdata(pixels)
    return result


def bind_command(piece: dict, texture: Texture, actor: bytes, camera: tuple[int, int], rows: list[dict], vram: bytes) -> dict:
    """Bind exact pixels plus source anchor, retaining CMDCTRL mirror provenance.

    Only undistorted, integer, one-to-one rectangles are accepted. The nearby
    reversed/compressed shadow command is deliberately not a matching body.
    """
    if piece['attributes'] != 0:
        raise ValueError('Unverified multi-piece attributes; composition remains blocked')
    foot = (divide16(signed_word(word(actor, 0))) - camera[0], divide16(signed_word(word(actor, 2))) - camera[1])
    x, y = foot[0] + piece['offset'][0], foot[1] + piece['offset'][1]
    expected = [x, y, x + texture.width - 1, y, x + texture.width - 1, y + texture.height - 1, x, y + texture.height - 1]
    candidates = []
    for row in rows:
        if row.get('kind') != 'command' or row.get('command') != 2 or row.get('color_mode') != 2 or (row.get('width'), row.get('height')) != (texture.width, texture.height):
            continue
        local = row['local_coordinate']
        positioned = [coord + local[i % 2] for i, coord in enumerate(row['signed_coordinates'])]
        if positioned != expected:
            continue
        raw = span(vram, row['texture_offset'], len(texture.indices))
        if raw == texture.indices:
            candidates.append(row)
    if len(candidates) != 1:
        raise ValueError(f'Expected one source/geometry-bound body command; found {len(candidates)}')
    return candidates[0] | {'screen_origin': [x, y], 'screen_anchor': list(foot),
                           'source_anchor': [-piece['offset'][0], -piece['offset'][1]],
                           'mirror_evidence': 'captured CMDCTRL bits 4/5; actor-to-mirror rule not yet inferred'}


def oriented_image(image: Image.Image, row: dict) -> Image.Image:
    if row['flip_x']:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if row['flip_y']:
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return image


def compare_visible(image: Image.Image, origin: tuple[int, int], video: bytes, width: int, height: int) -> dict:
    if len(video) != width * height * 4 or image.mode != 'RGBA':
        raise ValueError('Video frame or decoded image format is incomplete')
    matching, mismatches, outside = 0, [], 0
    for y in range(image.height):
        for x in range(image.width):
            expected = image.getpixel((x, y))
            if expected[3] == 0:
                continue
            px, py = origin[0] + x, origin[1] + y
            if not 0 <= px < width or not 0 <= py < height:
                outside += 1
                continue
            position = (py * width + px) * 4
            actual = tuple(video[position:position + 4])
            if expected == actual:
                matching += 1
            else:
                mismatches.append({'sprite_pixel': [x, y], 'screen_pixel': [px, py], 'decoded': list(expected), 'observed': list(actual)})
    return {'matching_opaque_pixels': matching, 'mismatched_opaque_pixels': len(mismatches),
            'outside_viewport_pixels': outside, 'mismatches': mismatches,
            'passed': matching > 0 and not mismatches and not outside,
            'scope': 'opaque body pixels only; transparent backdrop, projected shadow and other layers are not reconstructed'}


def executed_command(raw: bytes, address: int, local: tuple[int, int]) -> dict:
    """Decode the observed 32 bytes, without pretending to follow a RAM list."""
    if len(raw) != 32 or type(address) is not int or address < 0 or address % 8:
        raise ValueError('Invalid executed command payload/address')
    values = struct.unpack('>16H', raw)
    ctrl, _, pmod, colr, src, size = values[:6]
    if ctrl & (0x8000 | 0x4000):
        raise ValueError('Skipped/END command cannot be an executed body')
    return {'kind': 'command', 'offset': address, 'ctrl': ctrl, 'command': ctrl & 15,
            'pmod': pmod, 'colr': colr, 'texture_offset': src * 8,
            'width': ((size >> 8) & 63) * 8, 'height': size & 255,
            'color_mode': (pmod >> 3) & 7, 'flip_x': bool(ctrl & 16), 'flip_y': bool(ctrl & 32),
            'signed_coordinates': list(struct.unpack_from('>8h', raw, 12)), 'local_coordinate': list(local)}


def compare_framebuffer(texture: Texture, command: dict, framebuffer: bytes) -> dict:
    """Compare the 16-bit codes, independently of final VDP2 palette/composition."""
    if len(framebuffer) != 0x40000:
        raise ValueError('Truncated VDP1 framebuffer')
    matching, mismatches, outside = 0, [], 0
    for y in range(texture.height):
        for x in range(texture.width):
            tx = texture.width - 1 - x if command['flip_x'] else x
            ty = texture.height - 1 - y if command['flip_y'] else y
            value = texture.indices[ty * texture.width + tx]
            if not value and not command['pmod'] & 64:
                continue
            sx, sy = x + command['screen_origin'][0], y + command['screen_origin'][1]
            if not 0 <= sx < 512 or not 0 <= sy < 256:
                outside += 1
                continue
            expected = (command['colr'] & 0xffc0) | value
            actual = word(framebuffer, (sy * 512 + sx) * 2)
            if actual == expected:
                matching += 1
            else:
                mismatches.append({'screen_pixel': [sx, sy], 'expected_code': expected, 'actual_code': actual})
    return {'matching_opaque_codes': matching, 'mismatched_opaque_codes': len(mismatches),
            'outside_framebuffer_pixels': outside, 'mismatches': mismatches,
            'passed': matching > 0 and not mismatches and not outside}


def rectangular_code(command: dict, packed: bytes, x: int, y: int) -> int | None:
    """Source texel written by a one-to-one rectangle at a screen coordinate."""
    xy = [v + command['local_coordinate'][i % 2] for i, v in enumerate(command['signed_coordinates'])]
    if not min(xy[::2]) <= x <= max(xy[::2]) or not min(xy[1::2]) <= y <= max(xy[1::2]):
        return None
    width, height, mode = command['width'], command['height'], command['color_mode']
    left, top = xy[:2]
    if command['command'] != 2 or xy != [left, top, left + width - 1, top, left + width - 1, top + height - 1, left, top + height - 1]:
        raise ValueError('Overlapping sprite has unverified distortion')
    if mode not in (0, 2) or not command['pmod'] & 128 or command['pmod'] & (0x8000 | 0x100 | 7):
        raise ValueError('Overlapping sprite has unverified pixel operation')
    expected_size = width * height // 2 if mode == 0 else width * height
    if len(packed) != expected_size:
        raise ValueError('Overlapping sprite texture is truncated')
    tx, ty = x - left, y - top
    if command['flip_x']:
        tx = width - 1 - tx
    if command['flip_y']:
        ty = height - 1 - ty
    index = ty * width + tx
    value = ((packed[index // 2] >> (4 if index % 2 == 0 else 0)) & 15) if mode == 0 else packed[index] & 63
    if value == 0 and not command['pmod'] & 64:
        return None
    return (command['colr'] & (0xfff0 if mode == 0 else 0xffc0)) | value


def sprite_code_rgba(code: int, cram: bytes, regs: dict) -> tuple[tuple[int, int, int, int], int]:
    """Type-6 palette sprite pixel plus hardware priority (ordinary pixels only)."""
    if regs['SPCTL'] & 15 != 6 or (regs['RAMCTL'] >> 12) & 3 != 1 or code & 0x8000 or code & 1023 in (0, 1022):
        raise ValueError('Unverified sprite special/RGB format')
    if regs['CCCTL'] & 64 or regs['CLOFEN'] & 64 and any(regs[key] for key in ('COAR', 'COAG', 'COAB', 'CLOFSL')):
        raise ValueError('Unverified sprite blend/offset in composition')
    color = word(cram, ((((regs['CRAOFB'] >> 4) & 7) * 256 + (code & 1023)) * 2) & 0xffe)
    rgba = tuple(((color >> shift) & 31) << 3 for shift in (0, 5, 10)) + (255,)
    index = (code >> 12) & 7
    priority = (regs['PRIS' + 'ABCD'[index // 2]] >> ((index % 2) * 8)) & 7
    return rgba, priority


class BackgroundSource:
    """Bounded NBG0/1 special-priority foreground directly from original layout."""
    def __init__(self, raw: bytes):
        if sha(raw) != MAP_SHA256:
            raise ValueError('Changed foreground source')
        from decode_source_scene import source_data
        self.tiles, self.layout, self.palette, _ = source_data(raw)

    def pixel(self, layer: int, world_x: int, world_y: int) -> dict:
        if layer not in (0, 1) or not (0 <= world_x < 2048 and 0 <= world_y < 2048):
            raise ValueError('Foreground world coordinate outside source')
        offset = layer * 32768 + ((world_y // 16) * 128 + world_x // 16) * 2
        compact = word(self.layout, offset)
        if compact & 0x1c00:
            raise ValueError('Unverified source pattern bits')
        tx, ty = world_x % 16, world_y % 16
        if compact & 0x4000:
            tx = 15 - tx
        if compact & 0x8000:
            ty = 15 - ty
        tile_offset = (compact & 1023) * 256
        index = self.tiles[tile_offset + ((tx // 8) + (ty // 8) * 2) * 64 + (ty % 8) * 8 + tx % 8]
        color = word(self.palette, index * 2)
        return {'rgba': tuple(((color >> shift) & 31) << 3 for shift in (0, 5, 10)) + (255 if index else 0,),
                'priority': 2 | bool(compact & 0x2000), 'layer': layer, 'index': index,
                'layout_offset': offset, 'compact_pattern': compact, 'tile_offset': tile_offset}

    @staticmethod
    def check_registers(regs: dict) -> None:
        from decode_background import parameters
        for layer in (0, 1):
            parameters(regs, layer)
        if regs['PRINA'] != 0x0202 or regs['SFPRMD'] & 15 != 5 or regs['CRAOFA'] & 0x77 or regs['CCCTL'] & 3:
            raise ValueError('Unverified background priority/palette/blend configuration')
        if regs['CLOFEN'] & 3 and any(regs[k] for k in ('COAR', 'COAG', 'COAB', 'CLOFSL')):
            raise ValueError('Unverified background color offset')

    def foreground(self, camera: tuple[int, int] = (544, 1536)) -> Image.Image:
        image = Image.new('RGBA', (320, 224))
        for y in range(224):
            for x in range(320):
                # NBG0 wins equal background priority; sprite priority 2 is
                # overridden only by opaque special-priority 3 dots.
                for layer in (0, 1):
                    value = self.pixel(layer, x + camera[0], y + camera[1])
                    if value['priority'] == 3 and value['index']:
                        image.putpixel((x, y), value['rgba'])
                        break
        return image
