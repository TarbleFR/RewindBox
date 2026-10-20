"""Rebuild only PPSSPP's pinned source with the managed Darwin allocator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'build-utils/libretro'))
import build_cores as package


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--work', required=True)
    a = p.parse_args()
    base, output, work = (Path(x).resolve() for x in (a.base, a.output, a.work))
    work.mkdir(parents=True, exist_ok=True)
    pin = json.loads((ROOT / 'native/ppsspp/source.json').read_text())
    identity = json.loads((base / 'identity.json').read_text())
    assert identity['host_commit'] == pin['baseHostCommit']
    assert len(identity['cores']) == 35
    for name, sha in identity['files'].items():
        assert digest(base / name) == sha, name
    source = work / 'source'
    run(['git', 'init', source])
    run(['git', 'remote', 'add', 'origin', pin['upstream']], cwd=source)
    run(['git', 'fetch', '--depth=1', 'origin', pin['revision']], cwd=source)
    run(['git', 'checkout', '--detach', 'FETCH_HEAD'], cwd=source)
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip() == pin['revision']
    run(['git', 'submodule', 'update', '--init', '--recursive', '--depth=1',
         'ext/armips', 'ext/glslang', 'ext/SPIRV-Cross', 'ext/rapidjson', 'ext/cpu_features',
         'ext/lua', 'ext/freetype', 'ext/OpenXR-SDK'], cwd=source)
    patch = ROOT / 'native/ppsspp/managed-memory.patch'
    header = ROOT / 'packages/libretro_internal_bridge/ios/Classes/NeoStationPSPMemory.h'
    assert digest(patch) == pin['patchSHA256']
    assert digest(header) == pin['abiHeaderSHA256']
    for name, sha in pin['originalFilesSHA256'].items():
        assert digest(source / name) == sha, name
    run(['git', 'apply', '--check', patch], cwd=source)
    run(['git', 'apply', patch], cwd=source)
    shutil.copy2(header, source / 'Common/NeoStationPSPMemory.h')
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    clang = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--find', 'clang'], text=True).strip()
    clangxx = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--find', 'clang++'], text=True).strip()
    name = 'ppsspp_libretro'
    install = '@rpath/' + name + '.framework/' + name
    target = '-target arm64-apple-ios18.0 -isysroot ' + sdk
    # Command-line assignments override obsolete ARMv7 flags in the upstream
    # ios recipe; no source, feature or emulator option is disabled.
    ffmpeg = '-G "Unix Makefiles" -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=' + sdk
    ffmpeg += ' -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=18.0'
    ffmpeg += ' -DCMAKE_C_COMPILER=' + clang + ' -DCMAKE_CXX_COMPILER=' + clangxx
    # Upstream matches generic "arm64" before "ios". Select ios explicitly;
    # CC/CXX/target flags below select arm64 without taking its Linux branch.
    command = ['make', '-C', source / 'libretro', '-j3', '-k', 'platform=ios', 'TARGET_ARCH=arm64',
               'DEBUG=0', 'IOSSDK=' + sdk, 'GIT_VERSION=1bd28b0-neostation-memory1',
               'CC=' + clang, 'CXX=' + clangxx,
               'PLATCFLAGS=' + target + ' -DHAVE_POSIX_MEMALIGN -DMOBILE_DEVICE -DLUA_USE_IOS'
               ' -UHAVE_STRONG_GETAUXVAL -DHAVE_DLFCN_H',
               'CPUFLAGS=-DARM64', 'FFMPEG_CMAKE_TOOLCHAIN=' + ffmpeg,
               # Make exports command-line flags. FFmpeg's configure probes
               # must not inherit the core's dylib link or not-yet-built libs.
               'FFMPEG_CMAKE_ENV=env -u LDFLAGS -u CFLAGS -u CXXFLAGS -u CPPFLAGS -u MAKEFLAGS -u MFLAGS',
               'LDFLAGS=-dynamiclib ' + target + ' -Wl,-install_name,' + install + ' -lobjc $(FFMPEGLDFLAGS)']
    with (work / 'compile.log').open('w') as log:
        try:
            run(command, stdout=log, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            diagnostic = (work / 'compile.log').read_text()
            errors = [line for line in diagnostic.splitlines() if 'error:' in line or 'Error ' in line or 'Undefined symbols' in line]
            print('\n'.join(errors[-120:]), flush=True)
            print(diagnostic[-18000:], flush=True)
            raise
    binary = source / 'libretro/ppsspp_libretro_ios.dylib'
    info = package.macho(binary.read_bytes())
    assert info['platform'] == 2 and info['minimumOS'] == '18.0.0', info
    package.check_dependencies(name, info)
    assert set(package.REQUIRED_EXPORTS) | {'_neostation_ppsspp_set_memory_callbacks'} <= package.exported_symbols(binary)
    shutil.copytree(base, output)
    framework = output / ('Frameworks/' + name + '.framework')
    shutil.copy2(binary, framework / name)
    (framework / 'Info.plist').write_bytes(package.framework_plist('com.neogamelab.neostation.libretro.ppsspp', name, '18.0'))
    core = next(x for x in identity['cores'] if x['id'] == 'ppsspp')
    original = dict(core)
    core.update(sha256=digest(binary), bytes=binary.stat().st_size, minimumOS='18.0',
                installName=install, dependencies=info['dependencies'], source=pin['upstream'] + '/tree/' + pin['revision'],
                sourceRevision=pin['revision'], sourcePatchSha256=pin['patchSHA256'],
                archive='source-1bd28b0-neostation-memory1', url=pin['upstream'] + '/tree/' + pin['revision'])
    core.pop('archiveSha256', None)
    notices = output / 'Libretro-Licenses/LIBRETRO_CORES.txt'
    notices.write_text(notices.read_text() + '\nPPSSPP only: NeoStation managed Darwin backing arena and memory-view ownership.\n'
                      + core['source'] + ' (GPL-2.0-or-later); modification sources: TarbleFR/neostation-ios native/ppsspp/managed-memory.patch and packages/libretro_internal_bridge/ios/Classes/NeoStationPSPMemory.h.\n')
    identity['host_commit'] = os.environ['GITHUB_SHA']
    identity['ppssppManagedMemory'] = {'source': pin, 'originalCore': original,
                                     'compiledCoreSHA256': digest(binary), 'abi': 1,
                                     'xcode': subprocess.check_output(['xcodebuild', '-version'], text=True).strip()}
    allowed = {f'Frameworks/{name}.framework/{name}', f'Frameworks/{name}.framework/Info.plist',
               'Libretro-Licenses/LIBRETRO_CORES.txt'}
    for file, sha in identity['files'].items():
        if file not in allowed:
            assert digest(output / file) == sha, file
    identity['files'] = {f.relative_to(output).as_posix(): digest(f) for f in output.rglob('*')
                         if f.is_file() and f.name != 'identity.json'}
    (output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print('Compiled one corrected PPSSPP; 34 other cores and system assets unchanged.', flush=True)


if __name__ == '__main__':
    main()
