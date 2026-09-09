"""Trace a captured VDP1 list; never equate RAM reachability with visible pixels."""
from collections import Counter
import json
import struct

from pipeline import PROJECT, WORKSPACE, digest, parse_v1n, read_json, verify_source, write_json

REFERENCE = "work/bizhawk/dialogue_state_dumps/ascii_proof_page_01/VDP1_Ram.bin"
REFERENCE_SHA256 = "9f0f7685f0e86aa1032a42dda1656ab841084432a0a765ac926f25e4cf74088e"
MANUAL = "https://www.infochunk.com/saturn/segahtml_en/hard/vdp1/hon/p06_10.htm"


class TraceError(ValueError):
    def __init__(self, message: str, rows: list[dict], offset: int):
        super().__init__(message)
        self.rows = rows
        self.offset = offset


def trace(ram: bytes, max_steps: int = 16384) -> list[dict]:
    """CMDCTRL END takes precedence; skip commands still perform their jump.

    Invalid/ambiguous lists fail closed. A snapshot can be taken during list
    construction: termination is not proof that the VDP1 consumed this list.
    """
    pc, return_to = 0, None
    seen, rows = set(), []
    local = [0, 0]
    for _ in range(max_steps):
        if pc % 32 or pc < 0 or pc + 32 > len(ram):
            raise TraceError(f"Command outside/alignment at {pc:#x}", rows, pc)
        state = (pc, return_to)
        if state in seen:
            raise TraceError(f"Command cycle at {pc:#x}", rows, pc)
        seen.add(state)
        words = struct.unpack_from(">16H", ram, pc)
        ctrl, link, pmod, colr, src, size = words[:6]
        row = {"offset": pc, "ctrl": ctrl, "link": link * 8}
        if ctrl & 0x8000:
            rows.append(row | {"kind": "end"})
            return rows
        jump, command = (ctrl >> 12) & 7, ctrl & 15
        skipped = bool(jump & 4)
        if not skipped and command not in (0, 1, 2, 4, 5, 6, 8, 9, 10):
            raise TraceError(f"Prohibited command {command} at {pc:#x}", rows, pc)
        # Preserve raw coordinate words too; no guessed clipping or rasterizer.
        xy = list(struct.unpack_from(">8h", ram, pc + 12))
        if command == 10 and not skipped:
            local = xy[:2]
        row.update(kind="skip" if skipped else "command", command=command,
                   jump=jump, pmod=pmod, colr=colr, texture_offset=src * 8,
                   width=((size >> 8) & 63) * 8, height=size & 255,
                   color_mode=(pmod >> 3) & 7,
                   transparent_pixel_disabled=bool(pmod & 64), end_code_disabled=bool(pmod & 128),
                   flip_x=bool(ctrl & 16), flip_y=bool(ctrl & 32),
                   coordinate_words=list(words[6:14]), signed_coordinates=xy,
                   local_coordinate=list(local))
        rows.append(row)
        mode = jump & 3
        if mode == 0:
            pc += 32
        elif mode == 1:
            pc = link * 8
        elif mode == 2:
            if return_to is not None:
                raise TraceError(f"Nested call at {pc:#x}", rows, pc)
            return_to, pc = pc + 32, link * 8
        else:
            if return_to is None:
                raise TraceError(f"Return without call at {pc:#x}", rows, pc)
            pc, return_to = return_to, None
    raise TraceError("Command step budget exceeded", rows, pc)


def bind_textures(rows: list[dict], ram: bytes, source: bytes) -> list[dict]:
    """Match full packed bytes AND dimensions/depth; retain ambiguous IDs."""
    lookup = {}
    for rec in parse_v1n(source):
        key = (rec["width"], rec["height"], rec["bits_per_pixel"], rec["packed_sha256"])
        lookup.setdefault(key, []).append(rec["id"])
    bindings = []
    for row in rows:
        if row["kind"] != "command" or row["command"] not in (0, 1, 2):
            continue
        mode = row["color_mode"]
        depth = {0: 4, 1: 4, 2: 8, 3: 8, 4: 8, 5: 16}.get(mode)
        if depth is None or not row["width"] or not row["height"]:
            raise ValueError(f"Invalid texture mode/size at {row['offset']:#x}")
        start = row["texture_offset"]
        length = row["width"] * row["height"] * depth // 8
        if start + length > len(ram):
            raise ValueError(f"Texture outside RAM at {row['offset']:#x}")
        packed_hash = digest(ram[start:start + length])
        ids = lookup.get((row["width"], row["height"], depth, packed_hash), [])
        bindings.append({"command_offset": row["offset"], "texture_offset": start,
                         "packed_bytes": length, "packed_sha256": packed_hash,
                         "source_ids": ids, "width": row["width"], "height": row["height"],
                         "bits_per_pixel": depth, "color_mode": mode, "colr": row["colr"],
                         "status": "exact_source_binding" if ids else "unbound_texture"})
    return bindings


