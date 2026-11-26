#!/usr/bin/env python3
"""Verify five identical recorded inputs with a warm Mesa cache, in new processes."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("engine", type=Path)
parser.add_argument("tool_dir", type=Path, help="Contains dll/ShaderCases.dll and both Vulkan runners")
parser.add_argument("guest_dir", type=Path, help="Directory with DKSH/raw or the reference-guest.json fixture")
parser.add_argument("glsl", type=Path)
parser.add_argument("out", type=Path, help="New output directory")
a = parser.parse_args()
out = a.out.resolve()
out.mkdir(parents=True, exist_ok=False)
guest = a.guest_dir.resolve()
if guest.is_file():
    entry = json.loads(guest.read_text())
    guest = out/"reference"
    guest.mkdir()
    if set(entry["files"]) != {"color.dksh","color.raw"}:
        raise ValueError("Unexpected guest fixture files")
    for fn, record in entry["files"].items():
        binary = base64.b64decode(record["base64"], validate=True)
        if hashlib.sha256(binary).hexdigest() != record["sha256"]:
            raise ValueError(f"Guest fixture hash mismatch for {fn}")
        (guest/fn).write_bytes(binary)
env = {**os.environ, "MESA_SHADER_CACHE_DIR":str(out/"mesa-cache"), "LP_NUM_THREADS":"1",
       "PYTHONDONTWRITEBYTECODE":"1"}
script = Path(__file__).resolve().with_name("replay.py")
cmd = [sys.executable, script, a.engine.resolve()]
fixed_args = ["--translator",a.tool_dir.resolve()/"dll/ShaderCases.dll",
              "--runner",a.tool_dir.resolve()/"vulkan-runner",
              "--surface-runner",a.tool_dir.resolve()/"vulkan-surface-runner",
              "--glsl",a.glsl.resolve(),"--fixed",guest]
contract = None
runs = []
for i in range(6):
    name = "warmup" if i == 0 else f"run-{i}"
    target = out/name
    with (out/(name+".log")).open("w") as log:
        start = time.perf_counter_ns()
        subprocess.run([*cmd, target, *fixed_args], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        elapsed = time.perf_counter_ns() - start
    obtained = {p.name:sha(p) for p in sorted(target.iterdir())
                if p.suffix in (".spv",".metal",".bin",".rgba",".readback") or p.name=="report.json"}
    if contract is None:
        contract = obtained
    elif contract != obtained:
        raise ValueError(f"{name}: shader, check or readback bytes diverged from the warm-up")
    if i:
        runs.append({"trial":i, "wall_ns":elapsed, "file_sha256":obtained})
report = {
   "mode":"Linux CPU Vulkan lavapipe, full host-process wall time; six fresh processes; one warm-up then five timed replays",
   "frozen_dksh_sha256":sha(guest / "color.dksh"),
   "frozen_raw_sha256":sha(guest / "color.raw"),
   "source_glsl_sha256":sha(a.glsl),
   "median_wall_ns":statistics.median_low([r["wall_ns"] for r in runs]),
   "runs":runs
}
(out/"five.json").write_text(json.dumps(report, indent=2)+"\n")
print(f'5/5 byte-identical, {len(contract)} files per trial, median {report["median_wall_ns"]/1e9:.3f} s')
