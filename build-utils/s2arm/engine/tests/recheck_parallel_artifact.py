#!/usr/bin/env python3
"""Recheck macOS Metal replay outputs without rebuilding or writing to the original artifact."""
import argparse
from contextlib import nullcontext, redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import zipfile

from parallel_replay import ARMS, FRAMES, validate
from replay_sync_oracle import verify_negative_controls


PROFILES = (("default", Path("parallel-replay"), 4), ("fixed", Path("parallel-replay/fixed-cuts"), 3))


def input_files():
    paths = [Path(f"parallel-encode-{k}.txt") for k in (0, 1)] + [Path("parallel-gpu-halt.txt")]
    paths += [Path(f"parallel-replay/xqueue-encode1-resume{k}.log") for k in (0, 1)]
    for _, profile, rounds in PROFILES:
        paths.extend(profile / name for name in ("metrics.json", "diagnostic-metrics.json", "times.json",
                                                 "validation.json", "candidate-variants.txt"))
        for arm in ARMS:
            paths.append(profile / f"{arm}.diagnostic.trace")
            paths.extend(profile / f"{arm}.{run}.log" for run in ("diagnostic", *range(rounds)))
    return sorted(paths)


def copy_inputs(source, dest):
    digest = hashlib.sha256()
    with (zipfile.ZipFile(source) if source.is_file() else nullcontext()) as archive:
        for name in input_files():
            key = name.as_posix()
            if archive and archive.namelist().count(key) != 1:
                raise ValueError(f"missing or duplicate artifact member {key}")
            data = archive.read(key) if archive else (source / name).read_bytes()
            digest.update(key.encode() + b"\0" + hashlib.sha256(data).digest())
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return digest.hexdigest()


def line_after(content, prefix):
    rows = [row[len(prefix):] for row in content.splitlines() if row.startswith(prefix)]
    if len(rows) != 1:
        raise ValueError(f"expected a single {prefix.strip()} record")
    return rows[0]


def read_json(path):
    return json.loads(path.read_text())


def check_processes(folder, rounds):
    diag, metrics, times, errors = [read_json(folder / f"{key}.json")
                                    for key in ("diagnostic-metrics", "metrics", "times", "validation")]
    if any(set(d) != set(ARMS) for d in (diag, metrics, times, errors)) or any(errors.values()):
        raise ValueError("missing arms or upstream replay comparison failure")
    expected = ("Metal3", 1, FRAMES, 1, 372, 1, "f2c8d5939b7f046b", "22f104742e837afc")
    metrics_keys = ("backend", "enc_thread", "frames", "exec_equals_put", "draws", "dispatches",
                    "pixel_digest", "draw_state_digest")
    for arm in ARMS:
        if len(metrics[arm]) != rounds or set(times[arm]) != {str(i) for i in range(rounds)}:
            raise ValueError(f"{arm}: incomplete rounds")
        for run in ("diagnostic", *range(rounds)):
            log = (folder / f"{arm}.{run}.log").read_text()
            raw = json.loads(line_after(log, "METRICS "))
            if raw != (diag[arm] if run == "diagnostic" else metrics[arm][run]):
                raise ValueError(f"{arm}.{run}: summary disagrees with original process output")
            if tuple(raw[k] for k in metrics_keys) != expected:
                raise ValueError(f"{arm}.{run}: unexpected backend, workload or state/pixel digest")
            ms = [float(value) for value in line_after(log, "TIMES ").split()]
            if len(ms) != FRAMES or not all(math.isfinite(v) and v > 0 for v in ms):
                raise ValueError(f"{arm}.{run}: invalid frame times")
            if run != "diagnostic" and ms != times[arm][str(run)]:
                raise ValueError(f"{arm}.{run}: saved times differ")
    return len(ARMS)*(rounds+1)


def require_checks(path, count, witnesses):
    log = path.read_text()
    if sum(s.startswith("PASS ") for s in log.splitlines()) != count or any(
            s.startswith(("FAIL ", "SETUP FAIL", "✗")) for s in log.splitlines()):
        raise ValueError(f"{path.name}: incomplete or failed checks")
    for witness in witnesses:
        if witness not in log:
            raise ValueError(f"{path.name}: missing {witness!r}")
    return count


def native_checks(folder):
    results = {}
    for mode, witness in enumerate(("control keeps all 65 records private", "consumes exactly the 64 complete records")):
        results[f"encode_{mode}"] = require_checks(folder / f"parallel-encode-{mode}.txt", 7,
                                                  ("Encode worker checks: 7/7", witness))
        results[f"xqueue_{mode}"] = require_checks(folder / f"parallel-replay/xqueue-encode1-resume{mode}.log", 14,
                                                   ("✓ t_nvn_xqueue：14 项全过", f"mode={mode}", "order verified by readback",
                                                    "Direct vertex-pool lifetime fixture requires Metal 4 residency sets"))
    results["gpu_halt"] = require_checks(folder / "parallel-gpu-halt.txt", 28, (
        "real Metal 3 queue, empty command buffers on Apple Paravirtual device",
        "future GPU timestamp is neither charged nor classified as a hang",
        "three long frames in ten seconds trigger the GPU halt", "real pre-halt command buffer completed",
        "refused present does not register a drawable", "✓ t_nvn_gpu_halt：全过"))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="original upload ZIP or extracted artifact directory")
    parser.add_argument("output", type=Path, help="separate directory for the recheck evidence")
    parser.add_argument("--sha256", help="also require this exact digest of the original ZIP")
    parser.add_argument("--inputs-sha256", help="optional known digest of the selected filenames and content hashes")
    args = parser.parse_args()
    archive_digest = hashlib.sha256(args.artifact.read_bytes()).hexdigest() if args.artifact.is_file() else None
    if args.sha256 and archive_digest != args.sha256:
        parser.error("ZIP digest differs (for an extracted directory omit --sha256)")
    verify_negative_controls()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest = copy_inputs(args.artifact, root)
        if args.inputs_sha256 and manifest != args.inputs_sha256:
            raise ValueError(f"selected inputs differ from the authenticated capture: {manifest}")
        evidence = dict(inputs_sha256=manifest, archive_sha256=archive_digest, input_files=len(input_files()),
                        native_checks=native_checks(root), profiles={})
        outputs = {}
        for label, profile, rounds in PROFILES:
            folder = root / profile
            runs = check_processes(folder, rounds)
            with redirect_stdout(io.StringIO()):
                validate(folder, label == "fixed", rounds)
            report = read_json(folder / "parallel-validation.json")
            evidence["profiles"][label] = dict(processes=runs, measured_or_diagnostic_frames=runs*FRAMES,
                pass_cuts=sum(sum(sum(frame_counts) for frame_counts in a["pass_cuts_by_run"]) for a in report.values()),
                strengthened_waits=sum(len(frame) for a in report.values() for run in a["strengthened_wait_ordinals_by_run"] for frame in run))
            outputs[label] = report
        args.output.mkdir(parents=True, exist_ok=True)
        for name, obj in {**outputs, "recheck": evidence}.items():
            (args.output / f"{name}.json").write_text(json.dumps(obj, indent=2)+"\n")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
