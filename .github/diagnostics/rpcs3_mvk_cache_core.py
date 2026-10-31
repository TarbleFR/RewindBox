#!/usr/bin/env python3
"""Authenticate historical CPU evidence and a separately built MoltenVK candidate.

The twelve CPU/renderer modes keep their original sources and compiler runs.
Only the new complete dependency, actual iOS syntax/compile/link and final
binary are fresh in this route. This never creates an IPA or a release.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/rpcs3-core-diagnostics"
PROOF = OUT / "mvk-cache-core-proof.json"
SOURCE = "a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a"
UPSTREAM = "22f1152783cef1f7e04af7b1c895173e28fd5b03"
PATCH_SHA = "70d694bb3ef812b87b8839e53335376028aa16476893512d012b77ef1952fd79"
RECORD = "docs/evidence/rpcs3-device601-20261030/source-contract.json"
RECORD_SHA = "657aa623d118644888ec9fe588db68882bc61cacc794de26d4cfc2878cfba77d"
VERIFIER = "test/verify_rpcs3_device601_core_archive.py"
VERIFIER_SHA = "1c49cd057592835b4f7be4a58127ee7c45f0a558314b548b306b8d8a9454914c"
HOST = "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm"
HOST_BEFORE = "60f7140fd100aab0fab929864a171a027d05cd2d5b3523a51c471792225bce01"
HOST_AFTER = "d6326d968f3552c5539d48a0933b41d3e61a3e61c0302972ec370e8df5bd3d16"
CODEGEN = {"PPU": "a987639e9f838d1c", "SPU": "477a3fa442d27917"}
GENERATED_HEADER = "rpcs3/git-version.h"
VERSION_GENERATOR = "rpcs3/git-version.cmake"
VERSION_GENERATOR_SHA = "ff5ab78fe7e35c78f4fd7efe49d13e4bd5b85b99ff9070a36f74080f913696f0"
VERSION_GENERATOR_BLOB = "51c41da9d7fe3aed7cffcd49d895a8c11030cd2a"
GENERATED_HEADER_BYTES = b'''// This is a generated file.

#define RPCS3_GIT_VERSION "1-22f11527"
#define RPCS3_GIT_BRANCH "HEAD"
#define RPCS3_GIT_FULL_BRANCH "local_build"

// If you don't want this file to update/recompile, change to 1.
#define RPCS3_GIT_VERSION_NO_UPDATE 0
'''
REFERENCES = {
    "a4-core": (13007148559, 29263531, "b260bb4fa48b72ff889d6e9c4eb061591676b18e12427c0160a44974c9ff2b07"),
    "a4-diagnostics": (13006694440, 152518949, "3663b28d81f196509618a15a8cf18c61b39ac8d582ee800521a96f27f129284e"),
    "original532": (13005716946, 153758703, "14bf88f0c5fb2698b82656932c174886b42778d55c562a38c17f5c1742a4bb74"),
}
INPUTS = [
    ".github/diagnostics/rpcs3_mvk_cache_core.py",
    ".github/diagnostics/rpcs3_mvk_dependency_artifact.py",
    ".github/workflows/rpcs3-mvk-cache-core.yml",
    "build-utils/rpcs3/build_rpcs3_mvk_cache_core.py",
    "build-utils/rpcs3/patches/mvk-cache-core-recipe.patch",
    "build-utils/rpcs3/build_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patch_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patches/moltenvk-1.4.2-deferred-cache.patch",
    "test/rpcs3_mvk_core_protocol_test.py",
    "test/rpcs3_mvk_dependency_artifact_test.py",
    "test/fixtures/rpcs3_git_version_22f11527.cmake",
    VERIFIER,
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(Path(path).read_bytes())


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def command(*argv, cwd=ROOT):
    return subprocess.check_output([str(arg) for arg in argv], cwd=cwd, text=True).strip()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def input_hashes():
    return {name: file_sha(ROOT / name) for name in INPUTS}


def historical_downloads(directory):
    directory.mkdir(parents=True, exist_ok=False)
    paths = {}
    for name, (artifact_id, size, digest) in REFERENCES.items():
        metadata = directory / (name + "-artifact.json")
        archive = directory / (name + ".zip")
        for endpoint, path in [(f"actions/artifacts/{artifact_id}", metadata),
                               (f"actions/artifacts/{artifact_id}/zip", archive)]:
            with path.open("wb") as output:
                subprocess.run(["gh", "api", "repos/TarbleFR/RewindBox/" + endpoint],
                               cwd=ROOT, stdout=output, check=True, timeout=300)
        item = load(metadata)
        require(item["id"] == artifact_id and item["expired"] is False
                and item["size_in_bytes"] == archive.stat().st_size == size
                and item["digest"] == "sha256:" + digest and file_sha(archive) == digest,
                "original Apple artifact differs: " + name)
        paths[name] = {"archive": str(archive), "metadata": str(metadata),
                       "bytes": size, "sha256": digest, "artifact": artifact_id,
                       "metadata_sha256": file_sha(metadata)}
    for name, run in [("a4", 41117115264), ("532", 41113741373)]:
        path = directory / (name + "-run.json")
        with path.open("wb") as output:
            subprocess.run(["gh", "api", f"repos/TarbleFR/RewindBox/actions/runs/{run}"],
                           cwd=ROOT, stdout=output, check=True, timeout=60)
        item = load(path)
        expected_source = SOURCE if name == "a4" else "532ca40efc91730a6770db63879e9db759c7867d"
        require(item["id"] == run and item["head_sha"] == expected_source
                and item["status"] == "completed"
                and item["conclusion"] == ("success" if name == "a4" else "failure"),
                "original run/source/conclusion differs: " + name)
        paths[name + "-run"] = {"path": str(path), "sha256": file_sha(path)}
    return paths


def historical_checkout(destination):
    require(not destination.exists(), "historical verifier workspace already exists")
    subprocess.run(["git", "clone", "--no-checkout", "--shared", "--quiet", str(ROOT), str(destination)], check=True)
    partial = subprocess.run(["git", "config", "--get", "remote.origin.promisor"], cwd=ROOT,
                             capture_output=True, text=True, check=False).stdout.strip() == "true"
    if partial:
        # --shared does not inherit the parent's promisor remote. Restore that
        # metadata so real missing historical blobs are fetched, never invented.
        command("git", "-C", destination, "remote", "set-url", "origin", "https://github.com/TarbleFR/RewindBox.git")
        command("git", "-C", destination, "config", "remote.origin.promisor", "true")
        command("git", "-C", destination, "config", "remote.origin.partialclonefilter", "blob:none")
    subprocess.run(["git", "-C", str(destination), "checkout", "--detach", "--quiet", SOURCE], check=True)
    require(command("git", "rev-parse", "HEAD", cwd=destination) == SOURCE, "wrong historical verifier ROOT")
    command("git", "diff", "--quiet", "HEAD", cwd=destination)
    return {"source": SOURCE, "parent_partial_clone": partial, "tracked_worktree_clean": True}


def reference_verification(source, references, directory):
    """The original verifier sees the original ROOT and 92 original inputs."""
    require(file_sha(ROOT / VERIFIER) == VERIFIER_SHA, "offline verifier changed")
    historical_root = directory / "a4-source"
    checkout = historical_checkout(historical_root)
    # This read-only verifier was added after a4. Its exact bytes are copied,
    # rather than changing its ROOT/global state or weakening its assertions.
    destination = historical_root / VERIFIER
    require(not destination.exists(), "unexpected verifier in original a4 checkout")
    destination.write_bytes((ROOT / VERIFIER).read_bytes())
    require(file_sha(destination) == VERIFIER_SHA, "copied verifier bytes changed")
    report = directory / "reference-verification.json"
    argv = [sys.executable, str(destination), "--archive", references["a4-core"]["archive"],
            "--artifact-metadata", references["a4-core"]["metadata"],
            "--run-metadata", references["a4-run"]["path"], "--source-root", str(source),
            "--diagnostics-archive", references["a4-diagnostics"]["archive"],
            "--diagnostics-metadata", references["a4-diagnostics"]["metadata"],
            "--reused-diagnostics-archive", references["original532"]["archive"], "--report", str(report)]
    try:
        with (directory / "reference-verifier.log").open("wb") as output:
            subprocess.run(argv, cwd=historical_root, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=300)
    finally:
        # This checkout was created solely above in the new owned directory.
        # Preserve receipts and original archives, not a duplicate app repository.
        shutil.rmtree(historical_root)
    result = load(report)
    require(result["passed"] is True and result["verifier_native_compilations"] == 0
            and result["verifier_native_executions"] == 0
            and result["diagnostic_reports_traces_and_captured_inputs_verified"] is True
            and result["original_diagnostics_archive_verified"] is True, "incomplete original archive verification")
    with zipfile.ZipFile(references["a4-core"]["archive"]) as archive:
        identity = json.loads(archive.read("identity.json"))
        original = json.loads(archive.read("runtime592-proof.json"))
    save(directory / "original-a4-identity.json", identity)
    save(directory / "original-a4-runtime-proof.json", original)
    return identity, original, {"historical_root": SOURCE, "copied_verifier_sha256": VERIFIER_SHA,
                                "historical_checkout": checkout,
                                "report": str(report), "report_sha256": file_sha(report),
                                "native_compilations": 0, "native_executions": 0}


def generated_version_header(source, build_log):
    """Bind only the actual pinned generator's exact depth-one detached output."""
    generator, header = source / VERSION_GENERATOR, source / GENERATED_HEADER
    require(generator.is_file() and not generator.is_symlink() and file_sha(generator) == VERSION_GENERATOR_SHA,
            "pinned git-version generator changed")
    require(header.is_file() and not header.is_symlink(), "generated git-version header is missing or a symlink")
    git_context = {
        "head": command("git", "-C", source, "rev-parse", "HEAD"),
        "count": command("git", "-C", source, "rev-list", "HEAD", "--count"),
        "short": command("git", "-C", source, "rev-parse", "--short=8", "HEAD"),
        "branch": command("git", "-C", source, "rev-parse", "--abbrev-ref", "HEAD"),
        "generator_blob": command("git", "-C", source, "rev-parse", "HEAD:" + VERSION_GENERATOR),
    }
    require(git_context == {"head": UPSTREAM, "count": "1", "short": "22f11527", "branch": "HEAD",
                            "generator_blob": VERSION_GENERATOR_BLOB}, "generated version Git context differs")
    data = header.read_bytes()
    require(data == GENERATED_HEADER_BYTES, "generated git-version header differs from the exact pinned output")
    expected = {"RPCS3_GIT_VERSION": "1-22f11527", "RPCS3_GIT_BRANCH": "HEAD",
                "RPCS3_GIT_FULL_BRANCH": "local_build"}
    observed = {}
    for name, value in expected.items():
        values = re.findall(r"^-- " + name + r": ([^\n]*)$", build_log, re.M)
        require(values and all(item == value for item in values), "actual CMake version context differs: " + name)
        observed[name] = values
    return {GENERATED_HEADER: {"sha256": sha(data), "bytes": len(data), "content": data.decode("utf-8"),
                              "category": "generated build input; outside canonical native postimages",
                              "generator": {"path": VERSION_GENERATOR, "sha256": VERSION_GENERATOR_SHA,
                                            "git_blob": VERSION_GENERATOR_BLOB, "upstream_commit": UPSTREAM},
                              "git_context": git_context, "cmake_log_values": observed}}


