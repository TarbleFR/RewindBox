"""Measure cold-independent frame submission, GPU completion and host notification with a fixed homebrew fragment."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile


def summarize(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 12 * 2 * 180:
        raise ValueError("missing frame samples")
    print("pair,limit,submission_wait_p50_ms,cpu_encode_commit_p95_ms,gpu_work_p50_ms,gpu_work_p95_ms,"
          "gpu_end_interval_p99_ms,gpu_intervals_gt_16_67ms,callback_latency_p95_ms,host_completed_per_s,"
          "footprint_before,footprint_after,device_allocated")
    for pair in range(1,13):
        for limit in (1,3):
            batch = [r for r in rows if int(r["pair"])==pair and int(r["limit"])==limit]
            if [int(x["frame"]) for x in batch] != list(range(180)):
                raise ValueError((pair,limit))
            def delta(end,start):
                return [1000*(float(row[end])-float(row[start])) for row in batch]
            def percentile(v,p):
                return sorted(v)[math.ceil(p*len(v))-1]
            # Sort completion timestamps when measuring the spacing of completions.
            # The driver can finish command buffers in a different order from submission.
            times = sorted(float(row["gpu_end"]) for row in batch)
            intervals = [1000*(b-a) for a,b in zip(times,times[1:])]
            elapsed = max(float(row["callback"]) for row in batch)-float(batch[0]["start"])
            result = [pair,limit,median(delta("after_wait","start")),percentile(delta("committed","after_wait"),.95),
                      median(delta("gpu_end","gpu_start")),percentile(delta("gpu_end","gpu_start"),.95),
                      percentile(intervals,.99),sum(x>1000/60 for x in intervals),
                      percentile(delta("callback","start"),.95),len(batch)/elapsed,
                      *(int(batch[0][key]) for key in ("footprint_before","footprint_after","device_allocated"))]
            print(",".join(f"{v:.6f}" if isinstance(v,float) else str(v) for v in result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--summarize",action="store_true")
    args=parser.parse_args()
    if args.summarize:
        summarize(args.output)
        return 0
    here=Path(__file__).resolve().parent
    ref=next(r for r in json.loads((here.parent/"reference-output.json").read_text()) if r["id"]=="switchbrew/deko_basic")
    key=ref["spirv_sha256"][:16]
    msl=here.parent/"msl"/(key+".metal")
    if hashlib.sha256(msl.read_bytes()).hexdigest()!=ref["msl_sha256"] or ref["readback_first4"]!=[64,128,191,255]:
        raise ValueError("homebrew shader or Vulkan oracle changed")
    if sys.platform!="darwin":
        return 77
    with tempfile.TemporaryDirectory() as d:
        exe=Path(d)/"measure"
        subprocess.run(["xcrun","--sdk","macosx","clang","-O2","-Wall","-Wextra","-Werror","-fobjc-arc",
                        here/"measure.m","-framework","Metal","-framework","Foundation","-o",exe],check=True)
        rc=subprocess.run([exe,msl,"vk_"+key,args.output]).returncode
        if rc:
            return rc
    summarize(args.output)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
