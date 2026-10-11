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


def fixture(source="a" * 40, pid=123):
    info = {"sourceCommit": source, "pid": pid, "sessionSequence": 1, "bootTimestamp": 100,
            "title": "BCES00510", "workloadId": "save-fixture-route-10s", "deviceId": "fixture-device",
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
    diagnostics = [diag(100, "game_boot_begin", "BCES00510")]
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
            diag(timestamp, "performance_sample", f"title=BCES00510 valid=0x1 fps={index * 20} sample_epoch=1"),
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


if __name__ == "__main__":
    unittest.main()
