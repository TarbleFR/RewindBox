#!/usr/bin/env python3
"""Refuse Mario Kart Wii code or data in a NeoStation artifact.

NeoStation distributes the KartPad runtime only as built from its public
sources. Code translated from the game (a player's personal pack, the old
0.5.1 donor) and files extracted from a disc must never reach the
repository, a GitHub Actions job output or an IPA. This gate inspects every
file of a directory, ZIP or IPA (including the decompressed bytes of ZIP
members and of .gz files) and fails on any of:

- a known file of game origin, by SHA-256 (disc executables, Retro Rewind
  code and payload, the 0.5.1 donor runtime and its official IPA);
- a file named like game code or a disc image (libkartpad_game.dylib,
  main.dol, StaticR.rel, Code.pul, .iso/.wbfs/.rvz/.wia/.gcz/.ciso...);
- a Wii/GameCube disc header or WBFS/RVZ/WIA/GCZ/CISO container magic;
- markers that only translated game code carries: func_8xxxxxxx translated
  function names, the game's SDK build strings (RVL_SDK), its class names
  from the function map (RKSystem, RKSYS::, CtrlMenu, RaceinfoPlayer), its
  DWC internals (DWCi_), and a personal pack's exported identity string.

The markers were calibrated on real binaries: the official game-free
KartPad 0.8.3 runtime and every non-KartPad image of the NeoStation Build 350
IPA contain none of them; the 0.5.1 donor runtime contains all of them
(29,065 func_8 symbols). A pass is evidence for this artifact only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

KNOWN_GAME_HASHES = {
    "80d18895b39c63bd80f457398bfcbb91b7d16ac116a41a88967e954080155b05": "RMCP01 sys/main.dol",
    "16d9d146112541fefea701ecb5bc1a496f9d50e4a752fbb5b6778e7c6399f67d": "RMCP01 files/rel/StaticR.rel",
    "58f4ac46afdeda4d57aacab361b381ccd95f08c3dbb2779e6e5760b48b1df036": "Retro Rewind 6.13.3 Code.pul",
    "099097a0f85a97c348123d91438438b24b112362f1fb23c94df6a343c5366471": "Retro WFC payload RMCPD00",
    "7e8008b5d38cf824bf034373322bfedaddfe7b1a432e8ed14bd339fe626326b9": "Retro Rewind 6.13.3 archive",
    "ad5c00a0a508bbfcc0dc3eb1ee04a17f10919cde0b5cccd90d1d9e6a31c39eb0": "KartPad 0.5.1 donor runtime (translated game code)",
    "1474809c8e14447c159c30902aaf66b022db89d28a3181d69acfac3467508f58": "KartPad 0.5.1 official IPA (translated game code)",
    "fc035e60610842da6860d23d4a30c1f1c0f019d492469deb8a2ac25ef5822331": "RMCP01 development WBFS image",
}
FORBIDDEN_NAME = re.compile(
    r"(?i)(^|/)(libkartpad_game\.dylib|main\.dol|staticr\.rel|code\.pul|"
    r"payload\.rmcpd00\.bin|[^/]+\.(iso|gcm|wbfs|rvz|wia|gcz|ciso|wad))$")
MARKERS = {
    "translated function name": re.compile(rb"func_8[0-9A-F]{7}"),
    "game SDK build string": re.compile(rb"RVL_SDK"),
    "game class from the function map": re.compile(rb"RKSystem|RKSYS::|CtrlMenu|RaceinfoPlayer"),
    "game DWC internals": re.compile(rb"DWCi_"),
    "personal pack identity": re.compile(rb"kartpad-pack-fingerprint:[0-9a-f]{64}"),
}
MAX_NESTED = 512 * 1024 * 1024


def disc_or_container(data: bytes) -> str | None:
    if len(data) >= 0x20 and data[0x18:0x1C] == bytes.fromhex("5D1C9EA3"):
        return "Wii disc header"
    if len(data) >= 0x20 and data[0x1C:0x20] == bytes.fromhex("C2339F3D"):
        return "GameCube disc header"
    for magic, label in ((b"WBFS", "WBFS image"), (b"RVZ\x01", "RVZ image"),
                         (b"WIA\x01", "WIA image"), (b"CISO", "CISO image")):
        if data.startswith(magic):
            return label
    if data[:4] == bytes.fromhex("B10BC0DE"):
        return "GCZ image"
    return None


def inspect(name: str, data: bytes, findings: list[dict], depth: int = 0) -> None:
    def fail(reason: str, detail: str = "") -> None:
        findings.append({"path": name, "reason": reason, "detail": detail})

    digest = hashlib.sha256(data).hexdigest()
    if digest in KNOWN_GAME_HASHES:
        fail("known file of game origin", KNOWN_GAME_HASHES[digest])
    if FORBIDDEN_NAME.search(name):
        fail("game code or disc image file name")
    container = disc_or_container(data)
    if container:
        fail("disc image", container)
    for reason, pattern in MARKERS.items():
        match = pattern.search(data)
        if match:
            fail(reason, match.group(0)[:48].decode("latin-1"))
    if depth >= 2:
        return
    if data[:4] == b"PK\x03\x04" and len(data) <= MAX_NESTED:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if not member.is_dir() and member.file_size <= MAX_NESTED:
                        inspect(f"{name}!{member.filename}", archive.read(member), findings, depth + 1)
        except zipfile.BadZipFile:
            pass
    elif data[:2] == b"\x1f\x8b" and len(data) <= MAX_NESTED:
        try:
            inspect(f"{name}!gunzip", gzip.decompress(data)[:MAX_NESTED], findings, depth + 1)
        except (OSError, EOFError):
            fail("unreadable gzip member")


def scan(path: Path) -> dict:
    findings: list[dict] = []
    files = 0
    if path.is_dir():
        for item in sorted(p for p in path.rglob("*") if p.is_file()):
            files += 1
            inspect(item.relative_to(path).as_posix(), item.read_bytes(), findings)
    else:
        data = path.read_bytes()
        files += 1
        inspect(PurePosixPath(path.name).as_posix(), data, findings)
    return {"artifact": str(path), "files": files, "findings": findings,
            "passed": not findings}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    results = [scan(path) for path in args.paths]
    if args.report:
        args.report.write_text(json.dumps(results, indent=2) + "\n")
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status}: {result['artifact']} ({result['files']} files, "
              f"{len(result['findings'])} findings)")
        for finding in result["findings"][:20]:
            print(f"  {finding['path']}: {finding['reason']} {finding['detail']}")
    sys.exit(0 if all(result["passed"] for result in results) else 1)
