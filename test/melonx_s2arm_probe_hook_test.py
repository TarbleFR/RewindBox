#!/usr/bin/env python3
"""The S2Arm diagnostic hook of the MeloNX JIT transaction (MeloNXS2ArmProbeHook.m), on macOS.

Static (any host): the launch calls phase 1 only for the first transaction, with the universal helper, when the
Info.plist sets RewindBoxS2ArmProbe; between the core load handoff and prepareJit; phase 2 after the detach succeeded
and before the guest memory lease; no result of the hook can fail the launch; the pinned helper script is untouched.
Executed (macOS, Xcode): the hook compiled with clang, and the exact Swift call of the launch compiled against its
header. Scenarios: no S2ArmProbePlugin class (one "absent" line, phase 2 not run); a fake probe class whose phase 1
logs, asks a capability-shaped region (length 0, refused without a trap) and returns 2, whose phase 2 logs and returns
0; a second phase 1 in the process is refused; every line is the launch journal's JSON line, durable (fsync) and
escaped. The region check: below 64 KiB, unaligned, above 2^48 or not the address asked for is a refusal. No trap is
executed (there is no helper on the runner). Writes dist/melonx/s2arm-probe-hook-checks.json.
"""
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
HOOK, HEADER = CLASSES / 'MeloNXS2ArmProbeHook.m', CLASSES / 'MeloNXS2ArmProbeHook.h'
PLUGIN = CLASSES / 'MeloNXInternalBridgePlugin.swift'
SCRIPT = ROOT / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


plugin = PLUGIN.read_text()
launch = plugin[plugin.index('stage = "jit"'):plugin.index('stage = "memory"')]
hook = launch[launch.index('var s2armProbe: Int32 = -2'):]
check(launch.index('MeloNXJitConfirmCoreLoadHandoff()') < launch.index('MeloNXS2ArmProbeAttached(') < launch.index('try runtime.prepareJit()') <
      launch.index('MeloNXJitWaitForDetach(120,&message)') < launch.index('MeloNXS2ArmProbeDetached()'),
      'phase 1 between the load handoff and prepareJit, phase 2 after the detach')
check('if !reuseArena, universal, Bundle.main.object(forInfoDictionaryKey:"RewindBoxS2ArmProbe") as? Bool == true {' in hook and
      '"RewindBoxS2ArmProbeMapped") as? Bool == true ? 1 : 0' in hook and 'if s2armProbe >= 0 { _ = MeloNXS2ArmProbeDetached() }' in hook,
      'test IPAs only, first transaction, universal helper, phase 2 only after a phase 1 that ran')
check(plugin.count('MeloNXS2ArmProbeAttached(') == 1 and plugin.count('MeloNXS2ArmProbeDetached(') == 1 and 'throw' not in hook[:hook.index('try runtime.prepareJit()')] and
      'guard' not in hook[:hook.index('try runtime.prepareJit()')], 'no hook result changes the launch')
check(plugin.index('MeloNXS2ArmProbeDetached()') < plugin.index('try MeloNXMemoryLease.shared.prepare('), 'phase 2 before the guest memory lease')
source = HOOK.read_text()
check('"mov x16, #1\\n" "brk #0xf00d\\n" "ret"' in source and source.count('"brk #') == 1, 'one trap: the Core\'s command 1 trampoline')
check('fsync(fd);' in source and 'O_APPEND' in source and 'sigaction' not in source and 'mmap' not in source,
      'durable appends; the hook installs no handler and maps nothing itself')
check(hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == 'fe162e0bd44471aa930db8582203b85ed135baf51712b57249dfcbfc6fe112fc',
      'the pinned helper script is unchanged')

