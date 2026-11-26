"""Compare ownership of pitched 2D textures before and after the candidate geometry change."""
import argparse
from pathlib import Path
import subprocess
import sys


def compare(engine, output):
    here = Path(__file__).resolve().parent
    rel = Path("graphics/nvn/gfx/nvn/nvn_mtl.m")
    engine = engine.resolve()
    output = output.resolve()
    target = output / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    current = (engine / rel).read_text()
    target.write_text(current)
    already_fixed = "static void linear_bytes_rects(" in current
    cmd = ["patch", "-p1", "--batch", "--fuzz=0", *(["-R"] if already_fixed else [])]
    subprocess.run(cmd, input=(here / "candidate.diff").read_bytes(), cwd=output, check=True)
    alternate = target.read_text()
    for name, text in [("base", alternate if already_fixed else current),
                       ("candidate", current if already_fixed else alternate)]:
        start = text.index("static unsigned tex_layers(const tex_t *t) {")
        end = text.index("typedef struct { const tex_t *t; uint64_t *pgpu", start)
        (output / (name+".inc")).write_text(text[start:end])
        nvn = (engine / rel).parent
        options = ["-O2", "-std=c11", "-I", nvn, "-I", output, f'-DIMPL="{name}.inc"']
        if name == "candidate":
            options.append("-DEXPECT_FIXED")
        for source in ["oracle.c", *(["metal.m"] if sys.platform == "darwin" else [])]:
            apple = source.endswith(".m")
            flags = ["-fobjc-arc", "-framework", "Foundation", "-framework", "Metal"] if apple else [
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
            exe = output / (name+"-"+Path(source).stem)
            subprocess.run(["clang", *options, *flags, here/source, nvn/"nvn_tex.c", "-o", exe], check=True)
            subprocess.run([exe], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compare(args.engine, args.output)
