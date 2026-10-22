#!/usr/bin/env python3
"""Build private iOS dependencies from pinned source, never upstream binaries.

The output is component evidence, not a claim that a guest or an IPA ran.
All commands, sources, licenses and resulting Mach-O identities are retained.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
PIN = json.loads((ROOT / "build-utils/melonx/native-dependencies.json").read_text())
OUT = ROOT / "dist/melonx-native"
WORK = ROOT / "build/melonx-native"
COMMANDS = []


def run(args, cwd=None, env=None, capture=False):
    args = [str(x) for x in args]
    COMMANDS.append({"args": args, "cwd": str(cwd or ROOT)})
    print("+ " + " ".join(args), flush=True)
    return subprocess.check_output(args, cwd=cwd, env=env, text=True).strip() if capture else subprocess.run(args, cwd=cwd, env=env, check=True)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source(name):
    pin = PIN["sources"][name]
    target = WORK / "source" / name
    target.mkdir(parents=True)
    run(["git", "init", target])
    run(["git", "-C", target, "remote", "add", "origin", pin["repository"]])
    run(["git", "-C", target, "fetch", "--depth", "1", "origin", pin["revision"]])
    run(["git", "-C", target, "checkout", "--detach", "FETCH_HEAD"])
    assert run(["git", "-C", target, "rev-parse", "HEAD"], capture=True) == pin["revision"]
    archive = OUT / "sources" / f"{name}-{pin['revision']}.tar.gz"
    with archive.open("wb") as stream:
        subprocess.run(["git", "-C", str(target), "archive", "--format=tar.gz", "--prefix", name + "/", "HEAD"], stdout=stream, check=True)
    return target


def framework(binary, name, platform):
    directory = OUT / platform / f"{name}.framework"
    directory.mkdir(parents=True)
    target = directory / name
    # Frameworks in this lane are intentionally thin ARM64, for device or sim.
    run(["xcrun", "lipo", binary, "-thin", "arm64", "-output", target]) if "Non-fat" not in run(["xcrun", "lipo", "-info", binary], capture=True) else shutil.copy2(binary, target)
    run(["xcrun", "lipo", target, "-verify_arch", "arm64"])
    run(["install_name_tool", "-id", f"@rpath/{name}.framework/{name}", target])
    info = {
        "CFBundleExecutable": name, "CFBundleName": name,
        "CFBundleIdentifier": "com.neogamelab.neostation.melonx." + name.lower(),
        "CFBundlePackageType": "FMWK", "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0", "MinimumOSVersion": PIN["minimumIOS"],
        "CFBundleSupportedPlatforms": ["iPhoneOS" if platform == "ios" else "iPhoneSimulator"],
        "UIDeviceFamily": [1, 2],
    }
    with (directory / "Info.plist").open("wb") as stream:
        plistlib.dump(info, stream)
    return target


def build_moltenvk(path, platforms):
    # fetchDependencies uses the exact commits in ExternalRevisions. Capture
    # both those pins and complete source trees, including their notices.
    flags = ["--ios" if p == "ios" else "--iossim" for p in platforms]
    run([path / "fetchDependencies", *flags], cwd=path)
    for p in platforms:
        run(["make", "ios" if p == "ios" else "iossim"], cwd=path)
        xcframework = path / "Package/Latest/MoltenVK/dynamic/MoltenVK.xcframework"
        candidates = list(xcframework.glob("*/MoltenVK.framework/MoltenVK"))
        expected = [x for x in candidates if ("simulator" in x.parts[-3]) == (p != "ios")]
        assert len(expected) == 1, candidates
        framework(expected[0], "MeloNXMoltenVK", p)
    with tarfile.open(OUT / "sources/MoltenVK-external-sources.tar.gz", "w:gz") as archive:
        archive.add(path / "ExternalRevisions", arcname="ExternalRevisions")
        external = path / "External"
        for child in sorted(external.iterdir()):
            if child.is_dir() and (child / ".git").exists():
                identity = run(["git", "-C", child, "rev-parse", "HEAD"], capture=True)
                archive.add(child, arcname=f"External/{child.name}-{identity}", filter=lambda m: None if "/.git" in m.name else m)


def build_sdl(path, platforms):
    for p in platforms:
        sdk = "iphoneos" if p == "ios" else "iphonesimulator"
        build = WORK / f"sdl-{p}"
        run(["cmake", "-S", path, "-B", build, "-G", "Xcode",
             "-DCMAKE_SYSTEM_NAME=iOS", f"-DCMAKE_OSX_SYSROOT={sdk}",
             "-DCMAKE_OSX_ARCHITECTURES=arm64", f"-DCMAKE_OSX_DEPLOYMENT_TARGET={PIN['minimumIOS']}",
             "-DSDL_SHARED=ON", "-DSDL_STATIC=OFF", "-DSDL_FRAMEWORK=ON", "-DSDL_TESTS=OFF", "-DSDL_EXAMPLES=OFF"])
        run(["cmake", "--build", build, "--config", "Release", "--", "CODE_SIGNING_ALLOWED=NO"])
        candidates = [x for x in build.rglob("SDL3.framework/SDL3") if "Release" in str(x)]
        assert len(candidates) == 1, candidates
        framework(candidates[0], "MeloNXSDL3", p)


def build_ffmpeg(path, platforms):
    for p in platforms:
        sdk = "iphoneos" if p == "ios" else "iphonesimulator"
        sysroot = run(["xcrun", "--sdk", sdk, "--show-sdk-path"], capture=True)
        compiler = run(["xcrun", "--sdk", sdk, "--find", "clang"], capture=True)
        triple = "arm64-apple-ios18.0" + ("-simulator" if p != "ios" else "")
        build = WORK / f"ffmpeg-{p}"
        build.mkdir()
        prefix = build / "install"
        run([path / "configure", "--target-os=darwin", "--arch=arm64", "--enable-cross-compile",
             f"--cc={compiler}", f"--sysroot={sysroot}", f"--prefix={prefix}",
             f"--extra-cflags=-target {triple} -fPIC", f"--extra-ldflags=-target {triple}",
             "--enable-shared", "--disable-static", "--disable-programs", "--disable-doc",
             "--disable-debug", "--disable-autodetect", "--disable-everything", "--enable-version3",
             "--disable-gpl", "--disable-nonfree", "--disable-network", "--disable-avdevice",
             "--disable-avformat", "--disable-avfilter", "--disable-swscale", "--disable-swresample",
             "--disable-postproc", "--enable-avcodec", "--enable-avutil",
             "--enable-decoder=h264,hevc,vp8,vp9", "--enable-parser=h264,hevc,vp8,vp9"], cwd=build)
        run(["make", "-j", str(os.cpu_count() or 4)], cwd=build)
        run(["make", "install"], cwd=build)
        avutil = framework(prefix / "lib/libavutil.58.dylib", "MeloNXAvUtil", p)
        avcodec = framework(prefix / "lib/libavcodec.60.dylib", "MeloNXAvCodec", p)
        deps = run(["otool", "-L", avcodec], capture=True)
        for line in deps.splitlines()[1:]:
            old = line.strip().split(" (", 1)[0]
            if "libavutil" in old:
                run(["install_name_tool", "-change", old, "@rpath/MeloNXAvUtil.framework/MeloNXAvUtil", avcodec])
        config = OUT / "sources" / f"FFmpeg-{p}-configuration.txt"
        config.write_text((build / "config.h").read_text() + "\n" + (build / "ffbuild/config.mak").read_text())


def build_jit(platforms):
    for p in platforms:
        sdk = "iphoneos" if p == "ios" else "iphonesimulator"
        triple = "arm64-apple-ios18.0" + ("-simulator" if p != "ios" else "")
        binary = WORK / f"jit-{p}.dylib"
        run(["xcrun", "--sdk", sdk, "clang", "-target", triple, "-dynamiclib",
             ROOT / "native/melonx/jit/MeloNXJitSupport.S", "-o", binary])
        framework(binary, "MeloNXJitSupport", p)


def audit(platforms):
    binaries = []
    for p in platforms:
        for binary in sorted((OUT / p).glob("*.framework/*")):
            if binary.name == "Info.plist":
                continue
            deps = run(["otool", "-L", binary], capture=True)
            build = run(["xcrun", "vtool", "-show-build", binary], capture=True)
            expected = "IOS" if p == "ios" else "IOSSIMULATOR"
            assert f"platform {expected}\n" in build, build
            for line in deps.splitlines()[1:]:
                dep = line.strip().split(" (", 1)[0]
                if dep.startswith("@rpath/"):
                    assert (OUT / p / dep.removeprefix("@rpath/")).is_file(), dep
                else:
                    assert dep.startswith(("/usr/lib/", "/System/Library/Frameworks/")), dep
                    verify_sdk_dependency(dep, p)
            run(["codesign", "--force", "--sign", "-", binary.parent])
            run(["codesign", "--verify", "--strict", binary.parent])
            binaries.append({"path": str(binary.relative_to(OUT)), "sha256": digest(binary),
                             "bytes": binary.stat().st_size, "dependencies": deps, "platform": build})
    return binaries


def verify_sdk_dependency(dependency, platform):
    """Trust exact Apple SDK install names, never a guessed path rewrite.

    The iOS SDK's IOKit stub itself declares Versions/A/IOKit. Versioned spelling
    alone is not a macOS binary. Validate platform and the SDK's declaration.
    """
    sdk = "iphoneos" if platform == "ios" else "iphonesimulator"
    sysroot = Path(run(["xcrun", "--sdk", sdk, "--show-sdk-path"], capture=True))
    relative = dependency.lstrip("/")
    candidates = [sysroot / relative, sysroot / (relative + ".tbd")]
    if ".framework/" in relative:
        prefix = relative.split(".framework/", 1)[0] + ".framework"
        framework_name = Path(prefix).stem
        candidates.append(sysroot / prefix / (framework_name + ".tbd"))
    elif dependency.endswith(".dylib"):
        candidates.extend((sysroot / "usr/lib").glob(Path(dependency).name.removesuffix(".dylib") + "*.tbd"))
        if not any(x.is_file() for x in candidates):
            candidates.extend((sysroot / "usr/lib").glob("*.tbd"))
    assert any(x.is_file() and dependency in x.read_text(errors="replace") for x in candidates if x.suffix == ".tbd"), (dependency, candidates[:5])


def recover_compiled_dependencies(platforms):
    # The original run built every component and failed only in audit. Check
    # that every compilation function, pin and assembly input is unchanged.
    previous = "f76ec4e9488d6adbc5443ef180762a2d2fe61a54"
    run(["git", "fetch", "--depth", "1", "origin", previous])
    run(["git", "diff", "--exit-code", previous, "HEAD", "--",
         "build-utils/melonx/native-dependencies.json", "native/melonx/jit/MeloNXJitSupport.S"])
    original = ast.parse(run(["git", "show", previous + ":build-utils/melonx/build_native_dependencies.py"], capture=True))
    current = ast.parse(Path(__file__).read_text())
    for name in ["source", "framework", "build_moltenvk", "build_sdl", "build_ffmpeg", "build_jit"]:
        old = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == name)
        new = next(n for n in current.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(old) == ast.dump(new), name
    commands = json.loads((OUT / "commands.json").read_text())
    assert commands[-1]["args"][0:3] == ["xcrun", "vtool", "-show-build"]
    assert commands[-1]["args"][-1].endswith("ios/MeloNXMoltenVK.framework/MeloNXMoltenVK")
    shutil.copy2(OUT / "commands.json", OUT / "source-build-commands.json")
    for name, pin in PIN["sources"].items():
        assert (OUT / "sources" / f"{name}-{pin['revision']}.tar.gz").is_file()
    for p in platforms:
        assert len(list((OUT / p).glob("*.framework/Info.plist"))) == 5
    return {"run": 39850575802, "artifact": 12459370798, "source": previous,
            "originalRunConclusion": "failure", "failurePhase": "overbroad versioned system-framework path guard",
            "compilationInputsUnchanged": True, "compilersReexecuted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["ios", "iossimulator", "both"], default="both")
    parser.add_argument("--audit-recovered", action="store_true")
    args = parser.parse_args()
    platforms = ["ios", "iossimulator"] if args.platform == "both" else [args.platform]
    OUT.mkdir(parents=True, exist_ok=args.audit_recovered)
    (OUT / "sources").mkdir(exist_ok=args.audit_recovered)
    reuse = recover_compiled_dependencies(platforms) if args.audit_recovered else None
    paths = None if reuse else {name: source(name) for name in PIN["sources"]}
    try:
        if not reuse:
            build_moltenvk(paths["MoltenVK"], platforms)
            build_sdl(paths["SDL"], platforms)
            build_ffmpeg(paths["FFmpeg"], platforms)
            build_jit(platforms)
        binaries = audit(platforms)
        receipt = {"pins": PIN, "binaries": binaries, "status": "source-built-component-not-gameplay-tested",
                   "sourceArchives": [{"path": str(p.relative_to(OUT)), "sha256": digest(p)} for p in sorted((OUT / "sources").iterdir())]}
        receipt['reusedCompilation'] = reuse
        (OUT / "identity.json").write_text(json.dumps(receipt, indent=2) + "\n")
    finally:
        (OUT / "commands.json").write_text(json.dumps(COMMANDS, indent=2) + "\n")


if __name__ == "__main__":
    main()
