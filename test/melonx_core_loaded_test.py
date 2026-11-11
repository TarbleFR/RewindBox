#!/usr/bin/env python3
"""The "MeloNXCore has begun loading in this process" flag of the bridge (MeloNXCoreLoaded.{h,m}) and its use.

Static (any host): the plugin refuses to load MeloNXCore once another NativeAOT engine says it has begun loading
(rb_s2arm_engine_loaded through dlsym, absent meaning no), then marks the process, then constructs the runtime, which is
the only place MeloNXCore is opened from; the S2Arm diagnostic hook of the JIT transaction is gone.
Executed (macOS; elsewhere skipped): the two functions compiled as in the pod and linked into a program that reads them
through dlsym(RTLD_DEFAULT): 0 before the mark, 1 after it and after a second mark.
"""
from pathlib import Path
import json, platform, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
sys.dont_write_bytecode = True
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


plugin = (CLASSES / 'MeloNXInternalBridgePlugin.swift').read_text()
source = (CLASSES / 'MeloNXCoreLoaded.m').read_text()
header = (CLASSES / 'MeloNXCoreLoaded.h').read_text()
ensure = plugin[plugin.index('private func ensureRuntime() throws -> MeloNXRuntimeAPI {'):plugin.index('public func handle(_ call: FlutterMethodCall')]
check(ensure.index('dlsym(UnsafeMutableRawPointer(bitPattern:-2), "rb_s2arm_engine_loaded")') < ensure.index('throw MeloNXHostError.load("A Switch 2 game already ran')
      < ensure.index('rb_melonx_core_mark_loading()') < ensure.index('runtime = try MeloNXRuntimeAPI(library:'),
      'another engine is asked first, then the process is marked, then MeloNXCore is loaded')
check(plugin.count('MeloNXRuntimeAPI(library:') == 1 and plugin.count('rb_melonx_core_mark_loading()') == 1 and
      all('MeloNXRuntimeAPI(library:' not in path.read_text() for path in CLASSES.glob('*.swift') if path.name != 'MeloNXInternalBridgePlugin.swift'),
      'the runtime is constructed in one place only, after the mark')
check('static _Atomic int gLoading;' in source and source.count('__attribute__((visibility("default"), used))') == 1 and
      'MELONX_CORE_LOADED_EXPORT int rb_melonx_core_loaded(void) { return atomic_load(&gLoading); }' in source and
      'MELONX_CORE_LOADED_EXPORT void rb_melonx_core_mark_loading(void) { atomic_store(&gLoading, 1); }' in source and
      'int rb_melonx_core_loaded(void);' in header and 'void rb_melonx_core_mark_loading(void);' in header,
      'an atomic flag, set only, behind two exported functions')
check('#import "MeloNXCoreLoaded.h"' in (CLASSES / 'MeloNXJitBridgePlugin.h').read_text() and
      not (CLASSES / 'MeloNXS2ArmProbeHook.m').exists() and not (CLASSES / 'MeloNXS2ArmProbeHook.h').exists() and
      'S2ArmProbe' not in plugin and 's2armProbe' not in plugin, 'the flag is in the plugin\'s header; the S2Arm diagnostic hook is gone')

if platform.system() != 'Darwin':
    print(json.dumps(dict(result='passed', checks=checks, staticOnly=True)))
    raise SystemExit(0)
with tempfile.TemporaryDirectory(prefix='melonx-core-loaded-') as directory:
    work = Path(directory)
    (work / 'main.c').write_text(r'''#include <dlfcn.h>
#include <stdio.h>
int main(void) {
    int (*loaded)(void) = (int (*)(void))dlsym(RTLD_DEFAULT, "rb_melonx_core_loaded");
    void (*mark)(void) = (void (*)(void))dlsym(RTLD_DEFAULT, "rb_melonx_core_mark_loading");
    void *other = dlsym(RTLD_DEFAULT, "rb_s2arm_engine_loaded");
    if (!loaded || !mark) { printf("missing\n"); return 2; }
    int before = loaded(); mark(); int after = loaded(); mark(); int again = loaded();
    printf("%d %d %d %s\n", before, after, again, other ? "other" : "noOther");
    return 0;
}
''')
    subprocess.run(['xcrun', 'clang', '-Wall', '-Wextra', '-Werror', '-Os', '-fvisibility=hidden', '-dynamiclib', str(CLASSES / 'MeloNXCoreLoaded.m'),
                    '-Wl,-dead_strip', '-o', str(work / 'libbridge.dylib')], check=True)
    subprocess.run(['xcrun', 'clang', str(work / 'main.c'), str(work / 'libbridge.dylib'), '-o', str(work / 'main')], check=True)
    run = subprocess.run([str(work / 'main')], capture_output=True, text=True, timeout=60)
    check(run.returncode == 0 and run.stdout.strip() == '0 1 1 noOther', 'through dlsym: 0, then 1 after the mark and after another: ' + run.stdout + run.stderr)
print(json.dumps(dict(result='passed', checks=checks, staticOnly=False)))
