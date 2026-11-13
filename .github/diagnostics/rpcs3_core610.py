#!/usr/bin/env python3
"""Compile one declared RPCS3 iPhone Core build with the authenticated MoltenVK dependency.

The build is declared in build-utils/rpcs3/core-build.json: its number, the
delivered reference Core (committed identity, proof and run receipt, bound by
digest), the canonical delta (patch, postimages, records), the folded record
that is the only change on top of the reference, the expected exports, the
reviewed Core-input drift, the codegen identities, the runtime markers, the
MoltenVK dependency run and the native harness accounting. No per-build value
is written in this file; it keeps its Core 610 path because the frozen recipe
patch (build-utils/rpcs3/patches/core610-recipe.patch) and the driver pins
name it, so every build executes the recipe Core 610 executed.

Generic checks (generated version header, postbuild upstream map, executed
link line, common ABI constants) are those of the delivered gate, imported
unchanged. This route compiles only the Core; it never creates an IPA or a
release, and claims no device or FPS result.
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
SPEC_PATH = ROOT / "build-utils/rpcs3/core-build.json"
GATE_PATH = ".github/diagnostics/rpcs3_core610.py"
OUT = ROOT / "build/rpcs3-core-diagnostics"
# Route file names (not build numbers): the driver writes core610-recipe.sh.
PROOF = OUT / "core610-proof.json"
RECIPE_OUTPUT = OUT / "core610-recipe.sh"
require, sha, file_sha, load, save, command = base.require, base.sha, base.file_sha, base.load, base.save, base.command
HEX40, HEX64 = re.compile(r"[0-9a-f]{40}"), re.compile(r"[0-9a-f]{64}")


def _hex(value, pattern, what):
    require(isinstance(value, str) and pattern.fullmatch(value) is not None, "core build spec: bad " + what)
    return value


def _artifact(item, what):
    require(isinstance(item, dict) and set(item) == {"id", "name", "bytes", "sha256"}
            and type(item["id"]) is int and type(item["bytes"]) is int and isinstance(item["name"], str),
            "core build spec: bad " + what)
    _hex(item["sha256"], HEX64, what + " digest")
    return item


def load_spec(path=SPEC_PATH):
    """Read and check the declared Core build; every caller sees the same validated values."""
    spec = load(path)
    require(spec.get("schema") == 1 and type(spec.get("build")) is int and spec["build"] > 0,
            "core build spec: schema or build number")
    build = spec["build"]
    require(spec["identity_type"] == f"rpcs3-ios-core{build}", "core build spec: identity type must carry the build")
    route = spec["route"]
    require(route["gate"] == GATE_PATH and route["workflow"] == ".github/workflows/rpcs3-core610.yml"
            and route["driver"] == "build-utils/rpcs3/build_rpcs3_core610.py"
            and route["recipe_patch"] == "build-utils/rpcs3/patches/core610-recipe.patch",
            "core build spec: another route")
    markers = route["markers"]
    require(set(markers) == {"core_and_apple", "apple_only"} and markers["core_and_apple"] != markers["apple_only"]
            and all(re.fullmatch(r"\[[a-z0-9-]+\]", m) for m in [*markers.values(), *route["retired_markers"]])
            and not set(markers.values()) & set(route["retired_markers"])
            and not any(a != b and a in b for a in markers.values() for b in markers.values()),
            "core build spec: markers")
    require(_hex(spec["upstream_commit"], HEX40, "upstream") == base.UPSTREAM,
            "core build spec: the imported generic checks pin another upstream")
    require(type(spec["abi_version"]) is int and re.fullmatch(r"\d+\.\d+\.\d+", spec["minimum_os"]),
            "core build spec: ABI or minimum OS")
    canonical = spec["canonical"]
    _hex(canonical["patch_sha256"], HEX64, "canonical patch")
    require(type(canonical["postimages"]) is int and canonical["records"] and len(set(canonical["records"])) == len(canonical["records"]),
            "core build spec: canonical scope")
    reference = spec["reference"]
    require(type(reference["build"]) is int and reference["build"] < build
            and reference["type"] == f"rpcs3-ios-core{reference['build']}", "core build spec: reference build")
    _hex(reference["source"], HEX40, "reference source")
    for key in ("identity_sha256", "proof_sha256", "run_receipt_sha256", "patch_sha256"):
        _hex(reference[key], HEX64, "reference " + key)
    for key in ("run", "attempt", "core_job", "apple_host_test_job", "postimages", "exports"):
        require(type(reference[key]) is int, "core build spec: reference " + key)
    _artifact(reference["artifact"], "reference artifact")
    _artifact(reference["apple_host_tests_artifact"], "reference Apple host test artifact")
    require(reference["artifact"]["name"] == f"RPCS3Core-{reference['build']}-{reference['source']}"
            and reference["apple_host_tests_artifact"]["name"] == f"RPCS3Core-{reference['build']}-apple-host-tests-{reference['source']}",
            "core build spec: reference artifact names")
    delta = spec["delta"]
    require(delta["record"] in canonical["records"], "core build spec: the folded record is not a canonical record")
    _hex(delta["patch_sha256"], HEX64, "folded patch")
    require(type(spec["exports"]) is int and spec["exports"] > reference["exports"], "core build spec: exports")
    inputs = spec["core_inputs"]
    _hex(inputs["host_sha256"], HEX64, "host")
    require(type(inputs["count"]) is int and inputs["host"] == base.HOST
            and inputs["reviewed_drift"] == sorted(set(inputs["reviewed_drift"])) and inputs["host"] in inputs["reviewed_drift"],
            "core build spec: Core inputs")
    require(spec["new_canonical_upstream"] == sorted(set(spec["new_canonical_upstream"])), "core build spec: new upstream files")
    require(set(spec["codegen"]) == {"PPU", "SPU"} and all(re.fullmatch(r"[0-9a-f]{16}", v) for v in spec["codegen"].values()),
            "core build spec: codegen")
    require(spec["runtime_markers"] and all(isinstance(m, str) and m for m in spec["runtime_markers"]),
            "core build spec: runtime markers")
    dependency = spec["moltenvk_dependency"]
    require(type(dependency["run"]) is int and isinstance(dependency["reviewed_host_delta"], bool),
            "core build spec: MoltenVK dependency")
    _hex(dependency["source"], HEX40, "MoltenVK dependency source")
    _hex(dependency["library_sha256"], HEX64, "MoltenVK library")
    # A Core may link a reviewed new MoltenVK build (for instance the in-pass read barrier fence wait); its spec then
    # names the dependency the reference Core linked, which it replaces, and the reason.
    if "replaces" in dependency:
        replaced = dependency["replaces"]
        require(set(replaced) == {"run", "source", "library_sha256", "reason"} and type(replaced["run"]) is int
                and replaced["run"] != dependency["run"] and isinstance(replaced["reason"], str) and replaced["reason"],
                "core build spec: replaced MoltenVK dependency")
        _hex(replaced["source"], HEX40, "replaced MoltenVK dependency source")
        _hex(replaced["library_sha256"], HEX64, "replaced MoltenVK library")
    modes = spec["native_modes"]
    require(modes["reused"] == sorted(set(modes["reused"])) and type(modes["reused_count"]) is int
            and modes["reused_count"] == 2 * len(modes["reused"]) and modes["affected"]
            and not set(modes["reused"]) & set(modes["affected"]), "core build spec: native modes")
    _hex(modes["reuse_audit"]["sha256"], HEX64, "reuse audit evidence")
    apple = spec["apple_host_tests"]
    _hex(apple["baseline"]["source"], HEX40, "Apple baseline source")
    _hex(apple["baseline"]["canonical_patch_sha256"], HEX64, "Apple baseline patch")
    names = [item["name"] for item in apple["rerun"]]
    reused = apple["reused"]
    require(names and len(names) == len(set(names)) and all(item["argv"][:1] == ["python3"] and item["reason"] for item in apple["rerun"])
            and set(reused["reused_commands"]) <= set(reused["commands"]) and len(reused["commands"]) == len(set(reused["commands"])),
            "core build spec: Apple harness accounting")
    for name, item in reused["reused_commands"].items():
        require(item.get("rerun_by_this_build", False) == (name in names), "core build spec: reused or rerun: " + name)
    # Every Apple result of the reference run is either authenticated and reused or run again.
    require(set(reused["commands"]) <= set(reused["reused_commands"]) | set(names),
            "core build spec: a reference Apple result is neither reused nor rerun")
    return spec


SPEC = load_spec()
BUILD = SPEC["build"]
CORE_TYPE = SPEC["identity_type"]
UPSTREAM = SPEC["upstream_commit"]
ABI = SPEC["abi_version"]
PATCH_SHA = SPEC["canonical"]["patch_sha256"]
POSTIMAGES = SPEC["canonical"]["postimages"]
RECORDS = tuple(SPEC["canonical"]["records"])
REFERENCE = SPEC["reference"]
REFERENCE_BUILD = REFERENCE["build"]
DELIVERED_SOURCE = REFERENCE["source"]
DELIVERED = ROOT / REFERENCE["evidence"]
DELIVERED_IDENTITY_SHA = REFERENCE["identity_sha256"]
DELIVERED_PROOF_SHA = REFERENCE["proof_sha256"]
DELIVERED_PATCH_SHA = REFERENCE["patch_sha256"]
HOST = SPEC["core_inputs"]["host"]
HOST_SHA = SPEC["core_inputs"]["host_sha256"]
# Core inputs (test/neo_swap_core_pin_test.py) that may differ from the reference Core.
REVIEWED_CORE_INPUT_DRIFT = set(SPEC["core_inputs"]["reviewed_drift"])
# Ordinary upstream files the delta newly carries as postimages since the reference.
NEW_CANONICAL_UPSTREAM = set(SPEC["new_canonical_upstream"])
# Delivered native modes whose extracted inputs stay byte-identical
# (test/rpcs3_core610_reuse_audit_test.py); the affected harnesses have their own
# Apple ARM64 evidence (apple-host-tests job of the same workflow, rerun or reused).
REUSED_MODES = tuple(SPEC["native_modes"]["reused"])
AFFECTED_MODES = dict(SPEC["native_modes"]["affected"])
CODEGEN = dict(SPEC["codegen"])
RUNTIME_MARKERS = tuple(SPEC["runtime_markers"])
WORKFLOW = SPEC["route"]["workflow"]
INPUTS = [
    GATE_PATH,
    ".github/diagnostics/rpcs3_mvk_cache_core.py",
    ".github/diagnostics/rpcs3_mvk_dependency_artifact.py",
    ".github/diagnostics/rpcs3_core_apple_host.py",
    WORKFLOW,
    "build-utils/rpcs3/core-build.json",
    SPEC["delta"]["manifest"],
    SPEC["delta"]["patch"],
    SPEC["route"]["driver"],
    SPEC["route"]["recipe_patch"],
    "build-utils/rpcs3/build_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patch_moltenvk_deferred_cache.py",
    "build-utils/rpcs3/patches/moltenvk-1.4.2-deferred-cache.patch",
    "build-utils/rpcs3/collect_rpcs3_mvk_unverified_core.py",
    "test/rpcs3_mvk_dependency_artifact_test.py",
    "test/rpcs3_pipeline_cache_milestones_test.py",
    "test/fixtures/rpcs3_git_version_22f11527.cmake",
    "test/rpcs3_core610_reuse_audit_test.py",
    "test/rpcs3_core610_codegen_test.py",
    "test/rpcs3_retroachievements_test.py",
    "test/rpcs3_retroachievements_core_test.cpp",
    "test/rpcs3_retroachievements_policy_test.cpp",
    SPEC["native_modes"]["reuse_audit"]["path"],
]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def input_hashes():
    return {name: file_sha(ROOT / name) for name in INPUTS}


def delivered():
    """The committed reference Core identity and proof, bound by their reviewed digests and run receipt."""
    identity_raw = (DELIVERED / REFERENCE["identity"]).read_bytes()
    proof_raw = (DELIVERED / REFERENCE["proof"]).read_bytes()
    receipt_raw = (DELIVERED / REFERENCE["run_receipt"]).read_bytes()
    require(sha(identity_raw) == DELIVERED_IDENTITY_SHA and sha(proof_raw) == DELIVERED_PROOF_SHA
            and sha(receipt_raw) == REFERENCE["run_receipt_sha256"],
            f"delivered Core {REFERENCE_BUILD} identity, proof or run receipt changed")
    reference_identity, proof, receipt = json.loads(identity_raw), json.loads(proof_raw), json.loads(receipt_raw)
    require(reference_identity["type"] == proof["type"] == REFERENCE["type"]
            and reference_identity["host_commit"] == proof["source"] == DELIVERED_SOURCE
            and reference_identity["source_commit"] == UPSTREAM
            and reference_identity["source_patch_sha256"] == DELIVERED_PATCH_SHA
            and len(reference_identity["native_source_sha256"]) == REFERENCE["postimages"]
            and reference_identity["abi_version"] == ABI and len(reference_identity["exported_symbols"]) == REFERENCE["exports"]
            and reference_identity["codegen"] == CODEGEN
            and reference_identity["sha256"] == REFERENCE["core"]["sha256"]
            and reference_identity["bytes"] == REFERENCE["core"]["bytes"]
            and len(reference_identity["reused_native_modes"]) == SPEC["native_modes"]["reused_count"]
            and set(reference_identity["affected_native_modes"]) == set(AFFECTED_MODES)
            and reference_identity["native_modes_executed_in_core_job"] == 0,
            f"delivered Core {REFERENCE_BUILD} identity differs from its reviewed contract")
    tests = REFERENCE["apple_host_tests_artifact"]
    require(receipt["run"] == REFERENCE["run"] and receipt["attempt"] == REFERENCE["attempt"]
            and receipt["source"] == DELIVERED_SOURCE and receipt["core_job"] == REFERENCE["core_job"]
            and receipt["apple_host_test_job"] == REFERENCE["apple_host_test_job"]
            and receipt["artifact"] == REFERENCE["artifact"]
            and receipt["apple_host_tests"] == {key: tests[key] for key in ("id", "bytes", "sha256")}
            and receipt["core"]["bytes"] == REFERENCE["core"]["bytes"] and receipt["core"]["sha256"] == REFERENCE["core"]["sha256"]
            and receipt["core"]["identity_sha256"] == DELIVERED_IDENTITY_SHA,
            f"delivered Core {REFERENCE_BUILD} run receipt differs from the reviewed reference pins")
    return reference_identity, proof


def folded_delta(manifest, reference_identity):
    """The canonical delta is the reference postimages plus only the declared folded record."""
    declared = SPEC["delta"]
    staged = load(ROOT / declared["manifest"])
    record = manifest[declared["record"]]
    require(record == staged, "canonical record differs from the reviewed staged manifest: " + declared["record"])
    require(record["folded_into_canonical_delta"] is True and record["base_canonical_patch_sha256"] == DELIVERED_PATCH_SHA
            and record["upstream_commit"] == UPSTREAM and record["patch"] == declared["patch"]
            and record["patch_sha256"] == declared["patch_sha256"] == file_sha(ROOT / declared["patch"])
            and record["abi_version"] == ABI and record["abi_version_changed"] is False,
            "folded delta record differs from its reviewed contract")
    reference = reference_identity["native_source_sha256"]
    before, after, new = record["files_before_sha256"], record["files_after_sha256"], record["new_files"]
    require(all(reference.get(name) == digest for name, digest in before.items()) and not set(new) & set(reference)
            and set(after) == set(before) | set(new), "folded delta does not start from the reference postimages")
    require(manifest["files_sha256"] == {**reference, **after},
            f"canonical Core {BUILD} is not the reference Core {REFERENCE_BUILD} plus only the folded delta")
    return {"record": declared["record"], "patch_sha256": record["patch_sha256"],
            "base_canonical_patch_sha256": record["base_canonical_patch_sha256"],
            "files_after_sha256": after, "new_files": new, "exports_added": record["exports_added"]}


def source_closure(source, generated=None):
    reference_identity, original = delivered()
    manifest = load(ROOT / "build-utils/rpcs3/canonical-source.json")
    require(manifest["upstream_commit"] == UPSTREAM and manifest["patch_sha256"] == PATCH_SHA
            and file_sha(ROOT / "build-utils/rpcs3/embedded-core.patch") == PATCH_SHA
            and len(manifest["files_sha256"]) == POSTIMAGES and all(name in manifest for name in RECORDS),
            f"canonical Core {BUILD} source changed")
    delta = folded_delta(manifest, reference_identity)
    require(command("git", "-C", source, "rev-parse", "HEAD") == UPSTREAM, "wrong native upstream")
    for name, digest in manifest["files_sha256"].items():
        require(sha((source / name).read_bytes().replace(b"\r\n", b"\n")) == digest, "native postimage changed: " + name)
    sys.path.insert(0, str(ROOT / "test"))
    import neo_swap_core_pin_test as pin
    current = pin.core_input_hashes(ROOT)
    before = reference_identity["core_input_sha256"]
    require(len(current) == len(before) == SPEC["core_inputs"]["count"] and set(current) == set(before),
            "Core input scope changed")
    drift = {name for name in current if current[name] != before[name]}
    require(drift == REVIEWED_CORE_INPUT_DRIFT and current[HOST] == HOST_SHA,
            f"Core inputs differ outside the reviewed Core {BUILD} delta: " + repr(sorted(drift ^ REVIEWED_CORE_INPUT_DRIFT)))
    if SPEC["moltenvk_dependency"]["reviewed_host_delta"]:
        import rpcs3_mvk_dependency_artifact as dependency
        require(dependency.HOST == HOST and before[HOST] == dependency.HOST_BEFORE and current[HOST] == dependency.HOST_AFTER,
                "Core-input host delta differs from the reviewed MoltenVK host delta")
    support = module("core_upstream_source_support", ROOT / ".github/diagnostics/rpcs3runtime_device597_core.py")
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
    declared = sorted(reference_identity["exported_symbols"] + ["_" + name for name in delta["exports_added"]])
    require(len(exports) == len(set(exports)) == SPEC["exports"] == len(set(declared)) and exports == declared,
            "ABI exports changed")
    return {"native_source_sha256": manifest["files_sha256"], "canonical_patch_sha256": PATCH_SHA,
            "current_core_input_sha256": current,
            "reviewed_core_input_drift": {name: {"delivered": before[name], f"core{BUILD}": current[name]}
                                          for name in sorted(drift)},
            "upstream_dependencies": upstream, "upstream_files_newly_in_delta": sorted(NEW_CANONICAL_UPSTREAM),
            "folded_delta": delta, "exported_symbols": exports, "exports_added": sorted(set(exports) - set(reference_identity["exported_symbols"])),
            "codegen": CODEGEN, "delivered_reference": DELIVERED_SOURCE}


def reused_modes(identity, source=None):
    """The reference's reused delivered modes, still valid only while every extracted input is unchanged."""
    result = {}
    for name, item in identity["reused_native_modes"].items():
        harness = name.rsplit("-", 1)[0].removesuffix("-asan")
        require(harness in REUSED_MODES, "unexpected reused native mode: " + name)
        require(item["passed"] is True and item["native_executed_now"] is False, "reused native mode did not pass")
        result[name] = {"passed": True, "native_executed_now": False, "reused_from_delivered": item["reused_from_delivered"],
                        "carried_by": {"build": REFERENCE_BUILD, "source": DELIVERED_SOURCE,
                                       "identity_sha256": DELIVERED_IDENTITY_SHA},
                        "report_sha256": item["report_sha256"], "compile_trace_sha256": item["compile_trace_sha256"]}
    require(len(result) == SPEC["native_modes"]["reused_count"], "reused native mode count changed")
    evidence = SPEC["native_modes"]["reuse_audit"]
    raw = (ROOT / evidence["path"]).read_bytes()
    require(sha(raw) == evidence["sha256"], "reuse audit evidence changed")
    audit = json.loads(raw)
    for harness in REUSED_MODES:
        require(audit["harnesses"][harness]["delivered_result_reusable"] is True, "reuse audit no longer covers " + harness)
    for harness in AFFECTED_MODES:
        require(audit["harnesses"][harness]["delivered_result_reusable"] is False, "affected harness relabelled: " + harness)
    if source is not None:
        # The audit recorded the reference tree's extracted inputs; the same
        # extractors must give the same bytes on this build's tree.
        extractors = module("core_reuse_audit_extractors", ROOT / "test/rpcs3_core610_reuse_audit_test.py").HARNESSES
        require(set(extractors) == set(audit["harnesses"]), "reuse audit harness scope changed")
        column = f"core{REFERENCE_BUILD}"
        for harness, entry in extractors.items():
            recorded = audit["harnesses"][harness]["inputs"]
            require(set(recorded) == set(entry["inputs"]), "reuse audit input scope changed: " + harness)
            for label, extract in entry["inputs"].items():
                require(sha(extract(source).encode()) == recorded[label][column],
                        f"extracted input changed since Core {REFERENCE_BUILD}: {harness} {label}")
    return result


