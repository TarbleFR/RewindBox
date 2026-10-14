#!/usr/bin/env python3
"""Compile and link the neo_shader_kit pod for iPhone (macOS).

    test/neo_shader_kit_ios_build.py [--jobs N]

The delivery compiles packages/neo_shader_kit/ios through its podspec in the
cold Xcode build; the macOS tests compile the kit for macOS only. This
compiles the files the podspec lists (source_files: the Objective-C API, the
C++ core, the vendored glslang and SPIRV-Cross) for arm64 iPhone with the
podspec's settings (C++17 with libc++ and exceptions, ARC, the Core /
glslang / SPIRV-Cross search paths), links them into one dynamic library
with the podspec's frameworks and lists what stays undefined. A symbol of
the kit (an Objective-C class or constant whose name starts with "Neo", or
a C++ symbol of the neoshader namespace) left undefined is a declaration
without a definition, which would otherwise only fail the delivery link.
The Flutter plugin class compiles against the declaration stub of
test/libretro_host/stubs; Flutter and system symbols stay undefined on
purpose (the application resolves them).

compile_kit() is shared with test/libretro_simulator_probe.py, which links
the kit built for the iOS Simulator with the libretro bridge.
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'packages/neo_shader_kit/ios'
PODSPEC = KIT / 'neo_shader_kit.podspec'
FLUTTER_STUB = ROOT / 'test/libretro_host/stubs'
PLUGIN = 'NeoShaderKitPlugin.m'
IPHONE_TARGET = 'arm64-apple-ios17.4'
# Third-party code compiles without its own warnings, as in the host build.
THIRD_PARTY = KIT / 'ThirdParty'
KIT_SYMBOL = re.compile(r'(?:^_Neo|OBJC_(?:CLASS|METACLASS)_\$_Neo|neoshader)')


def podspec_list(field):
    text = PODSPEC.read_text(encoding='utf-8')
    match = re.search(rf"\b{field}\s*=\s*((?:'[^']*'\s*,?\s*)+)", text)
    if match is None:
        raise SystemExit(f'neo_shader_kit.podspec declares no {field}')
    return re.findall(r"'([^']*)'", match.group(1))


def expand(pattern):
    """A podspec glob ('Classes/**/*.{h,m,mm}') as files of the pod."""
    braces = re.search(r'\{([^}]*)\}', pattern)
    patterns = ([pattern[:braces.start()] + choice + pattern[braces.end():] for choice in braces.group(1).split(',')]
                if braces else [pattern])
    files = set()
    for item in patterns:
        files.update(path for path in KIT.glob(item) if path.is_file())
    return files


def kit_sources(plugin=True):
    """The compiled files of the podspec's source_files, in a stable order."""
    files = set()
    for pattern in podspec_list('source_files'):
        files.update(path for path in expand(pattern) if path.suffix in ('.m', '.mm', '.cpp'))
    if not plugin:
        files = {path for path in files if path.name != PLUGIN}
    return sorted(files)


def podspec_frameworks():
    return podspec_list('frameworks')


def podspec_export_flags():
    match = re.search(r"'EXPORTED_SYMBOLS_FILE'\s*=>\s*'\$\{PODS_TARGET_SRCROOT\}/([^']+)'", PODSPEC.read_text())
    if match is None:
        raise SystemExit('The compiler framework must declare its private symbol boundary.')
    return ['-Wl,-exported_symbols_list,' + str(KIT / match.group(1))]


