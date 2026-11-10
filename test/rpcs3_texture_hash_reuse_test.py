#!/usr/bin/env python3
"""Exercise reuse of completed synchronous hashes in the existing prehash table.

Production slot publication/lookup, worker, range hash and section validation
are extracted from each supplied snapshot. Only the old VM/section adapters
are reused; none of the old test cases runs. Hash observations and a worker
pause exist in this host harness only. No device, GPU or FPS claim is made.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile

from rpcs3_cell559_test import without_ios_blocks
from rpcs3_prehash_admission_test import braced, HEADS

ROOT = Path(__file__).resolve().parents[1]
CACHE = "rpcs3/Emu/RSX/Common/texture_cache.cpp"
HEADER = "rpcs3/ios/IOSTexturePrehash.h"
UTILS = "rpcs3/Emu/RSX/Common/texture_cache_utils.h"
SOURCE = [CACHE, HEADER]
SUPPORT = [UTILS, "rpcs3/ios/IOSTextureValidationProfile.h", "rpcs3/ios/IOSThreadQoS.h",
           "rpcs3/Emu/RSX/Common/texture_cache_protection_policy.h", "Utilities/xxhash3.h"]
ADAPTER = ROOT / "test/native/rpcs3_texture_hash_reuse.inc"
RETAINED = ROOT / "test/native/rpcs3_prehash581.inc"


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def source_guards(source, baseline):
    for path in SUPPORT:
        assert sha(source / path) == sha(baseline / path), path
    current, old = (source / CACHE).read_text(), (baseline / CACHE).read_text()
    assert without_ios_blocks(current) == without_ios_blocks(old)
    signature = "bool buffered_section::sync() const"
    assert current.replace(braced(current, signature), braced(old, signature)) == old
    # In particular the worker still consults lookup before hash_guest_range.
    worker = braced(current, "void worker_main()")
    assert worker.index("if (lookup(") < worker.index("if (!hash_guest_range(")
    publish = braced((source / HEADER).read_text(), "inline void publish(")
    assert publish.count("compare_exchange_strong") == 1
    assert "while" not in publish and "for (" not in publish
    current_header, old_header = (source / HEADER).read_text(), (baseline / HEADER).read_text()
    normalized_header = current_header.replace(publish, braced(old_header, "inline void publish("))
    def code_only(text):
        return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", text)).strip()
    assert code_only(normalized_header) == code_only(old_header)


def harness(tree, candidate, mutation=None):
    cache, header = (tree / CACHE).read_text(), (tree / HEADER).read_text()
    code = RETAINED.read_text().split("namespace\n{\n\tusing section = rsx::after::buffered_section;")[0]
    code = code.replace("CELL581_SECTION(, @BEFORE_RESET_VALIDATION@)",
                        "CELL581_SECTION(mutable bool prehash_bypass = false;, @BEFORE_RESET_VALIDATION@)")
    reset = braced((tree / UTILS).read_text(), "void reset_validation() const")
    for version in ("BEFORE", "AFTER"):
        code = code.replace("@" + version + "_RESET_VALIDATION@", reset)
        for name, marker in HEADS.items():
            block = braced(cache, marker)
            if mutation == "no_bypass" and name == "SYNC":
                assert block.count("!prehash_bypass && ") == 1
                block = block.replace("!prehash_bypass && ", "")
            if mutation == "no_reuse" and name == "SYNC":
                assert block.count("share_hash = !prehash_bypass;") == 1
                block = block.replace("share_hash = !prehash_bypass;", "share_hash = false;")
            code = code.replace("@" + version + "_" + name + "@", block)
    if mutation == "no_epoch":
        header = header.replace(" || stored_epoch != epoch",
                                " || (static_cast<void>(stored_epoch), static_cast<void>(epoch), false)")
    if mutation == "single_writer":
        start = header.index("\tstd::uint64_t seq = slot.seq.load", header.index("inline void publish("))
        end = header.index("\t// Release stores:", start)
        header = header[:start] + ("\tconst std::uint64_t seq = slot.seq.load(std::memory_order_relaxed);\n"
                                  "\tslot.seq.store(seq + 1, std::memory_order_relaxed);\n") + header[end:]
    worker = braced(cache, "namespace rpcs3::ios::texture_prehash\n{")
    real_hash = braced(worker, "u64 range_hash(")
    secret = braced(cache, "namespace\n{\n\tstruct ios_xxh3_seeded_secret")
    adapter = ADAPTER.read_text()
    probe, cases = adapter.split("// @CASES@")
    worker = worker.replace(real_hash, "")
    # The production hash stays verbatim. A macro redirects only its call sites
    # through a host observer; it is off during timing and cannot change bytes.
    block = (secret + "\nnamespace rpcs3::ios::texture_prehash {\n" + real_hash + "\n}\n" + probe +
             "\n#define range_hash observed_range_hash\n" + worker)
    code = code.replace("@SECRET_AND_PREHASH@", block)
    code = code.replace("@PREHASH_HEADER_INCLUDE@", header.replace("#pragma once", ""))
    # Compile the actual reset body too, preserving range invalidation on reuse.
    code = code.replace("\tu64 fast_hash_internal() const; \\\n",
                        "\tvoid reset(const address_range32&); \\\n"
                        "\tvoid init_lockable_range(const address_range32& r) { locked_range = r.to_page_range(); } \\\n"
                        "\tu64 fast_hash_internal() const; \\\n")
    code = code.replace("\t\tbool valid() const { return start <= end; }",
                        "\t\taddress_range32 to_page_range() const { return {start & ~4095u, end | 4095u}; }\n"
                        "\t\tbool valid() const { return start <= end; }")
    assert "@BEFORE_" not in code and "@AFTER_" not in code
    reset_body = braced(cache, "void buffered_section::reset(")
    return ("#ifdef NDEBUG\n#error Assertions must remain enabled\n#endif\n"
            "#define RPCS3_IOS 1\n#define HASH_REUSE_CANDIDATE " + str(int(candidate)) + "\n" + code +
            "\n#undef range_hash\nnamespace rsx::after {\n" + reset_body + "\n}\n" + cases)


def expected(source, baseline):
    source_guards(source, baseline)
    return {
        "sourceSHA256": {p: sha(source / p) for p in SOURCE + SUPPORT},
        "baselineSHA256": {p: sha(baseline / p) for p in SOURCE + SUPPORT},
        "harnessesSHA256": {"baseline": digest(harness(baseline, False)),
                            "candidate": digest(harness(source, True))},
        "adapterSHA256": sha(ADAPTER), "retainedAdapterSHA256": sha(RETAINED),
        "nonIosSourceIdentical": True, "workerLookupBeforeHashPreserved": True,
        "slotStorageUnchanged": True, "publicationTryOnce": True,
    }


def verify_counts(result):
    assert result["passed"] is True
    for name, candidate in (("baseline", False), ("candidate", True)):
        r = result[name]
        assert r["candidate"] is candidate and r["passed"] is True
        assert r["repeatedQueries"] == 96
        assert r["repeatedHashes"] == (12 if candidate else 96)
        assert r["repeatedBytes"] == r["repeatedHashes"] * 65536
        assert r["distinctQueries"] == r["distinctHashes"] == 32
        assert r["overlapWriteHashes"] == 3 and r["overlapChangedRejected"] == 3
        assert r["confirmedRangeReuse"] and r["cacheReset"] and r["oldWorkerAfterScopedWrite"]
        assert r["epochDuringHash"] and r["oldPublisherAfterNewEpoch"] and r["disabledControls"]
        assert r["collisionChecks"] == 64
        assert r["heldSlotNoWait"] is candidate
        assert r["stressWrites"] == (500000 if candidate else 250000)
        assert r["stressReads"] == 500000
        assert 0 < r["stressAcceptedMatches"] <= r["stressReads"]
        assert r["multiWriterTested"] is candidate
        assert r["workerPredictionHashes"] == (2 if candidate else 3)
        assert r["workerPredictionBytes"] == r["workerPredictionHashes"] * 65536
        assert r["workerSynchronousHashes"] == 1
        assert r["guestMemoryMappingModeled"] and r["gpuExecuted"] is False


def run(tree, candidate, compiler, sanitizer, benchmark, work, mutation=None):
    name = ("candidate" if candidate else "baseline") + ("-" + mutation if mutation else "")
    cpp, binary = work / (name + ".cpp"), work / name
    cpp.write_text(harness(tree, candidate, mutation))
    flags = ["-std=c++20", "-O2", "-UNDEBUG", "-g", "-Wall", "-Wextra", "-Werror",
             "-fno-exceptions", "-fno-omit-frame-pointer", "-pthread", "-DRPCS3_IOS=1",
             "-I" + str(tree / "rpcs3"), "-I" + str(tree)]
    if sdk := os.environ.get("HOST_MACOS_SDK"):
        flags += ["-isysroot", sdk]
    if sanitizer:
        flags += ["-fsanitize=" + sanitizer]
    subprocess.run(compiler + flags + [str(cpp), "-o", str(binary)], check=True)
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
               TSAN_OPTIONS="halt_on_error=1")
    proc = subprocess.run([str(binary)] + (["--benchmark"] if benchmark else []),
                          capture_output=True, text=True, timeout=120, env=env)
    if mutation:
        expected_assertion = {"no_reuse": "repeated_hashes ==", "no_bypass": "!s.sync()",
                              "no_epoch": "out.repeated_hashes ==", "single_writer": "slot.seq.load() == seq"}[mutation]
        assert proc.returncode and expected_assertion in proc.stderr, (mutation, proc.returncode, proc.stderr)
        return {"rejected": True, "assertion": expected_assertion}
    if proc.returncode:
        raise AssertionError((name, proc.returncode, proc.stdout, proc.stderr))
    report = json.loads(proc.stdout)
    report["compilerFlags"] = flags
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--compiler", default=os.environ.get("CXX", "g++"))
    parser.add_argument("--sanitizer", default="")
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--mutations", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    assert not (args.sanitizer and (args.benchmark or args.mutations)), "time/mutate the plain mode only"
    source, baseline = args.source.resolve(), args.baseline.resolve()
    compiler = shlex.split(args.compiler)
    report = expected(source, baseline)
    report.update({"passed": True, "compiler": subprocess.check_output(compiler + ["--version"], text=True).splitlines()[0],
                   "host": platform.platform(), "machine": platform.machine(), "sanitizer": args.sanitizer,
                   "physicalDeviceTested": False, "gameplayMeasured": False, "fullCoreBuilt": False,
                   "hashCountersSource": "harness observer; disabled during timing",
                   "existingPrehashHitsCanIncludeSynchronousProducers": True,
                   "hybridHashExecuted": False, "hashImplementation": "production XXH3 with cached seeded secret; host SIMD",
                   "tsanSuppressions": []})
    with tempfile.TemporaryDirectory(prefix="rpcs3-hash-reuse-") as tmp:
        work = Path(tmp)
        report["baseline"] = run(baseline, False, compiler, args.sanitizer, args.benchmark, work)
        report["candidate"] = run(source, True, compiler, args.sanitizer, args.benchmark, work)
        verify_counts(report)
        if args.mutations:
            report["mutations"] = {m: run(source, True, compiler, "", False, work, m)
                                   for m in ("no_reuse", "no_bypass", "no_epoch", "single_writer")}
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
