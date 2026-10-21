#!/usr/bin/env python3
"""Embed NeoStation and third-party legal notices into a built iOS app.

This affects future builds only. It never rewrites an existing IPA asset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL_ASSETS = ROOT / "assets" / "legal"

REQUIRED_LEGAL_FILES = (
    "THIRD_PARTY_NOTICES.md",
    "Dolphin-COPYING.txt",
    "RPCS3-GPL-2.0.txt",
    "ARMSX2-GPL-3.0.txt",
    "StikJIT-MPL-2.0.txt",
    "NeoStation-Assets-CC-BY-NC-SA-4.0.txt",
    "RiiSU-ATTRIBUTION.md",
    "Canvas-ES-DE-ATTRIBUTION.md",
    "NeoStation-GPL-3.0.txt",
    "GameDB-PS3-GPL-3.0.txt",
    "Guest-Page-Relay-MIT.txt",
    "OnceUponATime-CC0-1.0.txt",
    # Build 450: the shader compilers vendored by neo_shader_kit.
    "glslang-LICENSE.txt",
    "SPIRV-Cross-Apache-2.0.txt",
)
# The Khronos SDK tag both shader compilers are vendored at
# (packages/neo_shader_kit/ios/ThirdParty/*/SOURCE.txt).
SHADER_COMPILERS_TAG = "vulkan-sdk-1.4.350.1"

# Notices for components actually used by the delivered integration. MeloNX
# remains staged source work and is deliberately absent from this collection.
ADDITIONAL_NOTICE_COLLECTIONS = (
    ("textures", "Textures"),
    ("ppsspp", "PPSSPP"),
)
CATALOG_CREDIT_DOCUMENTS = (
    "CHEAT_CATALOG_SOURCES.md",
    "OVERLAY_SOURCES_AND_CREDITS.md",
    "HD_TEXTURE_CATALOG_SOURCES.md",
    "HD_TEXTURE_SOURCES_AND_CREDITS.md",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require_pinned_header(path: Path, expected: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker = f"Pinned revision/tag: {expected}"
    if marker not in text:
        raise SystemExit(
            f"Legal notice {path.relative_to(ROOT)} is stale: expected {marker!r}"
        )


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def validate_libretro_notices() -> dict[str, str]:
    """Return verified notice hashes, without claiming binary-source equivalence."""
    directory = LEGAL_ASSETS / "libretro"
    manifest = load_json(directory / "license-sources.json")
    cores = load_json(ROOT / "build-utils/libretro/cores.json")["cores"]
    expected = {core["id"] for core in cores}
    covered = [core for component in manifest["components"]
               for core in component["cores"]]
    if set(covered) != expected or len(covered) != len(set(covered)):
        raise SystemExit("Libretro notice coverage differs from the core catalog")
    entries = list(manifest["support_files"])
    for component in manifest["components"]:
        if not component["files"]:
            raise SystemExit(f"Missing license text: {component['component']}")
        entries.extend(component["files"])
        for core in cores:
            if core["id"] in component["cores"] and "release" in core:
                if component["license_reference_revision"] != core["release"]["commit"]:
                    raise SystemExit(f"Stale release license reference: {core['id']}")
    hashes = {}
    for entry in entries:
        name = entry["path"]
        if not name or Path(name).name != name or "\\" in name or name in hashes:
            raise SystemExit(f"Invalid or duplicate Libretro notice path: {name}")
        path = directory / name
        if not path.is_file() or not path.stat().st_size:
            raise SystemExit(f"Missing or empty Libretro notice: {name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise SystemExit(f"Changed Libretro notice: {name}")
        hashes[name] = digest
    for name in ("license-sources.json", "LIBRETRO_CORES.md"):
        path = directory / name
        if not path.is_file() or not path.stat().st_size:
            raise SystemExit(f"Missing or empty Libretro attribution record: {name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def validate_additional_notices() -> dict[str, tuple[Path, str]]:
    """Collect exact notice bytes, not an assertion of binary/source identity."""
    result: dict[str, tuple[Path, str]] = {}

    def add(source: Path, target: str, expected: str | None = None) -> None:
        if target in result:
            raise SystemExit(f"Duplicate additional notice: {target}")
        if not source.is_file() or not source.stat().st_size:
            raise SystemExit(f"Missing or empty additional notice: {target}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if expected is not None and digest != expected:
            raise SystemExit(f"Changed additional notice: {target}")
        result[target] = (source, digest)

    def filename(name: str) -> str:
        if not name or Path(name).name != name or "\\" in name or name in (".", ".."):
            raise SystemExit(f"Invalid additional notice path: {name}")
        return name

    for folder, target in ADDITIONAL_NOTICE_COLLECTIONS:
        directory = LEGAL_ASSETS / folder
        manifest_path = directory / "license-sources.json"
        if not manifest_path.is_file():
            raise SystemExit(f"Missing additional notice manifest: {folder}")
        manifest = load_json(manifest_path)
        if manifest.get("schema") != 1 or not manifest.get("components"):
            raise SystemExit(f"Invalid additional notice manifest: {folder}")
        for component in manifest["components"]:
            if not component.get("files"):
                raise SystemExit(f"Missing additional notice entries: {folder}")
            for entry in component["files"]:
                name = filename(entry["path"])
                digest = entry.get("sha256")
                if (not isinstance(digest, str) or len(digest) != 64
                        or any(c not in "0123456789abcdef" for c in digest)):
                    raise SystemExit(f"Invalid additional notice digest: {folder}/{name}")
                add(directory / name, f"{target}/{name}", digest)
                # Check duplicate notices against the existing native bundle
                # when the manifest explicitly identifies that local original.
                if entry.get("copied_from"):
                    original = (ROOT / entry["copied_from"]).resolve()
                    if not original.is_relative_to(ROOT) or not original.is_file():
                        raise SystemExit(f"Missing original notice: {folder}/{name}")
                    if hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                        raise SystemExit(f"Stale copied notice: {folder}/{name}")
        add(manifest_path, f"{target}/license-sources.json")

    cheat_directory = ROOT / "docs/licenses/cheats"
    cheat_manifest = cheat_directory / "provenance.json"
    if not cheat_manifest.is_file():
        raise SystemExit("Missing additional notice manifest: cheats")
    cheat_entries = load_json(cheat_manifest).get("files", [])
    if not cheat_entries:
        raise SystemExit("Missing additional notice entries: cheats")
    for entry in cheat_entries:
        name = filename(entry["local_file"])
        add(cheat_directory / name, f"Cheats/{name}", entry["preserved_sha256"])
    add(cheat_manifest, "Cheats/provenance.json")
    add(cheat_directory / "README.md", "Cheats/README.md")

    for name in CATALOG_CREDIT_DOCUMENTS:
        add(ROOT / "docs" / name, f"Catalogs/{name}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path)
    parser.add_argument("--build-number")
    parser.add_argument("--dolphin-sha", required=True)
    parser.add_argument("--validate-only", action="store_true",
                        help="Check source notices without requiring or writing an app bundle")
    args = parser.parse_args()

    if not args.validate_only:
        if args.app is None or args.build_number is None:
            parser.error("--app and --build-number are required when embedding notices")
        app = args.app.resolve()
        if not app.is_dir() or app.suffix != ".app":
            raise SystemExit(f"Expected built .app bundle, got: {app}")

    for name in REQUIRED_LEGAL_FILES:
        path = LEGAL_ASSETS / name
        if not path.is_file() or not path.stat().st_size:
            raise SystemExit(f"Missing or empty legal bundle file: assets/legal/{name}")

    libretro_notices = validate_libretro_notices()
    additional_notices = validate_additional_notices()

    rpcs3 = load_json(ROOT / "build-utils/rpcs3/canonical-source.json")
    armsx2 = load_json(ROOT / "build-utils/armsx2/source.json")

    require_pinned_header(
        LEGAL_ASSETS / "Dolphin-COPYING.txt", args.dolphin_sha
    )
    require_pinned_header(
        LEGAL_ASSETS / "RPCS3-GPL-2.0.txt", rpcs3["upstream_commit"]
    )
    require_pinned_header(
        LEGAL_ASSETS / "ARMSX2-GPL-3.0.txt", armsx2["revision"]
    )
    require_pinned_header(
        LEGAL_ASSETS / "StikJIT-MPL-2.0.txt", "1.9.0"
    )
    for name, folder in (("glslang-LICENSE.txt", "glslang"), ("SPIRV-Cross-Apache-2.0.txt", "SPIRV-Cross")):
        require_pinned_header(LEGAL_ASSETS / name, SHADER_COMPILERS_TAG)
        source = (ROOT / "packages/neo_shader_kit/ios/ThirdParty" / folder / "SOURCE.txt").read_text(encoding="utf-8")
        if not source.startswith(f"{folder} {SHADER_COMPILERS_TAG}\n"):
            raise SystemExit(f"Legal notice {name} does not match the vendored {folder}")

    if args.validate_only:
        print("Validated all required notices and pinned revisions before compilation")
        return

    destination = app / "Legal"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    copy_file(ROOT / "LICENSE.md", destination / "NeoStation-GPL-3.0.txt")
    copy_file(ROOT / "NOTICE.md", destination / "NeoStation-NOTICE.md")
    copy_file(
        ROOT / "docs/LEGAL_AND_CREDITS.md",
        destination / "LEGAL_AND_CREDITS.md",
    )

    for name in REQUIRED_LEGAL_FILES:
        copy_file(LEGAL_ASSETS / name, destination / name)

    for name in libretro_notices:
        copy_file(LEGAL_ASSETS / "libretro" / name,
                  destination / "Libretro" / name)

    for name, (source, _) in additional_notices.items():
        copy_file(source, destination / name)

    identity = {
        "schema": 1,
        "build_number": str(args.build_number),
        "host_commit": os.environ.get("GITHUB_SHA", ""),
        "source_repository": "https://github.com/TarbleFR/neostation-ios",
        "additional_notice_sha256": {
            name: digest for name, (_, digest) in additional_notices.items()
        },
        "dolphin": {
            "repository": "https://github.com/OatmealDome/dolphin-ios",
            "revision": args.dolphin_sha,
        },
        "rpcs3": {
            "repository": "https://github.com/XITRIX/rpcs3",
            "revision": rpcs3["upstream_commit"],
            "license_note": "Most RPCS3 files: GPL-2.0-only; per-file notices apply",
        },
        "armsx2": {
            "repository": armsx2.get(
                "repository", "https://github.com/ARMSX2/ARMSX2.git"
            ),
            "revision": armsx2["revision"],
        },
        "stikjit": {
            "repository": "https://github.com/StikDebug/StikJIT",
            "version": "1.9.0",
            "license": "MPL-2.0",
        },
        "shader_kit": {
            "glslang": {
                "repository": "https://github.com/KhronosGroup/glslang",
                "tag": SHADER_COMPILERS_TAG,
                "license": "BSD-3-Clause and others (glslang-LICENSE.txt)",
            },
            "spirv_cross": {
                "repository": "https://github.com/KhronosGroup/SPIRV-Cross",
                "tag": SHADER_COMPILERS_TAG,
                "license": "Apache-2.0",
            },
            "catalogs": "slang-catalog.json (libretro/slang-shaders, files downloaded by the player at the pinned "
                        "commit, each under its own license) and dolphin-catalog.json (Dolphin's Sys/Shaders)",
        },
    }
    (destination / "BUILD_SOURCE_IDENTITY.json").write_text(
        json.dumps(identity, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Embedded legal bundle: {destination}")
    for item in sorted(destination.rglob("*")):
        if item.is_file():
            print(item.relative_to(app))


if __name__ == "__main__":
    main()
