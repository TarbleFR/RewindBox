"""Reconstruct only the IPA 793 archive writer for the macOS negative control."""

import argparse
import hashlib
from pathlib import Path
import subprocess


HEADER = Path("graphics/nvn/gfx/nvn/pso_archive.h")
SHA256_793 = "190a6474cd36e9300246ad1bcd51aaa8a9d45da77580d5b344563b4343bba678"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_tree", type=Path)
    parser.add_argument("patch_0127", type=Path)
    parser.add_argument("output_tree", type=Path)
    args = parser.parse_args()
    header = args.output_tree / HEADER
    header.parent.mkdir(parents=True)
    # HEAD in the producer is pristine pinned S2Arm. Replay only the writer's
    # own changes before 0127. Later production changes must never enter the
    # counterfactual, even when they also edit this header.
    header.write_bytes(subprocess.check_output(
        ["git", "-C", str(args.source_tree), "show", f"HEAD:{HEADER}"]
    ))
    for patch in sorted(args.patch_0127.parent.glob("*.patch")):
        if patch.name >= args.patch_0127.name:
            break
        if f"+++ b/{HEADER}".encode() not in patch.read_bytes().splitlines():
            continue
        subprocess.run(
            ["git", "apply", "--no-index", f"--include={HEADER}", patch.resolve()],
            cwd=args.output_tree, check=True,
        )
    original = header.read_bytes()
    if hashlib.sha256(original).hexdigest() != SHA256_793:
        raise RuntimeError("Reconstructed writer differs from the pinned IPA 793 header")
    # Pause immediately after a real descriptor add. This hook does not read
    # the thermal tier, control the loop, or change archive writes.
    end = b"else { e = e1; atomic_fetch_add(&g_par_write_failed, 1); } }"
    if original.count(end) != 1:
        raise RuntimeError("The descriptor barrier requires one insertion point")
    header.write_bytes(original.replace(end, end[:-1] + b"RB_ARCHIVE_TEST_AFTER_DESCRIPTOR(it[0]); }"))
    print(f"IPA 793 archive writer SHA-256 {SHA256_793} verified before adding the test barrier")


if __name__ == "__main__":
    main()
