#!/usr/bin/env python3
"""Compile the real Swift host against a native ABI double and the iPhone SDK.

The double proves host lifetime/FFI behavior, never emulation or JIT readiness.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
sources = sorted((root / 'packages/melonx_internal_bridge/ios/Classes').glob('*.swift'))
header = root / 'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionABI.h'
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
subprocess.run(['xcrun', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk,
                '-target', 'arm64-apple-ios17.4', *map(str, sources)], check=True)
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
let fail = unsafeBitCast(dlsym(handle,"test_failure")!, to:(@convention(c) (Int32) -> Void).self)
let host = MeloNXSessionHost(api:api)
check(!host.isSessionActive)
final class Surface: NSObject {}
func awaitResult(_ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !predicate() && Date() < deadline { RunLoop.main.run(until:Date().addingTimeInterval(0.002)) }
    precondition(predicate(), "Timed out")
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
check(arguments() == 1 && host.setPaused(true) && host.setPaused(false))
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
// The actual error buffer crosses the C ABI with UTF-8 intact.
check(api.diagnostic == "échec natif témoin")
fail(1)
var failed = false
try host.start(game:URL(fileURLWithPath:"/tmp/Jeu été.nro"),locale:"fr-FR",width:1280,height:720,
    surface:Surface(),pointer:UnsafeMutableRawPointer(bitPattern:1)!) { result in
    if case .failure(let error) = result { failed = error.description.contains("échec natif témoin") }
    completed += 1
}
awaitResult { completed == 3 }
check(failed && !host.isSessionActive && api.state == 4)
do {
    try host.start(game:URL(fileURLWithPath:"/tmp/Jeu été.nro"),locale:"fr-FR",width:1280,height:720,
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
               inputs={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sources,header,Path(__file__)]},
               iphoneSDKTypecheck=True, nativeABIDouble=True, gameplayTested=False, result=result.stdout.strip())
out=root/'dist/melonx-host/checks.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(receipt,indent=2)+'\n')
