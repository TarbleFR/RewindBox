"""validate_no_kartpad_ipa.py refuses any part of the former KartPad port.

Synthetic IPAs only (no game data): a clean app passes, Dolphin's own
Sys/GC/dsp_coef.bin is allowed, and each KartPad leftover (frameworks, bridge,
personal pack, nested app, identity, root runtime resources) or any member
carrying a game-origin marker is refused, as is a wrong build number.
"""
from __future__ import annotations

import io
import plistlib
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build-utils"))
import validate_no_kartpad_ipa as validator  # noqa: E402

APP = "Payload/Runner.app/"
CLEAN = {
    APP + "Info.plist": plistlib.dumps({"CFBundleVersion": "491"}),
    APP + "Runner": b"\xcf\xfa\xed\xfe runner",
    APP + "Frameworks/DusklightCore.framework/DusklightCore": b"dusklight",
    APP + "Frameworks/dusklight_internal_bridge.framework/dusklight_internal_bridge": b"bridge",
    APP + "Sys/GC/dsp_coef.bin": b"\0" * 4096,
    APP + "Legal/NeoStation-NOTICE.md": b"KartPad was embedded in earlier builds only.",
}
LEFTOVERS = {
    "Frameworks/KartPadCore.framework/KartPadCore": b"core",
    "Frameworks/KartPadRuntime.framework/KartPadRuntime": b"runtime",
    "Frameworks/KartPadEngine.framework/KartPadEngine": b"engine",
    "Frameworks/kartpad_internal_bridge.framework/kartpad_internal_bridge": b"bridge",
    "Frameworks/libkartpad_game.dylib": b"pack",
    "PlugIns/Mods.appex/KartPad.app/KartPad": b"nested",
    "KartPad-native-identity.json": b"{}",
    "wii_bootstrap/shared2/wc24/misc.bin": b"\0" * 16,
    "initial_pipeline_cache.db": b"SQLite format 3\0",
    "dsp_coef.bin": b"\0" * 4096,
}


def ipa(directory: Path, members: dict[str, bytes], name: str = "case.ipa") -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, data in members.items():
            archive.writestr(member, data)
    return path


def refused(path: Path, build: str | None = "491") -> bool:
    try:
        return not validator.validate(path, build)["passed"]
    except SystemExit:
        return True


with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    clean = ipa(work, CLEAN)
    result = validator.validate(clean, "491")
    assert result["passed"] and result["kartpadMembers"] == [], result
    assert result["contentGate"]["members"] == len(CLEAN)
    assert refused(clean, "490"), "a wrong build number must be refused"

    for relative, data in LEFTOVERS.items():
        case = ipa(work, {**CLEAN, APP + relative: data})
        outcome = validator.validate(case, "491")
        assert not outcome["passed"] and outcome["kartpadMembers"] == [relative], (relative, outcome)

    marker = ipa(work, {**CLEAN, APP + "Frameworks/Other.framework/Other": b"x func_8000951C x"})
    outcome = validator.validate(marker, "491")
    assert not outcome["passed"] and outcome["kartpadMembers"] == [], outcome
    assert outcome["contentGate"]["findings"][0]["reason"] == "translated function name", outcome

    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as inner:
        inner.writestr("sys/main.dol", b"dol")
    hidden = ipa(work, {**CLEAN, APP + "Resources/archive.zip": nested.getvalue()})
    assert refused(hidden), "a disc file inside a nested archive must be refused"

print(f"PASS: KartPad-free IPA validator — clean app, Dolphin Sys/GC allowed, "
      f"{len(LEFTOVERS)} KartPad leftovers, a game marker, a nested disc file and a wrong build refused")
