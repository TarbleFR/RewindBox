#!/usr/bin/env python3
"""Convert the optional NVN host trace to a summary and a Perfetto time line."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re


def natural(fields, key):
    raw = fields[key]
    if not re.fullmatch(r"[0-9]{1,20}", raw) or int(raw) >= 2**64:
        raise ValueError(key)
    return int(raw)


def seconds(fields, key):
    value = float(fields[key])
    if not math.isfinite(value) or value < 0:
        raise ValueError(key)
    return value


def interval(fields, start, end):
    a, b = seconds(fields, start), seconds(fields, end)
    if a > b:
        raise ValueError("reversed time interval")
    return a, b


def union(spans):
    result = []
    for start, end in sorted(spans):
        if result and start <= result[-1][1]:
            result[-1] = result[-1][0], max(result[-1][1], end)
        else:
            result.append((start, end))
    return result


def duration(spans):
    return sum((end - start for start, end in spans), 0.0)


def intersect(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = max(left[i][0], right[j][0]), min(left[i][1], right[j][1])
        if a < b:
            result.append((a, b))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return result


def distribution(values):
    if not values:
        return None
    samples = sorted(values)
    return {f"p{p}": samples[math.ceil(len(samples) * p / 100) - 1] for p in (50, 95, 99)}


def read_trace(lines):
    sessions = defaultdict(dict)
    for line_num, line in enumerate(lines, 1):
        token = "[rb-parallel] "
        if token not in line:
            continue
        try:
            tokens = line.partition(token)[2].split()
            fields = dict(piece.split("=", 1) for piece in tokens)
            if len(fields) != len(tokens) or fields["v"] != "1":
                raise ValueError("invalid fields or version")
            session = natural(fields, "session")
            kind = fields["event"]
            row = {"event": kind}
            ident = None
            if kind in ("begin", "window_end"):
                keys = ("from", "frames", "cb_cap", "present_cap") if kind == "begin" else (
                    "cb_reserved", "present_reserved", "cb_limited", "present_limited")
                row.update({key: natural(fields, key) for key in keys})
            elif kind == "limit" and fields["stream"] in ("cb", "present"):
                ident = fields["stream"]
                row.update(stream=ident, cap=natural(fields, "cap"))
            elif kind in ("cb", "present"):
                status = fields["status"]
                row.update(frame=natural(fields, "frame"), status=status)
                if kind == "cb" and status in ("ok", "error", "missing"):
                    ident = natural(fields, "cb")
                    row.update(sub=natural(fields, "sub"), seg=natural(fields, "seg"),
                               metal=natural(fields, "metal"), reason=fields["reason"],
                               cpu=interval(fields, "prep_start_s", "prep_end_s"))
                    if row["metal"] not in (3, 4):
                        raise ValueError("unknown backend")
                    if "prep_thread_ns" in fields:
                        row["prep_thread_ns"] = natural(fields, "prep_thread_ns")
                    if status == "ok":
                        row["gpu"] = interval(fields, "gpu_start_s", "gpu_end_s")
                        a, b = row["gpu"]
                        if a <= 0 or b <= a or a < row["cpu"][1]:
                            raise ValueError("incompatible GPU times marked ok")
                elif kind == "present" and status in ("shown", "unshown", "missing"):
                    ident = natural(fields, "ticket")
                    row.update(resource=natural(fields, "resource"), enqueue=seconds(fields, "enqueue_s"))
                    if status == "shown":
                        row["shown"] = seconds(fields, "present_s")
                        if row["shown"] <= 0 or row["shown"] < row["enqueue"]:
                            raise ValueError("incompatible display time marked shown")
                else:
                    raise ValueError("unknown callback status")
                row["id"] = ident
            else:
                raise ValueError("unknown event")
            key = kind, ident
            if key in sessions[session]:
                raise ValueError("duplicate event or concatenated process launches")
            sessions[session][key] = row
        except (KeyError, ValueError, OverflowError) as exc:
            raise ValueError(f"line {line_num}: {exc}") from exc
    if not sessions:
        raise ValueError("no supported [rb-parallel] events")
    return sessions


def summarize(sessions):
    summaries = {}
    trace = []
    for pid, (session, records) in enumerate(sorted(sessions.items()), 1):
        trace.append(dict(ph="M", name="process_name", pid=pid, tid=0, args={"name": f"S2Arm session {session}"}))
        for tid, label in enumerate(("CPU producer window", "GPU main queue", "Display"), 1):
            trace.append(dict(ph="M", name="thread_name", pid=pid, tid=tid, args={"name": label}))
        frames = defaultdict(lambda: {"cpu": [], "gpu": [], "present": [], "missing": 0, "thread_ns": []})
        for row in records.values():
            if "frame" not in row:
                continue
            current = frames[row["frame"]]
            details = {k: str(v) if k in ("id", "sub", "frame", "resource") else v
                       for k, v in row.items() if k not in ("cpu", "gpu", "shown")}
            for field, tid in (("cpu", 1), ("gpu", 2)):
                if field in row:
                    a, b = row[field]
                    current[field].append((a, b))
                    trace.append(dict(pid=pid, tid=tid, ph="X", name=row["reason"],
                                      ts=a * 1e6, dur=(b-a) * 1e6, args=details))
            if row["event"] == "present":
                current["present"].append(row)
                if "shown" in row:
                    trace.append(dict(pid=pid, tid=3, ph="i", s="t", name="Presented",
                                      ts=row["shown"] * 1e6, args=details))
            else:
                if row["status"] != "ok":
                    current["missing"] += 1
                if "prep_thread_ns" in row:
                    current["thread_ns"].append(row["prep_thread_ns"])
        all_cpu = union(s for f in frames.values() for s in f["cpu"])
        all_gpu = union(s for f in frames.values() for s in f["gpu"])
        overlap = duration(intersect(all_cpu, all_gpu))
        per_frame = []
        presents = []
        known_pairs = 0
        for frame, data in sorted(frames.items()):
            cpu, gpu = union(data["cpu"]), union(data["gpu"])
            report = {"frame": frame, "cb_callbacks": len(data["cpu"]), "unavailable_gpu_intervals": data["missing"],
                      "producer_window_union_ms": duration(cpu)*1e3 if cpu else None,
                      "producer_thread_cpu_ms": sum(data["thread_ns"])*1e-6
                        if data["cpu"] and len(data["thread_ns"]) == len(data["cpu"]) else None,
                      "gpu_envelope_union_ms": duration(gpu)*1e3 if gpu else None,
                      "next_frame_overlap_ms": None, "next_frame_gpu_covered_percent": None}
            following = frames.get(frame+1)
            if following and gpu and following["cpu"] and not data["missing"]:
                shared = duration(intersect(gpu, union(following["cpu"])))
                report.update(next_frame_overlap_ms=1e3*shared, next_frame_gpu_covered_percent=100*shared/duration(gpu))
                known_pairs += 1
            for p in data["present"]:
                if "shown" in p:
                    presents.append((p["id"], frame, p["shown"], p["enqueue"]))
            per_frame.append(report)
        presents.sort()
        gaps = [(b[2]-a[2])*1e3 for a,b in zip(presents, presents[1:])
                if b[0] == a[0]+1 and b[1] == a[1]+1 and b[2] > a[2]]
        by_display_time = sorted(presents, key=lambda p: (p[2], p[0]))
        observed_gaps = [(b[2]-a[2])*1e3 for a,b in zip(by_display_time, by_display_time[1:])]
        crossed = sum(b[0] != a[0]+1 or b[1] != a[1]+1
                      for a,b in zip(by_display_time, by_display_time[1:]))
        cb_count = sum(r["event"] == "cb" for r in records.values())
        present_count = sum(r["event"] == "present" for r in records.values())
        end = records.get(("window_end", None))
        limits = sorted(r["stream"] for r in records.values() if r["event"] == "limit")
        summaries[session] = {
            "window": records.get(("begin", None)), "window_end": end, "limits_reported": limits,
            "reservations_match_callbacks": None if end is None else
                end["cb_reserved"] == cb_count and end["present_reserved"] == present_count,
            "cb_callbacks": cb_count, "unavailable_gpu_intervals": sum(f["missing"] for f in frames.values()),
            "presentation_callbacks": present_count, "shown_callbacks": len(presents),
            "unshown_callbacks": sum(r.get("status") == "unshown" for r in records.values()),
            "missing_display_time": sum(r["event"] == "present" and r["status"] == "missing" for r in records.values()),
            "observed_cpu_window_union_ms": duration(all_cpu)*1e3 if all_cpu else None,
            "observed_gpu_envelope_union_ms": duration(all_gpu)*1e3 if all_gpu else None,
            "observed_overlap_ms": overlap*1e3 if all_cpu and all_gpu else None,
            "observed_gpu_covered_percent": 100*overlap/duration(all_gpu) if all_cpu and all_gpu else None,
            "eligible_next_frame_pairs": known_pairs,
            "observed_gaps_between_main_queue_gpu_intervals_ms": distribution(
                [(b[0]-a[1])*1e3 for a,b in zip(all_gpu, all_gpu[1:])]),
            "observed_display_intervals": len(observed_gaps),
            "observed_display_interval_ms": distribution(observed_gaps),
            "observed_display_intervals_crossing_frame_or_ticket_gaps": crossed,
            "consecutive_presentation_intervals": len(gaps),
            "consecutive_presentation_interval_ms": distribution(gaps),
            "ticket_enqueue_to_display_ms": distribution([(stamp-enqueue)*1e3 for _,_,stamp,enqueue in presents]),
            "frames": per_frame}
    return summaries, {"traceEvents": trace, "displayTimeUnit": "ms"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="one session log file from a single process launch")
    parser.add_argument("--timeline", type=Path, help="write a trace for Perfetto")
    args = parser.parse_args()
    try:
        with args.log.open(encoding="utf-8") as stream:
            summary, trace = summarize(read_trace(stream))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.timeline:
        args.timeline.write_text(json.dumps(trace, allow_nan=False))
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