def postbuild_upstream_dependencies(source, manifest, generated):
    """Preserve the old ordinary-source map; admit one separately verified output."""
    require(set(generated) == {GENERATED_HEADER} and
            generated[GENERATED_HEADER]["sha256"] == sha(GENERATED_HEADER_BYTES)
            and (source / GENERATED_HEADER).read_bytes() == GENERATED_HEADER_BYTES,
            "generated build input scope or bytes changed")
    entries = subprocess.check_output(["git", "-C", str(source), "ls-tree", "-rz", "HEAD"]).split(b"\0")
    ordinary, links, modules = {}, {}, {}
    canonical = set(manifest["files_sha256"])
    for entry in entries:
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        name = raw_name.decode()
        if kind == "commit":
            modules[name] = blob
            continue
        require(kind == "blob", "unexpected upstream tree object")
        if name in canonical:
            continue
        path = source / name
        if mode == "120000":
            require(path.is_symlink(), "missing upstream symlink: " + name)
            raw = os.fsencode(os.readlink(path))
            links[name] = raw.decode()
        else:
            require(path.is_file() and not path.is_symlink(), "ordinary upstream file changed type: " + name)
            raw = path.read_bytes()
        require(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == blob,
                "noncanonical source differs from pinned upstream: " + name)
        ordinary[name] = sha(raw)
    untracked = {name.decode() for name in subprocess.check_output(
        ["git", "-C", str(source), "ls-files", "--others", "-z"]).split(b"\0") if name}
    require(untracked <= canonical | {GENERATED_HEADER},
            "unreviewed postbuild source files: " + repr(sorted(untracked - canonical - {GENERATED_HEADER})))
    return {"files_sha256": ordinary, "symlinks": links, "submodule_commits": modules,
            "submodule_contents_authenticated": False}


