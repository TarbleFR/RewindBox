#!/usr/bin/env python3
"""Require a NeoStation IPA without KartPad and without any game-origin file.

KartPad left NeoStation on 19 October 2026 (maintainer decision): its runtime
carries code translated from Mario Kart Wii, so each player builds KartPad
themselves as a separate app. This check fails when the IPA still contains any
part of the former embedded port, or when build-utils/game_content_gate.py
finds a file of game origin anywhere in it:

- the old frameworks (KartPadCore, KartPadRuntime, KartPadEngine), the
  kartpad_internal_bridge plugin, a player's game pack (libkartpad_game.dylib)
  or a nested standalone KartPad.app;
- KartPad's identity record and the runtime resources the old port placed at
  the application root (wii_bootstrap/, initial_pipeline_cache.db,
  dsp_coef.bin; Dolphin keeps its own under Sys/GC).
"""
from __future__ import annotations

import argparse
import json
import plistlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build-utils"))
import game_content_gate  # noqa: E402

FORBIDDEN_PREFIXES = (
    "Frameworks/KartPadCore.framework/",
    "Frameworks/KartPadRuntime.framework/",
    "Frameworks/KartPadEngine.framework/",
    "Frameworks/kartpad_internal_bridge.framework/",
    "wii_bootstrap/",
)
FORBIDDEN_FILES = (
    "Frameworks/libkartpad_game.dylib",
    "KartPad-native-identity.json",
    "initial_pipeline_cache.db",
    "dsp_coef.bin",
)


def single_app(archive: zipfile.ZipFile) -> str:
    plists = [name for name in archive.namelist()
              if name.startswith("Payload/") and name.endswith(".app/Info.plist")
              and name.count("/") == 2]
    if len(plists) != 1:
        raise SystemExit(f"ERROR: the IPA must contain one application, found {plists}")
    return plists[0].removesuffix("Info.plist")


def kartpad_members(names: list[str], app: str) -> list[str]:
    found = []
    for name in names:
        if not name.startswith(app):
            continue
        relative = name[len(app):]
        if (relative.startswith(FORBIDDEN_PREFIXES) or relative in FORBIDDEN_FILES
                or "KartPad.app/" in relative):
            found.append(relative)
    return found


def validate(ipa: Path, build_number: str | None) -> dict:
    with zipfile.ZipFile(ipa) as archive:
        app = single_app(archive)
        if build_number is not None:
            info = plistlib.loads(archive.read(app + "Info.plist"))
            if str(info.get("CFBundleVersion")) != str(build_number):
                raise SystemExit(
                    f"ERROR: CFBundleVersion {info.get('CFBundleVersion')} is not {build_number}")
        leftovers = kartpad_members(archive.namelist(), app)
        members = len(archive.namelist())
    content = game_content_gate.scan(ipa)
    result = {
        "ipa": ipa.name,
        "kartpadMembers": leftovers,
        "contentGate": {"members": members, "findings": content["findings"][:50],
                        "passed": content["passed"]},
        "passed": not leftovers and content["passed"],
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipa", type=Path)
    parser.add_argument("--build-number")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.ipa, args.build_number)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "contentGate"}, indent=2))
    for finding in result["contentGate"]["findings"][:20]:
        print(f"  game content: {finding['path']}: {finding['reason']} {finding['detail']}")
    if not result["passed"]:
        raise SystemExit("ERROR: the IPA still contains KartPad or a file of game origin")
    print(f"No KartPad and no game-origin file in {args.ipa.name} "
          f"({result['contentGate']['members']} members inspected).")
