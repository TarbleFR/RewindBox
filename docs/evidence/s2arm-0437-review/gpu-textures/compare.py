"""Vary only the launch geometry of the engine's Metal texture decoder; retain the same shader bytes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: compare.py PREPARED_S2ARM_TREE")
    gfx = Path(sys.argv[1]).resolve() / "graphics/nvn/gfx"
    source = (gfx / "tex/nvn_deswizzle_gpu.m").read_text()
    literal = source.split("static const char *const k_nvn_deswz_msl =",1)[1].split('"}\\n";',1)
    if len(literal) != 2:
        raise ValueError("unexpected texture shader terminator")
    strings = re.findall(r'^\s*("(?:[^"\\]|\\.)*")',literal[0], re.M)
    shader = "".join(map(json.loads,strings)) + "}\n"
    if shader.count("kernel void deswz(") != 1:
        raise ValueError("failed to extract engine shader")
    print("shader SHA-256", hashlib.sha256(shader.encode()).hexdigest(), flush=True)
    if sys.platform != "darwin":
        print("Kernel extracted; Apple runtime unavailable.")
        return 77
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        msl = root / "deswz.metal"
        msl.write_text(shader)
        exe = root / "benchmark"
        subprocess.run(["xcrun","--sdk","iphoneos","metal","-c",msl,"-o",root/"deswz.air"],check=True)
        cflags = ["-O2","-I"+str(gfx/"nvn/include"),"-I"+str(gfx/"nvn"),"-I"+str(gfx/"tex")]
        obj = []
        for unit in [gfx/"tex/nvn_deswizzle.c",gfx/"nvn/nvn_tex.c"]:
            output = root / (unit.stem + ".o")
            subprocess.run(["xcrun","--sdk","macosx","clang",*cflags,"-c",unit,"-o",output],check=True)
            obj.append(output)
        subprocess.run(["xcrun","--sdk","macosx","clang",*cflags,"-fobjc-arc",Path(__file__).with_suffix(".m"),
                        *obj,"-framework","Metal","-framework","Foundation","-o",exe],check=True)
        return subprocess.run([exe,msl]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