result = dict(result='passed', staticOnly=True, physicalDeviceTested=False)
if platform.system() == 'Darwin' and shutil.which('xcrun'):
    work = Path(tempfile.mkdtemp(prefix='melonx-s2arm-hook-'))
    (work / 'Fake.m').write_text(r'''#import <Foundation/Foundation.h>
#include <stdint.h>
typedef uint64_t (*P)(uint64_t, uint64_t);
typedef void (*L)(const char *, const char *, const char *);
static uint64_t refused;
static int Attached(P prepare, L log, uint32_t flags) {
    refused = prepare(0, 0); // capability-shaped: refused without a trap
    log("synthetic", "attached", flags ? "flags 1 \"quoted\" \\ back\nline" : "flags 0");
    return 2;
}
static int Detached(L log) { log("synthetic", "detached", refused == 0 ? "capability refused" : "capability returned"); return 0; }
@interface S2ArmProbePlugin : NSObject
@end
@implementation S2ArmProbePlugin
+ (void *)attachedFunction { return (void *)Attached; }
+ (void *)detachedFunction { return (void *)Detached; }
@end
''')
    (work / 'main.swift').write_text(r'''import Foundation
let path = CommandLine.arguments[1]
let flags: UInt32 = CommandLine.arguments[2] == "1" ? 1 : 0
var s2armProbe: Int32 = -2
s2armProbe = MeloNXS2ArmProbeAttached(Optional(path) ?? "", flags)
let again = MeloNXS2ArmProbeAttached(path, flags)
var detached: Int32 = -2
if s2armProbe >= 0 { detached = MeloNXS2ArmProbeDetached() }
let regions = [MeloNXS2ArmCheckedRegion(0, 0xE08), MeloNXS2ArmCheckedRegion(0, 0x1_0000_2000), MeloNXS2ArmCheckedRegion(0, 0x1_0000_4000),
               MeloNXS2ArmCheckedRegion(0x2_0000_0000, 0x1_0000_4000), MeloNXS2ArmCheckedRegion(0x2_0000_0000, 0x2_0000_0000),
               MeloNXS2ArmCheckedRegion(0, 0x1_0000_0000_0000)]
print("{\"phase1\": \(s2armProbe), \"again\": \(again), \"phase2\": \(detached), \"regions\": [\(regions.map { String($0) }.joined(separator: ","))]}")
''')
    runs = {}
    for name, with_fake in (('absent', False), ('fake', True), ('fakeMapped', True)):
        out = work / name
        sources = [str(HOOK)] + ([str(work / 'Fake.m')] if with_fake else [])
        objects = []
        for index, src in enumerate(sources):
            obj = work / f'{name}-{index}.o'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Werror', '-c', src, '-o', str(obj), '-I', str(CLASSES)], check=True)
            objects.append(str(obj))
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-import-objc-header', str(HEADER), str(work / 'main.swift'), *objects,
                        '-framework', 'Foundation', '-o', str(out)], check=True)
        journal = work / f'{name}.log'
        run = subprocess.run([str(out), str(journal), '1' if name == 'fakeMapped' else '0'], capture_output=True, text=True, timeout=60)
        check(run.returncode == 0, name + ': runs: ' + run.stderr[-500:])
        lines = [json.loads(l[len('[MeloNX:native] '):]) for l in journal.read_text().splitlines()]
        runs[name] = dict(output=json.loads(run.stdout.strip().splitlines()[-1]), lines=lines)
    a, f, m = runs['absent'], runs['fake'], runs['fakeMapped']
    check(a['output']['phase1'] == -1 and a['output']['again'] == -2 and a['output']['phase2'] == -2, 'absent probe: -1, then refused, no phase 2')
    check([(l['stage'], l['status']) for l in a['lines']] == [('s2armProbe.hook', 'absent'), ('s2armProbe.hook', 'skipped')], str(a['lines']))
    check(f['output']['phase1'] == 2 and f['output']['again'] == -2 and f['output']['phase2'] == 0, 'fake probe: phase 1 result, refused again, phase 2')
    check([(l['stage'], l['status']) for l in f['lines']] == [('s2armProbe.hook', 'phase1'), ('s2armProbe.synthetic', 'attached'),
          ('s2armProbe.hook', 'phase1Done'), ('s2armProbe.hook', 'skipped'), ('s2armProbe.hook', 'phase2'),
          ('s2armProbe.synthetic', 'detached'), ('s2armProbe.hook', 'phase2Done')], str(f['lines']))
    check(f['lines'][5]['diagnostic'] == 'capability refused' and f['lines'][0]['diagnostic'] == 'phase 1 begins, flags 0x0', 'no trap for a 0 length')
    check(m['lines'][1]['diagnostic'] == 'flags 1 "quoted" \\ back\nline' and m['lines'][0]['diagnostic'] == 'phase 1 begins, flags 0x1',
          'flags passed; JSON escaping round-trips')
    check(all(set(l) == {'diagnostic', 'nativeStatus', 'pid', 'stage', 'status', 'timestamp'} and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', l['timestamp'])
              for r in runs.values() for l in r['lines']), 'the launch journal line format')
    check(f['output']['regions'] == [0, 0, 0x100004000, 0, 0x200000000, 0], 'region check: Exx, unaligned, wrong address and above 2^48 refused')
    result = dict(result='passed', staticOnly=False, physicalDeviceTested=False, runs=runs)
result['checks'] = checks
result['inputs'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (HOOK, HEADER, PLUGIN, Path(__file__))}
out = ROOT / 'dist/melonx/s2arm-probe-hook-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=1) + '\n')
print(json.dumps(dict(result='passed', checks=checks, staticOnly=result['staticOnly'])))
