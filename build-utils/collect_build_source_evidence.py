#!/usr/bin/env python3
"""Retain the actual dependency resolution and immutable source references.

This is a build-input record, not a certificate of complete Corresponding
Source. In particular, a package lock does not identify every native binary.
Nothing in this module downloads, builds or executes a dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re

REPOSITORY_URL = "https://github.com/TarbleFR/RewindBox"
PS2_POCKET_REVIEW = "docs/evidence/ps2-pocket-skins-declarations-2026-11-04.json"
BOARD_ORIGINALS_REVIEW = "docs/evidence/pocket-board-originals-declarations-2026-11-04.json"
PS2_ORIGINAL_REVIEW = "docs/evidence/ps2-pocket-original-declarations-2026-11-04.json"
SWITCH_POCKET_REVIEW = "docs/evidence/switch-pocket-declarations-2026-11-10.json"
GLACIER_REVIEW = "docs/evidence/rewindbox-glacier-declarations-2026-11-02.json"
# The Switch 2 tile of the Glacier pack, chained after the Glacier review (it moves the pack index on).
SWITCH2_TILE_REVIEW = "docs/evidence/switch2-glacier-tile-declarations-2026-11-11.json"
SKIN_REVISION_REVIEW = "docs/evidence/pocket-skins-framing-press-declarations-2026-11-10.json"
# Revisions in place, in order; each binds the packs of the one before it (PR #169: the windows at the game's ratio;
# PR #170: the precise pressed states of the board packs; PR #171: the pressed buttons of the two rendered packs).
SKIN_REVISION_REVIEWS = (SKIN_REVISION_REVIEW, "docs/evidence/pocket-skins-native-ratio-declarations-2026-11-10.json",
                         "docs/evidence/pocket-skins-press-precision-declarations-2026-11-10.json",
                         "docs/evidence/pocket-skins-pocket-press-declarations-2026-11-11.json")
ARMSX2_PODSPEC = "packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec"
# Xbox 360 playlist (PR #172): moves pubspec.yaml on from the Pocket originals review.
XENIOS_PLAYLIST_REVIEW = "docs/evidence/xenios-playlist-declarations-2026-11-11.json"
XENIOS_DECLARATIONS = (
    "pubspec.yaml",
    "packages/xenia_internal_bridge/pubspec.yaml",
    "packages/xenia_internal_bridge/ios/xenia_internal_bridge.podspec",
    "packages/xenia_jit_helper/ios/xenia_jit_helper.podspec",
)
S2ARM_ENGINE_REVIEW = "docs/evidence/s2arm-engine-declarations-2026-11-11.json"
S2ARM_ENGINE_PODSPEC = "packages/s2arm_engine_bridge/ios/s2arm_engine_bridge.podspec"
# The delivery that ships XeniaCore, chained after the Xbox 360 playlist review: binds the engine pin, the recipe
# files compiled into the binary, and the statically linked LGPL libraries with their chosen relinking means.
XENIOS_CORE_REVIEW = "docs/evidence/xenios-core-delivery-declarations-2026-11-12.json"
# The RetroAchievements disc reader (b06888a9): the libretro podspec compiles a vendored libchdr. Chained on the
# session review, whose libretro podspec postimage it moves on.
RA_DISC_READER_REVIEW = "docs/evidence/ra-disc-reader-declarations-2026-11-12.json"
# Xbox 360 controller rumble: the xenia bridge podspec links CoreHaptics (a system framework). Chained on the XeniOS
# playlist review, whose xenia podspec postimage it moves on.
XENIOS_HAPTICS_REVIEW = "docs/evidence/xenios-haptics-declarations-2026-11-12.json"
XENIA_BRIDGE_PODSPEC = "packages/xenia_internal_bridge/ios/xenia_internal_bridge.podspec"
# Licence audit: the notice folders the Legal and credits dialog opens become Flutter assets. Chained on the S2Arm
# engine review, whose pubspec.yaml postimage it moves on.
LEGAL_ASSETS_REVIEW = "docs/evidence/legal-assets-declarations-2026-11-12.json"
LEGAL_ASSETS_ADDED = ["assets/legal/engines/", "assets/legal/melonx/", "assets/legal/xenios/"]
LIBRETRO_PODSPEC = "packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec"
XENIOS_CORE_PIN = "build-utils/xenia/core-pin.json"
XENIOS_CORE_RECIPE = (
    "build-utils/xenia/build_core.sh",
    "build-utils/xenia/prepare_source.py",
    "build-utils/xenia/rewindbox-core.patch",
    "build-utils/xenia/upstream-files.json",
    "packages/xenia_internal_bridge/core/XeniaCore.mm",
    "packages/xenia_internal_bridge/core/XeniaCoreInput.h",
    "packages/xenia_internal_bridge/core/exports.txt",
    "packages/xenia_internal_bridge/core/neo_xenia_core_hooks.h",
    "packages/xenia_internal_bridge/core/target.cmake",
    "packages/xenia_internal_bridge/ios/Classes/XeniaCoreABI.h",
)
XENIOS_CORE_BUNDLED = ("Frameworks/XeniaCore.framework/XeniaCore", "Frameworks/libmetalirconverter.dylib")
XENIOS_LGPL = {
    "FFmpeg": {"path": "third_party/FFmpeg", "repository": "https://github.com/has207/FFmpeg.git",
               "branch": "xmaframes", "gitlink": "dfc5a3993b405f3a8b382756828cdfae06380c8b",
               "license": "LGPL-2.1-or-later"},
    "libmspack": {"path": "third_party/mspack", "tree": "91d0f9431729969b6d015dd8cd1e4168a27f74de",
                  "license": "LGPL-2.1"},
}
SOURCE_DOCUMENTS = (
    "SOURCE_CODE_ACCESS.md",
    "PACKAGE_SOURCES_AND_LICENSES.md",
    "ENGINE_CORRESPONDING_SOURCES.md",
    "PPSSPP_SOURCE_AND_LICENSE_AUDIT.md",
)
SOURCE_EVIDENCE = (
    "package-sources-license-audit-2026-10-21.json",
    "engine-source-license-audit-2026-10-21.json",
    "ppsspp-source-license-audit-2026-10-21.json",
    "modified-sources-since-0.0.8-2026-10-21.json",
    "achievement-translation-declarations-2026-10-31.json",
    "retro-achievements-session-declarations-2026-11-01.json",
    "rpcs3-retroachievements-declarations-2026-11-02.json",
    "rewindbox-glacier-declarations-2026-11-02.json",
    "pocket-originals-declarations-2026-11-03.json",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_input(root: Path, path: Path) -> bytes:
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise SystemExit(f"Source evidence is not a repository file: {path}")
    data = path.read_bytes()
    if not data:
        raise SystemExit(f"Empty source evidence: {path.relative_to(root)}")
    return data


def check_ra_disc_reader(root: Path, pubspec_lock_sha256: str, declarations: dict) -> None:
    """The disc reader review: the libretro podspec's only change since the session review is the vendored libchdr
    (BSD-3-Clause, with the public-domain LZMA SDK and the BSD Zstandard decoder), every file bound by digest, and its
    notices ship in the libretro legal set."""
    review = json.loads(read_input(root, root / RA_DISC_READER_REVIEW))
    prior = "docs/evidence/retro-achievements-session-declarations-2026-11-01.json"
    vendored = review.get("dependency_changes", {}).get("vendored_sources", {})
    if (review.get("schema") != 1 or review.get("baseline_inventory") != prior or
            review.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior)) or
            review.get("pubspec_lock_sha256") != pubspec_lock_sha256 or
            review.get("complete_corresponding_source_attested") is not False or
            review.get("dependency_changes", {}).get("external_packages_added") != []):
        raise SystemExit("RetroAchievements disc reader review has a different baseline or dependency scope")
    updates = review.get("declarations", {})
    if set(updates) != {LIBRETRO_PODSPEC}:
        raise SystemExit("RetroAchievements disc reader declaration review scope changed")
    update = updates[LIBRETRO_PODSPEC]
    if update.get("before") != declarations.get(LIBRETRO_PODSPEC):
        raise SystemExit(f"Wrong previous declaration identity: {LIBRETRO_PODSPEC}")
    current = sha256(read_input(root, root / LIBRETRO_PODSPEC))
    if current == update.get("before"):
        # A delivered product tree that still holds the podspec the session review declared (IPA 731's effective tree:
        # b06888a9's disc reader was never promoted into a delivery) compiles no libchdr; that previous declaration
        # stands and nothing else is accepted. The shipped notices then cover more than is compiled, never less.
        return
    if update.get("after") != current:
        raise SystemExit(f"Disc reader source/license declaration changed since review: {LIBRETRO_PODSPEC}")
    declarations[LIBRETRO_PODSPEC] = update["after"]
    vendored_root = vendored.get("path", "")
    vendored_files = vendored.get("files_sha256", {})
    actual = sorted(str(path.relative_to(root)) for path in (root / vendored_root).rglob("*")
                    if path.is_file()) if vendored_root else []
    if (vendored_root != "packages/libretro_internal_bridge/ios/ThirdParty/libchdr" or
            not vendored.get("license") or sorted(vendored_files) != actual or vendored.get("files") != len(actual)):
        raise SystemExit("Vendored libchdr sources differ from the disc reader review")
    for name, expected in vendored_files.items():
        if sha256(read_input(root, root / name)) != expected:
            raise SystemExit(f"Vendored libchdr source changed since review: {name}")
    manifest = json.loads(read_input(root, root / "assets/legal/libretro/license-sources.json"))
    notice = "RA-disc-reader-NOTICES.txt"
    listed = {entry.get("path"): entry.get("sha256") for entry in manifest.get("support_files", [])}
    if listed.get(notice) != sha256(read_input(root, root / "assets/legal/libretro" / notice)):
        raise SystemExit("The libchdr, LZMA and Zstandard notices are not in the libretro legal set")


def check_switch2_glacier_tile(root: Path, pubspec_lock_sha256: str) -> None:
    """The Switch 2 tile review, chained after the Glacier review: the pack gains backgrounds/switch2.webp (the
    official Nintendo Switch 2 logo on red, supplied by the maintainer to identify the system; Nintendo trademark,
    not BAXY-guided, not CC BY content) and aliases.json, theme.json and CREDITS.md declare it. No package, dependency,
    framework, engine or native source change. The review binds the previous index (the Glacier review's), the new
    one, and the size and SHA-256 of each added or changed file, checked against the index and the bytes."""
    review = json.loads(read_input(root, root / SWITCH2_TILE_REVIEW))
    glacier = json.loads(read_input(root, root / GLACIER_REVIEW))
    if (review.get("schema") != 1 or review.get("baseline_inventory") != GLACIER_REVIEW or
            review.get("baseline_inventory_sha256") != sha256(read_input(root, root / GLACIER_REVIEW)) or
            review.get("pubspec_lock_sha256") != pubspec_lock_sha256 or
            review.get("complete_corresponding_source_attested") is not False or
            review.get("dependency_changes") != {"external_packages_added": [], "external_packages_removed": [],
                                                 "system_frameworks_added": {}}):
        raise SystemExit("Switch 2 Glacier tile review has a different baseline or dependency scope")
    if review.get("declarations") != {}:
        raise SystemExit("Switch 2 Glacier tile declaration review scope changed")
    bundle = review.get("bundled_assets", {})
    index_path = bundle.get("index", "")
    if (index_path != "assets/system_art/rewindbox-glacier/bundle-index.json" or
            bundle.get("previous_index_sha256") != glacier.get("bundled_assets", {}).get("index_sha256") or
            bundle.get("index_sha256") != sha256(read_input(root, root / index_path))):
        raise SystemExit("RewindBox Glacier bundled pack index changed since the Switch 2 tile review")
    added = bundle.get("added_files", {})
    changed = bundle.get("changed_files", {})
    reviewed = dict(added)
    for name, change in changed.items():
        reviewed[name] = {"size": change.get("size"), "sha256": change.get("sha256")}
    index = json.loads(read_input(root, root / index_path))
    entries = {entry.get("path"): {"size": entry.get("size"), "sha256": entry.get("sha256")}
               for entry in index.get("files", [])}
    if (set(added) != {"backgrounds/switch2.webp"} or set(changed) != {"aliases.json", "theme.json", "CREDITS.md"} or
            len(entries) != bundle.get("files") or any(entries.get(name) != identity for name, identity in reviewed.items())):
        raise SystemExit("Switch 2 Glacier tile files differ from the review")
    pack = root / PurePosixPath(index_path).parent
    for name, identity in reviewed.items():
        raw = read_input(root, pack / name)
        if len(raw) != identity["size"] or sha256(raw) != identity["sha256"]:
            raise SystemExit("Switch 2 Glacier tile file differs from the index: " + name)


def check_xenios_core_delivery(root: Path, pubspec_lock_sha256: str) -> None:
    """The review of the delivery that ships XeniaCore, chained after the Xbox 360 playlist review (whose
    engine_binaries_bundled is empty). It binds build-utils/xenia/core-pin.json (the binary, its fingerprint, the
    XeniOS revision), the RewindBox files compiled into that binary (so the IPA's own host archive holds the recipe that
    built it), and the two statically linked LGPL libraries (FFmpeg, libmspack) with their sources, configuration and
    the relinking means chosen. No package or declaration changes. A core pin without this review is refused."""
    pin_path = root / XENIOS_CORE_PIN
    review_path = root / XENIOS_CORE_REVIEW
    if not review_path.is_file():
        if pin_path.is_file():
            raise SystemExit("XeniaCore is pinned without its delivery source review")
        return
    review = json.loads(read_input(root, review_path))
    engine = review.get("engine", {})
    if (review.get("schema") != 1 or review.get("baseline_inventory") != XENIOS_PLAYLIST_REVIEW or
            review.get("baseline_inventory_sha256") != sha256(read_input(root, root / XENIOS_PLAYLIST_REVIEW)) or
            review.get("pubspec_lock_sha256") != pubspec_lock_sha256 or
            review.get("complete_corresponding_source_attested") is not False or
            review.get("dependency_changes") != {"external_packages_added": [], "external_packages_removed": [],
                                                 "declarations_changed": []} or
            review.get("engine_binaries_bundled") != list(XENIOS_CORE_BUNDLED)):
        raise SystemExit("XeniaCore delivery review has a different baseline or scope")
    pin = json.loads(read_input(root, pin_path))
    source = json.loads(read_input(root, root / "build-utils/xenia/source.json"))
    binary = pin.get("binaries", {}).get("ios-arm64", {})
    if (engine.get("core_pin") != XENIOS_CORE_PIN or engine.get("core_pin_sha256") != sha256(read_input(root, pin_path))
            or pin.get("status") != "verified" or engine.get("revision") != source.get("revision") or
            pin.get("source") != source.get("revision") or engine.get("repository") != source.get("repository") or
            engine.get("binary_sha256") != binary.get("sha256") or
            engine.get("packaged_fingerprint") != pin.get("packagedFingerprint")):
        raise SystemExit("XeniaCore delivery review is not bound to the current core pin")
    recipe = engine.get("recipe_sha256", {})
    if set(recipe) != set(XENIOS_CORE_RECIPE):
        raise SystemExit("XeniaCore delivery review recipe scope changed")
    for name, digest in recipe.items():
        if sha256(read_input(root, root / name)) != digest:
            raise SystemExit(f"XeniaCore recipe changed since its delivery review: {name}")
    components = {entry.get("name"): entry for entry in review.get("lgpl_components", [])}
    if set(components) != set(XENIOS_LGPL) or len(review.get("lgpl_components", [])) != len(XENIOS_LGPL):
        raise SystemExit("XeniaCore delivery review LGPL scope changed")
    for name, expected in XENIOS_LGPL.items():
        entry = components[name]
        if ({key: entry.get("source", {}).get(key) for key in expected if key != "license"} !=
                {key: value for key, value in expected.items() if key != "license"} or
                entry.get("license") != expected["license"] or entry.get("linking") != "static" or
                entry.get("modifications") != "not enumerated"):
            raise SystemExit(f"XeniaCore delivery review LGPL entry differs: {name}")
    means = review.get("relinking_means", {})
    if means.get("chosen") != "LGPL-2.1 section 6(a)" or means.get("legal_clearance") is not False:
        raise SystemExit("XeniaCore delivery review must state its relinking means without a clearance claim")


def check_review_chain(root: Path, package_audit: dict, declarations: dict) -> None:
    """The declaration reviews chained after the achievement translation follow-up, in order. Each starts at the
    exact postimage of the one before and moves only its own declarations on (updating declarations in place);
    repository_inputs then binds every declaration to the checked-out file."""
    # Build608 adds a second, separately reviewed local plugin. Preserve the
    # original audit and605 follow-up verbatim; this overlay must start at their
    # exact postimages and may change only the six session declarations.
    session_path = root / "docs/evidence/retro-achievements-session-declarations-2026-11-01.json"
    session = json.loads(read_input(root, session_path))
    prior_name = "docs/evidence/achievement-translation-declarations-2026-10-31.json"
    if (session.get("schema") != 1 or session.get("baseline_inventory") != prior_name or
            session.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior_name)) or
            session.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
            session.get("complete_corresponding_source_attested") is not False or
            session.get("dependency_changes", {}).get("external_packages_added") != []):
        raise SystemExit("RetroAchievements session review has a different baseline or dependency scope")
    updates = session.get("declarations", {})
    expected_updates = {
        "pubspec.yaml",
        "packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec",
        "packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec",
        "packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec",
        "packages/retro_achievements_session/pubspec.yaml",
        "packages/retro_achievements_session/ios/retro_achievements_session.podspec",
    }
    if set(updates) != expected_updates:
        raise SystemExit("RetroAchievements session declaration review scope changed")
    # A later review overlay may move pubspec.yaml on (RewindBox Glacier); the
    # final loop below binds every declaration to the checked-out file.
    later_pubspec = (root / "docs/evidence/rewindbox-glacier-declarations-2026-11-02.json").is_file()
    # The PS2 Pocket skins review overlay may move the ARMSX2 bridge podspec on (system frameworks).
    later_armsx2 = (root / PS2_POCKET_REVIEW).is_file()
    # The disc reader review overlay moves the libretro bridge podspec on (vendored libchdr).
    later_libretro = (root / RA_DISC_READER_REVIEW).is_file()
    for name, update in updates.items():
        if update.get("before") != declarations.get(name):
            raise SystemExit(f"Wrong previous declaration identity: {name}")
        if not (later_pubspec and name == "pubspec.yaml") and not (later_armsx2 and name == ARMSX2_PODSPEC) and \
                not (later_libretro and name == LIBRETRO_PODSPEC) and \
                update.get("after") != sha256(read_input(root, root / name)):
            raise SystemExit(f"Session source/license declaration changed since review: {name}")
        declarations[name] = update["after"]
    if later_libretro:
        check_ra_disc_reader(root, package_audit["pubspec_lock_sha256"], declarations)
    # Build611: PS3 RetroAchievements through RPCS3. The RPCS3 bridge compiles a
    # vendored rcheevos copy, byte-identical to the declared libretro copy. This
    # overlay starts at the session review's exact postimage and may change only
    # the RPCS3 bridge podspec; every vendored file stays bound by digest.
    rpcs3_path = root / "docs/evidence/rpcs3-retroachievements-declarations-2026-11-02.json"
    rpcs3 = json.loads(read_input(root, rpcs3_path))
    prior_name = "docs/evidence/retro-achievements-session-declarations-2026-11-01.json"
    vendored = rpcs3.get("dependency_changes", {}).get("vendored_sources", {})
    if (rpcs3.get("schema") != 1 or rpcs3.get("baseline_inventory") != prior_name or
            rpcs3.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior_name)) or
            rpcs3.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
            rpcs3.get("complete_corresponding_source_attested") is not False or
            rpcs3.get("dependency_changes", {}).get("external_packages_added") != []):
        raise SystemExit("RPCS3 RetroAchievements review has a different baseline or dependency scope")
    updates = rpcs3.get("declarations", {})
    if set(updates) != {"packages/rpcs3_internal_bridge/ios/rpcs3_internal_bridge.podspec"}:
        raise SystemExit("RPCS3 RetroAchievements declaration review scope changed")
    for name, update in updates.items():
        if update.get("before") != declarations.get(name):
            raise SystemExit(f"Wrong previous declaration identity: {name}")
        if update.get("after") != sha256(read_input(root, root / name)):
            raise SystemExit(f"RPCS3 source/license declaration changed since review: {name}")
        declarations[name] = update["after"]
    vendored_root = vendored.get("path", "")
    vendored_files = vendored.get("files_sha256", {})
    actual_files = sorted(str(path.relative_to(root)) for path in (root / vendored_root).rglob("*")
                          if path.is_file()) if vendored_root else []
    if (vendored_root != "packages/rpcs3_internal_bridge/ios/ThirdParty/rcheevos" or
            vendored.get("license") != "MIT" or sorted(vendored_files) != actual_files or
            vendored.get("files") != len(actual_files)):
        raise SystemExit("Vendored rcheevos sources differ from the RPCS3 review")
    for name, expected in vendored_files.items():
        if sha256(read_input(root, root / name)) != expected:
            raise SystemExit(f"Vendored rcheevos source changed since review: {name}")
    # RewindBox Glacier: pubspec.yaml declares the bundled menu and System Art
    # assets. No package, dependency, engine or native source changes; the
    # bundled pack is bound file by file by its bundle-index.json.
    glacier_path = root / "docs/evidence/rewindbox-glacier-declarations-2026-11-02.json"
    if glacier_path.is_file():
        glacier = json.loads(read_input(root, glacier_path))
        prior_name = "docs/evidence/rpcs3-retroachievements-declarations-2026-11-02.json"
        if (glacier.get("schema") != 1 or glacier.get("baseline_inventory") != prior_name or
                glacier.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior_name)) or
                glacier.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                glacier.get("complete_corresponding_source_attested") is not False or
                glacier.get("dependency_changes", {}).get("external_packages_added") != []):
            raise SystemExit("RewindBox Glacier review has a different baseline or dependency scope")
        updates = glacier.get("declarations", {})
        if set(updates) != {"pubspec.yaml"}:
            raise SystemExit("RewindBox Glacier declaration review scope changed")
        # A later review overlay may move pubspec.yaml on (Pocket originals).
        later_pubspec = (root / "docs/evidence/pocket-originals-declarations-2026-11-03.json").is_file()
        for name, update in updates.items():
            if update.get("before") != declarations.get(name):
                raise SystemExit(f"Wrong previous declaration identity: {name}")
            if not later_pubspec and update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"RewindBox Glacier source/license declaration changed since review: {name}")
            declarations[name] = update["after"]
        bundle = glacier.get("bundled_assets", {})
        index_path = bundle.get("index", "")
        # A later review overlay may move the pack index on (the Switch 2 tile); it binds this digest.
        later_glacier_index = (root / SWITCH2_TILE_REVIEW).is_file()
        if (index_path != "assets/system_art/rewindbox-glacier/bundle-index.json" or
                (not later_glacier_index and bundle.get("index_sha256") != sha256(read_input(root, root / index_path)))):
            raise SystemExit("RewindBox Glacier bundled pack index changed since review")
        if later_glacier_index:
            check_switch2_glacier_tile(root, package_audit["pubspec_lock_sha256"])
    # RewindBox Pocket originals: pubspec.yaml declares the two bundled original
    # skin packs. No package, dependency, engine or native source changes; the
    # catalog binds each archive to its size and SHA-256.
    pocket_path = root / "docs/evidence/pocket-originals-declarations-2026-11-03.json"
    if pocket_path.is_file():
        pocket = json.loads(read_input(root, pocket_path))
        prior_name = "docs/evidence/rewindbox-glacier-declarations-2026-11-02.json"
        if (pocket.get("schema") != 1 or pocket.get("baseline_inventory") != prior_name or
                pocket.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior_name)) or
                pocket.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                pocket.get("complete_corresponding_source_attested") is not False or
                pocket.get("dependency_changes", {}).get("external_packages_added") != []):
            raise SystemExit("Pocket originals review has a different baseline or dependency scope")
        updates = pocket.get("declarations", {})
        if set(updates) != {"pubspec.yaml"}:
            raise SystemExit("Pocket originals declaration review scope changed")
        # A later review overlay may move pubspec.yaml on (XeniOS playlist); it binds this digest as its "before".
        later_pocket_pubspec = (root / XENIOS_PLAYLIST_REVIEW).is_file()
        for name, update in updates.items():
            if update.get("before") != declarations.get(name):
                raise SystemExit(f"Wrong previous declaration identity: {name}")
            if not later_pocket_pubspec and update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"Pocket originals source/license declaration changed since review: {name}")
            declarations[name] = update["after"]
        bundle = pocket.get("bundled_assets", {})
        catalog_path = bundle.get("catalog", "")
        # A later review overlay may move the catalog on (PS2 Pocket); it binds the previous digest.
        later_catalog = (root / PS2_POCKET_REVIEW).is_file()
        if (catalog_path != "assets/skins/pocket/catalog.json" or
                (not later_catalog and bundle.get("catalog_sha256") != sha256(read_input(root, root / catalog_path)))):
            raise SystemExit("Pocket originals catalog changed since review")
    # RewindBox skins orientation and PS2 Pocket (PR #152): the ARMSX2 bridge podspec adds Apple system frameworks
    # (QuartzCore, CoreGraphics) and the Pocket catalog gains the original PS2 pack. No package, dependency, engine
    # or native source change; the catalog binds each archive to its size and SHA-256.
    ps2_path = root / PS2_POCKET_REVIEW
    if ps2_path.is_file():
        ps2 = json.loads(read_input(root, ps2_path))
        prior_name = "docs/evidence/pocket-originals-declarations-2026-11-03.json"
        prior_pocket = json.loads(read_input(root, root / prior_name))
        changes = ps2.get("dependency_changes", {})
        if (ps2.get("schema") != 1 or ps2.get("baseline_inventory") != prior_name or
                ps2.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior_name)) or
                ps2.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                ps2.get("complete_corresponding_source_attested") is not False or
                changes.get("external_packages_added") != [] or changes.get("external_packages_removed") != [] or
                changes.get("system_frameworks_added") != {ARMSX2_PODSPEC: ["QuartzCore", "CoreGraphics"]}):
            raise SystemExit("PS2 Pocket skins review has a different baseline or dependency scope")
        updates = ps2.get("declarations", {})
        if set(updates) != {ARMSX2_PODSPEC}:
            raise SystemExit("PS2 Pocket skins declaration review scope changed")
        for name, update in updates.items():
            if update.get("before") != declarations.get(name):
                raise SystemExit(f"Wrong previous declaration identity: {name}")
            if update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"PS2 Pocket skins source/license declaration changed since review: {name}")
            declarations[name] = update["after"]
        bundle = ps2.get("bundled_assets", {})
        catalog_path = bundle.get("catalog", "")
        # A later review overlay may move the catalog on (GameCube/Wii board Originals); it binds this digest.
        later_ps2_catalog = (root / BOARD_ORIGINALS_REVIEW).is_file()
        if (catalog_path != "assets/skins/pocket/catalog.json" or
                bundle.get("previous_catalog_sha256") != prior_pocket.get("bundled_assets", {}).get("catalog_sha256") or
                (not later_ps2_catalog and bundle.get("catalog_sha256") != sha256(read_input(root, root / catalog_path)))):
            raise SystemExit("PS2 Pocket catalog changed since review")
    # RewindBox Pocket skins revised in place (PR #166 screen framing, PR #167 pressed controls; then PR #169, the
    # windows at the game's ratio; then PR #170, the precise pressed states; then PR #171, the pressed buttons of the
    # GameCube / Wii Pocket packs): packs of the catalog are rebuilt, none is added. Each revision review binds each pack
    # it rebuilds to the identity the review before it gave that pack; the earlier reviews below then check the identity
    # of the last revision, never an unreviewed one. A revision counts only with every revision before it.
    revision_path = root / SKIN_REVISION_REVIEW
    revisions = []
    for index, name in enumerate(SKIN_REVISION_REVIEWS):
        if (root / name).is_file():
            if len(revisions) != index:
                raise SystemExit("A Pocket skin revision review lacks the revision before it: " + name)
            revisions.append((name, json.loads(read_input(root, root / name))))

    def reviewed_identity(added_skins: dict) -> dict:
        result = {}
        for skin_id, identity in added_skins.items():
            for _, revision_review in revisions:
                revision = revision_review.get("bundled_assets", {}).get("revised_skins", {}).get(skin_id)
                if revision is not None:
                    if (revision.get("previous") != {"size": identity["size"], "sha256": identity["sha256"]} or
                            revision.get("archiveAsset") != identity["archiveAsset"]):
                        raise SystemExit("A later Pocket skin revision does not bind the reviewed pack: " + skin_id)
                    identity = {"size": revision.get("size"), "sha256": revision.get("sha256"),
                                "archiveAsset": revision["archiveAsset"]}
            result[skin_id] = identity
        return result
    # RewindBox GameCube/Wii Pocket Originals from the approved boards (PR #155): the Pocket catalog gains two packs,
    # nothing else. No package, dependency, framework, engine or native source declaration changes; the review binds
    # the previous (PS2 Pocket) catalog, the new catalog and the exact id, size and SHA-256 of each added pack.
    board_path = root / BOARD_ORIGINALS_REVIEW
    if board_path.is_file():
        board = json.loads(read_input(root, board_path))
        prior_ps2 = json.loads(read_input(root, root / PS2_POCKET_REVIEW))
        changes = board.get("dependency_changes", {})
        if (board.get("schema") != 1 or board.get("baseline_inventory") != PS2_POCKET_REVIEW or
                board.get("baseline_inventory_sha256") != sha256(read_input(root, root / PS2_POCKET_REVIEW)) or
                board.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                board.get("complete_corresponding_source_attested") is not False or
                changes != {"external_packages_added": [], "external_packages_removed": [], "system_frameworks_added": {}}):
            raise SystemExit("Pocket board Originals review has a different baseline or dependency scope")
        if board.get("declarations") != {}:
            raise SystemExit("Pocket board Originals declaration review scope changed")
        bundle = board.get("bundled_assets", {})
        catalog_path = bundle.get("catalog", "")
        # A later review overlay may move the catalog on (PS2 Pocket - Original); it binds this digest, and the two
        # packs reviewed here stay checked below in whatever catalog follows.
        later_board_catalog = (root / PS2_ORIGINAL_REVIEW).is_file()
        if (catalog_path != "assets/skins/pocket/catalog.json" or
                bundle.get("previous_catalog_sha256") != prior_ps2.get("bundled_assets", {}).get("catalog_sha256") or
                (not later_board_catalog and bundle.get("catalog_sha256") != sha256(read_input(root, root / catalog_path)))):
            raise SystemExit("Pocket board Originals catalog changed since review")
        catalog = json.loads(read_input(root, root / catalog_path))
        added = {skin["id"]: {"size": skin["size"], "sha256": skin["sha256"], "archiveAsset": skin["archiveAsset"]}
                 for skin in catalog.get("skins", []) if skin["id"] in bundle.get("added_skins", {})}
        if added != reviewed_identity(bundle.get("added_skins", {})) or (not later_board_catalog and
                                                  len(catalog.get("skins", [])) != bundle.get("catalog_skins")):
            raise SystemExit("Pocket board Originals added packs differ from the review")
        for skin in added.values():
            raw = read_input(root, root / skin["archiveAsset"])
            if len(raw) != skin["size"] or sha256(raw) != skin["sha256"]:
                raise SystemExit("Pocket board Originals archive differs from the catalog: " + skin["archiveAsset"])
    # RewindBox PS2 Pocket - Original from the approved PS2 design (PR #158): the Pocket catalog gains one pack, nothing
    # else. No package, dependency, framework, engine or native source declaration changes; the review binds the previous
    # (board Originals) catalog, the new catalog and the exact id, size and SHA-256 of the added pack.
    ps2_original_path = root / PS2_ORIGINAL_REVIEW
    if ps2_original_path.is_file():
        ps2_original = json.loads(read_input(root, ps2_original_path))
        prior_board = json.loads(read_input(root, root / BOARD_ORIGINALS_REVIEW))
        changes = ps2_original.get("dependency_changes", {})
        if (ps2_original.get("schema") != 1 or ps2_original.get("baseline_inventory") != BOARD_ORIGINALS_REVIEW or
                ps2_original.get("baseline_inventory_sha256") != sha256(read_input(root, root / BOARD_ORIGINALS_REVIEW)) or
                ps2_original.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                ps2_original.get("complete_corresponding_source_attested") is not False or
                changes != {"external_packages_added": [], "external_packages_removed": [], "system_frameworks_added": {}}):
            raise SystemExit("PS2 Pocket Original review has a different baseline or dependency scope")
        if ps2_original.get("declarations") != {}:
            raise SystemExit("PS2 Pocket Original declaration review scope changed")
        bundle = ps2_original.get("bundled_assets", {})
        catalog_path = bundle.get("catalog", "")
        # A later review overlay may move the catalog on (Switch Pocket); it binds this digest, and the pack reviewed
        # here stays checked below in whatever catalog follows.
        later_ps2_original_catalog = (root / SWITCH_POCKET_REVIEW).is_file()
        if (catalog_path != "assets/skins/pocket/catalog.json" or
                bundle.get("previous_catalog_sha256") != prior_board.get("bundled_assets", {}).get("catalog_sha256") or
                (not later_ps2_original_catalog and bundle.get("catalog_sha256") != sha256(read_input(root, root / catalog_path)))):
            raise SystemExit("PS2 Pocket Original catalog changed since review")
        catalog = json.loads(read_input(root, root / catalog_path))
        added = {skin["id"]: {"size": skin["size"], "sha256": skin["sha256"], "archiveAsset": skin["archiveAsset"]}
                 for skin in catalog.get("skins", []) if skin["id"] in bundle.get("added_skins", {})}
        if added != reviewed_identity(bundle.get("added_skins", {})) or (not later_ps2_original_catalog and
                                                  len(catalog.get("skins", [])) != bundle.get("catalog_skins")):
            raise SystemExit("PS2 Pocket Original added pack differs from the review")
        for skin in added.values():
            raw = read_input(root, root / skin["archiveAsset"])
            if len(raw) != skin["size"] or sha256(raw) != skin["sha256"]:
                raise SystemExit("PS2 Pocket Original archive differs from the catalog: " + skin["archiveAsset"])
    # RewindBox Switch Pocket from the approved Switch design (PR #165): the Pocket catalog gains one pack, nothing else.
    # No package, dependency, framework, engine or native source declaration changes; the review binds the previous
    # (PS2 Pocket - Original) catalog, the new catalog, the exact id, size and SHA-256 of the added pack and of the
    # approved design it is built from.
    switch_path = root / SWITCH_POCKET_REVIEW
    if switch_path.is_file():
        switch = json.loads(read_input(root, switch_path))
        prior_ps2_original = json.loads(read_input(root, root / PS2_ORIGINAL_REVIEW))
        changes = switch.get("dependency_changes", {})
        if (switch.get("schema") != 1 or switch.get("baseline_inventory") != PS2_ORIGINAL_REVIEW or
                switch.get("baseline_inventory_sha256") != sha256(read_input(root, root / PS2_ORIGINAL_REVIEW)) or
                switch.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                switch.get("complete_corresponding_source_attested") is not False or
                changes != {"external_packages_added": [], "external_packages_removed": [], "system_frameworks_added": {}}):
            raise SystemExit("Switch Pocket review has a different baseline or dependency scope")
        if switch.get("declarations") != {}:
            raise SystemExit("Switch Pocket declaration review scope changed")
        bundle = switch.get("bundled_assets", {})
        catalog_path = bundle.get("catalog", "")
        # A later review overlay may move the catalog on (Pocket skin revision); it binds this digest, and the pack
        # reviewed here stays checked below at the identity that revision gives it.
        later_switch_catalog = revision_path.is_file()
        if (catalog_path != "assets/skins/pocket/catalog.json" or
                bundle.get("previous_catalog_sha256") != prior_ps2_original.get("bundled_assets", {}).get("catalog_sha256") or
                (not later_switch_catalog and bundle.get("catalog_sha256") != sha256(read_input(root, root / catalog_path)))):
            raise SystemExit("Switch Pocket catalog changed since review")
        catalog = json.loads(read_input(root, root / catalog_path))
        added = {skin["id"]: {"size": skin["size"], "sha256": skin["sha256"], "archiveAsset": skin["archiveAsset"]}
                 for skin in catalog.get("skins", []) if skin["id"] in bundle.get("added_skins", {})}
        if added != reviewed_identity(bundle.get("added_skins", {})) or (not later_switch_catalog and
                                                                         len(catalog.get("skins", [])) != bundle.get("catalog_skins")):
            raise SystemExit("Switch Pocket added pack differs from the review")
        for skin in added.values():
            raw = read_input(root, root / skin["archiveAsset"])
            if len(raw) != skin["size"] or sha256(raw) != skin["sha256"]:
                raise SystemExit("Switch Pocket archive differs from the catalog: " + skin["archiveAsset"])
        design = bundle.get("design_reference", {})
        raw = read_input(root, root / design.get("path", "missing"))
        if len(raw) != design.get("size") or sha256(raw) != design.get("sha256"):
            raise SystemExit("Switch Pocket approved design differs from the review")
    # RewindBox Pocket skins revised in place (PR #166 and PR #167; then PR #169; then PR #170; then PR #171): no pack added or
    # removed, no package, dependency, framework, engine or native source declaration change. Each revision binds the
    # catalog before it (the Switch Pocket review's for the first, the previous revision's after), its own catalog, and
    # for every pack its exact id, size and SHA-256, with the identity each revised pack replaces. The last revision is
    # checked against the catalog and the archives; an earlier one against the packs the next revision starts from.
    for index, (name, revision) in enumerate(revisions):
        baseline = revisions[index - 1][0] if index else SWITCH_POCKET_REVIEW
        prior_switch = json.loads(read_input(root, root / baseline))
        later_revision = revisions[index + 1][1] if index + 1 < len(revisions) else None
        changes = revision.get("dependency_changes", {})
        if (revision.get("schema") != 1 or revision.get("baseline_inventory") != baseline or
                revision.get("baseline_inventory_sha256") != sha256(read_input(root, root / baseline)) or
                revision.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                revision.get("complete_corresponding_source_attested") is not False or
                changes != {"external_packages_added": [], "external_packages_removed": [], "system_frameworks_added": {}}):
            raise SystemExit("Pocket skin revision review has a different baseline or dependency scope")
        if revision.get("declarations") != {}:
            raise SystemExit("Pocket skin revision declaration review scope changed")
        bundle = revision.get("bundled_assets", {})
        catalog_path = bundle.get("catalog", "")
        if (catalog_path != "assets/skins/pocket/catalog.json" or
                bundle.get("previous_catalog_sha256") != prior_switch.get("bundled_assets", {}).get("catalog_sha256") or
                (later_revision is None and bundle.get("catalog_sha256") != sha256(read_input(root, root / catalog_path)))):
            raise SystemExit("Pocket skin revision catalog changed since review")
        if later_revision is None:
            catalog = json.loads(read_input(root, root / catalog_path))
            listed = {skin["id"]: {"size": skin["size"], "sha256": skin["sha256"], "archiveAsset": skin["archiveAsset"]}
                      for skin in catalog.get("skins", [])}
            listed_count = len(catalog.get("skins", []))
        else:
            # The packs the next revision starts from: the identity each pack it rebuilds replaces, the others as kept.
            following = later_revision.get("bundled_assets", {})
            listed = {skin_id: {"size": (value.get("previous") or {}).get("size"),
                                "sha256": (value.get("previous") or {}).get("sha256"), "archiveAsset": value.get("archiveAsset")}
                      for skin_id, value in following.get("revised_skins", {}).items()}
            listed.update({skin_id: {key: value.get(key) for key in ("size", "sha256", "archiveAsset")}
                           for skin_id, value in following.get("unchanged_skins", {}).items()})
            listed_count = following.get("catalog_skins")
        revised, unchanged = bundle.get("revised_skins", {}), bundle.get("unchanged_skins", {})
        reviewed = {skin_id: {key: value.get(key) for key in ("size", "sha256", "archiveAsset")}
                    for group in (revised, unchanged) for skin_id, value in group.items()}
        if (listed != reviewed or set(revised) & set(unchanged) or not revised or
                listed_count != bundle.get("catalog_skins")):
            raise SystemExit("Pocket skin revision packs differ from the review")
        for skin_id, value in revised.items():
            previous = value.get("previous")
            if (not isinstance(previous, dict) or set(previous) != {"size", "sha256"} or
                    (previous["size"], previous["sha256"]) == (value["size"], value["sha256"])):
                raise SystemExit("Pocket skin revision lacks the identity it replaces: " + skin_id)
        for skin in listed.values() if later_revision is None else ():
            raw = read_input(root, root / skin["archiveAsset"])
            if len(raw) != skin["size"] or sha256(raw) != skin["sha256"]:
                raise SystemExit("Pocket skin revision archive differs from the catalog: " + skin["archiveAsset"])
    # RewindBox Xbox 360 playlist (PR #172): pubspec.yaml adds the local workspace plugin xenia_internal_bridge; the
    # plugin and the dedicated XeniOS JIT helper pod are new local sources, declared from nothing. No hosted package is
    # added or removed and pubspec.lock is unchanged. The XeniOS engine (XeniaCore.framework) and Apple's Metal Shader
    # Converter are not built from this tree: nothing of either is committed, retained or bundled by this review.
    xenios_path = root / XENIOS_PLAYLIST_REVIEW
    if xenios_path.is_file():
        xenios = json.loads(read_input(root, xenios_path))
        prior_name = "docs/evidence/pocket-originals-declarations-2026-11-03.json"
        changes = xenios.get("dependency_changes", {})
        if (xenios.get("schema") != 1 or xenios.get("baseline_inventory") != prior_name or
                xenios.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior_name)) or
                xenios.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                xenios.get("complete_corresponding_source_attested") is not False or
                changes.get("external_packages_added") != [] or changes.get("external_packages_removed") != [] or
                changes.get("local_plugins_added") != ["xenia_internal_bridge"] or
                changes.get("engine_binaries_bundled") != []):
            raise SystemExit("XeniOS playlist review has a different baseline or dependency scope")
        updates = xenios.get("declarations", {})
        if set(updates) != set(XENIOS_DECLARATIONS):
            raise SystemExit("XeniOS playlist declaration review scope changed")
        for name, update in updates.items():
            if update.get("before") != declarations.get(name):
                raise SystemExit(f"Wrong previous declaration identity: {name}")
            # A later review overlay may move pubspec.yaml on (S2Arm engine bridge), or the xenia bridge podspec
            # (controller rumble).
            if not (name == "pubspec.yaml" and (root / S2ARM_ENGINE_REVIEW).is_file()) and \
                    not (name == XENIA_BRIDGE_PODSPEC and (root / XENIOS_HAPTICS_REVIEW).is_file()) and \
                    update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"XeniOS playlist source/license declaration changed since review: {name}")
            declarations[name] = update["after"]
    # Switch 2 (S2Arm), chained after the XeniOS playlist review: the root pubspec.yaml gains the workspace member and
    # the path dependency of the local plugin packages/s2arm_engine_bridge (RewindBox host code of the embedded engine).
    # Its podspec vendors S2ArmPrepare.xcframework, never committed: the delivery installs it from its pinned,
    # authenticated producer run before CocoaPods. No hosted package, Core or vendored source of this tree changes.
    engine_path = root / S2ARM_ENGINE_REVIEW
    if engine_path.is_file():
        engine = json.loads(read_input(root, engine_path))
        changes = engine.get("dependency_changes", {})
        if (engine.get("schema") != 1 or engine.get("baseline_inventory") != XENIOS_PLAYLIST_REVIEW or
                engine.get("baseline_inventory_sha256") != sha256(read_input(root, root / XENIOS_PLAYLIST_REVIEW)) or
                engine.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                engine.get("complete_corresponding_source_attested") is not False or
                changes != {"external_packages_added": [], "external_packages_removed": [],
                            "system_frameworks_added": {S2ARM_ENGINE_PODSPEC: ["Foundation", "UIKit", "Security"]},
                            "vendored_frameworks_added": {S2ARM_ENGINE_PODSPEC: ["Frameworks/S2ArmPrepare.xcframework"]}}):
            raise SystemExit("S2Arm engine review has a different baseline or dependency scope")
        updates = engine.get("declarations", {})
        if set(updates) != {"pubspec.yaml", "packages/s2arm_engine_bridge/pubspec.yaml", S2ARM_ENGINE_PODSPEC}:
            raise SystemExit("S2Arm engine declaration review scope changed")
        for name, update in updates.items():
            if update.get("before") != declarations.get(name):
                raise SystemExit(f"Wrong previous declaration identity: {name}")
            # The legal assets review overlay may move pubspec.yaml on.
            if not (name == "pubspec.yaml" and (root / LEGAL_ASSETS_REVIEW).is_file()) and \
                    update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"S2Arm engine source/license declaration changed since review: {name}")
            declarations[name] = update["after"]
        vendored = engine.get("vendored_library", {})
        if (vendored.get("path") != "packages/s2arm_engine_bridge/ios/Frameworks/S2ArmPrepare.xcframework" or
                vendored.get("in_repository") is not False or vendored.get("producer") != ".github/workflows/s2arm-core.yml"):
            raise SystemExit("S2Arm engine vendored library differs from the review")
    legal_assets_path = root / LEGAL_ASSETS_REVIEW
    if legal_assets_path.is_file():
        legal_assets = json.loads(read_input(root, legal_assets_path))
        if (legal_assets.get("schema") != 1 or legal_assets.get("baseline_inventory") != S2ARM_ENGINE_REVIEW or
                legal_assets.get("baseline_inventory_sha256") != sha256(read_input(root, root / S2ARM_ENGINE_REVIEW)) or
                legal_assets.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                legal_assets.get("complete_corresponding_source_attested") is not False or
                legal_assets.get("dependency_changes") != {"external_packages_added": [], "external_packages_removed": [],
                                                           "assets_added": LEGAL_ASSETS_ADDED}):
            raise SystemExit("Legal assets review has a different baseline or dependency scope")
        updates = legal_assets.get("declarations", {})
        if set(updates) != {"pubspec.yaml"}:
            raise SystemExit("Legal assets declaration review scope changed")
        update = updates["pubspec.yaml"]
        if update.get("before") != declarations.get("pubspec.yaml"):
            raise SystemExit("Wrong previous declaration identity: pubspec.yaml")
        if update.get("after") != sha256(read_input(root, root / "pubspec.yaml")):
            raise SystemExit("Legal assets source/license declaration changed since review: pubspec.yaml")
        declarations["pubspec.yaml"] = update["after"]
    haptics_path = root / XENIOS_HAPTICS_REVIEW
    if haptics_path.is_file():
        haptics = json.loads(read_input(root, haptics_path))
        if (haptics.get("schema") != 1 or haptics.get("baseline_inventory") != XENIOS_PLAYLIST_REVIEW or
                haptics.get("baseline_inventory_sha256") != sha256(read_input(root, root / XENIOS_PLAYLIST_REVIEW)) or
                haptics.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                haptics.get("complete_corresponding_source_attested") is not False or
                haptics.get("dependency_changes") != {"external_packages_added": [], "external_packages_removed": [],
                                                      "system_frameworks_added": {XENIA_BRIDGE_PODSPEC: ["CoreHaptics"]}}):
            raise SystemExit("XeniOS haptics review has a different baseline or dependency scope")
        updates = haptics.get("declarations", {})
        if set(updates) != {XENIA_BRIDGE_PODSPEC}:
            raise SystemExit("XeniOS haptics declaration review scope changed")
        update = updates[XENIA_BRIDGE_PODSPEC]
        if update.get("before") != declarations.get(XENIA_BRIDGE_PODSPEC):
            raise SystemExit(f"Wrong previous declaration identity: {XENIA_BRIDGE_PODSPEC}")
        if update.get("after") != sha256(read_input(root, root / XENIA_BRIDGE_PODSPEC)):
            raise SystemExit(f"XeniOS haptics source/license declaration changed since review: {XENIA_BRIDGE_PODSPEC}")
        declarations[XENIA_BRIDGE_PODSPEC] = update["after"]


def repository_inputs(root: Path) -> dict[str, str]:
    """Hash the source declarations and local modifications without executing them."""
    required = [root / "pubspec.yaml", root / "pubspec.lock"]
    for name in SOURCE_DOCUMENTS:
        required.append(root / "docs" / name)
    for name in SOURCE_EVIDENCE:
        required.append(root / "docs/evidence" / name)
    package_audit = json.loads(read_input(root, root / "docs/evidence/package-sources-license-audit-2026-10-21.json"))
    if package_audit.get("pubspec_lock_sha256") != sha256(read_input(root, root / "pubspec.lock")):
        raise SystemExit("Package source/license inventory is stale for pubspec.lock")
    declarations = dict(package_audit.get("source_declaration_sha256", {}))
    if not declarations:
        raise SystemExit("Package source/license inventory lacks dependency declaration identities")
    # Preserve the historical review; authenticate the narrowly scoped follow-up
    # instead of silently relabeling old package evidence as a new review.
    followup_path = root / "docs/evidence/achievement-translation-declarations-2026-10-31.json"
    followup = json.loads(read_input(root, followup_path))
    baseline_path = "docs/evidence/package-sources-license-audit-2026-10-21.json"
    if (followup.get("schema") != 1 or followup.get("baseline_inventory") != baseline_path or
            followup.get("baseline_inventory_sha256") != sha256(read_input(root, root / baseline_path)) or
            followup.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
            followup.get("complete_corresponding_source_attested") is not False):
        raise SystemExit("Achievement translation declaration review has a different baseline")
    updates = followup.get("declarations", {})
    expected_updates = {
        "pubspec.yaml",
        "packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec",
        "packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec",
        "packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec",
        "packages/achievement_translation/pubspec.yaml",
        "packages/achievement_translation/ios/achievement_translation.podspec",
    }
    if set(updates) != expected_updates:
        raise SystemExit("Achievement translation review scope changed")
    for name, update in updates.items():
        if update.get("before") != declarations.get(name):
            raise SystemExit(f"Wrong historical declaration identity: {name}")
        declarations[name] = update["after"]
    check_review_chain(root, package_audit, declarations)
    check_xenios_core_delivery(root, package_audit["pubspec_lock_sha256"])
    for name, expected in declarations.items():
        if sha256(read_input(root, root / name)) != expected:
            raise SystemExit(f"Package source/license declaration changed since review: {name}")
    patterns = (
        "pubspec_overrides.yaml", "packages/*/pubspec.yaml", XENIOS_CORE_PIN,
        "packages/*/ios/*.podspec", "build-utils/*/source.json",
        "build-utils/*/upstream-files.json", "build-utils/*/*.patch",
        "build-utils/rpcs3/canonical-source.json", "native/*/source.json",
        "native/*/*.patch", "build-utils/libretro/cores.json",
        "packages/neo_shader_kit/ios/ThirdParty/*/SOURCE.txt",
        "packages/neo_texture_catalog/ios/ThirdParty/*/source.json",
        "assets/legal/*/license-sources.json",
        "build-utils/collect_build_source_evidence.py",
        "build-utils/embed_legal_bundle.py", "build-utils/validate_legal_bundle_ipa.py",
        "build-utils/fetch_locked_package_sources.py",
    )
    paths = set(required)
    for pattern in patterns:
        paths.update(root.glob(pattern))
    return {str(path.relative_to(root)): sha256(read_input(root, path))
            for path in sorted(paths)}


def collect(root: Path, host_commit: str, app: Path | None = None) -> tuple[dict[str, bytes], dict]:
    """Return files under Legal/Sources and their identity, without writing them."""
    inputs = repository_inputs(root)
    files: dict[str, bytes] = {}

    def retain(relative: str) -> None:
        files["Build/" + relative] = read_input(root, root / relative)

    for relative in ("pubspec.yaml", "pubspec.lock", "pubspec_overrides.yaml"):
        if (root / relative).is_file():
            retain(relative)
    for name in SOURCE_DOCUMENTS:
        files[name] = read_input(root, root / "docs" / name)
    for name in SOURCE_EVIDENCE:
        files["Reviews/" + name] = read_input(root, root / "docs/evidence" / name)

    pod_lock = root / "ios/Podfile.lock"
    sandbox_lock = root / "ios/Pods/Manifest.lock"
    acknowledgements = root / "ios/Pods/Target Support Files/Pods-Runner/Pods-Runner-acknowledgements.plist"
    cocoa_status = "not_present_in_this_source_checkout"
    cocoa_gaps = []
    if pod_lock.exists() or sandbox_lock.exists() or (root / "ios/Pods").exists():
        # An incomplete or stale sandbox cannot describe the assembled app.
        if not pod_lock.is_file() or not sandbox_lock.is_file():
            raise SystemExit("CocoaPods source evidence requires both Podfile.lock and Pods/Manifest.lock")
        if read_input(root, pod_lock) != read_input(root, sandbox_lock):
            raise SystemExit("CocoaPods source evidence differs: Podfile.lock and Pods/Manifest.lock")
        if not acknowledgements.is_file():
            raise SystemExit("CocoaPods source evidence is missing dependency acknowledgements")
        try:
            plist = plistlib.loads(read_input(root, acknowledgements))
        except (ValueError, plistlib.InvalidFileException) as exc:
            raise SystemExit("Invalid CocoaPods dependency acknowledgements") from exc
        if not isinstance(plist, dict) or not isinstance(plist.get("PreferenceSpecifiers"), list) or not any(
            isinstance(item, dict) and item.get("Title") and item.get("FooterText")
            for item in plist["PreferenceSpecifiers"]
        ):
            raise SystemExit("CocoaPods dependency acknowledgements contain no notices")
        for path in (pod_lock, sandbox_lock, acknowledgements):
            retain(str(path.relative_to(root)))
        cocoa_status = "matching_locks_and_notices_captured"
        if (root / "ios/Podfile").is_file():
            retain("ios/Podfile")
        else:
            cocoa_gaps.append("Generated Podfile not present")
        specs = sorted((root / "ios/Pods/Local Podspecs").glob("*.podspec.json"))
        for path in specs:
            try:
                spec = json.loads(read_input(root, path))
            except ValueError as exc:
                raise SystemExit(f"Invalid resolved podspec: {path.name}") from exc
            if not isinstance(spec, dict) or not spec.get("name") or not spec.get("version"):
                raise SystemExit(f"Incomplete resolved podspec: {path.name}")
            retain(str(path.relative_to(root)))
        if not specs:
            cocoa_gaps.append("No resolved local podspec snapshots were available")

    # Retain names and plugin selection, never an absolute runner home/cache path.
    plugin_file = root / ".flutter-plugins-dependencies"
    if plugin_file.is_file():
        plugin_data = json.loads(read_input(root, plugin_file))
        plugins = plugin_data.get("plugins", {})
        selected = {}
        if isinstance(plugins, dict):
            for platform, entries in plugins.items():
                if not isinstance(entries, list):
                    continue
                selected[platform] = [
                    {key: value for key, value in entry.items()
                     if key in ("name", "native_build", "dependencies", "dev_dependency", "shared_darwin_source")}
                    for entry in entries if isinstance(entry, dict)
                ]
        files["Build/flutter-plugin-selection.json"] = encoded({
            "source_file": ".flutter-plugins-dependencies",
            "source_sha256": sha256(plugin_file.read_bytes()),
            "absolute_paths_omitted": True,
            "plugins": selected,
        })

    flutter_root = os.environ.get("FLUTTER_ROOT")
    flutter_identity = "not_observed"
    if flutter_root:
        version = Path(flutter_root) / "bin/cache/flutter.version.json"
        if version.is_file():
            version_data = json.loads(version.read_bytes())
            selected = {key: version_data[key] for key in (
                "frameworkVersion", "frameworkRevision", "engineRevision",
                "dartSdkVersion", "channel", "repositoryUrl", "flutterVersion",
            ) if key in version_data}
            files["Build/flutter-sdk-version.json"] = encoded(selected)
            flutter_identity = "observed_version_file"

    runtime_notices = []
    if app:
        for relative in ("Frameworks/App.framework/flutter_assets/NOTICES.Z",
                         "Frameworks/App.framework/flutter_assets/NOTICES",
                         "Frameworks/App.framework/flutter_assets/NOTICES.txt",
                         "flutter_assets/NOTICES.Z", "flutter_assets/NOTICES", "flutter_assets/NOTICES.txt"):
            path = app / relative
            if path.is_file():
                data = path.read_bytes()
                if not data:
                    raise SystemExit("Flutter runtime notice archive is empty")
                runtime_notices.append({"path": relative, "sha256": sha256(data), "bytes": len(data)})
        if not runtime_notices:
            raise SystemExit("Built app is missing Flutter runtime dependency notices")

    pinned = bool(re.fullmatch(r"[0-9a-f]{40}", host_commit))
    manifest = {
        "schema": 1,
        "collection_context": "built_app" if app else "source_preflight",
        "host_commit": host_commit,
        "repository": REPOSITORY_URL,
        "immutable_host_source_archive": f"{REPOSITORY_URL}/archive/{host_commit}.tar.gz" if pinned else None,
        "host_archive_scope": "Tracked host files, local patches and recipes; external source trees and submodules require the referenced pinned sources",
        "complete_corresponding_source_attested": False,
        "repository_input_sha256": inputs,
        "repository_file_url_template": f"{REPOSITORY_URL}/blob/{host_commit}/{{path}}" if pinned else None,
        "cocoapods": {"status": cocoa_status, "gaps": cocoa_gaps},
        "flutter_sdk_identity": flutter_identity,
        "flutter_runtime_notices": runtime_notices,
        "captured_files_sha256": {name: sha256(data) for name, data in sorted(files.items())},
        "limitations": [
            "Source access and notice inclusion do not settle every license compatibility or redistribution question.",
            "Historical buildbot binaries without exact source attestation remain open in ENGINE_CORRESPONDING_SOURCES.md.",
            "Native package downloads must be matched separately to their source, configuration and licenses.",
            "MeloNX test-runtime identity, private native dependency source archives and notices are recorded separately in MeloNX-native-identity.json and Legal/MeloNX; physical gameplay is not attested.",
        ],
    }
    files["BUILD_SOURCE_EVIDENCE.json"] = encoded(manifest)
    return files, manifest


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_archive(archive, names: list[str], prefix: str, host_commit: str, root: Path) -> None:
    """Check retained bytes and current reviewed source inputs in a packaged archive."""
    manifest_name = prefix + "Sources/BUILD_SOURCE_EVIDENCE.json"
    if names.count(manifest_name) != 1:
        raise SystemExit("Missing or duplicate build source evidence")
    manifest = json.loads(archive.read(manifest_name))
    if manifest.get("schema") != 1 or manifest.get("host_commit") != host_commit:
        raise SystemExit("Build source evidence identity mismatch")
    if manifest.get("complete_corresponding_source_attested") is not False:
        raise SystemExit("Build source evidence must retain unresolved source status")
    if manifest.get("collection_context") != "built_app" or not manifest.get("flutter_runtime_notices"):
        raise SystemExit("Packaged app is missing captured Flutter runtime dependency notices")
    if manifest.get("repository_input_sha256") != repository_inputs(root):
        raise SystemExit("Build source evidence differs from reviewed repository inputs")
    entries = manifest.get("captured_files_sha256", {})
    required = {"Build/pubspec.yaml", "Build/pubspec.lock", *SOURCE_DOCUMENTS,
                *("Reviews/" + name for name in SOURCE_EVIDENCE)}
    if not required.issubset(entries):
        raise SystemExit("Build source evidence is missing required references")
    if manifest.get("cocoapods", {}).get("status") == "matching_locks_and_notices_captured":
        required_pods = {"Build/ios/Podfile.lock", "Build/ios/Pods/Manifest.lock",
                         "Build/ios/Pods/Target Support Files/Pods-Runner/Pods-Runner-acknowledgements.plist"}
        if not required_pods.issubset(entries):
            raise SystemExit("Packaged CocoaPods source evidence is incomplete")
    else:
        cocoa = manifest.get("cocoapods", {}).get("status")
        if cocoa != "not_present_in_this_source_checkout":
            raise SystemExit("Invalid packaged CocoaPods evidence status")
    for name, digest in entries.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise SystemExit("Unsafe packaged source evidence path")
        member = prefix + "Sources/" + name
        if names.count(member) != 1 or sha256(archive.read(member)) != digest:
            raise SystemExit(f"Missing, duplicate or changed source evidence: {name}")
        source = None
        if name.startswith("Build/") and name.removeprefix("Build/") in manifest["repository_input_sha256"]:
            source = name.removeprefix("Build/")
        elif name in SOURCE_DOCUMENTS:
            source = "docs/" + name
        elif name.startswith("Reviews/"):
            source = "docs/evidence/" + name.removeprefix("Reviews/")
        if source and manifest["repository_input_sha256"].get(source) != digest:
            raise SystemExit(f"Packaged source reference differs from the repository: {name}")
    if manifest["cocoapods"]["status"] == "matching_locks_and_notices_captured":
        if archive.read(prefix + "Sources/Build/ios/Podfile.lock") != archive.read(prefix + "Sources/Build/ios/Pods/Manifest.lock"):
            raise SystemExit("Packaged CocoaPods locks differ")
    app_prefix = prefix.removesuffix("Legal/")
    for entry in manifest.get("flutter_runtime_notices", []):
        if entry["path"] not in (
            "Frameworks/App.framework/flutter_assets/NOTICES.Z",
            "Frameworks/App.framework/flutter_assets/NOTICES",
            "Frameworks/App.framework/flutter_assets/NOTICES.txt",
            "flutter_assets/NOTICES.Z", "flutter_assets/NOTICES", "flutter_assets/NOTICES.txt",
        ):
            raise SystemExit("Unexpected Flutter runtime notice path")
        member = app_prefix + entry["path"]
        if names.count(member) != 1 or sha256(archive.read(member)) != entry["sha256"]:
            raise SystemExit("Flutter runtime notice archive differs from the source record")
