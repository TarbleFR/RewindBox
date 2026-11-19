#!/usr/bin/env python3
"""Summarize one iPhone session. Supply frame signatures from the same session only."""
import argparse
import json
import math
from pathlib import Path
import re


COURSE_FIELDS = ("samples", "interval_ms", "over100", "over500", "pso_wait_ms",
                 "shared_library_wait_ms", "xlate_wait_ms", "xlate_ms", "msl_count",
                 "msl_ms", "texture_upload_ms", "texture_gpu_completed_ms")
COURSE_COUNTS = {"samples", "over100", "over500", "msl_count"}
COURSE_LINE = re.compile(
    r"RewindBox course metrics frames=(\d+)\.\.(\d+) asset=([A-Za-z0-9_\[\]-]{1,63}) "
    + " ".join(key + (r"=(\d+)" if key in COURSE_COUNTS else r"=(\d+\.\d+)") for key in COURSE_FIELDS)
    + r"\s*$")


def course_totals(windows):
    by_asset = {}
    first_incomplete = []
    previous_end = -1
    for (start, end), assets in sorted(windows.items()):
        if start <= previous_end or end < start:
            raise ValueError("Overlapping course windows. Supply a single session.")
        previous_end = end
        if sum(row["samples"] for row in assets.values()) != end - start + 1:
            first_incomplete.append([start, end])
            continue
        for asset, row in assets.items():
            totals = by_asset.setdefault(asset, dict.fromkeys(COURSE_FIELDS, 0))
            for key, value in row.items():
                totals[key] += value
    for totals in by_asset.values():
        for key in totals.keys() - COURSE_COUNTS:
            totals[key] = round(totals[key], 3)
    return {"completeIntervalsByAsset": by_asset, "incompleteWindows": first_incomplete}

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
    slow_logged = {100: 0, 200: 0, 500: 0}
    full_windows, gap_rows, reference_binds = [], {}, []
    course_windows = {}
    archive = None
    missing = None
    shared_library_count = None
    completed_predictions, active_prediction, governor = [], None, []
    with host.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            if "RewindBox course metrics frames=" in line:
                m = COURSE_LINE.search(line)
                if m and selected(int(m[1])) and selected(int(m[2])):
                    assets = course_windows.setdefault((int(m[1]), int(m[2])), {})
                    if m[3] in assets:
                        raise ValueError("Duplicate course window and asset. Supply a single session.")
                    assets[m[3]] = {key: (int(v) if key in COURSE_COUNTS else float(v))
                                    for key, v in zip(COURSE_FIELDS, m.groups()[3:])}
            m = re.search(r"\[longframe\] frame (\d+) \(([\d.]+) s\) whole frame ([\d.]+) ms", line)
            if m and selected(int(m[1])):
                parts = re.search(r"shader translations on the submit thread (\d+), ([\d.]+) ms, waits for one in flight (\d+), ([\d.]+) ms; MSL compiled there (\d+), ([\d.]+) ms", line)
                i = int(m[1])
                if i in long_frames:
                    raise ValueError(f"Duplicate host frame {i}. Supply a single session.")
                long_frames[i] = list(map(float, parts.groups())) if parts else None
                for threshold in slow_logged:
                    slow_logged[threshold] += float(m[3]) > threshold
                gaps = re.search(r"outside submit/present ([\d.]+) ms, longest ([\d.]+) ms over (\d+) gaps", line)
                if gaps:
                    gap_rows[i] = {"outsideMs": float(gaps[1]), "longestMs": float(gaps[2]), "count": int(gaps[3])}
            m = re.search(r"RewindBox frame intervals (\d+)\.\.(\d+): (\d+) samples, (\d+) ns, above 100/200/500 ms (\d+)/(\d+)/(\d+)", line)
            if m and selected(int(m[1])) and selected(int(m[2])):
                a, b, n, ns, s100, s200, s500 = map(int, m.groups())
                if b - a + 1 != n or not ns or not (0 <= s500 <= s200 <= s100 <= n):
                    raise ValueError("Invalid frame-interval window")
                if full_windows and full_windows[-1][1] >= a:
                    raise ValueError("Overlapping frame-interval windows. Supply a single session.")
                full_windows.append((a, b, n, ns, s100, s200, s500))
            m = re.search(r"reference: encoder bound exact prewarmed PSO ([0-9a-f]{40}) at frame (\d+)", line)
            if m and selected(int(m[2])):
                reference_binds.append({"archiveKey": m[1], "frame": int(m[2])})
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
    intervals = None
    if full_windows:
        n, ns, s100, s200, s500 = map(sum, zip(*(w[2:] for w in full_windows)))
        intervals = {"first": full_windows[0][0], "last": full_windows[-1][1], "samples": n,
                     "missingWithinObservedSpan": full_windows[-1][1] - full_windows[0][0] + 1 - n,
                     "averageFPS": round(n * 1e9 / ns, 3), "over100Ms": s100, "over200Ms": s200, "over500Ms": s500}
    return {"courseAssetWindows": course_totals(course_windows),
        "frameSignatureIntervals": sig, "completeHostWindows": intervals, "referenceBinds": reference_binds,
        "selectedLoggedFrames": {"rowsOverMs": slow_logged, "submitGaps": gap_rows,
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
