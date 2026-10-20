"""validate_no_dusklight_ipa.py refuses any part of Dusklight or of the Ports playlist.

Synthetic IPAs only: a clean app passes with the historical credits in its
notices and NeoSwap's owner label table; each removed member (Core framework
and resources, bridge plugin, identity, notices, Ports assets), the word in any
binary, plist, JSON, asset manifest or compressed Flutter NOTICES, a second
NeoSwap occurrence and a wrong build number are refused. The real published
0.0.8 IPA (Build 480, Dusklight embedded) was refused on 60 members when this
check was written (docs/ports-removal-2026-10-20.md).
"""
from __future__ import annotations

import gzip
import plistlib
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build-utils"))
import validate_no_dusklight_ipa as validator  # noqa: E402

APP = "Payload/NeoStation.app/"
ASSETS = "Frameworks/App.framework/flutter_assets/"
TABLE = b"budget\x00rpcs3\x00dolphin\x00armsx2\x00dusklight\x00kartpad\x00probe\x00owner"
CLEAN = {
    "Info.plist": plistlib.dumps({"CFBundleVersion": "492"}),
    "Runner": b"\xcf\xfa\xed\xfe DolphinInternalBridgePlugin\x00Rpcs3InternalBridgePlugin\x00",
    "Frameworks/App.framework/App": b"\xcf\xfa\xed\xfe ios_dolphin_internal ios_rpcs3_internal",
    ASSETS + "AssetManifest.bin": b"assets/systems/gc.json\x00assets/systems/wii.json",
    ASSETS + "NOTICES.Z": gzip.compress(b"flutter\nMIT License"),
    ASSETS + "assets/systems/gc.json": b'{"system":{"id":"gc"}}',
    ASSETS + "assets/legal/THIRD_PARTY_NOTICES.md": b"Dusklight, embedded in earlier builds only.",
    "Frameworks/neo_swap.framework/neo_swap": TABLE,
    "Legal/NeoStation-NOTICE.md": b"DUSKLIGHT \xe2\x80\x94 FORMERLY EMBEDDED, REMOVED",
    "Legal/LEGAL_AND_CREDITS.md": b"| **Dusklight** (earlier builds only) |",
    "Legal/BUILD_SOURCE_IDENTITY.json": b'{"schema": 1, "armsx2": {}}',
}
REMOVED = {
    "Frameworks/DusklightCore.framework/DusklightCore": b"core",
    "Frameworks/DusklightCore.framework/res/logo.png": b"png",
    "Frameworks/dusklight_internal_bridge.framework/dusklight_internal_bridge": b"bridge",
    "Dusklight-native-identity.json": b"{}",
    "Dusklight-Licenses/aurora-LICENSE": b"MIT",
    "Legal/Dusklight-CC0-1.0.txt": b"CC0",
    "Legal/Dusklight-Dependency-Licenses/SDL-LICENSE.txt": b"zlib",
    ASSETS + "assets/legal/Dusklight-CC0-1.0.txt": b"CC0",
    ASSETS + "assets/systems/ports.json": b'{"system":{"id":"ports"}}',
    ASSETS + "assets/images/ports-gaming.webp": b"RIFF",
}
WORD_IN = {
    "Runner": b"\xcf\xfa\xed\xfe\x00DusklightInternalBridgePlugin\x00",
    "Frameworks/App.framework/App": b"\xcf\xfa\xed\xfe neostation/dusklight_internal",
    "Frameworks/Other.framework/Info.plist": b"<string>NeoDusklightControls</string>",
    "Legal/BUILD_SOURCE_IDENTITY.json": b'{"dusklight": {"revision": "40457c6a"}}',
    ASSETS + "NOTICES.Z": gzip.compress(b"Dusklight\nCC0"),
    "Frameworks/neo_swap.framework/neo_swap": TABLE + b"\x00dusklight-session\x00",
}


def ipa(directory: Path, members: dict[str, bytes], name: str = "case.ipa") -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, data in members.items():
            archive.writestr(APP + member, data)
    return path


with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    clean = validator.validate(ipa(work, CLEAN), "492")
    assert clean["passed"] and clean["findings"] == {}, clean
    assert clean["membersInspected"] == len(CLEAN)
    assert clean["allowedHistoricalOrAbi"] == sorted([
        ASSETS + "assets/legal/THIRD_PARTY_NOTICES.md", "Frameworks/neo_swap.framework/neo_swap",
        "Legal/LEGAL_AND_CREDITS.md", "Legal/NeoStation-NOTICE.md"]), clean
    try:
        validator.validate(ipa(work, CLEAN, "wrong.ipa"), "491")
        raise AssertionError("a wrong build number must be refused")
    except SystemExit:
        pass

    for relative, data in REMOVED.items():
        outcome = validator.validate(ipa(work, {**CLEAN, relative: data}), "492")
        assert not outcome["passed"] and list(outcome["findings"]) == [relative], (relative, outcome)

    for relative, data in WORD_IN.items():
        outcome = validator.validate(ipa(work, {**CLEAN, relative: data}), "492")
        assert not outcome["passed"] and list(outcome["findings"]) == [relative], (relative, outcome)

    manifest = ASSETS + "AssetManifest.bin"
    outcome = validator.validate(ipa(work, {**CLEAN, manifest: CLEAN[manifest] + b"\x00assets/systems/ports.json"}), "492")
    assert outcome["findings"] == {manifest: ["asset manifest lists assets/systems/ports.json"]}, outcome

print(f"PASS: Dusklight-free IPA validator — clean app with historical credits and NeoSwap's ABI "
      f"label, {len(REMOVED)} removed members, {len(WORD_IN)} hidden occurrences, the Ports asset "
      f"manifest entry and a wrong build refused")
