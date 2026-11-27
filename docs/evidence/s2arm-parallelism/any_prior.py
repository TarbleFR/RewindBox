"""Bound encode-wall overlap with any preceding GPU command in the Apple offscreen trace."""
import argparse
import csv
import gzip
from itertools import groupby
from pathlib import Path
import sys


def covered_time(begin, end, intervals):
    """Intersect a CPU window with a union of GPU intervals, counting each instant once."""
    cursor = begin
    covered = 0.0
    for start, stop in sorted(intervals):
        if start >= end:
            break
        latest = min(end, stop)
        covered += max(0.0, latest - max(start, cursor))
        cursor = max(cursor, latest)
    return covered


def summarize_block(block, policy, rows):
    known = []
    possible = []
    lower = upper = total = 0.0
    observed = 0
    for frame, row in enumerate(rows):
        if int(row["frame"]) != frame:
            raise ValueError("missing or reordered frame")
        cpu_start = float(row["after_wait"])
        before_commit = float(row["before_commit"])
        cb_end = float(row["callback"])
        if not cpu_start <= before_commit <= cb_end:
            raise ValueError("invalid host interval")
        if frame:
            lo = covered_time(cpu_start, before_commit, known)
            hi = covered_time(cpu_start, before_commit, possible)
            observed += lo > 0
            lower += lo
            upper += hi
            total += before_commit - cpu_start
        start = float(row["gpu_start"])
        stop = float(row["gpu_end"])
        if not 0 <= start <= stop:
            raise ValueError("invalid GPU interval")
        interval = (before_commit, cb_end)
        if 0 < start < stop:
            if not before_commit <= start < stop <= cb_end:
                raise ValueError("incompatible clocks in GPU/host timing")
            interval = (start, stop)
            known.append(interval)
        possible.append(interval)
    if frame != 179 or total <= 0:
        raise ValueError("expected a complete batch with measurable encode time")
    return dict(block=block, policy=policy or "adaptive", pct_encode_wall_lower=100*lower/total,
                pct_encode_wall_upper=100*upper/total, observed_pairs_with_any_overlap=observed, encode_windows=frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_csv", type=Path)
    args = parser.parse_args()
    opener = gzip.open if args.raw_csv.suffix == ".gz" else open
    with opener(args.raw_csv, "rt", encoding="utf-8", newline="") as stream:
        grouped = groupby(csv.DictReader(stream), key=lambda r: (int(r["pair"]), int(r["limit"])))
        rows = [summarize_block(block, policy, batch) for (block, policy), batch in grouped]
    expected = {(b, p) for b in range(1, 5) for p in (1, 2, 3, "adaptive")}
    if len(rows) != 16 or {(r["block"], r["policy"]) for r in rows} != expected:
        raise ValueError("expected four blocks and four distinct policies per block")
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
