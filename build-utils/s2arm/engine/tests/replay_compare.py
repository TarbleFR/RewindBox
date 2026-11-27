#!/usr/bin/env python3
"""Run t_rb_replay_metrics per variant (replay_variants.txt), several times each, and compare each with the baseline.

usage: replay_compare.py <binary> <variants file> <output dir> [frames] [repeats]
Each run is a new process with DM_NVN_ENC_THREAD=1 and the variant's switches. Rounds alternate the variant order (round k starts at variant k)
and every variant runs `repeats` times (default 5). Prints, per variant, whether its metrics and digests were the same in every run, the metrics
that differ from the baseline's (values of the first run, with their spread when runs disagree), and whether the state digest (what every draw and
dispatch sees) and the pixel digest (every target read back) are identical to the baseline's. A digest is only compared when it is stable across
the baseline's own runs; otherwise it is reported as unstable (not evidence either way). Each run writes a per-draw trace (RBM_TRACE) and the
first line where two runs part is printed: between the baseline's own runs, and for a variant whose metrics move.
Timing (TIMES line): wall time of each measured frame, submit to queue finish, on the runner's GPU. Per variant: median over all its frames, and
the paired change against the baseline of the same round (median, p25, p75 of the per-round medians' ratio). Runner timings, not iPhone frame times.
Exit 1 when a variant changes the pixels: such a switch is not an equivalent optimization.
"""
import json, os, statistics, subprocess, sys
from pathlib import Path

binary, variants, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
frames = sys.argv[4] if len(sys.argv) > 4 else "3"
repeats = int(sys.argv[5]) if len(sys.argv) > 5 else 5
out.mkdir(parents=True, exist_ok=True)
plan = []
for line in variants.read_text().splitlines():
    line = line.split("#", 1)[0].strip()
    if line:
        name, *pairs = line.split()
        plan.append((name, dict(p.split("=", 1) for p in pairs)))
runs = {name: [] for name, _ in plan}
times = {name: {} for name, _ in plan}   # variant -> round -> frame wall times (ms)
for k in range(repeats):
    for name, sw in plan[k % len(plan):] + plan[:k % len(plan)]:
        env = {**os.environ, "DM_NVN_ENC_THREAD": "1", **sw, "RBM_TRACE": str(out / f"{name}.{k}.trace")}
        r = subprocess.run([str(binary), frames], capture_output=True, text=True, env=env, timeout=600)
        (out / f"{name}.{k}.log").write_text(r.stdout + r.stderr)
        m = [l for l in r.stdout.splitlines() if l.startswith("METRICS ")]
        if r.returncode or not m:
            print(f"{name} run {k}: FAILED rc={r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}")
            continue
        runs[name].append(json.loads(m[-1][8:]))
        t = [l for l in r.stdout.splitlines() if l.startswith("TIMES")]
        if t and t[-1].split()[1:]:
            times[name][k] = [float(x) for x in t[-1].split()[1:]]
(out / "metrics.json").write_text(json.dumps(runs, indent=1))
(out / "times.json").write_text(json.dumps(times, indent=1))
if not runs.get("baseline"):
    sys.exit("baseline failed")
base_runs = runs["baseline"]
base = base_runs[0]
keys = [k for k, v in base.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
stable = lambda rs, k: len({json.dumps(r.get(k)) for r in rs}) == 1
st_ok, px_ok = stable(base_runs, "state_digest"), stable(base_runs, "pixel_digest")
print(f"baseline: Metal{base['backend'][-1]}, {base['frames']} frames, {len(base_runs)}/{repeats} runs, per frame: "
      + ", ".join(f"{k}={base[k]:g}" for k in keys if k not in ("frames", "enc_thread")))
print(f"baseline digests across its runs: state {'stable' if st_ok else 'UNSTABLE (not compared)'}, pixels {'stable' if px_ok else 'UNSTABLE'}")
moving = [k for k in keys if not stable(base_runs, k)]
if moving:
    print("baseline metrics that change between its own runs: " + ", ".join(f"{k} {sorted({r[k] for r in base_runs})}" for k in moving))
def first_split(a, b):   # first line where two traces differ: (line number, line of a, line of b), or None
    try:
        la, lb = (out / a).read_text().splitlines(), (out / b).read_text().splitlines()
    except OSError:
        return ("no trace",)
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return (i + 1, x, y)
    return None if len(la) == len(lb) else (min(len(la), len(lb)) + 1, f"{len(la)} lines", f"{len(lb)} lines")
def show_split(title, a, b):
    d = first_split(a, b)
    if d:
        print(f"{title}: first difference at trace line {d[0]}" + (f"\n    {a}: {d[1][:300]}\n    {b}: {d[2][:300]}" if len(d) > 1 else ""))
    return d
splits = [show_split("baseline run 0 vs run %d" % k, "baseline.0.trace", f"baseline.{k}.trace") for k in range(1, repeats)]
if not any(splits):
    print("baseline traces identical across its runs")
bad = 0 if px_ok else 1
for name, rs in runs.items():
    if name == "baseline":
        continue
    if not rs:
        bad = 1
        continue
    m = rs[0]
    same_px = all(r["pixel_digest"] == base["pixel_digest"] for r in rs) and px_ok
    same_st = "unstable" if not st_ok else ("identical" if all(r["state_digest"] == base["state_digest"] for r in rs) else "different")
    spread = lambda k, rr: f" [{min(r[k] for r in rr):g}..{max(r[k] for r in rr):g}]" if not stable(rr, k) else ""
    diff = [f"{k} {base[k]:g}{spread(k, base_runs)} -> {m[k]:g}{spread(k, rs)}" + (f" ({(m[k] - base[k]) / base[k] * 100:+.1f}%)" if base[k] else "")
            for k in keys if m[k] != base[k] or not stable(rs, k)]
    print(f"\n### {name} ({len(rs)}/{repeats} runs)\npixels {'identical' if same_px else 'DIFFERENT'}, state at draws {same_st}")
    for d in diff:
        print(f"- {d}")
    for k in range(len(rs)):
        if any(rs[k][x] != base[x] for x in keys if x != "residency_adds"):
            show_split(f"  {name} run {k} vs baseline run 0", "baseline.0.trace", f"{name}.{k}.trace")
            break
    bad |= not same_px
def q(v, p):
    v = sorted(v); i = (len(v) - 1) * p; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
print("\n### Frame wall time on the runner (submit to finish, ms; paired with the baseline of the same round)")
bt = times.get("baseline", {})
for name, per in times.items():
    allf = [x for v in per.values() for x in v]
    if not allf:
        continue
    line = f"- {name}: median {statistics.median(allf):.4f} ms over {len(allf)} frames in {len(per)} runs"
    if name != "baseline":
        pct = [(statistics.median(per[k]) / statistics.median(bt[k]) - 1) * 100 for k in per if k in bt]
        if pct:
            line += f", paired {statistics.median(pct):+.2f}% (p25 {q(pct, .25):+.2f}, p75 {q(pct, .75):+.2f}, {len(pct)} pairs)"
    print(line)
sys.exit(1 if bad else 0)
