"""Exercise CPU texture writes and reads on the source immediately before or after 0450."""
import argparse
from pathlib import Path
import subprocess


def compare(engine, output):
    gfx = engine.resolve() / "graphics/nvn/gfx"
    tex = gfx / "tex"
    nvn = gfx / "nvn"
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    hle = (nvn / "hle_nvn.c").read_text()
    metal = (nvn / "nvn_mtl.m").read_text()
    write = hle[hle.index("static int write_region_bl("):hle.index("\nNVN(nvnTextureWriteTexels,")]
    read = hle[hle.index("static void read_texels(const tex_t *o"):hle.index("\nNVN(nvnTextureReadTexels,")]
    cpu = metal.index("void nvn_be_read_texels(const tex_t *t, unsigned level,")
    cpu_read = metal[cpu:metal.index("    id<MTLTexture> mt = tex_mtl(t);", cpu)]
    (output / "actual.inc").write_text(write + "\n" + cpu_read + "    abort();\n}\n" + read + "\n")

    source = (tex / "nvn_deswizzle.c").read_text()
    original = "|| (d->flags & 0x10) || d->samples > 1) return -1;"
    corrected = original.replace("0x10", "(0x10 | 0x40)")
    if source.count(original) + source.count(corrected) != 1:
        raise ValueError("expected one block-linear geometry guard")
    patch = Path(__file__).resolve().parents[4] / "build-utils/s2arm/engine/patches/0450-honor-linear-layout-for-render-target-writes.patch"
    for label, reverse in (("base", True), ("fixed", False)):
        tree = output / label
        path = tree / "graphics/nvn/gfx/tex/nvn_deswizzle.c"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        if (corrected in source) == reverse:
            command = ["patch", "--batch", "--fuzz=0", "-p1"]
            if reverse:
                command.append("-R")
            subprocess.run(command, cwd=tree, input=patch.read_bytes(), check=True)
        for fixture in (Path(__file__).with_name("probe.c").resolve(), tex / "tests/t_tex.c", tex / "tests/t_tex_layout.c"):
            program = output / f"{label}-{fixture.stem}"
            sanitizer = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"] if fixture.stem == "probe" else []
            subprocess.run(["clang", "-std=c11", "-O2", "-I", tex, "-I", output, f"-DFIXED={int(not reverse)}",
                            *sanitizer, fixture, path, nvn / "nvn_tex.c", "-lm", "-o", program], check=True)
            with program.with_suffix(".txt").open("w") as stream:
                subprocess.run([program], stdout=stream, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compare(args.engine, args.output)
