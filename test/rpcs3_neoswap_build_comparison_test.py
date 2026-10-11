#!/usr/bin/env python3
"""Behavioral evidence checks; all numbers below are synthetic test fixtures."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/compare_rpcs3_neoswap_builds.py"
SPEC = importlib.util.spec_from_file_location("rpcs3_neoswap_comparison", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(source="a" * 40, pid=123, title="BCES00510", workload="save-fixture-route-10s"):
    info = {"sourceCommit": source, "pid": pid, "sessionSequence": 1, "bootTimestamp": 100,
            "title": title, "workloadId": workload, "deviceId": "fixture-device",
            "settingsId": "fixture-settings"}
    memory = []
    for index, timestamp in enumerate((100, 105, 110)):
        memory.append({
            "pid": pid, "timestamp": timestamp,
            "event": ("rpcs3_memory_session_start", "sample", "rpcs3_memory_session_end")[index],
            "memoryProfile": {"sessionSequence": 1, "sampledSessionActive": index != 2},
            "experiment": {"sourceCommit": source, "mode": "integrated", "valid": True},
            "physicalMemoryBytes": 8 << 30, "osVersion": "fixture-ios", "processResidentBytes": 200 + index,
            "processFootprintBytes": 100 + index, "processAvailableBytes": 500 - index,
            "donationPreparedBytes": 1024, "neoswapContribution": {
                "donorLoanLiveBytes": 10 * index, "relayGuestLiveBytes": 30,
                "relayHostLoanLiveBytes": 20 - 5 * index},
            "cpuBufferExperiment": {"fallbackCount": 100 + index},
            "fastAllocation": {"requests": 10 + 2 * index, "successes": 5 + index,
                "broker_busy": index, "donor_busy": 0, "ready_misses": 0, "fallback_count": 5 + index,
                "total_time_us": 100 + 8 * index, "max_time_us": 50, "prepare_requests": index,
                "prepared_loans": index, "prepare_failures": 0},
            "donationPreparation": {"mode": ("warming", "relay-only", "donors-partial")[index],
                "campaign": 1, "readinessTimedOut": index == 1},
        })
    def diag(timestamp, stage, message):
        return {"pid": pid, "timestamp": timestamp, "stage": stage, "message": message}
    diagnostics = [diag(100, "game_boot_begin", title)]
    for index, timestamp in enumerate((104, 109)):
        diagnostics.extend([
            diag(timestamp, "core_log", "SPUPROF session=7 loading_attempts=2 loading_failures=0 "
                 "loading_total_ms=20 loading_max_ms=15 gameplay_attempts=1 gameplay_failures=0 "
                 "gameplay_total_ms=3 gameplay_max_ms=3 warm_reuses=10 warm_recompile_attempts=0"),
            diag(timestamp, "core_log", "RANGELOCKPROF session=7 episodes=2 total_ms=4 max_ms=3 "
                 "iterations_max=10 blocker_samples=3 blocker_max=2"),
            diag(timestamp, "core_log", "COREPROF frames=10 range_wait_ms=0.25 range_stalls=50 "
                 "frametime_ms=33 p95_ms=40"),
            diag(timestamp, "core_log", "COREPROF_RESILIENCE spu_compile_ms=23"),
            diag(timestamp, "performance_sample", f"title={title} valid=0x1 fps={index * 20} sample_epoch=1"),
        ])
    return info, memory, diagnostics


def donated_fixture():
    info, memory, diagnostics = fixture()
    # Disjoint peaks occur in different samples: the total is never their sum.
    for row, (guest, relay, donor) in zip(memory, ((40, 0, 0), (0, 45, 5), (0, 0, 0))):
        row["neoswapContribution"].update({
            "schema": 2, "donatedBytes": guest + relay + donor,
            "donatedGuestBytes": guest, "donatedHostRelayBytes": relay, "donatedDonorBytes": donor,
        })
    return info, memory, diagnostics


def guest_fixture():
    info, memory, diagnostics = donated_fixture()
    for index, (timestamp, phase) in enumerate(((100.1, "before_boot"), (101, "boot_return"),
                                               (106, "sample"), (109.5, "session_end"))):
        counters = {key: 100 + 10 * index for key in MODULE.GUEST_COUNTERS}
        counters.update(prepared_hit_bytes=(1 << 53) + 17 + 128 * index,
                        first_map_total_ns=100000 + 12000 * index, first_map_max_ns=5000 + 100 * index)
        message = (f"title=BCES00510 schema=1 valid=1 result=0 sample_epoch=1 phase={phase} "
                   "scope=process_lifetime gameplay_active=1 " +
                   " ".join(f"{key}={value}" for key, value in counters.items()))
        diagnostics.append({"pid": info["pid"], "timestamp": timestamp,
                            "stage": "neoswap_guest_sample", "message": message})
    diagnostics.sort(key=lambda row: row["timestamp"])
    return info, memory, diagnostics


def ext_fixture():
    """Build 444 Core: the extension line accompanies each base guest line.

    Cumulative counters grow by 10 per sample; the fallback_live_* pair is a
    current count that rises and falls as candidate objects die.
    """
    info, memory, diagnostics = guest_fixture()
    for index, (timestamp, phase) in enumerate(((100.1, "before_boot"), (101, "boot_return"),
                                               (106, "sample"), (109.5, "session_end"))):
        counters = {key: 200 + 10 * index for key in MODULE.GUEST_EXT_COUNTERS}
        counters.update(gameplay_direct_create_bytes=(1 << 53) + 5 + 64 * index,
                        fallback_live_objects=(3, 7, 2, 4)[index], fallback_live_bytes=(300, 900, 100, 500)[index])
        message = (f"title=BCES00510 schema=1 valid=1 result=0 sample_epoch=1 phase={phase} "
                   "scope=process_lifetime " + " ".join(f"{key}={value}" for key, value in counters.items()))
        diagnostics.append({"pid": info["pid"], "timestamp": timestamp,
                            "stage": "neoswap_guest_sample_ext", "message": message})
    diagnostics.sort(key=lambda row: row["timestamp"])
    return info, memory, diagnostics


def jit_line(index, session=7):
    """One Build 444 JITPROF window; each phase tuple is events:total_ms:max_ms:bytes.

    The first window completed no PPU module, so its printed 0.000 headroom
    must never become the session minimum.
    """
    phases = " ".join(
        f"{name}={1 + index + position}:{10.5 * (index + 1):.3f}:{6.25 + index:.3f}:{1024 * (index + 1)}"
        for position, name in enumerate(MODULE.JIT_PHASES))
    headroom = ("headroom_samples=0 headroom_min_mib=0.000", "headroom_samples=2 headroom_min_mib=512.250")[index]
    return f"JITPROF session={session} {phases} {headroom}"


def jit_fixture():
    info, memory, diagnostics = fixture()
    for index, timestamp in enumerate((104.5, 109.6)):
        diagnostics.append({"pid": info["pid"], "timestamp": timestamp, "stage": "core_log",
                            "message": jit_line(index)})
    diagnostics.sort(key=lambda row: row["timestamp"])
    return info, memory, diagnostics


def direct_fixture():
    """Build 444 host: direct admission object, budget allowance/wakeups, file fallback."""
    info, memory, diagnostics = fixture()
    for index, row in enumerate(memory):
        admission = {key: 50 + 5 * index for key in MODULE.DIRECT_CREATION_COUNTERS}
        admission.update(schema=1, available=True, requestedBytes=(1 << 40) + 4096 * index,
                         oversizeMaxBytes=(0, 4096, 2048)[index], allowanceBytes=(100, 200, 300)[index],
                         createdIsDonated=False, residencyMeasured=False)
        row["guestRelay"] = {"guestDirectCreation": admission}
        row["budget"] = {"directGuestAllowanceBytes": (10, 20, 30)[index], "demandWakeups": 7 + 3 * index}
        row["neoswapContribution"]["fileFallbackLiveBytes"] = (0, 777, 5)[index]
    return info, memory, diagnostics


class ComparisonTest(unittest.TestCase):
    def test_observed_metrics_respect_units_and_semantics(self):
        info, memory, diagnostics = fixture()
        report = MODULE.measure(info, memory, diagnostics)
        value = lambda key: report["metrics"][key]["value"]
        self.assertEqual(value("spu_loading_total_ms"), 40)
        self.assertEqual(value("spu_loading_max_ms"), 15)
        self.assertEqual(value("spu_gameplay_total_ms"), 6)
        self.assertEqual(value("spu_warmed_heavy_recompiles"), 0)
        self.assertEqual(value("range_lock_wait_iterations"), 100)
        self.assertEqual(value("range_lock_legacy_total_ms"), 5)
        self.assertEqual(value("range_lock_legacy_max_window_ms"), 2.5)
        self.assertEqual(value("range_lock_episodes"), 4)
        self.assertEqual(value("range_lock_episode_total_ms"), 8)
        self.assertEqual(value("range_lock_episode_max_ms"), 3)
        self.assertEqual(value("sampled_fps_mean"), 10)
        self.assertEqual(value("sampled_fps_min"), 0)
        self.assertEqual(value("native_frame_worst_window_p95_ms"), 40)
        self.assertIsNone(value("session_frame_p95_ms"))
        # Max of simultaneous disjoint values, NOT sum of unrelated high-water marks.
        self.assertEqual(value("neoswap_live_backing_peak_bytes"), 60)
        self.assertIsNone(value("neoswap_donated_peak_bytes"))
        self.assertEqual(value("cpu_buffer_fallbacks"), 2)
        self.assertEqual(value("fast_acquisition_requests"), 4)
        self.assertEqual(value("fast_acquisition_total_time_us"), 16)
        self.assertEqual(value("fast_acquisition_mean_us"), 4)
        self.assertIsNone(value("neoswap_usable_capacity_bytes"))
        self.assertIsNone(value("neoswap_fault_latency_ms"))
        self.assertIsNone(value("neoswap_fallback_latency_ms"))
        self.assertTrue(report["donorPreparation"]["readinessTimedOut"])
        self.assertIn("relay-only", report["donorPreparation"]["modesObserved"])

    def test_active_donation_does_not_count_idle_capacity_or_add_independent_peaks(self):
        info, memory, diagnostics = donated_fixture()
        for row in memory:
            row["donationPreparedBytes"] = 8 << 30
            row["neoswapContribution"].update({
                "donorLoanLiveBytes": 100, "relayGuestLiveBytes": 300,
                "relayHostLoanLiveBytes": 200,
            })
        report = MODULE.measure(info, memory, diagnostics)
        value = lambda key: report["metrics"][key]["value"]
        self.assertEqual(value("neoswap_donated_peak_bytes"), 50)
        self.assertEqual(value("neoswap_donated_guest_peak_bytes"), 40)
        self.assertEqual(value("neoswap_donated_host_relay_peak_bytes"), 45)
        self.assertEqual(value("neoswap_donated_donor_peak_bytes"), 5)
        self.assertEqual(value("neoswap_live_backing_peak_bytes"), 600)
        self.assertEqual(value("donor_prepared_peak_bytes"), 8 << 30)
        self.assertEqual(value("process_footprint_peak_bytes"), 102)
        self.assertIn("idle host-loan shelves", report["metrics"]["neoswap_live_backing_peak_bytes"]["source"])

    def test_active_donation_rejects_missing_legacy_inconsistent_or_non_uint64_samples(self):
        changes = [
            lambda row: row.pop("neoswapContribution"),
            lambda row: row["neoswapContribution"].pop("schema"),
            lambda row: row["neoswapContribution"].update(schema=1),
            lambda row: row["neoswapContribution"].update(schema=2.0),
            lambda row: row["neoswapContribution"].update(donatedBytes=49),
        ]
        for _, name in MODULE.DONATED_FIELDS:
            changes.append(lambda row, key=name: row["neoswapContribution"].pop(key))
            for bad in (None, True, False, -1, 1.5, 50.0, float("nan"), float("inf"), 1 << 64):
                changes.append(lambda row, key=name, value=bad: row["neoswapContribution"].update({key: value}))
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                args = donated_fixture()
                change(args[1][1])
                report = MODULE.measure(*args)
                for key, _ in MODULE.DONATED_FIELDS:
                    self.assertIsNone(report["metrics"][key]["value"], key)
                    self.assertTrue(report["metrics"][key]["reason"], key)
                self.assertEqual(report["metrics"]["process_footprint_peak_bytes"]["value"], 102)

    def test_active_donation_preserves_valid_zero_and_exact_uint64_boundary(self):
        for expected in (0, (1 << 64) - 1):
            with self.subTest(bytes=expected):
                args = donated_fixture()
                for row in args[1]:
                    row["neoswapContribution"].update({
                        "donatedBytes": expected, "donatedGuestBytes": expected,
                        "donatedHostRelayBytes": 0, "donatedDonorBytes": 0,
                    })
                measured = MODULE.measure(*args)["metrics"]["neoswap_donated_peak_bytes"]
                self.assertEqual(measured["value"], expected)
                self.assertIsNone(measured["reason"])

    def test_comparing_legacy_to_active_donation_keeps_change_unknown(self):
        before = MODULE.measure(*fixture())
        after = MODULE.measure(*donated_fixture())
        report = MODULE.compare(before, after)
        self.assertIsNone(report["afterMinusBefore"]["neoswap_donated_peak_bytes"])
        self.assertEqual(after["metrics"]["neoswap_donated_peak_bytes"]["value"], 50)
        self.assertFalse(report["deviceValidationPassed"])

    def test_guest_deltas_include_boot_and_keep_exact_large_counters(self):
        report = MODULE.measure(*guest_fixture())
        value = lambda name: report["metrics"][name]["value"]
        self.assertEqual(value("guest_relay_candidate_first_maps"), 30)
        self.assertEqual(value("guest_relay_prepared_hit_bytes"), 384)
        self.assertEqual(value("guest_relay_prepared_published_bytes"), 30)
        self.assertEqual(value("guest_relay_ordinary_fallback_bytes"), 30)
        self.assertEqual(value("guest_relay_first_map_total_ns"), 36000)
        self.assertEqual(value("guest_relay_first_map_body_mean_us"), 1.2)
        self.assertEqual(value("guest_relay_first_map_process_lifetime_max_ns"), 5300)
        # Publication bytes are not added to active backing or deducted from footprint.
        self.assertEqual(value("neoswap_donated_peak_bytes"), 50)
        self.assertEqual(value("process_footprint_peak_bytes"), 102)

    def test_guest_missing_endpoints_or_invalid_snapshot_never_becomes_zero(self):
        mutations = [
            lambda rows: rows.pop(0),
            lambda rows: rows.pop(),
            lambda rows: rows[1].update(message=rows[1]["message"].replace("valid=1", "valid=0")),
            lambda rows: rows[1].update(message=rows[1]["message"].replace("schema=1", "schema=2")),
            lambda rows: rows[1].update(message=rows[1]["message"].replace("map_failures=110", "")),
            lambda rows: rows[1].update(message=rows[1]["message"].replace("requested_bytes=110", "requested_bytes=1.5")),
            lambda rows: rows[1].update(message=rows[1]["message"].replace("requested_bytes=110", f"requested_bytes={1 << 64}")),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(change=index):
                info, memory, diagnostics = guest_fixture()
                rows = [row for row in diagnostics if row["stage"] == "neoswap_guest_sample"]
                mutation(rows)
                diagnostics = [row for row in diagnostics if row["stage"] != "neoswap_guest_sample"] + rows
                diagnostics.sort(key=lambda row: row["timestamp"])
                report = MODULE.measure(info, memory, diagnostics)
                self.assertIsNone(report["metrics"]["guest_relay_candidate_first_maps"]["value"])
                self.assertIsNone(report["metrics"]["guest_relay_first_map_body_mean_us"]["value"])
                self.assertEqual(report["metrics"]["neoswap_donated_peak_bytes"]["value"], 50)

    def test_guest_counter_resets_and_different_epoch_rejected(self):
        for old, new in (("candidate_first_maps=110", "candidate_first_maps=1"),
                         ("first_map_max_ns=5100", "first_map_max_ns=1"),
                         ("sample_epoch=1", "sample_epoch=2"),
                         ("title=BCES00510", "title=OTHER0001")):
            with self.subTest(field=old):
                args = guest_fixture()
                row = next(row for row in args[2] if row["stage"] == "neoswap_guest_sample" and "phase=boot_return" in row["message"])
                row["message"] = row["message"].replace(old, new)
                with self.assertRaises(ValueError):
                    MODULE.measure(*args)

    def test_before_after_different_revisions_allowed_and_not_device_validation(self):
        before = MODULE.measure(*fixture())
        after = MODULE.measure(*fixture("b" * 40, 456))
        report = MODULE.compare(before, after)
        self.assertFalse(report["deviceValidationPassed"])
        self.assertFalse(report["automaticPromotionAllowed"])
        self.assertEqual(report["afterMinusBefore"]["spu_gameplay_total_ms"], 0)
        self.assertIsNone(report["afterMinusBefore"]["neoswap_fault_latency_ms"])
        for key in ("title", "workloadId", "deviceId", "settingsId", "physicalMemoryBytes", "osVersion"):
            with self.subTest(key=key):
                bad = copy.deepcopy(after)
                bad["identity"][key] = "unrelated"
                with self.assertRaisesRegex(ValueError, key):
                    MODULE.compare(before, bad)

    def test_missing_and_partial_telemetry_is_not_zero(self):
        info, memory, diagnostics = fixture()
        legacy = [row for row in diagnostics if "SPUPROF" not in row["message"] and
                  "RANGELOCKPROF" not in row["message"] and "COREPROF " not in row["message"]]
        for row in memory:
            del row["fastAllocation"]
            del row["neoswapContribution"]
            row["donationPreparedBytes"] = 8 << 30
        result = MODULE.measure(info, memory, legacy)
        for key in ("spu_gameplay_total_ms", "range_lock_episode_total_ms", "native_frame_window_mean_ms",
                    "fast_acquisition_requests", "neoswap_live_backing_peak_bytes"):
            self.assertIsNone(result["metrics"][key]["value"], key)
            self.assertTrue(result["metrics"][key]["reason"], key)
        self.assertEqual(result["metrics"]["legacy_spu_compile_observed_ms"]["value"], 46)
        self.assertEqual(result["metrics"]["sampled_fps_mean"]["value"], 10)
        # One incomplete new window invalidates its affected total.
        diagnostics[-5]["message"] = diagnostics[-5]["message"].replace("gameplay_total_ms=3", "")
        result = MODULE.measure(info, memory, diagnostics)
        self.assertIsNone(result["metrics"]["spu_gameplay_total_ms"]["value"])

    def test_reused_sessions_mixed_titles_commits_and_epochs_rejected(self):
        def rejected(change):
            args = fixture()
            change(*args)
            with self.assertRaises(ValueError):
                MODULE.measure(*args)
        rejected(lambda i, m, d: m.append(dict(m[0], timestamp=1000)))
        rejected(lambda i, m, d: m.pop())
        rejected(lambda i, m, d: m[1]["experiment"].update(sourceCommit="b" * 40))
        rejected(lambda i, m, d: d.append(dict(d[0], timestamp=106)))
        rejected(lambda i, m, d: d[-1].update(message="title=OTHER0001 valid=1 fps=30"))
        rejected(lambda i, m, d: d[-1].update(message=d[-1]["message"].replace("sample_epoch=1", "sample_epoch=2")))
        rejected(lambda i, m, d: d[-5].update(message=d[-5]["message"].replace("session=7", "session=8")))
        rejected(lambda i, m, d: d[-4].update(message=d[-4]["message"].replace("session=7", "session=8")))
        rejected(lambda i, m, d: m[1]["fastAllocation"].update(requests=1))
        rejected(lambda i, m, d: m[1]["cpuBufferExperiment"].update(fallbackCount=1))

    def test_manifest_sha_not_in_log_is_explicitly_unverified(self):
        info, memory, diagnostics = fixture()
        for row in memory:
            del row["experiment"]["sourceCommit"]
        self.assertEqual(MODULE.measure(info, memory, diagnostics)["sourceCommitEvidence"], "manifest_only")

    def test_cli_hashes_inputs_deduplicates_rotation_and_writes_valid_json_table(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name, args in (("before", fixture()), ("after", fixture("b" * 40, 456))):
                info, memory, diagnostics = args
                for kind, records in (("memory", memory), ("rpcs3", diagnostics)):
                    (directory / f"{name}-{kind}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in records))
                info.update(memoryLogs=[f"{name}-memory.jsonl", f"{name}-memory.jsonl"],
                            rpcs3Logs=[f"{name}-rpcs3.jsonl"])
                (directory / f"{name}.json").write_text(json.dumps(info))
            subprocess.run([sys.executable, str(TOOL), "--before", str(directory / "before.json"),
                "--after", str(directory / "after.json"), "--output", str(directory / "report.json"),
                "--markdown", str(directory / "report.md")], check=True, capture_output=True, text=True)
            result = json.loads((directory / "report.json").read_text())
            self.assertEqual(result["before"]["observations"]["memory"], 3)
            self.assertEqual(len(result["before"]["inputs"][0]["sha256"]), 64)
            self.assertIn("| Metric | Unit | Before | After | Change |", (directory / "report.md").read_text())
            (directory / "bad.jsonl").write_text('{"timestamp":1}\n{')
            with self.assertRaisesRegex(ValueError, "incomplete/invalid JSONL"):
                MODULE.read_logs([directory / "bad.jsonl"])

    # --- Build 444: guest extension line, JITPROF, host direct admission, cross-title mode.

    def test_guest_extension_deltas_and_live_peaks_keep_exact_counters(self):
        report = MODULE.measure(*ext_fixture())
        value = lambda name: report["metrics"][name]["value"]
        self.assertEqual(value("guest_relay_ext_gameplay_direct_requests"), 30)
        self.assertEqual(value("guest_relay_ext_gameplay_direct_create_bytes"), 192)
        self.assertEqual(value("guest_relay_ext_boot_creates"), 30)
        self.assertEqual(value("guest_relay_ext_direct_published_bytes"), 30)
        self.assertEqual(report["metrics"]["guest_relay_ext_direct_published_bytes"]["unit"], "bytes")
        self.assertEqual(report["metrics"]["guest_relay_ext_boot_creates"]["unit"], "count")
        self.assertIsNone(report["metrics"]["guest_relay_ext_gameplay_direct_requests"]["reason"])
        # Live counts rise and fall with object lifetime: a peak and an end value, never a delta.
        self.assertEqual(value("guest_relay_ext_fallback_live_bytes_peak"), 900)
        self.assertEqual(value("guest_relay_ext_fallback_live_bytes_end"), 500)
        self.assertEqual(value("guest_relay_ext_fallback_live_objects_peak"), 7)
        self.assertEqual(value("guest_relay_ext_fallback_live_objects_end"), 4)
        for name in MODULE.GUEST_EXT_LIVE_COUNTERS:
            self.assertNotIn("guest_relay_ext_" + name, report["metrics"])
        self.assertEqual(len([key for key in report["metrics"] if key.startswith("guest_relay_ext_")]),
                         len(MODULE.GUEST_EXT_COUNTERS) + len(MODULE.GUEST_EXT_LIVE_COUNTERS))
        # Base counters, donation and footprint are untouched by the extension.
        self.assertEqual(value("guest_relay_candidate_first_maps"), 30)
        self.assertEqual(value("neoswap_donated_peak_bytes"), 50)
        self.assertEqual(value("process_footprint_peak_bytes"), 102)

    def test_guest_extension_missing_or_incomplete_is_null_with_reason(self):
        phase = lambda row: dict(MODULE.PAIR.findall(row["message"]))["phase"]
        older_core = ("title=BCES00510 schema=1 valid=0 result=-3 sample_epoch=1 phase={} scope=process_lifetime")
        cases = [
            (lambda rows: rows.clear(), "extension_line_not_recorded_by_this_core"),
            (lambda rows: [row.update(message=older_core.format(phase(row))) for row in rows],
             "extension_line_not_recorded_by_this_core"),
            (lambda rows: rows.pop(), "complete_valid_guest_extension_samples_with_boot_and_end_not_recorded"),
            (lambda rows: rows.pop(0), "complete_valid_guest_extension_samples_with_boot_and_end_not_recorded"),
            (lambda rows: rows[1].update(message=rows[1]["message"].replace("boot_creates=210", "")),
             "complete_valid_guest_extension_samples_with_boot_and_end_not_recorded"),
            (lambda rows: rows[1].update(message=rows[1]["message"].replace("boot_creates=210", "boot_creates=2.5")),
             "complete_valid_guest_extension_samples_with_boot_and_end_not_recorded"),
            (lambda rows: rows[1].update(message=rows[1]["message"].replace("boot_creates=210", f"boot_creates={1 << 64}")),
             "complete_valid_guest_extension_samples_with_boot_and_end_not_recorded"),
            (lambda rows: rows[1].update(message=rows[1]["message"].replace("valid=1", "valid=0")),
             "complete_valid_guest_extension_samples_with_boot_and_end_not_recorded"),
        ]
        for index, (mutation, reason) in enumerate(cases):
            with self.subTest(change=index):
                info, memory, diagnostics = ext_fixture()
                rows = [row for row in diagnostics if row["stage"] == "neoswap_guest_sample_ext"]
                mutation(rows)
                diagnostics = [row for row in diagnostics if row["stage"] != "neoswap_guest_sample_ext"] + rows
                diagnostics.sort(key=lambda row: row["timestamp"])
                report = MODULE.measure(info, memory, diagnostics)
                keys = [key for key in report["metrics"] if key.startswith("guest_relay_ext_")]
                self.assertEqual(len(keys), len(MODULE.GUEST_EXT_COUNTERS) + len(MODULE.GUEST_EXT_LIVE_COUNTERS))
                for key in keys:
                    self.assertIsNone(report["metrics"][key]["value"], key)
                    self.assertEqual(report["metrics"][key]["reason"], reason, key)
                # The base line keeps measuring independently of the extension.
                self.assertEqual(report["metrics"]["guest_relay_candidate_first_maps"]["value"], 30)

    def test_guest_extension_counter_reset_or_other_epoch_rejected(self):
        for old, new in (("gameplay_direct_requests=210", "gameplay_direct_requests=1"),
                         ("direct_published_bytes=210", "direct_published_bytes=199"),
                         ("sample_epoch=1", "sample_epoch=2"),
                         ("title=BCES00510", "title=OTHER0001")):
            with self.subTest(field=old):
                args = ext_fixture()
                row = next(row for row in args[2] if row["stage"] == "neoswap_guest_sample_ext" and "phase=boot_return" in row["message"])
                row["message"] = row["message"].replace(old, new)
                with self.assertRaises(ValueError):
                    MODULE.measure(*args)

    def test_jitprof_tuples_use_sum_max_and_min_semantics(self):
        report = MODULE.measure(*jit_fixture())
        value = lambda name: report["metrics"][name]["value"]
        self.assertEqual(value("jit_ppu_translate_events"), 3)
        self.assertEqual(value("jit_ppu_translate_total_ms"), 31.5)
        self.assertEqual(value("jit_ppu_translate_max_ms"), 7.25)
        self.assertEqual(value("jit_ppu_translate_bytes"), 3072)
        self.assertEqual(value("jit_spu_codegen_events"), 25)
        self.assertEqual(value("jit_spu_codegen_bytes"), 3072)
        for suffix, unit in (("events", "count"), ("total_ms", "ms"), ("max_ms", "ms"), ("bytes", "bytes")):
            self.assertEqual(report["metrics"][f"jit_ppu_cache_read_{suffix}"]["unit"], unit)
        # The window without a completed PPU module prints 0.000: it is not a minimum.
        self.assertEqual(value("jit_headroom_min_mib"), 512.25)
        self.assertEqual(report["metrics"]["jit_headroom_min_mib"]["unit"], "MiB")
        self.assertEqual(value("jit_windows"), 2)
        self.assertEqual(report["observations"]["jitWindows"], 2)
        self.assertEqual(len([key for key in report["metrics"] if key.startswith("jit_")]),
                         len(MODULE.JIT_PHASES) * len(MODULE.JIT_FIELDS) + 2)
        # The generic numeric profile parser cannot read a tuple: unknown, never zero.
        self.assertIsNone(MODULE.profile_rows(jit_fixture()[2], "JITPROF")[0]["ppu_translate"])
        # One malformed tuple leaves only its phase unknown in the observed windows.
        info, memory, diagnostics = jit_fixture()
        row = next(row for row in diagnostics if row["message"].startswith("JITPROF") and "session=7 ppu_translate=1:" in row["message"])
        row["message"] = row["message"].replace("ppu_opt=2:10.500:6.250:1024", "ppu_opt=2:10.500")
        partial = MODULE.measure(info, memory, diagnostics)["metrics"]
        for suffix in ("events", "total_ms", "max_ms", "bytes"):
            self.assertIsNone(partial[f"jit_ppu_opt_{suffix}"]["value"])
            self.assertEqual(partial[f"jit_ppu_opt_{suffix}"]["reason"], "missing_or_invalid_field_in_observed_records")
        self.assertEqual(partial["jit_ppu_translate_events"]["value"], 3)

    def test_jitprof_missing_or_without_compiles_is_null_with_reason(self):
        report = MODULE.measure(*fixture())
        keys = [key for key in report["metrics"] if key.startswith("jit_")]
        self.assertEqual(len(keys), len(MODULE.JIT_PHASES) * len(MODULE.JIT_FIELDS) + 2)
        for key in keys:
            self.assertIsNone(report["metrics"][key]["value"], key)
            self.assertEqual(report["metrics"][key]["reason"], "jitprof_not_recorded_by_this_core", key)
        self.assertEqual(report["observations"]["jitWindows"], 0)
        info, memory, diagnostics = jit_fixture()
        for row in diagnostics:
            row["message"] = row["message"].replace("headroom_samples=2 headroom_min_mib=512.250",
                                                    "headroom_samples=0 headroom_min_mib=0.000")
        idle = MODULE.measure(info, memory, diagnostics)["metrics"]
        self.assertIsNone(idle["jit_headroom_min_mib"]["value"])
        self.assertEqual(idle["jit_headroom_min_mib"]["reason"], "no_ppu_module_compiled_in_observed_windows")
        self.assertEqual(idle["jit_ppu_translate_events"]["value"], 3)
        self.assertEqual(idle["jit_windows"]["value"], 2)

    def test_jitprof_epoch_must_match_spu_and_range_lock_profiles(self):
        def rejected(change):
            info, memory, diagnostics = jit_fixture()
            change(diagnostics)
            with self.assertRaisesRegex(ValueError, "epoch"):
                MODULE.measure(info, memory, diagnostics)
        jit = lambda rows: [row for row in rows if row["message"].startswith("JITPROF")]
        rejected(lambda rows: [row.update(message=row["message"].replace("session=7", "session=8")) for row in jit(rows)])
        rejected(lambda rows: jit(rows)[1].update(message=jit(rows)[1]["message"].replace("session=7", "session=8")))
        rejected(lambda rows: jit(rows)[0].update(message=jit(rows)[0]["message"].replace("session=7 ", "")))
        # Without SPUPROF/RANGELOCKPROF windows, one JITPROF epoch stands on its own.
        info, memory, diagnostics = jit_fixture()
        alone = [row for row in diagnostics if "SPUPROF" not in row["message"] and "RANGELOCKPROF" not in row["message"]]
        for row in jit(alone):
            row["message"] = row["message"].replace("session=7", "session=8")
        self.assertEqual(MODULE.measure(info, memory, alone)["metrics"]["jit_windows"]["value"], 2)

    def test_host_direct_admission_deltas_budget_allowance_and_file_fallback(self):
        report = MODULE.measure(*direct_fixture())
        value = lambda name: report["metrics"][name]["value"]
        self.assertEqual(value("host_direct_requests"), 10)
        self.assertEqual(value("host_direct_requestedBytes"), 8192)
        self.assertEqual(value("host_direct_refusedInvalid"), 10)
        self.assertEqual(value("host_direct_wakeups"), 10)
        self.assertEqual(report["metrics"]["host_direct_createdBytes"]["unit"], "bytes")
        self.assertEqual(report["metrics"]["host_direct_refusedPressure"]["unit"], "count")
        self.assertIsNone(report["metrics"]["host_direct_requests"]["reason"])
        self.assertEqual(value("host_direct_oversizeMaxBytes"), 4096)
        self.assertEqual(value("host_direct_allowanceBytes_mean"), 200)
        self.assertEqual(value("budget_direct_guest_allowance_mean_bytes"), 20)
        self.assertEqual(value("budget_demand_wakeups"), 6)
        self.assertEqual(value("file_fallback_live_peak_bytes"), 777)
        self.assertEqual(len([key for key in report["metrics"] if key.startswith("host_direct_")]),
                         len(MODULE.DIRECT_CREATION_COUNTERS) + 2)
        # Admission objects and budgets are never added to donation, backing or footprint.
        self.assertEqual(value("process_footprint_peak_bytes"), 102)
        self.assertEqual(value("neoswap_live_backing_peak_bytes"), 60)
        self.assertIsNone(value("neoswap_donated_peak_bytes"))

    def test_host_direct_admission_absent_or_unavailable_is_null_not_zero(self):
        absent = MODULE.measure(*fixture())["metrics"]
        for key in [key for key in absent if key.startswith("host_direct_")]:
            self.assertIsNone(absent[key]["value"], key)
            self.assertEqual(absent[key]["reason"], "direct_admission_not_recorded_by_this_host", key)
        for key, reason in (("budget_direct_guest_allowance_mean_bytes", "missing_or_invalid_field_in_observed_records"),
                            ("budget_demand_wakeups", "counter_not_recorded_in_all_session_samples"),
                            ("file_fallback_live_peak_bytes", "missing_or_invalid_field_in_observed_records")):
            self.assertIsNone(absent[key]["value"], key)
            self.assertEqual(absent[key]["reason"], reason, key)
        changes = [
            lambda row: row.pop("guestRelay"),
            lambda row: row["guestRelay"].pop("guestDirectCreation"),
            lambda row: row["guestRelay"]["guestDirectCreation"].update(available=False),
            lambda row: row["guestRelay"]["guestDirectCreation"].update(available=1),
            lambda row: row["guestRelay"].update(guestDirectCreation={"schema": 1, "available": False, "result": -3}),
        ]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                info, memory, diagnostics = direct_fixture()
                change(memory[1])
                metrics = MODULE.measure(info, memory, diagnostics)["metrics"]
                for key in [key for key in metrics if key.startswith("host_direct_")]:
                    self.assertIsNone(metrics[key]["value"], key)
                    self.assertEqual(metrics[key]["reason"], "direct_admission_not_recorded_by_this_host", key)
                self.assertEqual(metrics["budget_demand_wakeups"]["value"], 6)
        # A cumulative admission counter running backwards is a reset, not a negative delta.
        info, memory, diagnostics = direct_fixture()
        memory[2]["guestRelay"]["guestDirectCreation"]["created"] = 1
        with self.assertRaisesRegex(ValueError, "guestDirectCreation.created"):
            MODULE.measure(info, memory, diagnostics)

    def test_cross_title_mode_compares_two_titles_on_one_build_only(self):
        before = MODULE.measure(*fixture())
        other = MODULE.measure(*fixture(pid=456, title="NPUB30000", workload="save-other-route-5s"))
        report = MODULE.compare(before, other, mode="cross-title")
        self.assertEqual(report["mode"], "cross-title")
        self.assertEqual(report["schema"], 1)
        self.assertEqual(report["afterMinusBefore"]["spu_gameplay_total_ms"], 0)
        self.assertIsNone(report["afterMinusBefore"]["neoswap_fault_latency_ms"])
        self.assertFalse(report["deviceValidationPassed"])
        self.assertFalse(report["automaticPromotionAllowed"])
        self.assertIn("Cross-title comparison explains differences between two games on one build; it is not a "
                      "build-to-build improvement measurement and different workloads are not comparable in duration.",
                      report["limitations"])
        text = MODULE.markdown(report)
        self.assertIn(f"Title A: BCES00510 (`{'a' * 40}`)", text)
        self.assertIn(f"Title B: NPUB30000 (`{'a' * 40}`)", text)
        self.assertNotIn("Before: `", text)
        self.assertNotIn("After: `", text)
        self.assertIn("| Metric | Unit | Before | After | Change |", text)
        # The other title on another build is two builds: refused on the commit.
        rebuilt = MODULE.measure(*fixture("b" * 40, 789, title="NPUB30000", workload="save-other-route-5s"))
        with self.assertRaisesRegex(ValueError, "sourceCommit"):
            MODULE.compare(before, rebuilt, mode="cross-title")
        for key in ("deviceId", "settingsId", "physicalMemoryBytes", "osVersion"):
            with self.subTest(key=key):
                bad = copy.deepcopy(other)
                bad["identity"][key] = "unrelated"
                with self.assertRaisesRegex(ValueError, key):
                    MODULE.compare(before, bad, mode="cross-title")
        with self.assertRaisesRegex(ValueError, "mode"):
            MODULE.compare(before, other, mode="any-title")

    def test_same_title_mode_still_refuses_other_titles_and_keeps_its_report(self):
        before = MODULE.measure(*fixture())
        other = MODULE.measure(*fixture(pid=456, title="NPUB30000", workload="save-other-route-5s"))
        for options in ({}, {"mode": "same-title"}):
            with self.subTest(options=options):
                with self.assertRaisesRegex(ValueError, "title"):
                    MODULE.compare(before, other, **options)
        report = MODULE.compare(before, MODULE.measure(*fixture("b" * 40, 456)))
        self.assertEqual(report["mode"], "same-title")
        self.assertFalse(any("Cross-title" in note for note in report["limitations"]))
        text = MODULE.markdown(report)
        self.assertIn(f"Before: `{'a' * 40}`", text)
        self.assertIn(f"After: `{'b' * 40}`", text)
        self.assertNotIn("Title A:", text)

    def test_cli_mode_flag_selects_cross_title_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name, args in (("a", fixture()),
                               ("b", fixture(pid=456, title="NPUB30000", workload="save-other-route-5s")),
                               ("c", fixture("b" * 40, 789, title="NPUB30000", workload="save-other-route-5s"))):
                info, memory, diagnostics = args
                for kind, records in (("memory", memory), ("rpcs3", diagnostics)):
                    (directory / f"{name}-{kind}.jsonl").write_text(
                        "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
                info.update(memoryLogs=[f"{name}-memory.jsonl"], rpcs3Logs=[f"{name}-rpcs3.jsonl"])
                (directory / f"{name}.json").write_text(json.dumps(info), encoding="utf-8")
            command = [sys.executable, str(TOOL), "--before", str(directory / "a.json"),
                       "--output", str(directory / "report.json"), "--markdown", str(directory / "report.md")]
            refused = subprocess.run(command + ["--after", str(directory / "b.json")], capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("title", refused.stderr)
            subprocess.run(command + ["--after", str(directory / "b.json"), "--mode", "cross-title"],
                           check=True, capture_output=True, text=True)
            result = json.loads((directory / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(result["mode"], "cross-title")
            self.assertEqual((result["before"]["identity"]["title"], result["after"]["identity"]["title"]),
                             ("BCES00510", "NPUB30000"))
            self.assertIn(f"Title B: NPUB30000 (`{'a' * 40}`)", (directory / "report.md").read_text(encoding="utf-8"))
            rebuilt = subprocess.run(command + ["--after", str(directory / "c.json"), "--mode", "cross-title"],
                                     capture_output=True, text=True)
            self.assertNotEqual(rebuilt.returncode, 0)
            self.assertIn("sourceCommit", rebuilt.stderr)
            unknown = subprocess.run(command + ["--after", str(directory / "b.json"), "--mode", "any-title"],
                                     capture_output=True, text=True)
            self.assertNotEqual(unknown.returncode, 0)


if __name__ == "__main__":
    unittest.main()
