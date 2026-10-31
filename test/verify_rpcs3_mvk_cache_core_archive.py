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
SOURCE = "a4ae86d085c231e3c5c93f7f72d2eced0f38ec24"
RUN = 41243687649
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


def module(name, path, root=ROOT):
    spec = importlib.util.spec_from_file_location(name, root / path)
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


def loader_value(argument, previous):
    return previous in ("-install_name", "-dylib_install_name", "-rpath") and argument.startswith(
        ("@rpath/", "@loader_path/", "@executable_path/"))


def response_arguments(archive, identity, proof):
    link = identity["actual_link"]
    require(sha(link["line"].encode()) == link["line_sha256"] and link["library_sha256"] == LIBRARY, "Link receipt differs")
    saved = json.loads(archive.read("link-response-manifest.json"))
    require(set(saved) == set(link["response_files"]), "RSP manifest scope differs")
    args, used, members = [], set(), set()
    build = posixpath.normpath(proof["build_root"])
    for argument in shlex.split(link["line"]):
        if not argument.startswith("@") or loader_value(argument, args[-1] if args else None):
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
        require(not any(value.startswith("@") and not loader_value(value, values[index - 1] if index else (args[-1] if args else None))
                        for index, value in enumerate(values)), "Nested RSP is not supported")
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


def generated_header(identity, proof, gate):
    generated = identity["generated_build_inputs"]
    require(generated == proof["generated_build_inputs"] and set(generated) == {gate.GENERATED_HEADER}, "Generated build input scope differs")
    entry = generated[gate.GENERATED_HEADER]
    expected = {"sha256": sha(gate.GENERATED_HEADER_BYTES), "bytes": len(gate.GENERATED_HEADER_BYTES),
                "content": gate.GENERATED_HEADER_BYTES.decode(),
                "category": "generated build input; outside canonical native postimages",
                "generator": {"path": gate.VERSION_GENERATOR, "sha256": gate.VERSION_GENERATOR_SHA,
                              "git_blob": gate.VERSION_GENERATOR_BLOB, "upstream_commit": UPSTREAM},
                "git_context": {"head": UPSTREAM, "count": "1", "short": "22f11527", "branch": "HEAD",
                                "generator_blob": gate.VERSION_GENERATOR_BLOB}}
    require(set(entry) == set(expected) | {"cmake_log_values"} and all(entry[k] == v for k, v in expected.items()),
            "Generated header content/hash/generator/Git context differs")
    values = {"RPCS3_GIT_VERSION": "1-22f11527", "RPCS3_GIT_BRANCH": "HEAD", "RPCS3_GIT_FULL_BRANCH": "local_build"}
    require(set(entry["cmake_log_values"]) == set(values) and all(
            type(entry["cmake_log_values"][k]) is list and entry["cmake_log_values"][k]
            and all(item == v for item in entry["cmake_log_values"][k]) for k, v in values.items()), "Generated CMake version context differs")
    ordinary = proof["source_closure"]["upstream_dependencies"]["files_sha256"]
    require(gate.GENERATED_HEADER not in identity["native_source_sha256"] and gate.GENERATED_HEADER not in ordinary
            and ordinary[gate.VERSION_GENERATOR] == gate.VERSION_GENERATOR_SHA, "Generated input entered the canonical/ordinary source map")


