#!/usr/bin/env python3
"""Compile and link every libretro bridge source and rcheevos file for iPhone (macOS).

Uses the iPhoneOS SDK with the podspec's flags, so a broken API use is caught
before the full delivery build. The Flutter plugin header is replaced by a
declaration stub; everything else is the real SDK.

The bridge depends on the external_display pod (NeoExternalRenderHost, Build
447) and on the neo_shader_kit pod (slang shaders, Build 450), and imports
their headers as <pod/Name.h>. The generated host links every pod as a
framework (use_frameworks!), where only the headers a pod publishes (its
podspec's public_header_files) resolve that way: the same headers, and only
those, are staged under a folder named after each pod and added to the
search path, so a bridge import of an unpublished header fails here rather
than in the cold Xcode build.

The objects are then linked into one dynamic library with the same SDK and
`nm -u` lists what it still needs from elsewhere. A symbol of the bridge
itself (a name containing "Libretro": its C functions and constants, and its
classes through OBJC_CLASS_$_Libretro... / OBJC_METACLASS_$_Libretro...) left
undefined means a declaration without a definition, which would otherwise
only fail the cold Xcode link of the delivery. Flutter symbols (declared by
the stub) and system symbols stay undefined on purpose: they are resolved by
the real application.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/libretro_internal_bridge/ios'
# Pods the bridge depends on: name -> folder of its podspec.
DEPENDENCY_PODS = {
    'external_display': ROOT / 'packages/external_display/ios',
    'neo_shader_kit': ROOT / 'packages/neo_shader_kit/ios',
}
TARGET = 'arm64-apple-ios17.4'
DEFINES = ('GLES_SILENCE_DEPRECATION=1', 'COREVIDEO_SILENCE_GL_DEPRECATION=1', 'VK_USE_PLATFORM_METAL_EXT=1',
           'VK_NO_PROTOTYPES=1', 'RC_CLIENT_SUPPORTS_HASH=1')
# The podspec's frameworks, plus ImageIO and CoreGraphics used by the skin
# code. Modules imported by the Objective-C sources are also auto-linked.
FRAMEWORKS = ('UIKit', 'Foundation', 'Metal', 'QuartzCore', 'AVFoundation', 'GameController', 'OpenGLES',
              'CoreVideo', 'Security', 'ImageIO', 'CoreGraphics')
BRIDGE_SYMBOL = 'Libretro'


def object_name(source):
    """One object per source, distinct even for equal file names in different folders."""
    return '_'.join(source.relative_to(BRIDGE).with_suffix('.o').parts)


def public_headers(pod, folder):
    """The headers a pod publishes (public_header_files of its podspec,
    globs expanded): the only ones another pod can import as <pod/Name.h>
    from the framework CocoaPods builds."""
    podspec = (folder / f'{pod}.podspec').read_text(encoding='utf-8')
    match = re.search(r"public_header_files\s*=\s*((?:'[^']*'\s*,?\s*)+)", podspec)
    if match is None:
        raise SystemExit(f'{pod}.podspec declares no public_header_files')
    headers = []
    for pattern in re.findall(r"'([^']*)'", match.group(1)):
        found = sorted(folder.glob(pattern)) if any(character in pattern for character in '*?[') else [folder / pattern]
        if not found or not all(header.is_file() for header in found):
            raise SystemExit(f'{pod}.podspec publishes missing headers: {pattern}')
        headers += found
    return headers


def external_display_public_headers():
    """The headers the external_display pod publishes (kept for the Dolphin
    harnesses that import this module)."""
    return public_headers('external_display', DEPENDENCY_PODS['external_display'])


def stage_external_display(directory):
    """A search path where <external_display/Name.h> resolves as a pod that
    depends on external_display sees it (used by the Dolphin harnesses)."""
    include = directory / 'include'
    staged = include / 'external_display'
    staged.mkdir(parents=True)
    headers = external_display_public_headers()
    for header in headers:
        shutil.copyfile(header, staged / header.name)
    print(f'Staged {len(headers)} public external_display header(s) as <external_display/...>: '
          + ', '.join(header.name for header in headers), flush=True)
    return include


def stage_dependency_headers(directory):
    """A search path where <pod/Name.h> resolves exactly as the bridge sees
    the pods it depends on: a folder named after each pod holding copies of
    its public headers and nothing else."""
    include = directory / 'include'
    for pod, folder in DEPENDENCY_PODS.items():
        staged = include / pod
        staged.mkdir(parents=True)
        headers = public_headers(pod, folder)
        for header in headers:
            shutil.copyfile(header, staged / header.name)
        print(f'Staged {len(headers)} public {pod} header(s) as <{pod}/...>: '
              + ', '.join(header.name for header in headers), flush=True)
    return include


def compile_sources(sdk, sources, directory, include):
    includes = [
        BRIDGE / 'Classes', BRIDGE / 'ThirdParty/include', BRIDGE / 'ThirdParty/include/libretro',
        BRIDGE / 'ThirdParty/rcheevos/include', BRIDGE / 'ThirdParty/rcheevos/src',
        ROOT / 'test/libretro_host/stubs', include,
    ]
    base = ['xcrun', '--sdk', 'iphoneos', 'clang', '-target', TARGET, '-isysroot', sdk,
            '-Wall', '-Wno-unused-function']
    for include in includes:
        base += ['-I', str(include)]
    for define in DEFINES:
        base += ['-D', define]
    objects = []
    failed = []
    for source in sources:
        output = directory / object_name(source)
        arguments = list(base)
        if source.suffix == '.m':
            arguments += ['-fobjc-arc', '-fmodules']
        arguments += ['-c', str(source), '-o', str(output)]
        result = subprocess.run(arguments, capture_output=True, text=True)
        status = 'ok' if result.returncode == 0 else 'FAILED'
        print(f'{status:6} {source.relative_to(ROOT)}', flush=True)
        if result.stderr.strip():
            print(result.stderr, flush=True)
        if result.returncode != 0:
            failed.append(source.name)
        objects.append(output)
    return objects, failed


def link(sdk, objects, output):
    arguments = ['xcrun', '--sdk', 'iphoneos', 'clang', '-dynamiclib', '-target', TARGET, '-isysroot', sdk,
                 '-fobjc-arc', *(str(item) for item in objects)]
    for framework in FRAMEWORKS:
        arguments += ['-framework', framework]
    arguments += ['-lz', '-Wl,-undefined,dynamic_lookup', '-o', str(output)]
    print('+ clang -dynamiclib ' + ' '.join(f'-framework {name}' for name in FRAMEWORKS)
          + f' -lz -Wl,-undefined,dynamic_lookup ({len(objects)} objects)', flush=True)
    result = subprocess.run(arguments, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout, flush=True)
    if result.stderr.strip():
        print(result.stderr, flush=True)
    if result.returncode != 0:
        raise SystemExit('iPhone link of the libretro bridge failed (see the linker output above)')


def undefined_symbols(library):
    result = subprocess.run(['xcrun', 'nm', '-u', str(library)], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, flush=True)
        raise SystemExit('nm -u failed on the linked libretro bridge')
    names = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and not line.endswith(':'):
            names.add(line.split()[-1])
    return names


def main():
    if sys.platform != 'darwin':
        raise SystemExit('The iPhone syntax check runs on macOS.')
    sdk = subprocess.run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], check=True,
                         capture_output=True, text=True).stdout.strip()
    sources = sorted((BRIDGE / 'Classes').glob('*.m')) + sorted((BRIDGE / 'ThirdParty/rcheevos/src').rglob('*.c'))
    with tempfile.TemporaryDirectory(prefix='libretro-ios-') as temporary:
        directory = Path(temporary)
        include = stage_dependency_headers(directory)
        objects, failed = compile_sources(sdk, sources, directory, include)
        if failed:
            raise SystemExit('iPhone compilation failed: ' + ', '.join(failed))
        print(f'All {len(sources)} libretro bridge sources compile for iPhone', flush=True)
        library = directory / 'liblibretro_internal_bridge.dylib'
        link(sdk, objects, library)
        undefined = undefined_symbols(library)
    missing = sorted(name for name in undefined if BRIDGE_SYMBOL in name)
    if missing:
        print('Bridge symbols used but defined by no source:', flush=True)
        for name in missing:
            print('  ' + name, flush=True)
        raise SystemExit(f'{len(missing)} libretro bridge symbol(s) declared and used but never defined')
    print(f'Linked {len(objects)} objects for iPhone: no bridge symbol left undefined '
          f'({len(undefined)} Flutter and system symbols left to the application)')


if __name__ == '__main__':
    main()
