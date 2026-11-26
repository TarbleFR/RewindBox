"""Build and interleave managed CPU probes in scratch space. CSV times cover RewriteWindow calls."""
import argparse
import csv
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MODES = ("row", "column", "ortho", "invalid", "mixed", "near-miss")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--variants", nargs="+", default=["direct", "lazy", "ortho", "all"])
    parser.add_argument("--pairs", type=int, default=16)
    parser.add_argument("--aot", help="publish NativeAOT for this runtime identifier")
    parser.add_argument("--modes", choices=MODES, nargs="+", default=MODES)
    parser.add_argument("--peak-rss", type=Path, help="separate 24-triplet NativeAOT memory check")
    args = parser.parse_args()
    if args.peak_rss and (not args.aot or set(args.variants) != {"control","compatible"}):
        parser.error("--peak-rss requires --aot and the two variants control compatible")
    prefix = [] if args.cpu is None else ["taskset", "-c", str(args.cpu)]
    env = dict(os.environ, DOTNET_TieredCompilation="0")
    rng = random.Random(44220)
    with tempfile.TemporaryDirectory() as scratch:
        suffix = ".dylib" if sys.platform == "darwin" else ".so"
        clock = Path(scratch) / ("libs2arm_bench_clock" + suffix)
        subprocess.run(["cc", "-shared", "-fPIC", "-O2", HERE / "threadclock.c", "-o", clock], check=True)
        libpath = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        env[libpath] = os.pathsep.join(filter(None, (scratch, env.get(libpath))))
        programs = {}
        reference = None
        for label in ("base", *args.variants):
            root = Path(scratch) / label
            widen = root / "graphics" / "widen"
            shutil.copytree(args.tree / "graphics" / "widen", widen, ignore=shutil.ignore_patterns("bin", "obj"))
            if label not in ("base", "control"):
                with (HERE / (label + ".patch")).open("rb") as change:
                    subprocess.run(["patch", "-p1"], cwd=root, stdin=change, check=True)
            bench = widen.parent / "bench"
            bench.mkdir()
            shutil.copy(HERE / "bench.csproj", bench)
            shutil.copy(HERE / "probe.cs", bench)
            if args.aot:
                subprocess.run(["dotnet", "publish", "--nologo", "-c", "Release", "-r", args.aot,
                                "-p:PublishAot=true", "-o", root / "native"], cwd=bench, check=True)
                programs[label] = [*prefix, root / "native/bench"]
            else:
                subprocess.run(["dotnet","build","--nologo","-c","Release"],cwd=bench,check=True)
                programs[label] = [*prefix, "dotnet", bench / "bin/Release/net10.0/bench.dll"]
            checksum = subprocess.check_output([*programs[label], "verify"], env=env, text=True).strip()
            reference = reference or checksum
            if checksum != reference:
                raise ValueError((label, checksum, reference))
            print(label, "output hash", checksum, flush=True)
        seen = {}
        with args.csv.open("x", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(("pair","mode","variant","ms","hash","allocated","thread_cpu_ms"))
            for pair in range(1, args.pairs + 1):
                modes = rng.sample(args.modes, len(args.modes))
                for label in rng.sample(list(programs),len(programs)):
                    rows = subprocess.check_output([*programs[label], *modes], env=env, text=True).splitlines()
                    for mode, line in zip(modes, rows[len(modes):], strict=True):
                        name,ms,checksum,alloc,cpu = line.split(",")
                        if name != mode or seen.setdefault(name,(checksum,alloc)) != (checksum,alloc):
                            raise ValueError((line, mode, label))
                        writer.writerow((pair,name,label,ms,checksum,alloc,cpu))
                    output.flush()

        if args.peak_rss:
            rss_root = Path(scratch) / "rss"
            rss_root.mkdir()
            for label, command in programs.items():
                (rss_root / label).symlink_to(command[-1])
            (rss_root / clock.name).symlink_to(clock)
            subprocess.run([*prefix, sys.executable, HERE / "rss.py", rss_root, args.peak_rss], check=True)

if __name__ == "__main__":
    main()
