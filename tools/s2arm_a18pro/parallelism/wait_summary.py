#!/usr/bin/env python3
"""Read existing NVN wait counters from one session's host.log or perf.txt. No device-side hooks."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re


SYNC_COUNTS = ("queue_wait_records", "queue_wait_drains", "allocator_reset_deferred",
               "visibility_reserves", "pieces_without_visibility", "visibility_waits", "visibility_failures")
SYNC_TIMES = ("queue_wait_drain_ms", "allocator_wait_ms", "visibility_wait_ms")
LONG_WAITS = ("submit_lock_ms", "gpu_fences_ms", "encode_or_uniform_copy_ms",
              "readback_or_upload_slot_ms", "owed_cross_queue_fences_ms")
M = r"(-?[0-9]+(?:\.[0-9]+)?)"
LONG = re.compile(r"\bframe (\d+) \(" + M + r" s\) whole frame " + M + r" ms")
BLOCKED = re.compile(r"presenting thread blocked on the submit lock " + M + r" ms, GPU fences " + M
                     + r" ms, the encode thread " + M + r" ms, readbacks and upload slots " + M
                     + r" ms, owed cross-queue fences " + M + r" ms")
CORES = re.compile(r"thread cores up to frame (\d+): encode thread " + M + r" ms a frame, " + M
                   + r"% on performance cores; present thread " + M + r" ms a frame, " + M + r"% on performance cores")
PIECE = re.compile(r"up to submission (\d+): (\d+) pieces handed over without waiting for the encode thread, "
                   r"(\d+) submit calls waited for it once at their end \(" + M + r" ms in all\)")
REPLAY = re.compile(r"stopped: submitted=(\d+) completed=(\d+) admission_wait_ms=" + M + r"(?:\s|$)")


def count(raw):
    if not re.fullmatch(r"[0-9]{1,20}", raw) or int(raw) >= 2**64:
        raise ValueError("invalid unsigned counter")
    return int(raw)


def duration(raw, unavailable=False):
    if not re.fullmatch(r"-?[0-9]{1,20}(?:\.[0-9]{1,9})?", raw):
        raise ValueError("invalid duration")
    value = Decimal(raw)
    if unavailable and value == -1:
        return None
    if value < 0:
        raise ValueError("negative duration")
    return value


def append_sample(rows, label, position, counters):
    previous = rows[-1] if rows else None
    delta = None
    if previous:
        if position <= previous[label]:
            raise ValueError(f"nonincreasing {label}, split captures by session")
        delta = {k: v - previous["cumulative"][k] for k, v in counters.items()}
        if any(v < 0 for v in delta.values()):
            raise ValueError("cumulative counter reset, split captures by session")
    rows.append({label: position, "previous_" + label: previous[label] if previous else None,
                 "cumulative": counters, "window_delta": delta})


def required(pattern, text):
    hit = pattern.search(text)
    if not hit:
        raise ValueError("recognized NVN report is malformed or truncated")
    return hit.groups()


def summarize(lines):
    sync, pieces, threads, long_frames = [], [], [], []
    session = None
    stop = None
    for lineno, line in enumerate(lines, 1):
        try:
            if "[rb-parallel] " in line and "event=begin" in line.split():
                if session is not None or any((sync, pieces, threads, long_frames, stop)):
                    raise ValueError("multiple sessions or samples preceding session marker")
                version, ident = required(re.compile(r"\[rb-parallel\] v=(\d+) session=(\d+) event=begin\b"), line)
                if version != "1" or count(ident) == 0:
                    raise ValueError("unsupported trace session")
                session = count(ident)
            elif "[rb-cpu-gpu-sync] cumulative " in line:
                raw = line.partition("[rb-cpu-gpu-sync] cumulative ")[2]
                pairs = re.findall(r"\b([a-z_]+)=([^\s]+)", raw)
                fields = dict(pairs)
                if len(fields) != len(pairs):
                    raise ValueError("duplicate counter")
                counters = {k: count(fields[k]) for k in SYNC_COUNTS}
                counters.update({k: duration(fields[k]) for k in SYNC_TIMES})
                append_sample(sync, "report_frame_label", count(fields["frame"]), counters)
            elif "[rb-piece] up to submission " in line:
                pos, held, waited, elapsed = required(PIECE, line)
                append_sample(pieces, "submission", count(pos), {
                    "pieces_handed_over": count(held), "submit_calls_with_end_drain": count(waited),
                    "accounted_encode_wait_ms": duration(elapsed)})
            elif "[nvn] thread cores up to frame " in line:
                end, enc, epct, present, ppct = required(CORES, line)
                end = count(end)
                if threads and end <= threads[-1]["end_frame"]:
                    raise ValueError("repeated or decreasing CPU report frame")
                if any(duration(v) > 100 for v in (epct, ppct)):
                    raise ValueError("invalid CPU residency percentage")
                threads.append({"end_frame": end, "encode_cpu_ms_per_frame": duration(enc),
                                "present_cpu_ms_per_frame": duration(present)})
            elif "[rb-replay] stopped:" in line:
                submitted, completed, elapsed = required(REPLAY, line)
                if stop or count(completed) > count(submitted):
                    raise ValueError("unexpected replay stop counters or multiple sessions")
                stop = {"submitted": count(submitted), "completed": count(completed),
                        "replay_join_ms": duration(elapsed)}
            elif "[longframe]" in line and (frame := LONG.search(line)):
                ident = count(frame[1])
                if long_frames and ident <= long_frames[-1]["frame"]:
                    raise ValueError("repeated or decreasing long-frame ID")
                reported = None
                if "presenting thread blocked on the submit lock" in line:
                    values = required(BLOCKED, line)
                    reported = {k: duration(v, unavailable=True) for k, v in zip(LONG_WAITS, values)}
                long_frames.append({"frame": ident, "reported_whole_frame_ms": duration(frame[3]),
                                    "presenting_thread_waits": reported})
        except (KeyError, ValueError) as error:
            raise ValueError(f"line {lineno}: {error}") from error
    if not any((sync, pieces, threads, long_frames, stop)):
        raise ValueError("no supported NVN wait reports")
    return {"schema": 1, "trace_session_id": session,
            "scope": "One session per source. An unmarked source has no inferred session ID.",
            "presenting_thread_long_frames": long_frames,
            "sync_report_windows": sync, "submission_report_windows": pieces,
            "thread_cpu_windows": threads, "replay_worker_stop": stop,
            "interpretation": {
                "long_frames": "Selected late frames only. Times are from the presenting thread. Null means unavailable.",
                "sync": "Differences between periodic counter samples. Spread reports keep the boundary label although the count sample may be taken 12 frames later. The first delta is unavailable.",
                "pieces": "Cumulative by submission, including deferred drain accounting. No corresponding frame ID is available.",
                "cpu": "Reported worker CPU per frame over a reporting window, not individual encode blocks.",
                "replay": "Session total time spent joining pending ordered replay jobs. Excludes initial admission mutex acquisition.",
                "accounting": "Do not sum these populations or assume that elapsed wait time equals GPU idle time."}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="One session, one file; keep host and perf logs separate")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        with args.log.open(encoding="utf-8", errors="replace") as src:
            result = summarize(src)
        report = json.dumps(result, indent=2, default=float, allow_nan=False) + "\n"
        if args.out:
            args.out.write_text(report, encoding="utf-8")
        else:
            print(report, end="")
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
