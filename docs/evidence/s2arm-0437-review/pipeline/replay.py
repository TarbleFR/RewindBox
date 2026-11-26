"""Compile the pipeline-key builder and resident lookup from each prepared S2Arm tree."""
import argparse
import csv
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

MODES = ("mixed", "sparse", "merged", "cold", "warm")
GOLDEN = ("9aef96c14443ee84", "0", "0", "344")


def function(source, signature):
    start = source.index(signature)
    end = source.index("\n}", start) + 2
    return source[start:end]


def build(tree, temp, index, sanitize):
    nvn = tree / "graphics/nvn/gfx/nvn"
    source = (nvn / "nvn_mtl.m").read_text()
    formats = (nvn / "nvn_pfkind.h").read_text()
    # The renderer uses a named Metal enum. Reassign deterministic test numbers
    # on all hosts while preserving the real classifier's cases.
    names = sorted(set(re.findall(r"MTLPixelFormat[A-Za-z0-9]+", formats)))
    code = ["typedef unsigned MTLPixelFormat;", "enum { " + ", ".join(
        f"{name}={8+3*i}" for i, name in enumerate(names)) + " };",
        function(formats, "static inline int pf_int_kind(")]
    key = (nvn / "nvn_pso_skey.h").read_text()
    code.append(key[key.index("typedef struct {"):key.index("} pso_key;") + len("} pso_key;")])
    for signature in ("static unsigned rb_read_vertex_mask(", "static void pso_norm_masks(",
                      "static void pso_key_norm(", "static const pso_key *rb_pso_live_key(",
                      "static __unsafe_unretained id rb_pso_probe(", "static void pso_key_fill("):
        code.append(function(source, signature))
    inc = temp / f"source-{index}.inc"
    inc.write_text("\n".join(code) + "\n")
    binary = temp / f"variant-{index}-{'san' if sanitize else 'time'}"
    flags = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"] if sanitize else []
    if sys.platform.startswith("linux"):
        flags += ["-fno-pie", "-no-pie"]
    subprocess.run(["clang", "-O2", *flags, "-I", nvn, "-I", nvn / "include",
                    f'-DIMPL="{inc}"', Path(__file__).with_name("probe.c"), "-o", binary], check=True)
    return binary


def run(command):
    fields = subprocess.check_output(command, text=True).strip().split()
    if len(fields) != 7:
        raise RuntimeError(f"unexpected output from {command}")
    return tuple(map(float, fields[:3])), tuple(fields[3:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trees", type=Path, nargs="+", help="prepared baseline and candidate trees, in order")
    parser.add_argument("--pairs", type=int, default=29)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    if len(args.trees)<2 or args.pairs<1:
        parser.error("provide at least two prepared trees and one measured pair")
    prefix = []
    if sys.platform.startswith("linux") and hasattr(os, "sched_getaffinity") and shutil.which("taskset"):
        allowed = os.sched_getaffinity(0)
        core = args.cpu if args.cpu is not None else min(allowed)
        if core not in allowed:
            parser.error(f"core {core} unavailable; allowed {sorted(allowed)}")
        prefix = ["taskset", "-c", str(core)]
    elif args.cpu is not None:
        print("CPU affinity unavailable on this host. Running with the OS scheduler.")
    result = []
    rng = random.Random(289)
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        binaries = []
        for index, tree in enumerate(args.trees):
            san = build(tree, temp, index, True)
            if run([san, "verify"])[1] != GOLDEN:
                raise RuntimeError(f"reference byte or shader-identity mismatch in {tree}")
            binpath = build(tree, temp, index, False)
            if run([binpath,"verify"])[1] != GOLDEN:
                raise RuntimeError(f"optimized binary mismatch in {tree}")
            binaries.append(binpath)
        for pair in range(1+args.pairs):
            for mode in rng.sample(MODES,len(MODES)):
                for index in rng.sample(range(len(binaries)), len(binaries)):
                    (elapsed,p50,p95), observed = run([*prefix,binaries[index],mode])
                    table = mode in ("warm", "cold")
                    expected = ("0000000000000000", "13088640" if table else "0",
                                "102656" if mode=="cold" else "256" if mode=="warm" else "0", "344")
                    if observed != expected:
                        raise RuntimeError(f"table result changed in {mode}: {observed}")
                    if pair: result.append((pair,mode,index,elapsed,p50,p95))
    if args.csv:
        with args.csv.open("w",newline="") as stream:
            writer=csv.writer(stream,lineterminator="\n")
            writer.writerow(("pair","mode","tree_index","total_ms","batch_p50_ms","batch_p95_ms"))
            writer.writerows(result)
    for mode in MODES:
        for i, tree in enumerate(args.trees):
            group = [r for r in result if r[1]==mode and r[2]==i]
            print(mode,tree,"median total / median batch p50 / median batch p95 (ms)",
                  *(f"{statistics.median(r[k] for r in group):.6f}" for k in (3,4,5)))

if __name__=="__main__":
    main()
