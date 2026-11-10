#!/usr/bin/env python3
"""Finalize preserved Core bytes offline; retain the original failed CI provenance.

This creates metadata and a new local ZIP only. It never compiles, executes,
changes or signs the native Core, and never creates a GitHub Core artifact.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("diagnostics-archive", "artifact-metadata", "run-metadata", "jobs-metadata", "source-root", "native-source-root", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    report = args.report.resolve() if args.report else output.with_suffix(".verification.json")
    if output == report or output.exists() or report.exists():
        parser.error("output/report must be separate new files")
    for root in (args.source_root.resolve(), args.native_source_root.resolve()):
        if output.is_relative_to(root) or report.is_relative_to(root):
            parser.error("keep the original source roots unchanged; save output elsewhere")
    spec = importlib.util.spec_from_file_location("offline_mvk_core_verifier", ROOT / "test/verify_rpcs3_mvk_cache_core_archive.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    inputs = (args.diagnostics_archive, args.artifact_metadata, args.run_metadata, args.jobs_metadata,
              args.source_root.resolve(), args.native_source_root.resolve())
    payloads, _ = verifier.recovery_payloads(*inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=output.name + ".tmp-", suffix=".zip", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in sorted(payloads.items()):
                archive.writestr(name, data)
        result = verifier.verify_recovery(temporary, *inputs)
        # The temporary file shares the destination filesystem. link() refuses
        # to overwrite another file created while validation was running.
        os.link(temporary, output)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": "verified_offline_recovery", "archive": str(output), "report": str(report),
                          "original_ci_conclusion": "failure", "core_sha256": result["core_sha256"]}))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
