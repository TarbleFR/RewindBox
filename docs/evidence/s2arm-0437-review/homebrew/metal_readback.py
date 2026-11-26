"""Compile frozen MSL emitted from the documented guest programs and compare Metal to the independent Vulkan oracle."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def main():
    here = Path(__file__).resolve().parent
    outcomes = json.loads((here / "reference-output.json").read_text())
    if len(outcomes) != 3:
        raise ValueError("expected all three independent Vulkan readback records")
    apple = sys.platform == "darwin"
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        if apple:
            subprocess.run(["xcrun","--sdk","macosx","clang","-O2","-fobjc-arc",
                            here / "metal_readback.m","-framework","Foundation","-framework","Metal",
                            "-o",root / "check"],check=True)
        commands = []
        for case in outcomes:
            stem = case["spirv_sha256"][:16]
            shader = here / "msl" / (stem + ".metal")
            if hashlib.sha256(shader.read_bytes()).hexdigest() != case["msl_sha256"]:
                raise ValueError(f"MSL changed for {case['id']}")
            if case["stage"] == "comp":
                expected = struct.pack("<64I", 17, 17, 42, *range(3,64))
                digest = case["readback_sha256"]
            else:
                expected = bytes(case["readback_first4"]) * (64 * 64)
                digest = case["full_surface_sha256"]
            if hashlib.sha256(expected).hexdigest() != digest:
                raise ValueError(f"Vulkan oracle mismatch for {case['id']}")
            oracle = root / (stem + ".expected")
            oracle.write_bytes(expected)
            if apple:
                subprocess.run(["xcrun","--sdk","iphoneos","metal","-c",shader,"-o",root / (stem+".air")],check=True)
            commands.append([root / "check",shader,"vk_" + stem,case["stage"],oracle])
        if not apple:
            print("Three emitted MSL hashes and three Vulkan output hashes match. Apple runtime unavailable.")
            return 77
        print("All three MSL programs compiled to AIR for iPhoneOS.",flush=True)
        for command in commands:
            status = subprocess.run(command).returncode
            if status:
                return status
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