def verify_core(archive, run, *, source_root=ROOT, recovered=False):
    identity = json.loads(archive.read("identity.json"))
    proof = json.loads(archive.read("mvk-cache-core-proof.json"))
    expected_type = "rpcs3-ios-mvk-deferred-cache-offline-recovery" if recovered else "rpcs3-ios-mvk-deferred-cache-candidate"
    require(identity["schema_version"] == proof["schema"] == 1 and identity["type"] == expected_type
            and proof["type"] == "rpcs3-mvk-deferred-cache-core"
            and identity["host_commit"] == proof["source"] == run["head_sha"], "Core source/type differs")
    require(identity["native_source_commit"] == NATIVE and identity["source_commit"] == UPSTREAM
            and identity["source_patch_sha256"] == PATCH and identity["codegen"] == CODEGEN, "Native identity differs")
    manifest = load(source_root / "build-utils/rpcs3/canonical-source.json")
    closure = proof["source_closure"]
    require(manifest["patch_sha256"] == PATCH and manifest["upstream_commit"] == UPSTREAM
            and len(manifest["files_sha256"]) == 326 and closure["canonical_patch_sha256"] == PATCH and closure["codegen"] == CODEGEN
            and identity["native_source_sha256"] == closure["native_source_sha256"] == manifest["files_sha256"], "Native postimage closure differs")
    gate = module("offline_candidate_gate_constants", ".github/diagnostics/rpcs3_mvk_cache_core.py", source_root)
    generated_header(identity, proof, gate)
    inputs = {name: sha((source_root / name).read_bytes()) for name in gate.INPUTS}
    require(identity["candidate_input_sha256"] == proof["input_sha256"] == inputs, "Candidate build inputs differ")
    frozen = load(source_root / "docs/evidence/rpcs3-device601-20261030/source-contract.json")["repository_inputs"]
    require(sha((source_root / gate.RECORD).read_bytes()) == gate.RECORD_SHA and len(frozen) == 38 and closure["frozen_repository_input_sha256"] == frozen
            and all(sha((source_root / name).read_bytes()) == digest for name, digest in frozen.items()), "Frozen Core recipe/test inputs differ")
    require(closure["reviewed_host_delta"] == {gate.HOST: {"before": gate.HOST_BEFORE, "after": gate.HOST_AFTER}}, "Unreviewed host delta")
    pin = module("offline_core_input_hashes", "test/neo_swap_core_pin_test.py", source_root)
    require(identity["core_input_sha256"] == closure["current_core_input_sha256"] == pin.core_input_hashes(source_root), "Core input hashes differ")
    baseline_path = source_root / "docs/evidence/rpcs3-device601-20261030/apple-core/runtime592-proof.json"
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
    recipe = module("offline_candidate_recipe_constants", "build-utils/rpcs3/build_rpcs3_mvk_cache_core.py", source_root)
    require(identity["build_recipe"] == proof["build_recipe"] and identity["build_recipe"]["candidate_recipe_sha256"] == recipe.AFTER
            and identity["build_recipe"]["original_recipe_sha256"] == recipe.BEFORE
            and identity["build_recipe"]["recipe_patch_sha256"] == recipe.PATCH_SHA, "Executed recipe identity differs")
    dependency = identity["moltenvk_dependency"]
    require(dependency == proof["dependency"] and dependency["source"] == DEPENDENCY_SOURCE and dependency["run"] == 41239096061
            and dependency["artifact"] == {"id": 13056518647, "bytes": 5144230,
                "sha256": "833e431b0274002fba4fe36db65219144dedfa5440c7b7c821591c264352da0c"}
            and dependency["library_sha256"] == LIBRARY
            and dependency["source_patch_sha256"] == "f176ffc09bcd1cbae22dcf9be7f4fb62aa7dd4d79e13cc63275978ddaa78b6a1", "Native dependency binding differs")
    bindings = load(source_root / "docs/evidence/rpcs3-bo2-multiplayer-604-20261031/apple-artifact-bindings.json")["artifacts"]
    for label, item in (("preflight", dependency["preflight"]), ("metal", dependency["metal_validation"])):
        expected = next(a for a in bindings if a["name"] == "RPCS3-MVK-cache-" + label + "-" + DEPENDENCY_SOURCE)
        require(item["source"] == DEPENDENCY_SOURCE and item["run"] == 41239096061 and item["artifact"] ==
                {"id": expected["id"], "bytes": expected["size_in_bytes"], "sha256": expected["digest"].removeprefix("sha256:")}, "Dependency evidence artifact differs")
    raw = archive.read("libRPCS3Core.dylib")
    require(raw[:4] == b"\xcf\xfa\xed\xfe" and len(raw) == identity["bytes"] and sha(raw) == identity["sha256"], "Core bytes/hash/thin image differs")
    image = module("offline_macho_reader", "packages/dolphin_internal_bridge/ci/verify_ipa.py", source_root).macho(raw)
    require(image["architecture"] == "arm64" and identity["architectures"] == ["arm64"] and image["platform"] == 2 and image["fileType"] == 6
            and image["minimumOS"] == identity["minimum_os"] == "16.3.0" and image["id"] == "@rpath/libRPCS3Core.dylib"
            and sorted(image["definedSymbols"]) == identity["exported_symbols"] == closure["exported_symbols"] == baseline["exported_symbols"]
            and len(set(image["definedSymbols"])) == len(image["definedSymbols"]) == 88, "Actual Mach-O/exports differ")
    require(not {"_rbx_mvk_compile_qos_queue", "_rbx_mvk_exec_q_create"} & set(image["undefinedSymbols"]), "Unresolved queue hook")
    require(archive.read("RPCS3_IOS_ABI.txt").strip() == b"30" and archive.read("RPCS3_SOURCE_COMMIT.txt").strip().decode() == UPSTREAM
            and archive.read("libRPCS3Core.dylib.sha256").decode().split()[0] == sha(raw), "Core sidecar identity differs")
    required = {"identity.json", "mvk-cache-core-proof.json", "libRPCS3Core.dylib", "RPCS3_IOS_ABI.txt",
                "RPCS3_SOURCE_COMMIT.txt", "libRPCS3Core.dylib.sha256", "link-response-manifest.json"}
    if recovered:
        require(identity["original_ci_conclusion"] == "failure" and identity["metadata_recovered_offline"] is True,
                "Recovery relabeled the original failed CI")
        required |= {"recovery.json", "original-run.json", "original-artifact.json", "original-jobs.json",
                     "original-collector.json", "generated-build-inputs/git-version.h"}
    require({name for name in archive.namelist() if not name.endswith("/")} == required | response_arguments(archive, identity, proof), "Unexpected Core artifact members")
    return identity, proof


