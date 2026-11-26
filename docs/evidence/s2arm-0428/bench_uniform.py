"""Compare reconstructed uniform bindings in two prepared S2Arm source trees on Linux."""
import argparse
import csv
from math import comb
from pathlib import Path
import random
import re
from statistics import median
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trees", nargs=2, type=Path, metavar="TREE")
    parser.add_argument("--pairs", type=int, default=18)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    if args.pairs < 6 or args.pairs > 1000:
        parser.error("--pairs must be between 6 and 1000")
    source = Path(__file__).with_name("bench_uniform.c").resolve()
    rng = random.Random(42)
    timings = {}
    checks = {}
    with tempfile.TemporaryDirectory() as tmp:
        binaries = [Path(tmp) / str(i) for i in range(2)]
        for binary, tree in zip(binaries, args.trees, strict=True):
            subprocess.run(["clang", "-O2", "-no-pie", "-I", tree / "graphics/nvn/gfx/nvn",
                            source, "-o", binary], check=True)
        for rep in range(args.pairs + 1):
            for i in rng.sample(range(2), 2):
                cmd = [binaries[i]] if rep else [binaries[i], "--verify"]
                for line in subprocess.check_output(cmd, text=True).splitlines():
                    name, ms, digest = re.fullmatch(
                        r"(\w+)\s+total=\s*([\d.]+) ms .*?hash=(\w+)", line).groups()
                    if checks.setdefault((name, bool(rep)), digest) != digest:
                        raise ValueError(f"divergence in {name}")
                    if rep:
                        timings.setdefault((name, i), []).append(float(ms))
    # Exact sign interval (binomial, two tails) for the paired median ratio.
    n = args.pairs
    cut = 0
    cumulative = 1
    while 40 * cumulative <= 2**n:
        cut += 1
        cumulative += comb(n, cut)
    rows = []
    for name, timed in checks:
        if timed:
            continue
        before, after = timings[name, 0], timings[name, 1]
        ratios = sorted(b / a for a, b in zip(before, after, strict=True))
        print(name, checks[name, False], round(median(before), 3), round(median(after), 3),
              "paired delta %", *(round(100 * (r - 1), 2)
                                 for r in (median(ratios), ratios[max(0, cut-1)], ratios[n-max(1, cut)])))
        rows.extend((name, j, a, b) for j, (a, b) in enumerate(zip(before, after, strict=True), 1))
    if args.csv:
        with args.csv.open("w", newline="") as dest:
            writer = csv.writer(dest, lineterminator="\n")
            writer.writerow(("scenario", "pair", "before_ms", "after_ms"))
            writer.writerows(rows)


if __name__ == "__main__":
    main()
