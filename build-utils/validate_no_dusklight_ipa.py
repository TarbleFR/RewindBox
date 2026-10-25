#!/usr/bin/env python3
"""Require a NeoStation IPA without Dusklight and without the Ports playlist.

Dusklight (a reimplementation of The Legend of Zelda: Twilight Princess built
on its decompilation) and the Ports playlist that launched it left NeoStation
on 20 October 2026 (maintainer decision, docs/ports-removal-2026-10-20.md).
This check fails when the IPA still holds any of it:

- a member whose path names Dusklight (its Core framework and resources,
  bridge plugin, identity record, notices and dependency notices);
- the Ports playlist assets (assets/systems/ports.json, its background);
- the bytes "dusklight" (any case) inside any other member: executables,
  frameworks, the Dart snapshot, plists, JSON, the asset manifest and the
  gzip-compressed Flutter NOTICES included.

Two places may still carry the word, and only as stated:
- Frameworks/neo_swap.framework/neo_swap: NeoSwap's owner label table
  ("rpcs3", "dolphin", "armsx2", "dusklight", "kartpad", "probe"), an ABI
  shared with the pinned RPCS3 Core whose value 3 has no producer any more;
  exactly one occurrence, in that table;
- text notices under Legal/ and the bundled assets/legal/: the credit kept
  for the earlier builds that embedded Dusklight.
"""
from __future__ import annotations

import argparse
import gzip
import json
import plistlib
import re
import zipfile
from pathlib import Path

WORD = re.compile(rb"(?i)dusklight")
FLUTTER_ASSETS = "Frameworks/App.framework/flutter_assets/"
PORTS_ASSETS = (
    FLUTTER_ASSETS + "assets/systems/ports.json",
    FLUTTER_ASSETS + "assets/images/ports-gaming.webp",
)
# Asset keys of the Ports playlist, as the asset manifest lists them.
PORTS_KEYS = (b"assets/systems/ports.json", b"assets/images/ports-gaming.webp")
NEOSWAP = "Frameworks/neo_swap.framework/neo_swap"
NEOSWAP_OWNER_TABLE = b"\x00rpcs3\x00dolphin\x00armsx2\x00dusklight\x00kartpad\x00probe\x00"
NOTICE_SUFFIXES = (".md", ".txt")
# Immutable legal/source audit generated when native ports were removed.
# It documents the former component but cannot load or expose it at runtime.
HISTORICAL_LEGAL_RECORDS = {
    "Legal/Sources/Reviews/modified-sources-since-0.0.8-2026-10-21.json",
}


def single_app(archive: zipfile.ZipFile) -> str:
    plists = [name for name in archive.namelist()
              if name.startswith("Payload/") and name.endswith(".app/Info.plist")
              and name.count("/") == 2]
    if len(plists) != 1:
        raise SystemExit(f"ERROR: the IPA must contain one application, found {plists}")
    return plists[0].removesuffix("Info.plist")


def notice(relative: str) -> bool:
    return (relative in HISTORICAL_LEGAL_RECORDS
            or (relative.startswith(("Legal/", FLUTTER_ASSETS + "assets/legal/"))
                and relative.lower().endswith(NOTICE_SUFFIXES)))


def findings_of(relative: str, data: bytes) -> list[str]:
    if relative.endswith("NOTICES.Z") and data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    found = []
    if relative.endswith("AssetManifest.bin") or relative.endswith("AssetManifest.json"):
        found += [f"asset manifest lists {key.decode()}" for key in PORTS_KEYS if key in data]
    hits = len(WORD.findall(data))
    if not hits or notice(relative):
        return found
    if relative == NEOSWAP and hits == 1 and data.count(NEOSWAP_OWNER_TABLE) == 1:
        return found
    found.append(f"{hits} occurrence(s) of 'dusklight'")
    return found


def validate(ipa: Path, build_number: str | None) -> dict:
    members: dict[str, list[str]] = {}
    allowed: list[str] = []
    with zipfile.ZipFile(ipa) as archive:
        app = single_app(archive)
        if build_number is not None:
            info = plistlib.loads(archive.read(app + "Info.plist"))
            if str(info.get("CFBundleVersion")) != str(build_number):
                raise SystemExit(
                    f"ERROR: CFBundleVersion {info.get('CFBundleVersion')} is not {build_number}")
        inspected = 0
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith(app):
                continue
            relative = entry.filename[len(app):]
            inspected += 1
            if "dusklight" in relative.lower() or relative in PORTS_ASSETS:
                members.setdefault(relative, []).append("removed component")
                continue
            data = archive.read(entry)
            found = findings_of(relative, data)
            if found:
                members[relative] = found
            elif WORD.search(data):
                allowed.append(relative)
    return {
        "ipa": ipa.name,
        "membersInspected": inspected,
        "findings": members,
        "allowedHistoricalOrAbi": sorted(allowed),
        "passed": not members,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipa", type=Path)
    parser.add_argument("--build-number")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.ipa, args.build_number)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    for relative, found in list(result["findings"].items())[:40]:
        print(f"  {relative}: {'; '.join(found)}")
    print(json.dumps({key: value for key, value in result.items() if key != "findings"}, indent=2))
    if not result["passed"]:
        raise SystemExit(f"ERROR: the IPA still contains Dusklight or the Ports playlist "
                         f"({len(result['findings'])} members)")
    print(f"No Dusklight and no Ports playlist in {args.ipa.name} "
          f"({result['membersInspected']} members inspected).")
