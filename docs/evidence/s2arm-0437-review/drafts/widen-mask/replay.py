"""Compare the real WidenSession methods with the four archived variants, in a scratch tree."""
import argparse
import csv
import hashlib
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE_SHA = "72a4abb174c92ea1a2a2a72527a98e5fd72f9e5df9547bdb9377712cc02f8d77"
MODES = ("single", "mixed", "dense", "none", "sparse-bind")


def build(source, root, label):
    location = root / label / "graphics" / "widen"
    shutil.copytree(source, location, ignore=shutil.ignore_patterns("obj", "bin"))
    if label != "base":
        with (HERE / f"{label}.diff").open("rb") as patch:
            subprocess.run(["patch", "-p1"], cwd=root / label, stdin=patch, check=True)
    bench = location.parent / "bench"
    bench.mkdir()
    for filename in ("Program.cs", "bench.csproj"):
        shutil.copy(HERE / filename, bench)
    subprocess.run(["dotnet", "build", "-c", "Release", "--nologo"], cwd=bench, check=True)
    return bench / "bin" / "Release" / "net10.0" / "bench.dll"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    parser.add_argument("variant", choices=("hybrid", "split", "tuple"))
    parser.add_argument("csv", type=Path)
    parser.add_argument("--cpu", type=int, help="pin all measurement processes to this Linux CPU")
    args = parser.parse_args()
    source = args.tree / "graphics" / "widen"
    if hashlib.sha256((source / "WidenSession.cs").read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("WidenSession.cs differs from the archived reference")
    rng = random.Random(1045)
    env = dict(os.environ, DOTNET_TieredCompilation="0")
    prefix = [] if args.cpu is None else ["taskset", "-c", str(args.cpu)]
    with tempfile.TemporaryDirectory() as scratch:
        programs = {key: build(source, Path(scratch), key) for key in ("base", "mask", args.variant)}

        def run(label, mode):
            cmd = [*prefix, "dotnet", programs[label], mode]
            reported, ms, checksum, alloc = subprocess.check_output(cmd, env=env, text=True).split()
            if reported != mode or int(alloc) != 0:
                raise ValueError((reported, mode, alloc))
            return ms, checksum, alloc

        for name in programs:
            if run(name, "verify")[1] != "7348d5c5":
                raise ValueError(f"mismatched camera read descriptors for {name}")
        seen = {}
        with args.csv.open("x", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("pair", "mode", "var", "ms", "hash", "allocated"))
            for pair in range(13):
                for mode in rng.sample(MODES, len(MODES)):
                    for label in rng.sample(list(programs), len(programs)):
                        ms, checksum, alloc = run(label, mode)
                        if seen.setdefault(mode, checksum) != checksum:
                            raise ValueError(f"mismatched workload {mode}, {label}")
                        writer.writerow((pair, mode, label, ms, checksum, alloc))


if __name__ == "__main__":
    main()
