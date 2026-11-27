#!/usr/bin/env python3
"""Summarize private S2Arm endurance captures and score independently labeled holdout runs."""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import re
from pathlib import Path
from statistics import median

NS = 1_000_000_000
GAP_NS = 10 * NS
FIELDS = re.compile(r"(\w+)=(-?\d+|[a-z_]+)\b")
LEGACY = re.compile(
    r"\[nvn\] timing up to frame (\d+):.*thermal state (\d+); fixed GPU probe ([0-9.]+) ms"
)

CONFIGURATIONS = {"historical", "reactive", "observe_v2", "active_v2"}
MARKERS = ("RB-ENERGY-V2", "RB-ENERGY-PROBE", "RB-ENERGY-SPEC", "RB-ARCHIVE-ADMISSION")


def read_log(path: Path) -> tuple[dict, list[tuple[int, int, float]]]:
    events = {kind: [] for kind in MARKERS}
    legacy = []
    with path.open(encoding="utf-8", errors="replace") as log:
        for line in log:
            for marker in MARKERS:
                token = f"[{marker}] "
                if token in line:
                    events[marker].append({
                        key: int(value) if value.lstrip("-").isdigit() else value
                        for key, value in FIELDS.findall(line.split(token, 1)[1])
                    })
                    break
            else:
                if match := LEGACY.search(line):
                    legacy.append((int(match[1]), int(match[2]), float(match[3])))
    return events, legacy


def quantiles(values: list[float]) -> dict | None:
    if not values:
        return None
    values = sorted(values)
    return {f"p{pc}": values[math.ceil(len(values) * pc / 100) - 1] for pc in (50, 95, 99)}


def windows(knots: list[dict], first: int, last: int) -> tuple[dict, dict]:
    states, thermal = {}, {}
    for i, row in enumerate(knots):
        if i + 1 == len(knots):
            break
        start = max(first, row["t_ns"])
        # A long gap can hide a focus change, pause or transition.
        stop = min(last, knots[i + 1]["t_ns"], row["t_ns"] + GAP_NS)
        if stop <= start:
            continue
        state = row["state"]
        states[state] = states.get(state, 0) + (stop - start)
        key = str(row["thermal"])
        thermal[key] = thermal.get(key, 0) + (stop - start)
    return states, thermal


def validate_episodes(truth: list[dict], first: int, last: int) -> None:
    starts = [e["start_ns"] for e in truth]
    if starts != sorted(set(starts)) or any(
        not first <= e["start_ns"] < e["end_ns"] <= last for e in truth
    ) or any(a["end_ns"] > b["start_ns"] for a, b in zip(truth, truth[1:])):
        raise ValueError("truth episodes must be ordered, distinct, non-overlapping and inside the window")


def score_warnings(knots: list[dict], truth: list[dict], first: int, last: int, horizon: int) -> dict:
    warnings = []
    previous = None
    for row in knots:
        if first <= row["t_ns"] < last and row["state"] == "prevent" and previous != "prevent":
            warnings.append(row["t_ns"])
        previous = row["state"]
    # Episodes without two timely observations in their forecast window are
    # reported as unscorable. Their absence cannot improve accuracy.
    decided = [r["t_ns"] for r in knots if r.get("observed_ns", 0) and r.get("eligible") == 1]
    measurable = {i for i, event in enumerate(truth) if
                  sum(max(first, event["start_ns"] - horizon) <= t < event["start_ns"] for t in decided) >= 2}
    used = set()
    leads = []
    false_alarms = 0
    censored_warnings = 0
    for warning in warnings:
        match = next((i for i, event in enumerate(truth) if i not in used and
                      warning < event["start_ns"] <= warning + horizon), None)
        if match is not None and match in measurable:
            used.add(match)
            leads.append((truth[match]["start_ns"] - warning) / NS)
        elif match is not None or warning + horizon > last:
            censored_warnings += 1
        else:
            false_alarms += 1
    misses = len(measurable) - len(leads)
    evaluated = len(leads) + false_alarms
    return {
        "true_warnings": len(leads), "false_warnings": false_alarms, "missed_episodes": misses,
        "unscorable_episodes": len(truth) - len(measurable),
        "warnings_censored_at_end_or_gap": censored_warnings, "lead_s": leads,
        "false_warning_percent": 100 * false_alarms / evaluated if evaluated else None,
        "missed_episode_percent": 100 * misses / len(measurable) if measurable else None,
    }


