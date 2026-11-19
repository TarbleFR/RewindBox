#!/usr/bin/env python3
"""Summarize one iPhone session. Supply frame signatures from the same session only."""
import argparse
import json
import math
from pathlib import Path
import re


def summarize(host, captures, first, last):
    def selected(frame):
        return first <= frame <= last

    frames = {}
    for path in captures:
        with path.open(encoding="utf-8") as lines:
            if "microseconds to the next frame" not in lines.readline():
                raise ValueError(f"Unrecognized frame-signature format: {path.name}")
            for line in lines:
                c = line.split()
                if not c or not c[0].isdecimal():
                    continue
                i = int(c[0])
                if not selected(i):
                    continue
                # Column 18 is the start-to-start interval. Zero is unavailable.
                us = int(c[17])
                if not us:
                    continue
                row = us, int(c[6]), c[1]
                if frames.setdefault(i, row) != row:
                    raise ValueError(f"Inconsistent signatures for frame {i}. Use one session.")
    spans = sorted(us for us, _, _ in frames.values())
    sig = {"observedIntervals": len(spans)}
    if spans:
        sig.update(first=min(frames), last=max(frames),
                   missingWithinObservedSpan=max(frames) - min(frames) + 1 - len(spans),
                   averageFPS=round(1e6 * len(spans) / sum(spans), 3),
                   **{f"p{p}Ms": spans[math.ceil(p * len(spans) / 100) - 1] / 1000 for p in (95, 99)},
                   **{f"over{ms}Ms": sum(t > ms * 1000 for t in spans) for ms in (100, 200, 500)},
                   pipelineSkippedDraws=sum(n for _, n, _ in frames.values()))

    long_frames, waits, footprint, thermal = {}, [], [], {}
    archive = None
    missing = None
    shared_library_count = None
    completed_predictions, active_prediction, governor = [], None, []
    with host.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            m = re.search(r"\[longframe\] frame (\d+) \(([\d.]+) s\) whole frame ([\d.]+) ms", line)
            if m and selected(int(m[1])):
                parts = re.search(r"shader translations on the submit thread (\d+), ([\d.]+) ms, waits for one in flight (\d+), ([\d.]+) ms; MSL compiled there (\d+), ([\d.]+) ms", line)
                i = int(m[1])
                if i in long_frames:
                    raise ValueError(f"Duplicate host frame {i}. Supply a single session.")
                long_frames[i] = list(map(float, parts.groups())) if parts else None
            m = re.search(r"first-use wait #\d+ frame (\d+): .*?waited for the queued compile ([\d.]+) ms", line)
            if m and selected(int(m[1])):
                waits.append(float(m[2]))
            m = re.search(r"on-screen up to frame (\d+): .*?footprint (\d+) MiB; .*?thermal (\d+)", line)
            if m and selected(int(m[1])):
                footprint.append(int(m[2]))
                thermal.setdefault(m[3], []).append(int(m[1]))
            m = re.search(r"pipeline archive after the prewarm: (\d+) builds from the archive, (\d+) compiled", line)
            if m:
                archive = {"strictHits": int(m[1]), "fallbackBuildRequests": int(m[2])}
            m = re.search(r"(\d+) lines left out for (\d+) keys with no current translation and no kept stage bytes", line)
            if m:
                missing = {"rows": int(m[1]), "keys": int(m[2])}
            m = re.search(r"existing Metal source library reused for another shader identity: (\d+)", line)
            if m:
                shared_library_count = int(m[1])
            m = re.search(r"PSO transitions: (\d+) first-used, (\d+) promoted, (\d+) published, (\d+) warmed Metal objects bound, (\d+) published but unused", line)
            if m:
                fields = ("firstUsed", "promoted", "published", "bound", "publishedUnused")
                completed_predictions.append(dict(zip(fields, map(int, m.groups()))))
                active_prediction = None
            m = re.search(r"PSO transitions: (\d+) promoted, (\d+) warmed Metal objects bound", line)
            if m:
                active_prediction = {"promoted": int(m[1]), "bound": int(m[2])}
            m = re.search(r"speculative shader work (held|on one worker|back on every worker): (.*?) \(thermal state (\d+), (-?\d+) MB left .*?Low Power Mode (\d+); (\d+) changes", line)
            if m:
                levels = {"held": "HOLD", "on one worker": "ONE", "back on every worker": "RUN"}
                governor.append({"change": int(m[6]), "level": levels[m[1]], "reason": m[2],
                                 "appleThermalState": int(m[3]), "headroomMiB": int(m[4]) if int(m[4]) >= 0 else None,
                                 "lowPowerMode": bool(int(m[5]))})
    available = [row for row in long_frames.values() if row is not None]
    sums = [round(sum(col), 2) for col in zip(*available)]
    return {"frameSignatureIntervals": sig, "selectedLoggedFrames": {
        "longFrameRows": len(long_frames), "rowsWithCompilerBreakdown": len(available),
        "compilerTotalsOnTheseRows": dict(zip(
            ("translations", "translationMs", "inFlightWaits", "translationWaitMs", "mslSourceCalls", "mslSourceMs"), sums)) if sums else None,
        "detailedPSOWaits": len(waits), "loggedPSOQueueWaitMs": round(sum(waits), 2) if waits else None,
        "maxSampledFootprintMiB": max(footprint, default=None),
        "thermalSamplesByState": {k: {"count": len(v), "firstFrame": min(v)} for k, v in thermal.items()}},
        "sessionPrewarm": {"archive": archive, "unreconstructible": missing},
        "wholeLog": {"lastReportedSourceLibraryReuses": shared_library_count,
                     "completedPredictionSessions": completed_predictions,
                     "lastUnfinishedPredictionSample": active_prediction,
                     "loggedGovernorChanges": governor}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", type=Path)
    parser.add_argument("captures", type=Path, nargs="*")
    parser.add_argument("--first", type=int, default=0, help="first frame, inclusive")
    parser.add_argument("--last", type=int, default=2**63-1, help="last frame, inclusive")
    args = parser.parse_args()
    if args.first > args.last:
        parser.error("--first must precede --last")
    print(json.dumps(summarize(args.host, args.captures, args.first, args.last), indent=2))


if __name__ == "__main__":
    main()