def compile_kit(sdk_name, target, sdk, directory, jobs=None, plugin=True, optimization='-O0'):
    """Objects of the kit for one SDK. Prints each failure and raises on any."""
    directory.mkdir(parents=True, exist_ok=True)
    includes = [KIT / 'Classes', KIT / 'Classes/Public', KIT / 'Core', KIT / 'ThirdParty/glslang',
                KIT / 'ThirdParty/SPIRV-Cross', FLUTTER_STUB]
    base = ['xcrun', '--sdk', sdk_name, 'clang', '-target', target, '-isysroot', sdk, optimization]
    for include in includes:
        base += ['-I', str(include)]
    sources = kit_sources(plugin)

    def build(index_source):
        index, source = index_source
        output = directory / f'kit_{index:03d}_{source.stem}.o'
        arguments = list(base)
        if source.suffix in ('.cpp', '.mm'):
            arguments += ['-std=c++17', '-stdlib=libc++', '-fcxx-exceptions', '-fexceptions']
        if source.suffix in ('.m', '.mm'):
            arguments += ['-fobjc-arc']
        if source.suffix == '.m':
            arguments += ['-fmodules']
        arguments += ['-w'] if THIRD_PARTY in source.parents else ['-Wall', '-Wno-unused-parameter']
        result = subprocess.run(arguments + ['-c', str(source), '-o', str(output)], capture_output=True, text=True)
        return source, output, result

    objects, failed = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs or os.cpu_count() or 2) as pool:
        for source, output, result in pool.map(build, enumerate(sources)):
            if result.returncode != 0 or result.stderr.strip():
                status = 'ok' if result.returncode == 0 else 'FAILED'
                print(f'{status:6} {source.relative_to(ROOT)}\n{result.stderr}', flush=True)
            if result.returncode != 0:
                failed.append(source.name)
            objects.append(output)
    if failed:
        raise SystemExit(f'neo_shader_kit does not compile for {target}: ' + ', '.join(failed))
    print(f'compiled {len(sources)} neo_shader_kit sources for {target}', flush=True)
    return objects


def undefined_symbols(library):
    result = subprocess.run(['xcrun', 'nm', '-u', str(library)], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, flush=True)
        raise SystemExit('nm -u failed on the linked neo_shader_kit')
    return {line.split()[-1] for line in result.stdout.splitlines() if line.strip() and not line.endswith(':')}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--jobs', type=int)
    arguments = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('The iPhone build of neo_shader_kit runs on macOS.')
    sdk = subprocess.run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], check=True, capture_output=True,
                         text=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='neo-shader-kit-ios-') as temporary:
        directory = Path(temporary)
        objects = compile_kit('iphoneos', IPHONE_TARGET, sdk, directory, arguments.jobs)
        library = directory / 'libneo_shader_kit.dylib'
        link = ['xcrun', '--sdk', 'iphoneos', 'clang++', '-dynamiclib', '-target', IPHONE_TARGET, '-isysroot', sdk,
                '-fobjc-arc', '-stdlib=libc++', *(str(item) for item in objects)]
        for framework in podspec_frameworks():
            link += ['-framework', framework]
        link += [*podspec_export_flags(), '-Wl,-undefined,dynamic_lookup', '-o', str(library)]
        result = subprocess.run(link, capture_output=True, text=True)
        if result.stdout.strip() or result.stderr.strip():
            print(result.stdout + result.stderr, flush=True)
        if result.returncode != 0:
            raise SystemExit('iPhone link of neo_shader_kit failed (see the linker output above)')
        undefined = undefined_symbols(library)
        exported = subprocess.run(['xcrun', 'nm', '-gU', str(library)], check=True, capture_output=True, text=True).stdout
        if re.search(r'glslang|spirv_cross|__ZN3spv|_Sh(?:Initialize|Compile|Construct)', exported):
            raise SystemExit('The iPhone framework still exposes a shader compiler implementation.')
        if '_OBJC_CLASS_$_NeoSlangProgram' not in exported or '_NeoShaderFormatSlang' not in exported:
            raise SystemExit('The framework export boundary hid its public Objective-C API.')
        print('iPhone framework exports its public API and no glslang/SPIRV-Cross implementation', flush=True)
    missing = sorted(name for name in undefined if KIT_SYMBOL.search(name))
    if missing:
        print('Kit symbols used but defined by no source:', flush=True)
        for name in missing:
            print('  ' + name, flush=True)
        raise SystemExit(f'{len(missing)} neo_shader_kit symbol(s) declared and used but never defined')
    print(f'PASS: neo_shader_kit compiles and links for iPhone ({len(objects)} objects; '
          f'{len(undefined)} Flutter and system symbols left to the application)', flush=True)


if __name__ == '__main__':
    main()
