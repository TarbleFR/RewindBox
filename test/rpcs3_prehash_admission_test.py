#!/usr/bin/env python3
"""Execute the actual prehash worker and validation paths in the existing VM model.

Only speculative admission changes. The test checks deterministic byte avoidance
for RSX-write bypasses, mixed eligibility of one range, epoch ordinal alignment,
re-eligibility, the existing unmap/teardown races, and stale-result mutations.
Host work counts are not an iPhone frame-time or FPS measurement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

import rpcs3_runtime_log_followup as log_followup

ROOT = Path(__file__).resolve().parents[1]
CACHE = "rpcs3/Emu/RSX/Common/texture_cache.cpp"
HEADER = "rpcs3/ios/IOSTexturePrehash.h"
UTILS = "rpcs3/Emu/RSX/Common/texture_cache_utils.h"
HEADS = {
    "FAST_HASH": "u64 buffered_section::fast_hash_internal() const",
    "IS_LOCKED": "bool buffered_section::is_locked(bool actual_page_flags) const",
    "PROTECT": "void buffered_section::protect(utils::protection new_prot, bool force)",
    "SYNC": "bool buffered_section::sync() const",
    "DISCARD": "void buffered_section::discard()",
}


def braced(text, marker):
    start = text.index(marker)
    at = text.index("{", start)
    depth = 1
    end = at + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def harness(source, candidate, mutation=None):
    cache = (source / CACHE).read_text()
    header = (source / HEADER).read_text()
    code = (ROOT / "test/native/rpcs3_prehash581.inc").read_text()
    # Both snapshots have the existing 581 bypass field. The old model's
    # disabled-path comparison originally used the pre-581 section instead.
    code = code.replace("CELL581_SECTION(, @BEFORE_RESET_VALIDATION@)",
                        "CELL581_SECTION(mutable bool prehash_bypass = false;, @BEFORE_RESET_VALIDATION@)")
    reset = braced((source / UTILS).read_text(), "void reset_validation() const")
    for version in ("BEFORE", "AFTER"):
        code = code.replace("@" + version + "_RESET_VALIDATION@", reset)
        for name, marker in HEADS.items():
            block = braced(cache, marker)
            if mutation == "no_bypass" and name == "SYNC" and version == "AFTER":
                assert block.count("!prehash_bypass && ") == 1
                block = block.replace("!prehash_bypass && ", "")
            code = code.replace("@" + version + "_" + name + "@", block)
    worker = braced(cache, "namespace rpcs3::ios::texture_prehash\n{")
    if mutation == "ignore_admission":
        assert worker.count("if (!range.eligible)") == 1
        worker = worker.replace("if (!range.eligible)", "if (false && !range.eligible)")
    if mutation == "no_epoch_check":
        assert header.count(" || stored_epoch != epoch") == 1
        header = header.replace(" || stored_epoch != epoch",
                                " || (static_cast<void>(stored_epoch), static_cast<void>(epoch), false)")
    secret = braced(cache, "namespace\n{\n\tstruct ios_xxh3_seeded_secret")
    code = code.replace("@SECRET_AND_PREHASH@", secret + "\n" + worker)
    code = code.replace("@PREHASH_HEADER_INCLUDE@", header.replace("#pragma once", ""))
    assert "@AFTER_" not in code and "@BEFORE_" not in code
    code = code.replace("int main(int argc, char** argv)", "int existing_model_main(int argc, char** argv)")
    code = code.replace("disabledIdenticalTo579", "disabledPrehashNoWorker")
    code = code.replace("frame < 4000 &&", "frame < 40000 &&")
    tests = (ROOT / "test/native/rpcs3_prehash_admission.inc").read_text()
    return ("#ifdef NDEBUG\n#error Assertions must remain enabled\n#endif\n"
            "#define RPCS3_IOS 1\n#define ADMISSION_CANDIDATE " + str(int(candidate)) + "\n" + code + "\n\n" + tests)


def run(source, dependencies, compiler, sanitizer, candidate, work, mutation=None):
    name = ("candidate" if candidate else "baseline") + ("-" + mutation if mutation else "")
    code = harness(source, candidate, mutation)
    cpp, binary = work / (name + ".cpp"), work / name
    cpp.write_text(code)
    flags = ["-std=c++20", "-O2", "-UNDEBUG", "-g", "-Wall", "-Wextra", "-Werror", "-fno-exceptions", "-pthread",
             "-fno-omit-frame-pointer", "-I" + str(source / "rpcs3"), "-I" + str(source)]
    for dep in dependencies:
        flags += ["-I" + str(dep / "rpcs3"), "-I" + str(dep)]
    if sdk := os.environ.get("HOST_MACOS_SDK"):
        flags += ["-isysroot", sdk]
    if sanitizer:
        flags += ["-fsanitize=" + sanitizer]
    subprocess.run(compiler + flags + [str(cpp), "-o", str(binary)], check=True)
    suppressions = work / "guest-memory-tsan.supp"
    # These are only the same plain guest-byte accesses excluded by the 581
    # model. All admission metadata, vectors, slots and worker lifetime stay
    # instrumented. The emulator itself also permits concurrent guest accesses.
    suppressions.write_text("race:fill\nrace:XXH3_\nrace:XXH_\nrace:XXH64\nrace:range_hash\n")
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
               TSAN_OPTIONS="halt_on_error=1:suppressions=" + str(suppressions))
    result = subprocess.run([str(binary), "0"], capture_output=True, text=True, timeout=180, env=env)
    if mutation:
        expected = {"ignore_admission": "worker_bytes_used == expected_bytes",
                    "no_epoch_check": "!a.sync()", "no_bypass": "!a.sync()"}[mutation]
        assert result.returncode and expected in result.stderr, (mutation, result.returncode, result.stdout, result.stderr)
        return {"rejected": True, "assertion": expected, "compilerFlags": flags}
    if result.returncode:
        raise AssertionError((result.returncode, result.stdout, result.stderr))
    reports = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert len(reports) == 2 and all(r["passed"] for r in reports), result.stdout
    return {"admission": reports[0], "existingModel": reports[1],
            "harnessSHA256": hashlib.sha256(code.encode()).hexdigest(), "compilerFlags": flags}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--baseline", type=Path,
                        help="Optional Core592 tree; otherwise reconstruct the authenticated follow-up baseline when present.")
    parser.add_argument("--dependency-root", action="append", type=Path, default=[])
    parser.add_argument("--compiler", default=os.environ.get("CXX", "g++"))
    parser.add_argument("--sanitizer", default="")
    parser.add_argument("--mutations", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    deps = [p.resolve() for p in args.dependency_root] + [source]
    compiler = shlex.split(args.compiler)
    manifest = json.loads((ROOT / "build-utils/rpcs3/canonical-source.json").read_bytes())
    authenticated = log_followup.authenticate(source, manifest) if log_followup.KEY in manifest else None
    with tempfile.TemporaryDirectory(prefix="rpcs3-prehash-admission-") as temporary:
        work = Path(temporary)
        baseline = args.baseline.resolve() if args.baseline else None
        if baseline is None and authenticated:
            baseline = log_followup.reconstruct(source, work / "before", authenticated, extra_paths=[UTILS])
        if baseline is not None and authenticated:
            for relative in (CACHE, HEADER, UTILS):
                assert log_followup.normalized_sha(baseline / relative) == authenticated[2]["files_sha256"][relative], relative
        report = {"passed": True, "compiler": subprocess.check_output(compiler + ["--version"], text=True).splitlines()[0],
                  "sanitizer": args.sanitizer, "physicalDeviceTested": False, "gameplayMeasured": False}
        report["candidate"] = run(source, deps, compiler, args.sanitizer, True, work)
        if baseline is not None:
            report["baseline"] = run(baseline, deps, compiler, args.sanitizer, False, work)
            now, old = report["candidate"]["admission"], report["baseline"]["admission"]
            assert now["frames"] == old["frames"] and now["changedTexturesRejected"] == old["changedTexturesRejected"]
            assert old["workerBytes"] - now["workerBytes"] == now["frames"] * now["rewrittenBytesPerFrame"]
            report["speculativeBytesAvoided"] = old["workerBytes"] - now["workerBytes"]
        if args.mutations:
            report["mutations"] = {m: run(source, deps, compiler, "", True, work, m)
                                   for m in ("ignore_admission", "no_epoch_check", "no_bypass")}
        report["sourceSHA256"] = {p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in (CACHE, HEADER)}
        if authenticated:
            report["followupFixtureSHA256"] = authenticated[1]["fixture_sha256"]
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
