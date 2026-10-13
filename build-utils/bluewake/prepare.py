#!/usr/bin/env python3
"""Pinned BlueWake source preparation and disc-free iOS reference build.

This builds the upstream standalone host, NOT a callable NeoStation core.
No command installs, signs, uploads or publishes a personal game module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = Path(__file__).with_name("source.json")


def command(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_lock():
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def verify_vendored(lock):
    for item in lock["vendored_files"]:
        if digest(ROOT / item["destination"]) != item["sha256"]:
            raise ValueError(f"Vendored source differs from the pin: {item['destination']}")


def verify_checkout(path, expected_sha):
    path = Path(path).resolve()
    # Reject a directory that merely inherits a parent's .git directory.
    if Path(command("git", "rev-parse", "--show-toplevel", cwd=path)).resolve() != path:
        raise ValueError(f"Not an independent checkout: {path}")
    if command("git", "rev-parse", "HEAD", cwd=path) != expected_sha:
        raise ValueError(f"Wrong source revision in {path}; existing work was not changed")
    if command("git", "status", "--porcelain", "--untracked-files=normal", cwd=path):
        raise ValueError(f"Local changes in {path}; existing work was not changed")


def prepare_checkout(destination, repository, commit):
    destination = Path(destination).expanduser().absolute()
    if destination.is_symlink():
        raise ValueError("A source checkout may not be a symlink")
    if destination.exists():
        verify_checkout(destination, commit)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Only newly created temporary directories are cleaned on failure.
    with tempfile.TemporaryDirectory(prefix=".bluewake-source-", dir=destination.parent) as temp:
        checkout = Path(temp) / "source"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "remote", "add", "origin", repository], cwd=checkout, check=True)
        subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", commit], cwd=checkout, check=True)
        subprocess.run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=checkout, check=True)
        verify_checkout(checkout, commit)
        # Refuse to replace a directory another operation created in the meantime.
        if destination.exists():
            raise ValueError("The destination appeared during preparation; it was not replaced")
        checkout.rename(destination)
    return destination


def verify_profile(source, lock):
    profile = (source / "scripts/builder/profiles/bluewake.sh").read_text()
    expected = {
        "RECOMPCORE_SHA": lock["dependencies"]["recompcore"]["commit"],
        "DOLRECOMP_SHA": lock["dependencies"]["dolrecomp"]["commit"],
        "DAWN_SHA256": lock["dependencies"]["dawn"]["expected_sha256"],
        "COMPOSITE_DIGEST": lock["game_contract"]["expected_base_composite_digest"],
    }
    for key, value in expected.items():
        if f"{key}={value}" not in profile.splitlines():
            raise ValueError(f"Upstream builder disagrees with the source lock: {key}")
    for item in lock["vendored_files"]:
        if digest(source / item["upstream_path"]) != item["sha256"]:
            raise ValueError(f"Upstream source differs: {item['upstream_path']}")


def probe_disc(path, contract):
    """Read-only executable compatibility check, NOT full-disc/import validation.

    The complete 415-module set, extraction and source digest are still the
    personal upstream builder's responsibility. No game byte is written out.
    """
    path = Path(path)
    if path.suffix.lower() not in (".iso", ".gcm"):
        raise ValueError("Only uncompressed ISO/GCM inputs are supported")
    if not path.is_file():
        raise ValueError("The disc must be an existing regular file")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("The disc must be a regular file")
        size = info.st_size
        header = stream.read(0x440)
        if len(header) != 0x440:
            raise ValueError("Truncated GameCube header")
        if header[0x1C:0x20] != bytes.fromhex("c2339f3d"):
            raise ValueError("An uncompressed GameCube image is required")
        if header[:6].decode("ascii", errors="replace") != contract["disc_id"]:
            raise ValueError("Only GZLE01 USA is supported")
        if header[6] != 0 or header[7] != contract["revision"]:
            raise ValueError("Only disc 0, revision 0 is supported")
        dol_offset, fst_offset, fst_size = struct.unpack_from(">III", header, 0x420)
        if dol_offset < 0x440 or dol_offset + 0x100 > size:
            raise ValueError("Executable offset is outside the disc")
        if fst_offset < 0x440 or fst_size < 12 or fst_offset + fst_size > size:
            raise ValueError("File table is outside the disc")
        stream.seek(dol_offset)
        dol_header = stream.read(0x100)
        if len(dol_header) != 0x100:
            raise ValueError("Disc changed or executable header is truncated")
        dol_size = 0x100
        for i in range(18):
            offset = struct.unpack_from(">I", dol_header, 4 * i)[0]
            length = struct.unpack_from(">I", dol_header, 0x90 + 4 * i)[0]
            if not length:
                continue
            if offset < 0x100 or offset + length > 16 * 1024 * 1024:
                raise ValueError("Malformed executable section")
            dol_size = max(dol_size, offset + length)
        if dol_offset + dol_size > size:
            raise ValueError("Truncated executable")
        stream.seek(dol_offset)
        value = hashlib.sha1()
        remaining = dol_size
        while remaining:
            chunk = stream.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise ValueError("Disc changed or executable is truncated")
            remaining -= len(chunk)
            value.update(chunk)
        if value.hexdigest() != contract["expected_dol_sha1"]:
            raise ValueError("Unsupported or damaged game executable")
        after = os.fstat(stream.fileno())
        if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Disc changed during validation")
    return {"disc_id": contract["disc_id"], "revision": contract["revision"],
            "executable_matches": True, "full_disc_verified": False,
            "native_module_built": False}


def check_tools():
    if platform.system() != "Darwin":
        raise ValueError("The iOS reference build requires macOS with Xcode; source checks work here")
    for tool in ("git", "cmake", "ninja", "xcrun", "xcodebuild"):
        if not shutil.which(tool):
            raise ValueError(f"Missing build tool: {tool}")
    version = command("cmake", "--version").splitlines()[0].split()[-1]
    if tuple(int(x) for x in version.split(".")[:2]) < (3, 25):
        raise ValueError("CMake 3.25 or later is required")
    command("xcrun", "--sdk", "iphoneos", "--show-sdk-path")
    return {"xcode": command("xcodebuild", "-version"),
            "cmake": version, "architecture": platform.machine()}


def extract_dawn(archive, destination):
    # The pinned SDK contains libraries/headers, never disc-derived data.
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if Path(member.name).is_absolute() or ".." in parts:
                raise ValueError("Unsafe Dawn archive path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Unexpected link/device in Dawn archive")
        bundle.extractall(destination)


def build_shell(source, output, lock, jobs):
    tools = check_tools()
    source = source.resolve()
    verify_checkout(source, lock["bluewake"]["commit"])
    verify_profile(source, lock)
    if output.is_symlink():
        raise ValueError("The output path may not be a symlink")
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError("Use a new empty output path; previous builds are never overwritten")
    if source == output or source in output.parents or ROOT == output or ROOT in output.parents:
        raise ValueError("Keep the reference build outside both source repositories")
    # The dependency checkout is isolated from NeoStation's Dolphin and SDL.
    dependency = lock["dependencies"]["recompcore"]
    recompcore = prepare_checkout(source / "ref/recompcore", dependency["repository"], dependency["commit"])
    output.mkdir(parents=True)
    dawn = lock["dependencies"]["dawn"]
    archive = output / "dawn-ios-arm64.tar.gz"
    with urllib.request.urlopen(dawn["url"], timeout=60) as response, archive.open("xb") as target:
        shutil.copyfileobj(response, target)
    if digest(archive) != dawn["expected_sha256"]:
        raise ValueError("Dawn archive checksum mismatch")
    dawn_root = output / "dawn"
    extract_dawn(archive, dawn_root)
    cmake_args = ["cmake", "-S", str(source / "apple/ios"), "-B", str(output / "app"), "-G", "Ninja",
                  "-DCMAKE_SYSTEM_NAME=iOS", "-DCMAKE_OSX_SYSROOT=iphoneos",
                  "-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_OSX_DEPLOYMENT_TARGET=17.0",
                  "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF", "-DBUILD_SHARED_LIBS=OFF",
                  "-DPNG_SHARED=OFF", "-DBLUEWAKE_TVOS=OFF", "-DAURORA_DAWN_PROVIDER=system",
                  f"-DDawn_DIR={dawn_root}/lib/cmake/Dawn", "-DAURORA_DAWN_LINKAGE=static",
                  "-DAURORA_SDL3_PROVIDER=vendor", "-DAURORA_SDL3_LINKAGE=static",
                  f"-DAURORA_SDL3_REF={lock['dependencies']['sdl']['resolved_commit']}",
                  "-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew;/usr/local",
                  "-DCMAKE_DISABLE_FIND_PACKAGE_PkgConfig=ON"]
    subprocess.run(cmake_args, check=True)
    subprocess.run(["cmake", "--build", str(output / "app"), "--target", "BlueWake", "-j", str(jobs)], check=True)
    app = output / "app/BlueWake.app"
    binary = app / "BlueWake"
    if not binary.is_file():
        raise ValueError("The standalone application was not produced")
    if any(app.rglob("gGZLE01*")):
        raise ValueError("Unexpected translated game module in a disc-free build")
    with binary.open("rb") as stream:
        macho = stream.read(16)
    if len(macho) != 16 or struct.unpack("<IIII", macho)[:2] != (0xFEEDFACF, 0x0100000C):
        raise ValueError("The reference executable is not a thin ARM64 Mach-O")
    if struct.unpack("<IIII", macho)[3] != 2:
        raise ValueError("Expected an upstream standalone executable, not an embedded core")
    verify_checkout(source, lock["bluewake"]["commit"])
    verify_checkout(recompcore, dependency["commit"])
    receipt = {"status": "upstream_ios_shell_compiled", "tools": tools,
               "bluewake": lock["bluewake"]["commit"], "recompcore": dependency["commit"],
               "sdl": lock["dependencies"]["sdl"]["resolved_commit"],
               "dawn_sha256": digest(archive), "binary_sha256": digest(binary),
               "binary_kind": "MH_EXECUTE", "neostation_core": False,
               "game_module_built": False, "gameplay_tested": False,
               "cmake_arguments": cmake_args}
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("verify-vendored")
    sub.add_parser("check-tools")
    prepare = sub.add_parser("prepare-source")
    prepare.add_argument("destination", type=Path)
    probe = sub.add_parser("probe-disc")
    probe.add_argument("disc", type=Path)
    build = sub.add_parser("build-shell")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    lock = load_lock()
    try:
        verify_vendored(lock)
        if args.action == "verify-vendored":
            result = {"vendored_sources_verified": True}
        elif args.action == "check-tools":
            result = check_tools()
        elif args.action == "prepare-source":
            source = prepare_checkout(args.destination, lock["bluewake"]["repository"], lock["bluewake"]["commit"])
            verify_profile(source, lock)
            result = {"source": str(source), "commit": lock["bluewake"]["commit"]}
        elif args.action == "probe-disc":
            result = probe_disc(args.disc, lock["game_contract"])
        else:
            if args.jobs < 1:
                raise ValueError("--jobs must be positive")
            result = build_shell(args.source, args.output, lock, args.jobs)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"BlueWake preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
