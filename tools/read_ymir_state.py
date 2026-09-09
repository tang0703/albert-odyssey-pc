"""Read a hash-pinned Ymir v13 VDP region; not a general save-state loader."""
import json
import struct

from PIL import Image, ImageDraw

from pipeline import PROJECT, WORKSPACE, digest, read_json, verify_source, write_json
from trace_vdp1 import TraceError, bind_textures, trace


def extract(data: bytes, lock: dict) -> dict:
    if len(data) != lock["size"] or digest(data) != lock["sha256"]:
        raise ValueError("Save-state fixture identity changed")
    if data[:5] != b"\x01\x0d\0\0\0" or lock["version"] != 13:
        raise ValueError("Only little-endian cereal archive version 13 is supported")
    pos = lock["vdp_payload_offset"]
    if data[pos-4:pos] != b"VDP#" or data.count(b"VDP#") != 1:
        raise ValueError("Pinned VDP boundary does not match")
    blocks, spans = {}, {}
    for name, size in [("vram1", 0x80000), ("vram2", 0x80000), ("cram", 0x1000), ("framebuffers", 0x80000)]:
        if pos + size > len(data):
            raise ValueError("Truncated VDP region")
        blocks[name] = data[pos:pos+size]
        spans[name] = {"offset": pos, "size": size, "sha256": digest(blocks[name])}
        pos += size
    display, penalty, changed, vcnt_latch, next_address = struct.unpack_from("<BQ?HI", data, pos)
    pos += 16
    if display not in (0, 1):
        raise ValueError("Invalid framebuffer index")
    names1 = "TVMR FBCR PTMR EWDR EWLR EWRR EDSR LOPR COPR MODR".split()
    regs1 = dict(zip(names1, struct.unpack_from("<10H", data, pos)))
    pos += 20
    names2 = lock["registers2"]
    if len(names2) != 142 or len(set(names2)) != 142:
        raise ValueError("Register schema mismatch")
    regs2 = dict(zip(names2, struct.unpack_from("<142H", data, pos)))
    pos += 284
    hphase, vphase = struct.unpack_from("<II", data, pos)
    # Renderer prefix: 7 uint16 clip/doubleV fields, 2 sint32 local coordinates.
    drawing, display_erase, vblank_erase = struct.unpack_from("<3B", data, pos + 8 + 14 + 8)
    if any(v not in (0, 1) for v in (drawing, display_erase, vblank_erase)):
        raise ValueError("Invalid renderer Boolean")
    return {"blocks": blocks, "spans": spans, "regs1": regs1, "regs2": regs2,
            "display_framebuffer": display, "drawing": bool(drawing),
            "next_command_address": next_address, "hphase": hphase, "vphase": vphase,
            "timing_penalty": penalty, "fbcr_changed": changed, "vcnt_latch": vcnt_latch}


