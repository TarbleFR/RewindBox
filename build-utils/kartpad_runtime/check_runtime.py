#!/usr/bin/env python3
"""Identity checks for the KartPad runtime built from public sources.

pristine  compares upstream's own publishable-app build, made in CI, with the
          official game-free KartPad IPA: same provenance record, same
          exported interface, same pack fingerprint, no game code.
embedded  checks NeoStation's KartPadCore.framework: arm64 iOS dylib, the
          official runtime interface still exported (a player's pack binds
          to it by name), the pinned pack fingerprint, NeoStation's entry
          points, and no game code; then writes its identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import macho  # noqa: E402
import game_content_gate  # noqa: E402

PINS = json.loads((HERE / "source.json").read_text())
EXECUTABLE_ONLY = {"_main", "__mh_execute_header"}
TRANSLATED = re.compile(r"^_func_8[0-9A-F]{7}$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def names_digest(names) -> str:
    return sha256("".join(name + "\n" for name in sorted(set(names))).encode())


def app_member(archive: zipfile.ZipFile, relative: str) -> bytes:
    roots = sorted({name.split("/")[1] for name in archive.namelist()
                    if name.startswith("Payload/") and name.split("/")[1].endswith(".app")})
    if len(roots) != 1:
        raise SystemExit(f"ERROR: expected one application, found {roots}")
    return archive.read(f"Payload/{roots[0]}/{relative}")


def describe(binary: bytes) -> dict:
    info = macho.parse(binary)
    exports = macho.exported_names(binary, info)
    symbols = macho.symbol_names(binary, info)
    return {
        "sha256": sha256(binary),
        "bytes": len(binary),
        "filetype": info["filetype"],
        "platform": info["platform"],
        "minos": info["minos"],
        "segments": [segment["name"] for segment in info["segments"]],
        "dylibs": sorted(info["dylibs"]),
        "install_name": info["install_name"],
        "exports": len(exports),
        "exports_sha256": names_digest(exports),
        "translated_symbols": sum(1 for name in set(exports) | set(symbols) if TRANSLATED.match(name)),
        "fingerprint_present": (PINS["pack_interface_fingerprint"].encode() + b"\0") in binary,
        "_exports": exports,
    }


def gate(path: Path) -> dict:
    result = game_content_gate.scan(path)
    if not result["passed"]:
        raise SystemExit("ERROR: game content found: " + json.dumps(result["findings"][:5]))
    return {"files": result["files"], "passed": True}


def check_pristine(built: Path, official: Path, report: Path) -> dict:
    reference = PINS["official_game_free_ipa"]
    if sha256(official.read_bytes()) != reference["sha256"]:
        raise SystemExit("ERROR: official reference IPA hash mismatch")
    with zipfile.ZipFile(built) as ours, zipfile.ZipFile(official) as theirs:
        mine = describe(app_member(ours, "KartPad"))
        upstream = describe(app_member(theirs, "KartPad"))
        provenance_ours = app_member(ours, "kartpad-build.json")
        provenance_theirs = app_member(theirs, "kartpad-build.json")
    problems = []
    if upstream["sha256"] != reference["executable_sha256"]:
        problems.append("official executable hash differs from the pin")
    if upstream["exports_sha256"] != reference["export_names_sha256"]:
        problems.append("official export set differs from the pin")
    if provenance_ours != provenance_theirs:
        problems.append("kartpad-build.json differs from the official build record")
    for key in ("filetype", "platform", "minos", "segments", "dylibs", "exports_sha256"):
        if mine[key] != upstream[key]:
            problems.append(f"{key} differs: {mine[key]!r} != {upstream[key]!r}")
    if not mine["fingerprint_present"]:
        problems.append("pack fingerprint missing from the built runtime")
    if mine["translated_symbols"]:
        problems.append(f"{mine['translated_symbols']} translated function symbols")
    content = gate(built)
    result = {
        "mode": "pristine",
        "built": {k: v for k, v in mine.items() if not k.startswith("_")},
        "official": {k: v for k, v in upstream.items() if not k.startswith("_")},
        "byte_identical_executable": mine["sha256"] == upstream["sha256"],
        "build_record_identical": provenance_ours == provenance_theirs,
        "content_gate": content,
        "problems": problems,
        "passed": not problems,
    }
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("built", "official")}, indent=2))
    if problems:
        raise SystemExit("ERROR: pristine build does not reproduce the official runtime interface")
    return result


def check_embedded(framework: Path, official: Path, report: Path, host_commit: str) -> dict:
    embedded = PINS["embedded"]
    binary = (framework / "KartPadCore").read_bytes()
    mine = describe(binary)
    with zipfile.ZipFile(official) as theirs:
        upstream = describe(app_member(theirs, "KartPad"))
    required = set(upstream["_exports"]) - EXECUTABLE_ONLY
    missing = sorted(required - set(mine["_exports"]))
    problems = []
    if mine["filetype"] != 6 or mine["platform"] != 2:
        problems.append("KartPadCore must be an iPhoneOS dylib")
    if mine["install_name"] != embedded["install_name"]:
        problems.append(f"install name {mine['install_name']!r}")
    if missing:
        problems.append(f"{len(missing)} official runtime exports missing, e.g. {missing[:5]}")
    for entry in ("_NeoKartPad_GetAPI", "_NeoKartPad_PrepareUserGame"):
        if entry not in mine["_exports"]:
            problems.append(f"{entry} is not exported")
    if not mine["fingerprint_present"]:
        problems.append("pack fingerprint missing")
    if mine["translated_symbols"]:
        problems.append(f"{mine['translated_symbols']} translated function symbols")
    if any(dylib.startswith(("/opt/homebrew", "/usr/local")) for dylib in mine["dylibs"]):
        problems.append("host-only dependency")
    content = gate(framework)
    identity = {
        "schemaVersion": 1,
        "mode": "game-free-source-build",
        "contains_game_code": False,
        "host_commit": host_commit,
        "kartpad_release": PINS["kartpad"]["release"],
        "kartpad_commit": PINS["kartpad"]["commit"],
        "ios_runtime_commit": PINS["kartpad"]["submodules"]["vendor/runtimes/ios"],
        "translator_commit": PINS["kartpad"]["submodules"]["vendor/wiicompiled"],
        "dolphin_discio_commit": PINS["dolphin_discio"]["commit"],
        "dawn_sha256": PINS["dawn"]["sha256"],
        "abi_version": embedded["neostation_abi"],
        "runtime_identity": embedded["runtime_identity"],
        "pack_abi": 3,
        "pack_interface_fingerprint": PINS["pack_interface_fingerprint"],
        "sha256": mine["sha256"],
        "bytes": mine["bytes"],
        "exports": mine["exports"],
        "official_exports_kept": len(required),
        "architectures": ["arm64"],
    }
    result = {"mode": "embedded", "identity": identity, "content_gate": content,
              "problems": problems, "passed": not problems}
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if problems:
        raise SystemExit("ERROR: embedded KartPadCore failed its identity checks")
    (framework.parent / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pristine", "embedded"))
    parser.add_argument("--built", type=Path, help="pristine: the IPA built from source")
    parser.add_argument("--framework", type=Path, help="embedded: KartPadCore.framework")
    parser.add_argument("--official", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--host-commit", default="")
    args = parser.parse_args()
    if args.mode == "pristine":
        check_pristine(args.built, args.official, args.report)
    else:
        check_embedded(args.framework, args.official, args.report, args.host_commit)
