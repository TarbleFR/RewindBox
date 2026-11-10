#!/usr/bin/env python3
"""Verify the 593 JIT I/O follow-up using real CMake, without a Core build.

Inputs are an exact delivered baseline, its canonical manifest, current source,
the pinned RPCS3 upstream tree metadata and the repository's unchanged LLVM patch.
No old CELL538 Git tree, network request, C++ compilation or historical suite is
used. The LLVM backend digest is deliberately reused from the authenticated
baseline manifest after checking the current LLVM pin and patch identity.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


JIT_PATH = "Utilities/JITLLVM.cpp"
JIT_SOURCE = "../../Utilities/JITLLVM.cpp"
CMAKE_PATH = "rpcs3/Emu/CMakeLists.txt"
COMPAT_PATH = "rpcs3/Emu/CPU/JITCacheCompatibility.cmake"
BACKEND_SOURCE = "../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp"
BACKEND_PATH = "3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp"
EXPECTED_IDS = {"PPU": "a987639e9f838d1c", "SPU": "d070cb361bdef607"}
UPSTREAM_COMMIT = "22f1152783cef1f7e04af7b1c895173e28fd5b03"
REVIEWED_JIT = "772636dc0bd451e1c580a677a5450647f0727b16d6105d9f304d8aee9b0112bf"
DELIVERED_JIT = "6dc91ec7e52f504b7af42302d90c286a922575f3d81070ef29732d9671fa828d"
COMPATIBLE_JIT = "001be95de7767a086647076009cdd9a2d92bf0b82d64a6560f2b06f13111bbdf"
IO_METHODS = [
    ("ObjectCache::load", "static std::unique_ptr<llvm::MemoryBuffer> load(const std::string& path, jit_phase::phase read_phase = jit_phase::ppu_cache_read)"),
    ("ObjectCache::getObject", "std::unique_ptr<llvm::MemoryBuffer> getObject(const llvm::Module* _module) override"),
    ("jit_compiler::load_cached_object", "jit_cached_object jit_compiler::load_cached_object(const std::string& path, const std::string& required_symbol)"),
]
UNCHANGED_METHODS = [
    ("ObjectCache::validate", "static bool validate(const llvm::MemoryBuffer& buffer, std::string_view required_symbol)"),
    ("ObjectCache::notifyObjectCompiled", "void notifyObjectCompiled(const llvm::Module* _module, llvm::MemoryBufferRef obj) override"),
    ("jit_compiler::add(module,path)", "void jit_compiler::add(std::unique_ptr<llvm::Module> _module, const std::string& path)"),
    ("jit_compiler::try_add(module,path)", "bool jit_compiler::try_add(std::unique_ptr<llvm::Module> _module, const std::string& path, std::string& error)"),
    ("jit_compiler::add(module)", "void jit_compiler::add(std::unique_ptr<llvm::Module> _module)"),
    ("jit_compiler::try_add(module)", "bool jit_compiler::try_add(std::unique_ptr<llvm::Module> _module, std::string& error)"),
    ("jit_compiler::add(path)", "bool jit_compiler::add(const std::string& path)"),
]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def cmake_quote(value):
    value = str(value)
    check("]==]" not in value, "CMake bracket delimiter in path/value")
    return "[==[" + value + "]==]"


def extract_block(text, kind):
    marker = f'    set(NEOSTATION_{kind}_CODEGEN_DIGEST "")'
    check(text.count(marker) == 1, f"Ambiguous {kind} CMake digest block")
    at = text.index(marker)
    begin = text.rfind('\nif(RPCS3_FRONTEND STREQUAL "IOS")\n', 0, at)
    check(begin >= 0, f"No enclosing iOS block for {kind}")
    begin += 1
    end = text.index("\nendif()", at) + len("\nendif()")
    return text[begin:end] + "\n"


def extract_names(block, kind):
    found = re.findall(r"foreach\(NEOSTATION_" + kind + r"_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)", block, re.S)
    check(len(found) == 1, f"Ambiguous {kind} input list")
    names = found[0].split()
    check(len(names) == len(set(names)), f"Repeated {kind} codegen input")
    check(names.count(BACKEND_SOURCE) == 1 and names.count(JIT_SOURCE) == 1, f"Missing reviewed inputs in {kind}")
    return names


def alias_table(text):
    pattern = (
        r'(?:if|elseif)\(source STREQUAL "([^"]+)" AND\s+'
        r'actual STREQUAL "([0-9a-f]{64})"\)\s+'
        r'set\(\$\{output\} "([0-9a-f]{64})" PARENT_SCOPE\)'
    )
    entries = re.findall(pattern, text)
    check(len(entries) == 4, "Expected exactly four reviewed compatibility aliases")
    check(len({(path, actual) for path, actual, _ in entries}) == 4, "Duplicate alias")
    return {(path, actual): mapped for path, actual, mapped in entries}


def code_without_comments(text):
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def body_span(text, signature):
    check(text.count(signature) == 1, f"Ambiguous method: {signature}")
    signature_at = text.index(signature)
    start = text.index("{", signature_at + len(signature))
    depth = 0
    state = "code"
    i = start
    while i < len(text):
        c = text[i]
        n = text[i:i+2]
        if state == "line_comment":
            if c == "\n": state = "code"
        elif state == "block_comment":
            if n == "*/": state = "code"; i += 1
        elif state in ('"', "'"):
            if c == "\\": i += 1
            elif c == state: state = "code"
        else:
            if n == "//": state = "line_comment"; i += 1
            elif n == "/*": state = "block_comment"; i += 1
            elif c in ('"', "'"): state = c
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0: return start, i + 1, signature_at
        i += 1
    raise ValueError(f"Unbalanced method body: {signature}")


def prove_io_only(before, after):
    check("\r" not in before and "\r" not in after, "Expected exact LF sources")
    normalized = []
    spans = []
    for text in (before, after):
        entries = []
        for label, signature in IO_METHODS:
            start, end, declaration = body_span(text, signature)
            entries.append((start, end, label, declaration))
        entries.sort()
        check(all(entries[i][1] <= entries[i+1][0] for i in range(len(entries)-1)), "Overlapping method spans")
        result = text
        for start, end, label, _ in reversed(entries):
            result = result[:start] + "{ /* REVIEWED I/O BODY: " + label + " */ }" + result[end:]
        normalized.append(result)
        spans.append({label: (start, end, declaration) for start, end, label, declaration in entries})
    check(normalized[0] == normalized[1], "JITLLVM changed outside the three reviewed I/O bodies")
    changed = []
    restored = after
    for label, signature in IO_METHODS:
        b0, b1, bd = spans[0][label]
        a0, a1, ad = spans[1][label]
        check(before[b0:b1] != after[a0:a1], f"Expected changed body: {label}")
        changed.append({
            "method": label,
            "signature": signature,
            "baseline": {"sha256": sha(before[b0:b1].encode()), "bytes": b1-b0, "firstLine": before[:bd].count("\n")+1, "lastLine": before[:b1].count("\n")+1},
            "candidate": {"sha256": sha(after[a0:a1].encode()), "bytes": a1-a0, "firstLine": after[:ad].count("\n")+1, "lastLine": after[:a1].count("\n")+1},
        })
    for label in sorted(spans[1], key=lambda key: spans[1][key][0], reverse=True):
        a0, a1, _ = spans[1][label]
        b0, b1, _ = spans[0][label]
        restored = restored[:a0] + before[b0:b1] + restored[a1:]
    check(restored == before, "Restoring only the I/O bodies does not exactly recover baseline")
    unchanged = []
    for label, signature in UNCHANGED_METHODS:
        b0, b1, _ = body_span(before, signature)
        a0, a1, _ = body_span(after, signature)
        check(before[b0:b1] == after[a0:a1], f"Changed emission/validation method: {label}")
        unchanged.append({"method": label, "bytes": b1-b0, "sha256": sha(before[b0:b1].encode())})
    return {
        "changedMethodCount": 3,
        "changedMethods": changed,
        "entireFileOutsideThoseBodiesByteIdentical": True,
        "outsideBodiesSHA256": sha(normalized[0].encode()),
        "restoringBaselineBodiesRecoversExactBaselineSHA256": sha(restored.encode()),
        "unchangedSelectedMethods": unchanged,
        "scope": "Every byte outside these three method bodies is identical, including all object emission, symbol validation, memory manager, linker and relocation code in JITLLVM.cpp. This is a source-equivalence proof, not a new native binary comparison.",
    }


def real_cmake(source, cmake, blocks, names, aliases, backend_digest, future_hash, cases, destination):
    destination.mkdir(parents=True, exist_ok=True)
    observed = destination/"inputs.txt"
    results = destination/"results.txt"
    case_results = destination/"alias-cases.txt"
    script = [
        "cmake_minimum_required(VERSION 3.20)",
        'set(RPCS3_FRONTEND "IOS")',
        "set(CMAKE_CURRENT_SOURCE_DIR " + cmake_quote(source/"rpcs3/Emu") + ")",
        "set(VERIFY_BACKEND_SHA256 " + cmake_quote(backend_digest) + ")",
        "set(VERIFY_FUTURE_JIT_SHA256 " + cmake_quote(future_hash) + ")",
        "set(VERIFY_OBSERVED " + cmake_quote(observed) + ")",
        "file(WRITE ${VERIFY_OBSERVED} \"\")",
        "set(VERIFY_DEFINITIONS \"\")",
        "function(target_compile_definitions target scope definition)",
        '  if(NOT "${ARGC}" STREQUAL "3" OR NOT "${target}" STREQUAL "rpcs3_emu" OR NOT "${scope}" STREQUAL "PRIVATE")',
        '    message(FATAL_ERROR "Unexpected identity target declaration")',
        "  endif()",
        '  set(VERIFY_DEFINITIONS "${VERIFY_DEFINITIONS}${definition}\\n" PARENT_SCOPE)',
        "endfunction()",
    ]
    adaptations = []
    for kind in ("PPU", "SPU"):
        block = blocks[kind]
        prefix = f"NEOSTATION_{kind}_CODEGEN_"
        file_line = f'        file(SHA256 "${{CMAKE_CURRENT_SOURCE_DIR}}/${{{prefix}SOURCE}}" {prefix}FILE_SHA256)'
        alias_line = f'        neostation_codegen_compatible_hash("${{{prefix}SOURCE}}" "${{{prefix}FILE_SHA256}}" {prefix}FILE_SHA256)'
        check(block.count(file_line) == 1 and block.count(alias_line) == 1, f"Unexpected {kind} hashing syntax")
        replacement = f'''        if("${{{prefix}SOURCE}}" STREQUAL "{BACKEND_SOURCE}")
            set({prefix}FILE_SHA256 "${{VERIFY_BACKEND_SHA256}}")
        else()
{file_line}
        endif()'''
        block = block.replace(file_line, replacement, 1)
        record = f'''        set(VERIFY_ACTUAL_SHA256 "${{{prefix}FILE_SHA256}}")
{alias_line}
        file(APPEND "${{VERIFY_OBSERVED}}" "{kind}|${{{prefix}SOURCE}}|${{VERIFY_ACTUAL_SHA256}}|${{{prefix}FILE_SHA256}}\\n")
        set(VERIFY_FUTURE_MAPPED "${{{prefix}FILE_SHA256}}")
        if("${{{prefix}SOURCE}}" STREQUAL "{JIT_SOURCE}")
            neostation_codegen_compatible_hash("${{{prefix}SOURCE}}" "${{VERIFY_FUTURE_JIT_SHA256}}" VERIFY_FUTURE_MAPPED)
        endif()
        string(APPEND VERIFY_{kind}_FUTURE_DIGEST "${{{prefix}SOURCE}}:${{VERIFY_FUTURE_MAPPED}};")'''
        block = block.replace(alias_line, record, 1)
        script.append(f'set(VERIFY_{kind}_FUTURE_DIGEST "")')
        script.append(block)
        script.append(f'string(SHA256 VERIFY_{kind}_FUTURE_ID "${{VERIFY_{kind}_FUTURE_DIGEST}}")')
        script.append(f'string(SUBSTRING "${{VERIFY_{kind}_FUTURE_ID}}" 0 16 VERIFY_{kind}_FUTURE_ID)')
        adaptations.append({"kind": kind, "originalBlockSHA256": sha(blocks[kind].encode()), "executedBlockSHA256": sha(block.encode())})
    script.append("file(WRITE " + cmake_quote(results) + ' "PPU=${NEOSTATION_PPU_CODEGEN_ID}\\nSPU=${NEOSTATION_SPU_CODEGEN_ID}\\nPPU_future=${VERIFY_PPU_FUTURE_ID}\\nSPU_future=${VERIFY_SPU_FUTURE_ID}\\n${VERIFY_DEFINITIONS}")')
    script.append("file(WRITE " + cmake_quote(case_results) + ' "")')
    for case in cases:
        script.extend([
            "neostation_codegen_compatible_hash(" + cmake_quote(case["source"]) + " " + cmake_quote(case["actual"]) + " VERIFY_CASE_MAPPED)",
            'if(NOT "${VERIFY_CASE_MAPPED}" STREQUAL ' + cmake_quote(case["expected"]) + ")",
            "  message(FATAL_ERROR " + cmake_quote("Alias case failed: " + case["name"]) + ")",
            "endif()",
            "file(APPEND " + cmake_quote(case_results) + " " + cmake_quote(case["name"]+"|") + ' "${VERIFY_CASE_MAPPED}\\n")',
        ])
    script_path = destination/"verify.cmake"
    script_path.write_text("\n".join(script)+"\n")
    command = [str(cmake), "-P", str(script_path)]
    run = subprocess.run(command, text=True, capture_output=True, check=False, timeout=60)
    (destination/"stdout.txt").write_text(run.stdout)
    (destination/"stderr.txt").write_text(run.stderr)
    check(run.returncode == 0, f"CMake failed ({run.returncode}):\n{run.stdout}\n{run.stderr}")
    ids = {}
    futures = {}
    definitions = []
    for line in results.read_text().splitlines():
        if line.startswith("NEOSTATION_"): definitions.append(line)
        else:
            key, value = line.split("=", 1)
            if key.endswith("_future"): futures[key[:-7]] = value
            else: ids[key] = value
    check(ids == EXPECTED_IDS, f"Wrong actual CMake identities: {ids}")
    check(len(definitions) == 2, "CMake did not emit both target definitions")
    for kind in ("PPU", "SPU"):
        check(f'NEOSTATION_{kind}_CODEGEN_ID="{ids[kind]}"' in definitions, "Wrong CMake target definition")
    records = []
    for line in observed.read_text().splitlines():
        kind, relative, actual, effective = line.split("|")
        check(effective == aliases.get((relative, actual), actual), f"Python/CMake alias mismatch: {relative}")
        records.append({"kind": kind, "source": relative, "actualSHA256": actual, "effectiveSHA256": effective})
    for kind in ("PPU", "SPU"):
        subset = [record for record in records if record["kind"] == kind]
        check([r["source"] for r in subset] == names[kind], f"CMake input order changed: {kind}")
        digest = "".join(r["source"]+":"+r["effectiveSHA256"]+";" for r in subset)
        check(sha(digest.encode())[:16] == ids[kind], f"Python/CMake digest mismatch: {kind}")
        future_digest = "".join(r["source"]+":"+(future_hash if r["source"] == JIT_SOURCE else r["effectiveSHA256"])+";" for r in subset)
        check(sha(future_digest.encode())[:16] == futures[kind], f"Python/CMake future mismatch: {kind}")
        check(futures[kind] != ids[kind], f"Future JIT change reused {kind} identity")
    seen_cases = dict(line.split("|", 1) for line in case_results.read_text().splitlines())
    check(len(seen_cases) == len(cases), "Missing alias results")
    for case in cases: check(seen_cases[case["name"]] == case["expected"], f"Alias observation mismatch: {case['name']}")
    return {
        "identities": ids, "syntheticFutureIdentities": futures, "targetCompileDefinitions": definitions,
        "inputCount": {kind: len(names[kind]) for kind in names}, "inputs": records,
        "aliasCases": [{**case, "observed": seen_cases[case["name"]], "passed": True} for case in cases],
        "command": command, "scriptSHA256": sha(script_path.read_bytes()), "adaptations": adaptations,
        "stdout": run.stdout, "stderr": run.stderr,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--upstream-metadata", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--cmake", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path): setattr(args, key, value.resolve())
    manifest = read_json(args.baseline_manifest)
    metadata = read_json(args.upstream_metadata)
    current_manifest_path = args.repo/"build-utils/rpcs3/canonical-source.json"
    current_manifest = read_json(current_manifest_path)
    check(manifest["upstream_commit"] == current_manifest["upstream_commit"] == metadata["commit"]["sha"] == UPSTREAM_COMMIT, "Upstream pin mismatch")
    check(metadata["commit"]["tree"]["sha"] == metadata["tree"]["sha"], "Upstream tree is not the pinned commit's tree")
    tree = {entry["path"]: entry for entry in metadata["tree"]["tree"]}
    backend = manifest["llvm_aarch64_ghc_patch"]
    check(current_manifest["llvm_aarch64_ghc_patch"] == backend, "LLVM patch/backend identity changed")
    llvm_patch = args.repo/"build-utils/rpcs3/llvm-aarch64-ghc-emergency-spill.patch"
    check(sha(llvm_patch.read_bytes()) == backend["patch_sha256"], "LLVM patch bytes differ from authenticated baseline")
    check(manifest["runtime_log_followup_20261029"]["codegen"] == EXPECTED_IDS, "Wrong delivered codegen identity")
    for relative in (CMAKE_PATH, COMPAT_PATH, JIT_PATH):
        check(sha((args.baseline/relative).read_bytes()) == manifest["files_sha256"][relative], "Baseline manifest mismatch: " + relative)
    baseline_cmake = (args.baseline/CMAKE_PATH).read_bytes()
    candidate_cmake = (args.source/CMAKE_PATH).read_bytes()
    check(baseline_cmake == candidate_cmake, "Codegen input CMake file changed")
    cmake_text = candidate_cmake.decode()
    blocks = {kind: extract_block(cmake_text, kind) for kind in ("PPU", "SPU")}
    names = {kind: extract_names(blocks[kind], kind) for kind in blocks}
    candidate_compat = (args.source/COMPAT_PATH).read_text()
    baseline_compat = (args.baseline/COMPAT_PATH).read_text()
    aliases = alias_table(candidate_compat)
    baseline_aliases = alias_table(baseline_compat)
    before = (args.baseline/JIT_PATH).read_bytes()
    after = (args.source/JIT_PATH).read_bytes()
    check(sha(before) == DELIVERED_JIT and sha(after) == REVIEWED_JIT, "Not the reviewed exact JITLLVM snapshots")
    check(aliases[(JIT_SOURCE, REVIEWED_JIT)] == baseline_aliases[(JIT_SOURCE, DELIVERED_JIT)] == COMPATIBLE_JIT, "JIT alias target changed")
    check(code_without_comments(candidate_compat.replace(REVIEWED_JIT, DELIVERED_JIT)) == code_without_comments(baseline_compat), "Compatibility code changed beyond exact JIT hash update")
    code_proof = prove_io_only(before.decode(), after.decode())
    future_hash = sha(after + b"\n// Synthetic future source edit for identity verification only.\n")
    auth = []
    for relative in sorted(set(names["PPU"] + names["SPU"])):
        if relative == BACKEND_SOURCE:
            auth.append({"source": relative, "path": BACKEND_PATH, "method": "reused authenticated delivered manifest backend digest; current LLVM pin and patch bytes unchanged", "baselineSHA256": backend["postimage_sha256"], "candidateSHA256": backend["postimage_sha256"], "equal": True, "bytesRead": False})
            continue
        baseline_path = (args.baseline/"rpcs3/Emu"/relative).resolve()
        path = baseline_path.relative_to(args.baseline).as_posix()
        old_bytes = baseline_path.read_bytes()
        new_bytes = (args.source/path).read_bytes()
        old_hash, new_hash = sha(old_bytes), sha(new_bytes)
        if path in manifest["files_sha256"]:
            check(old_hash == manifest["files_sha256"][path], "Unauthenticated baseline postimage: " + path)
            method = "delivered 593 canonical manifest SHA256"
            blob = None
        else:
            check(path in tree and tree[path]["type"] == "blob", "Missing upstream file identity: " + path)
            blob = blob_sha(old_bytes)
            check(blob == tree[path]["sha"] and len(old_bytes) == tree[path]["size"], "Unauthenticated baseline upstream bytes: " + path)
            method = "pinned 22f1152 Git blob SHA1 and size"
        check(path == JIT_PATH or new_bytes == old_bytes, "Another codegen input changed: " + path)
        auth.append({"source": relative, "path": path, "method": method, "gitBlobSHA1": blob, "baselineSHA256": old_hash, "candidateSHA256": new_hash, "baselineBytes": len(old_bytes), "candidateBytes": len(new_bytes), "equal": old_bytes == new_bytes, "bytesRead": True})
    changed_inputs = [entry["path"] for entry in auth if not entry["equal"]]
    check(changed_inputs == [JIT_PATH], "Unexpected changed codegen input set")
    cases = [
        {"name": "reviewed_jit_exact_pair", "source": JIT_SOURCE, "actual": REVIEWED_JIT, "expected": COMPATIBLE_JIT},
        {"name": "future_jit_hash_not_aliased", "source": JIT_SOURCE, "actual": future_hash, "expected": future_hash},
        {"name": "wrong_path_same_hash_not_aliased", "source": "../../Utilities/Other.cpp", "actual": REVIEWED_JIT, "expected": REVIEWED_JIT},
        {"name": "noncanonical_path_same_hash_not_aliased", "source": "Utilities/JITLLVM.cpp", "actual": REVIEWED_JIT, "expected": REVIEWED_JIT},
        {"name": "baseline_hash_not_broadly_aliased", "source": JIT_SOURCE, "actual": DELIVERED_JIT, "expected": DELIVERED_JIT},
    ]
    for index, ((relative, actual), effective) in enumerate(aliases.items()):
        if relative == JIT_SOURCE: continue
        future_other = sha((actual+" future").encode())
        cases.extend([
            {"name": f"existing_alias_{index}_unchanged", "source": relative, "actual": actual, "expected": effective},
            {"name": f"existing_alias_{index}_future_rejected", "source": relative, "actual": future_other, "expected": future_other},
            {"name": f"existing_alias_{index}_wrong_path_rejected", "source": "Other/"+relative, "actual": actual, "expected": actual},
        ])
    baseline_cases = [
        {"name": "delivered_jit_exact_pair", "source": JIT_SOURCE, "actual": DELIVERED_JIT, "expected": COMPATIBLE_JIT},
        {"name": "new_hash_not_yet_aliased_by_delivered_rules", "source": JIT_SOURCE, "actual": REVIEWED_JIT, "expected": REVIEWED_JIT},
        {"name": "future_hash_not_aliased_by_delivered_rules", "source": JIT_SOURCE, "actual": future_hash, "expected": future_hash},
    ]
    if args.work_dir:
        work = args.work_dir
        work.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="rpcs3-codegen-identity-"))
    baseline_result = real_cmake(args.baseline, args.cmake, blocks, names, baseline_aliases, backend["postimage_sha256"], future_hash, baseline_cases, work/"baseline")
    candidate_result = real_cmake(args.source, args.cmake, blocks, names, aliases, backend["postimage_sha256"], future_hash, cases, work/"candidate")
    for label, cmake_result in (("baseline", baseline_result), ("candidate", candidate_result)):
        by_source = {entry["source"]: entry[label+"SHA256"] for entry in auth}
        for observed in cmake_result["inputs"]:
            check(observed["actualSHA256"] == by_source[observed["source"]], "CMake/Python file SHA mismatch: " + observed["source"])
    cmake_version = subprocess.check_output([str(args.cmake), "--version"], text=True).splitlines()[0]
    report = {
        "passed": True,
        "verifiedAtUTC": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": str(args.source), "baseline": str(args.baseline),
        "upstreamCommit": UPSTREAM_COMMIT, "upstreamTree": metadata["tree"]["sha"],
        "baselineManifestSHA256": sha(args.baseline_manifest.read_bytes()),
        "currentManifestSHA256": sha(current_manifest_path.read_bytes()),
        "upstreamMetadataSHA256": sha(args.upstream_metadata.read_bytes()),
        "cmake": {"path": str(args.cmake), "version": cmake_version, "executableSHA256": sha(args.cmake.read_bytes())},
        "expectedCodegen": EXPECTED_IDS,
        "baselineCMake": baseline_result, "candidateCMake": candidate_result,
        "uniqueInputCount": len(auth), "directlyReadUniqueInputCount": sum(entry["bytesRead"] for entry in auth),
        "changedCodegenInputs": changed_inputs, "authenticatedInputs": auth,
        "llvmBackendDigestReuse": {**backend, "currentPinAndPatchMetadataEqualBaseline": True, "patchBytesSHA256": sha(llvm_patch.read_bytes()), "backendSourceBytesReadOrRebuilt": False, "reason": "Reuse the delivered 593 backend proof; no LLVM change in this follow-up and no repeat of its historical build/patch test."},
        "cmakeInputListSHA256": sha(candidate_cmake),
        "compatibilityModule": {"baselineSHA256": sha(baseline_compat.encode()), "candidateSHA256": sha(candidate_compat.encode()), "onlySemanticChangeIsExactJITSourceHash": True, "aliasCount": len(aliases)},
        "jitLLVM": {"baselineSHA256": sha(before), "candidateSHA256": sha(after), "effectiveSHA256": COMPATIBLE_JIT, **code_proof},
        "syntheticFutureJITHash": future_hash,
        "negativeCaseCount": sum(case["expected"] == case["actual"] for case in cases),
        "scriptSHA256": sha(Path(__file__).read_bytes()),
        "scope": "Actual CMake 593 identity blocks and compatibility function executed in script mode; target_compile_definitions is captured, no Core configuration or compilation. Only the unavailable, unchanged LLVM backend file(SHA256) is substituted with the authenticated manifest digest. Added recording and a separate synthetic future digest do not alter production identity variables. Python independently checks every direct file digest, alias mapping, input ordering and aggregate SHA256. No historical suite, gameplay benchmark, new object emission or device test was run.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"passed": True, "report": str(args.output), "codegen": candidate_result["identities"], "futureCodegen": candidate_result["syntheticFutureIdentities"], "uniqueInputs": len(auth), "changedInputs": changed_inputs, "candidateAliasCases": len(cases), "baselineAliasCases": len(baseline_cases), "changedMethods": 3}, indent=2))


if __name__ == "__main__":
    main()