def source_closure(source, original_identity, original_proof, generated=None):
    manifest = load(ROOT / "build-utils/rpcs3/canonical-source.json")
    record = load(ROOT / RECORD)
    require(manifest["upstream_commit"] == UPSTREAM and manifest["patch_sha256"] == PATCH_SHA
            and file_sha(ROOT / "build-utils/rpcs3/embedded-core.patch") == PATCH_SHA
            and file_sha(ROOT / RECORD) == RECORD_SHA
            and len(manifest["files_sha256"]) == 326, "canonical native source changed")
    require(command("git", "-C", source, "rev-parse", "HEAD") == UPSTREAM, "wrong native upstream")
    for name, digest in manifest["files_sha256"].items():
        require(sha((source / name).read_bytes().replace(b"\r\n", b"\n")) == digest, "native postimage changed: " + name)
    for name, digest in record["repository_inputs"].items():
        require(file_sha(ROOT / name) == digest, "frozen repository input changed: " + name)
    require(len(record["repository_inputs"]) == 38, "historical follow-up input scope changed")
    sys.path.insert(0, str(ROOT / "test"))
    import neo_swap_core_pin_test as pin
    current = pin.core_input_hashes(ROOT)
    before = original_identity["core_input_sha256"]
    require(len(current) == len(before) == 92 and set(current) == set(before), "Core input scope changed")
    differences = {name for name in current if current[name] != before[name]}
    require(differences == {HOST} and before[HOST] == HOST_BEFORE and current[HOST] == HOST_AFTER,
            "Core inputs differ outside the reviewed bounded host milestones")
    support = module("candidate_upstream_source_support", ROOT / ".github/diagnostics/rpcs3runtime_device597_core.py")
    upstream = (support.upstream_dependencies(source, manifest) if generated is None
                else postbuild_upstream_dependencies(source, manifest, generated))
    require(upstream == original_proof["upstream_dependencies"], "ordinary native/dependency recipe inputs changed")
    exports = sorted((source / "rpcs3/ios/RPCS3IOS.exports").read_text().split())
    require(len(exports) == len(set(exports)) == 88 and exports == original_proof["exported_symbols"], "ABI exports changed")
    return {"native_source_sha256": manifest["files_sha256"], "canonical_patch_sha256": PATCH_SHA,
            "frozen_repository_input_sha256": record["repository_inputs"], "current_core_input_sha256": current,
            "reviewed_host_delta": {HOST: {"before": HOST_BEFORE, "after": HOST_AFTER}},
            "upstream_dependencies": upstream, "exported_symbols": exports, "codegen": CODEGEN}


