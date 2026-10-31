#!/usr/bin/env python3
"""Build the isolated RPCS3 MoltenVK candidate from the complete pinned source.

This does not select a new dependency in the delivered Core recipe. The old
prebuilt-archive patchers must never be applied to this archive. A later Core
producer must authenticate this receipt and retain the existing ABI/codegen
checks. --prepare-only materializes sources; it is not an Apple build result.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import time


UPSTREAM = "https://github.com/KhronosGroup/MoltenVK.git"
COMMIT = "db66022459ffb663aa2b50f6b018bc2e124f5edf"
MACRO = "RBX_MVK_DEFERRED_CACHE_IMPORT=1"
IOS_TARGET = "16.3"
PLATFORMS = {"ios": ("iOS", "iphoneos", 2, (16, 3, 0), "ios-arm64"),
             "macos": ("macOS", "macosx", 1, (12, 0, 0), "macos-arm64")}
DEPENDENCIES = {
    "cereal": "cereal",
    "Vulkan-Headers": "Vulkan-Headers",
    "SPIRV-Cross": "SPIRV-Cross",
    "SPIRV-Tools": "SPIRV-Tools",
    "SPIRV-Headers": "SPIRV-Tools/external/spirv-headers",
    "Vulkan-Tools": "Vulkan-Tools",
    "Volk": "Volk",
}
HOOKS = {"_rbx_mvk_compile_qos_queue", "_rbx_mvk_exec_q_create"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_manifest(root):
    """Hash shipped bytes; packages are dereferenced and contain no symlinks."""
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"package contains a symbolic link: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "bytes": path.stat().st_size, "sha256": sha256(path)}
    return result


def dependency_pins(source):
    pins = {}
    for name in DEPENDENCIES:
        path = source / "ExternalRevisions" / f"{name}_repo_revision"
        value = path.read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError(f"dependency is not pinned to a full SHA: {name}")
        pins[name] = value
    return pins


def verify_source_delta(source, patch_report, run):
    """A pinned HEAD alone must not admit unrelated working-tree changes."""
    expected = patch_report["source_postimages"]
    if patch_report["upstream_commit"] != COMMIT or patch_report["macro"] + "=1" != MACRO:
        raise ValueError("adapter receipt does not describe this pinned candidate")
    changed = run.run(["git", "-C", source, "diff", "--name-only", "HEAD"]).splitlines()
    if set(changed) - set(expected):
        raise ValueError("MoltenVK contains unrelated tracked source changes")
    for name, digest in expected.items():
        path = source / name
        if not path.is_file() or path.is_symlink() or sha256(path) != digest:
            raise ValueError(f"MoltenVK source postimage mismatch: {name}")


def copy_dependency_licenses(source, output):
    for name, relative in DEPENDENCIES.items():
        root = source / "External" / relative
        files = sorted(path for path in root.iterdir() if path.is_file() and
                       re.match(r"^(LICENSE|LICENCE|COPYING|NOTICE)([._-]|$)", path.name, re.I))
        if not files:
            raise ValueError(f"dependency license files are missing: {name}")
        destination = output / "ThirdPartyLicenses" / name
        destination.mkdir(parents=True)
        for path in files:
            shutil.copy2(path, destination / path.name)


def build_command(selected_platform, products=None):
    name, sdk, _, _, _ = PLATFORMS[selected_platform]
    # The packaging aggregate also links a dynamic framework. Only the complete
    # static target can intentionally leave the two Core hooks unresolved.
    command = ["xcodebuild", "build", "-project", "MoltenVK/MoltenVK.xcodeproj",
               "-target", f"MoltenVK-{name}-static",
               "-configuration", "Release", "-sdk", sdk,
               "ARCHS=arm64", "ONLY_ACTIVE_ARCH=NO", "CODE_SIGNING_ALLOWED=NO",
               "GCC_PREPROCESSOR_DEFINITIONS=$(inherited) " + MACRO]
    command.append("IPHONEOS_DEPLOYMENT_TARGET=" + IOS_TARGET
                   if selected_platform == "ios" else "MACOSX_DEPLOYMENT_TARGET=12.0")
    if products:
        command.append("CONFIGURATION_BUILD_DIR=" + str(products))
    return command


def version_tuple(encoded):
    return encoded >> 16, (encoded >> 8) & 255, encoded & 255


def inspect_macho_object(data, selected_platform):
    """Check every real archive member, including platform and minimum OS."""
    if len(data) < 32 or data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("archive member is not a little-endian Mach-O 64-bit object")
    _, cpu, subtype, filetype, ncmds, sizeofcmds, _, _ = struct.unpack_from("<8I", data)
    if cpu != 0x0100000C or subtype != 0 or filetype != 1:
        raise ValueError("archive member is not a generic arm64 relocatable object")
    if 32 + sizeofcmds > len(data):
        raise ValueError("truncated Mach-O load commands")
    wanted_platform, maximum = PLATFORMS[selected_platform][2:4]
    versions = []
    offset = 32
    for _ in range(ncmds):
        if offset + 8 > 32 + sizeofcmds:
            raise ValueError("truncated Mach-O command header")
        command, size = struct.unpack_from("<2I", data, offset)
        if size < 8 or offset + size > 32 + sizeofcmds:
            raise ValueError("invalid Mach-O command extent")
        if command == 0x32:  # LC_BUILD_VERSION
            if size < 24:
                raise ValueError("truncated LC_BUILD_VERSION")
            target, minimum = struct.unpack_from("<2I", data, offset + 8)
            if target != wanted_platform:
                raise ValueError(f"wrong archive platform: {target}")
            versions.append(version_tuple(minimum))
        elif command in (0x24, 0x25, 0x2F, 0x30):
            # Accept old deployment commands only for the requested platform.
            wanted_command = 0x25 if selected_platform == "ios" else 0x24
            if command != wanted_command or size < 16:
                raise ValueError("wrong legacy archive platform")
            versions.append(version_tuple(struct.unpack_from("<I", data, offset + 8)[0]))
        offset += size
    if offset != 32 + sizeofcmds or len(versions) != 1:
        raise ValueError("archive member needs exactly one complete platform command")
    if versions[0] > maximum:
        raise ValueError(f"archive minimum OS {versions[0]} exceeds {maximum}")
    return ".".join(map(str, versions[0]))


def inspect_archive(path, selected_platform):
    """Parse a thin BSD/GNU ar archive; reject fat/simulator/non-object inputs."""
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("expected a thin static ar archive")
    offset, objects, minimums = 8, 0, set()
    while offset < len(data):
        if offset + 60 > len(data) or data[offset + 58:offset + 60] != b"`\n":
            raise ValueError("invalid ar member header")
        header = data[offset:offset + 60]
        try:
            size = int(header[48:58].decode("ascii").strip())
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("invalid ar member size") from error
        if size < 0 or offset + 60 + size > len(data):
            raise ValueError("truncated ar member")
        name = header[:16].decode("ascii").strip()
        payload = data[offset + 60:offset + 60 + size]
        if name.startswith("#1/"):
            name_size = int(name[3:])
            if name_size < 1 or name_size > len(payload):
                raise ValueError("invalid BSD ar extended name")
            name, payload = payload[:name_size].rstrip(b"\0").decode("utf-8"), payload[name_size:]
        if not (name.startswith("__.SYMDEF") or name in ("/", "//", "/SYM64/")):
            minimums.add(inspect_macho_object(payload, selected_platform))
            objects += 1
        offset += 60 + size + (size % 2)
    if offset != len(data) or not objects:
        raise ValueError("static archive has no objects or invalid alignment")
    return {"objects": objects, "architecture": "arm64", "platform": selected_platform,
            "object_minimum_os_versions": sorted(minimums)}


class Runner:
    def __init__(self, logs):
        self.logs = logs
        self.commands = []

    def run(self, command, cwd=None):
        index = len(self.commands) + 1
        log = self.logs / f"{index:02d}-{Path(str(command[0])).name}.log"
        started = time.monotonic()
        with log.open("wb") as stream:
            process = subprocess.run([str(value) for value in command], cwd=cwd,
                                     stdout=stream, stderr=subprocess.STDOUT, check=False)
        record = {"argv": [str(value) for value in command], "cwd": str(cwd) if cwd else None,
                  "exit_code": process.returncode, "seconds": time.monotonic() - started,
                  "log": log.name, "log_sha256": sha256(log)}
        self.commands.append(record)
        if process.returncode:
            raise RuntimeError(f"command failed ({process.returncode}); see {log}")
        return log.read_text(errors="replace").strip()


def create_empty_directory(path):
    """Never reset, remove, or reuse a caller's working/output directory."""
    if path.exists():
        raise ValueError(f"path already exists; use a new dedicated directory: {path}")
    path.mkdir(parents=True)


