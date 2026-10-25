#!/usr/bin/env python3
"""Execute production Build 543 pipeline lookup, normalization, publication and cache bodies.

Every production body is copied verbatim from the Core source tree (the
543 work tree, and the 542 baseline reconstructed by reverse-applying the
reviewed fixture). Adapters replace Vulkan, Metal and the RPCS3 file layer.
The harness runs under ASan+UBSan and again under TSan. Synthetic requests and
injected disk latency only: no Metal compilation, rendering or iPhone timing.
"""
import argparse, hashlib, json, os, re, shlex, subprocess, tempfile
from pathlib import Path
from rpcs3_memory523_test import braced

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'test/native'
sha = lambda b: hashlib.sha256(b).hexdigest()
HEADERS = ['vulkan/vulkan.h', 'algorithm', 'array', 'atomic', 'bitset', 'cassert', 'chrono', 'cmath', 'condition_variable',
           'cstddef', 'cstdint', 'cstdio', 'cstdlib', 'cstring', 'deque', 'filesystem', 'fstream', 'functional', 'iostream', 'iterator',
           'limits', 'map', 'memory', 'mutex', 'numeric', 'set', 'shared_mutex', 'stdexcept', 'string', 'thread', 'tuple',
           'type_traits', 'unordered_map', 'unordered_set', 'utility', 'vector', 'fcntl.h', 'sys/stat.h', 'unistd.h']
ALIASES = ('using usz=std::size_t;using uchar=unsigned char;using u64=std::uint64_t;using u32=std::uint32_t;'
           'using u16=std::uint16_t;using u8=std::uint8_t;using s32=std::int32_t;using f32=float;\n')
MODIFIED = ['rpcs3/Emu/RSX/Program/ProgramStateCache.h', 'rpcs3/Emu/RSX/VK/VKProgramBuffer.h',
            'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp', 'rpcs3/Emu/RSX/VK/VKGSRender.cpp',
            'rpcs3/Emu/RSX/VK/vkutils/device.cpp', 'rpcs3/Emu/RSX/VK/vkutils/device.h',
            'rpcs3/Emu/RSX/VK/vkutils/pipeline_key_normalization.h', 'rpcs3/Emu/RSX/rsx_cache.h',
            'rpcs3/ios/IOSShaderTiming.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp']
NEW = ['rpcs3/Emu/RSX/Common/deferred_publisher.h']
# Unchanged by 543: copied into a reconstructed baseline as-is.
SHARED = ['rpcs3/util/fnv_hash.hpp', 'rpcs3/Emu/RSX/VK/vkutils/graphics_pipeline_state.hpp',
          'rpcs3/Emu/RSX/VK/VKPipelineCompiler.h']


