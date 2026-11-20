#!/usr/bin/env python3
"""Evaluate the host-heap target from three IPA 803 and three candidate windows.

Analysis only: no engine execution, network access, cache mutation or new test.
Pass --baseline LOG UUID three times and --candidate LOG UUID three times.
Each log must contain the selected RB-BENCH window and its complete RB-BENCH-VM
post-score census. Existing compare_benchmarks validation remains mandatory.

Exit codes: 0 = all four measured criteria met; 3 = valid comparison, target not
met; 2 = comparison refused or invalid arguments; 1 = output could not be written.
An accepted result describes these six observations, not a general FPS claim.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import compare_benchmarks as bench

VM_MARKER = b"[RB-BENCH-VM] "
BASELINE_BUILD = "803"
# Verified producer identity in ../rewind803/s2arm-identity803.json.
BASELINE_ENGINE = "342f534efc856eedeba9b085df291757bc942d41"
REPETITIONS = 3
TAG2_REDUCTION_BYTES = 250_000_000
UINT64_MAX = (1 << 64) - 1
VM_COVERAGE = "all_leaf_regions_encountered_to_end_of_map_over_time"
VM_COUNTS = (
    "regions", "virtual_bytes", "resident_pages", "compressed_logical_pages",
    "dirty_pages", "shared_now_private_pages", "reusable_pages",
    "reusable_count_unavailable_regions",
)
VM_SIDES = {
    "outside_guest_window", "inside_guest_window", "crossing_guest_window",
    "guest_window_unknown",
}
METRICS = (
    "tag2_compressed_logical_bytes", "process_pageins_median_per_10s",
    "display_p95_ms", "display_gt100_per_min",
)


def uint(value: Any, *, positive: bool = False) -> bool:
    return bench.integer(value) and int(positive) <= value <= UINT64_MAX


def vm_integer_boolean(value: Any) -> bool | None:
    # IPA 803 boxes two C int expressions, complete and external_pager_or_shadow,
    # as NSNumber 0/1. Accept only that exact encoding at these two sites.
    if isinstance(value, bool):
        return value
    if bench.integer(value) and value in (0, 1):
        return value == 1
    return None


def decode_record(raw: bytes, marker: bytes) -> dict:
    payload = raw.split(marker, 1)[1].strip().decode("utf-8")
    result = json.loads(payload, object_pairs_hook=bench.unique_object,
                        parse_constant=bench.reject_constant, parse_float=bench.finite_float)
    if not isinstance(result, dict):
        raise ValueError("record is not an object")
    return result


def read_vm(run: bench.Run) -> dict:
    """Never infer tag 2 from task ledgers or from an incomplete mapping walk."""
    issues_before = len(run.issues)
    rows: list[tuple[int, dict]] = []
    score_end_lines: list[int] = []
    digest = hashlib.sha256()
    size = 0
    try:
        with run.path.open("rb") as stream:
            for line_no, raw in enumerate(stream, 1):
                digest.update(raw)
                size += len(raw)
                marker = VM_MARKER if VM_MARKER in raw else bench.MARKER.encode()
                if marker not in raw:
                    continue
                if len(raw) > bench.MAX_RECORD_BYTES:
                    if marker == VM_MARKER:
                        run.issue("vm_oversized_record", f"line:{line_no}", "VM record exceeds the bounded parser limit.")
                    continue
                try:
                    record = decode_record(raw, marker)
                except (UnicodeDecodeError, ValueError) as exc:
                    if marker == VM_MARKER:
                        run.issue("vm_malformed_record", f"line:{line_no}", str(exc))
                    continue
                identifier = bench.uuid_text(record.get("id"))
                if marker == VM_MARKER and identifier is None:
                    run.issue("vm_id_missing", f"line:{line_no}", "A VM record without a UUID cannot safely be associated.")
                if identifier != run.selected_id or identifier is None:
                    continue
                if marker == VM_MARKER:
                    rows.append((line_no, record))
                elif record.get("type") == "end":
                    score_end_lines.append(line_no)
    except OSError as exc:
        run.issue("vm_input_unreadable", "vm.input", str(exc))
    if run.sha256 is not None and (digest.hexdigest() != run.sha256 or size != run.size_bytes):
        run.issue("input_changed_during_read", "input", "The log changed between score and VM reads; no mixed snapshot is accepted.")

    grouped: dict[str, list[tuple[int, dict]]] = {"begin": [], "mapping_tag": [], "end": []}
    for line_no, record in rows:
        event = record.get("event")
        if not bench.integer(record.get("schema")) or record.get("schema") != 1:
            run.issue("vm_schema_invalid", f"line:{line_no}", "Only VM schema 1 is accepted.")
        if record.get("phase") != "after_score":
            run.issue("vm_phase_invalid", f"line:{line_no}", "The mapping census must follow the score window.")
        if not isinstance(event, str) or event not in grouped:
            run.issue("vm_event_invalid", f"line:{line_no}", "Rejected, errored or unknown VM records prevent acceptance.")
        else:
            grouped[event].append((line_no, record))
    for event in ("begin", "end"):
        if len(grouped[event]) != 1:
            run.issue("vm_endpoint_not_unique", f"vm.{event}", f"Expected one {event}, observed {len(grouped[event])}.")
    report: dict = {"eligible": False, "tag2_compressed_logical_bytes": None,
                    "tag2_categories": [], "mapping_sums_may_count_aliases": True}
    if len(grouped["begin"]) != 1 or len(grouped["end"]) != 1:
        return report
    begin_line, begin = grouped["begin"][0]
    end_line, end = grouped["end"][0]
    generation = begin.get("generation")
    if not uint(generation, positive=True) or any(row.get("generation") != generation or
            not uint(row.get("generation"), positive=True) for _, row in rows):
        run.issue("vm_generation_mismatch", "vm.generation", "All VM records must identify one positive session generation.")
    if len(score_end_lines) != 1 or not score_end_lines[0] < begin_line < end_line or any(
            not begin_line < line < end_line for line, _ in grouped["mapping_tag"]):
        run.issue("vm_record_order_invalid", "vm.input", "Score end, VM begin, mapping rows and VM end must appear in that order.")
    expected = {
        "status": "complete", "complete": True, "reached_map_end": True,
        "begin_record_emitted": True, "counter_overflow": False, "coverage": VM_COVERAGE,
        "atomic_snapshot": False, "alias_deduplication": "none",
        "mapping_sums_may_count_aliases": True, "mapping_and_task_ledgers_are_additive": False,
    }
    for key, value in expected.items():
        observed = vm_integer_boolean(end.get(key)) if key == "complete" else end.get(key)
        if type(observed) is not type(value) or observed != value:
            run.issue("vm_coverage_invalid", f"vm.end.{key}", f"Required exported value: {value!r}.")
    page_bytes = begin.get("mapping_page_bytes")
    if not uint(page_bytes, positive=True) or not uint(end.get("mapping_page_bytes"), positive=True) or end.get("mapping_page_bytes") != page_bytes:
        run.issue("vm_page_size_invalid", "vm.mapping_page_bytes", "Begin and end must declare the same positive page size.")
    window = run.end.get("window")
    window = window if isinstance(window, dict) else {}
    times = [window.get("end_ns"), window.get("finalized_ns"), begin.get("requested_ns"),
             begin.get("started_ns"), end.get("ended_ns"), end.get("published_ns")]
    if not all(uint(t) for t in times) or times != sorted(times):
        run.issue("vm_clock_order_invalid", "vm.timestamps", "The VM request and walk must follow score finalization with monotonic timestamps.")
    for key in ("requested_ns", "started_ns"):
        if not uint(end.get(key)) or end.get(key) != begin.get(key):
            run.issue("vm_clock_identity_mismatch", f"vm.{key}", "Begin and end disagree about the same census.")
    for point, record, key in (("begin", begin, "ledger_begin"), ("end", end, "ledger_end")):
        ledger = record.get(key)
        if not isinstance(ledger, dict) or ledger.get("valid") is not True:
            run.issue("vm_ledger_unavailable", f"vm.{point}.{key}", "The complete census needs its associated valid task ledger.")

    totals = {key: 0 for key in VM_COUNTS}
    categories: set[tuple] = set()
    tag2_pages = 0
    for line_no, row in grouped["mapping_tag"]:
        tag, side = row.get("tag"), row.get("side")
        external = vm_integer_boolean(row.get("external_pager_or_shadow"))
        valid_key = uint(tag) and tag <= (1 << 32) - 1 and isinstance(side, str) and side in VM_SIDES and isinstance(external, bool)
        if not valid_key:
            run.issue("vm_mapping_category_invalid", f"line:{line_no}", "A numeric tag, known side and explicit external-pager boolean are required.")
        else:
            category = (tag, side, external)
            if category in categories:
                run.issue("vm_duplicate_category", f"line:{line_no}", "A tag/side/external-pager category was emitted more than once.")
            categories.add(category)
        counts = row.get("counts")
        valid_counts = isinstance(counts, dict) and all(uint(counts.get(key)) for key in VM_COUNTS)
        if not valid_counts or counts.get("regions", 0) < 1 or row.get("provisional_until_end") is not True:
            run.issue("vm_mapping_counts_invalid", f"line:{line_no}", "All nonnegative mapping counters and positive region coverage are required.")
            continue
        for key in VM_COUNTS:
            totals[key] += counts[key]
        if valid_key and tag == 2:
            tag2_pages += counts["compressed_logical_pages"]
            report["tag2_categories"].append({"side": side, "external_pager_or_shadow": external,
                                              "external_pager_or_shadow_source": row.get("external_pager_or_shadow"),
                                              "counts": counts})
    declared = end.get("mapping_counts")
    if not isinstance(declared, dict) or any(not uint(declared.get(key)) or
            not uint(totals[key]) or declared.get(key) != totals[key] for key in VM_COUNTS):
        run.issue("vm_mapping_totals_mismatch", "vm.end.mapping_counts", "All tag categories must sum exactly to the declared complete mapping totals.")
    if not uint(end.get("leaf_regions"), positive=True) or end.get("leaf_regions") != totals["regions"]:
        run.issue("vm_region_coverage_mismatch", "vm.end.leaf_regions", "Mapping rows must cover the declared positive number of leaf regions.")
    if not report["tag2_categories"]:
        run.issue("vm_tag2_missing", "vm.mapping_tag", "An absent tag 2 is unavailable, never an inferred zero.")
    tag2_bytes = tag2_pages * page_bytes if uint(page_bytes, positive=True) else None
    if not uint(tag2_bytes):
        run.issue("vm_tag2_bytes_invalid", "vm.tag2", "Page conversion must produce a representable nonnegative byte count.")
    report.update({"eligible": len(run.issues) == issues_before, "generation": generation,
                   "complete_source": end.get("complete"),
                   "mapping_page_bytes": page_bytes, "mapping_counts": declared,
                   "requested_ns": begin.get("requested_ns"), "started_ns": begin.get("started_ns"),
                   "ended_ns": end.get("ended_ns"), "coverage": end.get("coverage"),
                   "ledger_begin": begin.get("ledger_begin"), "ledger_end": end.get("ledger_end")})
    if report["eligible"]:
        report["tag2_compressed_logical_bytes"] = tag2_bytes
    return report


def window_metrics(run: bench.Run, vm: dict) -> tuple[dict, list]:
    rates: list[float | None] = []
    previous_elapsed = 0.0
    for index, sample in enumerate(run.samples):
        io = sample.get("process_io")
        count = io.get("pageins") if isinstance(io, dict) else None
        span, elapsed = sample.get("span_s"), sample.get("elapsed_s")
        rate = count * 10.0 / span if uint(count) and bench.numeric(span) and span > 0 else None
        if not bench.numeric(rate):
            rate = None
            run.issue("heap_pageins_unavailable", f"samples[{index}].process_io.pageins", "All 18 process page-in counts and measured spans are required; machine page-ins cannot substitute.")
        if bench.numeric(span) and bench.numeric(elapsed):
            # The baseline snapshot precedes the score start; preserve that
            # first span. Later spans must agree with the exported sample clock.
            expected = elapsed - previous_elapsed
            if (index == 0 and span + bench.EPSILON < elapsed) or (index > 0 and not bench.same_number(span, expected)):
                run.issue("heap_sample_span_inconsistent", f"samples[{index}].span_s", "The counter denominator disagrees with adjacent exported sample times.")
            previous_elapsed = elapsed
        rates.append(rate)
    complete = len(rates) == len(bench.NOMINAL_SAMPLES) and all(bench.numeric(rate) for rate in rates)
    if not complete:
        run.issue("heap_pageins_coverage_incomplete", "samples", "The page-in median requires exactly 18 available process observations.")
    display = run.end.get("display")
    display = display if isinstance(display, dict) else {}
    metrics = {"tag2_compressed_logical_bytes": vm["tag2_compressed_logical_bytes"],
               "process_pageins_median_per_10s": statistics.median(rates) if complete else None,
               "display_p95_ms": display.get("p95_ms"), "display_gt100_per_min": display.get("gt100_per_min")}
    for key, value in metrics.items():
        if not bench.numeric(value) or value < 0:
            run.issue("heap_required_metric_unavailable", f"metrics.{key}", "A missing, null or invalid acceptance metric prevents a result.")
    return metrics, rates


def dispersion(values: list) -> dict:
    complete = len(values) == REPETITIONS and all(bench.numeric(value) and value >= 0 for value in values)
    median = statistics.median(values) if complete else None
    return {"values_in_supplied_order": values, "available_count": sum(bench.numeric(v) for v in values),
            "required_count": REPETITIONS, "median": median,
            "minimum": min(values) if complete else None, "maximum": max(values) if complete else None,
            "range": max(values) - min(values) if complete else None,
            "median_absolute_deviation": statistics.median(abs(v - median) for v in values) if complete else None}


def analyze(inputs: dict[str, list[tuple[Path, str]]]) -> dict:
    runs, observations = [], []
    reasons = []
    for role, selected in inputs.items():
        for index, (path, identifier) in enumerate(selected, 1):
            run = bench.read_run(path, f"{role}[{index}]", identifier)
            vm = read_vm(run)
            metrics, rates = window_metrics(run, vm)
            runs.append(run)
            observations.append({"role": role, "repetition": index, "score": bench.run_report(run),
                                 "vm": vm, "metrics": metrics, "process_pageins_per_10s": rates})
    identifiers = [identifier for selected in inputs.values() for _, identifier in selected]
    if len(set(identifiers)) != 2 * REPETITIONS:
        reasons.append({"code": "duplicate_observation", "detail": "Six distinct UUIDs are required; a window cannot be counted twice."})
    for role in ("baseline", "candidate"):
        metadata = [o["score"].get("metadata") for o in observations if o["role"] == role]
        metadata = [m if isinstance(m, dict) else {} for m in metadata]
        if role == "baseline" and any(m.get("app_build") != BASELINE_BUILD for m in metadata):
            reasons.append({"code": "baseline_is_not_803", "detail": "Every baseline must explicitly identify app_build 803."})
        if role == "baseline" and any(m.get("engine_build") != BASELINE_ENGINE for m in metadata):
            reasons.append({"code": "baseline_engine_is_not_803", "detail": "The baseline engine must match the verified IPA 803 producer."})
        if role == "candidate" and any(m.get("app_build") == BASELINE_BUILD or m.get("engine_build") == BASELINE_ENGINE for m in metadata):
            reasons.append({"code": "candidate_is_baseline", "detail": "A new app and engine build are required for this candidate-versus-803 comparison."})
        for key in ("app_build", "engine_build"):
            values = [m.get(key) for m in metadata]
            if not all(bench.nonempty(v) for v in values) or any(v != values[0] for v in values):
                reasons.append({"code": "heterogeneous_builds", "role": role, "field": key,
                                "detail": "Each side must use one known app build and one known engine build."})
    pair_checks = []
    # Compare all 15 pairs, including within-version repetitions. This retains
    # every existing guard and prevents drifting conditions across the series.
    for a, b in itertools.combinations(runs, 2):
        result = bench.compare(a, b)
        pair_checks.append({"a": a.role, "b": b.role, "comparable": result["comparable"], "reasons": result["reasons"]})
    if any(not p["comparable"] for p in pair_checks):
        reasons.append({"code": "window_or_condition_refused", "detail": "See individual score reasons and pair checks; no invalid window is silently excluded."})
    aggregates = {role: {key: dispersion([o["metrics"][key] for o in observations if o["role"] == role])
                         for key in METRICS} for role in inputs}
    comparable = not reasons
    criteria = None
    if comparable:
        baseline, candidate = aggregates["baseline"], aggregates["candidate"]
        criteria = {}
        for key in METRICS:
            a, b = baseline[key]["median"], candidate[key]["median"]
            delta = b - a
            threshold = -TAG2_REDUCTION_BYTES if key == "tag2_compressed_logical_bytes" else 0
            strict = key == "process_pageins_median_per_10s"
            criteria[key] = {"baseline_median": a, "candidate_median": b, "candidate_minus_baseline": delta,
                             "required_comparison": "<" if strict else "<=", "threshold": threshold,
                             "met": delta < threshold if strict else delta <= threshold}
    met = all(c["met"] for c in criteria.values()) if criteria is not None else None
    return {
        "analysis_schema": 1, "analysis": "s2arm-host-heap-803-six-windows-v1",
        "status": "refused" if not comparable else "objective_met" if met else "objective_not_met",
        "comparable": comparable, "objective_met": met, "reasons": reasons,
        "policy": {"baseline_app_build": BASELINE_BUILD, "baseline_engine_build": BASELINE_ENGINE,
                   "windows_per_version": REPETITIONS,
                   "duration_s": bench.DURATION, "process_samples_per_window": 18,
                   "tag2_required_reduction_bytes": TAG2_REDUCTION_BYTES,
                   "pageins_method": "median of 18 process pageins * 10 / actual span_s per window, then median of three window medians",
                   "tag2_method": "sum tag 2 compressed_logical_pages across distinct mapping categories * mapping_page_bytes, then median of three complete censuses",
                   "display_method": "median of three full-window display p95 values and median of three display gt100_per_min values; no pooled quantile is invented",
                   "dispersion": "individual values, minimum, maximum, range and median absolute deviation",
                   "pair_validation": "all 15 pairs use unchanged compare_benchmarks.compare guards"},
        "observations": observations, "pair_checks": pair_checks, "aggregates": aggregates, "criteria": criteria,
        "interpretation_limits": [
            "Only these observed windows and the declared scenario are assessed; neither global game compatibility nor energy or FPS gains are inferred.",
            "The census is post-score and non-atomic. VM mappings may count aliases; logical compressed bytes are not physical compressor storage.",
            "Task ledgers and mapping totals overlap and are never added. Process page-ins remain separate from machine-wide VM activity.",
            "Per-window p95 values are summarized by their median, not merged into a six-window frame quantile. Individual values and dispersion remain visible.",
            "No missing observation becomes zero; no failed window is discarded or replaced by a best run.",
            "Device identity, exact route, saves, controller, unchanged caches, cooling and alternating installation order still require the recorded protocol and human evidence; exported metadata alone does not independently authenticate them.",
        ],
    }


def output_is_input(output: Path, inputs: list[Path]) -> bool:
    for path in inputs:
        if output.resolve() == path.resolve():
            return True
        try:
            if output.exists() and path.exists() and output.samefile(path):
                return True
        except OSError:
            pass
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for role in ("baseline", "candidate"):
        parser.add_argument(f"--{role}", action="append", nargs=2, required=True, metavar=("LOG", "UUID"),
                            help=f"Repeat exactly {REPETITIONS} times; select an explicit window UUID in each log.")
    parser.add_argument("--output", type=Path, required=True, help="JSON report destination; parent directory must exist.")
    args = parser.parse_args()
    inputs = {}
    for role in ("baseline", "candidate"):
        values = getattr(args, role)
        if len(values) != REPETITIONS:
            parser.error(f"--{role} must be supplied exactly {REPETITIONS} times")
        inputs[role] = []
        for filename, raw_id in values:
            identifier = bench.uuid_text(raw_id)
            if identifier is None:
                parser.error(f"--{role} requires a valid UUID after each LOG")
            inputs[role].append((Path(filename), identifier))
    paths = [path for selected in inputs.values() for path, _ in selected]
    if output_is_input(args.output, paths):
        parser.error("output must not overwrite any input log, including a symlink or hard-link alias")
    result = analyze(inputs)
    if output_is_input(args.output, paths):
        parser.error("output now aliases an input log; refusing to write")
    try:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Could not write heap comparison report: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "objective_met": result["objective_met"],
                      "output": str(args.output), "refusal_reasons": len(result["reasons"])}, ensure_ascii=False))
    return 2 if not result["comparable"] else 0 if result["objective_met"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