def load_cadence(path: Path | None) -> dict | None:
    if path is None:
        return None
    data = json.loads(path.read_text())
    return {key: data.get(key) for key in
            ("complete", "cadence_valid", "metric", "reason", "checkpoints")}


def native_windows(path: Path, first: int, last: int) -> dict:
    """Read native frame timestamps from the same clock as the declared window."""
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    frames = [int(row["t_ns"]) for row in rows]
    if frames != sorted(set(frames)) or any(t < first or t >= last for t in frames):
        raise ValueError("native frame CSV timestamps must be distinct, chronological and inside the window")
    minute = 60 * NS
    samples = {f"minute_{n}": (first + (n - 1) * minute, first + n * minute)
               for n in (1, 5, 10, 20, 30) if first + n * minute <= last}
    if last - first >= 5 * minute:
        samples.update(first_five=(first, first + 5 * minute), last_five=(last - 5 * minute, last))
    out = {}
    for name, (start, end) in samples.items():
        lo, hi = bisect.bisect_left(frames, start), bisect.bisect_left(frames, end)
        points = frames[lo:hi]
        intervals = [(b - a) / 1e6 for a, b in zip(points, points[1:])]
        values = {}
        for key in ("gpu_exec_ns", "required_wait_ns"):
            measures = [int(row[key]) / 1e6 for row in rows[lo:hi] if row.get(key)]
            if any(v < 0 for v in measures):
                raise ValueError(f"negative native frame duration in {key}")
            values[key.removesuffix("_ns") + "_ms"] = {
                "coverage_frames": len(measures), "quantiles": quantiles(measures),
            }
        out[name] = {
            "native_frames": hi - lo, "duration_s": (end - start) / NS,
            "native_fps": (hi - lo) * NS / (end - start) if points else None,
            "frametime_ms": quantiles(intervals),
            "intervals_over_100_ms": sum(v > 100 for v in intervals),
            "intervals_over_500_ms": sum(v > 500 for v in intervals),
            "edge_coverage_ms": [((points[0] - start) / 1e6), ((end - points[-1]) / 1e6)] if points else None,
            **values,
        }
    return out


def summarize(session: dict, root: Path, horizon_s: int) -> dict:
    identifier, configuration, split = (session[k] for k in ("id", "configuration", "split"))
    if configuration not in CONFIGURATIONS or split not in {"calibrate", "holdout", "ab"}:
        raise ValueError(f"{identifier}: unknown configuration or split")
    if session.get("source") not in {"device", "synthetic"}:
        raise ValueError(f"{identifier}: source must identify device or synthetic data")
    first, last = session["start_ns"], session["end_ns"]
    if not isinstance(first, int) or not isinstance(last, int) or not 0 < first < last:
        raise ValueError(f"{identifier}: expected bounds in the engine's CLOCK_MONOTONIC ns")
    events, legacy = read_log(root / session["host_log"])
    states = sorted((e for e in events["RB-ENERGY-V2"] if
                     0 < e.get("t_ns", 0) and "state" in e and "thermal" in e),
                    key=lambda e: e["t_ns"])
    if configuration == "observe_v2" and any(e.get("applied_limit", 0) for e in states):
        raise ValueError(f"{identifier}: observation-only log contains active admissions")
    raw_probes = [e for e in events["RB-ENERGY-PROBE"] if
                  first <= e.get("observed_ns", 0) < last and e.get("gpu_ns", 0) > 0]
    decided = [e for e in states if first <= e.get("observed_ns", 0) < last]
    samples = [e for e in states if first <= e["t_ns"] < last]
    observed, thermal = windows(states, first, last)
    known = sum(observed.values())
    truth = session.get("truth")
    if truth is not None:
        if not session.get("truth_source"):
            raise ValueError(f"{identifier}: independent episode labels need a source")
        if session["source"] == "device" and not session.get("identity"):
            raise ValueError(f"{identifier}: document the device, build and workload identity")
        validate_episodes(truth, first, last)
    scoring = truth is not None and configuration == "observe_v2" and split == "holdout"
    if scoring and not states:
        raise ValueError(f"{identifier}: holdout scoring requires observation timing")
    def probe_stats(field: str) -> dict | None:
        return quantiles([e[field] / 1e6 for e in raw_probes if e.get(field, -1) >= 0])
    report = {
        "id": identifier, "configuration": configuration, "source": session["source"],
        "split": split, "identity": session.get("identity"),
        "duration_s": (last - first) / NS,
        "states_observed_s": {state: ns / NS for state, ns in observed.items()},
        "unknown_s": (last - first - known) / NS,
        "thermal_percent_of_window_observed": {level: 100 * ns / (last - first) for level, ns in thermal.items()},
        "candidate_slow_time_s": observed.get("slow", 0) / NS if known else None,
        "first_candidate_slow_s": next(((e["t_ns"] - first) / NS for e in samples if e["state"] == "slow"), None),
        "probe_samples": len(raw_probes),
        "decision_samples": len(decided),
        "probe_execution_ms": probe_stats("gpu_ns"),
        "probe_before_execution_ms": probe_stats("enqueue_to_gpu_ns"),
        "probe_encode_cpu_ms": probe_stats("encode_cpu_ns"),
        "sample_age_ms": quantiles([(e["t_ns"] - e["observed_ns"]) / 1e6 for e in decided]),
        "legacy_probe_rows": len(legacy),
        "reactive_rows": len(events["RB-ENERGY-SPEC"]),
        "archive": events["RB-ARCHIVE-ADMISSION"] or None,
        "native_cadence": load_cadence(root / session["cadence"]) if "cadence" in session else None,
        "native_windows": native_windows(root / session["native_frames_csv"], first, last)
                          if "native_frames_csv" in session else None,
        "phase_marks": session.get("phase_marks"),
        "independent_power": session.get("power_measurement"),
        "independent_windows": session.get("measurements"),
        "independently_labeled_episodes": None if truth is None else {
            "count": len(truth),
            "first_slow_s": (truth[0]["start_ns"] - first) / NS if truth else None,
            "total_slow_s": sum(e["end_ns"] - e["start_ns"] for e in truth) / NS,
        },
        "holdout": score_warnings(states, truth, first, last, horizon_s * NS) if scoring else None,
    }
    for key in ("optional_admitted", "foreground_admitted"):
        counts = [e[key] for e in samples if key in e]
        report[key + "_per_s_observed"] = (
            (counts[-1] - counts[0]) * NS / (samples[-1]["t_ns"] - samples[0]["t_ns"])
            if len(counts) == len(samples) and len(counts) > 1 and counts == sorted(counts)
            and samples[-1]["t_ns"] > samples[0]["t_ns"] else None
        )
    return report


