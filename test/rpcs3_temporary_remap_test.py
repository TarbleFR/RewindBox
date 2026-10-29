#!/usr/bin/env python3
"""Exercise production temporary-cache lookup and Vulkan view remapping.

Extracts cache lookup/invalidation/release, descriptor key, channel decoding,
component selection, view lookup/format reinterpretation and the new wrapper.
Only Vulkan allocation/submission and image payload copies are host boundaries.
This proves a cache/view regression, not a game's visual result or iPhone FPS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile

from rpcs3_texture_address_index_test import braced
from rpcs3_texture_exact_index_test import stripped

ROOT = Path(__file__).resolve().parents[1]
VK = 'rpcs3/Emu/RSX/VK/'
CACHE = 'rpcs3/Emu/RSX/Common/texture_cache.h'
ARRAY = 'rpcs3/Emu/RSX/Common/simple_array.hpp'
RANGE = 'Utilities/address_range.h'
COLOR = 'rpcs3/Emu/RSX/Utils/color_utils.hpp'
ATTRS = 'rpcs3/Emu/RSX/Common/TextureUtils.h'
SOURCE = [VK + 'VKTextureCache.h', VK + 'VKTextureCache.cpp']
SUPPORT = [CACHE, ARRAY, RANGE, COLOR, ATTRS, VK + 'vkutils/image.cpp',
           VK + 'vkutils/image_helpers.cpp', VK + 'VKDraw.cpp', VK + 'VKGSRender.h']
ADAPTER = ROOT / 'test/native/rpcs3_temporary_remap.inc'
SIGNATURE = 'vk::image_view* texture_cache::create_temporary_subresource('
DECLARATION = '\t\tvk::image_view* create_temporary_subresource(vk::command_buffer& cmd, deferred_subresource& desc);'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def harness(source, baseline):
    for path in SUPPORT:
        assert sha(source / path) == sha(baseline / path), path
    cpp = (source / SOURCE[1]).read_text()
    wrapper = braced(cpp, SIGNATURE)
    assert cpp.replace('#ifdef RPCS3_IOS\n\t' + wrapper + '\n#endif\n\n', '') == (baseline / SOURCE[1]).read_text()
    header = (source / SOURCE[0]).read_text()
    assert header.replace('#ifdef RPCS3_IOS\n' + DECLARATION + '\n#endif\n\n', '') == (baseline / SOURCE[0]).read_text()
    assert 'vk::texture_cache m_texture_cache;' in (source / (VK + 'VKGSRender.h')).read_text()
    assert (source / (VK + 'VKDraw.cpp')).read_text().count('m_texture_cache.create_temporary_subresource(') == 5

    cache = (source / CACHE).read_text()
    color = (source / COLOR).read_text()
    desc = cache[cache.index('struct deferred_subresource :'):]
    desc = desc[:desc.index('\n\t\t\tdeferred_subresource() = default;')] + '\n' + braced(desc, 'u64 encoded_properties() const') + '\n};'
    remap_fields = color[color.index('struct texture_channel_remap_t'):color.index('\n\t\ttemplate <typename T>', color.index('struct texture_channel_remap_t'))]
    remap = remap_fields + '\n template<typename T>\n' + braced(color, 'std::array<T, 4> remap(') + '\n};\n'
    frame = braced(cache, 'virtual void on_frame_end()')
    begin, end = frame.index('for (auto& entry : m_temporary_subresource_cache)'), frame.index('m_predictor.on_frame_end();')
    key = braced(cache, 'struct temporary_subresource_key\n') + ';'
    code = ADAPTER.read_text()
    replacements = {
        '@RANGE@': stripped(source / RANGE),
        '@ARRAY@': '#define RPCS3_IOS\n' + stripped(source / ARRAY) + '\n#undef RPCS3_IOS',
        '@ATTRIBUTES@': braced((source / ATTRS).read_text(), 'struct image_section_attributes_t\n') + ';',
        # The unchanged decoder initializes each array immediately below its
        # designated initializer. Keep its source exact, and scope GCC's
        # missing-field-initializers diagnostic only to this extracted helper.
        '@REMAP@': remap + '\n#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wmissing-field-initializers"\n' + braced(color, 'static inline texture_channel_remap_t decode_remap_encoding(') + '\n#pragma GCC diagnostic pop\n',
        '@APPLY_REMAP@': braced((source / (VK + 'vkutils/image_helpers.cpp')).read_text(), 'VkComponentMapping apply_swizzle_remap('),
        '@GET_VIEW@': braced((source / (VK + 'vkutils/image.cpp')).read_text(), 'image_view* viewable_image::get_view('),
        '@AS@': braced((source / (VK + 'vkutils/image.cpp')).read_text(), 'image_view* image_view::as('),
        '@SET_LAYOUT@': braced((source / (VK + 'vkutils/image.cpp')).read_text(), 'void viewable_image::set_native_component_layout('),
        '@DESCRIPTOR@': desc,
        '@KEY@': key,
        '@LOOKUP@': braced(cache, 'image_view_type create_temporary_subresource('),
        '@INVALIDATE@': braced(cache, 'void notify_surface_changed('),
        '@CLEAR@': 'void clear() {' + frame[begin:end] + '\n release_uncached_temporary_subresources(); }',
        '@CLEAR_UNCACHED@': braced(cache, 'void release_uncached_temporary_subresources('),
        '@WRAPPER@': wrapper,
    }
    for marker, value in replacements.items():
        code = code.replace(marker, value)
    assert '@' not in code
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    code = harness(source, baseline)
    inputs = {p: sha(source / p) for p in SOURCE + SUPPORT}
    flags = ['-std=c++20', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-g']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    flags += ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitizer else ['-O3']
    if args.sanitizer and platform.system() == 'Linux':
        flags += ['-fno-pie', '-no-pie']
    compiler = shlex.split(args.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-temporary-remap-') as temp:
        cpp, exe = Path(temp) / 'test.cpp', Path(temp) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], text=True, capture_output=True, timeout=180,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            raise RuntimeError(run.stdout + run.stderr)
    assert inputs == {p: sha(source / p) for p in SOURCE + SUPPORT}
    report = dict(passed=True, sourceSHA256=inputs,
                  baselineSHA256={p: sha(baseline / p) for p in SOURCE + SUPPORT},
                  harnessSHA256=hashlib.sha256(code.encode()).hexdigest(), adapterSHA256=sha(ADAPTER),
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, host=platform.machine(), sanitizer=args.sanitizer,
                  results=json.loads(run.stdout), physicalDeviceTested=False, gameplayMeasured=False,
                  leakSanitizerEnabled=False, scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
