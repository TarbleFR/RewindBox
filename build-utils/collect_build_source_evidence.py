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

REPOSITORY_URL = "https://github.com/TarbleFR/neostation-ios"
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
    declarations = package_audit.get("source_declaration_sha256", {})
    if not declarations:
        raise SystemExit("Package source/license inventory lacks dependency declaration identities")
    for name, expected in declarations.items():
        if sha256(read_input(root, root / name)) != expected:
            raise SystemExit(f"Package source/license declaration changed since review: {name}")
    patterns = (
        "pubspec_overrides.yaml", "packages/*/pubspec.yaml",
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
            "MeloNX source references describe unfinished integration, not a delivered or approved runtime.",
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
