#!/usr/bin/env python3
"""Measure only the changed validation path, with paired alternating processes.

The correctness program and its receipts are unchanged. A separate program
parks the real worker in a host-only atomic wait before it can hash anything,
preallocates the existing sequence buffer and disables all hash observers.
Both implementations keep the real record/lookup/hash/publication code. No
old tests run. Timings are CPU host microbenchmarks, not gameplay or FPS.
"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import shlex
import statistics
import subprocess
import tempfile

import rpcs3_texture_hash_reuse_test as correctness

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "test/native/rpcs3_texture_hash_reuse_bench.inc"
SIZES = [32768, 65536, 262144, 1048576, 3686400]
PATTERNS = ["identical", "distinct", "scoped_bypass"]
SOURCE, SUPPORT = correctness.SOURCE, correctness.SUPPORT


def harness(tree, candidate):
    code = correctness.harness(tree, candidate).split("\nnamespace\n{\nusing section = rsx::after::buffered_section;")[0]
    original = correctness.braced(code, "u64 observed_range_hash(")
    parked = """u64 observed_range_hash(const void* src, u32 length) noexcept
{
    const auto paused = hash_reuse_probe::paused_start.load(std::memory_order_relaxed);
    if (paused && src == vm::g_sudo_addr + paused)
    {
        hash_reuse_probe::entered.store(true, std::memory_order_release);
        while (!hash_reuse_probe::resume.load(std::memory_order_acquire))
            hash_reuse_probe::resume.wait(false, std::memory_order_relaxed);
    }
    return range_hash(src, length);
}"""
    assert original in code
    return code.replace(original, parked) + ADAPTER.read_text()


def expected(source, baseline):
    evidence = correctness.expected(source, baseline)
    evidence["correctnessHarnessesSHA256"] = evidence.pop("harnessesSHA256")
    evidence["benchmarkHarnessesSHA256"] = {"baseline": correctness.digest(harness(baseline, False)),
                                           "candidate": correctness.digest(harness(source, True))}
    evidence["benchmarkAdapterSHA256"] = correctness.sha(ADAPTER)
    return evidence


def verify_counts(report):
    assert report["passed"] is True and report["measurementOnly"] is True
    assert report["workerParkedWithoutSpin"] is True
    assert report["observationHooksDisabled"] is True
    assert report["recordBufferPreallocated"] is True
    assert report["series"] == 7
    assert len(report["comparisons"]) == len(SIZES) * len(PATTERNS)
    for comparison, (size, pattern) in zip(report["comparisons"], [(s, p) for s in SIZES for p in PATTERNS]):
        assert comparison["bytes"] == size and comparison["pattern"] == pattern and comparison["sections"] == 8
        for label in ("baseline", "candidate"):
            values = comparison[label]["seriesNsPerValidation"]
            assert len(values) == 7 and all(math.isfinite(v) and v > 0 for v in values)
            assert comparison[label]["medianNsPerValidation"] == statistics.median(values)
        assert comparison["order"] == [["baseline", "candidate"] if i % 2 == 0 else ["candidate", "baseline"] for i in range(7)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--compiler", default=os.environ.get("CXX", "g++"))
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    compiler = shlex.split(args.compiler)
    report = expected(source, baseline)
    flags = ["-std=c++20", "-O2", "-UNDEBUG", "-g", "-Wall", "-Wextra", "-Werror",
             "-fno-exceptions", "-fno-omit-frame-pointer", "-pthread", "-DRPCS3_IOS=1"]
    if sdk := os.environ.get("HOST_MACOS_SDK"):
        flags += ["-isysroot", sdk]
    report.update({"passed": True, "measurementOnly": True, "series": 7,
                   "compiler": subprocess.check_output(compiler + ["--version"], text=True).splitlines()[0],
                   "compilerFlags": flags, "host": platform.platform(), "machine": platform.machine(),
                   "workerParkedWithoutSpin": True, "observationHooksDisabled": True,
                   "recordBufferPreallocated": True, "physicalDeviceTested": False,
                   "gameplayMeasured": False, "fullCoreBuilt": False, "hybridHashExecuted": False,
                   "epochNotificationExcludedFromTiming": True,
                   "timingScope": "eight real section validations per epoch; worker parked in test hook; no epoch notification scheduling",
                   "comparisons": []})
    with tempfile.TemporaryDirectory(prefix="rpcs3-hash-reuse-benchmark-") as tmp:
        work = Path(tmp)
        binaries = {}
        for label, tree, candidate in (("baseline", baseline, False), ("candidate", source, True)):
            cpp, binary = work / (label + ".cpp"), work / label
            cpp.write_text(harness(tree, candidate))
            subprocess.run(compiler + flags + ["-I" + str(tree / "rpcs3"), "-I" + str(tree), str(cpp), "-o", str(binary)], check=True)
            binaries[label] = binary
        affinity = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else None
        cpu = args.cpu if args.cpu is not None else max(affinity) if affinity else None
        if affinity:
            assert cpu in affinity
            os.sched_setaffinity(0, {cpu})
        report["affinityCpu"] = cpu
        report["affinityApplied"] = affinity is not None
        report["exclusiveHostCpuGuaranteed"] = False
        try:
            for size in SIZES:
                for kind, pattern in enumerate(PATTERNS):
                    comparison = {"bytes": size, "pattern": pattern, "sections": 8,
                                  "baseline": {"seriesNsPerValidation": []},
                                  "candidate": {"seriesNsPerValidation": []}, "order": []}
                    for series in range(7):
                        order = ["baseline", "candidate"] if series % 2 == 0 else ["candidate", "baseline"]
                        comparison["order"].append(order)
                        for label in order:
                            proc = subprocess.run([str(binaries[label]), str(size), str(kind)], capture_output=True, text=True, timeout=30, check=True)
                            value = json.loads(proc.stdout)
                            assert value["passed"] and value["workerHashesDuringTiming"] == 0
                            comparison[label]["seriesNsPerValidation"].append(value["nsPerValidation"])
                            comparison["iterationsPerSeries"] = value["iterations"]
                    for label in ("baseline", "candidate"):
                        values = comparison[label]["seriesNsPerValidation"]
                        comparison[label]["medianNsPerValidation"] = statistics.median(values)
                        comparison[label]["minNsPerValidation"] = min(values)
                        comparison[label]["maxNsPerValidation"] = max(values)
                    old = comparison["baseline"]["medianNsPerValidation"]
                    now = comparison["candidate"]["medianNsPerValidation"]
                    comparison["medianChangePercent"] = (now / old - 1) * 100
                    report["comparisons"].append(comparison)
        finally:
            if affinity:
                os.sched_setaffinity(0, affinity)
    verify_counts(report)
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