def produce(args):
    adapter = Path(__file__).with_name("patch_moltenvk_deferred_cache.py")
    if not adapter.is_file():
        raise ValueError(f"reviewed source adapter is missing: {adapter}")
    if not args.prepare_only and platform.system() != "Darwin":
        raise ValueError("the complete MoltenVK build requires macOS/Xcode; use --prepare-only for source preparation")
    work, output = args.work_root.resolve(), args.output.resolve()
    if work == output or work in output.parents or output in work.parents:
        raise ValueError("work and output must be separate directories")
    # Check both before creating either; no existing directory is changed.
    if work.exists() or output.exists():
        raise ValueError("work/output already exists; use new dedicated directories")
    create_empty_directory(work)
    create_empty_directory(output)
    logs = output / "logs"
    logs.mkdir()
    run = Runner(logs)
    products = work / "products"
    receipt = {"schema": 1, "component": "RewindBox RPCS3 MoltenVK deferred-cache candidate",
               "status": "started", "upstream_repository": UPSTREAM, "upstream_commit": COMMIT,
               "candidate_macro": MACRO, "platform": args.platform,
               "configuration": "Release", "static_only": True, "core_dependency_selected": False,
               "apple_native_build_executed": False, "core_built": False,
               "ipa_built": False, "device_tested": False,
               "producer_sha256": sha256(Path(__file__)), "adapter_sha256": sha256(adapter),
               "planned_build_command": build_command(args.platform, products)}
    try:
        source = work / "MoltenVK"
        run.run(["git", "init", "-q", source])
        repository = str(args.source_mirror.resolve()) if args.source_mirror else UPSTREAM
        run.run(["git", "-C", source, "fetch", "--depth", "1", repository, COMMIT])
        run.run(["git", "-C", source, "checkout", "-q", "--detach", "FETCH_HEAD"])
        if run.run(["git", "-C", source, "rev-parse", "HEAD"]) != COMMIT:
            raise ValueError("MoltenVK source pin mismatch")
        receipt["upstream_tree"] = run.run(["git", "-C", source, "rev-parse", "HEAD^{tree}"])
        receipt["dependency_pins"] = dependency_pins(source)
        patch_receipt = output / "source-patch.json"
        run.run([sys.executable, adapter, source, "--report", patch_receipt])
        run.run([sys.executable, adapter, source, "--check"])
        receipt["source_patch_report_sha256"] = sha256(patch_receipt)
        receipt["source_patch"] = json.loads(patch_receipt.read_text())
        verify_source_delta(source, receipt["source_patch"], run)
        if args.prepare_only:
            receipt["status"] = "source_prepared_only"
            receipt["limits"] = ["No dependencies fetched/built, no Apple compilation, no Core/IPA/device validation.",
                                 "The candidate is not selected by the delivered Core recipe."]
            return receipt
        receipt["xcode"] = run.run(["xcodebuild", "-version"])
        sdk = PLATFORMS[args.platform][1]
        receipt["sdk_version"] = run.run(["xcrun", "--sdk", sdk, "--show-sdk-version"])
        receipt["sdk_build"] = run.run(["xcrun", "--sdk", sdk, "--show-sdk-build-version"])
        receipt["clang"] = run.run(["xcrun", "--sdk", sdk, "clang", "--version"])
        receipt["apple_native_build_executed"] = True
        run.run(["./fetchDependencies", "--" + args.platform], cwd=source)
        actual_dependencies = {}
        for name, relative in DEPENDENCIES.items():
            dependency = source / "External" / relative
            actual = run.run(["git", "-C", dependency, "rev-parse", "HEAD"])
            if actual != receipt["dependency_pins"][name]:
                raise ValueError(f"fetched dependency pin mismatch: {name}")
            run.run(["git", "-C", dependency, "diff", "--quiet", "HEAD"])
            actual_dependencies[name] = actual
        receipt["verified_dependency_commits"] = actual_dependencies
        run.run(build_command(args.platform, products), cwd=source)
        # Verify the source adapter again after the complete framework build.
        run.run([sys.executable, adapter, source, "--check"])
        verify_source_delta(source, receipt["source_patch"], run)
        target = PLATFORMS[args.platform][4]
        library = products / "libMoltenVK.a"
        receipt["archive_validation"] = inspect_archive(library, args.platform)
        undefined = run.run(["xcrun", "nm", "-u", library])
        undefined_symbols = set(re.findall(r"(?m)^\s*(?:U\s+)?(_[A-Za-z0-9_]+)\s*$", undefined))
        if not HOOKS <= undefined_symbols:
            raise ValueError("source-built MoltenVK does not reference both existing Core queue hooks")
        receipt["required_core_queue_hooks"] = sorted(HOOKS)
        destination = output / "MoltenVK"
        include = source / "MoltenVK/include"
        if not (include / "vulkan/vulkan.h").is_file():
            raise ValueError("packaged Vulkan headers are missing")
        shutil.copytree(include, destination / "include", symlinks=False)
        xcframework = destination / "static/MoltenVK.xcframework"
        xcframework.parent.mkdir(parents=True)
        run.run(["xcodebuild", "-create-xcframework", "-library", library, "-output", xcframework])
        packaged_library = xcframework / target / "libMoltenVK.a"
        if sha256(packaged_library) != sha256(library):
            raise ValueError("static XCFramework packaging changed the built library")
        shutil.copy2(source / "LICENSE", output / "LICENSE")
        shutil.copytree(source / "Docs", output / "Docs", symlinks=False)
        copy_dependency_licenses(source, output)
        receipt["package_files"] = file_manifest(destination)
        receipt["license_sha256"] = sha256(output / "LICENSE")
        receipt["documentation_files"] = file_manifest(output / "Docs")
        receipt["dependency_license_files"] = file_manifest(output / "ThirdPartyLicenses")
        receipt["status"] = "candidate_dependency_built"
        receipt["limits"] = ["This is a full-source static MoltenVK candidate, not a compiled RPCS3 Core.",
                             "Not selected by the delivered Core recipe; consumer must authenticate this receipt.",
                             "No iPhone BO2/AC/GOW3 recovery or FPS gain is established."]
        return receipt
    except Exception as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
        raise
    finally:
        receipt["commands"] = run.commands
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-mirror", type=Path,
                        help="optional local Git object source; the exact upstream SHA is still required")
    parser.add_argument("--platform", choices=PLATFORMS, default="ios")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    try:
        receipt = produce(args)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.output.resolve() / "receipt.json")}))


if __name__ == "__main__":
    main()