def reuse_modes(original):
    result = {}
    for name, item in original["tests"].items():
        require(item["passed"] is True, "historical native mode failed")
        origin = item.get("reused_from", {"source": SOURCE, "run": 41117115264})
        result[name] = {"passed": True, "native_executed_now": False,
                        "original_native_origin": origin,
                        "authenticated_via": {"source": SOURCE, "run": 41117115264},
                        "report_sha256": item["report_sha256"],
                        "compile_trace_sha256": item["compile_trace_sha256"]}
    require(len(result) == 12, "historical mode count changed")
    return result


def prepare(source, dependency_run, dependency_source):
    import rpcs3_mvk_dependency_artifact as dependency
    require(not PROOF.exists(), "candidate proof already exists")
    OUT.mkdir(parents=True, exist_ok=True)
    references = historical_downloads(OUT / "mvk-cache-reference")
    identity, original, verification = reference_verification(source, references, OUT / "mvk-cache-reference")
    closure = source_closure(source, identity, original)
    dep = dependency.authenticate(dependency_run, dependency_source, OUT / "mvk-cache-dependency")
    recipe = module("candidate_recipe", ROOT / "build-utils/rpcs3/build_rpcs3_mvk_cache_core.py")
    require(sha(recipe.recipe_bytes()) == recipe.AFTER, "candidate recipe identity changed")
    proof = {"schema": 1, "type": "rpcs3-mvk-deferred-cache-core", "source": command("git", "rev-parse", "HEAD"),
             "source_root": str(source), "input_sha256": input_hashes(), "source_closure": closure,
             "reference_archives": references, "reference_verification": verification,
             "original_identity_path": str(OUT / "mvk-cache-reference/original-a4-identity.json"),
             "original_identity_sha256": file_sha(OUT / "mvk-cache-reference/original-a4-identity.json"),
             "original_proof_path": str(OUT / "mvk-cache-reference/original-a4-runtime-proof.json"),
             "original_proof_sha256": file_sha(OUT / "mvk-cache-reference/original-a4-runtime-proof.json"),
             "dependency": dep, "tests": reuse_modes(original), "native_modes_executed_now": 0,
             "native_modes_reused": 12, "historical_modes_replayed": 0,
             "historical_28_modes_remain_historical": True, "all_reused_modes_authenticated": True,
             "expected_core_compiler": original["host"]["compiler"],
             "physical_device_tested": False, "gameplay_measured": False, "public_release": False,
             "new_ipa": False, "host_application_built": False, "neoswap_host_component_packaged": False}
    save(PROOF, proof)
    verify_package(PROOF)
    print("PASS: original a4/532 archives authenticated; twelve modes reused, zero native modes replayed")