def palette_texture(row: dict, ram: bytes, cram: bytes, regs1: dict, regs2: dict) -> Image.Image:
    """Intrinsic texture in snapshot palette; not a rasterized/composited sprite.

    Narrow, fail-closed support for the actual bank modes in this fixture.
    No guessed fallback palettes, shadow colors or unsupported effects.
    """
    if regs1["TVMR"] != 0 or ((regs2["RAMCTL"] >> 12) & 3) != 1 or (regs2["SPCTL"] & 15) != 6:
        raise ValueError("Unsupported display/color RAM/sprite mode")
    mode, pmod = row["color_mode"], row["pmod"]
    if mode not in (0, 2) or not pmod & 128 or pmod & (0x8000 | 0x100 | 7):
        raise ValueError("Unsupported texture mode, end codes, mesh or color operation")
    width, height = row["width"], row["height"]
    if width <= 0 or height <= 0:
        raise ValueError("Empty texture")
    length = width * height // 2 if mode == 0 else width * height
    start = row["texture_offset"]
    packed = ram[start:start+length]
    if start < 0 or len(packed) != length or len(cram) != 4096:
        raise ValueError("Texture or CRAM bounds")
    pixels = [p for b in packed for p in (b >> 4, b & 15)] if mode == 0 else list(packed)
    mask = 15 if mode == 0 else 63
    bank = row["colr"] & (0xffff ^ mask)
    if bank & 0x8000:
        raise ValueError("Shadow/window or RGB bank is unsupported")
    base = ((regs2["CRAOFB"] >> 4) & 7) * 256
    select = "B" if regs2["CLOFSL"] & 64 else "A"
    offsets = [regs2[f"CO{select}{c}"] & 511 for c in "RGB"] if regs2["CLOFEN"] & 64 else [0]*3
    offsets = [v-512 if v & 256 else v for v in offsets]
    rgba = []
    for value in pixels:
        if value == 0 and not pmod & 64:
            rgba.append((0, 0, 0, 0))
            continue
        color_code = (bank | (value & mask)) & 1023  # SPCTL type 6, DC9..0
        if color_code in (0, 1022):
            raise ValueError("Transparent/special shadow code requires final sprite composition")
        address = ((base + color_code) * 2) & 0xffe
        color = struct.unpack_from(">H", cram, address)[0]
        rgb5 = [(color >> shift) & 31 for shift in (0, 5, 10)]
        rgb = [max(0, min(255, ((v << 3) | (v >> 2)) + ofs)) for v, ofs in zip(rgb5, offsets)]
        rgba.append((*rgb, 255))
    image = Image.new("RGBA", (width, height))
    image.putdata(rgba)
    return image


def run() -> dict:
    lock = read_json(PROJECT / "savestate-lock.json")
    data = verify_source(WORKSPACE, lock["path"], lock["sha256"])
    state = extract(data, lock)
    ram = state["blocks"]["vram1"]
    try:
        rows, failure = trace(ram), None
    except TraceError as exc:
        rows, failure = exc.rows, {"offset": exc.offset, "reason": str(exc)}
    sources = read_json(PROJECT / "source-lock.json")["sources"]
    original = verify_source(WORKSPACE, "work/extract/MAP001.V1N", sources["work/extract/MAP001.V1N"])
    bindings = bind_textures(rows, ram, original)
    output = PROJECT / "reports/snapshot-palettes"
    output.mkdir(parents=True, exist_ok=True)
    samples, images = [], []
    by_offset = {r["offset"]: r for r in rows}
    for binding in bindings:
        if not binding["source_ids"]:
            continue
        row = by_offset[binding["command_offset"]]
        sample = dict(binding)
        try:
            image = palette_texture(row, ram, state["blocks"]["cram"], state["regs1"], state["regs2"])
            name = f"command-{row['offset']:05x}.png"
            image.save(output / name)
            sample.update(palette_status="decoded_intrinsic_texture", image=name,
                          rgba_sha256=digest(image.tobytes()))
            images.append((name, image))
        except ValueError as exc:
            sample.update(palette_status="unsupported", reason=str(exc))
        samples.append(sample)
    if images:
        sheet = Image.new("RGB", (640, ((len(images)+3)//4)*176), "#20242b")
        draw = ImageDraw.Draw(sheet)
        for i, (name, image) in enumerate(images):
            x, y = (i % 4)*160, (i // 4)*176
            enlarged = image.resize((image.width*3, image.height*3), Image.Resampling.NEAREST)
            sheet.paste(enlarged, (x+8, y+24), enlarged)
            draw.text((x+8, y+5), name, fill="white")
        sheet.save(output / "contact.png")
    report = {k: v for k, v in state.items() if k != "blocks"}
    report.update(schema="ao_pc_coherent_vdp_snapshot_v1", path=lock["path"], sha256=lock["sha256"],
                  trace_failure=failure, samples=samples,
                  summary={"bound_commands": len(samples), "palette_samples": len(images),
                           "drawing": state["drawing"], "next_command_address": state["next_command_address"]},
                  limits=["One hash-pinned save-state region, not a general Ymir save loader or new emulator run.",
                          "Snapshot palette textures, not animation, actor identity or final screen verification.",
                          "No distortion, clipping, priority, background composition or mirror applied."])
    write_json(PROJECT / "reports/coherent-vdp-snapshot.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(run()["summary"], indent=2))
