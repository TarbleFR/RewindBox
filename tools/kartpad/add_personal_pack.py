#!/usr/bin/env python3
"""Add your own KartPad game pack to your copy of the NeoStation IPA.

Run this on your own computer, before your sideloading tool (SideStore,
AltStore, Sideloadly...) signs the app. It never connects to the network,
never uploads anything and never changes its inputs. It only works in a
private folder that is outside any Git repository and outside folders that
are synchronised to a cloud service.

Inputs:
- the NeoStation IPA you were given (game-free: its KartPad runtime is built
  from KartPad's public sources and contains no game code);
- your personal KartPad iOS IPA built by PadMint from your own Mario Kart Wii
  PAL RMCP01 revision 0 disc, or the libkartpad_game.dylib taken from it.

The pack is accepted only if its exported interface fingerprint equals the
fingerprint of the runtime inside this NeoStation IPA. It is then written to
Payload/<app>/Frameworks/libkartpad_game.dylib, where the sideloading tool
signs it together with the app, and where NeoStation looks for it.

The output contains code translated from your disc. Keep it for yourself:
do not share it, upload it, or put it in a synchronised or versioned folder.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PACK_NAME = "libkartpad_game.dylib"
IDENTITY_NAME = "KartPad-runtime-identity.json"
RUNTIME_BINARY = "Frameworks/KartPadCore.framework/KartPadCore"
MAX_PACK = 256 * 1024 * 1024
SYNC_MARKERS = re.compile(
    r"(?i)(onedrive|dropbox|google ?drive|googledrive|icloud ?drive|mobile documents|"
    r"box sync|pcloud|mega(sync)?|nextcloud|owncloud|syncthing|seafile|yandex\.?disk)")


def load_inspector():
    spec = importlib.util.spec_from_file_location(
        "inspect_personal_pack", ROOT / "build-utils/kartpad/inspect_personal_pack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refuse_unsafe_location(path: Path, label: str) -> None:
    resolved = path.resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            raise SystemExit(f"ERROR: {label} is inside a Git repository ({parent}). "
                             "Use a private folder outside any repository.")
    if SYNC_MARKERS.search(str(resolved)):
        raise SystemExit(f"ERROR: {label} looks like a cloud-synchronised folder ({resolved}). "
                         "Use a private local folder that is not synchronised.")


def application_root(archive: zipfile.ZipFile) -> str:
    roots = sorted({name.split("/")[1] for name in archive.namelist()
                    if name.startswith("Payload/") and name.count("/") >= 2
                    and name.split("/")[1].endswith(".app")})
    if len(roots) != 1:
        raise SystemExit(f"ERROR: expected one application in the IPA, found {roots}")
    return f"Payload/{roots[0]}/"


def runtime_fingerprint(archive: zipfile.ZipFile, app: str) -> str:
    try:
        identity = json.loads(archive.read(app + IDENTITY_NAME))
        runtime = archive.read(app + RUNTIME_BINARY)
    except KeyError as missing:
        raise SystemExit(f"ERROR: this NeoStation IPA has no game-free KartPad runtime ({missing})")
    fingerprint = identity.get("pack_interface_fingerprint", "")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise SystemExit("ERROR: the runtime identity has no pack interface fingerprint")
    if identity.get("contains_game_code") is not False:
        raise SystemExit("ERROR: the runtime identity does not declare a game-free runtime")
    if hashlib.sha256(runtime).hexdigest() != identity.get("sha256"):
        raise SystemExit("ERROR: the KartPad runtime does not match its identity")
    if fingerprint.encode() + b"\0" not in runtime:
        raise SystemExit("ERROR: the KartPad runtime does not carry its declared fingerprint")
    return fingerprint


def read_pack(path: Path) -> bytes:
    if path.suffix.lower() == ".ipa":
        with zipfile.ZipFile(path) as archive:
            app = application_root(archive)
            candidates = [app + "Frameworks/" + PACK_NAME, app + PACK_NAME]
            found = [name for name in candidates if name in archive.namelist()]
            if len(found) != 1:
                raise SystemExit("ERROR: this KartPad IPA has no personal game pack. Build it with "
                                 "PadMint from your own disc; the public KartPad IPA has no pack.")
            info = archive.getinfo(found[0])
            if info.file_size > MAX_PACK:
                raise SystemExit("ERROR: the game pack is larger than expected")
            return archive.read(info)
    if path.name != PACK_NAME:
        raise SystemExit(f"ERROR: expected a PadMint IPA or a file named {PACK_NAME}")
    if path.stat().st_size > MAX_PACK:
        raise SystemExit("ERROR: the game pack is larger than expected")
    return path.read_bytes()


def add_pack(neostation_ipa: Path, personal: Path, output: Path) -> dict:
    # The NeoStation IPA is game-free and may come from anywhere. Your KartPad
    # IPA and the output contain code translated from your disc.
    refuse_unsafe_location(personal, "your KartPad IPA")
    refuse_unsafe_location(output.parent, "the output folder")
    if output.exists():
        raise SystemExit(f"ERROR: {output} already exists; choose another name")
    if output.resolve() in (neostation_ipa.resolve(), personal.resolve()):
        raise SystemExit("ERROR: the output must be a new file")
    inspector = load_inspector()
    pack = read_pack(personal)
    with zipfile.ZipFile(neostation_ipa) as source:
        app = application_root(source)
        if any(PurePosixPath(name).name == PACK_NAME for name in source.namelist()):
            raise SystemExit("ERROR: this NeoStation IPA already contains a game pack")
        fingerprint = runtime_fingerprint(source, app)
        try:
            checked = inspector.inspect_macho(pack, {"pack_abi": 3,
                                                     "pack_interface_fingerprint": fingerprint})
        except ValueError as error:
            raise SystemExit(f"ERROR: your pack does not fit this NeoStation runtime: {error}. "
                             "Rebuild it with the PadMint release that matches this KartPad version.")
        temporary = output.with_name(output.name + ".partial")
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    target.writestr(info, source.read(info))
                entry = zipfile.ZipInfo(app + "Frameworks/" + PACK_NAME, date_time=(1980, 1, 1, 0, 0, 0))
                entry.external_attr = (0o100755 << 16)
                entry.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(entry, pack)
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
    return {"output": str(output), "pack_sha256": checked["pack_sha256"],
            "pack_bytes": checked["pack_bytes"], "pack_interface_fingerprint": fingerprint,
            "personal_build": True, "share": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("neostation_ipa", type=Path)
    parser.add_argument("personal_kartpad", type=Path,
                        help="your PadMint KartPad IPA or its libkartpad_game.dylib")
    parser.add_argument("output", type=Path,
                        help="new IPA to create in your private folder")
    args = parser.parse_args()
    result = add_pack(args.neostation_ipa, args.personal_kartpad, args.output)
    print(json.dumps(result, indent=2))
    print("Done. Sign and install this IPA with your sideloading tool. "
          "It contains code translated from your own disc: keep it private.", file=sys.stderr)