def compiler():
    llvm = os.environ.get("HOST_LLVM_ROOT") or command("brew", "--prefix", "llvm@22")
    return command(str(Path(llvm) / "bin/clang++"), "--version").splitlines()[0]


def apple_host_test_plan():
    apple = SPEC["apple_host_tests"]
    return {"baseline": apple["baseline"], "deferred": {item["name"]: item["reason"] for item in apple["rerun"]},
            "validation_mode": "build-only", "full_regression_suite_executed": False,
            "reused_from_reference": {"build": REFERENCE_BUILD, "run": REFERENCE["run"], "job": REFERENCE["apple_host_test_job"],
                                      "artifact": REFERENCE["apple_host_tests_artifact"],
                                      "commands": sorted(name for name, item in apple["reused"]["reused_commands"].items()
                                                         if not item.get("rerun_by_this_build"))},
            "executed_in_core_job": 0}


def prepare(source, dependency_run, dependency_source):
    import rpcs3_mvk_dependency_artifact as dependency
    declared = SPEC["moltenvk_dependency"]
    require(dependency_run == declared["run"] and dependency_source == declared["source"],
            "MoltenVK dependency arguments differ from the declared Core build")
    require(not PROOF.exists(), "candidate proof already exists")
    OUT.mkdir(parents=True, exist_ok=True)
    reference_identity, original = delivered()
    closure = source_closure(source)
    dep = dependency.authenticate(dependency_run, dependency_source, OUT / "mvk-cache-dependency",
                                  reviewed_host_delta=declared["reviewed_host_delta"])
    linked = reference_identity["moltenvk_dependency"]
    if "replaces" in declared:
        # The declared replacement: authenticated above from its own run, and the replaced one is the reference's.
        replaced = declared["replaces"]
        require(dep["library_sha256"] == declared["library_sha256"] and dep["run"] == declared["run"]
                and replaced["run"] == linked["run"] and replaced["library_sha256"] == linked["library_sha256"]
                and replaced["source"] == linked["source"],
                f"MoltenVK dependency is not the declared replacement of the one Core {REFERENCE_BUILD} linked")
    else:
        require(dep["library_sha256"] == declared["library_sha256"] == linked["library_sha256"]
                and dep["run"] == linked["run"],
                f"MoltenVK dependency differs from the one Core {REFERENCE_BUILD} linked")
    recipe = module("core_recipe", ROOT / SPEC["route"]["driver"])
    require(sha(recipe.recipe_bytes()) == recipe.AFTER, "candidate recipe identity changed")
    require({"original_recipe_sha256": recipe.BEFORE, "recipe_patch_sha256": recipe.PATCH_SHA,
             "candidate_recipe_sha256": recipe.AFTER} == {key: reference_identity["build_recipe"][key] for key in
                                                          ("original_recipe_sha256", "recipe_patch_sha256", "candidate_recipe_sha256")},
            f"the recipe differs from the one Core {REFERENCE_BUILD} executed")
    core_compiler = compiler()
    proof = {"schema": 1, "type": CORE_TYPE, "build": BUILD, "source": command("git", "rev-parse", "HEAD"),
             "source_root": str(source), "input_sha256": input_hashes(), "build_spec_sha256": file_sha(SPEC_PATH),
             "source_closure": closure,
             "delivered_identity_sha256": DELIVERED_IDENTITY_SHA, "delivered_proof_sha256": DELIVERED_PROOF_SHA,
             "delivered_reference_build": REFERENCE_BUILD,
             "dependency": dep, "reused_native_modes": reused_modes(reference_identity, source),
             "affected_native_modes": AFFECTED_MODES, "native_modes_executed_in_core_job": 0,
             "apple_host_tests": apple_host_test_plan(),
             "core_compiler": core_compiler, "delivered_core_compiler": original["core_compiler"],
             "core_compiler_equals_delivered": core_compiler == original["core_compiler"],
             "physical_device_tested": False, "gameplay_measured": False, "public_release": False,
             "new_ipa": False, "host_application_built": False, "validation_mode": "build-only"}
    save(PROOF, proof)
    verify_package(PROOF)
    print(f"PASS: Core {BUILD} source closure (Core {REFERENCE_BUILD} + {SPEC['delta']['record']}), "
          "reference and MoltenVK dependency authenticated")


