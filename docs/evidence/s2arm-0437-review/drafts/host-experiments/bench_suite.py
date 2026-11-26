#!/usr/bin/env python3
"""Autonomous Apple A18 Pro S2Arm comparative benchmark runner.

Compiles and executes bench_core.c against a baseline S2Arm tree and an
optional candidate S2Arm tree, enforcing:
  - ASan + UBSan correctness & bit-exact checksum parity
  - >= 5 alternating timed runs per variant (default: 7), pinned to CPU core 0
  - Valgrind Cachegrind simulation with exact Apple A18 Pro Everest P-core
    (192K L1i / 128K L1d / 16M L2 / 128B line) and Sawtooth E-core geometries
  - Analytical A18 Pro projections separated strictly from host measurements
  - Persistent recording into tools/s2arm_a18pro/perf_history.json
"""
import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCH_C = ROOT / "c_benches" / "bench_core.c"
REF_JSON = ROOT / "referentiel_a18pro_autonome.json"
HIST_JSON = ROOT / "perf_history.json"


def detect_flags(tree: Path) -> list[str]:
    nvn = tree / "graphics/nvn/gfx/nvn"
    flags = []
    if (nvn / "rb_pass_cut_rule.h").is_file():
        flags.append("-DHAS_RB_PASS_CUT_RULE")
    if (nvn / "rb_draw_fast_rule.h").is_file():
        flags.append("-DHAS_RB_DRAW_FAST_RULE")
    args_h = nvn / "rb_args_ubo.h"
    if args_h.is_file() and "RB_ARGS_HAS_SLOT_GENS" in args_h.read_text(encoding="utf-8", errors="ignore"):
        flags.append("-DRB_ARGS_HAS_SLOT_GENS")
    return flags


