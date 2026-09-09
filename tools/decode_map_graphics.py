"""MAP001 graphics block evidence; scene context is verified separately."""
import json
import struct

from pipeline import PROJECT, WORKSPACE, digest, read_json, verify_source, write_json
from read_ymir_state import extract


def decode_mode5(data: bytes) -> tuple[bytes, int]:
    if len(data) < 5 or data[0] != 5:
        raise ValueError("Expected mode-5 stream header")
    size = struct.unpack_from(">I", data, 1)[0]
    if not 0 < size <= 0x80000:
        raise ValueError("Decoded size outside bound")
    output, pos = bytearray(), 5
    while len(output) < size:
        if pos >= len(data):
            raise ValueError("Missing control byte")
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if flags & (1 << bit):
                if pos >= len(data):
                    raise ValueError("Truncated literal")
                output.append(data[pos])
                pos += 1
            else:
                if pos+2 > len(data):
                    raise ValueError("Truncated back reference")
                low, packed = data[pos:pos+2]
                pos += 2
                distance = low | ((packed & 0xf0) << 4)
                length = (packed & 15)+3
                if not 0 < distance <= len(output):
                    raise ValueError("Invalid backwards distance")
                if len(output)+length > size:
                    raise ValueError("Back reference exceeds declared output size")
                for _ in range(length):
                    output.append(output[-distance])
            if len(output) == size:
                break
    # Container spans are 4-byte aligned. Tail bytes are not necessarily zero;
    # preserve them in evidence rather than decoding beyond the declared size.
    if len(data) != ((pos+3) & ~3):
        raise ValueError("Unexpected trailing bytes")
    return bytes(output), pos


def map001_blocks(data: bytes) -> list[dict]:
    # This boundary is pinned for MAP001, not inferred for all TWN files.
    pos, rows = 0xf230, []
    for expected in range(1,7):
        if pos+8 > len(data):
            raise ValueError("Truncated block header")
        tag, index, size = struct.unpack_from(">HHI", data, pos)
        if tag != expected or index != 1 or size <= 0 or pos+8+size > len(data):
            raise ValueError("Unexpected MAP001 block directory")
        rows.append({"tag":tag,"index":index,"header_offset":pos,"payload_offset":pos+8,
                     "size":size,"sha256":digest(data[pos+8:pos+8+size])})
        pos += 8+size
    if data[pos:] != b"\xff"*4:
        raise ValueError("Unexpected MAP001 block trailer")
    return rows


def run() -> dict:
    sources = read_json(PROJECT/'source-lock.json')["sources"]
    path = "work/extract/MAP001.TWN"
    raw = verify_source(WORKSPACE,path,sources[path])
    blocks = map001_blocks(raw)
    decoded_blocks = []
    decoded = {}
    for block in blocks[:2]:
        start = block["payload_offset"]
        payload, consumed = decode_mode5(raw[start:start+block["size"]])
        decoded[block["tag"]] = payload
        decoded_blocks.append(block | {"decoded_size":len(payload),"decoded_sha256":digest(payload),
                                       "compressed_consumed":consumed,"padding":block["size"]-consumed,
                                       "alignment_tail_hex":raw[start+consumed:start+block["size"]].hex()})
    lock = read_json(PROJECT/'savestate-lock.json')
    state = extract(verify_source(WORKSPACE,lock['path'],lock['sha256']),lock)
    target = state['blocks']['vram2'][0x40000:0x80000]
    if decoded[1] != target:
        raise ValueError("Decoded background block differs from pinned VRAM")
    output = PROJECT/'reports/source-background'
    output.mkdir(parents=True,exist_ok=True)
    (output/'tiles.bin').write_bytes(decoded[1])
    (output/'layout.bin').write_bytes(decoded[2])
    report = {"schema":"ao_pc_map001_graphics_v1","source":path,"source_sha256":digest(raw),
              "snapshot_sha256":lock['sha256'],"blocks":blocks,"decoded_blocks":decoded_blocks,
              "transfer_evidence":{"vram_start":0x40000,"bytes":len(target),"exact_match":True,
                                   "sha256":digest(target),"runtime_upload_call_verified":False},
              "limits":["Mode-5 layout inferred and validated by complete bytes; CPU decompressor not traced yet.",
                        "Block 2 compact layout and source palette validation are in decode_source_scene.py.",
                        "No independent gameplay scene loader or source-derived camera rules yet."]}
    write_json(PROJECT/'reports/background-source.json',report)
    return report


if __name__ == '__main__':
    print(json.dumps(run()['transfer_evidence'],indent=2))
