#!/usr/bin/env python3
"""Apple ARM64 host harnesses of the declared Core build (apple-host-tests job).

build-utils/rpcs3/core-build.json declares which harnesses run again on this
build's tree (their inputs changed, or they are new) and which Apple results of
the reference Core run are reused.

--authenticate-reused fetches the reference Apple job, run and artifact through
the API, requires the exact pinned identities and bytes, requires every reused
report to equal its committed copy, and proves that every reused harness reads
the same inputs on this build's tree: its scripts are byte-identical to the
reference source commit, every tree file it reads or compiles is unchanged since
the reference Core, its recorded input digests are re-derived identically, and
the static audits re-derive the same report. Nothing is compiled or executed.

--run executes the declared commands and writes apple-host-tests.json, which
also carries the authenticated reused results (labelled reused).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from unittest import mock
import zipfile

DIAG = Path(__file__).resolve().parent
sys.path.insert(0, str(DIAG))
import rpcs3_core610 as gate  # noqa: E402

ROOT = gate.ROOT
REPOSITORY = "TarbleFR/RewindBox"
RECEIPT = "apple-host-tests.json"
REUSED_RECEIPT = "reused-apple-evidence.json"
require, sha, file_sha, load = gate.require, gate.sha, gate.file_sha, gate.load
APPLE = gate.SPEC["apple_host_tests"]
REUSED = APPLE["reused"]
REFERENCE = gate.REFERENCE


class _CompilerReached(Exception):
    """Raised instead of running a harness's compiler: only its input is wanted."""


def placeholders(argv, source, baseline, out, cxx=None):
    values = {"source": str(source), "baseline": str(baseline), "out": str(out)}
    result = [part.format(**values) for part in argv]
    if cxx:  # local rehearsal only; the declared commands use Apple clang (clang++)
        result = [cxx if previous in ("--compiler", "--cxx") else part for previous, part in zip([None, *result], result)]
    return result


def commands(source, baseline, out, cxx=None):
    return [(item["name"], placeholders(item["argv"], source, baseline, out, cxx)) for item in APPLE["rerun"]]


def api(endpoint, target):
    with target.open("wb") as stream:
        subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{endpoint}"], cwd=ROOT, stdout=stream, check=True, timeout=600)


def harness(name, path):
    return gate.module(name, ROOT / path)


@contextlib.contextmanager
def traced_reads(roots):
    """Record every Path.read_text/read_bytes under the given roots while a harness function runs."""
    seen = {label: set() for label in roots}
    original_text, original_bytes = Path.read_text, Path.read_bytes

    def note(path):
        resolved = Path(path).resolve()
        for label, root in roots.items():
            if resolved.is_relative_to(root):
                seen[label].add(resolved.relative_to(root).as_posix())

    def read_text(self, *args, **kwargs):
        note(self)
        return original_text(self, *args, **kwargs)

    def read_bytes(self):
        note(self)
        return original_bytes(self)

    with mock.patch.object(Path, "read_text", read_text), mock.patch.object(Path, "read_bytes", read_bytes):
        yield seen


def quoted_includes(text, directories, tree):
    """Tree files reached by #include "..." from a program, resolved like the harness compile."""
    found, pending = set(), [(text, None)]
    while pending:
        body, parent = pending.pop()
        for name in re.findall(r'^\s*#\s*include\s*"([^"]+)"', body, re.M):
            candidates = ([parent.parent / name] if parent else []) + [Path(d) / name for d in directories]
            target = next((c.resolve() for c in candidates if c.is_file()), None)
            require(target is not None and target.is_relative_to(tree), "unresolved or external include: " + name)
            relative = target.relative_to(tree).as_posix()
            if relative not in found:
                found.add(relative)
                pending.append((target.read_text(errors="replace"), target))
    return found


