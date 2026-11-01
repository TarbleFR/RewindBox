#!/usr/bin/env python3
"""Compile the reviewed Core 610 source lot with the authenticated MoltenVK dependency.

The delivered Core a4ae86d0 (IPA 607/608/609) is the reference: its committed
identity and proof (bound by digest) give the exact 92 Core inputs, the 88
exports, the ordinary upstream dependency map and the reused native modes.
Core 610 may differ only by the reviewed canonical delta (patch a63b9643, 329
postimages) and its pin, and one upstream file that the delta now carries.
The MoltenVK 1.4.2 dependency is the separately authenticated source build
(run 41239096061). Generic checks (generated version header, postbuild
upstream map, executed link line, common ABI constants) are those of the
delivered gate, imported unchanged. This route compiles only the Core; it never
creates an IPA or a release, and claims no device or FPS result.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

import rpcs3_mvk_cache_core as base

ROOT = base.ROOT
OUT = ROOT / "build/rpcs3-core-diagnostics"
PROOF = OUT / "core610-proof.json"
RECIPE_OUTPUT = OUT / "core610-recipe.sh"
UPSTREAM = base.UPSTREAM
PATCH_SHA = "a63b964354acb157f99fa9ba4787e18e19faf2473eb90b5710134bf9a88cdaaf"
POSTIMAGES = 329
RECORD = "core610_20261101"
DELIVERED_SOURCE = "a4ae86d085c231e3c5c93f7f72d2eced0f38ec24"
DELIVERED = ROOT / "docs/evidence/rpcs3-bo2-multiplayer-604-20261031/apple-core/recovered-a4ae86d0"
DELIVERED_IDENTITY_SHA = "01555aa3fc02d32857e711c70d787c528305acbf17246abb80548f202a1f458c"
DELIVERED_PROOF_SHA = "382a1ac4f5782122d57181e8b5a15d9fcae02c1c25b5906d10c77fe80e9f8418"
DELIVERED_PATCH_SHA = base.PATCH_SHA
HOST = base.HOST
HOST_SHA = base.HOST_AFTER
# Core inputs (test/neo_swap_core_pin_test.py) that may differ from a4ae86d0.
REVIEWED_CORE_INPUT_DRIFT = {
    "build-utils/rpcs3/canonical-source.json",
    "build-utils/rpcs3/embedded-core.patch",
    "test/neo_swap_core_pin_test.py",
}
# Ordinary upstream files the Core 610 delta now carries as postimages.
NEW_CANONICAL_UPSTREAM = {"rpcs3/Emu/RSX/VK/VKVertexProgram.cpp"}
# Delivered native modes whose extracted inputs are byte-identical in Core 610
# (test/rpcs3_core610_reuse_audit_test.py); the two affected harnesses run again
# on Apple ARM64 in the apple-host-tests job of the same workflow.
REUSED_MODES = ("color-feedback", "savestate-completion", "tiny-vertex", "vertex-range")
AFFECTED_MODES = {"exitspawn-worker": "test/rpcs3_exitspawn_worker610_test.py (plain and ASan/UBSan)",
                  "mfc-decrementer": "test/rpcs3_spu_mfc_lr_test.py (plain, ASan/UBSan, mutations)"}
CODEGEN = base.CODEGEN
WORKFLOW = ".github/workflows/rpcs3-core610.yml"
INPUTS = [
    ".github/diagnostics/rpcs3_core610.py",
    ".github/diagnostics/rpcs3_mvk_cache_core.py",
    ".github/diagnostics/rpcs3_mvk_dependency_artifact.py",
    WORKFLOW,
    "build-utils/rpcs3/build_rpcs3_core610.py",
    "build-utils/rpcs3/patches/core610-recipe.patch",
    "build-utils/rpcs3/build_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patch_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patches/moltenvk-1.4.2-deferred-cache.patch",
    "build-utils/rpcs3/collect_rpcs3_mvk_unverified_core.py",
    "test/rpcs3_mvk_dependency_artifact_test.py",
    "test/fixtures/rpcs3_git_version_22f11527.cmake",
    "test/rpcs3_core610_reuse_audit_test.py",
    "test/rpcs3_core610_codegen_test.py",
    "docs/evidence/rpcs3-core610-20261101/historical-harnesses/reuse-audit.json",
]
require, sha, file_sha, load, save, command = base.require, base.sha, base.file_sha, base.load, base.save, base.command


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def input_hashes():
    return {name: file_sha(ROOT / name) for name in INPUTS}


def delivered():
    """The committed a4ae86d0 identity and proof, bound by their reviewed digests."""
    identity_raw = (DELIVERED / "identity.json").read_bytes()
    proof_raw = (DELIVERED / "mvk-cache-core-proof.json").read_bytes()
    require(sha(identity_raw) == DELIVERED_IDENTITY_SHA and sha(proof_raw) == DELIVERED_PROOF_SHA,
            "delivered a4ae86d0 identity or proof changed")
    reference_identity, proof = json.loads(identity_raw), json.loads(proof_raw)
    require(reference_identity["host_commit"] == DELIVERED_SOURCE and reference_identity["source_patch_sha256"] == DELIVERED_PATCH_SHA
            and reference_identity["abi_version"] == 30 and len(reference_identity["exported_symbols"]) == 88
            and reference_identity["codegen"] == CODEGEN and len(reference_identity["tests"]) == 12,
            "delivered a4ae86d0 identity differs from its reviewed contract")
    return reference_identity, proof


def source_closure(source, generated=None):
    reference_identity, original = delivered()
    manifest = load(ROOT / "build-utils/rpcs3/canonical-source.json")
    require(manifest["upstream_commit"] == UPSTREAM and manifest["patch_sha256"] == PATCH_SHA
            and file_sha(ROOT / "build-utils/rpcs3/embedded-core.patch") == PATCH_SHA
            and len(manifest["files_sha256"]) == POSTIMAGES and RECORD in manifest,
            "canonical Core 610 source changed")
    require(command("git", "-C", source, "rev-parse", "HEAD") == UPSTREAM, "wrong native upstream")
    for name, digest in manifest["files_sha256"].items():
        require(sha((source / name).read_bytes().replace(b"\r\n", b"\n")) == digest, "native postimage changed: " + name)
    sys.path.insert(0, str(ROOT / "test"))
    import neo_swap_core_pin_test as pin
    current = pin.core_input_hashes(ROOT)
    before = reference_identity["core_input_sha256"]
    require(len(current) == len(before) == 92 and set(current) == set(before), "Core input scope changed")
    drift = {name for name in current if current[name] != before[name]}
    require(drift == REVIEWED_CORE_INPUT_DRIFT and current[HOST] == HOST_SHA,
            "Core inputs differ outside the reviewed Core 610 delta: " + repr(sorted(drift ^ REVIEWED_CORE_INPUT_DRIFT)))
    support = module("core610_upstream_source_support", ROOT / ".github/diagnostics/rpcs3runtime_device597_core.py")
    upstream = (support.upstream_dependencies(source, manifest) if generated is None
                else base.postbuild_upstream_dependencies(source, manifest, generated))
    expected = dict(original["source_closure"]["upstream_dependencies"])
    expected["files_sha256"] = {name: digest for name, digest in expected["files_sha256"].items()
                                if name not in NEW_CANONICAL_UPSTREAM}
    require(set(original["source_closure"]["upstream_dependencies"]["files_sha256"]) - set(expected["files_sha256"])
            == NEW_CANONICAL_UPSTREAM and NEW_CANONICAL_UPSTREAM <= set(manifest["files_sha256"]),
            "reviewed upstream file is not newly carried by the delta")
    require(upstream == expected, "ordinary native/dependency recipe inputs changed")
    exports = sorted((source / "rpcs3/ios/RPCS3IOS.exports").read_text().split())
    require(len(exports) == len(set(exports)) == 88 and exports == reference_identity["exported_symbols"], "ABI exports changed")
    return {"native_source_sha256": manifest["files_sha256"], "canonical_patch_sha256": PATCH_SHA,
            "current_core_input_sha256": current,
            "reviewed_core_input_drift": {name: {"delivered": before[name], "core610": current[name]}
                                          for name in sorted(drift)},
            "upstream_dependencies": upstream, "upstream_files_newly_in_delta": sorted(NEW_CANONICAL_UPSTREAM),
            "exported_symbols": exports, "codegen": CODEGEN, "delivered_reference": DELIVERED_SOURCE}


def reused_modes(identity):
    result = {}
    for name, item in identity["tests"].items():
        harness = name.rsplit("-", 1)[0].removesuffix("-asan")
        if harness in REUSED_MODES:
            require(item["passed"] is True, "reused native mode did not pass")
            result[name] = {"passed": True, "native_executed_now": False, "reused_from_delivered": DELIVERED_SOURCE,
                            "report_sha256": item["report_sha256"],
                            "compile_trace_sha256": item["compile_trace_sha256"]}
    require(len(result) == 8, "reused native mode count changed")
    audit = load(ROOT / "docs/evidence/rpcs3-core610-20261101/historical-harnesses/reuse-audit.json")
    for harness in REUSED_MODES:
        require(audit["harnesses"][harness]["delivered_result_reusable"] is True, "reuse audit no longer covers " + harness)
    for harness in AFFECTED_MODES:
        require(audit["harnesses"][harness]["delivered_result_reusable"] is False, "affected harness relabelled: " + harness)
    return result


def compiler():
    llvm = os.environ.get("HOST_LLVM_ROOT") or command("brew", "--prefix", "llvm@22")
    return command(str(Path(llvm) / "bin/clang++"), "--version").splitlines()[0]


def prepare(source, dependency_run, dependency_source):
    import rpcs3_mvk_dependency_artifact as dependency
    require(not PROOF.exists(), "candidate proof already exists")
    OUT.mkdir(parents=True, exist_ok=True)
    reference_identity, original = delivered()
    closure = source_closure(source)
    dep = dependency.authenticate(dependency_run, dependency_source, OUT / "mvk-cache-dependency")
    recipe = module("core610_recipe", ROOT / "build-utils/rpcs3/build_rpcs3_core610.py")
    require(sha(recipe.recipe_bytes()) == recipe.AFTER, "candidate recipe identity changed")
    proof = {"schema": 1, "type": "rpcs3-ios-core610", "source": command("git", "rev-parse", "HEAD"),
             "source_root": str(source), "input_sha256": input_hashes(), "source_closure": closure,
             "delivered_identity_sha256": DELIVERED_IDENTITY_SHA, "delivered_proof_sha256": DELIVERED_PROOF_SHA,
             "dependency": dep, "reused_native_modes": reused_modes(reference_identity),
             "affected_native_modes": AFFECTED_MODES, "native_modes_executed_in_core_job": 0,
             "core_compiler": compiler(), "delivered_core_compiler": original["expected_core_compiler"],
             "physical_device_tested": False, "gameplay_measured": False, "public_release": False,
             "new_ipa": False, "host_application_built": False}
    save(PROOF, proof)
    verify_package(PROOF)
    print("PASS: Core 610 source closure, a4ae86d0 reference and MoltenVK dependency authenticated")


def verify_package(path):
    import rpcs3_mvk_dependency_artifact as dependency
    proof = load(path)
    require(proof["schema"] == 1 and proof["type"] == "rpcs3-ios-core610"
            and proof["source"] == command("git", "rev-parse", "HEAD")
            and proof["input_sha256"] == input_hashes(), "candidate proof/source inputs changed")
    require(proof["native_modes_executed_in_core_job"] == 0 and len(proof["reused_native_modes"]) == 8,
            "native mode accounting changed")
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
    require(compiler() == proof["core_compiler"], "Core compiler changed during the run")
    return proof


def verify_reuse(path, source, *, post_build=False):
    proof = verify_package(path)
    generated = base.generated_version_header(source, (OUT / "build.log").read_text(errors="replace")) if post_build else None
    require(source_closure(source, generated) == proof["source_closure"], "materialized Core source closure changed")
    if post_build:
        proof["generated_build_inputs"] = generated
        save(path, proof)
    print("PASS: exact canonical Core 610 source; eight delivered modes reused, two affected harnesses run on Apple")
    return proof


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
    raw = core.read_bytes()
    for marker in (b"COREPROF FEEDBACK610", b"COREPROF EXITSPAWN phase=stop_main", b"COREPROF RUNPPU phase=running",
                   b"position_invariance=%d", b"MoltenVK asynchronous submits"):
        require(marker in raw, "Core 610 runtime marker absent: " + marker.decode())
    library = Path(proof["staged_package_root"]) / "MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a"
    link = base.linked_archive(log, library, Path(proof["build_root"]))
    require(link["library_sha256"] == proof["dependency"]["library_sha256"], "linked dependency hash differs")
    recipe = module("core610_recipe_identity", ROOT / "build-utils/rpcs3/build_rpcs3_core610.py")
    require(proof["build_recipe"]["candidate_recipe_sha256"] == recipe.AFTER
            and file_sha(RECIPE_OUTPUT) == recipe.AFTER, "executed recipe differs")
    item = {"schema_version": 1, "type": "rpcs3-ios-core610", "host_commit": proof["source"],
            "source_commit": UPSTREAM, "sha256": file_sha(core), "bytes": core.stat().st_size, "abi_version": 30,
            "minimum_os": image["minimumOS"], "architectures": ["arm64"],
            "exported_symbols": closure["exported_symbols"], "source_patch_sha256": PATCH_SHA,
            "native_source_sha256": closure["native_source_sha256"],
            "core_input_sha256": closure["current_core_input_sha256"], "candidate_input_sha256": proof["input_sha256"],
            "codegen": CODEGEN, "build_recipe": proof["build_recipe"], "moltenvk_dependency": proof["dependency"],
            "actual_link": link, "actual_ios_syntax_compile_link_passed": True,
            "generated_build_inputs": proof["generated_build_inputs"],
            "delivered_reference": {"source": DELIVERED_SOURCE, "identity_sha256": DELIVERED_IDENTITY_SHA,
                                    "proof_sha256": DELIVERED_PROOF_SHA},
            "reused_native_modes": proof["reused_native_modes"], "affected_native_modes": proof["affected_native_modes"],
            "native_modes_executed_in_core_job": 0, "core_compiler": proof["core_compiler"],
            "physical_device_tested": False, "gameplay_measured": False, "public_release": False,
            "new_ipa": False, "host_application_built": False,
            "host_change_requires_full_application_build": True}
    item.update(base.common_abi_identity(Path(proof["compiled_source_root"])))
    save(directory / "identity.json", item)
    save(OUT / "identity.json", item)
    shutil.copy2(PROOF, directory / PROOF.name)
    print("PASS: actual Core 610, iOS syntax/compile/link, ABI30/88 exports, preserved PPU/SPU codegen; no device/FPS result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dependency-run", type=int)
    parser.add_argument("--dependency-source")
    parser.add_argument("--verify-package", type=Path)
    parser.add_argument("--verify-reuse", type=Path)
    parser.add_argument("--write-core-identity", type=Path)
    parser.add_argument("--check-source-closure", action="store_true",
                        help="host-side check of the materialized source against the delivered reference")
    args = parser.parse_args()
    if args.prepare:
        require(args.source and args.dependency_run and args.dependency_source, "prepare arguments missing")
        prepare(args.source.resolve(), args.dependency_run, args.dependency_source)
    elif args.check_source_closure:
        require(args.source, "native source missing")
        closure = source_closure(args.source.resolve())
        delivered_identity, _ = delivered()  # never shadow identity() in main()
        print(json.dumps({"reviewed_core_input_drift": closure["reviewed_core_input_drift"],
                          "upstream_files": len(closure["upstream_dependencies"]["files_sha256"]),
                          "reused_native_modes": sorted(reused_modes(delivered_identity)),
                          "exports": len(closure["exported_symbols"])}, indent=2))
    elif args.verify_package:
        verify_package(args.verify_package.resolve())
    elif args.verify_reuse:
        require(args.source, "native source missing")
        verify_reuse(args.verify_reuse.resolve(), args.source.resolve())
    elif args.write_core_identity:
        identity(args.write_core_identity.resolve())
    else:
        parser.error("choose --prepare, --check-source-closure, --verify-package, --verify-reuse or --write-core-identity")


if __name__ == "__main__":
    main()
