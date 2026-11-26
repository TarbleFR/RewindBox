"""Restore only the known 0448 WidenRewriter in an experiment's private copy."""
import hashlib
from pathlib import Path
import subprocess

REFERENCE = "8e3cc210862e3dcc270f87a53b4ba362bcc91c1fafce2487ca72e5ddc7c7f7f4"
COMPATIBLE = "43d1e885181292f5bc1cedc01802d02145789ba025675cf31e577f616941adb6"


def restore_reference(scratch_root):
    source = scratch_root / "graphics/widen/WidenRewriter.cs"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest == COMPATIBLE:
        change = Path(__file__).with_name("compatible.patch")
        with change.open("rb") as patch:
            subprocess.run(["patch", "--batch", "-R", "-p1"], cwd=scratch_root, stdin=patch, check=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != REFERENCE:
        raise ValueError(f"unexpected WidenRewriter source {digest}")
