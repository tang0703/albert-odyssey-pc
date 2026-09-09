"""Source-only pixels/layout/palette for the verified MAP001 camera region."""
import json
import struct

from PIL import Image

from pipeline import PROJECT, WORKSPACE, digest, read_json, verify_source, write_json
from decode_map_graphics import map001_blocks, decode_mode5
from decode_background import decode_tile
from read_ymir_state import extract

CAMERA = (544, 1536)  # Captured context, not a source-decoded spawn point.
GRID_SIZE = 128


def source_data(raw: bytes) -> tuple[bytes, bytes, bytes, list[dict]]:
    blocks = map001_blocks(raw)
    decoded = []
    for block in blocks[:2]:
        pos = block['payload_offset']
        decoded.append(decode_mode5(raw[pos:pos+block['size']])[0])
    if tuple(map(len,decoded)) != (262144,65536):
        raise ValueError('Unexpected MAP001 tile/layout sizes')
    # The second 256-color palette matches visible nontransparent CRAM entries.
    start = blocks[3]['payload_offset']+512
    palette = raw[start:start+512]
    if len(palette) != 512:
        raise ValueError('Truncated source palette')
    return decoded[0],decoded[1],palette,blocks


def pattern_word(compact: int) -> int:
    if not 0 <= compact <= 65535 or compact & 0x1c00:
        raise ValueError('Unsupported compact pattern flags')
    return (0x2000+(compact & 1023)*8) | ((compact & 0xe000)<<16)


def render_view(tiles: bytes, layout: bytes, palette: bytes, layer: int,
                camera: tuple[int,int] = CAMERA) -> tuple[Image.Image,list[dict]]:
    if (len(tiles),len(layout),len(palette)) != (262144,65536,512) or layer not in (0,1):
        raise ValueError('Source dimensions or layer invalid')
    sx,sy = camera
    if sx%16 or sy%16 or sx<0 or sy<0 or sx+320>2048 or sy+224>2048:
        raise ValueError('Only in-bounds tile-aligned views supported')
    vram = bytes(0x40000)+tiles
    cram = palette+bytes(4096-512)
    image = Image.new('RGBA',(320,224))
    records,cache = [],{}
    for y in range(14):
        for x in range(20):
            world_x,world_y = sx//16+x,sy//16+y
            offset = layer*32768+(world_y*GRID_SIZE+world_x)*2
            compact = struct.unpack_from('>H',layout,offset)[0]
            word = pattern_word(compact)
            if word not in cache:
                cache[word] = decode_tile(vram,cram,word,{'cram_base':0,'transparent_zero':True})[0]
            image.paste(cache[word],(x*16,y*16))
            records.append({'layer':layer,'world_tile':[world_x,world_y],'layout_decoded_offset':offset,
                            'compact_pattern':compact,'vdp2_pattern':word,
                            'tile_id':f'map001_bg_{(compact&1023)*256:05x}'})
    return image,records


def run() -> dict:
    path = 'work/extract/MAP001.TWN'
    raw = verify_source(WORKSPACE,path,read_json(PROJECT/'source-lock.json')['sources'][path])
    tiles,layout,palette,blocks = source_data(raw)
    # Verification alone reads a state; render_view has no snapshot dependency.
    lock = read_json(PROJECT/'savestate-lock.json')
    state = extract(verify_source(WORKSPACE,lock['path'],lock['sha256']),lock)
    if palette[2:] != state['blocks']['cram'][2:512]:
        raise ValueError('Nontransparent source palette differs from reference')
    expected_png = read_json(PROJECT/'docs/background-validation.json')['png_sha256']
    output = PROJECT/'reports/source-scene'
    output.mkdir(parents=True,exist_ok=True)
    layers = []
    for layer in (0,1):
        image,records = render_view(tiles,layout,palette,layer)
        for record in records:
            x,y = record['world_tile']
            address = layer*0x2000+((y%32)*32+x%32)*4
            actual = struct.unpack_from('>I',state['blocks']['vram2'],address)[0]
            if actual != record['vdp2_pattern']:
                raise ValueError(f'Visible pattern differs at layer {layer}, {x},{y}')
            record['reference_pattern_offset'] = address
        name = f'nbg{layer}-viewport.png'
        image.save(output/name)
        png_hash = digest((output/name).read_bytes())
        if png_hash != expected_png[name]:
            raise ValueError('Source-only viewport differs from prior snapshot rendering')
        layers.append({'layer':layer,'matched_patterns':len(records),'png_sha256':png_hash,'records':records})
    report = {'schema':'ao_pc_source_scene_v1','source':path,'source_sha256':digest(raw),
              'snapshot_sha256':lock['sha256'],'camera_pixels':list(CAMERA),
              'layout':{'payload_offset':blocks[1]['payload_offset'],'grid_size':[128,128],'layers':2,
                        'decoded_sha256':digest(layout)},
              'palette':{'source_offset':blocks[3]['payload_offset']+512,'matched_nontransparent_bytes':510,
                         'source_zero_entry':palette[:2].hex(),'reference_zero_entry':state['blocks']['cram'][:2].hex(),
                         'zero_entry_policy':'index zero is transparent; RGB difference does not affect these layers'},
              'layers':layers,'limits':['Only this camera region has pattern-by-pattern snapshot validation.',
                                       'Camera and display context are captured constants, not source-derived spawn/event rules.',
                                       'No sprites, NBG3, composition, collision, animation or runtime upload validation.']}
    write_json(PROJECT/'reports/source-scene.json',report)
    return report


if __name__=='__main__':
    print(json.dumps({'matched_patterns':[l['matched_patterns'] for l in run()['layers']]},indent=2))
