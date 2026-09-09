"""Source-guarded PC asset import. Diagnostics never imply playable-map fidelity."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def checked_slice(data: bytes, offset: int, size: int) -> bytes:
    if type(offset) is not int or type(size) is not int or offset < 0 or size <= 0 or offset + size > len(data):
        raise ValueError(f"Invalid source span: {offset}+{size}/{len(data)}")
    return data[offset:offset + size]


def verify_source(root: Path, relative: str, expected: str) -> bytes:
    source = (root / relative).resolve()
    if not source.is_relative_to(root.resolve()):
        raise ValueError("Source escaped workspace")
    raw = source.read_bytes()
    if digest(raw) != expected.lower():
        raise ValueError(f"Source hash mismatch: {relative}")
    return raw


def parse_v1n(data: bytes) -> list[dict]:
    """Strict observed 0x0011/0x0001 layout; dimensions use CMDSIZE packing.

    Output contains palette indices, NOT proven display colors or animation order.
    Fail closed if a variant does not satisfy all record boundaries.
    """
    records = []
    cursor = 0
    ids = set()
    while cursor < len(data):
        if data[cursor:] == b"\0\0\0\0":
            cursor += 4
            break
        if len(data) - cursor < 8:
            raise ValueError(f"Truncated V1N header at {cursor:#x}")
        tag, index, attributes, size = struct.unpack_from(">4H", data, cursor)
        if tag not in (0x11, 0x01) or attributes != 0 or size & 0xC000:
            raise ValueError(f"Unsupported V1N record at {cursor:#x}: {tag:04x}/{attributes:04x}/{size:04x}")
        width, height = ((size >> 8) & 63) * 8, size & 255
        if not width or not height or index in ids:
            raise ValueError(f"Invalid dimensions or duplicate texture id at {cursor:#x}")
        bits = 8 if tag == 0x11 else 4
        packed = checked_slice(data, cursor + 8, width * height * bits // 8)
        payload = packed if bits == 8 else bytes(v for byte in packed for v in (byte >> 4, byte & 15))
        records.append({"id": f"map001_v1n_{index:04x}", "index": index,
                        "offset": cursor, "span": 8 + len(packed), "payload_offset": cursor + 8,
                        "bits_per_pixel": bits, "packed_sha256": digest(packed),
                        "width": width, "height": height, "indices_sha256": digest(payload),
                        "palette": None, "anchor": None, "duration": None,
                        "status": "structural_index_texture_only", "payload": payload})
        ids.add(index)
        cursor += 8 + len(packed)
    if not records:
        raise ValueError("Empty V1N")
    if data[-4:] != b"\0\0\0\0":
        raise ValueError("Missing V1N terminator")
    return records


def parse_snf_directory(data: bytes) -> list[dict]:
    """Bounds-checked structural directory; chunk purpose remains unclassified."""
    if len(data) < 16:
        raise ValueError("Truncated SNF")
    first_payload = struct.unpack_from(">I", data, 4)[0]
    if first_payload < 32 or first_payload % 16 or first_payload > len(data):
        raise ValueError("Invalid SNF directory boundary")
    chunks = []
    ended = False
    for cursor in range(0, first_payload, 16):
        tag, offset, length, reserved = struct.unpack_from(">4I", data, cursor)
        if tag == offset == length == reserved == 0:
            ended = True
            if any(data[cursor:first_payload]):
                raise ValueError("Nonzero bytes after directory terminator")
            break
        if reserved or offset < first_payload:
            raise ValueError("Invalid SNF entry")
        payload = checked_slice(data, offset, length)
        if chunks and offset < chunks[-1]["offset"] + chunks[-1]["span"]:
            raise ValueError("Overlapping SNF chunks")
        chunks.append({"tag": f"{tag:08x}", "offset": offset, "span": length,
                       "sha256": digest(payload), "status": "container_only_semantics_unknown"})
    if not ended:
        raise ValueError("SNF directory lacks terminator")
    return chunks


def parse_aiff(data: bytes) -> dict:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] != b"AIFF":
        raise ValueError("Not uncompressed AIFF")
    end = int.from_bytes(data[4:8], "big") + 8
    if end != len(data):
        raise ValueError("AIFF FORM length mismatch")
    cursor, chunks = 12, {}
    while cursor < end:
        header = checked_slice(data, cursor, 8)
        tag, size = header[:4], int.from_bytes(header[4:], "big")
        value = checked_slice(data, cursor + 8, size)
        if tag in chunks:
            raise ValueError("Duplicate AIFF chunk")
        chunks[tag] = value
        cursor += 8 + size + size % 2
    if cursor != end or b"COMM" not in chunks or b"SSND" not in chunks:
        raise ValueError("Incomplete AIFF")
    comm, sound = chunks[b"COMM"], chunks[b"SSND"]
    if len(comm) != 18 or len(sound) < 8:
        raise ValueError("Invalid AIFF metadata")
    channels, frames, bits = struct.unpack_from(">HIH", comm)
    exponent = int.from_bytes(comm[8:10], "big")
    mantissa = int.from_bytes(comm[10:18], "big")
    if exponent & 0x8000 or exponent in (0, 0x7FFF):
        raise ValueError("Unsupported AIFF sample rate")
    rate = math.ldexp(mantissa, exponent - 16383 - 63)
    offset, block = struct.unpack_from(">II", sound)
    if channels < 1 or channels > 8 or bits not in (8, 16, 24, 32) or block != 0:
        raise ValueError("Unsupported AIFF PCM layout")
    required = frames * channels * (bits // 8)
    if len(sound) != 8 + offset + required:
        raise ValueError("AIFF sample count mismatch")
    return {"format": "AIFF PCM big-endian", "channels": channels, "frames": frames,
            "bits": bits, "sample_rate": rate, "seconds": frames / rate,
            "loop_status": "not_validated", "role": "not_inferred_from_filename"}


def import_dialogue(raw: bytes, descriptor: dict, tsv: str) -> list[dict]:
    records = [r for r in descriptor["records"] if r["source_file"] == "/MAP001.TWN"]
    expected = next(f["sha256"] for f in descriptor["files"] if f["source_file"] == "/MAP001.TWN")
    if digest(raw) != expected:
        raise ValueError("Dialogue source changed")
    rows = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        if row["id"] in rows:
            raise ValueError("Duplicate translation id")
        rows[row["id"]] = row
    output = []
    for record in records:
        offset, span = int(record["record_offset"], 16), record["record_span"]
        if digest(checked_slice(raw, offset, span)) != record["original_sha256"]:
            raise ValueError(f"Record mismatch: {record['id']}")
        pages = []
        for page in record["pages"]:
            page_offset = int(page["text_offset"], 16)
            original = bytes.fromhex(page["original_hex"])
            if checked_slice(raw, page_offset, len(original)) != original:
                raise ValueError(f"Page bytes changed: {page['id']}")
            translated = rows[page["id"]]
            if (translated["en"] != page["en"] or translated["source_file"] != "/MAP001.TWN"
                    or int(translated["offset_or_ref"], 16) != page_offset or not translated["zh_tw"].strip()):
                raise ValueError(f"Translation no longer aligned: {page['id']}")
            pages.append({"id": page["id"], "speaker": page["speaker"], "en": page["en"],
                          "zh_tw": translated["zh_tw"], "offset": page_offset,
                          "span": len(original), "sha256": digest(original), "controls": page["controls"],
                          "playback_allowed": not bool(page["controls"])})
        output.append({"id": record["id"], "speaker": record["speaker"], "offset": offset,
                       "span": span, "pages": pages, "status": "text_verified_trigger_not_ported"})
    return output


def build(lock_path: Path = PROJECT / "source-lock.json") -> dict:
    lock = read_json(lock_path)
    sources = {p: verify_source(WORKSPACE, p, h) for p, h in lock["sources"].items()}
    raw = sources["work/extract/MAP001.TWN"]
    dialogue = import_dialogue(raw, json.loads(sources["work/analysis/dialogue_twn_all_descriptors.json"]),
                               sources["translation/zh-TW/dialogue_twn_all.tsv"].decode("utf-8-sig"))
    generated = PROJECT / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    blockers = [
        {"id": "map_layers", "detail": "Background layers, tile placement and collision have not been decoded and compared with MAP001 gameplay."},
        {"id": "sprite_binding", "detail": "V1N palette, actor identity, anchor and animation timing are not yet bound to runtime evidence."},
        {"id": "event_reachability", "detail": "Verified text records are not a map event graph; NPC placement and event triggers are unresolved."},
        {"id": "battle_rules", "detail": "Original battle formulas, encounter and return-to-map state are not yet reconstructed."},
    ]
    textures = []
    try:
        textures = parse_v1n(sources["work/extract/MAP001.V1N"])
    except ValueError as exc:
        blockers.append({"id": "v1n_layout", "detail": str(exc)})
    sheet = Image.new("RGB", (768, max(128, math.ceil(min(len(textures), 48) / 8) * 112)), "#151d27")
    draw = ImageDraw.Draw(sheet)
    for i, texture in enumerate(textures):
        payload = texture.pop("payload")
        # Grayscale is an explicit palette-index diagnostic, not a reconstructed palette.
        original = Image.frombytes("L", (texture["width"], texture["height"]), payload)
        file = generated / "indices" / f"{texture['id']}.png"
        file.parent.mkdir(exist_ok=True)
        original.save(file)
        texture["png"] = "res://generated/indices/" + file.name
        if i < 48:
            maximum = max(payload) or 1
            preview = original.point([round(v * 255 / maximum) for v in range(256)])
            preview.thumbnail((88, 84), Image.Resampling.NEAREST)
            x, y = (i % 8) * 96, (i // 8) * 112
            sheet.paste(preview, (x + (96 - preview.width) // 2, y))
            draw.text((x + 4, y + 88), f"#{texture['index']} {texture['width']}x{texture['height']}", fill="white")
    sheet.save(generated / "v1n-index-contact.png")
    chunks = parse_snf_directory(sources["work/extract/MAP001.SNF"])
    audio = parse_aiff(sources["work/extract/ACPAIK.AIF"])
    package = {"schema": "ao_pc_asset_package_v1", "source_lock_sha256": digest(lock_path.read_bytes()),
               "sources": [{"path": p, "sha256": h} for p, h in lock["sources"].items()],
               "map_id": "MAP001", "playable": False, "gate_b": "blocked",
               "dialogue_records": dialogue, "textures": textures, "snf_directory": chunks,
               "audio_probe": audio, "blockers": blockers}
    write_json(generated / "package.json", package)
    report = {"stage_a": "tool_verification_in_progress", "stage_b": "blocked", "stage_c": "not_started",
              "stage_d": "not_started", "stage_e": "not_started", "playable": False,
              "verified_dialogue_records": len(dialogue), "verified_dialogue_pages": sum(len(r["pages"]) for r in dialogue),
              "structural_texture_records": len(textures), "snf_chunks": len(chunks), "audio": audio,
              "blockers": blockers, "package_sha256": digest((generated / "package.json").read_bytes())}
    write_json(PROJECT / "reports" / "pipeline.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "verify"])
    args = parser.parse_args()
    try:
        if args.command == "verify":
            lock = read_json(PROJECT / "source-lock.json")
            for path, expected in lock["sources"].items():
                verify_source(WORKSPACE, path, expected)
            print("Source lock verified")
        else:
            print(json.dumps(build(), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f"IMPORT REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
