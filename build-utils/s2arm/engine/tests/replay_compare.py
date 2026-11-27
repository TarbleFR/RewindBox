#!/usr/bin/env python3
"""Run t_rb_replay_metrics per variant (replay_variants.txt), several times each, and compare each with the baseline.

usage: replay_compare.py <binary> <variants file> <output dir> [frames] [repeats]
Each run is a new process with DM_NVN_ENC_THREAD=1 and the variant's switches. Rounds alternate the variant order (round k starts at variant k)
and every variant runs `repeats` times (default 5). Prints, per variant, whether its metrics and digests were the same in every run, the metrics
that differ from the baseline's (values of the first run, with their spread when runs disagree), and whether the state digest (what every draw and
dispatch sees) and the pixel digest (every target read back) are identical to the baseline's. A digest is only compared when it is stable across
the baseline's own runs; otherwise it is reported as unstable (not evidence either way).
Exit 1 when a variant changes the pixels: such a switch is not an equivalent optimization.
"""
import json, os, subprocess, sys
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
for k in range(repeats):
    for name, sw in plan[k % len(plan):] + plan[:k % len(plan)]:
        env = {**os.environ, "DM_NVN_ENC_THREAD": "1", **sw}
        r = subprocess.run([str(binary), frames], capture_output=True, text=True, env=env, timeout=600)
        (out / f"{name}.{k}.log").write_text(r.stdout + r.stderr)
        m = [l for l in r.stdout.splitlines() if l.startswith("METRICS ")]
        if r.returncode or not m:
            print(f"{name} run {k}: FAILED rc={r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}")
            continue
        runs[name].append(json.loads(m[-1][8:]))
(out / "metrics.json").write_text(json.dumps(runs, indent=1))
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
    bad |= not same_px
sys.exit(1 if bad else 0)
