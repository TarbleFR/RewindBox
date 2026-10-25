"""The game content gate refuses game code/data and accepts the game-free runtime.

Synthetic fixtures only: no game byte is needed to exercise each rule. The
real calibration (official game-free 0.8.3 IPA and Build 350 native subset
pass, Build 350 IPA with the 0.5.1 donor fails) is recorded in
docs/kartpad-runtime083-integration.md.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("game_content_gate", ROOT / "build-utils/game_content_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

FINGERPRINT = "47d67acd0c1ac5e7736cb1a6159425ab7663e4d3a2d5dec28aee1c507fdac58e"
CLEAN_RUNTIME = (b"\xcf\xfa\xed\xfe" + b"\0" * 64 + b"Rebuild it with PadMint.\0" + FINGERPRINT.encode()
                 + b"\0kartpad-pack-fingerprint:\0Mario Kart Wii\0RMCP01\0")


def zipped(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def reasons(name: str, data: bytes) -> set[str]:
    findings: list[dict] = []
    gate.inspect(name, data, findings)
    return {finding["reason"] for finding in findings}


assert reasons("Frameworks/KartPadRuntime.framework/KartPadRuntime", CLEAN_RUNTIME) == set()
assert reasons("Payload/X.app/X", b"\0" * 0x30) == set()
cases = {
    "translated function name": CLEAN_RUNTIME + b"_func_8000951C",
    "game SDK build string": CLEAN_RUNTIME + b"<< RVL_SDK - OS release build >>",
    "game class from the function map": CLEAN_RUNTIME + b"RKSYS::LicenseMgr",
    "game DWC internals": CLEAN_RUNTIME + b"DWCi_Auth_GetGameSpyToken",
    "personal pack identity": CLEAN_RUNTIME + b"kartpad-pack-fingerprint:" + FINGERPRINT.encode(),
}
for reason, data in cases.items():
    assert reason in reasons("Frameworks/x.dylib", data), reason
wii = bytearray(0x40)
wii[0x18:0x1C] = bytes.fromhex("5D1C9EA3")
assert "disc image" in reasons("Documents/whatever.bin", bytes(wii))
gamecube = bytearray(0x40)
gamecube[0x1C:0x20] = bytes.fromhex("C2339F3D")
assert "disc image" in reasons("x.bin", bytes(gamecube))
for magic in (b"WBFS", b"RVZ\x01", b"WIA\x01", b"CISO", bytes.fromhex("B10BC0DE")):
    assert "disc image" in reasons("x.bin", magic + b"\0" * 64), magic
for name in ("Payload/NeoStation.app/Frameworks/libkartpad_game.dylib", "GameData/sys/main.dol",
             "files/rel/StaticR.rel", "RetroRewind6/Binaries/Code.pul", "game.WBFS", "mkw.rvz"):
    assert "game code or disc image file name" in reasons(name, b"x"), name

# Known files of game origin are recognised by SHA-256.
synthetic = b"synthetic stand-in for a game file"
gate.KNOWN_GAME_HASHES[hashlib.sha256(synthetic).hexdigest()] = "test entry"
assert "known file of game origin" in reasons("innocent.bin", synthetic)

# Nested archives: IPA members and gzip resources are scanned decompressed.
ipa = zipped({"Payload/NeoStation.app/Frameworks/KartPadRuntime.framework/KartPadRuntime": CLEAN_RUNTIME,
              "Payload/NeoStation.app/catalogue.json.gz": gzip.compress(b'{"name":"RKSystem"}')})
findings: list[dict] = []
gate.inspect("NeoStation.ipa", ipa, findings)
assert [f["path"] for f in findings] == ["NeoStation.ipa!Payload/NeoStation.app/catalogue.json.gz!gunzip"], findings
inner = zipped({"Payload/NeoStation.app/Frameworks/libkartpad_game.dylib": b"pack"})
findings = []
gate.inspect("outer.zip", zipped({"NeoStation.ipa": inner}), findings)
assert findings and findings[0]["path"].endswith("libkartpad_game.dylib"), findings

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / "clean").mkdir()
    (root / "clean" / "KartPadRuntime").write_bytes(CLEAN_RUNTIME)
    assert gate.scan(root / "clean")["passed"]
    (root / "clean" / "pack").mkdir()
    (root / "clean" / "pack" / "libkartpad_game.dylib").write_bytes(b"\0")
    result = gate.scan(root / "clean")
    assert not result["passed"] and result["files"] == 2
print("PASS: game content gate — game-free runtime accepted (bare fingerprint, pack prefix, title and "
      "disc ID text), 5 translated-code markers, 2 disc headers, 5 container magics, 6 file names, "
      "known hashes, nested IPA/ZIP/gzip members and directories refused")
