#!/usr/bin/env python3
"""Replay two original S2Arm microprograms and the public deko_basic fragment shader."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

def digest(data):
    return hashlib.sha256(data).hexdigest()

def run(*args):
    subprocess.run(list(map(str, args)), check=True)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("engine", type=Path)
parser.add_argument("out", type=Path)
parser.add_argument("--translator", type=Path, required=True)
parser.add_argument("--runner", type=Path, required=True)
parser.add_argument("--surface-runner", type=Path, required=True)
parser.add_argument("--glsl", type=Path, required=True)
source = parser.add_mutually_exclusive_group()
source.add_argument("--uam", type=Path, help="Pinned devkitPro/uam executable")
source.add_argument("--fixed", type=Path, help="Directory containing color.dksh and color.raw from an earlier compile")
args = parser.parse_args()
root, out = args.engine.resolve(), args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
cases = root / "tests/shader_cases"
sys.path[:0] = [str(cases), str(root / "graphics/tools")]
from run import binary, check_device_capabilities, compare
from spirv_msl import translate

vs = out / "helper.vert.spv"
run("glslc", "--target-env=vulkan1.1", cases/"harness.vert", "-o", vs)
run("spirv-val", "--target-env", "vulkan1.1", vs)
programs = []
for id in ("memory/copy17", "attribute/reverse"):
    c = json.loads((cases / (id + ".json")).read_text())
    programs.append((c, binary(c)))
if args.uam or args.fixed:
    if digest(args.glsl.read_bytes()) != "eb787709145962ab62ae4bdcc7c909267e028fe6265c2faac90ce7497a065d37":
        raise ValueError("Wrong public homebrew shader")
    if args.uam:
        run(args.uam, "-s", "frag", "-o", out/"color.dksh", "-r", out/"color.raw", args.glsl)
    guest = args.fixed or out
    dksh = (guest/"color.dksh").read_bytes()
    magic, header, control, codesize, programs_off, n = struct.unpack_from("<6I", dksh)
    stage, entry = struct.unpack_from("<II", dksh, programs_off)
    if (magic, header, n, stage, len(dksh)) != (0x48534b44, 24, 1, 1, control+codesize):
        raise ValueError("Unexpected UAM program layout")
    raw = (guest/"color.raw").read_bytes()
    # DkshProgramHeader.entrypoint addresses the 0x50-byte NVIDIA fragment shader
    # header relative to the code section. Verify the following instructions are
    # byte-identical to the standalone Maxwell module emitted by the same compile.
    nv = dksh[control + entry : control + entry + 0x50 + len(raw)]
    if not raw or nv[0x50:] != raw:
        raise ValueError("Expected the real UAM instructions after the Maxwell header")
    programs.append(({"id":"switchbrew/deko_basic","stage":"fragment",
                      "expected":[64,128,191,255]}, nv))

manifest = []
for c, nv in programs:
    p = out / c["id"].split("/")[1]
    p.with_suffix(".bin").write_bytes(nv)
    manifest.append({"id":c["id"], "stage":c["stage"], "binary":str(p.with_suffix(".bin")),
                     "spirv":str(p.with_suffix(".spv"))})
mf = out / "manifest.json"
mf.write_text(json.dumps(manifest))
run("dotnet", args.translator, mf, out/"events.json")
rows = []
for (c, nv), m in zip(programs, manifest):
    name = c["id"].split("/")[1]
    spv = Path(m["spirv"])
    check_device_capabilities(spv.read_bytes())
    run("spirv-val", "--target-env", "vulkan1.1", spv)
    got = out / (name+".readback")
    if c["stage"] == "compute":
        inp = out / "storage.input"
        inp.write_bytes(struct.pack("<64I", *c["inputs"]["storage0"]))
        run(args.runner, "compute", spv, inp, got)
        actual = list(struct.unpack("<64I", got.read_bytes()))
    else:
        run(args.runner, "fragment", vs, spv, got)
        actual = list(got.read_bytes())
    compare(c["id"], c["expected"], actual)
    surface = None
    if c["stage"] == "fragment":
        full = out / (name+".rgba")
        run(args.surface_runner, "fragment", vs, spv, full)
        surface = full.read_bytes()
        if surface != bytes(c["expected"]) * (64*64):
            raise ValueError(f"{name}: mismatch across 64×64 surface")
    if c["id"] == "switchbrew/deko_basic":
        # Independent frontend validates the guest translation against the original GLSL.
        refspv, refgot = out/"color-reference.spv", out/"color-reference.rgba"
        run("glslc", "-fshader-stage=fragment", "--target-env=vulkan1.1", args.glsl, "-o", refspv)
        run("spirv-val", "--target-env", "vulkan1.1", refspv)
        run(args.runner, "fragment", vs, refspv, refgot)
        compare("direct GLSL readback", actual, list(refgot.read_bytes()))
        reffull = out/"color-reference-full.rgba"
        run(args.surface_runner, "fragment", vs, refspv, reffull)
        if reffull.read_bytes() != surface:
            raise ValueError("GLSL and translated Maxwell readbacks differ across the 64×64 surface")
    unused_key, stage, resources, metal, unused_path = translate(str(spv), str(out), str(out))
    rows.append({"id":c["id"],"stage":stage,"guest_sha256":digest(nv),"spirv_sha256":digest(spv.read_bytes()),
                 "msl_sha256":digest(Path(metal[0]).read_bytes()),"resources":resources,
                 "readback_sha256":digest(got.read_bytes()),"verified":len(actual),"readback_first4":actual[:4],
                 "full_surface_sha256":digest(surface) if surface is not None else None})
(out/"report.json").write_text(json.dumps(rows, indent=2)+"\n")
print(json.dumps(rows, indent=2))
