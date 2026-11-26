"""Compare reconstructed uniform bindings in two prepared S2Arm source trees on Linux."""
import argparse
from pathlib import Path
import random
import re
from statistics import median
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trees", nargs=2, type=Path, metavar="TREE")
    args = parser.parse_args()
    source = Path(__file__).with_name("bench_uniform.c").resolve()
    rng = random.Random(42)
    timings = {}
    checks = {}
    with tempfile.TemporaryDirectory() as tmp:
        binaries = [Path(tmp) / str(i) for i in range(2)]
        for binary, tree in zip(binaries, args.trees, strict=True):
            subprocess.run(["clang", "-O2", "-no-pie", "-I", tree / "graphics/nvn/gfx/nvn",
                            source, "-o", binary], check=True)
        for rep in range(19):
            for i in rng.sample(range(2), 2):
                cmd = [binaries[i]] if rep else [binaries[i], "--verify"]
                for line in subprocess.check_output(cmd, text=True).splitlines():
                    name, ms, digest = re.fullmatch(
                        r"(\w+)\s+total=\s*([\d.]+) ms .*?hash=(\w+)", line).groups()
                    if checks.setdefault((name, bool(rep)), digest) != digest:
                        raise ValueError(f"divergence in {name}")
                    if rep:
                        timings.setdefault((name, i), []).append(float(ms))
    for name, timed in checks:
        if not timed:
            print(name, checks[name, False], *(round(median(timings[name, i]), 3) for i in range(2)))


if __name__ == "__main__":
    main()
