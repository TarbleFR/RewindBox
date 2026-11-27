#!/usr/bin/env python3
"""Run t_rb_replay_metrics once per variant (replay_variants.txt) and compare each with the baseline.

usage: replay_compare.py <binary> <variants file> <output dir> [frames]
Each run is a new process with DM_NVN_ENC_THREAD=1 and the variant's switches. Prints a Markdown table of the metrics that differ, and whether the
state digest (what every draw and dispatch sees) and the pixel digest (every target read back) are identical to the baseline's.
Exit 1 when a variant changes the pixels: such a switch is not an equivalent optimization.
"""
import json, os, subprocess, sys
from pathlib import Path

binary, variants, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
frames = sys.argv[4] if len(sys.argv) > 4 else "3"
out.mkdir(parents=True, exist_ok=True)
runs = {}
for line in variants.read_text().splitlines():
    line = line.split("#", 1)[0].strip()
    if not line:
        continue
    name, *pairs = line.split()
    env = {**os.environ, "DM_NVN_ENC_THREAD": "1"}
    for p in pairs:
        k, v = p.split("=", 1)
        env[k] = v
    r = subprocess.run([str(binary), frames], capture_output=True, text=True, env=env, timeout=600)
    (out / f"{name}.log").write_text(r.stdout + r.stderr)
    m = [l for l in r.stdout.splitlines() if l.startswith("METRICS ")]
    if r.returncode or not m:
        print(f"{name}: FAILED rc={r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}")
        runs[name] = None
        continue
    runs[name] = json.loads(m[-1][8:])
(out / "metrics.json").write_text(json.dumps(runs, indent=1))
base = runs.get("baseline")
if not base:
    sys.exit("baseline failed")
keys = [k for k, v in base.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
print(f"baseline: Metal{base['backend'][-1]}, {base['frames']} frames, per frame: " + ", ".join(f"{k}={base[k]:g}" for k in keys if k not in ("frames", "enc_thread")))
bad = 0
for name, m in runs.items():
    if name == "baseline" or m is None:
        continue
    same_px = m["pixel_digest"] == base["pixel_digest"]
    same_st = m["state_digest"] == base["state_digest"]
    diff = [f"{k} {base[k]:g} -> {m[k]:g} ({(m[k] - base[k]) / base[k] * 100:+.1f}%)" if base[k] else f"{k} {base[k]:g} -> {m[k]:g}"
            for k in keys if m[k] != base[k]]
    print(f"\n### {name}\npixels {'identical' if same_px else 'DIFFERENT'}, state at draws {'identical' if same_st else 'different'}")
    for d in diff:
        print(f"- {d}")
    bad |= not same_px
sys.exit(1 if bad else 0)
