#!/usr/bin/env python3
"""Diagnose the two glslang versions loaded by NeoStation's full image.

Build the unmodified compiler sources of the pinned Dolphin revision as a
separate dylib, then the shader kit as a separate dylib, in the same load
order as Runner. This is a compiler/linkage test, not a Dolphin engine or
device rendering test. Keep the native backtrace and Mach-O identities.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOLPHIN = '7cac54161659421ed95c2cd1c0b0746539a4cd38'
PRESETS = ('reshade/handheld-color-LUTs/PSP-2020.slangp',
           'crt/crt-easymode.slangp', 'crt/crt-geom.slangp',
           'pixel-art-scaling/sharp-bilinear.slangp')


def run(command, **kwargs):
    result = subprocess.run(list(map(str, command)), text=True, capture_output=True, **kwargs)
    if result.returncode:
        print(result.stdout[-6000:] + result.stderr[-6000:], flush=True)
        raise SystemExit(f'command failed ({result.returncode}): {command[0]}')
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dolphin-ios', type=Path, required=True)
    parser.add_argument('--slang-shaders', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--diagnose', action='store_true', help='record outcomes without claiming a fix')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('This test requires macOS dyld, not ELF symbol interposition.')
    assert run(['git', '-C', args.dolphin_ios, 'rev-parse', 'HEAD']).strip() == DOLPHIN
    args.evidence.mkdir(parents=True, exist_ok=True)
    kit = ROOT / 'packages/neo_shader_kit/ios'
    old = args.dolphin_ios.resolve() / 'Externals/glslang'
    cmake_sources = (old / 'CMakeLists.txt').read_text()
    # Precisely the list compiled into Dolphin, without its CMake wrappers.
    source_block = cmake_sources.split('set(SRCS', 1)[1].split('\n)', 1)[0]
    sources = [old / line.strip() for line in source_block.splitlines()
               if line.strip() and not line.strip().startswith('#')]
    sources += [old / 'glslang/OSDependent/Unix/ossource.cpp']
    project = args.evidence.resolve() / 'project'
    project.mkdir(exist_ok=True)
    # -Os matches the release pod's optimization and retains the explicit
    # weak addSwizzle instantiations. Two-level namespace is the default.
    cmake = f'''cmake_minimum_required(VERSION 3.16)
project(neo_compiler_coexistence CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "-Os -g -fno-omit-frame-pointer")
add_library(dolphin_glslang SHARED {' '.join('"' + str(p) + '"' for p in sources)})
target_include_directories(dolphin_glslang PRIVATE "{old}")
target_compile_options(dolphin_glslang PRIVATE -w)
file(GLOB NEW_GLSLANG "{kit}/ThirdParty/glslang/glslang/MachineIndependent/*.cpp"
  "{kit}/ThirdParty/glslang/glslang/MachineIndependent/preprocessor/*.cpp"
  "{kit}/ThirdParty/glslang/glslang/GenericCodeGen/*.cpp"
  "{kit}/ThirdParty/glslang/glslang/OSDependent/Unix/ossource.cpp"
  "{kit}/ThirdParty/glslang/glslang/ResourceLimits/*.cpp" "{kit}/ThirdParty/glslang/SPIRV/*.cpp")
file(GLOB NEW_CROSS "{kit}/ThirdParty/SPIRV-Cross/*.cpp")
file(GLOB CORE "{kit}/Core/*.cpp")
add_library(neo_compiler SHARED ${{NEW_GLSLANG}} ${{NEW_CROSS}} ${{CORE}})
target_include_directories(neo_compiler PUBLIC "{kit}/Core" PRIVATE
  "{kit}/ThirdParty/glslang" "{kit}/ThirdParty/SPIRV-Cross")
target_compile_options(neo_compiler PRIVATE -w)
add_executable(probe "{ROOT}/packages/neo_shader_kit/tools/neoshader_tool.cpp")
target_link_libraries(probe PRIVATE dolphin_glslang neo_compiler)
'''
    (project / 'CMakeLists.txt').write_text(cmake)
    build = args.evidence.resolve() / 'build'
    run(['cmake', '-S', project, '-B', build, '-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake', '--build', build, '-j', '3'])
    executable = build / 'probe'
    images = run(['otool', '-L', executable])
    (args.evidence / 'loaded-images.txt').write_text(images)
    assert images.index('libdolphin_glslang') < images.index('libneo_compiler'), images
    for name in ('libdolphin_glslang.dylib', 'libneo_compiler.dylib'):
        (args.evidence / (name + '.symbols.txt')).write_text(run(['nm', '-m', build / name]))
    outcomes = []
    for preset in PRESETS:
        command = [str(executable), 'slang', str(args.slang_shaders.resolve()), preset]
        result = subprocess.run(command, text=True, capture_output=True, timeout=90)
        slug = Path(preset).stem
        (args.evidence / f'{slug}.stdout.txt').write_text(result.stdout)
        (args.evidence / f'{slug}.stderr.txt').write_text(result.stderr)
        outcome = {'preset': preset, 'exit': result.returncode}
        if result.returncode == 0:
            outcome['compiled'] = json.loads(result.stdout)['ok']
        else:
            # LLDB runs the actual process anew and prints the faulting
            # instruction/stack instead of interpreting an exit code.
            trace = run(['lldb', '--batch', '-o', 'run', '-o', 'thread backtrace all',
                         '--', *command], timeout=120)
            (args.evidence / f'{slug}.backtrace.txt').write_text(trace)
            print(trace[-14000:], flush=True)
        print(json.dumps(outcome), flush=True)
        outcomes.append(outcome)
    (args.evidence / 'outcomes.json').write_text(json.dumps(outcomes, indent=2) + '\n')
    if not args.diagnose and any(o.get('compiled') is not True for o in outcomes):
        raise SystemExit('The kit cannot compile alongside the compiler loaded by Dolphin.')


if __name__ == '__main__':
    main()
