#!/usr/bin/env python3
"""Compare a synthetic NVN replay against its baseline (one process per run).
Usage: replay_compare.py binary variants output_dir [frames] [repeats] [--timeout seconds]

One diagnostic run per variant records a trace. Separate untraced, rotating
rounds measure submit-to-queue-finish latency with one queue finish per frame.
Digest checks include both modes. Pass-inclusive state_digest is retained for
diagnosis; only draw/dispatch state and pixel digests must match the baseline.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
from itertools import zip_longest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("binary", type=Path)
parser.add_argument("variants", type=Path)
parser.add_argument("out", type=Path)
parser.add_argument("frames", type=int, nargs="?", default=3)
parser.add_argument("repeats", type=int, nargs="?", default=5)
parser.add_argument("--timeout", type=int, default=600)
args = parser.parse_args()
if args.frames < 1 or args.repeats < 2 or args.timeout < 1:
    parser.error("positive frames/timeout and at least two timed rounds required")
out = args.out
out.mkdir(parents=True, exist_ok=True)
plan = {}
for line in args.variants.read_text().splitlines():
    parts = line.split("#", 1)[0].split()
    if parts:
        name, *pairs = parts
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in plan:
            parser.error(f"invalid or duplicate variant {name!r}")
        plan[name] = dict(p.split("=", 1) for p in pairs)
if "baseline" not in plan:
    parser.error("missing baseline variant")
digests = ("pixel_digest", "draw_state_digest", "state_digest")


def line_value(stdout, prefix):
    values = [line[len(prefix):] for line in stdout.splitlines() if line.startswith(prefix)]
    if len(values) != 1:
        raise ValueError(f"expected exactly one {prefix.strip()} line, found {len(values)}")
    return values[0]


def run(name, run_id, trace):
    env = {**os.environ, **plan[name], "DM_NVN_ENC_THREAD": "1"}
    env.pop("RBM_TRACE", None)
    path = out / f"{name}.{run_id}.trace"
    if trace:
        path.unlink(missing_ok=True)
        env["RBM_TRACE"] = str(path.resolve())
    log = out / f"{name}.{run_id}.log"
    try:
        r = subprocess.run([str(args.binary.resolve()), str(args.frames)], env=env,
                           capture_output=True, timeout=args.timeout)
    except subprocess.TimeoutExpired as e:
        log.write_bytes((e.stdout or b"") + (e.stderr or b""))
        raise ValueError(f"timeout after {args.timeout}s") from e
    except OSError as e:
        log.write_text(str(e))
        raise
    log.write_bytes(r.stdout + r.stderr)
    if r.returncode:
        raise ValueError(f"process exited {r.returncode}")
    stdout = r.stdout.decode()
    m = json.loads(line_value(stdout, "METRICS "))
    if not isinstance(m, dict) or m.get("frames") != args.frames or m.get("enc_thread") != 1:
        raise ValueError("invalid METRICS frame count or encode-thread flag")
    if m.get("backend") not in ("Metal3", "Metal4") or m.get("exec_equals_put") != 1:
        raise ValueError("invalid backend or exec_equals_put != 1")
    for key in digests:
        if not isinstance(m.get(key), str) or not re.fullmatch(r"[0-9a-f]{16}", m[key]):
            raise ValueError(f"invalid {key}")
    for key in ("draws", "dispatches"):
        if not isinstance(m.get(key), (float, int)) or m[key] <= 0:
            raise ValueError(f"no {key} in replay")
    for key, value in m.items():
        if key not in ("backend", *digests) and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f"invalid numeric metric {key}")
    if trace:
        frame_marks = []
        draws = dispatches = 0
        with path.open() as f:
            for line in f:
                if line.startswith("F "):
                    frame_marks.append(line.strip())
                elif line.startswith("D "):
                    draws += 1
                elif line.startswith("K "):
                    dispatches += 1
        if (frame_marks != [f"F {i}" for i in range(1, args.frames + 1)]
                or round(draws / args.frames, 1) != m["draws"]
                or round(dispatches / args.frames, 1) != m["dispatches"]):
            raise ValueError("incomplete diagnostic trace")
        return m, []
    samples = [float(n) for n in line_value(stdout, "TIMES ").split()]
    if len(samples) != args.frames or not all(math.isfinite(n) and n > 0 for n in samples):
        raise ValueError(f"expected {args.frames} finite positive frame times")
    return m, samples


def quantile(values, p):
    values = sorted(values)
    index = (len(values) - 1) * p
    low = int(index)
    return values[low] + (values[math.ceil(index)] - values[low]) * (index - low)


def trace_difference(name):
    files = [out / f"{n}.diagnostic.trace" for n in ("baseline", name)]
    with files[0].open() as a, files[1].open() as b:
        for i, (x, y) in enumerate(zip_longest(a, b, fillvalue="<end>"), 1):
            if x != y:
                return f"line {i}: baseline {x.strip()[:300]} / {name} {y.strip()[:300]}"
    return "identical"


names = list(plan)
runs = {name: [None] * args.repeats for name in names}
times = {name: {} for name in names}
diag = {}
errors = {name: [] for name in names}
for round_id in range(-1, args.repeats):
    diagnostic = round_id < 0
    run_id = "diagnostic" if diagnostic else round_id
    start = 0 if diagnostic else round_id % len(names)
    for name in names[start:] + names[:start]:
        try:
            metrics, samples = run(name, run_id, diagnostic)
            if diagnostic:
                diag[name] = metrics
            else:
                runs[name][round_id] = metrics
                times[name][round_id] = samples
        except (OSError, ValueError) as e:
            reason = f"run {run_id}: {e} (see {name}.{run_id}.log)"
            errors[name].append(reason)
            print(f"{name} FAILED {reason}", flush=True)

for filename, data in (("metrics", runs), ("times", times), ("diagnostic-metrics", diag)):
    (out / f"{filename}.json").write_text(json.dumps(data, indent=1) + "\n")

for name in names:
    records = [m for m in [diag.get(name), *runs[name]] if m is not None]
    if not records:
        continue
    for key in ("backend", *digests):
        if len({r[key] for r in records}) != 1:
            errors[name].append(f"unstable {key}")
    if any(r.keys() != records[0].keys() for r in records):
        errors[name].append("METRICS fields changed across runs")

baseline = diag.get("baseline", {})
baseline_valid = not errors["baseline"]
for name in ["baseline", *(n for n in names if n != "baseline")]:
    measured = [m for m in runs[name] if m is not None]
    print(f"\n### {name}: {len(measured)}/{args.repeats} timed runs, "
          f"{int(name in diag)}/1 diagnostic run")
    m = diag.get(name, {})
    if name != "baseline":
        if not baseline_valid:
            errors[name].append("baseline invalid")
        elif m:
            if m.keys() != baseline.keys():
                errors[name].append("METRICS fields differ from baseline")
            for key in ("backend", *digests[:2], "draws", "dispatches"):
                if m[key] != baseline[key]:
                    errors[name].append(f"{key} differs from baseline")
            same = m["state_digest"] == baseline["state_digest"]
            print(f"historical state_digest (includes pass begins): {'identical' if same else 'different'}")
            print("diagnostic trace: " + trace_difference(name))
    if m:
        print(", ".join(f"{k}={m[k]}" for k in ("backend", *digests)))
        for key, val in m.items():
            if not isinstance(val, (float, int)) or key in ("frames", "enc_thread", "exec_equals_put"):
                continue
            vals = [r[key] for r in measured if key in r] + [val]
            base_vals = [r[key] for r in runs["baseline"] if r and key in r]
            if key in baseline:
                base_vals.append(baseline[key])
            if name == "baseline" or set(vals) != set(base_vals):
                print(f"- {key} range per frame {min(vals):g}..{max(vals):g}")
        log = (out / f"{name}.diagnostic.log").read_text(errors="replace")
        print(next((l for l in log.splitlines() if l.startswith("PASSES")), ""))
    if errors[name]:
        print("REJECTED: " + "; ".join(errors[name]))
        continue
    print("equivalence checks passed")
    flat = [v for series in times[name].values() for v in series]
    print(f"Instrumented runner latency, submit to queue finish, one frame in flight: "
          f"median {statistics.median(flat):.4f} ms, p95 {quantile(flat, .95):.4f} ms, "
          f"p99 {quantile(flat, .99):.4f} ms ({len(flat)} untraced frames)")
    if name != "baseline":
        pairs = [(statistics.median(times[name][k]) / statistics.median(times["baseline"][k]) - 1) * 100
                 for k in range(args.repeats)]
        print(f"Paired latency change: median {statistics.median(pairs):+.2f}%, "
              f"p25 {quantile(pairs, .25):+.2f}%, p75 {quantile(pairs, .75):+.2f}% "
              f"({len(pairs)} complete rounds)")
(out / "validation.json").write_text(json.dumps(errors, indent=1) + "\n")
sys.exit(int(any(errors.values())))
