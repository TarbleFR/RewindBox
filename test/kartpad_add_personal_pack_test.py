"""add_personal_pack.py adds only a matching pack, only in a private folder.

Synthetic inputs only (no game byte): a NeoStation IPA carrying a stand-in
game-free runtime and its identity, and a stand-in pack Mach-O built like
test/kartpad_personal_pack_test.py. Checks: the pack lands at
Frameworks/libkartpad_game.dylib with mode 0755 and every other member is
unchanged; inputs are never modified; a pack for another runtime fingerprint,
a public KartPad IPA without pack, an IPA that already has a pack, a runtime
whose identity is not game-free, an existing output, an output inside a Git
repository and an output in a synchronised folder are refused.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import plistlib
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("add_personal_pack", ROOT / "tools/kartpad/add_personal_pack.py")
tool = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tool
spec.loader.exec_module(tool)

FINGERPRINT = "47d67acd0c1ac5e7736cb1a6159425ab7663e4d3a2d5dec28aee1c507fdac58e"
OTHER = "35ccf81c6a555b043cfbfa25fa62c8e335c7dfac21623a304b24dfbcbb623f52"


def pack(fingerprint: str = FINGERPRINT) -> bytes:
    data = bytearray(1024)
    struct.pack_into('<8I', data, 0, 0xFEEDFACF, 0x0100000C, 0, 6, 3, 120, 0, 0)
    struct.pack_into('<2I16s4Q4I', data, 32, 0x19, 72, b'__DATA', 0x100000000, 1024, 0, 1024, 3, 3, 0, 0)
    struct.pack_into('<6I', data, 104, 0x32, 24, 2, 0, 0, 0)
    strings = b'\0_kartpad_game_pack_info\0_kartpad_game_pack_fingerprint\0'
    struct.pack_into('<6I', data, 128, 2, 24, 512, 2, 560, len(strings))
    struct.pack_into('<I', data, 256, 3)
    struct.pack_into('<IBBHQ', data, 512, 1, 0x0F, 1, 0, 0x100000100)
    struct.pack_into('<IBBHQ', data, 528, 25, 0x0F, 1, 0, 0x100000000 + 640)
    data[560:560 + len(strings)] = strings
    marker = b'kartpad-pack-fingerprint:' + fingerprint.encode() + b'\0'
    data[640:640 + len(marker)] = marker
    return bytes(data)


def neostation_ipa(path: Path, game_free: bool = True, with_pack: bool = False) -> None:
    runtime = b"\xcf\xfa\xed\xfe runtime \0" + FINGERPRINT.encode() + b"\0"
    identity = {"pack_interface_fingerprint": FINGERPRINT, "contains_game_code": not game_free,
                "sha256": hashlib.sha256(runtime).hexdigest()}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Payload/NeoStation.app/Info.plist", plistlib.dumps({"CFBundleVersion": "490"}))
        archive.writestr("Payload/NeoStation.app/Frameworks/KartPadCore.framework/KartPadCore", runtime)
        archive.writestr("Payload/NeoStation.app/KartPad-runtime-identity.json", json.dumps(identity))
        if with_pack:
            archive.writestr("Payload/NeoStation.app/Frameworks/libkartpad_game.dylib", pack())


def kartpad_ipa(path: Path, payload: bytes | None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Payload/KartPad.app/Info.plist", plistlib.dumps({"CFBundleShortVersionString": "0.8.3"}))
        if payload is not None:
            archive.writestr("Payload/KartPad.app/Frameworks/libkartpad_game.dylib", payload)


def refused(call, needle: str) -> None:
    try:
        call()
    except SystemExit as error:
        assert needle in str(error), (needle, str(error))
        return
    raise AssertionError("expected refusal: " + needle)


with tempfile.TemporaryDirectory() as temporary:
    private = Path(temporary) / "kartpad-private"
    private.mkdir()
    source = private / "NeoStation.ipa"
    personal = private / "KartPad-personal.ipa"
    neostation_ipa(source)
    kartpad_ipa(personal, pack())
    before = (source.read_bytes(), personal.read_bytes())
    output = private / "NeoStation-with-my-pack.ipa"
    result = tool.add_pack(source, personal, output)
    assert result["pack_interface_fingerprint"] == FINGERPRINT and not result["share"]
    assert (source.read_bytes(), personal.read_bytes()) == before
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output) as built:
        names = set(built.namelist())
        assert names == set(original.namelist()) | {"Payload/NeoStation.app/Frameworks/libkartpad_game.dylib"}
        for name in original.namelist():
            assert built.read(name) == original.read(name)
        info = built.getinfo("Payload/NeoStation.app/Frameworks/libkartpad_game.dylib")
        assert built.read(info) == pack() and (info.external_attr >> 16) & 0o777 == 0o755
    assert not list(private.glob("*.partial"))

    # The bare dylib taken from the PadMint IPA is accepted as well.
    dylib = private / "libkartpad_game.dylib"
    dylib.write_bytes(pack())
    tool.add_pack(source, dylib, private / "from-dylib.ipa")

    refused(lambda: tool.add_pack(source, personal, output), "already exists")
    other = private / "other.ipa"
    kartpad_ipa(other, pack(OTHER))
    refused(lambda: tool.add_pack(source, other, private / "o.ipa"), "does not fit this NeoStation runtime")
    public = private / "public.ipa"
    kartpad_ipa(public, None)
    refused(lambda: tool.add_pack(source, public, private / "p.ipa"), "no personal game pack")
    already = private / "already.ipa"
    neostation_ipa(already, with_pack=True)
    refused(lambda: tool.add_pack(already, personal, private / "a.ipa"), "already contains a game pack")
    donor = private / "donor.ipa"
    neostation_ipa(donor, game_free=False)
    refused(lambda: tool.add_pack(donor, personal, private / "d.ipa"), "game-free runtime")

    repository = Path(temporary) / "neostation-clone"
    (repository / ".git").mkdir(parents=True)
    (repository / "out").mkdir()
    refused(lambda: tool.add_pack(source, personal, repository / "out" / "x.ipa"), "Git repository")
    synced = Path(temporary) / "OneDrive" / "Documents"
    synced.mkdir(parents=True)
    refused(lambda: tool.add_pack(source, personal, synced / "x.ipa"), "synchronised")
    refused(lambda: tool.add_pack(source, synced.parent / "KartPad.ipa", private / "s.ipa"), "synchronised")
print("PASS: personal pack added at Frameworks/libkartpad_game.dylib (0755, other members and inputs "
      "unchanged); other fingerprint, public IPA, existing pack, non-game-free runtime, existing output, "
      "Git repository and synchronised folders refused")
