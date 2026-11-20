#!/usr/bin/env python3
"""Compare two RB-BENCH v1 observations, or record why comparison is refused.

Analysis only: reads logs and writes one JSON report. No engine execution,
network access, cache changes, benchmarks or tests. Python standard library.

Exit status: 0 = observations comparable under the exported contract;
             2 = comparison refused (report still written);
             1 = output could not be written.

An accepted pair is not a causal performance claim. Values remain unavailable
when the producer reports null; machine VM counters are never assigned to the
game process, and Metal allocation is never called physical GPU residency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTOCOL = "rb-switch2-bench-v1"
SCHEMA = 1
DURATION = 180.0
NOMINAL_SAMPLES = tuple(range(10, 181, 10))
MARKER = "[RB-BENCH] "
MAX_RECORD_BYTES = 1024 * 1024
BATTERY_TOLERANCE = 0.05
BRIGHTNESS_TOLERANCE = 0.01
SAMPLE_LIMIT_MS = 1000.0
EPSILON = 1e-6

META_FIELDS = (
    "scenario", "game_id", "game_version", "device_model", "os_version",
    "engine_build", "app_build", "cache_protocol",
)
PAIR_FIELDS = (
    "scenario", "game_id", "game_version", "device_model", "os_version",
    "settings", "cache_protocol", "diagnostics",
)
CONDITION_VALUES = {
    "thermal_state": 0, "battery_state": "unplugged", "low_power": False,
    "screen_captured": False, "app_active": True,
}
COUNT_FIELDS = (
    "count", "interval_count", "gt100", "gt200", "gt500", "duplicate_timestamps",
    "censored_gt100", "censored_gt200", "censored_gt500",
    "gt100_including_censored_minimum", "gt200_including_censored_minimum", "gt500_including_censored_minimum",
)
FRAME_NUMBERS = (
    "p50_ms", "p95_ms", "p99_ms", "max_ms", "fps",
    "gt100_per_min", "gt200_per_min", "gt500_per_min",
    "leading_gap_lower_bound_ms", "tail_gap_lower_bound_ms",
)
COVERAGE_FIELDS = (
    "registered", "completed", "pending", "discarded", "outside_window",
    "overflow", "timestamp_errors",
)
COUNTERS = {
    "process_io": ("read_bytes", "pageins", "written_bytes", "logical_write_bytes"),
    "machine_vm": ("compressions_pages", "decompressions_pages", "pageins", "pageouts", "swapins", "swapouts"),
    "gc": ("allocated_bytes", "gen0", "gen1", "gen2", "pause_ms"),
    "audio": ("gap_estimate_ms", "underruns", "pauses", "late_bursts", "callbacks",
              "skipped_render_periods", "callback_gaps_gt100", "callback_gaps_gt200", "callback_gaps_gt500"),
}
MEMORY_FIELDS = (
    "metal_allocated_bytes", "process_footprint_bytes", "process_compressed_logical_bytes",
    "graphics_ledger_footprint_bytes", "graphics_ledger_compressed_bytes",
    "gpu_resident_physical_bytes",
)
GC_NUMBERS = COUNTERS["gc"] + ("pause_fraction",)
AUDIO_NUMBERS = COUNTERS["audio"] + (
    "active_outputs", "render_period_ns", "registry_overflow", "last_callback_age_ms",
)
SAMPLE_TIME_FIELDS = ("elapsed_s", "span_s", "nominal_elapsed_s", "sample_late_ms", "sample_read_ms")
EXPLICIT_DIAGNOSTICS = (
    "S2A_MEM_SPLIT", "S2A_CPU_PROF", "S2A_HEAP_AUDIT", "S2A_MEMPROBE",
    "DM_TEST_PRESENT_LAG", "DM_TEST_LINK_STALL", "S2A_AUDIO_WAV", "S2A_GALREC",
    "S2A_ALT", "S2A_ALLOC_TRACE", "DM_NVN_PROF", "DM_GPUPROF",
)
DEFAULT_ON_DIAGNOSTICS = ("S2A_RB_VM_TAGS", "S2A_RB_AUTO_PROBE", "S2A_RB_GPU_PROBE", "S2A_RB_CAPTURE")
GC_THRESHOLDS = {"pause_fraction": 0.02, "gen0_per_10s": 100, "gen2_per_10s": 10}
GC_ROLES = {"pause_fraction", "gen0_rate", "gen2_rate"}
SETTING_ENVIRONMENT = (
    "S2A_RES_SCALE", "S2A_ANTI_ALIASING", "S2A_SCALING_FILTER", "S2A_DOCKED",
    "S2A_WIDEN_DIRECT", "S2A_FPS60", "S2A_SYSTEM_LANGUAGE", "S2A_FPS",
    "DM_PRESENT_INTERVAL", "DM_PRESENT_HZ", "DM_PRESENT_LINK", "DM_PRESENT_FIFO",
    "DM_DETCLOCK", "DM_DETCLOCK_PACE", "S2A_RB_NATIVE_CADENCE",
)


def numeric(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def same_number(a: Any, b: float, tolerance: float = EPSILON) -> bool:
    return numeric(a) and abs(a - b) <= tolerance


def uuid_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {"unknown", "unavailable"}


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON floating-point value overflows")
    return result


@dataclass
class Run:
    role: str
    path: Path
    selected_id: str | None
    sha256: str | None = None
    size_bytes: int = 0
    available_ids: list[str] = field(default_factory=list)
    begin: dict = field(default_factory=dict)
    end: dict = field(default_factory=dict)
    samples: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    def issue(self, code: str, path: str, detail: str) -> None:
        entry = {"code": code, "path": path, "detail": detail}
        if entry not in self.issues:
            self.issues.append(entry)

    def warn(self, code: str, path: str, detail: str) -> None:
        self.warnings.append({"code": code, "path": path, "detail": detail})


def dictionary(run: Run, parent: dict, key: str, path: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict):
        run.issue("missing_or_invalid_object", f"{path}.{key}", "An object is required by schema 1.")
        return {}
    return value


def number(run: Run, obj: dict, key: str, path: str, *, nullable: bool = False, whole: bool = False) -> Any:
    if key not in obj:
        run.issue("missing_metric", f"{path}.{key}", "Missing is not equivalent to zero or an explicit null.")
        return None
    value = obj[key]
    if value is None and nullable:
        return None
    if not numeric(value) or value < 0 or (whole and not integer(value)):
        run.issue("invalid_metric", f"{path}.{key}", "Expected a finite nonnegative number" + (" (integer)." if whole else "."))
        return None
    return value


def nullable_bool(run: Run, obj: dict, key: str, path: str) -> None:
    if key not in obj or (obj[key] is not None and not isinstance(obj[key], bool)):
        run.issue("invalid_metric", f"{path}.{key}", "Expected an explicit boolean or null.")


def validate_settings(run: Run, metadata: dict) -> None:
    settings = dictionary(run, metadata, "settings", "begin.metadata")
    path = "begin.metadata.settings"
    if settings.get("source") != "runtime-getters-and-configured-environment-v1":
        run.issue("applied_settings_source_missing", f"{path}.source", "Stored or future launch preferences are not an applied runtime snapshot.")
    if settings.get("frameRateLimitSource") != "nvn_fps_limit":
        run.issue("fps_setting_source_missing", f"{path}.frameRateLimitSource", "Expected the runtime FPS getter.")
    limit = number(run, settings, "frameRateLimit", path, whole=True)
    if limit is not None and not (limit == 0 or 24 <= limit <= 1000):
        run.issue("fps_setting_unknown", f"{path}.frameRateLimit", "The declared runtime limit is outside the engine contract (0 or 24–1000).")
    if settings.get("dockedSource") != "dm_opmode" or not isinstance(settings.get("docked"), bool):
        run.issue("console_mode_source_missing", path, "A boolean docked value from dm_opmode is required.")
    if not isinstance(settings.get("performanceOverlay"), bool):
        run.issue("overlay_setting_unknown", f"{path}.performanceOverlay", "Current host overlay state is required.")
    environment = dictionary(run, settings, "environment", path)
    for key in SETTING_ENVIRONMENT:
        # An explicit null means no environment override. It is not a measured
        # effective value; retain that distinction instead of substituting 0/1.
        if key not in environment or (environment[key] is not None and not isinstance(environment[key], str)):
            run.issue("configuration_state_missing", f"{path}.environment.{key}", "Expected the configured string or explicit null for an unset override.")
    languages = settings.get("systemPreferredLanguages")
    if not isinstance(languages, list) or any(not isinstance(s, str) or not s for s in languages):
        run.issue("system_languages_missing", f"{path}.systemPreferredLanguages", "An explicit array is required.")
    if "resolutionScaleEffective" not in settings or settings["resolutionScaleEffective"] is not None:
        run.issue("unsupported_resolution_observation", f"{path}.resolutionScaleEffective", "v1 has no per-target physical resolution observation; this field must remain explicit null.")
    if not nonempty(settings.get("configuration_observation")):
        run.issue("configuration_scope_missing", f"{path}.configuration_observation", "The export must distinguish configuration from physical per-target observations.")


def read_run(path: Path, role: str, chosen: str | None) -> Run:
    run = Run(role, path, chosen)
    records: list[tuple[int, dict]] = []
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for line_no, raw in enumerate(stream, 1):
                digest.update(raw)
                run.size_bytes += len(raw)
                if MARKER.encode() not in raw:
                    continue
                if len(raw) > MAX_RECORD_BYTES:
                    run.issue("oversized_record", f"line:{line_no}", "RB-BENCH line exceeds the bounded parser limit.")
                    continue
                try:
                    line = raw.decode("utf-8")
                    payload = line.split(MARKER, 1)[1].strip()
                    obj = json.loads(payload, object_pairs_hook=unique_object,
                                     parse_constant=reject_constant, parse_float=finite_float)
                    if not isinstance(obj, dict):
                        raise ValueError("record is not an object")
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                    run.issue("malformed_record", f"line:{line_no}", str(exc))
                    continue
                identifier = uuid_text(obj.get("id"))
                if identifier is None:
                    run.issue("missing_or_invalid_id", f"line:{line_no}", "A UUID is required; record cannot safely be associated.")
                    continue
                obj["id"] = identifier
                records.append((line_no, obj))
    except OSError as exc:
        run.issue("input_unreadable", "input", str(exc))
        return run
    run.sha256 = digest.hexdigest()
    run.available_ids = sorted({obj["id"] for _, obj in records})
    if not records:
        run.issue("protocol_missing", "input", "No valid [RB-BENCH] JSON records. Legacy summaries and other logs are not comparable.")
        return run
    if chosen is None:
        if len(run.available_ids) != 1:
            run.issue("ambiguous_run", "input", "Several run IDs exist; choose one explicitly. No latest-run heuristic is used.")
            return run
        run.selected_id = run.available_ids[0]
    elif chosen not in run.available_ids:
        run.issue("selected_id_absent", "input", "Requested run ID is absent.")
        return run
    selected = [(n, obj) for n, obj in records if obj["id"] == run.selected_id]
    by_type: dict[str, list[tuple[int, dict]]] = {"begin": [], "sample": [], "end": []}
    for line_no, obj in selected:
        if obj.get("schema") != SCHEMA or not integer(obj.get("schema")):
            run.issue("unsupported_schema", f"line:{line_no}.schema", "Only schema 1 is accepted.")
        if obj.get("protocol_id") != PROTOCOL:
            run.issue("unsupported_protocol", f"line:{line_no}.protocol_id", f"Expected {PROTOCOL}.")
        kind = obj.get("type")
        if not isinstance(kind, str) or kind not in by_type:
            run.issue("unknown_record_type", f"line:{line_no}.type", "Expected begin, sample or end.")
        else:
            by_type[kind].append((line_no, obj))
    for kind in ("begin", "end"):
        if len(by_type[kind]) != 1:
            run.issue(f"{kind}_not_unique", "input", f"Expected one {kind}, observed {len(by_type[kind])}; no duplicate is silently discarded.")
        elif kind == "begin":
            run.begin = by_type[kind][0][1]
        else:
            run.end = by_type[kind][0][1]
    run.samples = [obj for _, obj in by_type["sample"]]
    if run.begin and run.end:
        first, last = by_type["begin"][0][0], by_type["end"][0][0]
        if first >= last or any(not first < n < last for n, _ in by_type["sample"]):
            run.issue("record_order_invalid", "input", "All samples must follow begin and precede end in this run.")
    validate_run(run)
    return run


def validate_metric_group(run: Run, obj: dict, group: str, path: str) -> dict:
    data = dictionary(run, obj, group, path)
    keys = GC_NUMBERS if group == "gc" else AUDIO_NUMBERS if group == "audio" else MEMORY_FIELDS if group == "memory" else COUNTERS[group]
    for key in keys:
        number(run, data, key, f"{path}.{group}", nullable=True)
    if group == "gc":
        nullable_bool(run, data, "pressure_alert", f"{path}.gc")
        if data.get("threshold_version") != 1:
            run.issue("unknown_gc_threshold", f"{path}.gc.threshold_version", "Expected diagnostic threshold version 1.")
        if data.get("thresholds") != GC_THRESHOLDS:
            run.issue("gc_threshold_mismatch", f"{path}.gc.thresholds", "Diagnostic thresholds differ from the frozen v1 contract.")
        roles = data.get("pressure_alert_roles")
        if "pressure_alert_roles" not in data or (roles is not None and
                (not isinstance(roles, list) or any(not isinstance(r, str) or r not in GC_ROLES for r in roles))):
            run.issue("gc_alert_roles_invalid", f"{path}.gc.pressure_alert_roles", "Expected explicit known diagnostic roles.")
        if path == "end":
            windows = number(run, data, "alerted_windows", "end.gc", nullable=True, whole=True)
            if integer(windows) and windows > 18:
                run.issue("gc_alert_windows_invalid", "end.gc.alerted_windows", "Alerted windows cannot exceed the 18 observed bins.")
    if group == "audio":
        nullable_bool(run, data, "observed_output", f"{path}.audio")
        if numeric(data.get("registry_overflow")) and data["registry_overflow"] > 0:
            run.issue("audio_registry_incomplete", f"{path}.audio.registry_overflow", "Audio registry overflow prevents complete tracking.")
    return data


def validate_frame(run: Run, key: str) -> None:
    data = dictionary(run, run.end, key, "end")
    for name in COUNT_FIELDS:
        number(run, data, name, f"end.{key}", whole=True)
    for name in FRAME_NUMBERS:
        number(run, data, name, f"end.{key}", nullable=name in {"p50_ms", "p95_ms", "p99_ms", "max_ms"})
    count, intervals = data.get("count"), data.get("interval_count")
    if integer(count) and integer(intervals):
        if intervals != max(count - 1, 0):
            run.issue("interval_count_inconsistent", f"end.{key}", "Schema 1 intervals must connect adjacent observed timestamps.")
        if intervals < 1:
            run.issue("no_observable_intervals", f"end.{key}", "At least two timestamps are required for a frame comparison.")
        qs = [data.get(k) for k in ("p50_ms", "p95_ms", "p99_ms", "max_ms")]
        if intervals and (not all(numeric(x) for x in qs) or qs != sorted(qs)):
            run.issue("quantiles_invalid", f"end.{key}", "Observed intervals require ordered p50/p95/p99/max values.")
        tails = [data.get(k) for k in ("gt500", "gt200", "gt100")]
        if all(integer(x) for x in tails) and not (0 <= tails[0] <= tails[1] <= tails[2] <= intervals):
            run.issue("tail_counts_invalid", f"end.{key}", "Tail counts are inconsistent with observed intervals.")
        if numeric(data.get("fps")) and not same_number(data["fps"], count / DURATION, 1e-5):
            run.issue("fps_denominator_mismatch", f"end.{key}.fps", "Schema 1 FPS uses timestamp count divided by the fixed observation duration.")
        for threshold in (100, 200, 500):
            c, rate = data.get(f"gt{threshold}"), data.get(f"gt{threshold}_per_min")
            if numeric(c) and numeric(rate) and not same_number(rate, c * 60 / DURATION, 1e-5):
                run.issue("tail_rate_denominator_mismatch", f"end.{key}.gt{threshold}_per_min", "Schema 1 rate uses the fixed observation duration.")
            censored = data.get(f"censored_gt{threshold}")
            minimum = data.get(f"gt{threshold}_including_censored_minimum")
            if integer(censored) and integer(minimum) and integer(c):
                if censored > 2 or minimum != c + censored:
                    run.issue("censored_counts_invalid", f"end.{key}", "Boundary counts are separate lower bounds and must not silently change complete-interval counts.")


def validate_run(run: Run) -> None:
    if not run.begin or not run.end:
        return
    for kind, obj in (("begin", run.begin), ("end", run.end)):
        if obj.get("comparable") is not True:
            run.issue("producer_not_comparable", f"{kind}.comparable", "Producer did not attest comparison eligibility.")
        reasons = obj.get("reasons")
        if not isinstance(reasons, list) or any(not isinstance(r, str) for r in reasons):
            run.issue("reasons_missing_or_invalid", f"{kind}.reasons", "An explicit array of producer reasons is required.")
        elif reasons:
            for reason in reasons:
                run.issue("producer_reason", f"{kind}.reasons", reason)
        if not same_number(obj.get("duration_target_s"), DURATION):
            run.issue("duration_target_mismatch", f"{kind}.duration_target_s", "Protocol requires 180 seconds.")
    if run.end.get("complete") is not True:
        run.issue("incomplete_run", "end.complete", "Interrupted or incomplete observations cannot be compared.")
    if not same_number(run.end.get("duration_s"), DURATION):
        run.issue("duration_incomplete", "end.duration_s", "The observation window must be exactly 180 seconds; drain is excluded.")
    metadata = dictionary(run, run.begin, "metadata", "begin")
    for key in META_FIELDS:
        if not nonempty(metadata.get(key)):
            run.issue("metadata_missing_or_unknown", f"begin.metadata.{key}", "A known nonempty string is required.")
    if metadata.get("cold_confirmed") is not True:
        run.issue("cold_not_confirmed", "begin.metadata.cold_confirmed", "Protocol requires explicit cold-start confirmation.")
    if metadata.get("protocol") != PROTOCOL or not same_number(metadata.get("duration_seconds"), DURATION):
        run.issue("metadata_protocol_mismatch", "begin.metadata", "Metadata must repeat the same protocol and duration.")
    validate_settings(run, metadata)
    diagnostics = dictionary(run, metadata, "diagnostics", "begin.metadata")
    for group, keys in (("explicit_perturbing_flags", EXPLICIT_DIAGNOSTICS),
                        ("configured_default_on_flags", DEFAULT_ON_DIAGNOSTICS)):
        values = dictionary(run, diagnostics, group, "begin.metadata.diagnostics")
        for key in keys:
            value = values.get(key)
            if not isinstance(value, bool):
                run.issue("diagnostic_state_missing", f"begin.metadata.diagnostics.{group}.{key}", "An explicit boolean is required; omission is not off.")
            elif value and group == "explicit_perturbing_flags":
                run.issue("perturbing_diagnostic_enabled", f"begin.metadata.diagnostics.{group}.{key}", "Explicit diagnostic activation prevents a clean protocol comparison.")
    run.warn("configured_diagnostics_are_not_activation_traces", "begin.metadata.diagnostics",
             "Default-on flags describe configuration, not proof that an automatic capture actually ran. The pair must match this configuration; observations are not certified unperturbed.")
    conditions = dictionary(run, run.begin, "initial_conditions", "begin")
    for key, required in CONDITION_VALUES.items():
        observed = conditions.get(key)
        type_ok = type(observed) is type(required)
        if not type_ok or observed != required:
            run.issue("initial_condition_invalid", f"begin.initial_conditions.{key}", f"Required value: {required!r}.")
    for key in ("battery_level", "brightness"):
        v = number(run, conditions, key, "begin.initial_conditions")
        if numeric(v) and v > 1:
            run.issue("initial_fraction_invalid", f"begin.initial_conditions.{key}", "Expected a fraction from 0 to 1.")
    start = number(run, run.begin, "start_ns", "begin", whole=True)
    window = dictionary(run, run.end, "window", "end")
    for key in ("start_ns", "end_ns", "finalized_ns"):
        number(run, window, key, "end.window", whole=True)
    if all(integer(window.get(k)) for k in ("start_ns", "end_ns", "finalized_ns")):
        if window["start_ns"] != start or window["end_ns"] - window["start_ns"] != int(DURATION * 1e9) or window["finalized_ns"] < window["end_ns"]:
            run.issue("clock_window_invalid", "end.window", "Raw-clock window disagrees with begin or the 180-second boundary.")
    protocol_hash = run.end.get("protocol_hash")
    if not isinstance(protocol_hash, str) or re.fullmatch(r"[0-9a-f]{64}", protocol_hash) is None:
        run.issue("protocol_hash_missing", "end.protocol_hash", "A SHA-256 protocol fingerprint is required.")
    for key in ("frame", "display"):
        validate_frame(run, key)
    coverage = dictionary(run, run.end, "coverage", "end")
    for key in COVERAGE_FIELDS:
        number(run, coverage, key, "end.coverage", whole=True)
    for key in ("pending", "overflow", "timestamp_errors"):
        if coverage.get(key) != 0:
            run.issue("coverage_incomplete", f"end.coverage.{key}", "Unresolved callbacks, overflow or timestamp errors prevent a complete comparison.")
    for key in ("discarded", "outside_window"):
        if numeric(coverage.get(key)) and coverage[key] > 0:
            run.warn("observed_callback_outcome", f"end.coverage.{key}", "Legitimate observed result; not converted to a missing callback or silently discarded.")
    thermal = dictionary(run, run.end, "thermal_time_s", "end")
    for key in ("nominal", "fair", "serious", "critical", "unknown"):
        number(run, thermal, key, "end.thermal_time_s")
    if all(numeric(thermal.get(k)) for k in ("nominal", "fair", "serious", "critical", "unknown")):
        if not same_number(sum(thermal[k] for k in ("nominal", "fair", "serious", "critical", "unknown")), DURATION, 1e-4):
            run.issue("thermal_coverage_invalid", "end.thermal_time_s", "Thermal occupancy must cover the observation window.")
    modes = dictionary(run, run.end, "mode_time_s", "end")
    for group in ("requested_game", "sent_period"):
        values = dictionary(run, modes, group, "end.mode_time_s")
        for key in ("30", "60", "other", "unknown"):
            number(run, values, key, f"end.mode_time_s.{group}")
        if all(numeric(values.get(k)) for k in ("30", "60", "other", "unknown")):
            if not same_number(sum(values[k] for k in ("30", "60", "other", "unknown")), DURATION, 1e-4):
                run.issue("mode_coverage_invalid", f"end.mode_time_s.{group}", "Cadence mode occupancy must cover the observation window.")
    for group in ("gc", "audio"):
        validate_metric_group(run, run.end, group, "end")
    memory = dictionary(run, run.end, "memory", "end")
    for point in ("start", "end"):
        values = dictionary(run, memory, point, "end.memory")
        for key in MEMORY_FIELDS:
            number(run, values, key, f"end.memory.{point}", nullable=True)
    if run.end.get("sample_count") != len(NOMINAL_SAMPLES) or len(run.samples) != len(NOMINAL_SAMPLES):
        run.issue("sample_coverage_incomplete", "samples", f"Expected 18 emitted samples, observed {len(run.samples)}; end reports {run.end.get('sample_count')!r}.")
    prior_elapsed = 0.0
    for index, sample in enumerate(run.samples):
        path = f"samples[{index}]"
        for key in SAMPLE_TIME_FIELDS:
            number(run, sample, key, path)
        nominal = NOMINAL_SAMPLES[index] if index < len(NOMINAL_SAMPLES) else None
        if nominal is None or not same_number(sample.get("nominal_elapsed_s"), nominal):
            run.issue("sample_sequence_invalid", f"{path}.nominal_elapsed_s", "Required sequence is exactly 10,20,...,180, without reconstructed samples.")
        elapsed, span = sample.get("elapsed_s"), sample.get("span_s")
        if numeric(elapsed):
            if elapsed <= prior_elapsed or elapsed > DURATION + 1 + EPSILON:
                run.issue("sample_clock_invalid", f"{path}.elapsed_s", "Sample time must increase and remain within the permitted final boundary delay.")
            prior_elapsed = elapsed
        if numeric(span) and span <= 0:
            run.issue("sample_span_invalid", f"{path}.span_s", "A positive measured span is needed for normalized counter rates.")
        for key in ("sample_late_ms", "sample_read_ms"):
            if numeric(sample.get(key)) and sample[key] > SAMPLE_LIMIT_MS + EPSILON:
                run.issue("sample_too_late_or_intrusive", f"{path}.{key}", "More than one second breaches the versioned protocol.")
        for group in ("process_io", "machine_vm", "gc", "audio", "memory"):
            validate_metric_group(run, sample, group, path)


def unit_for(key: str) -> str:
    if key.endswith("_bytes"):
        return "bytes"
    if key.endswith("_ms"):
        return "ms"
    if key.endswith("_ns"):
        return "ns"
    if key.endswith("_s"):
        return "s"
    if key.endswith("_per_min"):
        return "count/minute_of_observation"
    if key == "fps":
        return "observed_timestamps/second_of_observation"
    if "fraction" in key:
        return "fraction"
    return "count"


def flatten_metrics(run: Run) -> dict[str, dict]:
    result: dict[str, dict] = {}

    def add(path: str, value: Any, unit: str, complete: bool = True, **extra: Any) -> None:
        result[path] = {"value": value, "unit": unit, "available": numeric(value), "coverage_complete": complete, **extra}

    for group in ("frame", "display", "gc", "audio"):
        obj = run.end.get(group)
        if not isinstance(obj, dict):
            continue
        keys = COUNT_FIELDS + FRAME_NUMBERS if group in ("frame", "display") else GC_NUMBERS if group == "gc" else AUDIO_NUMBERS
        for key in keys:
            add(f"{group}.{key}", obj.get(key), unit_for(key))
        if group == "gc":
            complete_alerts = len(run.samples) == 18 and all(
                isinstance(s.get("gc"), dict) and isinstance(s["gc"].get("pressure_alert"), bool)
                for s in run.samples)
            add("gc.alerted_windows", obj.get("alerted_windows") if obj.get("pressure_alert") is not None else None,
                "observed_10s_bins", complete_alerts)
    thermal = run.end.get("thermal_time_s", {})
    if isinstance(thermal, dict):
        for key in ("nominal", "fair", "serious", "critical", "unknown"):
            add(f"thermal_time_s.{key}", thermal.get(key), "s")
    modes = run.end.get("mode_time_s", {})
    if isinstance(modes, dict):
        for group in ("requested_game", "sent_period"):
            values = modes.get(group, {})
            if isinstance(values, dict):
                for key in ("30", "60", "other", "unknown"):
                    add(f"mode_time_s.{group}.{key}", values.get(key), "s")
    valid_spans = all(numeric(s.get("span_s")) and s["span_s"] > 0 for s in run.samples)
    span_total = sum(s["span_s"] for s in run.samples) if run.samples and valid_spans else None
    for group, keys in COUNTERS.items():
        for key in keys:
            values = [s.get(group, {}).get(key) if isinstance(s.get(group), dict) else None for s in run.samples]
            count = sum(numeric(x) for x in values)
            complete = len(values) == 18 and count == 18 and numeric(span_total) and span_total > 0
            total = sum(values) if complete else None
            add(f"sample_totals.{group}.{key}", total, unit_for(key), complete,
                available_samples=count, expected_samples=18, measured_span_s=span_total)
            rate = total / span_total if complete else None
            add(f"sample_rates.{group}.{key}", rate, f"{unit_for(key)}/measured_second", complete,
                available_samples=count, expected_samples=18, measured_span_s=span_total)
    for key in MEMORY_FIELDS:
        values = [s.get("memory", {}).get(key) if isinstance(s.get("memory"), dict) else None for s in run.samples]
        present = [v for v in values if numeric(v)]
        add(f"memory.sampled_peak.{key}", max(present) if present else None, "bytes", len(present) == 18,
            available_samples=len(present), expected_samples=18, note="Peak of sampled gauges, not a continuous peak.")
        memory = run.end.get("memory", {})
        for point in ("start", "end"):
            values = memory.get(point, {}) if isinstance(memory, dict) else {}
            add(f"memory.{point}.{key}", values.get(key) if isinstance(values, dict) else None, "bytes")
    return result


def run_report(run: Run) -> dict:
    sample_rows = []
    for sample in run.samples:
        row = {key: sample.get(key) for key in SAMPLE_TIME_FIELDS}
        for group in ("process_io", "machine_vm", "gc", "audio", "memory"):
            row[group] = sample.get(group)
        span = sample.get("span_s")
        rates = {}
        for group, keys in COUNTERS.items():
            values = sample.get(group, {})
            values = values if isinstance(values, dict) else {}
            rates[group] = {key: values.get(key) / span if numeric(values.get(key)) and numeric(span) and span > 0 else None for key in keys}
        row["counter_rates_per_measured_second"] = rates
        sample_rows.append(row)
    metadata = run.begin.get("metadata")
    return {
        "source": {"name": run.path.name, "sha256": run.sha256, "bytes": run.size_bytes},
        "id": run.selected_id, "available_ids": run.available_ids,
        "protocol_id": run.begin.get("protocol_id"), "schema": run.begin.get("schema"),
        "eligible": not run.issues, "reasons": run.issues, "warnings": run.warnings,
        "metadata": metadata, "initial_conditions": run.begin.get("initial_conditions"),
        "duration_s": run.end.get("duration_s"), "duration_target_s": run.end.get("duration_target_s"),
        "producer_complete": run.end.get("complete"), "producer_comparable": run.end.get("comparable"),
        "producer_reasons": run.end.get("reasons"), "protocol_hash": run.end.get("protocol_hash"),
        "window": run.end.get("window"), "coverage": run.end.get("coverage"),
        "sample_count": run.end.get("sample_count"), "metrics": flatten_metrics(run),
        "samples": sample_rows,
        "raw_summary": {key: value for key, value in run.end.items() if key != "report_path"},
    }


def compare(baseline: Run, candidate: Run) -> dict:
    reasons = []

    def reason(code: str, path: str, detail: str) -> None:
        reasons.append({"code": code, "path": path, "detail": detail})

    for run in (baseline, candidate):
        if run.issues:
            reason("run_ineligible", run.role, "See this run's recorded reasons; no comparison delta is produced.")
    if baseline.selected_id and baseline.selected_id == candidate.selected_id:
        reason("same_run", "id", "The same observation cannot be used as both sides of a comparison.")
    ma = baseline.begin.get("metadata", {})
    mb = candidate.begin.get("metadata", {})
    ma, mb = ma if isinstance(ma, dict) else {}, mb if isinstance(mb, dict) else {}
    for key in PAIR_FIELDS:
        a, b = ma.get(key), mb.get(key)
        if key == "game_id" and isinstance(a, str) and isinstance(b, str):
            a, b = a.upper(), b.upper()
        if a != b:
            reason("condition_mismatch", f"metadata.{key}", "Baseline and candidate differ; app/engine build are the only freely changing metadata fields.")
    ia = baseline.begin.get("initial_conditions", {})
    ib = candidate.begin.get("initial_conditions", {})
    ia, ib = ia if isinstance(ia, dict) else {}, ib if isinstance(ib, dict) else {}
    for key, tolerance in (("battery_level", BATTERY_TOLERANCE), ("brightness", BRIGHTNESS_TOLERANCE)):
        a, b = ia.get(key), ib.get(key)
        if not numeric(a) or not numeric(b) or abs(a - b) > tolerance + 1e-12:
            reason("initial_condition_mismatch", f"initial_conditions.{key}", f"Difference exceeds inclusive tolerance {tolerance}, or a value is unavailable.")
    ha, hb = baseline.end.get("protocol_hash"), candidate.end.get("protocol_hash")
    if ha != hb:
        reason("protocol_fingerprint_mismatch", "protocol_hash", "Reported canonical protocol fingerprints differ; no hash is reconstructed with another JSON serializer.")
    a_report, b_report = run_report(baseline), run_report(candidate)
    accepted = not reasons
    deltas, unavailable = {}, []
    for key in sorted(set(a_report["metrics"]) | set(b_report["metrics"])):
        a, b = a_report["metrics"].get(key), b_report["metrics"].get(key)
        usable = bool(a and b and a["available"] and b["available"] and a["coverage_complete"] and b["coverage_complete"] and a["unit"] == b["unit"])
        if not usable:
            unavailable.append({"metric": key, "reason": "Metric absent, explicitly null, only partially sampled, or units differ; no zero substitution."})
        elif accepted:
            deltas[key] = {"baseline": a["value"], "candidate": b["value"],
                           "candidate_minus_baseline": b["value"] - a["value"], "unit": a["unit"]}
    return {
        "analysis_schema": 1, "expected_protocol_id": PROTOCOL,
        "status": "comparable_observations" if accepted else "refused",
        "comparable": accepted, "reasons": reasons,
        "policy": {
            "duration_target_s": DURATION, "required_samples": 18,
            "maximum_sample_late_ms": SAMPLE_LIMIT_MS, "maximum_sample_read_ms": SAMPLE_LIMIT_MS,
            "battery_fraction_tolerance_inclusive": BATTERY_TOLERANCE,
            "brightness_fraction_tolerance_inclusive": BRIGHTNESS_TOLERANCE,
            "equal_metadata_fields": list(PAIR_FIELDS),
            "allowed_treatment_differences": ["metadata.app_build", "metadata.engine_build"],
            "thermal_occupancy_is_outcome_not_matching_condition": True,
        },
        "baseline": a_report, "candidate": b_report,
        "descriptive_differences": deltas if accepted else None,
        "unavailable_metric_comparisons": unavailable,
        "interpretation_limits": [
            "Eligibility is based on exported protocol data, not independent authentication of device, binary, scenario execution or cache contents.",
            "One pair of runs does not establish causality, repeatability, energy savings or performance for other games.",
            "Differences are candidate minus baseline in the recorded unit; no relative gain, significance, energy or speed-up is invented.",
            "A matching cache protocol is a declaration of procedure, not proof of identical cache contents or hit rates.",
            "Settings compare runtime FPS/console getters, current overlay state and configured environment. Unset overrides remain null; physical per-target resolution is deliberately unknown, not inferred from a preference. launch_preferences are not used as matching conditions.",
            "Quantiles describe intervals whose endpoints are observed; leading/tail gaps and censored_gt counts are lower bounds. Complete-interval counts are never silently replaced by censored minimum counts.",
            "Frame/display timestamp rates do not measure guest simulation speed; guest frames minus display callbacks is not a count of missing callbacks.",
            "Counter rates use each actual sample span. GC pause is completed cumulative pause time; GC alerts are diagnostic thresholds/OR of observed bins, not attribution of every hitch. Audio gap is an estimate, not proof of audible silence.",
            "Machine VM counters are system-wide. TASK_VM_INFO compressed counts logical compressed bytes, not their physical compressed storage. Metal allocation and graphics ledgers are not physical GPU residency. Null remains unavailable.",
        ],
    }


def argument_id(value: str) -> str:
    normalized = uuid_text(value)
    if normalized is None:
        raise argparse.ArgumentTypeError("expected a UUID")
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline log containing [RB-BENCH] JSON lines.")
    parser.add_argument("--candidate", type=Path, required=True, help="Candidate log containing [RB-BENCH] JSON lines.")
    parser.add_argument("--baseline-id", type=argument_id, help="Required when baseline log contains several IDs.")
    parser.add_argument("--candidate-id", type=argument_id, help="Required when candidate log contains several IDs.")
    parser.add_argument("--output", type=Path, required=True, help="JSON output file; its parent directory must exist.")
    args = parser.parse_args()
    if args.output.resolve() in {args.baseline.resolve(), args.candidate.resolve()}:
        parser.error("output must not overwrite an input log")
    result = compare(read_run(args.baseline, "baseline", args.baseline_id), read_run(args.candidate, "candidate", args.candidate_id))
    try:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Could not write comparison report: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "pair_refusal_reasons": len(result["reasons"]),
                      "baseline_reasons": len(result["baseline"]["reasons"]),
                      "candidate_reasons": len(result["candidate"]["reasons"])}, ensure_ascii=False))
    return 0 if result["comparable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