def unchanged_tree_files(paths, source, reference_identity, reference_proof, manifest):
    reference_native = reference_identity["native_source_sha256"]
    ordinary = reference_proof["source_closure"]["upstream_dependencies"]["files_sha256"]
    result = {}
    for path in sorted(paths):
        raw = (source / path).read_bytes()
        if path in manifest["files_sha256"] or path in reference_native:
            current = sha(raw.replace(b"\r\n", b"\n"))
            require(manifest["files_sha256"].get(path) == reference_native.get(path) == current,
                    f"tree input changed since Core {gate.REFERENCE_BUILD}: {path}")
        else:
            current = sha(raw)
            require(ordinary.get(path) == current, "ordinary upstream input differs from the reference: " + path)
        result[path] = current
    return result


def unchanged_repo_files(paths):
    result = {}
    for path in paths:
        historical = subprocess.check_output(["git", "show", REFERENCE["source"] + ":" + path], cwd=ROOT)
        require(sha(historical) == file_sha(ROOT / path),
                f"harness input changed since the Core {gate.REFERENCE_BUILD} source commit: {path}")
        result[path] = sha(historical)
    return result


def routing_unit(phases, bridge_bytes, work):
    """The routing translation unit rpcs3_transition_phases_test.routing() compiles, for one bridge."""
    work.mkdir(parents=True)
    bridge = work / "Rpcs3InternalBridgePlugin.mm"
    bridge.write_bytes(bridge_bytes)
    with mock.patch.object(phases, "BRIDGE", bridge), mock.patch.object(phases.subprocess, "run", side_effect=_CompilerReached):
        with contextlib.suppress(_CompilerReached):
            phases.routing(work)
    return (work / "routing.cpp").read_bytes()


def checked_reports(work):
    """The reference Apple job, run and artifact (API metadata and bytes) and its reports."""
    artifact = REFERENCE["apple_host_tests_artifact"]
    job = load(work / "job.json")
    require(job["id"] == REFERENCE["apple_host_test_job"] and job["run_id"] == REFERENCE["run"]
            and job["head_sha"] == REFERENCE["source"] and job["run_attempt"] == REFERENCE["attempt"]
            and job["status"] == "completed" and job["conclusion"] == "success", "Wrong reused Apple job")
    require(set(REUSED["steps"]) <= {step["name"] for step in job["steps"] if step["conclusion"] == "success"},
            "Missing successful reused Apple steps")
    run = load(work / "run.json")
    require(run["id"] == REFERENCE["run"] and run["head_sha"] == REFERENCE["source"] and run["head_branch"] == "Claude"
            and run["path"] == gate.WORKFLOW and run["run_attempt"] == REFERENCE["attempt"]
            and run["status"] == "completed" and run["conclusion"] == "success", "Wrong reused Apple run")
    metadata = load(work / "artifact.json")
    require(metadata["id"] == artifact["id"] and metadata["name"] == artifact["name"]
            and metadata["size_in_bytes"] == artifact["bytes"] and metadata["digest"] == "sha256:" + artifact["sha256"]
            and metadata["expired"] is False and metadata["workflow_run"]["id"] == REFERENCE["run"]
            and metadata["workflow_run"]["head_sha"] == REFERENCE["source"], "Wrong reused Apple artifact")
    archive = work / "apple-host-tests.zip"
    require(archive.stat().st_size == artifact["bytes"] and file_sha(archive) == artifact["sha256"],
            "Reused Apple artifact bytes differ")
    evidence = ROOT / REUSED["evidence"]
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and z.testzip() is None, "Invalid reused Apple artifact")
        for name in names:
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and ".." not in path.parts and "\\" not in name, "Unsafe member: " + name)
        receipt_raw = z.read(RECEIPT)
        reports = {name: z.read(name + ".json") for name in REUSED["reused_commands"]}
    receipt = json.loads(receipt_raw)
    require(receipt["result"] == "passed" and receipt["source"] == REFERENCE["source"] and receipt["run"] == REFERENCE["run"]
            and [item["name"] for item in receipt["commands"]] == REUSED["commands"]
            and all(item["exit_code"] == 0 for item in receipt["commands"])
            and receipt["compiler"] == REUSED["compiler"] and receipt["physical_device_tested"] is False,
            "Reused Apple receipt differs from its reviewed contract")
    require(receipt_raw == (evidence / RECEIPT).read_bytes(), "Committed Apple receipt differs from the artifact")
    for name, raw in reports.items():
        require(raw == (evidence / (name + ".json")).read_bytes(), "Committed Apple report differs from the artifact: " + name)
    return receipt, {name: json.loads(raw) for name, raw in reports.items()}, reports


