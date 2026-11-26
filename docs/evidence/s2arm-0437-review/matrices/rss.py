"""Peak RSS of separate synthetic NativeAOT processes, in bytes; baseline, A/A and candidate."""
import argparse
import csv
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("binaries", type=Path, help="directory with base, control, compatible and thread clock library")
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    root = args.binaries.resolve()
    rng = random.Random(8671)
    link = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    env = dict(os.environ)
    env[link] = os.pathsep.join(filter(None, [str(root),env.get(link)]))
    with tempfile.TemporaryDirectory() as scratch, args.output.open("x", newline="") as stream:
        wrapper = Path(scratch) / "measure-rss"
        subprocess.run(["cc", "-O2", Path(__file__).with_name("rss-child.c"), "-o", wrapper], check=True)
        writer = csv.writer(stream)
        writer.writerow(("pair","variant","peak_rss_bytes"))
        for pair in range(1,25):
            for label in rng.sample(("base","control","compatible"),3):
                rows = subprocess.check_output([wrapper, root / label, "row","column","ortho","mixed","invalid"],
                                               env=env, text=True).splitlines()
                if len(rows) != 11 or not rows[-1].startswith("peak_rss_bytes,"):
                    raise RuntimeError(f"incomplete measurement for {label}")
                writer.writerow((pair, label, int(rows[-1].split(",")[1])))


if __name__ == "__main__":
    main()
