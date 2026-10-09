"""Verify real Ymir capture determinism and restart semantics against a local seed.

All inputs remain read-only; this creates a new output directory. No original game
data is embedded in the test. A passed result validates the backend, not collision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(executable: Path, ipl: Path, disc: Path, state: Path, root: Path,
        name: str, frames: int, sample_every: int = 1, trace: bool = True) -> Path:
    sequence = root / f"{name}-input.txt"
    sequence.write_text(f"none {frames}\n", encoding="ascii")
    output = root / name
    arguments = [str(executable), "--ipl", str(ipl), "--disc", str(disc),
                 "--load-state", str(state), "--sequence", str(sequence),
                 "--output", str(output), "--sample-every", str(sample_every)]
    if trace:
        arguments += ["--trace-function", "0x060AB61A", "--hook-pc", "0x06094AFC",
                      "--hook-pc", "0x060AA0DE", "--watch-range", "0x060C27AA:6"]
    result = subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=120)
    if not (output / "capture.json").exists():
        raise AssertionError(result.stdout + result.stderr)
    return output


def files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)).replace("\\", "/"): digest(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("executable", "ipl", "disc", "state", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source_inputs = {str(p.resolve()): digest(p) for p in (args.executable, args.ipl, args.disc, args.state)}
    outcomes = []
    runs = [run(args.executable, args.ipl, args.disc, args.state, root, f"repeat-{i}", 3) for i in range(3)]
    baseline = files(runs[0])
    for i, output in enumerate(runs[1:], 1):
        actual = files(output)
        differences = sorted(k for k in set(baseline) | set(actual) if baseline.get(k) != actual.get(k))
        outcomes.append({"test": f"repeat_{i}", "passed": not differences, "files": len(actual), "differences": differences})
    sparse = run(args.executable, args.ipl, args.disc, args.state, root, "sparse", 3, 1000000)
    untraced = run(args.executable, args.ipl, args.disc, args.state, root, "untraced", 3, trace=False)
    first = run(args.executable, args.ipl, args.disc, args.state, root, "split-first", 1)
    resumed = run(args.executable, args.ipl, args.disc, first / "frame-000001/state.savestate", root, "split-resumed", 2)
    final = runs[0] / "frame-000003"
    for name, folder in (("sampling_preserves_state", sparse / "frame-000003"),
                         ("tracing_preserves_non_audio_state", untraced / "frame-000003"),
                         ("resume_preserves_non_audio_state", resumed / "frame-000002")):
        # Counters in JSON are run-relative. Compare actual machine state and pixels.
        names = [p.name for p in final.iterdir() if p.is_file() and p.suffix != ".json"]
        differences = [n for n in names if digest(final / n) != digest(folder / n)]
        expected_state = (final / "state.savestate").read_bytes()
        actual_state = (folder / "state.savestate").read_bytes()
        # v13 has explicit tagged section boundaries. Keep complete-state results
        # visible: Ymir's audio state can differ after LoadState/debug-mode changes.
        assert expected_state.count(b"SCSP") == actual_state.count(b"SCSP") == 1
        assert expected_state.count(b"CD##") == actual_state.count(b"CD##") == 1
        start, end = expected_state.index(b"SCSP"), expected_state.index(b"CD##")
        non_audio_equal = (len(expected_state) == len(actual_state)
                           and actual_state.index(b"SCSP") == start and actual_state.index(b"CD##") == end
                           and expected_state[:start] == actual_state[:start]
                           and expected_state[end:] == actual_state[end:])
        complete_required = name == "sampling_preserves_state"
        passed = not differences if complete_required else non_audio_equal and set(differences) <= {"state.savestate"}
        outcomes.append({"test": name, "passed": passed, "files": len(names), "differences": differences,
                         "complete_state_equal": expected_state == actual_state,
                         "non_audio_state_equal": non_audio_equal,
                         "audio_state_differing_bytes": sum(a != b for a, b in zip(expected_state[start:end], actual_state[start:end]))})
    for name, sequence in (("reject_diagonal", "up+right 1\n"), ("reject_zero", "none 0\n"),
                           ("reject_negative", "none -1\n"), ("reject_trailing", "none 1 extra\n")):
        path = root / f"{name}.txt"
        path.write_text(sequence, encoding="ascii")
        output = root / name
        result = subprocess.run([str(args.executable), "--ipl", str(args.ipl), "--disc", str(args.disc),
                                 "--sequence", str(path), "--output", str(output)], capture_output=True, text=True, timeout=30)
        outcomes.append({"test": name, "passed": result.returncode != 0 and not output.exists()})
    source_unchanged = all(digest(Path(path)) == expected for path, expected in source_inputs.items())
    passed = source_unchanged and all(row["passed"] for row in outcomes)
    report = {"schema": "ao_ymir_capture_backend_test_v1", "passed": passed,
              "source_inputs_sha256": source_inputs, "source_inputs_unchanged": source_unchanged,
              "tests": outcomes, "limit": "Three neutral frames on one local seed; not gameplay, collision, or source-map acceptance. Across debug-mode changes/reloads, audio phase is explicitly outside parity acceptance; every changed byte must remain inside the SCSP section. Identical seed/configuration replays require all bytes equal."}
    (root / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