def checked_trees(source, baseline):
    manifest = load(ROOT / "build-utils/rpcs3/canonical-source.json")
    require(manifest["patch_sha256"] == gate.PATCH_SHA and len(manifest["files_sha256"]) == gate.POSTIMAGES,
            f"canonical Core {gate.BUILD} source changed")
    old = json.loads(subprocess.check_output(["git", "show", APPLE["baseline"]["source"] + ":build-utils/rpcs3/canonical-source.json"],
                                             cwd=ROOT))
    require(old["patch_sha256"] == APPLE["baseline"]["canonical_patch_sha256"], "Apple baseline delta differs")
    for tree, files in ((source, manifest["files_sha256"]), (baseline, old["files_sha256"])):
        require(gate.command("git", "-C", tree, "rev-parse", "HEAD") == gate.UPSTREAM, "wrong native upstream: " + str(tree))
        for name, digest in files.items():
            require(sha((tree / name).read_bytes().replace(b"\r\n", b"\n")) == digest, f"{tree}: postimage differs: {name}")
    return manifest


def lr_inputs(source, baseline, report, work):
    lr = harness("core_reuse_lr", "test/rpcs3_spu_mfc_lr_test.py")
    with traced_reads({"source": source, "baseline": baseline, "repo": ROOT}) as seen:
        contract = lr.contract(source, baseline)
        program = lr.generate(source, None)
    require(contract == report["contract"] and sha(program.encode()) == report["candidate"]["program_sha256"],
            "LR contract or generated program differs from the reused report")
    return seen, quoted_includes(program, [source / "rpcs3"], source), {"program_sha256": sha(program.encode())}


def census_inputs(source, baseline, report, work):
    census = harness("core_reuse_census", "test/rpcs3_feedback_census_test.py")
    with traced_reads({"source": source, "baseline": baseline, "repo": ROOT}) as seen:
        contract = census.source_contract(source, baseline)
        header = (source / census.HEADER).read_text()
        struct = census.struct_source((source / census.DRAW).read_text())
    for mode in ("plain", "asan_ubsan"):
        require(report["execution"][mode]["production_header_sha256"] == sha(header.encode())
                and report["execution"][mode]["production_struct_sha256"] == sha(struct.encode()),
                "feedback census production code differs from the reused report")
    require(contract == report["source_contract"], "feedback census source contract differs from the reused report")
    program = census.PRELUDE + header.replace("#pragma once", "") + "\n" + struct + census.MAIN
    # The census program is compiled from a temporary directory without -I.
    require(not re.search(r'^\s*#\s*include\s*"', program, re.M), "feedback census program gained a quoted include")
    phases = census.phases
    bridge = ROOT / gate.HOST
    old_bridge = subprocess.check_output(["git", "show", REFERENCE["source"] + ":" + gate.HOST], cwd=ROOT)
    require(sha(old_bridge) == report["routing"]["bridge_sha256"]
            and report["routing"]["diagnostics_sha256"] == file_sha(phases.DIAG), "feedback census routing inputs differ")
    unit = routing_unit(phases, old_bridge, work / "routing-reference")
    require(routing_unit(phases, bridge.read_bytes(), work / "routing-current") == unit,
            "the routing unit compiled from the bridge changed")
    return seen, set(), {"routing_unit_sha256": sha(unit), "routing_unit_bytes": len(unit),
                         "reference_bridge_sha256": sha(old_bridge), "current_bridge_sha256": file_sha(bridge)}


