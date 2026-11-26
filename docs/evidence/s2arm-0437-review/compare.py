"""Run the same texture tests against two prepared S2Arm trees, on Linux or macOS."""
import argparse
import csv
import json
import platform
import random
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("baseline", type=Path)
parser.add_argument("candidate", type=Path)
parser.add_argument("csv", type=Path)
args = parser.parse_args()
trees = [p.resolve() / "graphics/nvn/gfx" for p in (args.baseline, args.candidate)]
san = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]


def compile_c(exe, *args):
    subprocess.run(["clang", "-std=gnu11", "-O2", *args, "-o", exe], check=True)


def run(*cmd):
    return subprocess.check_output(cmd, text=True).strip()


def sources(tree):
    return [tree / "tex/nvn_deswizzle.c", tree / "nvn/nvn_tex.c"]


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    ref, candidate = trees
    # Prefix both reference translation units, including layout routines, so that
    # the reference copy cannot accidentally call the candidate's geometry code.
    headers = (ref / "tex/nvn_deswizzle.h").read_text() + (ref / "nvn/nvn_tex.h").read_text()
    symbols = set(re.findall(r"\b(nvn_\w+)\s*\(", headers)) | {"nvn_gob_switch2"}
    objects = []
    for src in sources(ref):
        obj = tmp / (src.stem + ".o")
        compile_c(obj, *san, *(f"-D{name}=ref_{name}" for name in sorted(symbols)), "-c", src)
        objects.append(obj)
    compile_c(tmp / "parity", *san, "-I" + str(candidate / "tex"),
              "-I" + str(candidate / "nvn/include"), HERE / "texture-bytes.c", *sources(candidate), *objects)
    print(run(tmp / "parity"))
    for t, tree in enumerate(trees):
        flags = ["-I" + str(tree / d) for d in ("tex", "nvn", "nvn/include")]
        compile_c(tmp / f"texture{t}", *flags, HERE / "texture-bench.c", *sources(tree))
        compile_c(tmp / f"geometry{t}", *flags, *(["-DUSE_GEOM_EX"] if t else []),
                  HERE / "geometry.c", *sources(tree))
        compile_c(tmp / f"sentinel{t}", *san, *flags, HERE / "geometry-sentinel.c", *sources(tree))
    assert run(tmp / "sentinel0") == run(tmp / "sentinel1"), "geometry sentinel mismatch"
    print("Geometry sentinel outputs identical")
    rng = random.Random(845)
    print(platform.platform(), platform.machine(), run("clang", "--version").splitlines()[0])
    with args.csv.open("w") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["workload", "pair", "variant", "ms"])
        for work in ("texture", "geometry"):
            timings = [[], []]
            expected = None
            for pair in range(13):
                order = [0, 1]
                rng.shuffle(order)
                for t in order:
                    output = run(tmp / f"{work}{t}")
                    if work == "texture":
                        row = json.loads(output.splitlines()[-1])
                        digest, ms = (row["checksum"], row["bytes"]), row["time_ms"]
                    else:
                        digest, ms = output.rsplit(" ms=", 1)
                    if expected is None:
                        expected = digest
                    assert digest == expected, (work, pair, digest, expected)
                    if pair:
                        timings[t].append(float(ms))
                        writer.writerow([work, pair, ("base", "candidate")[t], ms])
            print(work, [statistics.median(values) for values in timings], expected)
