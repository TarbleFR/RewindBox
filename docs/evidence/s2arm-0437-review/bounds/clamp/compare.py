"""Separate the clamp arithmetic from the removal of Objective-C accessors in len_fill."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

BOUNDS = Path(__file__).resolve().parents[1]
REL = Path("graphics/nvn/gfx/nvn/nvn_mtl.m")


def run(*cmd):
    subprocess.run([sys.executable, *cmd], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("initial", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as dirname:
        scratch = Path(dirname)
        harness = scratch / "harness"
        run(BOUNDS / "stable/prepare.py", args.current, BOUNDS, harness)
        variant = scratch / "arena-only"
        path = variant / REL
        path.parent.mkdir(parents=True)
        current = (args.current / REL).read_text()
        initial = (args.initial / REL).read_text()
        opening = "static inline uint32_t ubolen_vec4_cap("
        closing = "static inline uint32_t ubolen_vec4("
        old = initial[initial.index(opening):initial.index(closing)]
        new = current[current.index(opening):current.index(closing)]
        if old == new:
            raise ValueError("the two source points must bracket the clamp change")
        path.write_text(current.replace(new,old,1))
        shutil.copy((args.current / REL).with_name("nvn_refl.h"), path.with_name("nvn_refl.h"))
        for label, base, after in [("initial-current",args.initial,args.current),
                                   ("initial-arena",args.initial,variant),
                                   ("current-arena",args.current,variant)]:
            print(label, flush=True)
            folder = args.out / label
            run(harness / "compare_ubolen.py",base,after,folder)
            run(harness / "report.py",*(folder / f"{order}.tsv" for order in ("forward","reverse","control")))


if __name__ == "__main__":
    main()