def invariance_inputs(source, baseline, report, work):
    invariance = harness("core_reuse_invariance", "test/rpcs3_position_invariance_test.py")
    with traced_reads({"source": source, "baseline": baseline, "repo": ROOT}) as seen:
        contract = invariance.source_contract(source)
    require(contract == report["source_contract"], "position invariance source contract differs from the reused report")
    require(report["title_predicate"] == {"result": "pass", "scoped": invariance.SCOPED,
                                          "unscoped_checked": [s for s in invariance.UNSCOPED if s]}
            and str(report["shader_chain"]).startswith("skipped"), "position invariance report scope differs")
    work.mkdir(parents=True)
    with mock.patch.object(invariance, "run", side_effect=_CompilerReached):
        with contextlib.suppress(_CompilerReached):
            invariance.predicate(source, work, "c++")
    program = (work / "predicate.cpp").read_text()
    return seen, quoted_includes(program, [source / "rpcs3"], source), {"predicate_program_sha256": sha(program.encode())}


def codegen_inputs(source, baseline, raw):
    codegen = harness("core_reuse_codegen", "test/rpcs3_core610_codegen_test.py")
    text = json.dumps(codegen.audit(source, baseline), indent=2) + "\n"
    require(text.encode() == raw, "codegen audit re-derived on this tree differs from the reused report")
    return {"report_rederived_identically": True}


def reuse_audit_inputs(source, baseline, report):
    audit = harness("core_reuse_audit", "test/rpcs3_core610_reuse_audit_test.py")
    current = audit.audit(source, baseline)
    column, reference_column = f"core{gate.BUILD}", f"core{gate.REFERENCE_BUILD}"
    require(set(current) == set(report["harnesses"]), "reuse audit harness scope differs")
    for name, entry in current.items():
        old = report["harnesses"][name]
        require({k: v for k, v in entry.items() if k != "inputs"} == {k: v for k, v in old.items() if k != "inputs"}
                and set(entry["inputs"]) == set(old["inputs"]), "reuse audit classification differs: " + name)
        for label, digests in entry["inputs"].items():
            require(digests == {"delivered": old["inputs"][label]["delivered"], column: old["inputs"][label][reference_column]},
                    f"reuse audit extracted input differs: {name} {label}")
    return {"classification_and_digests_identical": True, "rerun_by_this_build": True}


def authenticate_reused(source, baseline, out, *, download=True):
    source, baseline, out = source.resolve(), baseline.resolve(), out.resolve()
    work = out / "reused-reference"
    artifact = REFERENCE["apple_host_tests_artifact"]
    if download:
        require(not work.exists(), "reused evidence directory already exists")
        work.mkdir(parents=True)
        api(f"actions/jobs/{REFERENCE['apple_host_test_job']}", work / "job.json")
        api(f"actions/runs/{REFERENCE['run']}", work / "run.json")
        api(f"actions/artifacts/{artifact['id']}", work / "artifact.json")
        api(f"actions/artifacts/{artifact['id']}/zip", work / "apple-host-tests.zip")
    receipt, reports, raw = checked_reports(work)
    manifest = checked_trees(source, baseline)
    reference_identity, reference_proof = gate.delivered()
    scratch = Path(tempfile.mkdtemp(prefix="rpcs3-core-reuse-", dir=out))
    derive = {"lr-full-queue": lr_inputs, "feedback-census": census_inputs,
              "position-invariance-contract": invariance_inputs}
    results = {}
    for name, declared in REUSED["reused_commands"].items():
        entry = {"report_sha256": sha(raw[name]), "reused_from": {"build": gate.REFERENCE_BUILD, "run": REFERENCE["run"],
                                                                  "job": REFERENCE["apple_host_test_job"],
                                                                  "artifact": artifact["id"]},
                 "native_executed_now": False, "repo_inputs_sha256": unchanged_repo_files(declared["repo_inputs"])}
        if declared.get("static_report"):
            entry["static_audit"] = (codegen_inputs(source, baseline, raw[name]) if name == "codegen-audit"
                                     else reuse_audit_inputs(source, baseline, reports[name]))
        else:
            seen, includes, derived = derive[name](source, baseline, reports[name], scratch / name)
            tree = set(declared["tree_inputs"])
            require(seen["source"] <= tree and seen["baseline"] <= tree and includes <= tree,
                    f"{name} reads undeclared tree inputs: " + repr(sorted((seen["source"] | seen["baseline"] | includes) - tree)))
            require(seen["repo"] <= set(declared["repo_inputs"]),
                    f"{name} reads undeclared repository inputs: " + repr(sorted(seen["repo"] - set(declared["repo_inputs"]))))
            entry.update(derived, tree_inputs_sha256=unchanged_tree_files(tree, source, reference_identity, reference_proof, manifest),
                         compiled_tree_includes=sorted(includes))
        results[name] = entry
    summary = {"schema": 1, "build": gate.BUILD, "reference_build": gate.REFERENCE_BUILD,
               "reference": {"run": REFERENCE["run"], "attempt": REFERENCE["attempt"], "job": REFERENCE["apple_host_test_job"],
                             "source": REFERENCE["source"], "artifact": artifact},
               "reference_receipt_sha256": file_sha(ROOT / REUSED["evidence"] / RECEIPT),
               "reference_compiler": receipt["compiler"], "commands": results,
               "reused_label": "reused: reference Apple results whose inputs are unchanged in this build",
               "native_tests_executed_now": 0, "physical_device_tested": False}
    out.mkdir(parents=True, exist_ok=True)
    (out / REUSED_RECEIPT).write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS: {len(results)} Core {gate.REFERENCE_BUILD} Apple results authenticated and reused for Core {gate.BUILD}: "
          + ", ".join(sorted(results)))
    return summary


