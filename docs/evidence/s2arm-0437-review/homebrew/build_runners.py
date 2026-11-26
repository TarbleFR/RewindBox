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
p.add_argument("--surface-size", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), default=(64, 64))
a = p.parse_args()
src = a.engine.resolve() / "tests/shader_cases/vulkan_runner.c"
original = src.read_text()
center = '''const uint8_t *center = (const uint8_t *)mapped + (32 * 64 + 32) * 4;'''
write = '''fwrite(center,1,4,out)!=4'''
if original.count(center) != 1 or original.count(write) != 1:
    raise ValueError("Unexpected original readback implementation")
surface = a.out / "full_surface.c"
a.out.mkdir(parents=True, exist_ok=True)
width, height = a.surface_size
if not (0 < width <= 8192 and 0 < height <= 8192):
    raise ValueError("invalid surface extent")
surface_src = original.replace(center, "const uint8_t *surface = (const uint8_t *)mapped;")
surface_src = surface_src.replace(write, f"fwrite(surface,4,{width}*{height},out)!={width}*{height}")
# Each occurrence sets a framebuffer, viewport, scissor, copy extent or buffer size for this draw.
for old, new, count in [
    ("64, 64", f"{width}, {height}", 3),
    ("64 * 64 * 4", f"{width} * {height} * 4", 1),
    ("width = 64", f"width = {width}", 3),
    ("height = 64", f"height = {height}", 3),
]:
    if surface_src.count(old) != count:
        raise ValueError(f"unexpected fixture extent: {old}")
    surface_src = surface_src.replace(old, new)
surface.write_text(surface_src)
direct = a.engine.resolve() / "android/native/direct"
for inp, target in [(src, "vulkan-runner"), (surface,"vulkan-surface-runner")]:
    run([os.environ.get("CC","cc"), "-std=c11", "-O1", *([f"-I{a.include}"] if a.include else []),
         f"-I{src.parent}", inp, direct/"vk_device.c", direct/"gs_path.c",
         "-Wl,-l:libvulkan.so.1","-lm","-o", a.out/target], check=True)
