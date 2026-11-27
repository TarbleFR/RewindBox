"""Summarize balanced offscreen batches. Durations are in ms unless stated otherwise."""
import csv
from itertools import groupby
from math import ceil, isfinite
from statistics import median
import sys


ORDERS = ((1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1), (0, 1, 3, 2))
MEMORY = ("footprint_before", "footprint_after", "device_allocated")
GPU_FIELDS = ("gpu_span_p50_ms", "gpu_span_p95_ms", "gpu_end_interval_p50_ms",
              "gpu_end_interval_p95_ms", "gpu_end_interval_p99_ms", "gpu_end_intervals_gt_16_67ms",
              "gpu_union_pct_batch_wall", "adjacent_overlap_pairs", "adjacent_pairs",
              "adjacent_overlap_ms", "adjacent_overlap_pct_next_encode_wall",
              "start_to_gpu_end_p95_ms", "adjacent_clocked_pairs", "adjacent_clocked_overlap_pairs",
              "adjacent_overlap_pct_all_encode_lower", "adjacent_overlap_pct_all_encode_upper",
              "gpu_union_pct_batch_wall_lower", "gpu_union_pct_batch_wall_upper")


def percentile(values, q):
    return sorted(values)[ceil(q * len(values)) - 1]


def union_duration(intervals):
    total = 0
    previous_end = 0
    for start, end in sorted(intervals):
        total += max(0, end - max(start, previous_end))
        previous_end = max(previous_end, end)
    return total