def run() -> dict:
    lock = read_json(PROJECT / "source-lock.json")
    source = verify_source(WORKSPACE, "work/extract/MAP001.V1N", lock["sources"]["work/extract/MAP001.V1N"])
    ram = verify_source(WORKSPACE, REFERENCE, REFERENCE_SHA256)
    failure = None
    try:
        rows = trace(ram)
    except TraceError as exc:
        rows = exc.rows
        failure = {"offset": exc.offset, "reason": str(exc)}
    bindings = bind_textures(rows, ram, source)
    summary = {"visited_commands": len(rows), "skipped_commands": sum(r["kind"] == "skip" for r in rows),
               "texture_commands": len(bindings), "bound_texture_commands": sum(bool(b["source_ids"]) for b in bindings),
               "unambiguous_bound_commands": sum(len(b["source_ids"]) == 1 for b in bindings),
               "ambiguous_bound_commands": sum(len(b["source_ids"]) > 1 for b in bindings),
               "distinct_source_candidates": len({i for b in bindings for i in b["source_ids"]}),
               "color_modes": dict(Counter(str(b["color_mode"]) for b in bindings)),
               "end_offset": rows[-1]["offset"] if rows and rows[-1]["kind"] == "end" else None,
               "list_status": "rejected_incomplete" if failure else "terminated"}
    result = {"schema": "ao_pc_vdp1_trace_v1", "capture": REFERENCE,
              "capture_sha256": digest(ram), "source_sha256": digest(source),
              "manual": MANUAL, "summary": summary, "failure": failure, "commands": rows, "bindings": bindings,
              "limits": ["Reachable list in an existing snapshot, not a new emulator execution trace.",
                         "Clipping, distortion, priority and transparency may prevent visible pixels.",
                         "No CRAM from this capture; never mix Ymir CRAM with this BizHawk snapshot.",
                         "No actor identities, animation timing, background layout or collision inferred."]}
    write_json(PROJECT / "reports/vdp1-trace.json", result)
    return result


def audit_captures() -> dict:
    """Inspect only explicitly locked inputs, never silently adopt new captures."""
    lock = read_json(PROJECT / "capture-lock.json")
    captures = []
    for path, expected in lock["sources"].items():
        data = verify_source(WORKSPACE, path, expected)
        item = {"path": path, "sha256": expected, "bytes": len(data)}
        if path.endswith(("VDP1_Ram.bin", "vdp1-vram.bin")):
            try:
                rows = trace(data)
                item.update(status="terminated", visited_commands=len(rows), end_offset=rows[-1]["offset"])
            except TraceError as exc:
                item.update(status="rejected_incomplete", visited_commands=len(exc.rows),
                            failure_offset=exc.offset, reason=str(exc))
        else:
            item.update(status="inventory_only", synchronization_verified=False)
        captures.append(item)
    report = {"schema": "ao_pc_capture_audit_v1", "captures": captures,
              "summary": dict(Counter(c["status"] for c in captures)),
              "requires": ["Same paused-frame screenshot, VDP1/VDP2 VRAM, CRAM and hardware registers.",
                           "VDP1 list start/current/end addresses and draw completion status.",
                           "Verify whether opcode 0xF is a deliberate termination dependency or a transient list.",
                           "VDP2 sprite type, color RAM mode/offset, layer and pattern table configuration."]}
    write_json(PROJECT / "reports/capture-audit.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(run()["summary"], indent=2))
    print(json.dumps(audit_captures()["summary"], indent=2))