def verify_package(path):
    import rpcs3_mvk_dependency_artifact as dependency
    proof = load(path)
    require(proof["schema"] == 1 and proof["type"] == "rpcs3-mvk-deferred-cache-core"
            and proof["source"] == command("git", "rev-parse", "HEAD")
            and proof["input_sha256"] == input_hashes(), "candidate proof/source inputs changed")
    require(proof["native_modes_executed_now"] == 0 and proof["native_modes_reused"] == 12,
            "historical native tests were relabeled")
    for field in ("original_identity", "original_proof"):
        require(file_sha(proof[field + "_path"]) == proof[field + "_sha256"], "original proof changed")
    reference = proof["reference_verification"]
    require(reference["copied_verifier_sha256"] == VERIFIER_SHA
            and file_sha(reference["report"]) == reference["report_sha256"], "historical verifier binding changed")
    for item in proof["reference_archives"].values():
        if "archive" in item:
            require(file_sha(item["archive"]) == item["sha256"]
                    and file_sha(item["metadata"]) == item["metadata_sha256"], "reference archive changed")
        else:
            require(file_sha(item["path"]) == item["sha256"], "reference run metadata changed")
    dep = proof["dependency"]
    require(set(dep["metadata_paths"]) == set(dep["metadata_sha256"]), "dependency metadata scope changed")
    for name, metadata in dep["metadata_paths"].items():
        require(file_sha(metadata) == dep["metadata_sha256"][name], "dependency metadata changed")
    dependency.validate_run(load(dep["metadata_paths"]["run.json"]), load(dep["metadata_paths"]["jobs.json"]),
                            dep["run"], dep["source"])
    artifact_root = Path(dep["metadata_paths"]["run.json"]).parent
    for label, item in [("ios", dep["artifact"]), ("preflight", dep["preflight"]["artifact"]),
                        ("metal", dep["metal_validation"]["artifact"])]:
        archive = artifact_root / (label + ".zip")
        require(archive.stat().st_size == item["bytes"] and file_sha(archive) == item["sha256"],
                "authenticated dependency artifact bytes changed")
    require(file_sha(artifact_root / "ios-extracted/host-ios.json") == dep["ios_host_receipt_sha256"]
            and file_sha(artifact_root / "preflight-extracted/arm64-source-extracted.json")
            == dep["preflight"]["report_sha256"]
            and file_sha(artifact_root / "metal-extracted/metal-probe/metal-result.json")
            == dep["metal_validation"]["report_sha256"], "dependency host/preflight/Metal receipts changed")
    checked = dependency.verify_package(Path(dep["package_root"]), dep["source"])
    require(checked["library_sha256"] == dep["library_sha256"], "candidate dependency bytes changed")
    if "staged_package_root" in proof:
        staged = dependency.verify_package(Path(proof["staged_package_root"]), dep["source"])
        require(staged["library_sha256"] == dep["library_sha256"], "staged dependency bytes changed")
    require(platform.system() == "Darwin" and platform.machine() == "arm64", "candidate Core build needs Apple ARM64")
    llvm = os.environ.get("HOST_LLVM_ROOT") or command("brew", "--prefix", "llvm@22")
    compiler = command(str(Path(llvm) / "bin/clang++"), "--version").splitlines()[0]
    require(compiler == proof["expected_core_compiler"], "Core compiler differs from the reused native evidence")
    return proof


