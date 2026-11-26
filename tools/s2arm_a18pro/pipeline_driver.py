#!/usr/bin/env python3
"""Time fresh, crossed and repeated synthetic stage pairs with S2Arm's Metal 4 PSO builder."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

PAIRS = 12


def shaders(index):
    prefix = "#include <metal_stdlib>\nusing namespace metal;\n"
    layout = f"struct Stage{index} {{ float4 p [[position]]; float2 uv [[user(locn0)]]; }};\n"
    vertex = (f"vertex Stage{index} sv{index}(uint id [[vertex_id]]) {{\n"
              "    float2 p = float2(float((id << 1) & 2), float(id & 2));\n"
              f"    return {{float4(p - 1.0f, 0.0f, 1.0f), p * {index+1}.0f}};\n}}\n")
    fragment = (f"fragment float4 sf{index}(Stage{index} in [[stage_in]]) {{\n"
                f"    return float4(fract(in.uv * {index+2}.25f), 0.0f, 1.0f);\n}}\n")
    return prefix + layout + vertex, prefix + layout + fragment


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tree", type=Path)
    ap.add_argument("output", type=Path, help="raw CSV for a Metal 4 device")
    args = ap.parse_args()
    builder = args.tree.resolve() / "graphics/metal/tools/psobench/pairbench.m"
    if not builder.is_file():
        ap.error("missing pinned engine PSO benchmark")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        all_sources = []
        for index in range(PAIRS * 2):
            vertex, fragment = shaders(index)
            (root / f"v{index}.metal").write_text(vertex)
            (root / f"f{index}.metal").write_text(fragment)
            all_sources.append(vertex + fragment[fragment.index("fragment float4"):])
        if sys.platform != "darwin":
            print("Generated synthetic Metal source. An Apple SDK is required to compile it.")
            return 77
        combined = root / "fixtures.metal"
        combined.write_text("".join(all_sources))
        subprocess.run(["xcrun", "--sdk", "iphoneos", "metal", "-c", combined, "-o", root/"fixtures.air"], check=True)
        print(f"Compiled {4*PAIRS} synthetic stages for iPhoneOS.", flush=True)
        exe = root / "pipeline-driver"
        subprocess.run(["xcrun", "--sdk", "macosx", "clang", "-O2", "-fobjc-arc",
                        "-I", builder.parent, Path(__file__).with_suffix(".m"), "-framework", "Metal",
                        "-framework", "Foundation", "-o", exe], check=True)
        result = subprocess.run([exe, root, str(PAIRS)], capture_output=True, text=True)
        sys.stderr.write(result.stderr)
        if result.returncode == 0:
            rows = result.stdout.splitlines()
            if len(rows) != PAIRS * 4 + 1:
                raise ValueError("incomplete Metal timings")
            args.output.write_text(result.stdout)
            print(result.stdout, end="")
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
