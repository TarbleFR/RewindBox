#!/usr/bin/env python3
"""Shared runner for source-extracted RPCS3 CPU regression harnesses."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def extract_block(text, needle):
    """Extract the known, balanced production block selected by an exact anchor."""
    start = text.index(needle)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline RPCS3 source root")
    parser.add_argument("--source", type=Path, required=True, help="Candidate RPCS3 source root")
    parser.add_argument("--output", type=Path, required=True, help="Directory for generated source and reports")
    parser.add_argument("--report", type=Path, help="Optional exact JSON report path")
    parser.add_argument("--compiler", default=os.environ.get("CXX", "g++"), help="Compiler command, defaults to CXX or g++")
    parser.add_argument("--sanitize", action="store_true", help="Compile with AddressSanitizer and UndefinedBehaviorSanitizer")
    parser.add_argument("--timeout", type=float, default=120, help="Executable timeout in seconds")
    parser.add_argument("--generate-only", action="store_true", help="Generate and hash source; do not compile or execute")
    parser.add_argument("--reference-result", type=Path, help="Compare generated source SHA256 with an existing execution report")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    for field in ("baseline", "source", "output", "report", "reference_result"):
        value = getattr(args, field)
        if value is not None:
            setattr(args, field, value.resolve())
    return args


def run_program(args, name, program, source_hashes, scope, limitations):
    args.output.mkdir(parents=True, exist_ok=True)
    src = args.output / (name + "-program.cpp")
    src.write_text(program)
    mode = "asan-ubsan" if args.sanitize else "plain"
    report = {
        "mode": mode,
        "status": "generated" if args.generate_only else "pending",
        "executed": False,
        "baseline": str(args.baseline),
        "source": str(args.source),
        "program_sha256": sha256(program),
        "sources": source_hashes,
        "scope": scope,
        "limitations": limitations,
    }
    report_path = args.report or args.output / (name + ("-generation" if args.generate_only else "-" + mode) + "-result.json")

    def save():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))

    if args.reference_result:
        reference = json.loads(args.reference_result.read_text())
        report["reference_result"] = str(args.reference_result)
        report["matches_reference_program"] = report["program_sha256"] == reference["program_sha256"]
        if not report["matches_reference_program"]:
            report["status"] = "reference_mismatch"
            save()
            return 1
    if args.generate_only:
        save()
        return 0

    exe = args.output / (name + "-" + mode)
    command = shlex.split(args.compiler)
    if args.sanitize:
        command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    command += ["-std=c++20", "-Wall", "-Wextra", "-Werror", "-O1" if args.sanitize else "-O2", "-g", str(src), "-o", str(exe)]
    report["command"] = command
    compiled = subprocess.run(command, text=True, capture_output=True)
    (args.output / (name + "-" + mode + "-compile.txt")).write_text(compiled.stdout + compiled.stderr)
    report["compile_exit_code"] = compiled.returncode
    if compiled.returncode:
        report["status"] = "compile_failure"
        report["failure"] = compiled.stdout + compiled.stderr
        save()
        return compiled.returncode

    env = os.environ.copy()
    if args.sanitize:
        env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1"
        env["UBSAN_OPTIONS"] = "halt_on_error=1"
    report["executed"] = True
    try:
        result = subprocess.run([str(exe)], text=True, capture_output=True, env=env, timeout=args.timeout)
    except subprocess.TimeoutExpired as error:
        report["status"] = "execution_timeout"
        report["timeout_seconds"] = args.timeout
        report["failure"] = str(error)
        save()
        return 124
    (args.output / (name + "-" + mode + "-output.txt")).write_text(result.stdout + result.stderr)
    report["exit_code"] = result.returncode
    report["status"] = "passed" if result.returncode == 0 else "execution_failure"
    if result.returncode == 0:
        report["results"] = json.loads(result.stdout)
    else:
        report["failure"] = result.stdout + result.stderr
    save()
    return result.returncode