def verify_package(path):
    import rpcs3_mvk_dependency_artifact as dependency
    proof = load(path)
    require(proof["schema"] == 1 and proof["type"] == CORE_TYPE and proof["build"] == BUILD
            and proof["source"] == command("git", "rev-parse", "HEAD")
            and proof["input_sha256"] == input_hashes() and proof["build_spec_sha256"] == file_sha(SPEC_PATH),
            "candidate proof/source inputs changed")
    require(proof["native_modes_executed_in_core_job"] == 0
            and len(proof["reused_native_modes"]) == SPEC["native_modes"]["reused_count"],
            "native mode accounting changed")
    require(proof['validation_mode'] == 'build-only' and proof['apple_host_tests'] == apple_host_test_plan(),
            'Core compilation was mislabeled as a regression-suite run')
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
    print(f"PASS: exact canonical Core {BUILD} source; {len(proof['reused_native_modes'])} delivered modes reused, "
          "affected harnesses not executed in this compilation")
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
            and image["minimumOS"] == SPEC["minimum_os"]
            and image["id"] == "@rpath/libRPCS3Core.dylib"
            and sorted(image["definedSymbols"]) == closure["exported_symbols"], "actual iPhone dylib/ABI differs")
    require(not {"_rbx_mvk_compile_qos_queue", "_rbx_mvk_exec_q_create"} & set(image["undefinedSymbols"]),
            "unresolved Core queue hook")
    require((directory / "RPCS3_IOS_ABI.txt").read_text().strip() == str(ABI)
            and (directory / "RPCS3_SOURCE_COMMIT.txt").read_text().strip() == UPSTREAM, "ABI/upstream receipt differs")
    log = (OUT / "build.log").read_text(errors="replace")
    for kind, expected in CODEGEN.items():
        require(re.findall("NeoStation " + kind + r" codegen identity: ([0-9a-f]{16})", log) == [expected], "codegen changed")
    for marker in ("MoltenVK compile QoS hook linked", "MoltenVK encoding-queue hook linked"):
        require(marker in log, "actual Core hook linkage not observed")
    require("PASS: actual compiler, target, flags and module maps for all " in log
            and " startup units" in log, "actual iOS syntax gate did not pass")
    raw = core.read_bytes()
    for marker in RUNTIME_MARKERS:
        require(marker.encode() in raw, f"Core {BUILD} runtime marker absent: " + marker)
    library = Path(proof["staged_package_root"]) / "MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a"
    link = base.linked_archive(log, library, Path(proof["build_root"]))
    require(link["library_sha256"] == proof["dependency"]["library_sha256"], "linked dependency hash differs")
    recipe = module("core_recipe_identity", ROOT / SPEC["route"]["driver"])
    require(proof["build_recipe"]["candidate_recipe_sha256"] == recipe.AFTER
            and file_sha(RECIPE_OUTPUT) == recipe.AFTER, "executed recipe differs")
    item = {"schema_version": 1, "type": CORE_TYPE, "build": BUILD, "host_commit": proof["source"],
            "source_commit": UPSTREAM, "sha256": file_sha(core), "bytes": core.stat().st_size, "abi_version": ABI,
            "minimum_os": image["minimumOS"], "architectures": ["arm64"],
            "exported_symbols": closure["exported_symbols"], "exports_added": closure["exports_added"],
            "source_patch_sha256": PATCH_SHA, "native_source_sha256": closure["native_source_sha256"],
            "folded_delta": closure["folded_delta"],
            "core_input_sha256": closure["current_core_input_sha256"], "candidate_input_sha256": proof["input_sha256"],
            "build_spec_sha256": proof["build_spec_sha256"],
            "codegen": CODEGEN, "build_recipe": proof["build_recipe"], "moltenvk_dependency": proof["dependency"],
            "actual_link": link, "actual_ios_syntax_compile_link_passed": True,
            "generated_build_inputs": proof["generated_build_inputs"],
            "delivered_reference": {"build": REFERENCE_BUILD, "source": DELIVERED_SOURCE,
                                    "identity_sha256": DELIVERED_IDENTITY_SHA, "proof_sha256": DELIVERED_PROOF_SHA},
            "reused_native_modes": proof["reused_native_modes"], "affected_native_modes": proof["affected_native_modes"],
            "apple_host_tests": proof["apple_host_tests"], "validation_mode": proof['validation_mode'],
            "native_modes_executed_in_core_job": 0, "core_compiler": proof["core_compiler"],
            "delivered_core_compiler": proof["delivered_core_compiler"],
            "core_compiler_equals_delivered": proof["core_compiler_equals_delivered"],
            "physical_device_tested": False, "gameplay_measured": False, "public_release": False,
            "new_ipa": False, "host_application_built": False,
            "host_change_requires_full_application_build": True}
    item.update(base.common_abi_identity(Path(proof["compiled_source_root"])))
    save(directory / "identity.json", item)
    save(OUT / "identity.json", item)
    shutil.copy2(PROOF, directory / PROOF.name)
    print(f"PASS: actual Core {BUILD}, iOS syntax/compile/link, ABI{ABI}/{len(closure['exported_symbols'])} exports, "
          "preserved PPU/SPU codegen; no device/FPS result")


