#!/usr/bin/env python3
"""Build the original Vulkan runner and a full-surface readback of that same draw."""
import argparse
import os
from pathlib import Path
from subprocess import run
p = argparse.ArgumentParser()
p.add_argument("engine", type=Path)
p.add_argument("out", type=Path)
p.add_argument("--include", type=Path)
a = p.parse_args()
src = a.engine.resolve() / "tests/shader_cases/vulkan_runner.c"
original = src.read_text()
center = '''const uint8_t *center = (const uint8_t *)mapped + (32 * 64 + 32) * 4;'''
write = '''fwrite(center,1,4,out)!=4'''
if original.count(center) != 1 or original.count(write) != 1:
    raise ValueError("Unexpected original readback implementation")
surface = a.out / "full_surface.c"
a.out.mkdir(parents=True, exist_ok=True)
surface.write_text(original.replace(center, "const uint8_t *surface = (const uint8_t *)mapped;").replace(write, "fwrite(surface,4,64*64,out)!=64*64"))
direct = a.engine.resolve() / "android/native/direct"
for inp, target in [(src, "vulkan-runner"), (surface,"vulkan-surface-runner")]:
    run([os.environ.get("CC","cc"), "-std=c11", "-O1", *([f"-I{a.include}"] if a.include else []),
         f"-I{src.parent}", inp, direct/"vk_device.c", direct/"gs_path.c",
         "-Wl,-l:libvulkan.so.1","-lm","-o", a.out/target], check=True)
