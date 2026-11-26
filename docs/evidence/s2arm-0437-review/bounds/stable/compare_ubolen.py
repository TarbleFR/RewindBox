"""Compare the engine's len_fill in two trees. Uses Clang with the platform Objective-C runtime on Linux or macOS."""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def run(*argv, **kwargs):
    subprocess.run(argv, check=True, **kwargs)


def extract(root, output, symbol):
    path = root / "graphics/nvn/gfx/nvn"
    source = (path / "nvn_mtl.m").read_text()
    start = source.index("static uint64_t len_fill(")
    body = source[start:source.index("\n}", start) + 2]
    helpers = source[source.index("static inline uint32_t ubolen_vec4_cap("):start]
    code = helpers + body.replace("static uint64_t len_fill(", "__attribute__((noinline)) uint64_t " + symbol + "(")
    for name in ("ubolen_vec4_cap", "ubolen_vec4", "sbsz_ctx", "sbsz_bound"):
        code = re.sub(r"\b" + name + r"\b", symbol + "_" + name, code)
    (output / (symbol + ".inc")).write_text(code)
    return (path / "nvn_refl.h").read_text().split("#ifdef __OBJC__")[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None)
    args = parser.parse_args()
    cc = ["clang", "-O2"]
    libs = ["-lobjc"]
    if sys.platform == "darwin":
        libs.extend(["-framework", "Foundation"])
    else:
        gcc_include = subprocess.check_output(["gcc", "-print-file-name=include"], text=True).strip()
        cc.append("-I" + gcc_include)
    affinity = ["taskset", "-c", str(args.cpu)] if args.cpu is not None else []
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        reflection = extract(args.baseline, tmp, "baseline")
        other_reflection = extract(args.candidate, tmp, "candidate")
        if reflection != other_reflection:
            raise ValueError("Les deux arbres utilisent des interfaces de réflexion différentes")
        (tmp / "nvn_refl.h").write_text(reflection)
        source = Path(__file__).with_name("bench.m").read_text()
        (tmp / "bench.m").write_text(source)
        output = args.results.resolve()
        output.mkdir(exist_ok=True, parents=True)
        run(*cc, "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "bench.m", *libs, "-o", "verify", cwd=tmp)
        with (output / "validation.txt").open("w") as stream:
            run("./verify", "verify", cwd=tmp, stdout=stream,
                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0"))
        for name in ("forward", "reverse", "control"):
            expression = '#include "baseline.inc"\n#include "candidate.inc"'
            assert expression in source
            if name == "reverse":
                version = source.replace(expression, '#include "candidate.inc"\n#include "baseline.inc"')
            elif name == "control":
                (tmp / "control.inc").write_text((tmp / "baseline.inc").read_text().replace("uint64_t baseline(", "uint64_t candidate(").replace("baseline_", "control_"))
                version = source.replace('#include "candidate.inc"', '#include "control.inc"')
            else:
                version = source
            (tmp / "test.m").write_text(version)
            run(*cc, "test.m", *libs, "-o", "timed", cwd=tmp)
            with (output / (name + ".tsv")).open("w") as stream:
                run(*affinity, "./timed", cwd=tmp, stdout=stream)


if __name__ == "__main__":
    main()
