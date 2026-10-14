#!/usr/bin/env python3
"""Dolphin post-processing choice and page (Build 450), on macOS.

1. test/dolphin_shader_store_test.mm runs DOLShaderStore.h on real files:
   names, choices for every game and per game, what reaches GFX.ini and
   Dolphin.ini before the core initializes (explicit empty value, options
   in Dolphin's formats, stale values removed), imports and removal, a
   damaged selection file, and the reversible display trial editing the
   same GFX.ini.
2. The page and the files the change touches compile for iPhone with the
   bridge's dependencies staged as the pod build sees them (<neo_shader_kit/>
   and <external_display/> public headers only): DOLShaderSettings.mm,
   DolphinFramePacing.mm.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
sys.path.insert(0, str(ROOT / 'test'))
from libretro_ios_syntax_test import stage_dependency_headers  # noqa: E402

IPHONE_TARGET = 'arm64-apple-ios17.4'
PAGE_SOURCES = ('DOLShaderSettings.mm', 'DolphinFramePacing.mm', 'DolphinSessionMenu.mm')


def source_contracts():
    """Host routing contracts only; these do not execute the Dolphin engine."""
    plugin=(CLASSES/'DolphinInternalBridgePlugin.mm').read_text()
    header=(CLASSES/'DolphinSessionMenu.h').read_text()
    menu=(CLASSES/'DolphinSessionMenu.mm').read_text()
    # The common GameCube/Wii launch writes the effect to the same user/Sys
    # directories handed to the retained core, before it reads configuration.
    launch=plugin[plugin.index('NSString* gamePath = [arguments[@"gamePath"]'):]
    assert '![system isEqualToString:@"gc"] && ![system isEqualToString:@"wii"]' in launch
    staged=launch.index('DOLApplyShaderSelection(userDirectory,systemDirectory,self.activeDisplayGameId,&stagedShader)')
    initialized=launch.index('neostation_dolphin_initialize(userDirectory.fileSystemRepresentation,')
    assert staged<initialized
    assert 'systemDirectory.fileSystemRepresentation' in launch[initialized:initialized+230]
    assert 'self.activeSystemDirectory = systemDirectory;' in launch
    assert 'self.activeUserDirectory = userDirectory;' in launch
    assert 'menu.openShaderSettings = ^{' in plugin
    direct=plugin[plugin.index('menu.openShaderSettings = ^{'):plugin.index('menu.openTextureSettings = ^{')]
    assert 'owner.framePacing.shaderPage()' in direct, 'the direct row must use the existing page factory'
    assert '@property(nonatomic, copy, nullable) dispatch_block_t openShaderSettings;' in header
    assert 'child.openShaderSettings = self.openShaderSettings;' in menu
    assert 'dolphinPostProcessingFromMenu' in menu
    assert 'DOLShaderText(@"nextLaunch",locale)' in menu
    print('PASS Dolphin shader host wiring: shared GameCube/Wii launch, same paths, staging before initialize, existing page',flush=True)


def run(arguments, **options):
    print('+', ' '.join(str(argument) for argument in arguments), flush=True)
    return subprocess.run([str(argument) for argument in arguments], **options)


def main():
    arguments=argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--reproduce-before',help='Git revision of DOLShaderStore.h before the staging fix.')
    arguments.add_argument('--source-only',action='store_true',help='Check host wiring without compiling or executing the engine.')
    options=arguments.parse_args()
    source_contracts()
    if options.source_only:
        return
    if sys.platform != 'darwin' or shutil.which('xcrun') is None:
        raise SystemExit('The Dolphin shader store and page checks run on macOS.')
    with tempfile.TemporaryDirectory(prefix='dolphin-shaders-') as temporary:
        temporary = Path(temporary)
        binary = temporary / 'dolphin-shader-store-tests'
        if options.reproduce_before:
            prior=temporary/'before'
            prior.mkdir()
            header='packages/dolphin_internal_bridge/ios/Classes/DOLShaderStore.h'
            (prior/'DOLShaderStore.h').write_bytes(subprocess.check_output(
                ['git','show',options.reproduce_before+':'+header],cwd=ROOT))
            before_binary=temporary/'dolphin-shader-store-before'
            run(['xcrun','clang++','-std=c++20','-x','objective-c++','-fobjc-arc','-Wall','-Wno-unused-function',
                 '-I',prior,'-I',CLASSES,ROOT/'test/dolphin_shader_store_test.mm',
                 '-framework','Foundation','-o',before_binary],check=True)
            before=run([before_binary,'--stage-failure-only'],capture_output=True,text=True)
            print(before.stdout+before.stderr,flush=True)
            assert before.returncode==1 and 'failed staging preserves the previous shader selection' in before.stderr, \
                'The pre-fix source must reproduce the partial shader selection write'
        run(['xcrun', 'clang++', '-std=c++20', '-x', 'objective-c++', '-fobjc-arc', '-Wall', '-Wno-unused-function',
             '-I', CLASSES, ROOT / 'test/dolphin_shader_store_test.mm', '-framework', 'Foundation', '-o', binary],
            check=True)
        result = run([binary])
        if result.returncode != 0:
            raise SystemExit('Dolphin shader store behaviour failed')

        sdk = subprocess.run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], check=True, capture_output=True,
                             text=True).stdout.strip()
        include = stage_dependency_headers(temporary)
        failed = []
        for name in PAGE_SOURCES:
            result = run(['xcrun', '--sdk', 'iphoneos', 'clang++', '-target', IPHONE_TARGET, '-isysroot', sdk,
                          '-std=c++20', '-fobjc-arc', '-fmodules', '-fcxx-modules', '-fsyntax-only', '-Wall',
                          '-Wno-unused-function', '-I', CLASSES, '-I', include, CLASSES / name],
                         capture_output=True, text=True)
            print(f'{"ok" if result.returncode == 0 else "FAILED":6} {name}', flush=True)
            if result.stderr.strip():
                print(result.stderr, flush=True)
            if result.returncode != 0:
                failed.append(name)
        if failed:
            raise SystemExit('iPhone compilation failed: ' + ', '.join(failed))
    print('PASS: Dolphin post-processing store behaviour and page iPhone compilation', flush=True)


if __name__ == '__main__':
    main()
