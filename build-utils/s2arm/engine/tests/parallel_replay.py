#!/usr/bin/env python3
"""Targeted candidate matrix on the host Metal fixture. Run from the prepared engine tree."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


FLAGS = ("S2A_RB_REC_EARLY", "S2A_RB_REPLAY_WORKER", "S2A_RB_REPLAY_SCALAR_QUERIES", "S2A_RB_PARALLEL_TRACE")
ARMS = {"baseline": (0, 0, 0, 0), "early": (1, 0, 0, 0), "worker": (0, 1, 0, 0),
        "worker_scalar": (0, 1, 1, 0), "combined": (1, 1, 1, 0), "combined_trace": (1, 1, 1, 1),
        "baseline_trace": (0, 0, 0, 1)}
FRAMES = 3
ROUNDS = 4


def ordered_trace(path, expected_barriers):
    counts = Counter()
    records = []
    frame = None
    for line in path.read_text().splitlines():
        tag = line.split(maxsplit=1)[0]
        if tag == "F":
            frame = int(line.split()[1])
        if tag == "S":
            counts[frame] += 1
        # Include boundaries, pass begins/ends, draw, dispatch, ordered barriers and consumed masks.
        if tag not in ("F", "P", "E", "D", "K", "S"):
            raise ValueError(f"unknown record {tag} in {path}")
        records.append(line)
    if counts != {f: expected_barriers for f in range(1, FRAMES + 1)}:
        raise ValueError(f"barrier trace does not match per-frame engine counters: {counts}")
    return records


def validate(out):
    baseline = None
    results = {}
    diag = json.loads((out / "diagnostic-metrics.json").read_text())
    measured = json.loads((out / "metrics.json").read_text())
    for name, (_, worker, _, tracing) in ARMS.items():
        metrics = diag[name]
        barrier_count = metrics["barriers_fences"]
        if barrier_count <= 0 or barrier_count != int(barrier_count):
            raise ValueError(f"invalid barrier/fence count {barrier_count}")
        trace = ordered_trace(out / f"{name}.diagnostic.trace", int(barrier_count))
        if name == "baseline":
            baseline = trace
        elif trace != baseline:
            raise ValueError(f"{name}: ordered render/dispatch/barrier stream differs from baseline")
        cb_counts = []
        for run in ("diagnostic", *range(ROUNDS)):
            log = (out / f"{name}.{run}.log").read_text(errors="replace")
            if f"CANDIDATE worker_seen={worker} scalar_checks={FRAMES+1}" not in log.splitlines():
                raise ValueError(f"{name}.{run}: expected worker/scalar observation missing")
            events = [s for s in log.splitlines() if "[rb-parallel] v=1 " in s]
            begins = sum(" event=begin " in s for s in events)
            cbs = sum(" event=cb " in s for s in events)
            if (tracing and (begins != 1 or not cbs)) or (not tracing and events):
                raise ValueError(f"{name}.{run}: trace enable state differs; begins={begins}, cbs={cbs}")
            if tracing:
                frames = {int(re.search(r" frame=([0-9]+) ", s).group(1)) for s in events if " event=cb " in s}
                if not set(range(1, FRAMES + 1)).issubset(frames):
                    raise ValueError(f"{name}.{run}: missing measured frame IDs in callbacks: {frames}")
            if any(" status=error" in s for s in events):
                raise ValueError(f"{name}.{run}: GPU feedback error")
            cb_counts.append(cbs)
        if any(m["barriers_fences"] != barrier_count for m in measured[name]):
            raise ValueError(f"{name}: unstable barrier count with fixture trace disabled")
        results[name] = dict(backend=metrics["backend"], barriers_per_frame=barrier_count,
                             diagnostic_order_sha256=hashlib.sha256(("\n".join(trace)+"\n").encode()).hexdigest(),
                             draw_state_digest=metrics["draw_state_digest"], pixel_digest=metrics["pixel_digest"],
                             worker_seen=worker, scalar_checks_per_process=FRAMES+1, trace_cb_callbacks=cb_counts)
    (out / "parallel-validation.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = out / "candidate-variants.txt"
    plan.write_text("".join(name+" "+" ".join(f"{k}={v}" for k, v in zip(FLAGS, values))+"\n"
                            for name, values in ARMS.items()))
    env = {**os.environ, "RBM_PARALLEL_REPLAY": "1", "S2A_RB_PARALLEL_FROM": "0"}
    subprocess.run([sys.executable, here / "replay_compare.py", args.binary.resolve(), plan, out, str(FRAMES),
                    str(ROUNDS), "--timeout", "90"], env=env, check=True)
    validate(out)
    # Complement the single-queue replay with the existing signal/wait fixture, compiled once.
    xqueue = Path("build/tests/t_nvn_xqueue")
    subprocess.run(["make", "-j4", "-f", "Makefile", "-f", here / "host-tests.mk", xqueue], check=True)
    for mode in (0, 1):
        run = subprocess.run([xqueue.resolve()], env={**os.environ, "DM_NVN_ENC_THREAD": "1", "S2A_RB_XQ_RESUME": str(mode)},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        (out / f"xqueue-encode1-resume{mode}.log").write_bytes(run.stdout)
        run.check_returncode()
        summary = re.search(r"✓ t_nvn_xqueue：\d+ 项全过[^\n]*", run.stdout.decode(errors="replace"))
        if not summary:
            raise ValueError(f"xqueue {mode}: missing executed assertion summary")
        print(f"resume={mode} {summary.group()}", flush=True)


if __name__ == "__main__":
    main()
