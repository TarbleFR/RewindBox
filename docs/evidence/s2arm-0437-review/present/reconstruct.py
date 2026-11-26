"""Reconstruct the presentation sources from the exact two S2Arm source manifests."""
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile

repository, upstream, out = map(pathlib.Path, sys.argv[1:4])
outputs = ["nvn_mtl.m", "nvn_fi_rule.h", "nvn_present_fi.inc", "rb_present_hold.h", "hle_nvn.c"]
prefix = pathlib.Path("graphics/nvn/gfx/nvn")
files = [str(prefix / name) for name in outputs]
bridge = "packages/s2arm_engine_bridge/ios/Classes"
menu = [f"{bridge}/{name}" for name in ["S2ArmEngineBridgePlugin.m", "S2ArmSessionMenu.m", "S2ArmSettings.m"]]
patches = "build-utils/s2arm/engine/patches"
versions = {"843": "1cb7aa166", "844": "ed9c3c570"}
def git(root, *args):
    return subprocess.check_output(["git", "-C", root, *args])
for label, delivery in versions.items():
    target = out / label
    target.mkdir(parents=True)
    source = json.loads(git(repository, "show", f"{delivery}:build-utils/s2arm/engine-pin.json"))["identity"]["sourceIdentity"]
    for name in menu:
        file = target / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(git(repository, "show", f"{delivery}:{name}"))
    existing = set(git(upstream, "ls-tree", "-r", "--name-only", source["s2arm_commit"], "--", *files).decode().splitlines())
    for name in existing:
        file = target / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(git(upstream, "show", f"{source['s2arm_commit']}:{name}"))
    with tarfile.open(fileobj=io.BytesIO(git(repository, "archive", source["head_sha"], patches))) as archive:
        for entry in source["patches"]:
            patch = archive.extractfile(f"{patches}/{entry['name']}").read()
            if hashlib.sha256(patch).hexdigest() != entry["sha256"]:
                raise ValueError(entry["name"])
            if any(name.encode() in patch for name in files):
                subprocess.run(["git", "apply", "--no-index", "--whitespace=nowarn", *[f"--include={name}" for name in files]], cwd=target, input=patch, check=True)
    print(label, "engine", source["head_sha"], "upstream", source["s2arm_commit"], "patches", len(source["patches"]), flush=True)
