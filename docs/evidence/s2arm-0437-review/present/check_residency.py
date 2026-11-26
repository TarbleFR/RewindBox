"""Run the engine's layer attachment and detachment statements on two counted queue doubles."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tree", type=Path)
    args = ap.parse_args()
    nvn = args.tree / "graphics/nvn/gfx/nvn"
    engine = (nvn / "nvn_mtl.m").read_text().splitlines()
    shutdown = (nvn / "nvn_session.inc").read_text().splitlines()
    select = next(line for line in engine if "static id<MTL4CommandQueue> rb_present_queue(" in line)
    attach = next(line for line in engine if "addResidencySet:layer.residencySet" in line).split("//")[0]
    detach = next(line for line in shutdown if "removeResidencySet:g_present_layer_resident.residencySet" in line)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source = Path(__file__).with_name("queue.m").read_text()
        for key, body in [("SELECT_QUEUE",select),("ATTACH_LAYER",attach),("DETACH_LAYER",detach)]:
            assert source.count(key) == 1
            source = source.replace(key,body)
        (root / "queue.m").write_text(source)
        inc = subprocess.check_output(["gcc","-print-file-name=include"],text=True).strip()
        cmd = ["clang","-O2","-fsanitize=address,undefined","-fno-sanitize-recover=all","-I"+inc,
               root/"queue.m","-lobjc","-o",root/"queue"]
        subprocess.run(cmd,check=True)
        import os
        return subprocess.run([root/"queue"],env={**os.environ,"ASAN_OPTIONS":"detect_leaks=0"}).returncode


if __name__ == "__main__":
    raise SystemExit(main())