def github_outputs():
    """Values the workflow needs before the gate runs (run-name and job names cannot read a file)."""
    baseline = SPEC["apple_host_tests"]["baseline"]
    return {"build": BUILD, "reference_build": REFERENCE_BUILD, "reference_source": DELIVERED_SOURCE,
            "dependency_run": SPEC["moltenvk_dependency"]["run"], "dependency_source": SPEC["moltenvk_dependency"]["source"],
            "apple_baseline_source": baseline["source"], "apple_baseline_short": baseline["source"][:8],
            "apple_baseline_patch_sha256": baseline["canonical_patch_sha256"]}


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
    parser.add_argument("--github-outputs", action="store_true", help="print the declared build values as KEY=VALUE lines")
    args = parser.parse_args()
    if args.prepare:
        require(args.source and args.dependency_run and args.dependency_source, "prepare arguments missing")
        prepare(args.source.resolve(), args.dependency_run, args.dependency_source)
    elif args.check_source_closure:
        require(args.source, "native source missing")
        source = args.source.resolve()
        closure = source_closure(source)
        delivered_identity, _ = delivered()  # never shadow identity() in main()
        print(json.dumps({"build": BUILD, "reference_build": REFERENCE_BUILD,
                          "reviewed_core_input_drift": closure["reviewed_core_input_drift"],
                          "folded_delta": {key: closure["folded_delta"][key] for key in ("record", "patch_sha256", "new_files")},
                          "upstream_files": len(closure["upstream_dependencies"]["files_sha256"]),
                          "reused_native_modes": sorted(reused_modes(delivered_identity, source)),
                          "exports": len(closure["exported_symbols"]), "exports_added": closure["exports_added"]}, indent=2))
    elif args.github_outputs:
        for key, value in github_outputs().items():
            print(f"{key}={value}")
    elif args.verify_package:
        verify_package(args.verify_package.resolve())
    elif args.verify_reuse:
        require(args.source, "native source missing")
        verify_reuse(args.verify_reuse.resolve(), args.source.resolve())
    elif args.write_core_identity:
        identity(args.write_core_identity.resolve())
    else:
        parser.error("choose --prepare, --check-source-closure, --github-outputs, --verify-package, --verify-reuse "
                     "or --write-core-identity")


if __name__ == "__main__":
    main()