def verify_reuse(path, source, *, post_build=False):
    proof = verify_package(path)
    identity, original = load(proof["original_identity_path"]), load(proof["original_proof_path"])
    generated = generated_version_header(source, (OUT / "build.log").read_text(errors="replace")) if post_build else None
    require(source_closure(source, identity, original, generated) == proof["source_closure"], "materialized Core source closure changed")
    require(reuse_modes(original) == proof["tests"], "native mode origins changed")
    if post_build:
        proof["generated_build_inputs"] = generated
        save(path, proof)
    print("PASS: exact canonical Core source; twelve historical modes reused, zero native modes executed now")
    return proof


def linked_archive(log, library, build_root=None):
    """Accept a real verbose executed link line, not a generated future command."""
    matches = []
    for line in log.splitlines():
        if "libRPCS3Core.dylib" not in line or " -o " not in line:
            continue
        args = shlex.split(line)
        response_files = {}
        expanded = []
        for arg in args:
            if arg.startswith("@"):
                require(build_root is not None, "actual linker response file needs its build directory")
                path = (Path(build_root) / arg[1:]).resolve()
                require(path.is_relative_to(Path(build_root).resolve()) and path.is_file() and not path.is_symlink(),
                        "linker response file escapes the actual build")
                content = path.read_bytes()
                values = shlex.split(content.decode())
                require(not any(value.startswith("@") for value in values), "nested linker response file is not reviewed")
                response_files[str(path)] = {"bytes": len(content), "sha256": sha(content)}
                expanded.extend(values)
            else:
                expanded.append(arg)
        args = expanded
        if str(library) in args and "-o" in args and any(arg.endswith("libRPCS3Core.dylib") for arg in args):
            require(args.count(str(library)) == 1, "candidate archive occurs twice in the linker arguments")
            matches.append((line, response_files))
    require(len(matches) == 1, "actual Core linker command does not name exactly one candidate static archive")
    line, response_files = matches[0]
    return {"line": line, "line_sha256": sha(line.encode()), "response_files": response_files,
            "library": str(library), "library_sha256": file_sha(library)}


def common_abi_identity(source):
    fields = {
        "neoswap_client_abi": ("NeoSwap.h", "NEOSWAP_ABI"),
        "neoswap_client_stats_abi": ("NeoSwapClientStats.h", "NEOSWAP_CLIENT_STATS_ABI"),
        "neoswap_relay_abi": ("NeoSwapRelay.h", "NEOSWAP_RELAY_ABI"),
        "neoswap_prepared_relay_abi": ("NeoSwapRelay.h", "NEOSWAP_PREPARED_RELAY_ABI"),
        "neoswap_relay_client_stats_abi": ("NeoSwapRelay.h", "NEOSWAP_RELAY_CLIENT_STATS_ABI"),
        "neoswap_storage_abi": ("NeoSwapStorage/StorageABI.h", "NEOSWAP_STORAGE_ABI"),
        "neoswap_source_archive_abi": ("NeoSwapStorage/SourceABI.h", "NEOSWAP_SOURCE_ABI"),
    }
    result = {}
    for key, (name, symbol) in fields.items():
        values = re.findall(r"\b" + symbol + r"\s*=\s*([0-9]+)\b", (source / "rpcs3/ios" / name).read_text())
        require(values == ["1"], "unchanged common ABI constant differs: " + symbol)
        result[key] = 1
    return result


