#!/usr/bin/env python3
"""Emit and run one exact reviewed Core recipe without editing the a4 recipe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "build-utils/build_rpcs3_embedded_core.sh"
PATCH = Path(__file__).with_name("patches") / "mvk-cache-core-recipe.patch"
BEFORE = "ec79fb073908151d8413a201ef61d242078d363eb317395b6c98f01421eb9a5d"
AFTER = "fc6b32a99f6ead9806ccae20401fd8face855b9e2ec8c09a2e213d6601b6d64d"
PATCH_SHA = "2b55e23144fb42496dd311d7ecc82abc4028545bd6cfd7909dbf4756dbae0f9e"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_bytes():
    if digest(ORIGINAL) != BEFORE or digest(PATCH) != PATCH_SHA:
        raise ValueError("frozen Core recipe or reviewed candidate recipe patch changed")
    with tempfile.TemporaryDirectory(prefix="rpcs3-mvk-recipe-") as temporary:
        work = Path(temporary).resolve()
        destination = work / "build-utils/build_rpcs3_embedded_core.sh"
        destination.parent.mkdir()
        destination.write_bytes(ORIGINAL.read_bytes())
        subprocess.run(["git", "apply", "--check", "--unsafe-paths", "--directory", str(work), str(PATCH)],
                       cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "apply", "--unsafe-paths", "--directory", str(work), str(PATCH)],
                       cwd=ROOT, check=True, capture_output=True)
        result = destination.read_bytes()
        if hashlib.sha256(result).hexdigest() != AFTER:
            raise ValueError("candidate Core recipe postimage changed")
        subprocess.run(["bash", "-n", str(destination)], check=True)
    return result


def emit(destination):
    data = recipe_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError("refusing to overwrite an unrelated generated recipe")
    destination.write_bytes(data)
    return {"original_recipe_sha256": BEFORE, "recipe_patch_sha256": PATCH_SHA,
            "candidate_recipe_sha256": AFTER, "frozen_recipe_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--recipe-output", type=Path,
                        default=ROOT / "build/rpcs3-core-diagnostics/mvk-cache-core-recipe.sh")
    parser.add_argument("--materialize-only", action="store_true")
    args = parser.parse_args()
    receipt = emit(args.recipe_output.resolve())
    if args.materialize_only:
        print(json.dumps(receipt))
        return
    if not args.proof or not args.output or not args.work_root:
        parser.error("--proof, --output and --work-root are required for the actual build")
    proof, output, work = args.proof.resolve(), args.output.resolve(), args.work_root.resolve()
    if output.exists() or work.exists() or output == work or output in work.parents or work in output.parents:
        raise ValueError("Core output/work must be separate new dedicated directories")
    gate = ROOT / ".github/diagnostics/rpcs3_mvk_cache_core.py"
    subprocess.run([sys.executable, str(gate), "--verify-package", str(proof)], cwd=ROOT, check=True)
    data = json.loads(proof.read_text())
    # Keep the historical include-root spelling for compiler cache relevance,
    # while copying the whole newly built and authenticated package. No object
    # or dependency from the displaced historical cache is consumed.
    work.mkdir(parents=True)
    staged = work / "moltenvk-1.4.2-compile-qos"
    shutil.copytree(data["dependency"]["package_root"], staged, symlinks=False)
    data["staged_package_root"] = str(staged)
    proof.write_text(json.dumps(data, indent=2) + "\n")
    subprocess.run([sys.executable, str(gate), "--verify-package", str(proof)], cwd=ROOT, check=True)
    env = dict(os.environ, WORK_ROOT=str(work), OUTPUT_DIR=str(output), BUILD_JOBS="3",
               RPCS3_REPOSITORY="https://github.com/XITRIX/rpcs3.git",
               RPCS3_COMMIT="22f1152783cef1f7e04af7b1c895173e28fd5b03", RPCS3_IOS_ABI="30",
               IOS_DEPLOYMENT_TARGET="16.3", MOLTENVK_VERSION="1.4.2",
               FFMPEG_VERSION="8.1.1",
               FFMPEG_SHA256="b6863adde98898f42602017462871b5f6333e65aec803fdd7a6308639c52edf3",
               RPCS3_MVK_CANDIDATE_PROOF=str(proof),
               RPCS3_MVK_CANDIDATE_PACKAGE=str(staged))
    proof.parent.mkdir(parents=True, exist_ok=True)
    (proof.parent / "mvk-cache-core-recipe.json").write_text(json.dumps(receipt, indent=2) + "\n")
    with (proof.parent / "build.log").open("wb") as log:
        # Preserve live compiler/linker output and the exact diagnostic bytes.
        process = subprocess.Popen(["bash", str(args.recipe_output.resolve())], cwd=ROOT, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for block in iter(lambda: process.stdout.read1(65536), b""):
            log.write(block)
            log.flush()
            sys.stdout.buffer.write(block)
            sys.stdout.buffer.flush()
        code = process.wait()
    if code:
        raise RuntimeError(f"candidate Core build failed with exit code {code}; original recipe remains unchanged")
    data["compiled_source_root"] = str(work / "rpcs3")
    data["build_root"] = str(work / "build")
    data["build_recipe"] = receipt
    proof.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