def baseline(source: Path, work: Path, before: Path | None) -> Path:
    if before:
        return before
    tree = work / 'before'
    for path in MODIFIED + NEW:
        dest = tree / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(ROOT / 'test/fixtures/rpcs3_cell543.diff')], cwd=tree, check=True)
    assert all(not (tree / p).exists() for p in NEW)
    assert not set(SHARED) & set(MODIFIED + NEW)
    for path in SHARED:
        dest = tree / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((source / path).read_bytes())
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    for path, digest in manifest['cell543']['before_sha256'].items():
        assert sha((tree / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    return tree


def common(tree: Path) -> str:
    fnv = (tree / 'rpcs3/util/fnv_hash.hpp').read_text().replace('#pragma once', '').replace('#include "util/types.hpp"', '')
    state = (tree / 'rpcs3/Emu/RSX/VK/vkutils/graphics_pipeline_state.hpp').read_text().replace('#pragma once', '').replace('#include "../VulkanAPI.h"', '')
    compiler = (tree / 'rpcs3/Emu/RSX/VK/VKPipelineCompiler.h').read_text()
    props = braced(compiler, 'struct pipeline_props\n') + ';'
    hashing = braced(compiler, 'inline usz hash_struct<vk::pipeline_props>(')
    # Qualified rpcs3::ios lookups inside a test namespace reach the one global profile.
    return (ALIASES + fnv + state + 'namespace vk {\n' + props + '\n}\nnamespace rpcs3 {template<>\n' + hashing +
            '\nnamespace ios = ::rpcs3::ios;\n}\n')


def normalization(tree: Path) -> str:
    return (tree / 'rpcs3/Emu/RSX/VK/vkutils/pipeline_key_normalization.h').read_text().replace(
        '#pragma once', '').replace('#include "graphics_pipeline_state.hpp"', '')


def lookup_namespace(name: str, tree: Path, after: bool, counter: str, tests: str) -> str:
    lookup = (tree / 'rpcs3/Emu/RSX/Program/ProgramStateCache.h').read_text()
    keys = '\n'.join(braced(lookup, 'struct ' + n + '\n') + ';' for n in ['pipeline_key', 'pipeline_key_hash', 'pipeline_key_compare'])
    body = 'template<typename... Args>\n' + braced(lookup, 'pipeline_data_type get_graphics_pipeline(')
    if after:
        for head in ['pipeline_type* acquire_pipeline(', 'pipeline_type* publish_pipeline(',
                     'void abandon_pipeline_build(', 'void wake_pipeline_waiters()']:
            body += '\n' + braced(lookup, head)
    validation = braced((tree / 'rpcs3/Emu/RSX/VK/VKProgramBuffer.h').read_text(), 'void validate_pipeline_properties(')
    adapter = (NATIVE / 'rpcs3_lookup543_adapter.inc').read_text()
    adapter = 'using Props=vk::pipeline_props;\n' + adapter.replace('// KEY_TYPES', keys).replace('// LOOKUP', body).replace('// VALIDATION', validation)
    return ('namespace ' + name + ' {\n' + ('#define CELL543_AFTER\n' if after else '') + common(tree) + normalization(tree) +
            'using namespace vk;\nusing BuildCounter=' + counter + ';\n' + adapter + tests + '\n' +
            ('#undef CELL543_AFTER\n' if after else '') + '}\n')


def store_namespace(name: str, tree: Path, after: bool) -> str:
    cache = (tree / 'rpcs3/Emu/RSX/rsx_cache.h').read_text()
    adapter = (NATIVE / 'rpcs3_publish543_adapter.inc').read_text()
    adapter = adapter.replace('// PIPELINE_DATA', braced(cache, 'struct pipeline_data\n') + ';')
    adapter = adapter.replace('// WRITE_ATOMICALLY', braced(cache, 'static bool write_atomically('))
    adapter = adapter.replace('// PACK', braced(cache, 'pipeline_data pack('))
    methods = braced(cache, 'void store(const pipeline_storage_type &pipeline')
    if after:
        adapter = adapter.replace('// PENDING_RECORD', braced(cache, 'struct pending_record\n') + ';\n' +
                                  re.search(r'static constexpr usz maximum_deferred_records = \d+;', cache).group(0))
        adapter = adapter.replace('// CONSTRUCTOR_PUBLISHER', braced(cache, 'if (!root_path.empty())\n'))
        for head in ['void flush_pending_writes()', 'bool write_record(const pending_record& record) const',
                     'bool write_record_files(const pending_record& record) const']:
            methods += '\n' + braced(cache, head)
        adapter = adapter.replace('// PUBLISHER_MEMBER', 'std::unique_ptr<deferred_publisher<pending_record>> m_publisher;')
    adapter = adapter.replace('// STORE_METHODS', methods)
    return ('namespace ' + name + ' {\n' + ('#define CELL543_AFTER\n' if after else '') + common(tree) +
            ('using rsx::deferred_publisher;\n' if after else '') + adapter +
            (NATIVE / 'rpcs3_publish543.inc').read_text() + '\n' + ('#undef CELL543_AFTER\n' if after else '') + '}\n')


def feedback_section(tree: Path) -> str:
    pipeline = (tree / 'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp').read_text()
    device_cpp = (tree / 'rpcs3/Emu/RSX/VK/vkutils/device.cpp').read_text()
    device_h = (tree / 'rpcs3/Emu/RSX/VK/vkutils/device.h').read_text()
    text = (NATIVE / 'rpcs3_feedback543.inc').read_text()
    text = text.replace('// CREATION_FEEDBACK', braced(pipeline, 'struct creation_feedback\n') + ';\n' +
                        braced(pipeline, 'void note_cache_effect('))
    constants = device_cpp[device_cpp.index('constexpr u32 pipeline_cache_file_magic'):
                           device_cpp.index('static_assert(sizeof(pipeline_cache_file_header) == 40);')]
    text = text.replace('// SAVE_CONSTANTS', constants)
    text = text.replace('// NOTE_UPDATE', braced(device_h, 'void note_pipeline_cache_update('))
    save = braced(device_cpp, 'void render_device::save_pipeline_cache() const').replace('render_device::', '', 1)
    return text.replace('// SAVE_BODY', save)


def build(source: Path, before: Path, work: Path, sanitizer: str, cxx: list[str]) -> tuple[Path, bytes]:
    code = '#define VK_NO_PROTOTYPES\n#define RPCS3_IOS 1\n' + ''.join('#include <' + h + '>\n' for h in HEADERS)
    code += '#include "ios/IOSShaderTiming.h"\n#include "Emu/RSX/Common/deferred_publisher.h"\n'
    code += ('using usz=std::size_t;using u64=std::uint64_t;using u32=std::uint32_t;using u16=std::uint16_t;using u8=std::uint8_t;'
             'using s32=std::int32_t;\n')
    code += ('struct umax_impl { template<class T> constexpr operator T() const { return std::numeric_limits<T>::max(); } };\n'
             'inline constexpr umax_impl umax{};\n')
    code += 'template<class T, class U> T narrow(U v) { assert(v<=std::numeric_limits<T>::max()); return static_cast<T>(v); }\n'
    lookup_tests = (NATIVE / 'rpcs3_lookup543.inc').read_text()
    code += lookup_namespace('before', before, False, 'std::atomic<unsigned>', lookup_tests)
    code += lookup_namespace('after', source, True, 'std::atomic<unsigned>', lookup_tests)
    code += lookup_namespace('regression542', source, True, 'unsigned',
                             '#define CELL542_AFTER\n' + (NATIVE / 'rpcs3_pipeline542.inc').read_text() + '\n#undef CELL542_AFTER\n')
    code += store_namespace('store_before', before, False) + store_namespace('store_after', source, True)
    code += (NATIVE / 'rpcs3_deferred543.inc').read_text() + feedback_section(source)
    code += (NATIVE / 'rpcs3_timing542.inc').read_text()
    code += (NATIVE / 'rpcs3_main543.inc').read_text()
    cpp = work / ('cell543-' + sanitizer + '.cpp')
    cpp.write_text(code)
    exe = work / ('cell543-' + sanitizer)
    flags = ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-format-security',
             '-Wno-missing-field-initializers',
             '-pthread', '-fno-omit-frame-pointer']
    flags += ['-fsanitize=address,undefined'] if sanitizer == 'asan' else ['-fsanitize=thread']
    subprocess.run(cxx + flags + ['-I' + str(ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include'),
                                  '-I' + str(source / 'rpcs3'), str(cpp), '-o', str(exe)], check=True)
    return exe, cpp.read_bytes()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--before', type=Path, help='Build 542 tree; default: reverse-apply the reviewed fixture')
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    results = {}
    with tempfile.TemporaryDirectory(prefix='cell543-') as td:
        work = Path(td)
        before = baseline(source, work, a.before.resolve() if a.before else None)
        for sanitizer in ('asan', 'tsan'):
            exe, code = build(source, before, work, sanitizer, cxx)
            scratch = work / ('io-' + sanitizer)
            scratch.mkdir()
            env = dict(os.environ, CELL543_SCRATCH=str(scratch), ASAN_OPTIONS='detect_leaks=0',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1', TSAN_OPTIONS='halt_on_error=1:second_deadlock_stack=1')
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=900, env=env)
            if run.returncode:
                print(run.stdout)
                print(run.stderr)
                run.check_returncode()
            results[sanitizer] = json.loads(run.stdout)
            results[sanitizer]['harnessSHA256'] = sha(code)
    # Source-bound checks for paths the host harness cannot execute.
    perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    for marker in ('COREPROF SHADERPUB543', 'COREPROF SHADERPIPE543', 'context543=1 origin=%u feedback=%u'):
        assert marker in perf, marker
    device = (source / 'rpcs3/Emu/RSX/VK/vkutils/device.cpp').read_text()
    assert 'requested_extensions.push_back(VK_EXT_PIPELINE_CREATION_FEEDBACK_EXTENSION_NAME);' in device
    assert 'device_extensions.is_supported(VK_EXT_PIPELINE_CREATION_FEEDBACK_EXTENSION_NAME)' in device
    pipeline = (source / 'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp').read_text()
    assert 'feedback.chain(create_info, create_info.stageCount);' in pipeline and 'CHECK_RESULT(result);' in pipeline
    render = (source / 'rpcs3/Emu/RSX/VK/VKGSRender.cpp').read_text()
    assert 'm_shaders_cache->flush_pending_writes();' in render
    buffer = (source / 'rpcs3/Emu/RSX/VK/VKProgramBuffer.h').read_text()
    assert 'normalize_pipeline_depth_stencil(properties.state, properties.renderpass_key);' in buffer
    report = dict(passed=True, sanitizers=['address', 'undefined', 'thread'], physicalDeviceTested=False, gameplayMeasured=False,
                  results=results,
                  scope=('Exact production lookup/single-flight, depth-stencil normalization, shader-cache publication, '
                         'creation-feedback interpretation and VkPipelineCache save skipping with adapters. Synthetic requests and '
                         'injected disk latency; no Metal compilation, rendering or iPhone frame-time measurement.'))
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