def identity(directory):
    proof = load(PROOF)
    require("compiled_source_root" in proof and "build_root" in proof, "candidate compile did not complete")
    proof = verify_reuse(PROOF, Path(proof["compiled_source_root"]), post_build=True)
    core = directory / "libRPCS3Core.dylib"
    sys.path.insert(0, str(ROOT / "packages/dolphin_internal_bridge/ci"))
    from verify_ipa import macho
    image = macho(core.read_bytes())
    closure = proof["source_closure"]
    require(image["architecture"] == "arm64" and image["platform"] == 2 and image["fileType"] == 6
            and image["minimumOS"] == "16.3.0"
            and image["id"] == "@rpath/libRPCS3Core.dylib"
            and sorted(image["definedSymbols"]) == closure["exported_symbols"], "actual iPhone dylib/ABI differs")
    require(not {"_rbx_mvk_compile_qos_queue", "_rbx_mvk_exec_q_create"} & set(image["undefinedSymbols"]),
            "unresolved Core queue hook")
    require((directory / "RPCS3_IOS_ABI.txt").read_text().strip() == "30"
            and (directory / "RPCS3_SOURCE_COMMIT.txt").read_text().strip() == UPSTREAM, "ABI/upstream receipt differs")
    log = (OUT / "build.log").read_text(errors="replace")
    for kind, expected in CODEGEN.items():
        require(re.findall("NeoStation " + kind + r" codegen identity: ([0-9a-f]{16})", log) == [expected], "codegen changed")
    for marker in ("MoltenVK compile QoS hook linked", "MoltenVK encoding-queue hook linked"):
        require(marker in log, "actual Core hook linkage not observed")
    require("PASS: actual compiler, target, flags and module maps for all " in log
            and " startup units" in log, "actual iOS syntax gate did not pass")
    library = Path(proof.get("staged_package_root", proof["dependency"]["package_root"])) / "MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a"
    link = linked_archive(log, library, Path(proof["build_root"]))
    require(link["library_sha256"] == proof["dependency"]["library_sha256"], "linked dependency hash differs")
    recipe = module("candidate_recipe_identity", ROOT / "build-utils/rpcs3/build_rpcs3_mvk_cache_core.py")
    require(proof["build_recipe"]["candidate_recipe_sha256"] == recipe.AFTER
            and file_sha(OUT / "mvk-cache-core-recipe.sh") == recipe.AFTER, "executed recipe differs")
    item = {"schema_version": 1, "type": "rpcs3-ios-mvk-deferred-cache-candidate",
            "host_commit": proof["source"], "native_source_commit": SOURCE, "source_commit": UPSTREAM,
            "sha256": file_sha(core), "bytes": core.stat().st_size, "abi_version": 30,
            "minimum_os": image["minimumOS"],
            "architectures": ["arm64"], "exported_symbols": closure["exported_symbols"],
            "source_patch_sha256": PATCH_SHA, "native_source_sha256": closure["native_source_sha256"],
            "core_input_sha256": closure["current_core_input_sha256"], "candidate_input_sha256": proof["input_sha256"],
            "codegen": CODEGEN, "build_recipe": proof["build_recipe"], "moltenvk_dependency": proof["dependency"],
            "actual_link": link, "actual_ios_syntax_compile_link_passed": True,
            "generated_build_inputs": proof["generated_build_inputs"],
            "native_modes_executed_now": 0, "native_modes_reused": 12, "tests": proof["tests"],
            "physical_device_tested": False, "gameplay_measured": False, "public_release": False,
            "new_ipa": False, "host_application_built": False, "neoswap_host_component_packaged": False,
            "host_change_requires_full_application_build": True}
    # These fields are source-derived from the already verified unchanged
    # canonical headers; the custom a4 identity omitted the common ABI fields.
    item.update(common_abi_identity(Path(proof["compiled_source_root"])))
    save(directory / "identity.json", item)
    save(OUT / "identity.json", item)
    shutil.copy2(PROOF, directory / PROOF.name)
    print("PASS: actual candidate Core, iOS syntax/compile/link, ABI30/88 exports, preserved guest codegen; no device/FPS result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dependency-run", type=int)
    parser.add_argument("--dependency-source")
    parser.add_argument("--verify-package", type=Path)
    parser.add_argument("--verify-reuse", type=Path)
    parser.add_argument("--write-core-identity", type=Path)
    args = parser.parse_args()
    if args.prepare:
        require(args.source and args.dependency_run and args.dependency_source, "prepare arguments missing")
        prepare(args.source.resolve(), args.dependency_run, args.dependency_source)
    elif args.verify_package:
        verify_package(args.verify_package.resolve())
    elif args.verify_reuse:
        require(args.source, "native source missing")
        verify_reuse(args.verify_reuse.resolve(), args.source.resolve())
    elif args.write_core_identity:
        identity(args.write_core_identity.resolve())
    else:
        parser.error("choose --prepare, --verify-package, --verify-reuse or --write-core-identity")


if __name__ == "__main__":
    main()
