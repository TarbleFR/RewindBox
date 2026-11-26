#!/usr/bin/env python3
"""Time paired synthetic S2Arm workloads on a Linux host and record exact inputs."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
from statistics import median
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
BENCH = ROOT / "c_benches" / "bench_core.c"
HISTORY = ROOT / "perf_history.json"
MODULES = {
    "M01": "production texture layout and CPU deswizzle; round-trip and byte reference",
    "M02": "production hash table; synthetic keys and lookup digest",
    "M03": "pool/vertex binding model with optional production rule header",
    "M04": "argument block model with production rule header; compares all slots to full rebuild",
    "M05": "pass-cut and snapshot decision model; calculated attachment bytes, no GPU",
    "M06": "production UBO reconstruction; complete byte and coverage digest in short workload",
    "M07": "production dirty range lookup; single-thread read path, registered range without writes",
    "M08": "production pipeline and cache decisions with fixed inputs; no compilation or disk I/O",
    "M09": "production texture candidate predicates; does not upload textures",
    "M10": "production interpolation/pacing decision rules; no MetalFX or presented frames",
}
# Set-associative cache sensitivity on the host binary. These configurations
# cannot convert x86 instructions or simulated misses into Apple device time.
CACHES = {
    "large": ["--I1=196608,6,128", "--D1=131072,8,128", "--LL=16777216,16,128"],
    "small": ["--I1=131072,4,128", "--D1=65536,4,128", "--LL=4194304,16,128"],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_bench(tree, directory):
    tree = tree.resolve()
    nvn = tree / "graphics/nvn/gfx/nvn"
    tex = tree / "graphics/nvn/gfx/tex"
    include = [nvn, nvn / "include", tex, tree / "runtime/include"]
    sources = [BENCH, tex / "nvn_deswizzle.c", nvn / "nvn_tex.c", nvn / "nvn_dirty.c"]
    flags = ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-pie"]
    if (nvn / "rb_pass_cut_rule.h").is_file():
        flags.append("-DHAS_RB_PASS_CUT_RULE")
    if (nvn / "rb_draw_fast_rule.h").is_file():
        flags.append("-DHAS_RB_DRAW_FAST_RULE")
    if "RB_ARGS_HAS_SLOT_GENS" in (nvn / "rb_args_ubo.h").read_text():
        flags.append("-DRB_ARGS_HAS_SLOT_GENS")
    cc = ["clang", *flags, *(f"-I{p}" for p in include)]
    deps = {}
    for unit in sources:
        built = subprocess.check_output([*cc, "-MM", "-MT", "unit", unit], text=True)
        for value in shlex.split(built.replace("\\\n", " ").split(":", 1)[1]):
            path = Path(value).resolve()
            key = "harness/bench_core.c" if path == BENCH else path.relative_to(tree).as_posix()
            deps[key] = digest(path)
    meta = {"inputs_sha256": dict(sorted(deps.items())), "compile_flags": flags,
            "include_paths": [p.relative_to(tree).as_posix() for p in include],
            "link_flags": ["-no-pie", "-lm", "-lpthread"]}
    meta["source_set_sha256"] = hashlib.sha256(json.dumps(deps, sort_keys=True).encode()).hexdigest()
    normal, sanitized = directory / "bench", directory / "bench-sanitized"
    san_flags = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
    for target, extra in [(normal, []), (sanitized, san_flags)]:
        subprocess.run([*cc, *extra, *sources, *meta["link_flags"], "-o", target], check=True)
    meta.update(sanitizer_flags=san_flags, binary_sha256=digest(normal), sanitized_binary_sha256=digest(sanitized))
    return normal, sanitized, meta


def run(binary, selected, env, only=None, verify=False):
    cmd = [binary]
    if verify:
        cmd.append("--verify-only")
    if only:
        cmd.extend(["--only", only])
    lines = subprocess.check_output(cmd, env=env, text=True).splitlines()
    rows = {}
    for line in lines:
        row = json.loads(line)
        module = row["module"].split("_", 1)[0]
        if module in rows or not re.fullmatch("[0-9a-f]{16}", row["checksum"]):
            raise ValueError(f"Invalid or duplicate checksum row for {module}")
        if not math.isfinite(row["time_ms"]) or row["time_ms"] < 0:
            raise ValueError(f"Invalid duration for {module}")
        rows[module] = row
    if set(selected) != rows.keys():
        raise ValueError(f"Requested {selected}, received {list(rows)}")
    return rows


def simulate(binary, short_id, cache, destination, env):
    subprocess.run(["valgrind", "--tool=cachegrind", "--cache-sim=yes", "--quiet",
                    f"--cachegrind-out-file={destination}", *CACHES[cache],
                    binary, "--verify-only", "--only", short_id],
                   env=env, stdout=subprocess.DEVNULL, check=True)
    text = destination.read_text()
    names = re.search(r"^events:\s+(.+)$", text, re.M).group(1).split()
    values = re.search(r"^summary:\s+(.+)$", text, re.M).group(1).split()
    return dict(zip(names, map(int, values), strict=True))


def persist(path, report, append=False):
    # Lock the parent directory across history read/modify/replace. A lock on
    # the replaced inode would let a simultaneous recorder lose a run.
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        if append:
            history = json.loads(path.read_text()) if path.exists() else {"schema_version": "2.0", "runs": []}
            history["runs"].append(report)
            data = history
        else:
            data = report
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            temp = Path(stream.name)
        temp.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o644)
        temp.replace(path)
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--best", type=Path, help="additional best intermediate revision with the same module interfaces")
    parser.add_argument("--runs", type=int, default=6, help="paired repetitions, alternating AB/BA")
    parser.add_argument("--cpu", type=int, help="allowed Linux CPU index, default first available")
    parser.add_argument("--only", choices=MODULES)
    parser.add_argument("--cachegrind", choices=MODULES, nargs="*", default=["M01","M02","M03","M04"])
    parser.add_argument("--label", default="synthetic")
    parser.add_argument("--record", action="store_true", help="append complete report to perf_history.json")
    parser.add_argument("--output", type=Path, help="write standalone JSON")
    args = parser.parse_args()
    if args.best and not args.candidate:
        parser.error("--best requires --candidate for the three-way comparison")
    if args.runs < 5:
        parser.error("--runs must be at least 5")
    if not hasattr(os, "sched_getaffinity"):
        parser.error("Linux CPU affinity is required for this runner")
    allowed = sorted(os.sched_getaffinity(0))
    cpu = allowed[0] if args.cpu is None else args.cpu
    if cpu not in allowed:
        parser.error(f"--cpu must be one of {allowed}")
    os.sched_setaffinity(0, {cpu})
    cg_modules = [m for m in args.cachegrind if not args.only or m == args.only]
    if cg_modules and not shutil.which("valgrind"):
        parser.error("Cachegrind requested but valgrind is unavailable")
    env = {k:v for k,v in os.environ.items() if not k.startswith(("DM_", "S2A_"))}
    env.update(ASAN_OPTIONS="detect_leaks=1:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
    selected = [args.only] if args.only else list(MODULES)
    platform_cpu = re.search(r"^model name\s*:\s*(.+)$", Path("/proc/cpuinfo").read_text(), re.M)
    report = {
        "schema_version": "2.0", "timestamp": datetime.now(timezone.utc).isoformat(), "label": args.label,
        "host": {"os": platform.system(), "arch": platform.machine(), "cpu_model": platform_cpu[1] if platform_cpu else None,
                 "cpu_affinity": sorted(os.sched_getaffinity(0)), "kernel": platform.release(),
                 "clang": subprocess.check_output(["clang","--version"],text=True).splitlines()[0]},
        "harness_sha256": {"bench_core.c":digest(BENCH), "bench_suite.py":digest(Path(__file__))},
        "runs_per_variant": args.runs, "sanitizer_workload": "short (--verify-only), engine environment overrides removed",
        "timing": "CLOCK_MONOTONIC, milliseconds, one CPU, one warmup per binary, rotating through all variant orders",
        "cachegrind": {"version": subprocess.check_output(["valgrind","--version"],text=True).strip() if cg_modules else None,
                      "configurations": CACHES if cg_modules else {}, "scope": "one complete short host process per module and configuration"},
        "physical_device_status": "not measured", "apple_performance_projection": "not calibrated; no estimate",
        "order": [], "variants": {}, "modules": {},
    }
    variants = {"baseline": args.baseline}
    if args.best:
        variants["best"] = args.best
    if args.candidate:
        variants["candidate"] = args.candidate
    with tempfile.TemporaryDirectory(prefix="s2arm-bench-") as tmp:
        binaries, verified = {}, {}
        for tag, tree in variants.items():
            directory = Path(tmp)/tag
            directory.mkdir()
            binaries[tag], san, report["variants"][tag] = compile_bench(tree, directory)
            verified[tag] = run(san, selected, env, args.only, verify=True)
        warm = {tag:run(binaries[tag], selected, env, args.only) for tag in variants}
        for module in selected:
            report["modules"][module] = {"scope": MODULES[module], "variants": {}, "cachegrind": {}}
            for tag in variants:
                row = warm[tag][module]
                report["modules"][module]["variants"][tag] = {
                    "sanitizer_short_workload": "passed",
                    "short_checksum": verified[tag][module]["checksum"],
                    "timed_checksum": row["checksum"], "raw_ms": [],
                    "workload_counters": {k:v for k,v in row.items() if k not in {"module","time_ms","checksum","throughput_mib_per_s"}},
                }
        orders = list(itertools.permutations(variants))
        for pair in range(args.runs):
            order = orders[pair % len(orders)]
            report["order"].append(order)
            for tag in order:
                rows = run(binaries[tag], selected, env, args.only)
                for module,row in rows.items():
                    record = report["modules"][module]["variants"][tag]
                    if row["checksum"] != record["timed_checksum"]:
                        raise RuntimeError(f"{module}: nondeterministic {tag} checksum in pair {pair+1}")
                    record["raw_ms"].append(row["time_ms"])
        for module in selected:
            entry = report["modules"][module]
            for tag,data in entry["variants"].items():
                data["median_ms"] = median(data["raw_ms"])
            if args.candidate:
                cand = entry["variants"]["candidate"]
                comparisons = {}
                for reference in variants:
                    if reference == "candidate":
                        continue
                    other = entry["variants"][reference]
                    same = all(other[k] == cand[k] for k in ("short_checksum", "timed_checksum"))
                    if module != "M05" and not same:
                        raise RuntimeError(f"{module}: {reference}/candidate checksum differs")
                    comparison = {"checksums_match": same}
                    if all(t > 0 for t in other["raw_ms"]):
                        changes = [round(100 * (c / b - 1), 4) for b, c in zip(other["raw_ms"], cand["raw_ms"])]
                        comparison.update(paired_percent_change=changes, paired_median_percent_change=median(changes))
                    comparisons[reference] = comparison
                entry["comparisons"] = comparisons
                entry.update(comparisons["baseline"])
                entry["parity"] = ("policy counters only; no rendering comparison" if module == "M05"
                                   else "matching short and timed workload checksums")
            else:
                entry["parity"] = "not compared; baseline only"
            print(module, entry["parity"], {k:v["median_ms"] for k,v in entry["variants"].items()}, flush=True)
            if module in cg_modules:
                for config in CACHES:
                    entry["cachegrind"][config] = {
                        tag:simulate(binary,module,config,Path(tmp)/f"{tag}-{module}-{config}.cg",env)
                        for tag,binary in binaries.items()
                    }
    if args.output:
        persist(args.output, report)
    if args.record:
        persist(HISTORY, report, append=True)


if __name__ == "__main__":
    main()
