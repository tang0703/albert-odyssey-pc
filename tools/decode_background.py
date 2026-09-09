"""Diagnostic NBG0/1 pages from the pinned snapshot, without final composition."""
import json
import struct

from PIL import Image

from pipeline import PROJECT, WORKSPACE, digest, read_json, verify_source, write_json
from read_ymir_state import extract


def parameters(regs: dict, layer: int) -> dict:
    if layer not in (0, 1):
        raise ValueError("Only NBG0/1 supported")
    if regs["TVMD"] != 0x8000:
        raise ValueError("Only the captured 320x224 progressive display mode is supported")
    ctl = (regs["CHCTLA"] >> (8*layer)) & 255
    if ctl != 0x11 or regs[f"PNCN{'AB'[layer]}"] != 0 or (regs["PLSZ"] >> (2*layer)) & 3:
        raise ValueError("Expected 16x16, 256-color, two-word patterns and single-page planes")
    if ((regs["RAMCTL"] >> 12) & 3) != 1:
        raise ValueError("Unsupported CRAM mode")
    if not regs["BGON"] & (1 << layer):
        raise ValueError("Layer disabled")
    if regs["SCRCTL"] != 0 or any(regs[f"ZM{axis}IN{layer}"] != 1 or regs[f"ZM{axis}DN{layer}"] != 0 for axis in "XY"):
        raise ValueError("Line/vertical scroll or scaling unsupported")
    if regs[f"SCXDN{layer}"] or regs[f"SCYDN{layer}"]:
        raise ValueError("Fractional scroll unsupported")
    high = ((regs["MPOFN"] >> (4*layer)) & 7) << 6
    planes = []
    for name in (f"MPABN{layer}", f"MPCDN{layer}"):
        for shift in (0, 8):
            index = high | ((regs[name] >> shift) & 63)
            planes.append((index & 255) << 12)
    return {"layer": layer, "plane_offsets": planes, "scroll_x": regs[f"SCXIN{layer}"] & 2047,
            "scroll_y": regs[f"SCYIN{layer}"] & 2047,
            "cram_base": ((regs["CRAOFA"] >> (4*layer)) & 7)*256,
            "transparent_zero": not bool(regs["BGON"] & (1 << (8+layer)))}


def decode_tile(vram: bytes, cram: bytes, word: int, params: dict) -> tuple[Image.Image, int]:
    char_address = (word & 0x7fff)*32
    if len(vram) != 0x80000 or len(cram) != 4096 or char_address+256 > len(vram):
        raise ValueError("VRAM/CRAM or tile bounds unsupported")
    palette = (word >> 16) & 0x70
    pixels = []
    for y in range(16):
        for x in range(16):
            tx, ty = (15-x if word & (1<<30) else x), (15-y if word & (1<<31) else y)
            cell = (tx//8) + (ty//8)*2
            value = vram[char_address + cell*64 + (ty%8)*8 + tx%8]
            if value == 0 and params["transparent_zero"]:
                pixels.append((0, 0, 0, 0))
            else:
                index = (params["cram_base"] + (palette<<4) + value) & 2047
                color = struct.unpack_from(">H", cram, index*2)[0]
                channels = [(color >> shift) & 31 for shift in (0, 5, 10)]
                pixels.append(tuple((c<<3)|(c>>2) for c in channels) + (255,))
    image = Image.new("RGBA", (16,16))
    image.putdata(pixels)
    return image, char_address


def decode_page(vram: bytes, cram: bytes, offset: int, params: dict) -> tuple[Image.Image, list[dict]]:
    if offset < 0 or offset+4096 > len(vram):
        raise ValueError("Pattern page outside VRAM")
    page = Image.new("RGBA", (512,512))
    entries = []
    cache = {}
    for i in range(1024):
        word = struct.unpack_from(">I", vram, offset+i*4)[0]
        if word not in cache:
            cache[word] = decode_tile(vram, cram, word, params)
        tile, address = cache[word]
        page.paste(tile, ((i%32)*16, (i//32)*16))
        entries.append({"pattern_offset": offset+i*4, "pattern_word": word,
                        "tile_offset": address, "tile_sha256": digest(vram[address:address+256])})
    return page, entries


def viewport(pages: list[Image.Image], sx: int, sy: int) -> Image.Image:
    if len(pages) != 4 or any(p.size != (512,512) for p in pages):
        raise ValueError("Expected four 512x512 planes")
    result = Image.new("RGBA", (320,224))
    for y in range(224):
        for x in range(320):
            xx, yy = (sx+x)%1024, (sy+y)%1024
            result.putpixel((x,y), pages[xx//512+(yy//512)*2].getpixel((xx%512, yy%512)))
    return result


def run() -> dict:
    lock = read_json(PROJECT / "savestate-lock.json")
    state = extract(verify_source(WORKSPACE, lock["path"], lock["sha256"]), lock)
    vram, cram = state["blocks"]["vram2"], state["blocks"]["cram"]
    source_lock = read_json(PROJECT / "source-lock.json")["sources"]
    sources = {p: verify_source(WORKSPACE, p, source_lock[p]) for p in
               ["work/extract/MAP001.SNF", "work/extract/MAP001.TWN", "work/extract/MAP001.V1N"]}
    output = PROJECT / "reports/background"
    output.mkdir(parents=True, exist_ok=True)
    layers = []
    for layer in (0,1):
        params = parameters(state["regs2"], layer)
        pages, page_entries = {}, {}
        for offset in set(params["plane_offsets"]):
            pages[offset], page_entries[offset] = decode_page(vram, cram, offset, params)
            pages[offset].save(output/f"nbg{layer}-page-{offset:05x}.png")
        viewport([pages[p] for p in params["plane_offsets"]], params["scroll_x"], params["scroll_y"]).save(output/f"nbg{layer}-viewport.png")
        tiles = {}
        for entries in page_entries.values():
            for entry in entries:
                address = entry["tile_offset"]
                if address in tiles:
                    continue
                payload = vram[address:address+256]
                matches = []
                # Avoid claiming provenance for uniform/low-information blocks.
                if len(set(payload)) >= 4:
                    for path, raw in sources.items():
                        start = raw.find(payload)
                        while start >= 0:
                            matches.append({"source": path, "offset": start})
                            start = raw.find(payload, start+1)
                tiles[address] = {"offset": address, "sha256": digest(payload), "matches": matches}
        layers.append({"parameters": params, "entries": {str(k): v for k,v in page_entries.items()},
                       "tiles": list(tiles.values()), "unique_tiles": len(tiles),
                       "exact_source_tiles": sum(bool(t["matches"]) for t in tiles.values())})
    result = {"schema": "ao_pc_background_pages_v1", "snapshot_sha256": lock["sha256"],
              "vram_sha256": digest(vram), "cram_sha256": digest(cram), "layers": layers,
              "limits": ["Diagnostic static NBG0/1 pages, not final screen reconstruction.",
                         "No VRAM cycle pipeline, color offsets, windows, priority, special color calculation, sprites or NBG3.",
                         "No collision or map identity inferred; negative byte matches do not rule out compressed source."]}
    write_json(PROJECT / "reports/background-layers.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps([{k:v for k,v in r.items() if k in ("parameters", "unique_tiles", "exact_source_tiles")} for r in run()["layers"]], indent=2))
