#!/usr/bin/env python3
"""Run production texture selection and Vulkan pipeline keys against their preimages.

The storage/GPU are adapters. Timings cover a synthetic CPU lookup, never a
Metal compile or iPhone gameplay. No project build or historical suite is run.
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

from rpcs3_memory523_test import braced
from rpcs3_cell559_test import without_ios_blocks

ROOT = Path(__file__).resolve().parents[1]
TEXTURE = 'rpcs3/Emu/RSX/Common/texture_cache.h'
PROGRAM = 'rpcs3/Emu/RSX/VK/VKProgramBuffer.h'
NORMALIZE = 'rpcs3/Emu/RSX/VK/vkutils/pipeline_key_normalization.h'
CACHE = 'rpcs3/Emu/RSX/Program/ProgramStateCache.h'
PATHS = [TEXTURE, PROGRAM, NORMALIZE, CACHE]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def texture_body(tree):
    text = (tree / TEXTURE).read_text()
    anchor = text.index('// Check shader_read storage. In a given scene, reads from local memory')
    start = text.index('\t\t\tconst u32 lookup_mask =', anchor)
    end = text.index('\n\t\t\tif (!options.prefer_surface_cache)', start)
    return text[start:end]


def stripped(path):
    return '\n'.join(line for line in path.read_text().splitlines()
                     if not line.startswith(('#include ', '#pragma once')))


def generate(source, before):
    preamble = '''#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <chrono>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <memory>
#include <mutex>
#include <random>
#include <shared_mutex>
#include <thread>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using usz=std::size_t; using uchar=unsigned char;
using u64=std::uint64_t; using u32=std::uint32_t; using u16=std::uint16_t;
using u8=std::uint8_t; using f32=float;
template<class T> concept UnsignedInt=std::is_integral_v<T> && std::is_unsigned_v<T>;
template<class C> u32 size32(const C& c) { return static_cast<u32>(c.size()); }
#define ensure(condition) do { if (!(condition)) std::abort(); } while (false)
#define AUDIT(condition) ensure(condition)
inline u64 allocations=0;
namespace rsx {
template<class T> using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t Align> void* malloc(size_t bytes) { ++allocations; return std::malloc(bytes); }
template<size_t Align> void* realloc(void* data,size_t,size_t bytes) { ++allocations; return std::realloc(data,bytes); }
inline void free(void* data) { std::free(data); }
}}
'''
    code = preamble + stripped(source / 'rpcs3/Emu/RSX/Common/simple_array.hpp')
    code += stripped(source / 'rpcs3/util/fnv_hash.hpp')
    code += stripped(source / 'rpcs3/Emu/RSX/VK/vkutils/graphics_pipeline_state.hpp')
    compiler = (source / 'rpcs3/Emu/RSX/VK/VKPipelineCompiler.h').read_text()
    code += '\nnamespace vk {\n' + braced(compiler, 'struct pipeline_props\n') + ';\n}\n'
    code += '\nnamespace rpcs3 {template<>\n' + braced(compiler, 'inline usz hash_struct<vk::pipeline_props>(') + '\n}\n'
    # All unchanged production types/hash functions above are shared by both versions.
    code += '''
struct Shader { u32 output_color_masks[4]{15,15,15,15}; };
using VKVertexProgram=Shader; using VKFragmentProgram=Shader;
'''
    for label, tree in [('before', before), ('after', source)]:
        code += '\nnamespace ' + label + ' { using namespace vk;\n'
        normalization = stripped(tree / NORMALIZE).replace('namespace vk\n{', 'namespace vk\n{\nusing namespace ::vk;')
        # Place the actual vk namespace in this test's version namespace.
        code += normalization + '\nusing namespace vk;\n'
        code += braced((tree / PROGRAM).read_text(), 'void validate_pipeline_properties(')
        code += '\n}\n'
    adapter = (ROOT / 'test/native/rpcs3_hotpaths.inc').read_text()
    find = braced((source / TEXTURE).read_text(), 'rsx::simple_array<section_storage_type*> find_texture_from_range(')
    code += adapter.split('// VERSIONED_TEXTURE_CLASSES')[0]
    for label, tree in [('before', before), ('after', source)]:
        code += '\nstruct ' + label + '_texture : TextureAdapter {\nusing TextureAdapter::TextureAdapter;\n'
        code += 'template<bool check_unlocked=false, bool check_protection=true>\n' + find
        code += '\n[[gnu::noinline]] Result query() {\nrsx::simple_array<Texture*> overlapping_locals;\n'
        code += texture_body(tree)
        code += '''
Result result{};
for (auto* texture : overlapping_locals) result.merge.push_back(texture->id);
return result;
}\n};\n'''
    code += adapter.split('// VERSIONED_TEXTURE_CLASSES')[1]
    cache = (source / CACHE).read_text()
    recent = (ROOT / 'test/native/rpcs3_recent_pipeline.inc').read_text()
    keys = '\n'.join(braced(cache, 'struct ' + name + '\n') + ';'
                     for name in ['pipeline_key', 'pipeline_key_hash', 'pipeline_key_compare'])
    recent = recent.replace('// KEY_TYPES', keys)
    for marker, signature in [('FIND', 'pipeline_type* find_cached_pipeline('),
                              ('PUBLISH', 'pipeline_type* publish_pipeline('),
                              ('ABANDON', 'void abandon_pipeline_build('), ('CLEAR', 'void clear()')]:
        recent = recent.replace('// ' + marker, braced(cache, signature))
    code = code.replace('// RECENT_PIPELINE_TESTS', recent)
    return code


def manifest_contract(source):
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['runtime_20261029']
    baseline = json.loads(subprocess.check_output(
        ['git', 'show', record['baseline_commit'] + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert record['modified_paths'] == PATHS
    expected = dict(baseline['files_sha256'])
    expected.update(record['after_sha256'])
    followup = manifest.get('runtime_followup_20261029')
    if followup:
        parent = json.loads(subprocess.check_output(
            ['git', 'show', followup['baseline_commit'] + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
        assert parent['files_sha256'] == expected
        assert followup['core_baseline_patch_sha256'] == parent['patch_sha256']
        assert set(followup['modified_paths']) == {
            'rpcs3/Emu/Cell/lv2/sys_time.cpp',
            'rpcs3/Emu/RSX/VK/vkutils/descriptors.cpp',
            'rpcs3/Emu/RSX/VK/vkutils/descriptors.h'}
        assert set(followup['after_sha256']) == set(followup['modified_paths'])
        assert set(followup['before_sha256']) == set(followup['modified_paths'])
        assert followup['codegen'] == record['codegen']
        for relative in followup['modified_paths']:
            before = subprocess.check_output(
                ['git', 'show', followup['preimages_from_upstream'] + ':' + relative], cwd=source)
            assert hashlib.sha256(before.replace(b'\r\n', b'\n')).hexdigest() == followup['before_sha256'][relative]
            assert digest(source / relative) == followup['after_sha256'][relative]
        expected.update(followup['after_sha256'])
    assert manifest['files_sha256'] == expected
    assert digest(ROOT / record['fixture']) == record['fixture_sha256']
    for relative in PATHS:
        assert digest(source / relative) == record['after_sha256'][relative]
    return manifest, record, baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--before', type=Path)
    sanitizer = parser.add_mutually_exclusive_group()
    sanitizer.add_argument('--sanitize', action='store_true')
    sanitizer.add_argument('--thread-sanitize', action='store_true')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    manifest, record, baseline = manifest_contract(source)
    with tempfile.TemporaryDirectory(prefix='rpcs3-hotpaths-') as tmp:
        work = Path(tmp)
        before = args.before.resolve() if args.before else work / 'before'
        if not args.before:
            for relative in PATHS:
                target = before / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source / relative).read_bytes())
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / 'test/fixtures/rpcs3_hotpaths_20261029.diff')],
                           cwd=before, check=True)
        # No off-iOS implementation is changed, including the old lookup branch.
        for relative in PATHS:
            assert digest(before / relative) == baseline['files_sha256'][relative] == record['before_sha256'][relative]
            assert digest(source / relative) == manifest['files_sha256'][relative] == record['after_sha256'][relative]
            assert without_ios_blocks((before / relative).read_text()) == without_ios_blocks((source / relative).read_text()), relative
        compiler = (source / 'rpcs3/Emu/RSX/VK/VKPipelineCompiler.cpp').read_text()
        for state in ['LINE_WIDTH', 'DEPTH_BIAS', 'BLEND_CONSTANTS', 'STENCIL_COMPARE_MASK', 'STENCIL_WRITE_MASK', 'STENCIL_REFERENCE', 'DEPTH_BOUNDS']:
            assert 'dynamic_state_descriptors.push_back(VK_DYNAMIC_STATE_' + state + ')' in compiler
        assert 'ds2.depthBoundsTestEnable = VK_FALSE' in compiler
        draw = (source / 'rpcs3/Emu/RSX/VK/VKDraw.cpp').read_text()
        for setter in ['line_width', 'depth_bias', 'blend_constants', 'depth_bounds', 'stencil_compare_mask', 'stencil_write_mask', 'stencil_reference']:
            assert 'm_current_command_buffer->set_' + setter + '(' in draw
        cpp = work / 'hotpaths.cpp'
        cpp.write_text(generate(source, before))
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        if sdk := os.environ.get('HOST_MACOS_SDK'):
            cxx += ['-isysroot', sdk]
        flags = ['-std=c++20', '-UNDEBUG', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-DRPCS3_IOS']
        if args.thread_sanitize:
            flags += ['-O1', '-fsanitize=thread', '-fno-omit-frame-pointer']
        elif args.sanitize:
            flags += ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-DTEXTURE_CACHE_DEBUG']
        else:
            flags += ['-O3']
        exe = work / 'hotpaths'
        subprocess.run(cxx + flags + ['-I' + str(ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include'),
                                      str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)] + (['benchmark'] if args.benchmark else []),
                             capture_output=True, text=True, timeout=90,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            print(run.stderr)
            run.check_returncode()
        report = {'passed': True, 'host': platform.machine(), 'sanitized': args.sanitize,
                  'leakSanitizer': False,
                  'threadSanitized': args.thread_sanitize,
                  'debugTexturePath': args.sanitize, 'offIOSUnchanged': PATHS,
                  'sourceBefore': {p: digest(before / p) for p in PATHS},
                  'sourceAfter': {p: digest(source / p) for p in PATHS},
                  'harnessSHA256': digest(cpp), 'results': json.loads(run.stdout),
                  'physicalDeviceTested': False, 'MetalCompiled': False, 'gameplayMeasured': False,
                  'scope': 'Production pipeline structs/hash/normalization, production simple_array and texture selection; range storage and GPU are adapters. Synthetic CPU lookup timing only.'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
