#!/usr/bin/env python3
"""Exercise shader-dependent view, filtering, conversion and parameter updates.

The complete before/after prefetch bodies and actual texture fast path, remapping,
filter selection, conversion-control branches and parameter transfer are compiled.
GPU image/cache handles, guest instruction decoding and ring allocation are adapters.
This test produces no rendered pixels or device/FPS result.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile

from rpcs3_bo2_fragment_key_test import braced

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ['rpcs3/Emu/RSX/RSXThread.cpp', 'rpcs3/Emu/RSX/VK/VKDraw.cpp', 'rpcs3/Emu/RSX/VK/VKGSRender.cpp']
SUPPORT = ['rpcs3/Emu/RSX/Core/RSXDriverState.h', 'rpcs3/Emu/RSX/Program/program_util.h',
           'rpcs3/Emu/RSX/Program/program_util.cpp', 'rpcs3/Emu/RSX/Common/TextureUtils.h',
           'rpcs3/Emu/RSX/Common/TextureUtils.cpp', 'rpcs3/Emu/RSX/Utils/color_utils.hpp',
           'rpcs3/Emu/RSX/gcm_enums.h', 'rpcs3/Emu/RSX/Program/ProgramStateCache.cpp',
           'rpcs3/Emu/RSX/VK/VKFragmentProgram.cpp', 'rpcs3/Emu/RSX/Program/GLSLCommon.cpp']
ADAPTER = ROOT / 'test/native/rpcs3_bx2_sampler_transition.inc'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def statement(text, marker):
    start = text.index(marker)
    return text[start:text.index(';', start) + 1]


def harness(source, baseline):
    read = lambda p: (source / p).read_text()
    thread, draw, render = [read(p) for p in SOURCE]
    old_thread = (baseline / SOURCE[0]).read_text()
    for path in SUPPORT + [SOURCE[1]]:
        assert sha(source / path) == sha(baseline / path), path
    driver, program_h, program_cpp, texture_h, texture_cpp, color, gcm, cache, fragment, glsl = [read(p) for p in SUPPORT]
    code = ADAPTER.read_text()
    constants = braced(driver, 'enum pipeline_state : u32') + ';\n'
    constants += braced(color, 'enum texture_control_bits : u32') + ';\n'
    for marker in ['enum format_features : u8', 'enum host_format_features : u8']:
        constants += braced(texture_h, marker) + ';\n'
    shader_start = gcm.rfind('\tenum\n\t{', 0, gcm.index('CELL_GCM_SHADER_CONTROL_DEPTH_EXPORT'))
    assert shader_start >= 0
    constants += braced(gcm[shader_start:], 'enum\n') + ';\n'
    for name in ['CELL_GCM_TEXTURE_A8R8G8B8', 'CELL_GCM_TEXTURE_D8R8G8B8',
                 'CELL_GCM_TEXTURE_LN', 'CELL_GCM_TEXTURE_UN', 'RSX_TEXTURE_REMAP_IDENTITY']:
        value = re.search(r'\b' + name + r'\s*=\s*([^,\n]+),', gcm).group(1)
        constants += 'constexpr u32 ' + name + ' = ' + value + ';\n'
    constants += statement(thread, 'constexpr u32 fs_export_config_mask =') + '\n'
    code = code.replace('// @CONSTANTS@', constants)
    types = '\n'.join(braced(program_h, 'struct ' + name + '\n') + ';'
                      for name in ['fragment_program_texture_config', 'fragment_program_texture_state'])
    types += '\n' + braced(texture_h, 'struct texture_format_ex\n') + ';\n'
    code = code.replace('// @PROGRAM_TYPES@', types)
    methods = '\n'.join(braced(program_cpp, marker) for marker in [
        'static u32 duplicate_and_extend(', 'void fragment_program_texture_config::masked_transfer(',
        'void fragment_program_texture_config::write_to(', 'void fragment_program_texture_state::clear(',
        'void fragment_program_texture_state::import(', 'void fragment_program_texture_state::set_dimension(',
        'bool fragment_program_texture_state::operator == ('])
    code = code.replace('// @PROGRAM_METHODS@', methods)
    methods = '\n'.join(braced(texture_cpp, 'bool texture_format_ex::' + name + '() const')
                        for name in ['hw_SNORM_possible', 'hw_SRGB_possible'])
    code = code.replace('// @FORMAT_METHODS@', methods)
    prefetch = 'void thread::prefetch_fragment_program()'
    code = code.replace('// @PREFETCH_BEFORE@', braced(old_thread, prefetch).replace(prefetch, 'void thread::prefetch_before()', 1))
    code = code.replace('// @PREFETCH_AFTER@', braced(thread, prefetch).replace(prefetch, 'void thread::prefetch_after()', 1))
    load = braced(draw, 'void VKGSRender::load_texture_env()')
    begin = load.index('for (u32 textures_ref = current_fp_metadata.referenced_textures_mask;')
    end = load.index('VkFilter mag_filter;', begin)
    code = code.replace('// @TEXTURE_PREFIX@', load[begin:end])
    filter_selection = statement(load, 'const bool sext_conv_required =') + '\n'
    begin = load.index('bool can_sample_linear;')
    filter_selection += load[begin:load.index('const auto mipmap_count', begin)]
    filter_selection += statement(load, 'min_filter = vk::get_min_filter(') + '\n'
    begin = load.index('if (can_sample_linear)')
    branch = braced(load[begin:], 'if (can_sample_linear)')
    tail = load[begin + len(branch):]
    assert tail.lstrip().startswith('else')
    filter_selection += branch + '\n' + braced(tail, 'else')
    code = code.replace('// @FILTER_SELECTION@', filter_selection)
    params = braced(thread, 'void thread::get_current_fragment_program(')
    begin = params.index('{') + 1
    last = 'current_fragment_program.ctrl &= fs_export_config_mask;'
    code = code.replace('// @PARAMETER_GUARD@', params[begin:params.index(last) + len(last)])
    control = statement(params, 'current_fragment_program.texture_params[i].remap = tex.remap()') + '\n'
    control += statement(params, 'm_graphics_state |= rsx::pipeline_state::fragment_texture_state_dirty;')
    code = code.replace('// @PARAMETER_REMAP@', control)
    format_marker = 'if (const auto& format_ex = sampler_descriptors[i]->format_ex; format_ex.features != 0)'
    code = code.replace('// @FORMAT_PARAMETERS@', braced(params, format_marker))
    code = code.replace('// @PARAMETER_CONTROL@', statement(params, 'current_fragment_program.texture_params[i].control ='))
    env = braced(render, 'void VKGSRender::load_program_env()')
    code = code.replace('// @PARAMETER_UPLOAD@', braced(env, 'if (update_fragment_texture_env)'))
    code = code.replace('// @CACHE_PROPERTIES@', braced(cache, 'bool fragment_program_compare::compare_properties('))
    code = code.replace('// @CACHE_NORMALIZATION@', braced(cache, 'std::optional<RSXFragmentProgram> fragment_program_utils::normalize_fragment_program_key('))
    code = code.replace('// @CONVERSION_PROPERTY@', statement(fragment, 'm_shader_props.require_color_format_convert ='))
    code = code.replace('// @CONVERSION_OPTION@', braced(glsl, 'if (props.require_color_format_convert)'))
    assert '// @' not in code
    return code


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    return dict(sourceSHA256={p: sha(source / p) for p in SOURCE + SUPPORT},
                baselineSHA256={p: sha(baseline / p) for p in SOURCE + SUPPORT},
                adapterSHA256=sha(ADAPTER),
                harnessSHA256=hashlib.sha256(harness(source, baseline).encode()).hexdigest())


def verify_counts(results):
    assert set(results) == {'ios', 'desktop'}
    for name, values in results.items():
        assert values == dict(transitions=16, baselineTransitionDefects=16,
                              candidateTransitionDefects=0 if name == 'ios' else 16,
                              lifecycleCases=24 if name == 'ios' else 0, baselineNegativeControls=7,
                              conversionRemovalCases=4, baselineRedundantConversionKeys=4,
                              candidateRedundantConversionKeys=0 if name == 'ios' else 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    identity = expected(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    flags += ['-O1', '-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer'] if args.sanitizer else ['-O3']
    if args.sanitizer and platform.system() == 'Linux':
        flags += ['-fno-pie', '-no-pie']
    results = {}
    with tempfile.TemporaryDirectory(prefix='rpcs3-bx2-sampler-') as directory:
        cpp = Path(directory) / 'test.cpp'
        cpp.write_text(harness(args.source, args.baseline))
        for ios in [False, True]:
            name = 'ios' if ios else 'desktop'
            exe = Path(directory) / name
            subprocess.run(compiler + flags + (['-DRPCS3_IOS'] if ios else []) + [str(cpp), '-o', str(exe)], check=True)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
            if run.returncode or run.stderr:
                raise RuntimeError(f'{name}: {run.returncode}\n{run.stdout}\n{run.stderr}')
            results[name] = json.loads(run.stdout)
    verify_counts(results)
    assert identity == expected(args.source, args.baseline)
    report = dict(passed=True, assertionsActive=True, compilerFlags=flags,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  host=platform.machine(), system=platform.system(), sanitizer=args.sanitizer,
                  **identity, results=results, physicalDeviceTested=False, gameplayMeasured=False,
                  gpuExecuted=False, scope=__doc__)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
