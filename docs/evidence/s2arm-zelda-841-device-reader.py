#!/usr/bin/env python3
"""Summarize the two Zelda 841 diagnostic captures, without treating them as an A/B.

Usage: python s2arm-zelda-841-device-reader.py --cpu-log CPU/host.log --gpu-log GPU/host.log
Only summaries, hashes and line numbers are emitted; private raw log lines stay local.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from statistics import median


def numbers(line):
    return {k: Decimal(v) for k, v in re.findall(r"(\w+)=([0-9.]+)", line)}


def stats(values):
    return {"samples": len(values), "min": min(values), "median": median(values), "max": max(values)} if values else None


def read(path, lo, hi):
    raw = path.read_bytes()
    lines = raw.decode(errors="replace").splitlines()
    sync, heads, wakes = {}, {}, defaultdict(dict)
    timing, speeds, probes, menu_probes, energy, thermal, stalls = [], [], [], [], [], [], []
    passes, cuts, targets, shaders, coverage = [], Counter(), defaultdict(Counter), {}, []
    gpudiag_lines, first_uses = 0, []
    for lineno, line in enumerate(lines, 1):
        d = numbers(line)
        if "[rb-cpu-gpu-sync]" in line:
            frame = int(d["frame"])
            if frame in sync or (sync and frame < max(sync)):
                raise ValueError("Expected a single session; split logs at resets first")
            sync[frame] = d
        if "[rb-wake]" in line:
            heads[int(d["frame"])] = d
        if "[rb-wake-site]" in line:
            key = re.search(r"site=(\S+) kind=(\S+)", line).groups()
            wakes[int(d["frame"])][key] = d
        if "[rb-gpu-probe]" in line:
            f, duration = int(d["frame"]), float(d["gpu_ns"] / 1000000)
            if lo < f <= hi:
                probes.append(duration)
            if 300 < f <= 2100:
                menu_probes.append(duration)
        if "[nvn] timing up to frame" in line:
            f = int(re.search(r"up to frame (\d+)", line)[1])
            if lo < f <= hi:
                gpu = re.search(r"GPU p50 ([\d.]+) / p95 ([\d.]+) / max ([\d.]+)", line)
                timing.append({"frame": f, "line": lineno,
                               "gpuP50Ms": float(gpu[1]), "gpuP95Ms": float(gpu[2]),
                               "thermal": int(re.search(r"thermal state (\d+)", line)[1])})
        if "[rb-speed] up to present" in line:
            m = re.search(r"present (\d+): game speed ([\d.]+).*?; ([\d.]+) presents a second", line)
            if lo < int(m[1]) <= hi:
                speeds.append({"frame": int(m[1]), "speedPercent": float(m[2]), "fps": float(m[3])})
        if "[nvn] power up to frame" in line:
            m = re.search(r"up to frame (\d+): CPU energy ([\d.]+).*?wakeups (\d+)/s", line)
            if lo < int(m[1]) <= hi:
                energy.append({"frame": int(m[1]), "cpuW": float(m[2]), "kernelWakeupsPerSecond": int(m[3])})
        if "[心跳]" in line:
            m = re.search(r"帧 (\d+)，热状态 (\d+).*?进程实占 (\d+) MB", line)
            if m:
                thermal.append({"line": lineno, "frame": int(m[1]), "state": int(m[2]), "footprintReportedMB": int(m[3])})
        if "[longframe]" in line:
            m = re.search(r"frame (\d+) \(([\d.]+) s\) whole frame ([\d.]+) ms", line)
            if m:
                item = {"line": lineno, "frame": int(m[1]), "elapsedS": float(m[2]), "wholeMs": float(m[3])}
                for key, pattern in [("compileReportedMs", r"shader libraries \d+, ([\d.]+) ms in all"),
                                     ("uploadMs", r"texture uploads .*? / ([\d.]+) ms"),
                                     ("storageReadMB", r"storage read ([\d.]+) MB")]:
                    hit = re.search(pattern, line)
                    if hit:
                        item[key] = float(hit[1])
                stalls.append(item)
        if "first-use wait #" in line:
            m = re.search(r"#(\d+) frame (\d+): ([\d.]+) ms", line)
            first_uses.append({"line": lineno, "ordinal": int(m[1]), "frame": int(m[2]), "ms": float(m[3])})
        if "[rb-gpudiag" not in line:
            continue
        gpudiag_lines += 1
        f = int(d.get("frame", d.get("up_to_frame", -1)))
        if not lo < f <= hi:
            continue
        if "[rb-gpudiag]" in line:
            passes.append(d)
        elif "[rb-gpudiag-cut]" in line:
            cuts[re.search(r"cause=(\S+)", line)[1]] += int(d["count"])
        elif "[rb-gpudiag-target]" in line and (d["width"], d["height"]) == (854, 480):
            targets[re.search(r"role=(\S+)", line)[1]][f] += int(d["reopens"])
        elif "[rb-gpudiag-shader]" in line:
            key = re.search(r"key=(\S+)", line)[1]
            facts = {k: int(v) for k, v in d.items() if k not in ("up_to_frame", "draws", "depth_test_draws")}
            if key in shaders and shaders[key]["facts"] != facts:
                raise ValueError("Shader facts changed within selected window")
            s = shaders.setdefault(key, {"key": key, "draws": 0, "depthDraws": 0, "facts": facts})
            s["draws"] += int(d["draws"])
            s["depthDraws"] += int(d["depth_test_draws"])
        elif "[rb-gpudiag-shader-coverage]" in line:
            coverage.append({k: int(v) for k, v in d.items()})
    if lo not in sync or hi not in sync:
        raise ValueError("Both cumulative boundaries must exist; no interpolation")
    fields = ("queue_wait_records", "queue_wait_drains", "queue_wait_drain_ms", "allocator_wait_ms", "visibility_wait_ms")
    def delta(a, b):
        diff = {k: b[k] - a[k] for k in fields}
        if any(v < 0 for v in diff.values()):
            raise ValueError("Cumulative counter reset")
        return {"fromFrame": int(a["frame"]), "toFrame": int(b["frame"]), "delta": diff,
                "allocatorMsPerFrame": diff["allocator_wait_ms"] / (b["frame"] - a["frame"])}
    frames = sorted(f for f in sync if lo <= f <= hi)
    wake_rows, wake_seconds = [], None
    if lo in heads and hi in heads:
        if heads[lo]["epoch"] != heads[hi]["epoch"]:
            raise ValueError("Wake epoch reset")
        wake_seconds = (heads[hi]["mono_ns"] - heads[lo]["mono_ns"]) / Decimal(1000000000)
        for key, b in wakes[hi].items():
            # Sites first registered after the initial snapshot begin at zero.
            a = wakes[lo].get(key, {})
            diffs = {k: int(b[k] - a.get(k, 0)) for k in ("waits", "returns", "timeouts", "signals", "short_waits", "errors")}
            if any(v < 0 for v in diffs.values()):
                raise ValueError("Wake counter reset")
            wake_rows.append({"site": key[0], "kind": key[1], "delta": diffs,
                              "returnsPerSecond": Decimal(diffs["returns"]) / wake_seconds,
                              "signalsPerSecond": Decimal(diffs["signals"]) / wake_seconds})
        wake_rows.sort(key=lambda r: r["delta"]["returns"] + r["delta"]["signals"], reverse=True)
    return {"log": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "lines": len(lines),
            "window": {"fromFrame": lo, "toFrame": hi, "notPairedAB": True},
            "sync": delta(sync[lo], sync[hi]),
            "syncIntervals": [delta(sync[a], sync[b]) for a, b in zip(frames, frames[1:])],
            "timing": timing, "speeds": speeds, "energy": energy, "thermalSnapshotsWholeSession": thermal,
            "probe3DMs": stats(probes), "probeMenuMs": stats(menu_probes),
            "wakeSeconds": wake_seconds, "wakeSites": wake_rows,
            "longestLoggedFramesWholeSession": sorted(stalls, key=lambda r: r["wholeMs"], reverse=True)[:6],
            "firstUseWaitLinesWholeSession": len(first_uses), "largestLoggedFirstUseMs": max((v["ms"] for v in first_uses), default=None),
            "gpuDiagnostic": {"linesWholeSession": gpudiag_lines, "frames": len(passes),
                "passesPerFrame": stats([int(r["passes"]) for r in passes]), "cuts": dict(cuts.most_common()),
                "droppedTargetRecords": sum(int(r["dropped_targets"]) for r in passes),
                "droppedCutRecords": sum(int(r["dropped_cuts"]) for r in passes),
                "main854x480ReopensSummedAcrossSerials": {k: stats(list(v.values())) for k, v in targets.items()},
                "shaderCoverage": coverage, "recordedDistinctShaderKeys": len(shaders),
                "recordedShaderDraws": sum(s["draws"] for s in shaders.values()),
                "recordedMissingEarlyKeys": sum(bool(s["facts"]["missing_requested_early"]) for s in shaders.values()),
                "recordedUnknownGuestEarlyKeys": sum(s["facts"]["guest_early"] == 0 for s in shaders.values()),
                "recordedPoolAtomicKeys": sum(bool(s["facts"]["pool_atomic_or"]) for s in shaders.values()),
                "topShadersByDepthDraws": sorted(shaders.values(), key=lambda r: r["depthDraws"], reverse=True)[:12]}}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cpu-log", type=Path, required=True)
    p.add_argument("--gpu-log", type=Path, required=True)
    a = p.parse_args()
    result = {"scope": "Device observations of diagnostic profiles; no causal speedup or pixel replay proof",
              "cpu": read(a.cpu_log, 2700, 6900), "gpu": read(a.gpu_log, 3600, 5700)}
    print(json.dumps(result, indent=2, default=lambda v: float(v) if isinstance(v, Decimal) else str(v)))
