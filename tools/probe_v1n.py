"""Recompute V1N layout and exact packed-byte matches against an existing RAM capture."""
from collections import Counter
from pathlib import Path
import json
import struct

from pipeline import PROJECT, WORKSPACE, digest, parse_v1n, read_json, verify_source, write_json


def run() -> dict:
    lock = read_json(PROJECT / "source-lock.json")
    raw = verify_source(WORKSPACE, "work/extract/MAP001.V1N", lock["sources"]["work/extract/MAP001.V1N"])
    capture = WORKSPACE / "work/bizhawk/dialogue_state_dumps/ascii_proof_page_01/VDP1_Ram.bin"
    # Existing capture hash published in the original LZSS study, independent of this decoder.
    expected_ram = "9f0f7685f0e86aa1032a42dda1656ab841084432a0a765ac926f25e4cf74088e"
    ram = capture.read_bytes()
    if digest(ram) != expected_ram:
        raise ValueError("Reference RAM snapshot changed")
    rows = []
    for record in parse_v1n(raw):
        packed = raw[record["payload_offset"]:record["offset"] + record["span"]]
        locations = []
        if len(set(packed)) >= 4:
            start = ram.find(packed)
            while start >= 0:
                locations.append(start)
                start = ram.find(packed, start + 1)
        rows.append({k: record[k] for k in ("id", "offset", "span", "width", "height", "bits_per_pixel", "packed_sha256")}
                    | {"vdp1_offsets": locations, "status": "exact_snapshot_bytes" if locations else "not_matched_or_low_information"})
    survey = []
    for source in sorted((WORKSPACE / "work/extract").glob("*.V1N")):
        data = source.read_bytes()
        item = {"file": source.name, "bytes": len(data), "sha256": digest(data)}
        try:
            records = parse_v1n(data)
            item.update(status="complete_structural_parse", records=len(records),
                        depths=dict(Counter(str(r["bits_per_pixel"]) for r in records)))
        except ValueError as exc:
            item.update(status="unsupported_layout", reason=str(exc))
        survey.append(item)
    report = {"schema": "ao_pc_v1n_evidence_v1", "source_sha256": digest(raw),
              "capture": str(capture.relative_to(WORKSPACE)).replace("\\", "/"), "capture_sha256": digest(ram),
              "summary": {"map001_records": len(rows), "exact_snapshot_matches": sum(bool(r["vdp1_offsets"]) for r in rows),
                          "survey_files": len(survey), "complete_parses": sum(r["status"] == "complete_structural_parse" for r in survey)},
              "records": rows, "survey": survey,
              "limits": ["Existing captured RAM evidence, not a new emulator run.",
                         "Matching uploaded packed bytes does not prove active draw commands, colors, actor identity or animation.",
                         "SNF map layering, collision and event entry are not established by V1N parsing."]}
    write_json(PROJECT / "reports/v1n-evidence.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(run()["summary"], indent=2))
