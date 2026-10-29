#!/usr/bin/env python3
"""Check RSX CPU writes against the delivered texture-validation path.

The test executes the complete nv308a/nv0039 handlers and nv3089's CPU/GPU
dispatch body from production sources. NV3089's image conversion and GPU
implementation are boundary adapters; this test checks notification ordering,
not FFmpeg, tiling, GPU synchronization, or physical-device rendering.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

import rpcs3_prehash_admission_test as prehash

ROOT = Path(__file__).resolve().parents[1]
HANDLERS = "rpcs3/Emu/RSX/NV47/HW/"
TEXTURES = "rpcs3/Emu/RSX/Common/texture_cache.h"
DRAWS = "rpcs3/Emu/RSX/VK/VKDraw.cpp"
UPSTREAM = {
    "nv0039.cpp": "2a507949680be2ebf4364ff22ffc8224cb56e528",
    "nv308a.cpp": "ab811eb2b9fdcf8bcd7b3eae761b7b42f7fc3959",
    "nv3089.cpp": "6e2e7162bcfce69c8be4eb80ba9d06cea078c228",
}


def without_ios(text):
    lines, out, depth = text.splitlines(keepends=True), [], 0
    for line in lines:
        if line.strip() == "#ifdef RPCS3_IOS":
            assert not depth
            depth = 1
        elif depth:
            if line.lstrip().startswith("#if"):
                depth += 1
            elif line.strip() == "#endif":
                depth -= 1
        else:
            out.append(line)
    assert not depth
    return "".join(out)


def handler(path, version):
    text = path.read_text()
    name = path.stem
    if name == "nv3089":
        body = prehash.braced(text, "void image_in(context* ctx, u32 /*reg*/, u32 /*arg*/)")
        return "namespace rsx::nv3089_" + version + " {\n" + body + "\n}\n"
    return text[text.index("namespace rsx"):].replace("namespace " + name, "namespace " + name + "_" + version, 1)


def make_harness(source, baseline):
    # Reuse only the already audited VM adapter and production extraction, not
    # the historical scenarios, timing loops, races, or their main functions.
    common = prehash.harness(source, True)
    anchor = "\nnamespace\n{\n\tusing section = rsx::after::buffered_section;"
    assert common.count(anchor) == 1
    common = common[:common.index(anchor)]
    adapter = (ROOT / "test/native/rpcs3_rsx_cpu_write.inc").read_text()
    blocks = []
    for version, tree in (("before", baseline), ("after", source), ("desktop", source)):
        if version == "desktop":
            blocks.append("#undef RPCS3_IOS\n")
        blocks.extend(handler(tree / HANDLERS / name, version) for name in UPSTREAM)
        if version == "desktop":
            blocks.append("#define RPCS3_IOS 1\n")
    code = common + adapter.replace("@PRODUCTION_HANDLERS@", "\n".join(blocks))
    code = code.replace("\nint main()\n{", "\nint cpu_write_main()\n{", 1)
    cache = (source / TEXTURES).read_text()
    old_cache = (baseline / TEXTURES).read_text()
    current_draw = (source / DRAWS).read_text()
    old_draw = (baseline / DRAWS).read_text()
    assert cache.count("exact_match.ios_validation_range = cached_texture->get_section_range();") == 2
    assert cache.count("uploaded_descriptor.ios_validation_range = tex_range;") == 1
    assert "get_texture_size" not in prehash.braced(cache, "void finish_sampler_validation(")
    binding = (ROOT / "test/native/rpcs3_rsx_cpu_write_bindings.inc").read_text()
    binding = binding.replace("@IS_EXPIRED@", prehash.braced(cache, "std::pair<bool, surface_type> is_expired("))
    assert prehash.braced(cache, "std::pair<bool, surface_type> is_expired(") == prehash.braced(old_cache, "std::pair<bool, surface_type> is_expired(")
    replacements = {
        "@REQUIRES@": "bool sampler_requires_validation(",
        "@PREPARE@": "rpcs3::ios::texture_validation::sampler_stamp prepare_sampler_validation(",
        "@FINISH@": "void finish_sampler_validation(",
        "@SCOPED@": "void revalidate_overlapping(",
    }
    for token, marker in replacements.items():
        binding = binding.replace(token, prehash.braced(cache, marker))
    binding = binding.replace("@BEFORE_SCOPED@", prehash.braced(old_cache, "void revalidate_overlapping(").replace("void revalidate_overlapping", "void before_revalidate_overlapping", 1))
    for stage, member in (("FS", "m_textures_dirty"), ("VS", "m_vertex_textures_dirty")):
        for version, draw in (("BEFORE", old_draw), ("AFTER", current_draw)):
            at = draw.index("!" + member + "[i]")
            start = draw.rindex("if (!m_samplers_dirty &&", 0, at)
            binding = binding.replace("@" + version + "_" + stage + "_GUARD@", prehash.braced(draw[start:], "if (!m_samplers_dirty &&"))
        at = current_draw.index("!" + member + "[i]")
        start = current_draw.index("#ifdef RPCS3_IOS\n\t\tconst auto validation_", at)
        end = current_draw.index("\n\t\tif (!sampler_state->validate())", start)
        binding = binding.replace("@" + stage + "_LOOKUP@", current_draw[start:end])
    assert "@" not in binding
    return code + "\n" + binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--baseline", type=Path, required=True, help="Authenticated pre-change tree with the three pristine upstream handlers.")
    parser.add_argument("--compiler", default=os.environ.get("CXX", "c++"))
    parser.add_argument("--dependency-root", action="append", type=Path, default=[])
    parser.add_argument("--sanitizer", default="")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    source_hashes, baseline_blobs = {}, {}
    for name, expected in UPSTREAM.items():
        relative = HANDLERS + name
        raw = (baseline / relative).read_bytes()
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        assert blob == expected, (relative, blob, expected)
        old, now = (baseline / relative).read_text(), (source / relative).read_text()
        assert without_ios(now) == old, relative + " changed outside iOS write notifications"
        assert now.count("texture_validation::advance_epoch()") == (4 if name == "nv308a.cpp" else 1)
        source_hashes[relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
        baseline_blobs[relative] = blob
    for relative in (prehash.CACHE, prehash.HEADER, prehash.UTILS, TEXTURES, DRAWS,
                     "rpcs3/ios/IOSTextureValidationProfile.h"):
        source_hashes[relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    compiler = shlex.split(args.compiler)
    flags = ["-std=c++20", "-O2", "-g", "-UNDEBUG", "-Wall", "-Wextra", "-Werror", "-pthread", "-fno-omit-frame-pointer"]
    for tree in [source] + args.dependency_root:
        flags += ["-I" + str(tree / "rpcs3"), "-I" + str(tree)]
    if sdk := os.environ.get("HOST_MACOS_SDK"):
        flags += ["-isysroot", sdk]
    if args.sanitizer:
        flags += ["-fsanitize=" + args.sanitizer]
        if sys.platform.startswith("linux"):
            flags += ["-fno-pie", "-no-pie"]
    code = make_harness(source, baseline)
    with tempfile.TemporaryDirectory(prefix="rpcs3-rsx-cpu-write-") as temporary:
        work = Path(temporary)
        cpp, binary = work / "write.cpp", work / "write"
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=90,
                                env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"))
        if result.returncode:
            raise AssertionError((result.returncode, result.stdout, result.stderr))
        reports = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        assert len(reports) == 2 and all(r["passed"] for r in reports), result.stdout
        report = reports[0]
        report["samplerBindings"] = reports[1]
    assert report["passed"] and report["baselineStaleAccepted"] > 0 and report["candidateStaleAccepted"] == 0
    report.update(compiler=subprocess.check_output(compiler + ["--version"], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer, sourceSHA256=source_hashes,
                  baselineGitBlobs=baseline_blobs, harnessSHA256=hashlib.sha256(code.encode()).hexdigest(),
                  adapterSHA256=hashlib.sha256((ROOT / "test/native/rpcs3_rsx_cpu_write.inc").read_bytes()).hexdigest(),
                  bindingAdapterSHA256=hashlib.sha256((ROOT / "test/native/rpcs3_rsx_cpu_write_bindings.inc").read_bytes()).hexdigest(),
                  physicalDeviceTested=False, gameplayMeasured=False,
                  scope="Production CPU-write handlers, binding guards, descriptor expiry, scoped invalidation, texture validation and prehash rejection; nv3089 conversion and GPU payload/resource boundaries modelled.")
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