def verify_diagnostics(diag, core, identity, proof, *, source_root=ROOT, recovered=False):
    for name in (("mvk-cache-core-proof.json",) if recovered else ("identity.json", "mvk-cache-core-proof.json")):
        require(diag.read(name) == core.read(name), "Core and diagnostic identity/proof differ")
    require(sha(diag.read("mvk-cache-core-recipe.sh")) == identity["build_recipe"]["candidate_recipe_sha256"], "Actual build recipe bytes differ")
    log = diag.read("build.log").decode(errors="replace")
    gate = module("offline_generated_header_constants", ".github/diagnostics/rpcs3_mvk_cache_core.py", source_root)
    for name, values in identity["generated_build_inputs"][gate.GENERATED_HEADER]["cmake_log_values"].items():
        require(re.findall(r"^-- " + name + r": ([^\n]*)$", log, re.M) == values, "Actual generated CMake log context differs")
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
            producer = module("offline_static_archive_inspector", "build-utils/rpcs3/build_moltenvk_deferred_cache.py", source_root)
            with tempfile.TemporaryDirectory(prefix="mvk-core-offline-") as temporary:
                path = Path(temporary) / "libMoltenVK.a"
                path.write_bytes(library)
                require(producer.inspect_archive(path, "ios") == receipt["archive_validation"], "Native archive platform/member scope differs")