def paired_deltas(requests: list[dict], reports: list[dict]) -> list[dict]:
    by_id = {r["id"]: r for r in reports}
    pairs = []
    for request in requests:
        before, after = by_id[request["a"]], by_id[request["b"]]
        if not before["identity"] or before["identity"] != after["identity"]:
            raise ValueError("A/B pairs need matching device, build and workload identity")
        if before["source"] != after["source"] or before["duration_s"] != after["duration_s"]:
            raise ValueError("A/B pairs need matching duration and source")
        delta = {}
        for name in ("first_five", "last_five", "minute_1", "minute_5", "minute_10", "minute_20", "minute_30"):
            a = (before["native_windows"] or {}).get(name)
            b = (after["native_windows"] or {}).get(name)
            if not a or not b or a["native_fps"] is None or b["native_fps"] is None:
                continue
            delta[name] = {"native_fps": b["native_fps"] - a["native_fps"]}
            if a["frametime_ms"] and b["frametime_ms"]:
                delta[name]["frametime_ms"] = {
                    key: b["frametime_ms"][key] - a["frametime_ms"][key] for key in ("p50", "p95", "p99")
                }
        pairs.append({"a": before["id"], "b": after["id"], "native_window_deltas_b_minus_a": delta})
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--horizon-s", type=int, default=8, help="fix on calibration data before evaluating holdout")
    args = parser.parse_args()
    if args.horizon_s <= 0:
        parser.error("warning horizon must be positive")
    manifest = json.loads(args.manifest.read_text())
    sessions = manifest["sessions"]
    identifiers = [s["id"] for s in sessions]
    # Labels and tuning inputs are separated by complete session, never by neighboring windows.
    logfiles = [(args.manifest.parent / s["host_log"]).resolve() for s in sessions]
    if len(set(identifiers)) != len(identifiers) or len(set(logfiles)) != len(logfiles):
        parser.error("each session and host log must appear in one split only")
    try:
        reports = [summarize(session, args.manifest.parent, args.horizon_s) for session in sessions]
        comparisons = paired_deltas(manifest.get("pairs", []), reports)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    observed = [r["holdout"] for r in reports if r["source"] == "device" and r["holdout"] is not None]
    leads = [lead for score in observed for lead in score["lead_s"]]
    result = {"sessions": reports, "pairs": comparisons, "device_holdout_sessions": len(observed),
              "device_median_warning_lead_s": median(leads) if leads else None}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
