#!/usr/bin/env python3
"""Authenticate the completed Apple MoltenVK candidate run without replaying it.

The returned paths refer to an authenticated, isolated extraction. No Core,
native harness, game or release is built by this module.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "TarbleFR/RewindBox"
WORKFLOW = ".github/workflows/rpcs3-mvk-cache-validation.yml"
PRODUCER = "build-utils/rpcs3/build_moltenvk_deferred_cache.py"
ADAPTER = "build-utils/rpcs3/patch_moltenvk_deferred_cache.py"
PATCH = "build-utils/rpcs3/patches/moltenvk-1.4.2-deferred-cache.patch"
HOST = "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm"
CURRENT_REQUIRED = (
    WORKFLOW, ".github/diagnostics/rpcs3_mvk_cache_host.py",
    PRODUCER, ADAPTER, PATCH, HOST,
    "test/rpcs3_moltenvk_metal_probe.py", "test/native/rpcs3_moltenvk_metal_probe.mm",
    "test/rpcs3_moltenvk_source_producer_test.py", "test/rpcs3_pipeline_cache_milestones_test.py",
)
# The source-extracted C++ runner's report-only metadata may differ. Its tested
# source commit and exact historical input remain bound by verify_host below.
# ExternalRevisions at MoltenVK db66022459ffb663aa2b50f6b018bc2e124f5edf.
DEPENDENCIES = {
    "cereal": "a56bad8bbb770ee266e930c95d37fff2a5be7fea",
    "Vulkan-Headers": "e3b1eec08173d6b825cd3ac88c885a63b621504a",
    "SPIRV-Cross": "6c09849fe88c48eaed08413aa022aaa136a3a057",
    "SPIRV-Tools": "0d6fd73ca73830ccab5fa1f00ed5ed40124e2c55",
    "SPIRV-Headers": "29981f65241605e08b0ede4cfeb999fe3b723c6a",
    "Vulkan-Tools": "8c66b352925cb771f793a4d3220b1321ae0febf1",
    "Volk": "776893306c5d3b22b6185b5d4a258b81d94572bf",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture(*argv):
    return subprocess.check_output([str(a) for a in argv], cwd=ROOT, stderr=subprocess.STDOUT)


def api(endpoint, target):
    with target.open("wb") as stream:
        subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{endpoint}"], cwd=ROOT,
                       stdout=stream, check=True, timeout=300)


def safe_name(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and name and path.parts and not path.is_absolute() and
            "\\" not in name and ".." not in path.parts and
            path.as_posix() == (name[:-1] if name.endswith("/") else name),
            "Unsafe/noncanonical artifact path: " + repr(name))
    return path


def checked_zip(path, metadata, *, run_id, source, label):
    require(metadata["name"] == f"RPCS3-MVK-cache-{label}-{source}", "Wrong dependency artifact name")
    require(metadata["expired"] is False, "Dependency artifact expired")
    origin = metadata["workflow_run"]
    require(origin["id"] == run_id and origin["head_sha"] == source, "Artifact source/run differs")
    require(path.stat().st_size == metadata["size_in_bytes"] and
            metadata["digest"] == "sha256:" + digest(path), "Dependency archive digest/size differs")
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    require(len(names) == len(set(names)), "Duplicate ZIP member")
    for member in archive.infolist():
        safe_name(member.filename)
        mode = (member.external_attr >> 16) & 0xFFFF
        require(not stat.S_ISLNK(mode) and (not stat.S_IFMT(mode) or
                stat.S_ISREG(mode) or stat.S_ISDIR(mode)), "Nonregular ZIP member")
    require(archive.testzip() is None, "Dependency ZIP CRC failure")
    return archive


def extract_checked(archive, target):
    require(not target.is_symlink(), "Extraction root is a symbolic link")
    expected = {item.filename for item in archive.infolist() if not item.is_dir()}
    if target.exists():
        actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
        require(actual == expected and not any(p.is_symlink() for p in target.rglob("*")),
                "Existing extraction differs from authenticated archive")
        for name in expected:
            require((target / name).read_bytes() == archive.read(name), "Extracted bytes differ: " + name)
    else:
        target.mkdir()
        archive.extractall(target)  # Every member was checked before any write.


def validate_run(run, jobs, run_id, source):
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None, "Expected exact dependency source SHA")
    require(run["id"] == run_id and run["head_sha"] == source and run["path"] == WORKFLOW,
            "Dependency workflow/source binding differs")
    require(run["status"] == "completed" and run["conclusion"] == "success",
            "Entire dependency validation run must succeed")
    require(jobs["total_count"] == len(jobs["jobs"]), "Incomplete dependency job metadata")
    table = {job["name"]: job for job in jobs["jobs"]}
    require(len(table) == len(jobs["jobs"]) and set(table) == {"preflight", "ios-dependency", "macos-metal"},
            "Unexpected dependency jobs")
    for job in table.values():
        require(job["run_id"] == run_id and job["head_sha"] == source and
                job["status"] == "completed" and job["conclusion"] == "success",
                "Dependency job did not succeed on the expected source")
    return table


def verify_host(path, phase, run_id, source, run_attempt):
    host = json.loads(path.read_bytes())
    require(host["status"] == "verified_host_and_inputs" and host["phase"] == phase and
            host["source_commit"] == host["requested_source_commit"] == source and
            int(host["run_id"]) == run_id and int(host["run_attempt"]) == run_attempt,
            "Host receipt source/scope differs")
    require(host["uname"]["system"] == "Darwin" and host["uname"]["machine"] == "arm64" and
            host["runner_arch"] == "ARM64" and host["xcode"].startswith("Xcode 16.4\n") and
            host["sdk"] == ("iphoneos" if phase == "ios" else "macosx"), "Wrong Apple host/toolchain")
    require(all(host[k] is False for k in ("physical_iphone_test", "core_built_by_this_job", "ipa_built_by_this_job")),
            "Host receipt exceeds dependency scope")
    expected_inputs = load_module("mvk_host_inputs", ROOT / ".github/diagnostics/rpcs3_mvk_cache_host.py").INPUTS
    require(set(host["input_sha256"]) == set(expected_inputs), "Host input closure incomplete")
    for name, expected in host["input_sha256"].items():
        safe_name(name)
        raw = capture("git", "show", source + ":" + name)
        require(hashlib.sha256(raw).hexdigest() == expected, "Historical dependency input changed: " + name)
    for name in CURRENT_REQUIRED:
        require(host["input_sha256"][name] == digest(ROOT / name), "Current compiled/host input differs: " + name)
    return host


def verify_manifest(root, expected):
    require(isinstance(expected, dict) and expected, "Empty package manifest")
    require(root.is_dir() and not root.is_symlink(), "Package manifest root is not an owned directory")
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Package contains a symbolic link")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(expected), "Package contains missing or extra files")
    for name, entry in expected.items():
        safe_name(name)
        path = root / name
        require(set(entry) == {"bytes", "sha256"} and type(entry["bytes"]) is int and
                path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"],
                "Package file bytes differ: " + name)


def verify_package(package, source_commit):
    """Recheck all consumed bytes, source identities and static archive members."""
    producer = load_module("mvk_source_producer", ROOT / PRODUCER)
    adapter = load_module("mvk_source_adapter", ROOT / ADAPTER)
    require(re.fullmatch(r"[0-9a-f]{40}", source_commit) is not None, "Expected exact dependency source SHA")
    receipt = json.loads((package / "receipt.json").read_bytes())
    require(receipt["status"] == "candidate_dependency_built" and receipt["apple_native_build_executed"] is True and
            receipt["static_only"] is True and receipt["platform"] == "ios" and receipt["configuration"] == "Release",
            "Dependency is not a complete Apple iOS static Release build")
    require(all(receipt[k] is False for k in ("core_built", "ipa_built", "device_tested", "core_dependency_selected")),
            "Dependency receipt exceeds its original scope")
    require(receipt["upstream_commit"] == producer.COMMIT == adapter.UPSTREAM_COMMIT and
            receipt["upstream_tree"] == "efebd918bbe772eead074100c0a18789ad39606d" and
            receipt["candidate_macro"] == producer.MACRO == adapter.BUILD_MACRO + "=1",
            "MoltenVK source pin/macro differs")
    require(receipt["producer_sha256"] == digest(ROOT / PRODUCER) and
            receipt["adapter_sha256"] == digest(ROOT / ADAPTER), "Compiled producer/adapter differs")
    patch = json.loads((package / "source-patch.json").read_bytes())
    require(digest(package / "source-patch.json") == receipt["source_patch_report_sha256"] and
            patch == receipt["source_patch"] and patch["source_postimages"] == adapter.POSTIMAGES and
            patch["patch_sha256"] == digest(ROOT / PATCH) and patch["upstream_commit"] == producer.COMMIT and
            patch["macro"] == adapter.BUILD_MACRO and patch["default_enabled"] is False and
            patch["requires_full_framework_rebuild"] is True, "Compiled source patch differs")
    require(receipt["dependency_pins"] == receipt["verified_dependency_commits"] == DEPENDENCIES,
            "MoltenVK dependency pin closure differs")
    for folder, field in (("MoltenVK", "package_files"), ("Docs", "documentation_files"),
                          ("ThirdPartyLicenses", "dependency_license_files")):
        verify_manifest(package / folder, receipt[field])
    require(digest(package / "LICENSE") == receipt["license_sha256"], "Dependency license differs")
    require({PurePosixPath(name).parts[0] for name in receipt["dependency_license_files"]} == set(DEPENDENCIES),
            "Incomplete dependency licenses")
    require((package / "MoltenVK/include/vulkan/vulkan.h").is_file(), "Missing Vulkan headers")
    command = receipt["planned_build_command"]
    products = next((a.split("=", 1)[1] for a in command if a.startswith("CONFIGURATION_BUILD_DIR=")), None)
    require(products and command == producer.build_command("ios", products), "Unexpected full-source build command")
    records = receipt["commands"]
    require(records and all(item["exit_code"] == 0 for item in records) and
            sum(item["argv"] == command for item in records) == 1, "Incomplete/failed source producer commands")
    logs = set()
    for item in records:
        name = item["log"]
        require(len(safe_name(name).parts) == 1 and name not in logs, "Invalid/duplicate producer log")
        logs.add(name)
        require(digest(package / "logs" / name) == item["log_sha256"], "Producer command log differs")
    require({p.name for p in (package / "logs").iterdir()} == logs, "Extra/missing producer logs")
    expected_files = {"receipt.json", "source-patch.json", "LICENSE"} | {"logs/" + name for name in logs}
    for folder, field in (("MoltenVK", "package_files"), ("Docs", "documentation_files"),
                          ("ThirdPartyLicenses", "dependency_license_files")):
        expected_files.update(folder + "/" + name for name in receipt[field])
    paths = list(package.rglob("*"))
    require(not package.is_symlink() and not any(p.is_symlink() for p in paths) and
            {p.relative_to(package).as_posix() for p in paths if p.is_file()} == expected_files,
            "Unexpected/missing package files or symbolic links")
    library = package / "MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a"
    require(producer.inspect_archive(library, "ios") == receipt["archive_validation"], "iOS archive platform/object scope differs")
    undefined = capture("xcrun", "nm", "-u", library).decode()
    symbols = set(re.findall(r"(?m)^\s*(?:U\s+)?(_[A-Za-z0-9_]+)\s*$", undefined))
    require(producer.HOOKS <= symbols and receipt["required_core_queue_hooks"] == sorted(producer.HOOKS),
            "Source-built archive lost the real Core queue hooks")
    return {"package_root": str(package.resolve()), "library": str(library.resolve()),
            "library_sha256": digest(library), "receipt_path": str((package / "receipt.json").resolve()),
            "receipt_sha256": digest(package / "receipt.json"), "source": source_commit,
            "source_patch_sha256": patch["patch_sha256"], "source_postimages": patch["source_postimages"],
            "producer_sha256": receipt["producer_sha256"], "adapter_sha256": receipt["adapter_sha256"]}


def verify_preflight(root, adapter):
    report = json.loads((root / "arm64-source-extracted.json").read_bytes())
    require(report["upstream_commit"] == adapter.UPSTREAM_COMMIT and report["source_postimages"] == adapter.POSTIMAGES and
            report["patch_sha256"] == digest(ROOT / PATCH), "Preflight tested another source patch")
    require(report["platform"] == "Darwin C++17 source-extracted adapters" and report["host_machine"] == "arm64" and
            report["behavior"] == {"behavioral_cases": 12, "same_entry_threads": 24, "metal_execution": False} and
            report["import_constructor_modes"] == [
                {"macro": 0, "imported_entries": 64, "import_compiles": 64, "variant_compiles": 1},
                {"macro": 1, "imported_entries": 64, "import_compiles": 0, "variant_compiles": 1}] and
            report["sanitizers"] == {"ASan": "passed", "UBSan": "passed", "LeakSanitizer": "not supported on Darwin"} and
            report["patch_contract_cases"] == 4, "Affected Apple adapter tests did not pass")
    require(report["apple_objcxx_build"] == report["real_metal_execution"] == report["iphone_bo2_multiplayer"] == "not_run" and
            report["fps_gain_claimed"] is False, "Adapter report exceeds its scope")
    milestone = (root / "arm64-host-milestones.log").read_text()
    require("PASS: 14 native cache boundaries, independent 16/s cap, notice routing, raw128 budget and 32 concurrent writers" in milestone,
            "Affected host boundary cases did not pass")
    return {"report_sha256": digest(root / "arm64-source-extracted.json"),
            "host_milestones_log_sha256": digest(root / "arm64-host-milestones.log"),
            "behavioral_cases": 12, "patch_contract_cases": 4,
            "native_tests_executed_now": 0, "reused_dependency_validation": True,
            "real_metal_execution_verified_by_this_artifact": False}


def verify_metal(root, adapter):
    probe, package = root / "metal-probe", root / "macos-package"
    receipt = json.loads((probe / "receipt.json").read_bytes())
    result = json.loads((probe / "metal-result.json").read_bytes())
    built = json.loads((package / "receipt.json").read_bytes())
    require(receipt["status"] == result["status"] == "passed" and
            receipt["real_metal_execution"] is result["real_metal_execution"] is True and
            receipt["iphone_tested"] is result["iphone_tested"] is False and
            receipt["fps_gain_claimed"] is result["fps_gain_claimed"] is False, "Metal probe did not pass within its scope")
    require(receipt["host"] == {"system": "Darwin", "machine": "arm64"} and
            receipt["source_sha256"] == digest(ROOT / "test/native/rpcs3_moltenvk_metal_probe.mm") and
            receipt["runner_sha256"] == digest(ROOT / "test/rpcs3_moltenvk_metal_probe.py"), "Metal probe source/host differs")
    require(receipt["metal_result"] == result and receipt["metal_result_sha256"] == digest(probe / "metal-result.json") and
            receipt["binary_sha256"] == digest(probe / "metal-probe") and
            receipt["fixture_sha256"] == digest(probe / "compute.spv"), "Metal probe result/binary/fixture bytes differ")
    require(built["status"] == "candidate_dependency_built" and built["platform"] == "macos" and
            built["configuration"] == "Release" and built["static_only"] is True and built["apple_native_build_executed"] is True and
            built["upstream_commit"] == receipt["upstream_commit"] == adapter.UPSTREAM_COMMIT and
            built["source_patch"]["source_postimages"] == adapter.POSTIMAGES and
            built["source_patch"]["patch_sha256"] == digest(ROOT / PATCH) and
            built["producer_sha256"] == digest(ROOT / PRODUCER) and built["adapter_sha256"] == digest(ROOT / ADAPTER),
            "Metal probe linked another source candidate")
    relative = "static/MoltenVK.xcframework/macos-arm64/libMoltenVK.a"
    require(receipt["package_receipt_sha256"] == digest(package / "receipt.json") and
            receipt["library_sha256"] == digest(package / "MoltenVK" / relative) == built["package_files"][relative]["sha256"],
            "Metal probe library/producer receipt differs")
    require(receipt["probe_environment"] == {"MVK_CONFIG_PERFORMANCE_TRACKING": "1", "MVK_CONFIG_ACTIVITY_PERFORMANCE_LOGGING_STYLE": "0"},
            "Metal probe performance counters were not enabled")
    for item in receipt["commands"]:
        require(item["exit_code"] == 0 and len(safe_name(item["log"]).parts) == 1 and
                digest(probe / item["log"]) == item["log_sha256"], "Metal command/log differs")
    counts = {"seed_library_compiles": 1, "import_library_compiles": 0, "first_demand_library_compiles": 1,
              "concurrent_threads": 8, "concurrent_library_compiles": 1, "concurrent_pipeline_failures": 0,
              "imported_shader_entries": 1}
    require(all(type(result[k]) is int and result[k] == v for k, v in counts.items()), "Metal compile-once/import counters differ")
    return {"report_sha256": digest(probe / "metal-result.json"), "receipt_sha256": digest(probe / "receipt.json"),
            "metal_device": result["metal_device"], "virtualized_metal_device": "Paravirtual" in result["metal_device"],
            "native_tests_executed_now": 0, "real_metal_execution_reused": True, "physical_iphone_tested": False}


def authenticate(run_id, source_commit, output, *, download=True):
    """Fetch exact run artifacts, or recheck an existing authenticated directory."""
    output = Path(output).resolve()
    if download:
        require(not output.exists(), "Dependency output already exists; use a new owned directory")
        output.mkdir(parents=True)
        api(f"actions/runs/{run_id}", output / "run.json")
        api(f"actions/runs/{run_id}/jobs?filter=latest&per_page=100", output / "jobs.json")
        api(f"actions/runs/{run_id}/artifacts?per_page=100", output / "artifacts.json")
    run = json.loads((output / "run.json").read_bytes())
    jobs = validate_run(run, json.loads((output / "jobs.json").read_bytes()), run_id, source_commit)
    artifacts = json.loads((output / "artifacts.json").read_bytes())
    require(artifacts["total_count"] == len(artifacts["artifacts"]), "Incomplete artifact metadata")
    try:
        capture("git", "cat-file", "-e", source_commit + "^{commit}")
    except subprocess.CalledProcessError:
        capture("git", "fetch", "--no-tags", "--depth", "1", "origin", source_commit)
    bindings = {}
    for label in ("preflight", "ios", "metal"):
        matches = [a for a in artifacts["artifacts"] if a["name"] == f"RPCS3-MVK-cache-{label}-{source_commit}"]
        require(len(matches) == 1, "Missing/ambiguous dependency artifact: " + label)
        listed = matches[0]
        metadata_path, archive_path = output / (label + "-artifact.json"), output / (label + ".zip")
        if download:
            api(f"actions/artifacts/{listed['id']}", metadata_path)
            api(f"actions/artifacts/{listed['id']}/zip", archive_path)
        metadata = json.loads(metadata_path.read_bytes())
        require(metadata == listed, "Artifact metadata changed between list/read")
        with checked_zip(archive_path, metadata, run_id=run_id, source=source_commit, label=label) as archive:
            extract_checked(archive, output / (label + "-extracted"))
        root = output / (label + "-extracted")
        phase = {"preflight": "preflight", "ios": "ios", "metal": "macos"}[label]
        host_file = {"preflight": "host-preflight.json", "ios": "host-ios.json", "metal": "host-macos.json"}[label]
        host = verify_host(root / host_file,
                           phase, run_id, source_commit, run["run_attempt"])
        bindings[label] = {"artifact": {"id": metadata["id"], "bytes": archive_path.stat().st_size,
                                         "sha256": digest(archive_path)},
                           "host_receipt_sha256": digest(root / host_file),
                           "source_input_sha256": host["input_sha256"]}
    package = output / "ios-extracted/ios-package"
    result = verify_package(package, source_commit)
    adapter = load_module("mvk_preflight_adapter", ROOT / ADAPTER)
    bindings["preflight"].update(verify_preflight(output / "preflight-extracted", adapter))
    bindings["preflight"].update({"source": source_commit, "run": run_id})
    bindings["metal"].update(verify_metal(output / "metal-extracted", adapter))
    bindings["metal"].update({"source": source_commit, "run": run_id})
    result.update({"run": run_id, "run_attempt": run["run_attempt"],
                   "artifact": bindings["ios"]["artifact"], "preflight": bindings["preflight"],
                   "metal_validation": bindings["metal"],
                   "ios_host_receipt_sha256": bindings["ios"]["host_receipt_sha256"],
                   "source_input_sha256": bindings["ios"]["source_input_sha256"],
                   "jobs": {name: {"id": j["id"], "conclusion": j["conclusion"]} for name, j in jobs.items()},
                   "metadata_paths": {name: str((output / name).resolve()) for name in
                                      ("run.json", "jobs.json", "artifacts.json", "ios-artifact.json", "preflight-artifact.json", "metal-artifact.json")},
                   "metadata_sha256": {name: digest(output / name) for name in
                                       ("run.json", "jobs.json", "artifacts.json", "ios-artifact.json", "preflight-artifact.json", "metal-artifact.json")},
                   "native_tests_executed_now": 0, "physical_device_tested": False, "fps_gain_claimed": False})
    return result
