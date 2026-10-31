#!/usr/bin/env python3
"""Verify downloaded Core/diagnostic ZIPs offline, without native execution.

GitHub run/artifact metadata are inputs, not fetched here. Without diagnostics,
native dependency provenance remains the successful CI's attestation. Historical
native programs are never compiled/replayed and their raw archives are not reopened.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "6c03067cc766b09c71186240d789a3cb5d69c6c2"
RUN = 41241336642
NATIVE = "a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a"
UPSTREAM = "22f1152783cef1f7e04af7b1c895173e28fd5b03"
PATCH = "70d694bb3ef812b87b8839e53335376028aa16476893512d012b77ef1952fd79"
LIBRARY = "0d711e4ad3610bb176e3c91e727940f7c448a25571158cc1919d633f1d622b1f"
DEPENDENCY_SOURCE = "7aa81cfb0ab749ebfd6c147929ca94751ea3a3ed"
CODEGEN = {"PPU": "a987639e9f838d1c", "SPU": "477a3fa442d27917"}
COMMON_ABI = ("client", "client_stats", "relay", "prepared_relay", "relay_client_stats", "storage", "source_archive")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def safe(name):
    path = PurePosixPath(name)
    require(name and path.parts and not path.is_absolute() and ".." not in path.parts and "\\" not in name
            and ":" not in path.parts[0] and path.as_posix() == (name[:-1] if name.endswith("/") else name), "Unsafe ZIP/member path")
    return path


def inspect_zip(raw):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = archive.namelist()
    require(len(names) == len(set(names)), "Duplicate ZIP members")
    for item in archive.infolist():
        safe(item.filename)
        mode = item.external_attr >> 16
        require(not stat.S_ISLNK(mode) and stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), "Nonregular ZIP member")
    require(archive.testzip() is None, "ZIP CRC failure")
    return archive


def artifact(path, metadata, name, run):
    raw = Path(path).read_bytes()
    require(metadata["name"] == name and metadata["expired"] is False
            and metadata["workflow_run"]["id"] == run["id"]
            and metadata["workflow_run"]["head_sha"] == run["head_sha"], "Artifact name/run/source differs")
    require(metadata["size_in_bytes"] == len(raw) and metadata["digest"] == "sha256:" + sha(raw), "Artifact size/digest differs")
    return inspect_zip(raw)


def response_arguments(archive, identity, proof):
    link = identity["actual_link"]
    require(sha(link["line"].encode()) == link["line_sha256"] and link["library_sha256"] == LIBRARY, "Link receipt differs")
    saved = json.loads(archive.read("link-response-manifest.json"))
    require(set(saved) == set(link["response_files"]), "RSP manifest scope differs")
    args, used, members = [], set(), set()
    build = posixpath.normpath(proof["build_root"])
    for argument in shlex.split(link["line"]):
        if not argument.startswith("@"):
            args.append(argument)
            continue
        original = posixpath.normpath(posixpath.join(build, argument[1:]))
        require(original.startswith(build + "/") and original in saved and original not in used, "Unbound/duplicate RSP")
        used.add(original)
        item = saved[original]
        require({k: item[k] for k in ("bytes", "sha256")} == link["response_files"][original], "RSP receipt differs")
        member = str(safe(item["artifact_path"]))
        require(re.fullmatch(r"link-response/[0-9]{3}\.rsp", member) and member not in members, "Invalid RSP artifact path")
        members.add(member)
        data = archive.read(member)
        require(len(data) == item["bytes"] and sha(data) == item["sha256"], "Actual linker RSP bytes differ")
        values = shlex.split(data.decode())
        require(not any(value.startswith("@") for value in values), "Nested RSP is not supported")
        args.extend(values)
    require(used == set(saved), "Unused linker RSP")
    library = link["library"]
    require(args.count(library) == 1 and args.count("-o") == 1
            and PurePosixPath(args[args.index("-o") + 1]).name == "libRPCS3Core.dylib", "Actual output/library link differs")
    require([a for a in args if "moltenvk" in a.lower() and
             (a.endswith((".a", ".dylib", ".framework")) or a.startswith("-l") or a.lower() == "moltenvk")] == [library],
            "Another MoltenVK library appears in the linker command")
    staged = proof.get("staged_package_root", proof["dependency"]["package_root"])
    require(library == staged + "/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a", "Wrong staged dependency path")
    return members


def verify_core(archive, run):
    identity = json.loads(archive.read("identity.json"))
    proof = json.loads(archive.read("mvk-cache-core-proof.json"))
    require(identity["schema_version"] == proof["schema"] == 1 and identity["type"] == "rpcs3-ios-mvk-deferred-cache-candidate"
            and proof["type"] == "rpcs3-mvk-deferred-cache-core"
            and identity["host_commit"] == proof["source"] == run["head_sha"], "Core source/type differs")
    require(identity["native_source_commit"] == NATIVE and identity["source_commit"] == UPSTREAM
            and identity["source_patch_sha256"] == PATCH and identity["codegen"] == CODEGEN, "Native identity differs")
    manifest = load(ROOT / "build-utils/rpcs3/canonical-source.json")
    closure = proof["source_closure"]
    require(manifest["patch_sha256"] == PATCH and manifest["upstream_commit"] == UPSTREAM
            and len(manifest["files_sha256"]) == 326 and closure["canonical_patch_sha256"] == PATCH and closure["codegen"] == CODEGEN
            and identity["native_source_sha256"] == closure["native_source_sha256"] == manifest["files_sha256"], "Native postimage closure differs")
    gate = module("offline_candidate_gate_constants", ".github/diagnostics/rpcs3_mvk_cache_core.py")
    inputs = {name: sha((ROOT / name).read_bytes()) for name in gate.INPUTS}
    require(identity["candidate_input_sha256"] == proof["input_sha256"] == inputs, "Candidate build inputs differ")
    frozen = load(ROOT / "docs/evidence/rpcs3-device601-20261030/source-contract.json")["repository_inputs"]
    require(sha((ROOT / gate.RECORD).read_bytes()) == gate.RECORD_SHA and len(frozen) == 38 and closure["frozen_repository_input_sha256"] == frozen
            and all(sha((ROOT / name).read_bytes()) == digest for name, digest in frozen.items()), "Frozen Core recipe/test inputs differ")
    require(closure["reviewed_host_delta"] == {gate.HOST: {"before": gate.HOST_BEFORE, "after": gate.HOST_AFTER}}, "Unreviewed host delta")
    pin = module("offline_core_input_hashes", "test/neo_swap_core_pin_test.py")
    require(identity["core_input_sha256"] == closure["current_core_input_sha256"] == pin.core_input_hashes(ROOT), "Core input hashes differ")
    baseline_path = ROOT / "docs/evidence/rpcs3-device601-20261030/apple-core/runtime592-proof.json"
    require(sha(baseline_path.read_bytes()) == "fcc51ecef5ad3b90ca11f1960080459871f70a4e1c0aef8b8079259aa326eb78", "Historical proof snapshot differs")
    baseline = load(baseline_path)
    expected_modes = gate.reuse_modes(baseline)  # Pure transformation; no native commands or archive downloads.
    require(identity["tests"] == proof["tests"] == expected_modes and len(expected_modes) == 12
            and closure["upstream_dependencies"] == baseline["upstream_dependencies"], "Historical native modes/dependencies differ")
    for record in (identity, proof):
        require(record["native_modes_executed_now"] == 0 and record["native_modes_reused"] == 12, "Reused tests relabeled fresh")
        require(all(record[k] is False for k in ("physical_device_tested", "gameplay_measured", "public_release", "new_ipa",
                                                  "host_application_built", "neoswap_host_component_packaged")), "Core scope exceeds evidence")
    require(proof["historical_modes_replayed"] == 0 and proof["all_reused_modes_authenticated"] is True
            and identity["actual_ios_syntax_compile_link_passed"] is True, "Incomplete compile/reuse attestation")
    require(identity["abi_version"] == 30 and all(type(identity["neoswap_" + name + "_abi"]) is int
            and identity["neoswap_" + name + "_abi"] == 1 for name in COMMON_ABI), "Common ABI differs")
    recipe = module("offline_candidate_recipe_constants", "build-utils/rpcs3/build_rpcs3_mvk_cache_core.py")
    require(identity["build_recipe"] == proof["build_recipe"] and identity["build_recipe"]["candidate_recipe_sha256"] == recipe.AFTER
            and identity["build_recipe"]["original_recipe_sha256"] == recipe.BEFORE
            and identity["build_recipe"]["recipe_patch_sha256"] == recipe.PATCH_SHA, "Executed recipe identity differs")
    dependency = identity["moltenvk_dependency"]
    require(dependency == proof["dependency"] and dependency["source"] == DEPENDENCY_SOURCE and dependency["run"] == 41239096061
            and dependency["artifact"] == {"id": 13056518647, "bytes": 5144230,
                "sha256": "833e431b0274002fba4fe36db65219144dedfa5440c7b7c821591c264352da0c"}
            and dependency["library_sha256"] == LIBRARY
            and dependency["source_patch_sha256"] == "f176ffc09bcd1cbae22dcf9be7f4fb62aa7dd4d79e13cc63275978ddaa78b6a1", "Native dependency binding differs")
    bindings = load(ROOT / "docs/evidence/rpcs3-bo2-multiplayer-604-20261031/apple-artifact-bindings.json")["artifacts"]
    for label, item in (("preflight", dependency["preflight"]), ("metal", dependency["metal_validation"])):
        expected = next(a for a in bindings if a["name"] == "RPCS3-MVK-cache-" + label + "-" + DEPENDENCY_SOURCE)
        require(item["source"] == DEPENDENCY_SOURCE and item["run"] == 41239096061 and item["artifact"] ==
                {"id": expected["id"], "bytes": expected["size_in_bytes"], "sha256": expected["digest"].removeprefix("sha256:")}, "Dependency evidence artifact differs")
    raw = archive.read("libRPCS3Core.dylib")
    require(raw[:4] == b"\xcf\xfa\xed\xfe" and len(raw) == identity["bytes"] and sha(raw) == identity["sha256"], "Core bytes/hash/thin image differs")
    image = module("offline_macho_reader", "packages/dolphin_internal_bridge/ci/verify_ipa.py").macho(raw)
    require(image["architecture"] == "arm64" and identity["architectures"] == ["arm64"] and image["platform"] == 2 and image["fileType"] == 6
            and image["minimumOS"] == identity["minimum_os"] == "16.3.0" and image["id"] == "@rpath/libRPCS3Core.dylib"
            and sorted(image["definedSymbols"]) == identity["exported_symbols"] == closure["exported_symbols"] == baseline["exported_symbols"]
            and len(set(image["definedSymbols"])) == len(image["definedSymbols"]) == 88, "Actual Mach-O/exports differ")
    require(not {"_rbx_mvk_compile_qos_queue", "_rbx_mvk_exec_q_create"} & set(image["undefinedSymbols"]), "Unresolved queue hook")
    require(archive.read("RPCS3_IOS_ABI.txt").strip() == b"30" and archive.read("RPCS3_SOURCE_COMMIT.txt").strip().decode() == UPSTREAM
            and archive.read("libRPCS3Core.dylib.sha256").decode().split()[0] == sha(raw), "Core sidecar identity differs")
    required = {"identity.json", "mvk-cache-core-proof.json", "libRPCS3Core.dylib", "RPCS3_IOS_ABI.txt",
                "RPCS3_SOURCE_COMMIT.txt", "libRPCS3Core.dylib.sha256", "link-response-manifest.json"}
    require({name for name in archive.namelist() if not name.endswith("/")} == required | response_arguments(archive, identity, proof), "Unexpected Core artifact members")
    return identity, proof


def verify_diagnostics(diag, core, identity, proof):
    for name in ("identity.json", "mvk-cache-core-proof.json"):
        require(diag.read(name) == core.read(name), "Core and diagnostic identity/proof differ")
    require(sha(diag.read("mvk-cache-core-recipe.sh")) == identity["build_recipe"]["candidate_recipe_sha256"], "Actual build recipe bytes differ")
    log = diag.read("build.log").decode(errors="replace")
    require(log.splitlines().count(identity["actual_link"]["line"]) == 1, "Actual link line is not present exactly once")
    require("PASS: actual compiler, target, flags and module maps for all " in log and " startup units" in log, "Missing actual iOS syntax pass")
    for name, value in CODEGEN.items():
        require(re.findall("NeoStation " + name + r" codegen identity: ([0-9a-f]{16})", log) == [value], "Observed codegen differs")
    for text in ("MoltenVK compile QoS hook linked", "MoltenVK encoding-queue hook linked"):
        require(text in log, "Missing actual Core hook linkage")
    dependency = proof["dependency"]
    for label, expected in (("ios", dependency["artifact"]), ("preflight", dependency["preflight"]["artifact"]),
                            ("metal", dependency["metal_validation"]["artifact"])):
        raw = diag.read("mvk-cache-dependency/" + label + ".zip")
        require(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "Original dependency ZIP bytes differ")
        with inspect_zip(raw) as nested:
            if label != "ios":
                continue
            receipt = json.loads(nested.read("ios-package/receipt.json"))
            require(receipt["status"] == "candidate_dependency_built" and receipt["apple_native_build_executed"] is True
                    and receipt["candidate_macro"] == "RBX_MVK_DEFERRED_CACHE_IMPORT=1"
                    and receipt["source_patch"]["patch_sha256"] == dependency["source_patch_sha256"], "Original source package receipt differs")
            library = nested.read("ios-package/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a")
            require(sha(library) == LIBRARY, "Actual native dependency bytes differ")
            producer = module("offline_static_archive_inspector", "build-utils/rpcs3/build_moltenvk_deferred_cache.py")
            with tempfile.TemporaryDirectory(prefix="mvk-core-offline-") as temporary:
                path = Path(temporary) / "libMoltenVK.a"
                path.write_bytes(library)
                require(producer.inspect_archive(path, "ios") == receipt["archive_validation"], "Native archive platform/member scope differs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "artifact-metadata", "run-metadata"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--diagnostics-archive", type=Path)
    parser.add_argument("--diagnostics-metadata", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(bool(args.diagnostics_archive) == bool(args.diagnostics_metadata), "Both diagnostic ZIP and metadata are required")
    run = load(args.run_metadata)
    require(run["id"] == RUN and run["head_sha"] == SOURCE and run["path"] == ".github/workflows/rpcs3-mvk-cache-core.yml"
            and run["status"] == "completed" and run["conclusion"] == "success" and run["run_attempt"] == 1
            and run["head_branch"] == "Claude" and run["repository"]["full_name"] == "TarbleFR/RewindBox", "Wrong/unsuccessful Core run")
    metadata = load(args.artifact_metadata)
    with artifact(args.archive, metadata, "RPCS3Core-MVK-cache-" + SOURCE, run) as core:
        identity, proof = verify_core(core, run)
        if args.diagnostics_archive:
            with artifact(args.diagnostics_archive, load(args.diagnostics_metadata), "RPCS3Core-MVK-cache-diagnostics-" + SOURCE, run) as diag:
                verify_diagnostics(diag, core, identity, proof)
    result = {"schema": 1, "passed": True, "source": SOURCE, "run": RUN, "artifact": metadata["id"],
              "archive_sha256": metadata["digest"].removeprefix("sha256:"), "core_sha256": identity["sha256"],
              "abi_version": 30, "exports": 88, "canonical_postimages": 326, "codegen": CODEGEN,
              "native_modes_reused": 12, "verifier_native_compilations": 0, "verifier_native_executions": 0,
              "linker_response_bytes_verified": True, "diagnostic_build_and_native_dependency_bytes_verified": bool(args.diagnostics_archive),
              "historical_archive_authentication": "reused CI attestation; original a4/532 ZIPs not reopened here",
              "physical_device_tested": False, "fps_gain_claimed": False,
              "limits": ["Without diagnostics, native dependency provenance is the successful Core CI attestation.",
                         "Mach-O/source receipts and a macOS Metal probe do not establish an iPhone game fix or FPS gain."]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