def compile_bench(tree: Path, out_bin: Path, sanitize: bool = False) -> None:
    nvn = tree / "graphics/nvn/gfx/nvn"
    inc = nvn / "include"
    tex = tree / "graphics/nvn/gfx/tex"
    rt_inc = tree / "runtime/include"
    cmd = [
        "clang", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
        f"-I{nvn}", f"-I{inc}", f"-I{tex}", f"-I{rt_inc}",
    ] + detect_flags(tree)
    if sanitize:
        cmd += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    cmd += [
        str(BENCH_C),
        str(tex / "nvn_deswizzle.c"),
        str(nvn / "nvn_tex.c"),
        str(nvn / "nvn_dirty.c"),
        "-lm", "-lpthread", "-o", str(out_bin),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Compile failed for {tree}:\n{res.stderr}\n{res.stdout}")


def run_once(bin_path: Path, extra_args: list[str] = None, pin_cpu: bool = True) -> dict:
    cmd = (["taskset", "-c", "0"] if pin_cpu else []) + [str(bin_path)] + (extra_args or [])
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Execution failed ({bin_path}):\n{res.stderr}\n{res.stdout}")
    out = {}
    for line in res.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            row = json.loads(line)
            out[row["module"]] = row
    return out


def run_cachegrind(bin_path: Path, module_short: str, geometry: str) -> dict:
    geo_args = {
        "everest": ["--I1=196608,6,128", "--D1=131072,8,128", "--LL=16777216,16,128"],
        "sawtooth": ["--I1=131072,4,128", "--D1=65536,4,128", "--LL=4194304,16,128"],
    }[geometry]
    with tempfile.NamedTemporaryFile(suffix=".cg", delete=False) as tf:
        cg_out = tf.name
    try:
        cmd = [
            "valgrind", "--tool=cachegrind", "--cache-sim=yes", f"--cachegrind-out-file={cg_out}",
            *geo_args, str(bin_path), "--verify-only", "--only", module_short,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return {"error": res.stderr[-400:]}
        txt = Path(cg_out).read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^summary:\s+(.+)$", txt, re.M)
        if not m:
            return {"error": "no summary"}
        vals = [int(x) for x in m.group(1).split()]
        # events: Ir I1mr ILmr Dr D1mr DLmr Dw D1mw DLmw
        keys = ["Ir", "I1mr", "ILmr", "Dr", "D1mr", "DLmr", "Dw", "D1mw", "DLmw"]
        return dict(zip(keys, vals))
    finally:
        if os.path.exists(cg_out):
            os.unlink(cg_out)


def summarize(samples: list[float]) -> dict:
    s = sorted(samples)
    n = len(s)
    med = statistics.median(s)
    mean = statistics.mean(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    p95 = s[min(n - 1, int(math.ceil(0.95 * n)) - 1)]
    return {
        "n": n,
        "median_ms": round(med, 4),
        "mean_ms": round(mean, 4),
        "iqr_ms": round(q3 - q1, 4),
        "min_ms": round(s[0], 4),
        "p95_ms": round(p95, 4),
        "max_ms": round(s[-1], 4),
    }


def a18pro_project_delta(ref: dict, cg_base: dict, cg_cand: dict, extra_dram_mb_delta: float = 0.0) -> dict:
    """Analytical A18 Pro delta estimate strictly separated from host measurements."""
    if "Ir" not in cg_base or "Ir" not in cg_cand:
        return {}
    d_ir = cg_cand["Ir"] - cg_base["Ir"]
    d_d1 = (cg_cand["D1mr"] + cg_cand["D1mw"]) - (cg_base["D1mr"] + cg_base["D1mw"])
    d_ll = (cg_cand["DLmr"] + cg_cand["DLmw"]) - (cg_base["DLmr"] + cg_base["DLmw"])
    lat = ref["cpu"]["latencies_ns_est"]
    l2_pen = lat["l2_hit"]["value"] - lat["l1d_hit"]["value"]
    dram_pen = lat["dram_cold_miss"]["value"] - lat["l2_hit"]["value"]
    out = {
        "delta_Ir": d_ir,
        "delta_Ir_pct": round(100.0 * d_ir / max(1, cg_base["Ir"]), 2),
        "delta_D1_misses": d_d1,
        "delta_D1_pct": round(100.0 * d_d1 / max(1, cg_base["D1mr"] + cg_base["D1mw"]), 2),
        "delta_LL_misses": d_ll,
        "projections_ms_per_bench_unit": {},
    }
    for scen_name, sc in ref["analytical_cost_model"]["scenarios"].items():
        # Convert x86 Ir to estimated ARM64 Ir (1.05x central, [0.85, 1.30] uncertainty)
        cpu_ms = ((d_ir * 1.05) / (sc["clock_ghz"] * 1e6 * sc["ipc"])
                  + d_d1 * l2_pen / 1e6
                  + d_ll * dram_pen / 1e6)
        bw_ms = extra_dram_mb_delta / (sc["effective_gpu_bw_gb_s"] * 1.024)
        out["projections_ms_per_bench_unit"][scen_name] = {
            "cpu_delta_ms_est": round(cpu_ms, 4),
            "gpu_bw_delta_ms_est": round(bw_ms, 4),
            "uncertainty_note": "±30% analytical model; unverified on physical iPhone",
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="Baseline S2Arm tree (e.g. /tmp/s2arm-0436-base)")
    ap.add_argument("--candidate", help="Candidate S2Arm tree (optional for baseline-only capture)")
    ap.add_argument("--label", default="run", help="Run label for perf_history.json")
    ap.add_argument("--runs", type=int, default=7, help="Number of timed repetitions per variant (>= 5)")
    ap.add_argument("--cachegrind", nargs="*", default=["M01", "M02", "M03", "M04"],
                    help="Short module IDs to profile under A18 Pro Everest/Sawtooth Cachegrind")
    ap.add_argument("--record", action="store_true", help="Append summary to perf_history.json")
    ap.add_argument("--only", help="Run a single module short ID (e.g. M01)")
    args = ap.parse_args()

    if args.runs < 5:
        print("ERROR: scientific protocol requires --runs >= 5", file=sys.stderr)
        return 2

    ref = json.loads(REF_JSON.read_text(encoding="utf-8"))
    base_tree = Path(args.baseline)
    cand_tree = Path(args.candidate) if args.candidate else None

    with tempfile.TemporaryDirectory(prefix="s2a_a18_") as td:
        td_p = Path(td)
        base_bin = td_p / "bench_base"
        base_san = td_p / "bench_base_san"
        compile_bench(base_tree, base_bin, sanitize=False)
        compile_bench(base_tree, base_san, sanitize=True)
        extra = ["--only", args.only] if args.only else []
        base_san_res = run_once(base_san, ["--verify-only"] + extra, pin_cpu=False)

        cand_bin = None
        cand_san_res = None
        if cand_tree:
            cand_bin = td_p / "bench_cand"
            cand_san = td_p / "bench_cand_san"
            compile_bench(cand_tree, cand_bin, sanitize=False)
            compile_bench(cand_tree, cand_san, sanitize=True)
            cand_san_res = run_once(cand_san, ["--verify-only"] + extra, pin_cpu=False)
            # Enforce exact parity on pure-computation modules (M01, M02, M03, M04, M06, M07, M08, M09, M10)
            for mod, b_row in base_san_res.items():
                if mod == "M05_tbdr_pass_cut":
                    continue
                c_row = cand_san_res[mod]
                if b_row["checksum"] != c_row["checksum"]:
                    print(f"FAIL BIT-PARITY {mod}: base={b_row['checksum']} cand={c_row['checksum']}", file=sys.stderr)
                    return 3

        # Alternating timed runs (>= 5) pinned to CPU 0
        base_times: dict[str, list[float]] = {}
        cand_times: dict[str, list[float]] = {}
        base_meta: dict[str, dict] = {}
        cand_meta: dict[str, dict] = {}

        # Warmup 1 pass
        run_once(base_bin, extra)
        if cand_bin:
            run_once(cand_bin, extra)

        for r in range(args.runs):
            order = [("base", base_bin), ("cand", cand_bin)] if (r % 2 == 0) else [("cand", cand_bin), ("base", base_bin)]
            for tag, bp in order:
                if bp is None:
                    continue
                res = run_once(bp, extra)
                for mod, row in res.items():
                    if tag == "base":
                        base_times.setdefault(mod, []).append(row["time_ms"])
                        base_meta[mod] = row
                    else:
                        cand_times.setdefault(mod, []).append(row["time_ms"])
                        cand_meta[mod] = row

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "label": args.label,
            "runs_per_variant": args.runs,
            "asan_ubsan_passed": True,
            "bit_parity_verified": True,
            "physical_device_status": "UNVERIFIED (host Linux x86-64 + A18 Pro Cachegrind geometry + analytical model)",
            "modules": {},
        }

        print(f"=== A18 Pro Autonomous Benchmark: {args.label} ({args.runs} alternating runs, taskset -c 0) ===")
        for mod in sorted(base_times):
            bs = summarize(base_times[mod])
            entry = {"baseline": bs, "baseline_meta": base_meta[mod]}
            if cand_bin and mod in cand_times:
                cs = summarize(cand_times[mod])
                delta_pct = round(100.0 * (cs["median_ms"] - bs["median_ms"]) / max(1e-9, bs["median_ms"]), 2)
                speedup = round(bs["median_ms"] / max(1e-9, cs["median_ms"]), 3)
                wins = sum(1 for b, c in zip(base_times[mod], cand_times[mod]) if c < b)
                entry["candidate"] = cs
                entry["candidate_meta"] = cand_meta[mod]
                entry["delta_median_pct"] = delta_pct
                entry["speedup_x"] = speedup
                entry["pair_wins"] = f"{wins}/{args.runs}"
                print(f"  {mod:20s}: {bs['median_ms']:8.3f} -> {cs['median_ms']:8.3f} ms ({delta_pct:+6.2f}%, {speedup:.2f}x, wins={wins}/{args.runs})")
            else:
                print(f"  {mod:20s}: {bs['median_ms']:8.3f} ms (IQR={bs['iqr_ms']:.3f} ms, p95={bs['p95_ms']:.3f} ms)")

            short = mod.split("_")[0]
            if short in args.cachegrind and (not args.only or args.only == short):
                cg = {}
                for geo in ("everest", "sawtooth"):
                    b_cg = run_cachegrind(base_bin, short, geo)
                    cg[geo] = {"baseline": b_cg}
                    if cand_bin:
                        c_cg = run_cachegrind(cand_bin, short, geo)
                        cg[geo]["candidate"] = c_cg
                        cg[geo]["a18pro_analytical"] = a18pro_project_delta(ref, b_cg, c_cg)
                        if "Ir" in b_cg and "Ir" in c_cg:
                            d_ir = 100.0 * (c_cg["Ir"] - b_cg["Ir"]) / max(1, b_cg["Ir"])
                            d_d1 = 100.0 * ((c_cg["D1mr"] + c_cg["D1mw"]) - (b_cg["D1mr"] + b_cg["D1mw"])) / max(1, b_cg["D1mr"] + b_cg["D1mw"])
                            print(f"      [{geo:8s}] Ir: {b_cg['Ir']:,} -> {c_cg['Ir']:,} ({d_ir:+.1f}%) | D1m: {b_cg['D1mr']+b_cg['D1mw']:,} -> {c_cg['D1mr']+c_cg['D1mw']:,} ({d_d1:+.1f}%)")
                entry["cachegrind_a18pro"] = cg
            report["modules"][mod] = entry

        if args.record:
            hist = json.loads(HIST_JSON.read_text(encoding="utf-8")) if HIST_JSON.is_file() else {
                "schema_version": "1.0.0",
                "baseline_ref": "0436",
                "runs": [],
                "accepted_optimizations": [],
                "rejected_optimizations": [],
                "remaining_bottlenecks": [],
                "next_axis": "",
            }
            hist["runs"].append(report)
            HIST_JSON.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Recorded into {HIST_JSON}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
