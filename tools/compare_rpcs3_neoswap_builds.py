#!/usr/bin/env python3
"""Compare two identified RPCS3/NeoSwap captures from different builds.

Each --before/--after JSON manifest names sourceCommit (full git SHA), pid,
sessionSequence, bootTimestamp (exact game_boot_begin timestamp), title,
workloadId (save/route/duration), deviceId, settingsId, memoryLogs and rpcs3Logs.
Log paths are relative to the manifest. Workload/device/settings must match.
The source SHA may differ, unlike compare_neoswap_sessions.py's mode experiment.

--mode cross-title instead compares two titles captured on one build: title and
workloadId may differ, but device, settings, physical memory, OS version and
sourceCommit must match. It explains differences between games, not builds.

Only complete, unambiguous memory sessions are accepted. Missing instrumentation
is null with a reason, never a zero. All totals cover observed log windows, not
an assertion of gap-free capture or device validation. COREPROF window p95 is
not a session p95; sampled FPS is never inverted to invent frame times.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


PAIR = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")
# JITPROF prints each phase as events:total_ms:max_ms:bytes (%llu:%.3f:%.3f:%llu).
JIT_TUPLE = re.compile(r"([0-9]+):([0-9]+(?:\.[0-9]+)?):([0-9]+(?:\.[0-9]+)?):([0-9]+)")
IDENTITY = ("sourceCommit", "pid", "sessionSequence", "bootTimestamp", "title",
            "workloadId", "deviceId", "settingsId")
SHARED_IDENTITY = ("deviceId", "settingsId", "physicalMemoryBytes", "osVersion")
COMPARISON_MODES = ("same-title", "cross-title")
SAMPLE_STAGES = ("performance_sample", "neoswap_guest_sample", "neoswap_guest_sample_ext")
GUEST_PHASES = ("before_boot", "boot_return", "sample", "session_end")
DONATED_FIELDS = (
    ("neoswap_donated_peak_bytes", "donatedBytes"),
    ("neoswap_donated_guest_peak_bytes", "donatedGuestBytes"),
    ("neoswap_donated_host_relay_peak_bytes", "donatedHostRelayBytes"),
    ("neoswap_donated_donor_peak_bytes", "donatedDonorBytes"),
)
GUEST_COUNTERS = (
    "candidate_first_maps", "requested_bytes", "gameplay_first_maps", "gameplay_requested_bytes",
    "prepared_hits", "prepared_hit_bytes", "prepared_misses", "prepared_miss_bytes",
    "ordinary_fallbacks", "ordinary_fallback_bytes", "map_failures", "alias_maps",
    "prepared_published_objects", "prepared_published_bytes", "first_map_total_ns",
)
# Build 444 neoswap_guest_sample_ext counters: cumulative independent atomics,
# except the fallback_live_* pair, which are current live counts of candidate
# objects on ordinary backing.
GUEST_EXT_COUNTERS = (
    "gameplay_direct_requests", "gameplay_direct_creates", "gameplay_direct_create_bytes",
    "gameplay_direct_busy", "gameplay_direct_pressure", "gameplay_direct_budget", "gameplay_direct_other",
    "gameplay_fallbacks", "gameplay_fallback_bytes", "fallback_live_objects", "fallback_live_bytes",
    "oversize_requests", "oversize_requested_bytes", "boot_creates", "boot_create_bytes",
    "direct_published_objects", "direct_published_bytes",
)
GUEST_EXT_LIVE_COUNTERS = ("fallback_live_objects", "fallback_live_bytes")
JIT_PHASES = (
    "ppu_translate", "ppu_opt", "ppu_verify", "ppu_codegen", "ppu_cache_write", "ppu_cache_read",
    "ppu_object_load", "ppu_finalize", "ppu_symbols", "spu_build", "spu_passes", "spu_codegen",
)
JIT_FIELDS = (("events", sum, "count"), ("total_ms", sum, "ms"), ("max_ms", max, "ms"), ("bytes", sum, "bytes"))
# Host-sampled guestRelay.guestDirectCreation cumulative counters (Build 444).
DIRECT_CREATION_COUNTERS = (
    "requests", "requestedBytes", "created", "createdBytes", "busy", "refusedPressure", "refusedBudget",
    "refusedCapacity", "refusedDisabled", "refusedLimit", "refusedInvalid", "oversizeRequests",
    "oversizeRequestedBytes", "allowanceGrants", "allowanceGrantedBytes", "wakeups",
)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def numeric(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if number(result) else None


def field(record, path):
    for key in path.split("."):
        record = record.get(key) if isinstance(record, dict) else None
    return record


def active_donation(record):
    """Accept only the measured schema-2 total and its disjoint active parts.

    Earlier occupied-backing counters include idle shelves and cannot recover
    this measure. Unknown, inconsistent and out-of-range samples stay unknown.
    """
    contribution = record.get("neoswapContribution")
    if not isinstance(contribution, dict) or type(contribution.get("schema")) is not int or contribution["schema"] != 2:
        return None
    values = {name: contribution.get(name) for _, name in DONATED_FIELDS}
    if any(type(value) is not int or not 0 <= value <= (1 << 64) - 1 for value in values.values()):
        return None
    if values["donatedBytes"] != sum(values[name] for _, name in DONATED_FIELDS[1:]):
        return None
    return values


def guest_counters(record, names):
    """Parse exact uint64 counters without rounding bytes through a float."""
    values = dict(PAIR.findall(str(record.get("message", ""))))
    if (values.get("schema") != "1" or values.get("valid") != "1" or
            values.get("result") != "0" or values.get("scope") != "process_lifetime" or
            values.get("phase") not in GUEST_PHASES):
        return None
    parsed = {}
    for name in (*names, "sample_epoch"):
        value = values.get(name, "")
        if not re.fullmatch(r"[0-9]+", value):
            return None
        parsed[name] = int(value)
        if parsed[name] > (1 << 64) - 1:
            return None
    if not parsed["sample_epoch"]:
        return None
    parsed["phase"] = values["phase"]
    return parsed


def guest_sample(record):
    """Base guest line; it additionally carries the gameplay_active flag."""
    values = dict(PAIR.findall(str(record.get("message", ""))))
    if values.get("gameplay_active") not in ("0", "1"):
        return None
    return guest_counters(record, (*GUEST_COUNTERS, "first_map_max_ns"))


def guest_sample_ext(record):
    """Build 444 extension line: same strictness, no gameplay_active flag."""
    return guest_counters(record, GUEST_EXT_COUNTERS)


def complete_endpoints(samples):
    """Explicit endpoints retain loading and final gameplay requests. A rotated
    or truncated capture must not masquerade as a complete guest delta."""
    if not samples or any(row is None for row in samples):
        return False
    phases = [row["phase"] for row in samples]
    return (phases[0] == "before_boot" and phases[-1] == "session_end" and
            phases.count("before_boot") == phases.count("session_end") == 1)


def read_logs(paths):
    """Deduplicate overlap in rotated exports, retaining file hashes as evidence."""
    unique, evidence = {}, []
    for path in paths:
        data = Path(path).read_bytes()
        evidence.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest()})
        for index, line in enumerate(data.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{index}: incomplete/invalid JSONL") from error
            if not isinstance(row, dict) or not number(row.get("timestamp")):
                raise ValueError(f"{path}:{index}: record requires a finite timestamp")
            unique[json.dumps(row, sort_keys=True)] = row
    return sorted(unique.values(), key=lambda row: row["timestamp"]), evidence


def manifest(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    for key in IDENTITY:
        if key not in result or result[key] is None or result[key] == "":
            raise ValueError(f"{path}: missing identity {key}")
    if not re.fullmatch(r"[0-9a-f]{40}", result["sourceCommit"]):
        raise ValueError("sourceCommit must be a full lowercase Git SHA")
    for key in ("pid", "sessionSequence"):
        if not isinstance(result[key], int) or isinstance(result[key], bool) or result[key] <= 0:
            raise ValueError(f"Invalid {key}")
    if not number(result["bootTimestamp"]):
        raise ValueError("bootTimestamp must be numeric")
    for key in ("memoryLogs", "rpcs3Logs"):
        if not isinstance(result.get(key), list) or not result[key]:
            raise ValueError(f"{path}: {key} must name at least one log")
        result[key] = [path.parent / value for value in result[key]]
    return result


def select_session(info, memory, diagnostics):
    rows = [row for row in memory if row.get("pid") == info["pid"] and
            field(row, "memoryProfile.sessionSequence") == info["sessionSequence"]]
    starts = [row for row in rows if row.get("event") == "rpcs3_memory_session_start"]
    ends = [row for row in rows if row.get("event") == "rpcs3_memory_session_end"]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("Need one complete memory session; missing/reused PID or session sequence")
    begin, end = starts[0]["timestamp"], ends[0]["timestamp"]
    if begin >= end or any(not begin <= row["timestamp"] <= end for row in rows):
        raise ValueError("Memory rows extend outside the selected session")
    boot = info["bootTimestamp"]
    # Memory polling records session activation independently of the boot queue.
    # A large offset is ambiguous and must not silently bind an unrelated boot.
    if abs(begin - boot) > 10 or boot >= end:
        raise ValueError("Memory session cannot be bound to the selected boot timestamp")
    selected = [row for row in diagnostics if row.get("pid") == info["pid"] and
                min(begin, boot) <= row["timestamp"] <= end]
    boots = [row for row in selected if row.get("stage") == "game_boot_begin"]
    if len(boots) != 1 or boots[0]["timestamp"] != boot or boots[0].get("message") != info["title"]:
        raise ValueError("Need exactly the selected title/boot; mixed launches are not comparable")
    epochs, commits, profiles = set(), set(), set()
    for row in rows:
        source = field(row, "experiment.sourceCommit")
        if source:
            commits.add(source)
        profile = row.get("experiment", {})
        profiles.add(json.dumps(profile, sort_keys=True))
    if len(profiles) > 1 or (commits and commits != {info["sourceCommit"]}):
        raise ValueError("Mixed source commits or experiment profiles in one memory session")
    for row in selected:
        values = dict(PAIR.findall(str(row.get("message", ""))))
        if "title" in values and values["title"] != info["title"]:
            raise ValueError("Diagnostic title differs from selected workload")
        if row.get("stage") in SAMPLE_STAGES and values.get("title") != info["title"]:
            raise ValueError("Performance/guest sample requires an explicit matching title")
        if row.get("stage") in SAMPLE_STAGES and "sample_epoch" in values:
            epochs.add(values["sample_epoch"])
    if len(epochs) > 1:
        raise ValueError("Performance epoch reset/relaunch inside selected session")
    for key in ("physicalMemoryBytes", "osVersion"):
        observed = {row[key] for row in rows if row.get(key) is not None}
        if len(observed) > 1:
            raise ValueError(f"Mixed memory capture identity: {key}")
    return rows, selected, bool(commits)


def profile_rows(diagnostics, marker, convert=numeric):
    result = []
    for row in diagnostics:
        message = str(row.get("message", ""))
        if row.get("stage") == "core_log" and re.search(r"\b" + marker + r" ", message):
            values = {key: convert(value) for key, value in PAIR.findall(message)}
            result.append(values)
    return result


def jit_rows(diagnostics):
    """Split JITPROF name=events:total_ms:max_ms:bytes tuples into exact fields.

    A malformed or absent tuple leaves that phase unknown in its window; the
    generic numeric conversion would otherwise silently drop every tuple.
    """
    result = []
    for raw in profile_rows(diagnostics, "JITPROF", str):
        window = {key: numeric(raw.get(key)) for key in ("session", "headroom_samples", "headroom_min_mib")}
        for name in JIT_PHASES:
            match = JIT_TUPLE.fullmatch(raw.get(name, ""))
            events, total_ms, max_ms, size = match.groups() if match else (None,) * 4
            window[name + "_events"] = int(events) if match else None
            window[name + "_total_ms"] = float(total_ms) if match else None
            window[name + "_max_ms"] = float(max_ms) if match else None
            window[name + "_bytes"] = int(size) if match else None
        result.append(window)
    return result


def measure(info, memory, diagnostics):
    rows, diagnostics, commit_verified = select_session(info, memory, diagnostics)
    metrics = {}

    def put(key, value, unit, source, reason="measurement_not_recorded"):
        metrics[key] = {"value": value, "unit": unit, "source": source,
                        "reason": reason if value is None else None}

    def aggregate(key, records, path, operation, unit, source, empty_reason=None):
        values = [field(row, path) for row in records]
        valid = bool(values) and all(number(value) and value >= 0 for value in values)
        put(key, operation(values) if valid else None, unit, source,
            empty_reason if empty_reason and not values else "missing_or_invalid_field_in_observed_records")

    def delta(key, path, unit):
        values = [field(row, path) for row in rows]
        if not values or any(not number(value) or value < 0 for value in values):
            put(key, None, unit, path, "counter_not_recorded_in_all_session_samples")
        elif any(current < prior for prior, current in zip(values, values[1:])):
            raise ValueError(f"Cumulative counter reset within session: {path}")
        else:
            put(key, values[-1] - values[0], unit, path)

    spu = profile_rows(diagnostics, "SPUPROF")
    epochs = {row.get("session") for row in spu}
    if spu and (None in epochs or len(epochs) != 1):
        raise ValueError("SPUPROF needs one reset epoch; cannot combine reboots")
    for phase in ("loading", "gameplay"):
        for suffix, operation, unit in (("attempts", sum, "count"), ("failures", sum, "count"),
                                         ("total_ms", sum, "ms"), ("max_ms", max, "ms")):
            aggregate(f"spu_{phase}_{suffix}", spu, f"{phase}_{suffix}", operation, unit,
                      "SPUPROF interval counters; observed windows")
    aggregate("spu_warm_reuses", spu, "warm_reuses", sum, "count", "SPUPROF")
    aggregate("spu_warmed_heavy_recompiles", spu, "warm_recompile_attempts", sum, "count", "SPUPROF")
    warmup = profile_rows(diagnostics, "SPUWARMUP end")
    aggregate("spu_warmup_elapsed_ms", warmup, "elapsed_ms", sum, "ms", "completed SPUWARMUP end records")
    aggregate("spu_warmup_failed_runs", warmup, "failed", sum, "count", "SPUWARMUP end")
    aggregate("spu_warmup_stopped_runs", warmup, "stopped", sum, "count", "SPUWARMUP end")
    aggregate("spu_warmup_analyzer_mismatches", warmup, "analyzer_mismatches", sum, "count", "SPUWARMUP end")
    resilience = profile_rows(diagnostics, "COREPROF_RESILIENCE")
    aggregate("legacy_spu_compile_observed_ms", resilience, "spu_compile_ms", sum, "ms",
              "COREPROF_RESILIENCE unclassified loading/gameplay windows")

    core = profile_rows(diagnostics, "COREPROF")
    aggregate("range_lock_wait_iterations", core, "range_stalls", sum, "count",
              "COREPROF polling iterations, not independent contention episodes")
    if core and all(number(row.get("frames")) and row["frames"] > 0 and
                    number(row.get("range_wait_ms")) and row["range_wait_ms"] >= 0 for row in core):
        waits = [row["range_wait_ms"] * row["frames"] for row in core]
        put("range_lock_legacy_total_ms", sum(waits), "ms", "COREPROF range_wait_ms * frames")
        put("range_lock_legacy_max_window_ms", max(waits), "ms", "COREPROF range_wait_ms * frames")
    else:
        put("range_lock_legacy_total_ms", None, "ms", "COREPROF", "native_range_lock_windows_missing")
        put("range_lock_legacy_max_window_ms", None, "ms", "COREPROF", "native_range_lock_windows_missing")
    ranges = profile_rows(diagnostics, "RANGELOCKPROF")
    range_epochs = {row.get("session") for row in ranges}
    if ranges and (None in range_epochs or len(range_epochs) != 1 or (epochs and range_epochs != epochs)):
        raise ValueError("RANGELOCKPROF/SPUPROF reset epochs disagree")
    for key, path, operation, unit in (
        ("range_lock_episodes", "episodes", sum, "count"),
        ("range_lock_episode_total_ms", "total_ms", sum, "ms"),
        ("range_lock_episode_max_ms", "max_ms", max, "ms"),
        ("range_lock_episode_max_iterations", "iterations_max", max, "count"),
        ("range_lock_blocker_samples", "blocker_samples", sum, "count"),
        ("range_lock_max_blockers", "blocker_max", max, "count"),
    ):
        aggregate(key, ranges, path, operation, unit, "RANGELOCKPROF observed windows")
    # JITPROF (Build 444) shares the profile reset epoch of the other windows.
    jit = jit_rows(diagnostics)
    jit_epochs = {row.get("session") for row in jit}
    if jit and (None in jit_epochs or len(jit_epochs) != 1 or
                (epochs and jit_epochs != epochs) or (range_epochs and jit_epochs != range_epochs)):
        raise ValueError("JITPROF/SPUPROF/RANGELOCKPROF reset epochs disagree")
    jit_reason = "jitprof_not_recorded_by_this_core" if not jit else None
    for name in JIT_PHASES:
        for suffix, operation, unit in JIT_FIELDS:
            aggregate(f"jit_{name}_{suffix}", jit, f"{name}_{suffix}", operation, unit,
                      "JITPROF per-phase compile accounting, exclusive of nested phases; observed windows",
                      jit_reason)
    headroom = [row for row in jit if number(row["headroom_samples"]) and row["headroom_samples"] > 0]
    aggregate("jit_headroom_min_mib", headroom, "headroom_min_mib", min, "MiB",
              "lowest process headroom sampled after a PPU module compile; JITPROF windows with headroom_samples > 0",
              jit_reason or "no_ppu_module_compiled_in_observed_windows")
    put("jit_windows", len(jit) if jit else None, "count", "JITPROF windows observed",
        "jitprof_not_recorded_by_this_core")
    # Native window summaries are valid observations but do not retain the
    # underlying distribution needed to reconstruct session percentiles.
    aggregate("native_frame_window_mean_ms", core, "frametime_ms", statistics.mean, "ms",
              "unweighted mean of native COREPROF window means")
    aggregate("native_frame_worst_window_p95_ms", core, "p95_ms", max, "ms", "COREPROF window p95")
    put("session_frame_p95_ms", None, "ms", "none", "raw_frame_intervals_not_exported")
    samples = []
    for row in diagnostics:
        if row.get("stage") != "performance_sample":
            continue
        values = dict(PAIR.findall(str(row.get("message", ""))))
        try:
            valid = int(values.get("valid", "0"), 0) & 1
        except ValueError:
            valid = False
        fps = numeric(values.get("fps"))
        if valid and fps is not None and fps >= 0:
            samples.append({"fps": fps})
    aggregate("sampled_fps_mean", samples, "fps", statistics.mean, "fps", "valid performance_sample FPS")
    aggregate("sampled_fps_min", samples, "fps", min, "fps", "valid performance_sample FPS")

    for key, path, operation in (
        ("process_resident_peak_bytes", "processResidentBytes", max),
        ("process_footprint_peak_bytes", "processFootprintBytes", max),
        ("process_available_min_bytes", "processAvailableBytes", min),
        ("donor_prepared_peak_bytes", "donationPreparedBytes", max),
        ("donor_live_loan_peak_bytes", "neoswapContribution.donorLoanLiveBytes", max),
        ("relay_guest_live_peak_bytes", "neoswapContribution.relayGuestLiveBytes", max),
        ("relay_host_live_peak_bytes", "neoswapContribution.relayHostLoanLiveBytes", max),
    ):
        aggregate(key, rows, path, operation, "bytes", path)
    backing = []
    for row in rows:
        values = [field(row, "neoswapContribution." + name) for name in
                  ("donorLoanLiveBytes", "relayGuestLiveBytes", "relayHostLoanLiveBytes")]
        backing.append({"live": sum(values) if all(number(v) and v >= 0 for v in values) else None})
    aggregate("neoswap_live_backing_peak_bytes", backing, "live", max, "bytes",
              "simultaneous occupied donor + guest relay + host relay backing, including idle host-loan shelves; not active donation/resident RAM/capacity")
    donations = [active_donation(row) for row in rows]
    donation_valid = bool(donations) and all(value is not None for value in donations)
    for key, name in DONATED_FIELDS:
        put(key, max(value[name] for value in donations) if donation_valid else None, "bytes",
            "neoswapContribution.schema=2/" + name + "; active backing, not residency or footprint savings",
            "schema_2_active_donation_missing_invalid_or_inconsistent_in_session_samples")
    guest = [guest_sample(row) for row in diagnostics if row.get("stage") == "neoswap_guest_sample"]
    guest_valid = complete_endpoints(guest)
    for name in GUEST_COUNTERS:
        values = [row[name] for row in guest] if guest_valid else []
        if any(current < prior for prior, current in zip(values, values[1:])):
            raise ValueError(f"Cumulative guest counter reset within session: {name}")
        unit = "bytes" if name.endswith("_bytes") else "ns" if name.endswith("_ns") else "count"
        put("guest_relay_" + name, values[-1] - values[0] if values else None, unit,
            "neoswap_guest_sample process-lifetime counter delta: " + name,
            "complete_valid_guest_samples_with_boot_and_end_not_recorded")
    maxima = [row["first_map_max_ns"] for row in guest] if guest_valid else []
    if any(current < prior for prior, current in zip(maxima, maxima[1:])):
        raise ValueError("Cumulative guest maximum reset within session: first_map_max_ns")
    put("guest_relay_first_map_process_lifetime_max_ns", max(maxima) if maxima else None, "ns",
        "first-map body after client mutex acquired; process maximum may predate this boot",
        "complete_valid_guest_samples_with_boot_and_end_not_recorded")
    count = metrics["guest_relay_candidate_first_maps"]["value"]
    elapsed = metrics["guest_relay_first_map_total_ns"]["value"]
    put("guest_relay_first_map_body_mean_us", elapsed / count / 1000 if count and elapsed is not None else None,
        "us", "first-map total_ns / candidate_first_maps; excludes client-mutex wait, outer VM locks and ordinary fallback",
        "no_measured_candidate_first_maps_or_guest_samples_missing")
    # Build 444 extension line. An older Core answers the extension query with
    # valid=0 (no counters) or never logs the line: unknown, never measured zeros.
    extension = [row for row in diagnostics if row.get("stage") == "neoswap_guest_sample_ext"]
    ext = [guest_sample_ext(row) for row in extension]
    ext_valid = complete_endpoints(ext)
    ext_reason = ("complete_valid_guest_extension_samples_with_boot_and_end_not_recorded"
                  if any(dict(PAIR.findall(str(row.get("message", "")))).get("valid") == "1" for row in extension)
                  else "extension_line_not_recorded_by_this_core")
    for name in GUEST_EXT_COUNTERS:
        values = [row[name] for row in ext] if ext_valid else []
        unit = "bytes" if name.endswith("_bytes") else "count"
        if name in GUEST_EXT_LIVE_COUNTERS:
            put(f"guest_relay_ext_{name}_peak", max(values) if values else None, unit,
                "neoswap_guest_sample_ext current live candidates on ordinary backing, maximum over session samples: " + name,
                ext_reason)
            put(f"guest_relay_ext_{name}_end", values[-1] if values else None, unit,
                "neoswap_guest_sample_ext current live candidates on ordinary backing at session_end: " + name,
                ext_reason)
            continue
        if any(current < prior for prior, current in zip(values, values[1:])):
            raise ValueError(f"Cumulative guest extension counter reset within session: {name}")
        put("guest_relay_ext_" + name, values[-1] - values[0] if values else None, unit,
            "neoswap_guest_sample_ext process-lifetime counter delta: " + name, ext_reason)
    put("neoswap_usable_capacity_bytes", None, "bytes", "none",
        "live_mappings_and_preparation_do_not_establish_additional_usable_capacity_under_gameplay_pressure")
    put("neoswap_fault_latency_ms", None, "ms", "none", "per_fault_duration_not_exported")
    put("neoswap_fallback_latency_ms", None, "ms", "none", "fallback_duration_not_exported")
    delta("cpu_buffer_fallbacks", "cpuBufferExperiment.fallbackCount", "count")
    for key in ("requests", "successes", "broker_busy", "donor_busy", "ready_misses", "fallback_count",
                "total_time_us", "prepare_requests", "prepared_loans", "prepare_failures"):
        delta("fast_acquisition_" + key, "fastAllocation." + key, "us" if key.endswith("_us") else "count")
    aggregate("fast_acquisition_process_lifetime_max_us", rows, "fastAllocation.max_time_us", max,
              "us", "process-lifetime high-water mark; may predate this session")
    requests = metrics["fast_acquisition_requests"]["value"]
    total_time = metrics["fast_acquisition_total_time_us"]["value"]
    put("fast_acquisition_mean_us", total_time / requests if requests and total_time is not None else None,
        "us", "delta acquisition total_time_us / delta requests; includes refusals",
        "no_measured_requests_or_acquisition_counters_missing")
    # Build 444 host-side direct admission on prepared-stock misses. The object
    # is only measured when the host reports it available in every sample.
    direct = "guestRelay.guestDirectCreation."
    admissions = [field(row, "guestRelay.guestDirectCreation") for row in rows]
    direct_recorded = bool(admissions) and all(isinstance(row, dict) and row.get("available") is True
                                               for row in admissions)
    for name in DIRECT_CREATION_COUNTERS:
        unit = "bytes" if name.endswith("Bytes") else "count"
        if direct_recorded:
            delta("host_direct_" + name, direct + name, unit)
        else:
            put("host_direct_" + name, None, unit, direct + name, "direct_admission_not_recorded_by_this_host")
    for key, name, operation, unit, source in (
        ("host_direct_oversizeMaxBytes", "oversizeMaxBytes", max, "bytes",
         "largest oversize request; process-lifetime high-water mark; may predate this session"),
        ("host_direct_allowanceBytes_mean", "allowanceBytes", statistics.mean, "bytes",
         "mean of the sampled direct allowance in force; a budget, not RAM"),
    ):
        if direct_recorded:
            aggregate(key, rows, direct + name, operation, unit, direct + name + "; " + source)
        else:
            put(key, None, unit, direct + name, "direct_admission_not_recorded_by_this_host")
    aggregate("budget_direct_guest_allowance_mean_bytes", rows, "budget.directGuestAllowanceBytes", statistics.mean,
              "bytes", "budget.directGuestAllowanceBytes; mean of sampled allowance in force, not RAM")
    delta("budget_demand_wakeups", "budget.demandWakeups", "count")
    aggregate("file_fallback_live_peak_bytes", rows, "neoswapContribution.fileFallbackLiveBytes", max, "bytes",
              "neoswapContribution.fileFallbackLiveBytes; file-backed fallback objects live at a sample, not RAM")
    preparation = [row["donationPreparation"] for row in rows if isinstance(row.get("donationPreparation"), dict)]
    warmup = {"modesObserved": sorted({row["mode"] for row in preparation if isinstance(row.get("mode"), str)}),
              "readinessTimedOut": any(row.get("readinessTimedOut") is True for row in preparation) if preparation else None,
              "campaignsObserved": sorted({row["campaign"] for row in preparation if number(row.get("campaign"))}),
              "meaning": "Prepared capacity and relay backend readiness do not prove gameplay memory benefit."}
    identity = {key: info[key] for key in IDENTITY}
    for key in ("physicalMemoryBytes", "osVersion"):
        identity[key] = next((row[key] for row in rows if row.get(key) is not None), None)
    return {"identity": identity, "sourceCommitEvidence": "log_and_manifest" if commit_verified else "manifest_only",
            "durationSeconds": rows[-1]["timestamp"] - info["bootTimestamp"],
            "observations": {"memory": len(rows), "spuWindows": len(spu), "coreWindows": len(core),
                             "rangeWindows": len(ranges), "jitWindows": len(jit), "fpsSamples": len(samples)},
            "donorPreparation": warmup, "metrics": metrics}


def compare(before, after, mode="same-title"):
    if mode not in COMPARISON_MODES:
        raise ValueError(f"Unknown comparison mode: {mode}")
    # One title on two builds shares its workload; two titles on one build
    # share the device and the source instead.
    if mode == "cross-title":
        keys = (*SHARED_IDENTITY, "sourceCommit")
    else:
        keys = ("title", "workloadId", *SHARED_IDENTITY)
    for key in keys:
        old, new = before["identity"][key], after["identity"][key]
        if old is None or old != new:
            raise ValueError(f"Incompatible comparison identity: {key}")
    changes = {}
    for key, old in before["metrics"].items():
        new = after["metrics"][key]
        changes[key] = new["value"] - old["value"] if number(old["value"]) and number(new["value"]) else None
    limitations = [
        "Workload/device/settings identities are operator attestations; source SHA is log-verified only where recorded.",
        "Observed log-window totals may omit initial/final partial windows or dropped messages.",
        "Cumulative counter deltas cover the first-to-last memory sample; process lifetime maxima can predate the boot.",
        "Loading SPU classification denotes startup compile scope, not the first playable frame.",
        "Range-lock waits are guest VM contention; NeoSwap acquisition latency is a separate measurement.",
        "Resident bytes, process footprint, prepared capacity and shared live backing must not be added as physical RAM.",
        "Schema-2 donated bytes exclude idle shelves; older occupied-backing counters cannot establish this value or footprint savings.",
        "Guest prepared hits/publications are cumulative objects/bytes, not active or resident RAM; first-map timing excludes mutex acquisition and the ordinary fallback allocator.",
        "No 50 s / 8.8 s / 118 ms / million-block baseline is assumed without identified source logs.",
    ]
    if mode == "cross-title":
        limitations.append(
            "Cross-title comparison explains differences between two games on one build; it is not a "
            "build-to-build improvement measurement and different workloads are not comparable in duration.")
    return {"schema": 1, "mode": mode, "before": before, "after": after, "afterMinusBefore": changes,
            "deviceValidationPassed": False, "automaticPromotionAllowed": False,
            "limitations": limitations}


def markdown(report):
    before, after = report["before"]["identity"], report["after"]["identity"]
    if report.get("mode", "same-title") == "cross-title":
        heading = [f"Title A: {before['title']} (`{before['sourceCommit']}`)",
                   f"Title B: {after['title']} (`{after['sourceCommit']}`)"]
    else:
        heading = [f"Before: `{before['sourceCommit']}`", f"After: `{after['sourceCommit']}`"]
    lines = ["RPCS3 + NeoSwap — observed before/after measurements", "", *heading, "",
             "| Metric | Unit | Before | After | Change |", "|---|---|---:|---:|---:|"]
    for key, old in report["before"]["metrics"].items():
        new = report["after"]["metrics"][key]
        display = lambda value: "unavailable" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)
        lines.append(f"| {key} | {old['unit']} | {display(old['value'])} | {display(new['value'])} | {display(report['afterMinusBefore'][key])} |")
    lines.extend(["", "Missing-data reasons and input hashes are in the JSON report. Device validation remains pending.", ""])
    lines.extend(f"- {note}" for note in report["limitations"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True, help="before-run manifest JSON")
    parser.add_argument("--after", type=Path, required=True, help="after-run manifest JSON")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--mode", choices=COMPARISON_MODES, default="same-title",
                        help="same-title: one title on two builds (default); "
                             "cross-title: two titles on one build and device")
    args = parser.parse_args()
    reports = []
    try:
        for path in (args.before, args.after):
            info = manifest(path)
            memory, memory_files = read_logs(info["memoryLogs"])
            diagnostics, diagnostic_files = read_logs(info["rpcs3Logs"])
            report = measure(info, memory, diagnostics)
            report["inputs"] = memory_files + diagnostic_files
            reports.append(report)
        result = compare(*reports, mode=args.mode)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown(result), encoding="utf-8")
    print("Observed comparison recorded; iPhone validation remains pending.")


if __name__ == "__main__":
    main()
