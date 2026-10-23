#!/usr/bin/env python3
"""Compile the real Swift host against a native ABI double and the iPhone SDK.

The double proves host lifetime/FFI behavior, never emulation or JIT readiness.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import os
import sys

root = Path(__file__).resolve().parents[1]
sources = sorted((root / 'packages/melonx_internal_bridge/ios/Classes').glob('*.swift'))
controller_sources = sorted((root / 'packages/melonx_internal_bridge/ios/Controller').rglob('*.swift'))
assert controller_sources, 'Materialize the pinned original controller first'
header = root / 'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionABI.h'
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
flutter_root = Path(os.environ['FLUTTER_ROOT'])
flutter = flutter_root / 'bin/cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64'
assert (flutter / 'Flutter.framework/Flutter').is_file(), flutter
jit_header = header.with_name('MeloNXJitBridgePlugin.h')
subprocess.run(['xcrun', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk,
                '-target', 'arm64-apple-ios18.0', '-F',str(flutter),
                '-import-objc-header',str(jit_header), '-module-name','melonx_internal_bridge',
                *map(str, [*sources,*controller_sources])], check=True)
subprocess.run(['xcrun','clang++','-fsyntax-only','-fobjc-arc','-std=c++20',
                '-target','arm64-apple-ios18.0','-isysroot',sdk,'-F',str(flutter),
                str(jit_header.with_suffix('.mm'))],check=True)
memory = root/'packages/melonx_internal_bridge/ios/Memory'
for source in [memory/'MLXRamDonor.m',memory/'Helper/MeloNXRamDonor.m']:
    subprocess.run(['xcrun','clang','-fsyntax-only','-fobjc-arc','-fmodules',
        '-target','arm64-apple-ios18.0','-isysroot',sdk,'-I',str(memory),str(source)],check=True)
if '--sdk-only' in sys.argv:
    unchanged = 'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift'
    assert subprocess.check_output(['git','show','303d9084db73b3016d29a5dca9bf439fa44ed7c7:'+unchanged],cwd=root) == (root/unchanged).read_bytes()
    inputs=[*sources,*controller_sources,header,jit_header,jit_header.with_suffix('.mm'),Path(__file__)]
    out=root/'dist/melonx-host/checks.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        inputs={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        iphoneSDKTypecheck=True,nativeABIDoubleReexecuted=False,unchangedABIDoubleRun=40031804127,gameplayTested=False),indent=2)+'\n')
    print('PASS complete iPhone SDK Swift/ObjC++ typecheck; unchanged session ABI fixtures not reexecuted.')
    raise SystemExit(0)
with tempfile.TemporaryDirectory(prefix='melonx-host-') as temporary:
    work = Path(temporary)
    (work / 'double.c').write_text(r'''#include "MeloNXSessionABI.h"
#include <stdatomic.h>
#include <string.h>
#include <unistd.h>
static _Atomic int state, stopping, failing;
static int64_t generation;
static char game[1024], locale[128];
static void *layer;
int32_t neostation_melonx_bootstrap_abi(void) { return 1; }
int32_t neostation_melonx_session_abi(void) {
#ifdef BAD_ABI
return 2;
#else
return 1;
#endif
}
int32_t neostation_melonx_initialize(const char *root) { return root && strstr(root,"MeloNX") ? 0 : 1; }
int32_t neostation_melonx_session_state(void) { return state; }
int32_t neostation_melonx_session_error(char *out, int32_t n) {
const char *s="échec natif témoin"; if(out && n>0) { strncpy(out,s,n-1); out[n-1]=0; } return (int32_t)strlen(s);
}
int64_t neostation_melonx_prepare(const char *path,const char *lang,int32_t w,int32_t h) {
if(state) return -1; if(!path || !lang || w!=1280 || h!=720) return -2;
strncpy(game,path,sizeof(game)-1); strncpy(locale,lang,sizeof(locale)-1); stopping=0; state=1; return ++generation;
}
int32_t neostation_melonx_run(int64_t id) {
if(id!=generation || state!=1 || !layer) return 2;
state=2; while(!stopping && !failing) usleep(1000);
usleep(40000); state=failing?4:0; layer=0; return failing?3:0;
}
int32_t neostation_melonx_stop(int64_t id) { if(id!=generation || !state || state==4) return 2; stopping=1; return 0; }
int32_t neostation_melonx_pause(int64_t id,int32_t paused) { return id==generation && state==2 ? 0:2; }
int32_t neostation_melonx_cancel_prepared(int64_t id) { if(id!=generation || state!=1)return 2;state=0;return 0; }
void set_native_window(void *p) { layer=p; }
int test_arguments(void) { return !strcmp(game,"/tmp/Jeu été.nro") && !strcmp(locale,"fr-FR"); }
const char *test_game(void) { return game; }
const char *test_locale(void) { return locale; }
void test_failure(int n) { failing=n; }
''')
    for variant, flags in [('good', []), ('bad', ['-DBAD_ABI'])]:
        subprocess.run(['xcrun', 'clang', '-dynamiclib', '-std=c11', '-I', str(header.parent),
                        *flags, str(work/'double.c'), '-o', str(work/(variant+'.dylib'))], check=True)
    (work/'missing.c').write_text('int neostation_melonx_bootstrap_abi(void) { return 1; }\n')
    subprocess.run(['xcrun','clang','-dynamiclib',str(work/'missing.c'),'-o',str(work/'missing.dylib')],check=True)
    (work/'main.swift').write_text(r'''import Foundation
import Darwin
let directory = URL(fileURLWithPath: CommandLine.arguments[1])
var cases = 0
func check(_ ok: Bool, line: Int = #line) { precondition(ok, "Host assertion at line \(line)"); cases += 1 }
func rejected(_ name: String) {
    do { _ = try MeloNXNativeSessionAPI(libraryURL: directory.appendingPathComponent(name)); fatalError("Accepted incompatible library") }
    catch { cases += 1 }
}
rejected("absent.dylib"); rejected("bad.dylib"); rejected("missing.dylib")
let url = directory.appendingPathComponent("good.dylib")
let api = try MeloNXNativeSessionAPI(libraryURL: url)
do { try api.initialize(root: URL(fileURLWithPath:"/tmp/other")); fatalError("Accepted invalid root") } catch { cases += 1 }
try api.initialize(root: URL(fileURLWithPath:"/tmp/MeloNX"))
let handle = dlopen(url.path, RTLD_NOW | RTLD_LOCAL)!
let arguments = unsafeBitCast(dlsym(handle,"test_arguments")!, to:(@convention(c) () -> Int32).self)
let gameArgument = unsafeBitCast(dlsym(handle,"test_game")!, to:(@convention(c) () -> UnsafePointer<CChar>?).self)
let localeArgument = unsafeBitCast(dlsym(handle,"test_locale")!, to:(@convention(c) () -> UnsafePointer<CChar>?).self)
let fail = unsafeBitCast(dlsym(handle,"test_failure")!, to:(@convention(c) (Int32) -> Void).self)
let host = MeloNXSessionHost(api:api)
check(!host.isSessionActive)
final class Surface: NSObject {}
func awaitResult(_ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !predicate() && Date() < deadline { RunLoop.main.run(until:Date().addingTimeInterval(0.002)) }
    precondition(predicate(), "Timed out")
}
do {
    try host.start(game:URL(fileURLWithPath:"/tmp/invalid.nro"),locale:"fr-FR",width:0,height:720,
        surface:Surface(),pointer:UnsafeMutableRawPointer(bitPattern:0x1234)!) { _ in fatalError("Rejected prepare completed") }
    fatalError("Accepted invalid preparation")
} catch MeloNXHostError.prepare(let status, let detail) {
    check(status == -2 && detail == "échec natif témoin")
    check(!host.isSessionActive)
}
var completed = 0
var surface: Surface? = Surface(); weak var weakSurface = surface
try host.start(game:URL(fileURLWithPath:"/tmp/Jeu été.nro"),locale:"fr-FR",width:1280,height:720,
    surface:surface!,pointer:UnsafeMutableRawPointer(bitPattern:0x1234)!) { result in
    if case .failure(let error) = result { fatalError(error.description) }; completed += 1
}
surface = nil
check(host.isSessionActive && weakSurface != nil)
awaitResult { api.state == 2 }
// Apple may decompose accented filesystem names. Compare the actual borrowed
// URL path semantically, including Unicode, rather than assume NFC C bytes.
check(String(cString:gameArgument()!) == URL(fileURLWithPath:"/tmp/Jeu été.nro").path)
check(String(cString:localeArgument()!) == "fr-FR")
check(host.setPaused(true)); check(host.setPaused(false))
do {
    try host.start(game:URL(fileURLWithPath:"/tmp/other.nro"),locale:"en",width:1280,height:720,
        surface:Surface(),pointer:UnsafeMutableRawPointer(bitPattern:1)!) { _ in fatalError("Duplicate completion") }
    fatalError("Accepted overlapping session")
} catch { cases += 1 }
check(host.requestStop() && host.isSessionActive && weakSurface != nil)
awaitResult { completed == 1 }
check(!host.isSessionActive && weakSurface == nil && api.state == 0 && !host.requestStop())
// Relaunch, then reject a delayed command carrying the first generation.
try host.start(game:URL(fileURLWithPath:"/tmp/Jeu été.nro"),locale:"fr-FR",width:1280,height:720,
    surface:Surface(),pointer:UnsafeMutableRawPointer(bitPattern:1)!) { _ in completed += 1 }
awaitResult { api.state == 2 }
check(api.stop(1) == 2 && api.state == 2 && host.isSessionActive)
check(host.requestStop()); awaitResult { completed == 2 }; check(!host.isSessionActive)
var reservedGeneration: Int64 = 0
var rejectedJit = false
try host.start(game:URL(fileURLWithPath:"/tmp/Jeu été.nro"),locale:"fr-FR",width:1280,height:720,
    surface:Surface(),pointer:UnsafeMutableRawPointer(bitPattern:1)!,
    prepared:{ reservedGeneration = $0 },beforeRun:{ false }) { outcome in
        if case .failure = outcome { rejectedJit = true }; completed += 1
    }
check(reservedGeneration > 2)
awaitResult { completed == 3 }
check(rejectedJit && !host.isSessionActive && api.state == 0)
// The actual error buffer crosses the C ABI with UTF-8 intact.
check(api.diagnostic == "échec natif témoin")
fail(1)
var failed = false
var poisoned: MeloNXSessionHost? = MeloNXSessionHost(api:api)
weak var weakPoisoned = poisoned
var failedSurface: Surface? = Surface(); weak var weakFailedSurface = failedSurface
try poisoned!.start(game:URL(fileURLWithPath:"/tmp/Jeu été.nro"),locale:"fr-FR",width:1280,height:720,
    surface:failedSurface!,pointer:UnsafeMutableRawPointer(bitPattern:1)!) { result in
    if case .failure(let error) = result { failed = error.description.contains("échec natif témoin") }
    completed += 1
}
failedSurface = nil
awaitResult { completed == 4 }
check(failed && poisoned!.isSessionActive && api.state == 4)
poisoned = nil
check(weakPoisoned != nil && weakFailedSurface != nil)
do {
    try weakPoisoned!.start(game:URL(fileURLWithPath:"/tmp/Jeu été.nro"),locale:"fr-FR",width:1280,height:720,
        surface:Surface(),pointer:UnsafeMutableRawPointer(bitPattern:1)!) { _ in fatalError() }
    fatalError("Reused quarantined native state")
} catch { cases += 1 }
print("Swift embedded session host: \(cases) cases passed.")
''')
    host = next(p for p in sources if p.name == 'MeloNXSessionHost.swift')
    executable = work/'host-checks'
    subprocess.run(['xcrun','swiftc','-swift-version','5',str(host),str(work/'main.swift'),'-o',str(executable)],check=True)
    result = subprocess.run([str(executable),str(work)],text=True,capture_output=True,timeout=30)
    print(result.stdout, flush=True)
    if result.returncode:
        print(result.stderr, flush=True)
        result.check_returncode()
receipt = dict(source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
               inputs={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sources,*controller_sources,header,jit_header,jit_header.with_suffix('.mm'),Path(__file__)]},
               iphoneSDKTypecheck=True, nativeABIDouble=True, gameplayTested=False, result=result.stdout.strip())
out=root/'dist/melonx-host/checks.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(receipt,indent=2)+'\n')