def run(source, baseline, out, *, cxx=None, reused=None):
    source, baseline, out = source.resolve(), baseline.resolve(), out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = cxx or "clang++"
    receipt = {"schema": 1, "build": gate.BUILD, "source": os.environ.get("GITHUB_SHA") or gate.command("git", "rev-parse", "HEAD"),
               "run": int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,
               "host": subprocess.check_output(["uname", "-a"], text=True).strip(),
               "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
               "baseline": APPLE["baseline"], "commands": [], "physical_device_tested": False}
    failed = 0
    for name, argv in commands(source, baseline, out, cxx):
        start = time.monotonic()
        log = out / (name + ".log")
        with log.open("wb") as stream:
            code = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
        print(f"{name}: exit {code}", flush=True)
        print(log.read_text(errors="replace")[-6000:], flush=True)
        receipt["commands"].append({"name": name, "argv": argv, "exit_code": code,
                                    "seconds": round(time.monotonic() - start, 3)})
        failed += code != 0
    if reused is not None:
        raw = reused.read_bytes()
        summary = json.loads(raw)
        require(summary["build"] == gate.BUILD and set(summary["commands"]) == set(REUSED["reused_commands"]),
                "reused Apple evidence belongs to another build")
        receipt["reused"] = {"receipt": REUSED_RECEIPT, "receipt_sha256": sha(raw), "reference": summary["reference"],
                             "commands": sorted(summary["commands"]), "label": summary["reused_label"]}
    else:
        failed += 1
        receipt["reused"] = None
    receipt["result"] = "passed" if not failed else "failed"
    (out / RECEIPT).write_text(json.dumps(receipt, indent=2) + "\n")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--authenticate-reused", action="store_true")
    parser.add_argument("--offline", action="store_true", help="recheck an existing reused-reference directory")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--source", type=Path, required=True, help="materialized Core tree of this build")
    parser.add_argument("--baseline", type=Path, required=True, help="materialized delivered baseline Core")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cxx", help="local rehearsal only: replaces the declared clang++")
    args = parser.parse_args()
    if args.authenticate_reused:
        authenticate_reused(args.source, args.baseline, args.output, download=not args.offline)
    elif args.run:
        reused = args.output / REUSED_RECEIPT
        sys.exit(run(args.source, args.baseline, args.output, cxx=args.cxx, reused=reused if reused.is_file() else None))
    else:
        parser.error("choose --authenticate-reused or --run")


if __name__ == "__main__":
    main()