def recovery_payloads(diagnostics, artifact_metadata, run_metadata, jobs_metadata, source_root, native_root):
    """Validate one failed run's preserved bytes; construct metadata, never a binary.

    The original gate/proof inputs are read from the explicit old source root.
    Current recovery code is bound separately and never substituted into them.
    """
    run, metadata, jobs = load(run_metadata), load(artifact_metadata), load(jobs_metadata)
    require(run["id"] == RUN and run["head_sha"] == SOURCE and run["run_attempt"] == 1
            and run["path"] == ".github/workflows/rpcs3-mvk-cache-core.yml" and run["status"] == "completed"
            and run["conclusion"] == "failure" and run["repository"]["full_name"] == "TarbleFR/RewindBox", "Wrong original failed run")
    require(metadata["id"] == 13059157171 and metadata["size_in_bytes"] == 51408674 and metadata["digest"] ==
            "sha256:59386bd5fe26c07b1c99b7adc8f0f2b152d16f505fe606d4308c03ecaf9a9cf7", "Wrong preserved diagnostic artifact")
    require(jobs["total_count"] == len(jobs["jobs"]) == 1, "Ambiguous original jobs")
    job = jobs["jobs"][0]
    require(job["id"] == 124662626330 and job["run_id"] == RUN and job["head_sha"] == SOURCE
            and job["run_attempt"] == 1 and job["status"] == "completed" and job["conclusion"] == "failure", "Wrong original failed job")
    expected_steps = {"Compile and link the actual iPhone Core with the new dependency": "success",
                      "Verify the actual binary and bind its new dependency identity": "failure",
                      "Preserve an unverified binary and actual inputs after metadata failure": "success",
                      "Upload the verified Core without an application delivery": "skipped",
                      "Preserve real diagnostics including partial failures": "success"}
    for name, conclusion in expected_steps.items():
        require([s["conclusion"] for s in job["steps"] if s["name"] == name] == [conclusion], "Original job step status differs: " + name)
    with artifact(diagnostics, metadata, "RPCS3Core-MVK-cache-diagnostics-" + SOURCE, run) as diag:
        raw_proof = diag.read("mvk-cache-core-proof.json")
        require(sha(raw_proof) == "382a1ac4f5782122d57181e8b5a15d9fcae02c1c25b5906d10c77fe80e9f8418", "Original proof bytes differ")
        proof = json.loads(raw_proof)
        collector = json.loads(diag.read("unverified-core-manifest.json"))
        require(collector["source_commit"] == SOURCE and collector["run_id"] == str(RUN)
                and collector["prior_job_status"] == "failure" and collector["validation_status"] == "unverified"
                and collector["status"] == "unverified_capture_due_to_job_failure" and collector["full_dist_copied"] is True
                and collector["gate_identity_present"] is False and collector["warnings"] == [], "Original collector scope differs")
        require(all(collector[k] is False for k in ("native_compilation_by_collector", "binary_modified", "verified_core_claimed",
                                                   "device_tested", "fps_gain_claimed")), "Collector promoted unverified bytes")
        require(collector["collector_source_sha256"] == sha((source_root / "build-utils/rpcs3/collect_rpcs3_mvk_unverified_core.py").read_bytes()),
                "Original collector source differs")
        expected_files = {"libRPCS3Core.dylib", "libRPCS3Core.dylib.sha256", "RPCS3_SOURCE_COMMIT.txt", "RPCS3_IOS_ABI.txt"}
        require(set(collector["files"]) == expected_files, "Unexpected original captured binary files")
        payloads = {name: diag.read("unverified-core/" + name) for name in expected_files}
        for name, data in payloads.items():
            require(collector["files"][name] == {"bytes": len(data), "sha256": sha(data)}, "Captured binary sidecar differs")
        raw = payloads["libRPCS3Core.dylib"]
        require(len(raw) == 77422944 and sha(raw) == "f512e6c4a6a2bf3b2ff6f41a2f2e2f6b966240ec2295a35e31f406a36229001f"
                and collector["core"] == collector["files"]["libRPCS3Core.dylib"], "Original compiled binary differs")
        for name, item in collector["captured_build_inputs"].items():
            data = diag.read("captured-build-inputs/" + str(safe(name)))
            require(len(data) == item["bytes"] and sha(data) == item["sha256"], "Captured build input bytes differ")
        header = diag.read("captured-build-inputs/git-version.h")
        gate = module("recovery_original_source_gate", ".github/diagnostics/rpcs3_mvk_cache_core.py", source_root)
        require(header == gate.GENERATED_HEADER_BYTES and sha(header) == proof["generated_build_inputs"][gate.GENERATED_HEADER]["sha256"],
                "Captured generated header differs")
        require(collector["captured_build_inputs"]["git-version.h"]["source_path"] == proof["compiled_source_root"] + "/rpcs3/git-version.h",
                "Captured generated header owner differs")
        closure = proof["source_closure"]
        require(all((native_root / name).is_file() and not (native_root / name).is_symlink()
                    and sha((native_root / name).read_bytes().replace(b"\r\n", b"\n")) == digest
                    for name, digest in closure["native_source_sha256"].items()), "Materialized native postimage differs")
        image = module("recovery_original_macho_reader", "packages/dolphin_internal_bridge/ci/verify_ipa.py", source_root).macho(raw)
        log = diag.read("build.log").decode(errors="replace")
        links = [line for line in log.splitlines() if "libRPCS3Core.dylib" in line and " -o " in line]
        require(len(links) == 1, "Original actual Core link is ambiguous")
        library = proof["staged_package_root"] + "/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a"
        link = {"line": links[0], "line_sha256": sha(links[0].encode()), "response_files": {}, "library": library, "library_sha256": LIBRARY}
        recovery = {"schema": 1, "type": "rpcs3-mvk-cache-metadata-recovery", "status": "verified_offline",
                    "original_source": SOURCE, "original_run": RUN, "original_run_attempt": 1, "original_ci_conclusion": "failure",
                    "original_job": job["id"], "original_artifact": metadata["id"], "original_archive_sha256": metadata["digest"].removeprefix("sha256:"),
                    "original_archive_bytes": metadata["size_in_bytes"], "original_proof_sha256": sha(raw_proof),
                    "original_collector_sha256": sha(diag.read("unverified-core-manifest.json")), "original_build_log_sha256": sha(diag.read("build.log")),
                    "original_run_metadata_sha256": sha(Path(run_metadata).read_bytes()), "original_artifact_metadata_sha256": sha(Path(artifact_metadata).read_bytes()),
                    "original_jobs_metadata_sha256": sha(Path(jobs_metadata).read_bytes()), "captured_generated_header_sha256": sha(header),
                    "captured_generated_header_bytes": len(header), "actual_link_line_sha256": link["line_sha256"],
                    "actual_link_response_files": 0, "captured_other_response_files": collector["captured_response_files"],
                    "core_sha256": sha(raw), "core_bytes": len(raw), "native_canonical_postimages_verified": 326,
                    "native_compilations_by_recovery": 0, "native_executions_by_recovery": 0, "binary_modified": False,
                    "original_proof_modified": False, "new_ci_success_claimed": False, "physical_device_tested": False, "fps_gain_claimed": False,
                    "recovery_tool_sha256": {name: sha((ROOT / name).read_bytes()) for name in
                        ("test/verify_rpcs3_mvk_cache_core_archive.py", "build-utils/rpcs3/finalize_mvk_cache_core_recovery.py")}}
        identity = {"schema_version": 1, "type": "rpcs3-ios-mvk-deferred-cache-offline-recovery", "host_commit": SOURCE,
                    "native_source_commit": NATIVE, "source_commit": UPSTREAM, "sha256": sha(raw), "bytes": len(raw), "abi_version": 30,
                    "minimum_os": image["minimumOS"], "architectures": ["arm64"], "exported_symbols": sorted(image["definedSymbols"]),
                    "source_patch_sha256": PATCH, "native_source_sha256": closure["native_source_sha256"],
                    "core_input_sha256": closure["current_core_input_sha256"], "candidate_input_sha256": proof["input_sha256"], "codegen": CODEGEN,
                    "build_recipe": proof["build_recipe"], "moltenvk_dependency": proof["dependency"], "actual_link": link,
                    "actual_ios_syntax_compile_link_passed": True, "generated_build_inputs": proof["generated_build_inputs"],
                    "native_modes_executed_now": 0, "native_modes_reused": 12, "tests": proof["tests"],
                    "physical_device_tested": False, "gameplay_measured": False, "public_release": False, "new_ipa": False,
                    "host_application_built": False, "neoswap_host_component_packaged": False, "host_change_requires_full_application_build": True,
                    "original_ci_conclusion": "failure", "metadata_recovered_offline": True, **gate.common_abi_identity(native_root)}
        json_bytes = lambda value: (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
        payloads.update({"mvk-cache-core-proof.json": raw_proof, "identity.json": json_bytes(identity), "recovery.json": json_bytes(recovery),
                         "original-run.json": Path(run_metadata).read_bytes(), "original-artifact.json": Path(artifact_metadata).read_bytes(),
                         "original-jobs.json": Path(jobs_metadata).read_bytes(), "original-collector.json": diag.read("unverified-core-manifest.json"),
                         "generated-build-inputs/git-version.h": header, "link-response-manifest.json": b"{}\n"})
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as archive:
            for name, data in payloads.items():
                archive.writestr(name, data)
        with inspect_zip(memory.getvalue()) as core:
            verify_core(core, run, source_root=source_root, recovered=True)
            verify_diagnostics(diag, core, identity, proof, source_root=source_root, recovered=True)
        return payloads, recovery


def verify_recovery(archive, diagnostics, artifact_metadata, run_metadata, jobs_metadata, source_root, native_root):
    payloads, recovery = recovery_payloads(diagnostics, artifact_metadata, run_metadata, jobs_metadata, source_root, native_root)
    with inspect_zip(Path(archive).read_bytes()) as saved:
        require(set(saved.namelist()) == set(payloads) and all(saved.read(name) == data for name, data in payloads.items()),
                "Recovery ZIP differs from independently checked original bytes and new metadata")
    return {"schema": 1, "passed": True, "profile": "offline_metadata_recovery", "source": SOURCE, "run": RUN,
            "original_ci_conclusion": "failure", "original_artifact": recovery["original_artifact"], "core_sha256": recovery["core_sha256"],
            "archive_sha256": sha(Path(archive).read_bytes()), "archive_bytes": Path(archive).stat().st_size,
            "abi_version": 30, "exports": 88, "canonical_postimages": 326, "native_modes_reused": 12,
            "verifier_native_compilations": 0, "verifier_native_executions": 0, "binary_modified": False,
            "original_proof_modified": False, "physical_device_tested": False, "fps_gain_claimed": False,
            "limits": ["The original CI remains failed; this ZIP was finalized and checked offline without another native build.",
                       "No successful Core GitHub artifact is invented. Historical native tests keep their original runs.",
                       "This is not an IPA, iPhone gameplay test, visual recovery or FPS measurement."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "artifact-metadata", "run-metadata"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--diagnostics-archive", type=Path)
    parser.add_argument("--diagnostics-metadata", type=Path)
    parser.add_argument("--recovery-profile", action="store_true", help="verify an offline-finalized ZIP against the original failed diagnostic artifact")
    parser.add_argument("--jobs-metadata", type=Path)
    parser.add_argument("--source-root", type=Path, help="original application source files; required by the recovery profile")
    parser.add_argument("--native-source-root", type=Path, help="materialized canonical native source; required by the recovery profile")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.recovery_profile:
        require(args.diagnostics_archive and args.jobs_metadata and args.source_root and args.native_source_root
                and not args.diagnostics_metadata, "Recovery needs the original diagnostic ZIP/artifact/run/jobs and explicit original source roots")
        result = verify_recovery(args.archive, args.diagnostics_archive, args.artifact_metadata, args.run_metadata,
                                 args.jobs_metadata, args.source_root.resolve(), args.native_source_root.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return
    require(not (args.jobs_metadata or args.source_root or args.native_source_root), "Recovery-only arguments require --recovery-profile")
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
              "generated_header_receipt_verified": True,
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
