"""Archive a new Ymir capture without replacing the historical fixture.

This is an offline custody tool, not an emulator controller. File hashes and
decoded section boundaries can pass; a claimed pause or frame number cannot
establish synchronized sampling or repeatability by itself.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import struct
import sys

from PIL import Image

from pipeline import PROJECT, digest
from probe_scene_metadata import system_ram
from read_ymir_state import extract


SCHEMA = "ao_pc_exploration_capture_v1"
METADATA_SCHEMA = "ao_pc_exploration_observations_v1"
SOURCES_SCHEMA = "ao_pc_exploration_sources_v1"
LOCK_NAME = "capture-lock.json"
FILES = {"snapshot.savestate", "screen.png", "observations.json"}
OBSERVATIONS = {"paused", "emulator_frame", "player_update", "synchronization"}
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
# The names are the existing v13 reader's register order, not a fixture identity.
REGISTERS2 = """TVMD EXTEN TVSTAT VRSIZE HCNT VCNT RAMCTL CYCA0L CYCA0U
CYCA1L CYCA1U CYCB0L CYCB0U CYCB1L CYCB1U BGON MZCTL SFSEL SFCODE CHCTLA
CHCTLB BMPNA BMPNB PNCNA PNCNB PNCNC PNCND PNCR PLSZ MPOFN MPOFR MPABN0 MPCDN0
MPABN1 MPCDN1 MPABN2 MPCDN2 MPABN3 MPCDN3 MPABRA MPCDRA MPEFRA MPGHRA MPIJRA
MPKLRA MPMNRA MPOPRA MPABRB MPCDRB MPEFRB MPGHRB MPIJRB MPKLRB MPMNRB MPOPRB
SCXIN0 SCXDN0 SCYIN0 SCYDN0 ZMXIN0 ZMXDN0 ZMYIN0 ZMYDN0 SCXIN1 SCXDN1 SCYIN1
SCYDN1 ZMXIN1 ZMXDN1 ZMYIN1 ZMYDN1 SCXIN2 SCYIN2 SCXIN3 SCYIN3 ZMCTL SCRCTL
VCSTAU VCSTAL LSTA0U LSTA0L LSTA1U LSTA1L LCTAU LCTAL BKTAU BKTAL RPMD RPRCTL
KTCTL KTAOF OVPNRA OVPNRB RPTAU RPTAL WPSX0 WPSY0 WPEX0 WPEY0 WPSX1 WPSY1
WPEX1 WPEY1 WCTLA WCTLB WCTLC WCTLD LWTA0U LWTA0L LWTA1U LWTA1L SPCTL SDCTL
CRAOFA CRAOFB LNCLEN SFPRMD CCCTL SFCCMD PRISA PRISB PRISC PRISD PRINA PRINB
PRIR CCRSA CCRSB CCRSC CCRSD CCRNA CCRNB CCRR CCRLB CLOFEN CLOFSL COAR COAG
COAB COBR COBG COBB""".split()


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read_json_bytes(raw: bytes) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=no_duplicates)
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def stable_read(path: Path) -> bytes:
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != after.st_size:
        raise ValueError(f"Source changed while reading: {path}")
    return raw


def stable_fingerprint(path: Path) -> dict:
    """Hash large disc tracks without retaining them, detecting concurrent writes."""
    def identity(stat):
        # Python 3.13 on Windows exposes different ctime meanings via stat/fstat.
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    path = path.resolve()
    path.stat()  # Explicit existence check; strict resolve needs extra Windows handle rights.
    if not path.is_file():
        raise ValueError(f"Source must be a regular file: {path}")
    before = path.stat()
    hasher, count = hashlib.sha256(), 0
    with path.open("rb") as handle:
        before_handle = os.fstat(handle.fileno())
        if identity(before_handle) != identity(before):
            raise ValueError(f"Source changed while opening: {path}")
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
            count += len(block)
        after_handle = os.fstat(handle.fileno())
    after = path.stat()
    if (identity(before) != identity(after_handle) or identity(before) != identity(after)
            or before.st_ctime_ns != after.st_ctime_ns
            or before_handle.st_ctime_ns != after_handle.st_ctime_ns or count != before.st_size):
        raise ValueError(f"Source changed while hashing: {path}")
    return {"path": str(path), "size": count, "sha256": hasher.hexdigest()}


def cue_tracks(cue: Path, raw: bytes) -> list[tuple[str, Path]]:
    """Resolve every FILE entry; CUE references cannot leave its directory tree."""
    cue = cue.resolve()
    root = cue.parent
    tracks = []
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not re.match(r"^\s*FILE(?:\s|$)", line, re.IGNORECASE):
            continue
        match = re.fullmatch(r'\s*FILE\s+(?:"([^"]+)"|(\S+))\s+BINARY\s*', line, re.IGNORECASE)
        if match is None:
            raise ValueError(f"Unsupported or malformed BINARY CUE FILE entry at line {line_number}")
        reference = match.group(1) or match.group(2)
        windows = PureWindowsPath(reference)
        parts = reference.replace("\\", "/").split("/")
        if windows.drive or windows.root or any(part in {"", ".", ".."} for part in parts) or ":" in reference:
            raise ValueError(f"CUE path must be relative and cannot traverse directories: {reference}")
        if windows.suffix.lower() != ".bin":
            raise ValueError(f"Only source-bound BIN track files are supported: {reference}")
        candidate = root
        for part in parts:
            candidate = candidate / part
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"CUE track cannot traverse symbolic links or junctions: {reference}")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"CUE track escaped its directory or is not a file: {reference}")
        tracks.append((reference, resolved))
    if not tracks:
        raise ValueError("CUE has no BINARY BIN FILE references")
    return tracks


def source_records(cue: Path, bios: Path, ymir: Path, config: Path,
                   harness: Path | None = None, source_manifest: Path | None = None) -> dict:
    paths = {"cue": cue, "bios": bios, "ymir": ymir, "config": config}
    if harness is not None:
        paths["harness"] = harness
    if source_manifest is not None:
        paths["source_manifest"] = source_manifest
    inputs = {role: stable_fingerprint(path) for role, path in paths.items()}
    cue_path = Path(inputs["cue"]["path"])
    cue_raw = stable_read(cue_path)
    if digest(cue_raw) != inputs["cue"]["sha256"]:
        raise ValueError("CUE changed while discovering track sources")
    tracks = [{"cue_reference": reference, **stable_fingerprint(path)} for reference, path in cue_tracks(cue_path, cue_raw)]
    build_metadata = None
    if source_manifest is not None:
        raw = stable_read(Path(inputs["source_manifest"]["path"]))
        if digest(raw) != inputs["source_manifest"]["sha256"]:
            raise ValueError("Build source manifest changed during intake")
        build_metadata = read_json_bytes(raw)
    # A second complete pass catches writes to an early track during later I/O.
    for record in [*inputs.values(), *tracks]:
        expected = {key: record[key] for key in ("path", "size", "sha256")}
        if stable_fingerprint(Path(record["path"])) != expected:
            raise ValueError(f"Source changed during provenance intake: {record['path']}")
    return {"inputs": inputs, "disc_files": tracks, "build_metadata": build_metadata}


def pin_sources(cue: Path, bios: Path, ymir: Path, config: Path, out: Path,
                harness: Path | None = None, source_manifest: Path | None = None) -> dict:
    out = out.resolve()
    if out.exists():
        raise ValueError("Source pin already exists; use a new manifest name")
    records = source_records(cue, bios, ymir, config, harness, source_manifest)
    manifest = {"schema": SOURCES_SCHEMA, "pinned_at_utc": datetime.now(timezone.utc).isoformat(),
                **records, "limits": [
                    "Hashes bind local input bytes; they do not prove that a running emulator loaded them.",
                    "Build metadata is retained as supplied; no binary-to-source reproducible-build claim.",
                    "A source pin does not establish synchronized capture or deterministic replay."]}
    raw = json_bytes(manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as handle:
        handle.write(raw)
    return {"source_manifest": str(out), "manifest_sha256": digest(raw),
            "source_integrity": "passed", "disc_files": len(records["disc_files"]),
            "harness_pinned": harness is not None, "build_metadata_pinned": source_manifest is not None,
            "e1_passed": False}


def verify_sources(manifest_path: Path, expected_manifest_sha256: str | None = None) -> dict:
    raw = stable_read(manifest_path)
    manifest_sha = digest(raw)
    if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
        raise ValueError("Source manifest SHA256 mismatch")
    manifest = read_json_bytes(raw)
    if manifest.get("schema") != SOURCES_SCHEMA:
        raise ValueError("Expected an independent exploration source manifest")
    inputs = manifest.get("inputs", {})
    required = {"cue", "bios", "ymir", "config"}
    optional = {"harness", "source_manifest"}
    if not isinstance(inputs, dict) or not required <= inputs.keys() or inputs.keys() - required - optional:
        raise ValueError("Source manifest roles are missing or unexpected")
    paths = {}
    for role, record in inputs.items():
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise ValueError(f"Malformed source identity: {role}")
        path = Path(record["path"])
        if not path.is_absolute():
            raise ValueError(f"Pinned source paths must be absolute: {role}")
        paths[role] = path
    current = source_records(**paths)
    if any(current[key] != manifest.get(key) for key in ("inputs", "disc_files", "build_metadata")):
        raise ValueError("Pinned source bytes, CUE references or build metadata changed")
    return {"source_manifest": str(manifest_path.resolve()), "manifest_sha256": manifest_sha,
            "source_integrity": "passed", "disc_files": len(current["disc_files"]),
            "harness_pinned": "harness" in inputs, "build_metadata_pinned": "source_manifest" in inputs,
            "e1_passed": False}


def validate_metadata(metadata: dict) -> None:
    if metadata.get("schema") != METADATA_SCHEMA:
        raise ValueError("Expected exploration observations schema, not a legacy fixture lock")
    if not isinstance(metadata.get("profile"), str) or not metadata["profile"].strip():
        raise ValueError("A named source profile is required")
    tool = metadata.get("tool", {})
    if not isinstance(tool, dict) or tool.get("name") != "Ymir" or not tool.get("version"):
        raise ValueError("Ymir tool name and version are required")
    if not re.fullmatch(r"[0-9a-f]{64}", str(tool.get("executable_sha256", ""))):
        raise ValueError("Ymir executable SHA256 is required")
    observations = metadata.get("observations")
    if not isinstance(observations, dict) or not OBSERVATIONS <= observations.keys():
        raise ValueError("Pause, emulator_frame, player_update and synchronization observations are required")
    for name, observation in observations.items():
        if not isinstance(observation, dict):
            raise ValueError(f"Invalid observation: {name}")
        status = observation.get("status")
        if status == "unknown":
            if observation.get("value") is not None or not observation.get("reason"):
                raise ValueError(f"Unknown {name} needs a reason and null value")
        elif status == "observed":
            if observation.get("value") is None or not observation.get("evidence"):
                raise ValueError(f"Observed {name} needs a value and evidence description")
            value = observation["value"]
            if name == "paused" and type(value) is not bool:
                raise ValueError("Observed paused must be a Boolean")
            if name in {"emulator_frame", "player_update"} and (type(value) is not int or value < 0):
                raise ValueError(f"Observed {name} must be a nonnegative integer")
        else:
            raise ValueError(f"Observation {name} must be observed or unknown; assertions are not proof")


def inspect_snapshot(raw: bytes) -> dict:
    if raw[:5] != b"\x01\x0d\0\0\0" or raw.count(b"VDP#") != 1:
        raise ValueError("A unique Ymir little-endian v13 VDP boundary is required")
    offset = raw.index(b"VDP#") + 4
    # extract() reads these fixed blocks plus the beginning of renderer state.
    minimum = 0x181000 + 16 + 20 + 284 + 8 + 14 + 8 + 3
    if offset < 9 or offset + minimum > len(raw):
        raise ValueError("Truncated VDP memory/register/renderer prefix")
    parser_lock = {"version": 13, "size": len(raw), "sha256": digest(raw),
                   "vdp_payload_offset": offset, "registers2": REGISTERS2}
    try:
        vdp = extract(raw, parser_lock)
        low, high, ram = system_ram(raw, parser_lock)
    except (struct.error, IndexError, KeyError) as exc:
        raise ValueError("Malformed supported save-state section") from exc
    if ram["high_state_offset"] + len(high) + 4 > offset - 4:
        raise ValueError("System RAM overlaps the VDP section")
    spans = dict(vdp["spans"])
    spans["wram_low"] = {"offset": ram["low_state_offset"], "size": len(low),
                         "sha256": ram["low_sha256"]}
    spans["wram_high"] = {"offset": ram["high_state_offset"], "size": len(high),
                          "sha256": ram["high_sha256"]}
    return {"parser_lock": parser_lock, "regions": spans,
            "vdp_state": {key: vdp[key] for key in (
                "regs1", "regs2", "display_framebuffer", "drawing", "next_command_address",
                "hphase", "vphase", "timing_penalty", "fbcr_changed", "vcnt_latch")}}


def inspect_png(raw: bytes) -> dict:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Screenshot must be a PNG")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 33_554_432:
                raise ValueError("Screenshot exceeds 32 megapixels")
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            return {"width": image.width, "height": image.height, "mode": image.mode}
    except (OSError, SyntaxError) as exc:
        raise ValueError("Corrupt or truncated PNG") from exc


def assessment(metadata: dict) -> dict:
    return {"archive_integrity": "passed", "supported_region_boundaries": "passed",
            "observations": {name: value["status"] for name, value in metadata["observations"].items()},
            "synchronized_sampling": "unknown", "repeatable_replay": "unknown", "e1_passed": False,
            "limits": ["Only the documented v13 WRAM and VDP prefixes were parsed; not a full save-state validator.",
                       "Observed values are supplied capture notes, not independently verified emulator counters.",
                       "File identity cannot prove simultaneous screenshot/state sampling or deterministic replay.",
                       "Pin the manifest SHA256 outside this directory to detect replacement of the entire archive."]}


def ingest(capture_id: str, snapshot: Path, screenshot: Path, metadata_path: Path,
           output_root: Path | None = None) -> dict:
    if not ID_PATTERN.fullmatch(capture_id):
        raise ValueError("Capture id must be 1-80 lowercase letters, digits, underscores or hyphens")
    output_root = (output_root or PROJECT / "reports/exploration/captures").resolve()
    destination = output_root / capture_id
    if destination.exists():
        raise ValueError("Capture already exists; archived captures cannot be overwritten")
    paths = {"snapshot.savestate": snapshot.resolve(), "screen.png": screenshot.resolve(),
             "observations.json": metadata_path.resolve()}
    contents = {name: stable_read(path) for name, path in paths.items()}
    metadata = read_json_bytes(contents["observations.json"])
    validate_metadata(metadata)
    inspected = inspect_snapshot(contents["snapshot.savestate"])
    screenshot_info = inspect_png(contents["screen.png"])
    # Catch an emulator writing a later state while the other files were read.
    for name, path in paths.items():
        if stable_read(path) != contents[name]:
            raise ValueError(f"Source changed during capture intake: {path}")
    lock = {"schema": SCHEMA, "capture_id": capture_id,
            "archived_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": {name: {"size": len(raw), "sha256": digest(raw)} for name, raw in contents.items()},
            "source_paths": {name: str(path) for name, path in paths.items()},
            "snapshot": inspected, "screenshot": screenshot_info, "assessment": assessment(metadata)}
    manifest = json_bytes(lock)
    output_root.mkdir(parents=True, exist_ok=True)
    destination.mkdir()  # No overwrite, including competing intakes with this id.
    for name, raw in {**contents, LOCK_NAME: manifest,
                      "capture-lock.sha256": (digest(manifest) + "\n").encode("ascii")}.items():
        with (destination / name).open("xb") as handle:
            handle.write(raw)
    return verify(destination, digest(manifest))


def verify(capture_dir: Path, expected_manifest_sha256: str | None = None) -> dict:
    capture_dir = capture_dir.resolve()
    if {entry.name for entry in capture_dir.iterdir()} != FILES | {LOCK_NAME, "capture-lock.sha256"}:
        raise ValueError("Capture file set changed or the archive is incomplete")
    if any(entry.is_symlink() or not entry.is_file() for entry in capture_dir.iterdir()):
        raise ValueError("Capture entries must be regular files, not links")
    raw_lock = stable_read(capture_dir / LOCK_NAME)
    manifest_sha = digest(raw_lock)
    sidecar = (capture_dir / "capture-lock.sha256").read_text(encoding="ascii").strip()
    if manifest_sha != sidecar or (expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256):
        raise ValueError("Capture manifest SHA256 mismatch")
    lock = read_json_bytes(raw_lock)
    if lock.get("schema") != SCHEMA or lock.get("capture_id") != capture_dir.name:
        raise ValueError("Not an independent exploration capture lock for this directory")
    if set(lock.get("files", {})) != FILES:
        raise ValueError("Unexpected capture manifest files")
    contents = {}
    for name in sorted(FILES):
        raw = stable_read(capture_dir / name)
        if lock["files"][name] != {"size": len(raw), "sha256": digest(raw)}:
            raise ValueError(f"Capture file identity changed: {name}")
        contents[name] = raw
    metadata = read_json_bytes(contents["observations.json"])
    validate_metadata(metadata)
    if inspect_snapshot(contents["snapshot.savestate"]) != lock.get("snapshot"):
        raise ValueError("Independent parser lock or region records changed")
    if inspect_png(contents["screen.png"]) != lock.get("screenshot"):
        raise ValueError("Screenshot metadata changed")
    if assessment(metadata) != lock.get("assessment"):
        raise ValueError("Capture assessment was substituted or promoted without evidence")
    return {"capture_directory": str(capture_dir), "manifest_sha256": manifest_sha,
            "snapshot_sha256": lock["files"]["snapshot.savestate"]["sha256"],
            **lock["assessment"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    intake = commands.add_parser("ingest", help="Create a new immutable-by-tool capture directory")
    intake.add_argument("--id", required=True, dest="capture_id")
    intake.add_argument("--snapshot", required=True, type=Path)
    intake.add_argument("--screenshot", required=True, type=Path)
    intake.add_argument("--metadata", required=True, type=Path)
    intake.add_argument("--output-root", type=Path)
    check = commands.add_parser("verify", help="Verify a local archive without accessing the original files")
    check.add_argument("capture_dir", type=Path)
    check.add_argument("--manifest-sha256")
    sources = commands.add_parser("pin-sources", help="Pin CUE, every BIN track, BIOS, executables and configuration")
    for name in ("cue", "bios", "ymir", "config", "out"):
        sources.add_argument(f"--{name}", required=True, type=Path)
    sources.add_argument("--harness", type=Path, help="Optional until the capture harness has been built")
    sources.add_argument("--source-manifest", type=Path, help="JSON describing source revision and build configuration")
    source_check = commands.add_parser("verify-sources", help="Rehash every input from a pinned source manifest")
    source_check.add_argument("manifest", type=Path)
    source_check.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            result = ingest(args.capture_id, args.snapshot, args.screenshot, args.metadata, args.output_root)
        elif args.command == "verify":
            result = verify(args.capture_dir, args.manifest_sha256)
        elif args.command == "pin-sources":
            result = pin_sources(args.cue, args.bios, args.ymir, args.config, args.out,
                                 args.harness, args.source_manifest)
        else:
            result = verify_sources(args.manifest, args.manifest_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Capture rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