def summarize_batch(raw, block, position, policy):
    if [int(r["frame"]) for r in raw] != list(range(180)):
        raise ValueError(f"incomplete or reordered frames in block {block}, policy {policy}")
    batch = [{k: float(v) for k, v in r.items()} for r in raw]
    for r in batch:
        if (not all(isfinite(v) for v in r.values())
                or not 0 < r["start"] <= r["after_wait"] <= r["before_commit"] <= r["committed"]
                or r["callback"] < r["before_commit"] or not 0 <= r["gpu_start"] <= r["gpu_end"]
                or not 0 <= r["encode_thread_cpu_s"] <= r["encode_cpu_s"]
                or r["admission_depth"] not in (1, 2, 3) or (policy and r["admission_depth"] != policy)):
            raise ValueError(f"invalid sample in block {block}, policy {policy}, frame {r['frame']}")
    for first, second in zip(batch, batch[1:]):
        if first["committed"] > second["start"]:
            raise ValueError("nonsequential submission timestamps")
    def durations(start, end):
        return [(r[end] - r[start]) * 1000 for r in batch]
    def cpu_times(key):
        return [1000 * r[key] for r in batch]
    elapsed = max(r["callback"] for r in batch) - batch[0]["start"]
    if elapsed <= 0:
        raise ValueError("empty completion interval")
    waits = durations("start", "after_wait")
    latency = durations("start", "callback")
    unresolved = sum(not 0 < r["gpu_start"] < r["gpu_end"] for r in batch)
    # Reject intervals outside their own host commit/callback envelope for cross-clock metrics.
    bad_clock = sum(r["gpu_start"] > 0 and r["gpu_end"] > r["gpu_start"]
                    and (r["gpu_start"] < r["before_commit"] or r["gpu_end"] > r["callback"]) for r in batch)
    result = dict(block=block, position=position, policy=policy or "adaptive", frames=len(batch),
                  duration_s=elapsed, offscreen_completions_per_s=len(batch)/elapsed,
                  admission_d1=sum(r["admission_depth"] == 1 for r in batch),
                  admission_d2=sum(r["admission_depth"] == 2 for r in batch),
                  admission_d3=sum(r["admission_depth"] == 3 for r in batch),
                  slot_wait_p50_ms=median(waits), slot_wait_p95_ms=percentile(waits, .95),
                  slot_wait_total_ms=sum(waits), encode_wall_p95_ms=percentile(durations("after_wait", "before_commit"), .95),
                  encode_thread_cpu_p95_ms=percentile(cpu_times("encode_thread_cpu_s"), .95),
                  encode_commit_thread_cpu_p95_ms=percentile(cpu_times("encode_cpu_s"), .95),
                  start_to_callback_p95_ms=percentile(latency, .95), start_to_callback_p99_ms=percentile(latency, .99),
                  unresolved_gpu_frames=unresolved, gpu_host_clock_mismatches=bad_clock)
    result.update(dict.fromkeys(GPU_FIELDS))
    if not unresolved:
        times = sorted(r["gpu_end"] for r in batch)
        gaps = [1000 * (b-a) for a, b in zip(times, times[1:])]
        spans = durations("gpu_start", "gpu_end")
        result.update(gpu_span_p50_ms=median(spans), gpu_span_p95_ms=percentile(spans, .95),
                      gpu_end_interval_p50_ms=median(gaps), gpu_end_interval_p95_ms=percentile(gaps, .95),
                      gpu_end_interval_p99_ms=percentile(gaps, .99),
                      gpu_end_intervals_gt_16_67ms=sum(gap > 1000/60 for gap in gaps))
    if not bad_clock:
        # A partial trace proves overlap only where the preceding frame has valid GPU times.
        # Missing intervals can fall anywhere inside that buffer's commit/callback envelope.
        def clocked(r):
            return 0 < r["gpu_start"] < r["gpu_end"]
        observed, possible = [], []
        for r in batch:
            if clocked(r):
                observed.append((r["gpu_start"], r["gpu_end"]))
                possible.append(observed[-1])
            else:
                possible.append((r["before_commit"], r["callback"]))
        def overlap(nxt, interval):
            return max(0, min(interval[1], nxt["before_commit"]) - max(interval[0], nxt["after_wait"]))
        adjacent = []
        possible_adjacent = []
        for i, (prev, nxt) in enumerate(zip(batch, batch[1:])):
            length = overlap(nxt, possible[i])
            possible_adjacent.append(length)
            if clocked(prev):
                adjacent.append(length)
        encodes = sum(r["before_commit"] - r["after_wait"] for r in batch[1:])
        result.update(adjacent_clocked_pairs=len(adjacent), adjacent_clocked_overlap_pairs=sum(x > 0 for x in adjacent),
                      adjacent_overlap_pct_all_encode_lower=100 * sum(adjacent) / encodes if encodes else None,
                      adjacent_overlap_pct_all_encode_upper=100 * sum(possible_adjacent) / encodes if encodes else None,
                      gpu_union_pct_batch_wall_lower=100 * union_duration(observed) / elapsed,
                      gpu_union_pct_batch_wall_upper=100 * union_duration(possible) / elapsed)
        if not unresolved:
            # Coverage is time spanned by command buffers, not hardware utilization.
            result.update(gpu_union_pct_batch_wall=result["gpu_union_pct_batch_wall_lower"],
                          adjacent_overlap_pairs=result["adjacent_clocked_overlap_pairs"], adjacent_pairs=len(adjacent),
                          adjacent_overlap_ms=1000 * sum(adjacent),
                          adjacent_overlap_pct_next_encode_wall=result["adjacent_overlap_pct_all_encode_lower"],
                          start_to_gpu_end_p95_ms=percentile(durations("start", "gpu_end"), .95))
    for key in MEMORY:
        values = {int(r[key]) for r in raw}
        if len(values) != 1:
            raise ValueError(f"inconsistent {key} in batch")
        result[key] = values.pop() or None
    result["final_surfaces_full_rgba_oracle"] = "3/3"
    return result


def summarize_depths(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    keys = [(block, policy) for block, order in enumerate(ORDERS, 1) for policy in order]
    batches = [(k, list(v)) for k, v in groupby(rows, lambda r: (int(r["pair"]), int(r["limit"])))]
    if [key for key, _ in batches] != keys:
        raise ValueError("missing or reordered measured block/policy")
    writer = csv.writer(sys.stdout, lineterminator="\n")
    for i, ((block, policy), raw) in enumerate(batches):
        result = summarize_batch(raw, block, i % 4 + 1, policy)
        if i == 0:
            writer.writerow(result)
        writer.writerow(f"{v:.6f}" if isinstance(v, float) else v for v in result.values())
