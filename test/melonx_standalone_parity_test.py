#!/usr/bin/env python3
"""Standalone MeloNX parity in the host: Game Mode keys, MoltenVK choice and
packaging, stderr capture into app.log, idle timer and present target.

The Swift capture is compiled and executed only where xcrun exists (macOS CI);
everything else runs anywhere. Gameplay and the device's MoltenVK are not tested.
"""
import hashlib
import io
import json
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
sys.path.insert(0, str(ROOT / 'build-utils'))
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
checks = 0


def check(condition, message):
    global checks
    assert condition, message
    checks += 1


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


# Game Mode: the standalone app's declarations, other keys untouched.
import configure_melonx_ios as configure
with tempfile.TemporaryDirectory() as temporary:
    runner = Path(temporary)
    (runner / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'x', 'CADisableMinimumFrameDurationOnPhone': True}))
    configure.RUNNER = runner
    configure.configure_game_mode()
    info = plistlib.loads((runner / 'Info.plist').read_bytes())
    check(info == {'CFBundleIdentifier': 'x', 'CADisableMinimumFrameDurationOnPhone': True, 'LSSupportsGameMode': True,
                   'GCSupportsGameMode': True, 'LSApplicationCategoryType': 'public.app-category.games'}, info)
check('configure_game_mode()' in (ROOT / 'build-utils/configure_melonx_ios.py').read_text().split('def main')[1], 'Game Mode not configured')

# Packaging: pinned bytes only, license from the MoltenVK source archive,
# a receipt of its own; the six-framework MeloNX receipt is not touched.
import package_standalone_moltenvk as standalone
check(standalone.PINNED_SHA256 == '5735ca4aee60ed7e0475b80b8ecdcfc952e4e0b7d49018f11781e51e5106bfa5', 'pin changed')
with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    pins = json.loads((ROOT / 'build-utils/melonx/native-dependencies.json').read_text())
    sources = work / 'dist/melonx-native/sources'
    sources.mkdir(parents=True)
    (work / 'build-utils/melonx').mkdir(parents=True)
    shutil.copy2(ROOT / 'build-utils/melonx/native-dependencies.json', work / 'build-utils/melonx/native-dependencies.json')
    license_text = b'Apache License\nVersion 2.0, January 2004\n'
    with tarfile.open(sources / f"MoltenVK-{pins['sources']['MoltenVK']['revision']}.tar.gz", 'w:gz') as archive:
        for name, data in [('MoltenVK/README.md', b'x'), ('MoltenVK/External/x/LICENSE', b'other'), ('MoltenVK/LICENSE', license_text)]:
            member = tarfile.TarInfo(name); member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    framework = work / 'frameworks' / f'{standalone.NAME}.framework'
    framework.mkdir(parents=True)
    (framework / standalone.NAME).write_bytes(b'binary')
    (framework / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': standalone.NAME}))
    receipt = work / 'receipt.json'
    receipt.write_text(json.dumps({'packagedSha256': hashlib.sha256(b'binary').hexdigest(), 'repository': 'r', 'revision': 'v',
                                   'path': standalone.SOURCE_PATH, 'sourceSha256': standalone.PINNED_SHA256}))
    standalone.ROOT, standalone.FRAMEWORKS, standalone.RECEIPT = work, work / 'frameworks', receipt
    app = work / 'Runner.app'
    (app / 'Frameworks').mkdir(parents=True)
    standalone.embed(app)
    check((app / 'Frameworks' / f'{standalone.NAME}.framework' / standalone.NAME).read_bytes() == b'binary', 'framework not embedded')
    check((app / standalone.LEGAL / 'LICENSE.txt').read_bytes() == license_text, 'license not copied verbatim')
    notice = (app / standalone.LEGAL / 'NOTICE.txt').read_text()
    check(standalone.PINNED_SHA256 in notice and 'Apache License, Version 2.0' in notice, notice)
    identity = json.loads((app / 'MeloNX-standalone-moltenvk-identity.json').read_text())
    check(identity['license']['sourcePath'] == 'MoltenVK/LICENSE', identity)
    check(not (app / 'MeloNX-native-identity.json').exists(), 'the six-framework receipt was written')
    (framework / standalone.NAME).write_bytes(b'tampered')
    try:
        standalone.embed(app)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'a changed framework was embedded')
package = (ROOT / 'build-utils/melonx/package_runtime.py').read_text()
check("NAMES = {'MeloNXMoltenVK','MeloNXSDL3','MeloNXAvUtil','MeloNXAvCodec','MeloNXJitSupport'}" in package, 'source-built set changed')

# Strings shown by the in-game MoltenVK menu, in all twelve languages.
strings = json.loads((ROOT / 'build-utils/melonx/ui-strings.json').read_text())
controller = (CLASSES / 'MeloNXMetalSessionViewController.swift').read_text()
for key in ['MoltenVK version', 'In use', 'Restart RewindBox to use this MoltenVK.', 'RewindBox (1.3.0)', 'MeloNX app (1.4.0)',
            'Emulation priority', 'High (RewindBox)', 'Default (MeloNX app)', 'Applies when the next game starts.']:
    row = strings['rows'][key]
    check(len(row) == 12 and all(value.strip() for value in row), key)
    check(f'"{key}"' in controller, key + ' unused')
check(strings['rows']['MoltenVK version'][1] == 'Version de MoltenVK', 'French label')
check(strings['rows']['Emulation priority'][1] == 'Priorité de l’émulation', 'French priority label')

# Wiring. The smoke app compiles MeloNXSessionHost.swift and MeloNXRuntimeAPI.swift
# alone, and the session host must stay byte-identical (session host test).
runtime = (CLASSES / 'MeloNXRuntimeAPI.swift').read_text()
host = CLASSES / 'MeloNXSessionHost.swift'
# (The session host test pins it to 084fdb5, absent from shallow clones.)
check(git('show', 'HEAD:' + str(host.relative_to(ROOT))) == host.read_bytes(), 'session host changed')
check('MeloNXMoltenVKChoice' not in runtime and 'MeloNXStdioCapture' not in runtime, 'runtime API depends on the parity file')
check(runtime.index('"neostation_melonx_select_moltenvk"') < runtime.index('configureNative($0)'), 'MoltenVK selected after loading')
check('init(library: URL, frameworks: URL, root: URL, moltenVk requested: Int32 = 0)' in runtime, 'smoke default changed')
plugin = (CLASSES / 'MeloNXInternalBridgePlugin.swift').read_text()
check('moltenVk:moltenVk' in plugin and 'MeloNXMoltenVKChoice.available(moltenVk' in plugin, 'plugin does not choose MoltenVK')
check('if moltenVk == 1, case .operation("frameworks", _, _)? = error as? MeloNXHostError {\n                MeloNXMoltenVKChoice.preferred = 0' in plugin, 'no way back from a failing standalone MoltenVK')
check(plugin.index('MeloNXLaunchJournal.configure(path:path)') < plugin.index('MeloNXStdioCapture.configure(path:path)'), 'capture journal')
start = controller.index('try host.start(')
check(controller.rindex('MeloNXStdioCapture.begin()', 0, start) > controller.rindex('override func viewDidAppear', 0, start), 'capture not begun')
check(controller.count('MeloNXStdioCapture.end(); UIApplication.shared.isIdleTimerDisabled = false') == 2, 'capture/idle timer not restored')
check('UIApplication.shared.isIdleTimerDisabled = true' in controller, 'idle timer')
check(controller.count('applyPresentTarget()') == 3 and 'maximumFramesPerSecond' in controller, 'present target')
# Emulation priority: applied on the session thread after authorization, never
# on the main thread, and journaled; the menu shows the choice in effect.
before = plugin[plugin.index('beforeRun:{ [weak self] in'):plugin.index('},firstFrame:')]
check(before.index('DispatchQueue.main.sync(execute:authorize)') < before.index('if authorized && !Thread.isMainThread {') < before.index('MeloNXEmulationPriority.applyToCurrentThread()'), 'priority wiring')
check('MeloNXLaunchJournal.record("session","emulationPriority"' in before and before.rstrip().endswith('return authorized'), 'priority journal')
check('MeloNXEmulationPriority.applied ?? 0' in controller and 'MeloNXEmulationPriority.preferred = choice' in controller, 'priority menu')
session = (ROOT / 'native/melonx/EmbeddedSession.cs').read_text()
check('Engine options: ptc=' in session and 'moltenVk={EmbeddedNativeLibraries.MoltenVk}' in session, 'options journal')

# Execute the capture where the toolchain exists.
if shutil.which('xcrun'):
    with tempfile.TemporaryDirectory(prefix='melonx-parity-') as temporary:
        work = Path(temporary)
        log = work / 'app.log'
        (work / 'main.swift').write_text(r'''import Foundation
import Darwin
let path = CommandLine.arguments[1]
UserDefaults.standard.removeObject(forKey:MeloNXMoltenVKChoice.key)
precondition(MeloNXMoltenVKChoice.preferred == 1)
MeloNXMoltenVKChoice.preferred = 0
precondition(MeloNXMoltenVKChoice.preferred == 0)
UserDefaults.standard.removeObject(forKey:MeloNXMoltenVKChoice.key)
// Emulation priority on a GCD worker of a user-initiated serial queue, like
// MeloNXSessionHost's session queue that runs beforeRun and the engine.
UserDefaults.standard.removeObject(forKey:MeloNXEmulationPriority.key)
precondition(MeloNXEmulationPriority.preferred == 0 && MeloNXEmulationPriority.applied == nil)
let sessionQueue = DispatchQueue(label:"parity.session", qos:.userInitiated)
func onUserInitiatedThread(_ body: @escaping () -> Void) {
    let done = DispatchSemaphore(value:0)
    sessionQueue.async { body(); done.signal() }
    done.wait()
}
onUserInitiatedThread {
    let kept = MeloNXEmulationPriority.applyToCurrentThread()
    precondition(kept.status == 0 && kept.qos == QOS_CLASS_USER_INITIATED && MeloNXEmulationPriority.applied == 0)
    precondition(MeloNXEmulationPriority.name(kept.qos) == "user-initiated")
}
MeloNXEmulationPriority.preferred = 1
onUserInitiatedThread {
    let lowered = MeloNXEmulationPriority.applyToCurrentThread()
    precondition(lowered.status == 0 && lowered.qos == QOS_CLASS_DEFAULT && qos_class_self() == QOS_CLASS_DEFAULT)
    precondition(MeloNXEmulationPriority.applied == 1 && MeloNXEmulationPriority.name(lowered.qos) == "default")
}
UserDefaults.standard.removeObject(forKey:MeloNXEmulationPriority.key)
MeloNXStdioCapture.begin()          // unconfigured: no capture
fputs("before configure\n", stderr)
MeloNXStdioCapture.configure(path:"/tmp/not-the-journal.txt")
MeloNXStdioCapture.begin()
fputs("still uncaptured\n", stderr)
MeloNXStdioCapture.configure(path:path)
MeloNXStdioCapture.begin()
MeloNXStdioCapture.begin()          // idempotent
fputs("[mvk-error] VK_ERROR_DEVICE_LOST: MTLCommandBuffer failed\n", stderr)
fputs("2026 RewindBox[1:2] [MeloNX:launch] gpu passed (0)\n", stderr)
fputs("secret " + String(repeating:"a", count:64) + "\n", stderr)
fputs("header_key = 0123\n", stderr)
fputs("partial", stderr)
fputs(" line\n", stderr)
for index in 0..<2100 { fputs("line \(index)\n", stderr) }
// NSLog's stderr copies (Ryujinx console output on iOS) have their own budget.
let banner = "\(ProcessInfo.processInfo.processName)[\(getpid()):"
// A stub logged every frame, in Ryujinx's real format (its own clock after
// the banner, as in the 553 log): copied once, then counted. Both clocks differ.
func clock(_ index: Int) -> String { String(format:"00:00:%02ld.%03ld", index / 10, index % 1000) }
for index in 0..<300 {
    fputs("2026-10-26 12:00:00.\(index) \(banner)772] \(clock(index)) |S| {Common} ServiceHid GetNpadJoyHoldType: Stubbed. {}\n", stderr)
    if index < 50 { fputs("2026-10-26 12:00:01.\(index) \(banner)773] \(clock(index + 1)) |S| {Common} ServiceAudio QueryAudioDeviceSystemEvent: Stubbed. \n", stderr) }
}
for index in 0..<520 { fputs("2026-10-26 12:00:00.000 \(banner)771] |S| stub \(index)\n", stderr) }
fputs("unterminated", stderr)
MeloNXStdioCapture.end()
MeloNXStdioCapture.end()            // idempotent
fputs("after end\n", stderr)
for _ in 0..<100 {
    if (try? String(contentsOfFile:path, encoding:.utf8))?.contains("capture end") == true { exit(0) }
    usleep(50_000)
}
exit(2)
''')
        executable = work / 'parity'
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(CLASSES / 'MeloNXStandaloneParity.swift'), str(work / 'main.swift'),
                        '-o', str(executable)], check=True)
        result = subprocess.run([str(executable), str(log)], capture_output=True, text=True, timeout=60)
        check(result.returncode == 0, result)
        lines = log.read_text().splitlines()
        check(all(line.startswith('[MeloNX:stderr] ') for line in lines), lines[:5])
        body = [line.removeprefix('[MeloNX:stderr] ') for line in lines]
        check(body[0] == 'capture begin' and body[1] == '[mvk-error] VK_ERROR_DEVICE_LOST: MTLCommandBuffer failed', body[:3])
        check(not any('[MeloNX:launch]' in line for line in body), 'journal echo copied')
        check('secret [redacted]' in body and '[redacted key entry]' in body and 'partial line' in body, body[:8])
        check('line 2099' in result.stderr and 'unterminated' in result.stderr, 'stderr not mirrored')
        check('before configure' in result.stderr and 'after end' in result.stderr, 'uncaptured output lost')
        check(not any(x in body for x in ['before configure', 'still uncaptured', 'after end']), 'captured outside the session')
        # 4 lines before the loop, then 1996 of its 2100 lines: 104 + the
        # unterminated tail are counted, not copied. NSLog-banner lines get
        # their own 500-line budget: the two repeated stubs are copied once
        # (348 repeats), then 498 of the 520 distinct ones; 22 more not copied.
        stubs = [line for line in body if '|S| stub ' in line]
        check(len(stubs) == 498 and stubs[-1].endswith('stub 497'), (len(stubs), stubs[-1:]))
        once = [line for line in body if line.endswith('] 00:00:00.000 |S| {Common} ServiceHid GetNpadJoyHoldType: Stubbed. {}')]
        check(len(once) == 1 and once[0].startswith('2026-10-26 12:00:00.0 '), once)
        plain = [line for line in body if '|S| ' not in line]
        check(len(plain) == 2002 and plain[-2] == 'line 1995', (len(plain), plain[-2:]))
        check(body[-3:] == ['repeated 299 more times: |S| {Common} ServiceHid GetNpadJoyHoldType: Stubbed. {}',
                            'repeated 49 more times: |S| {Common} ServiceAudio QueryAudioDeviceSystemEvent: Stubbed. ',
                            'capture end: 2000 lines, 500 NSLog lines, 348 repeats, 127 not copied'], body[-3:])
    print('Executed the stderr capture and MoltenVK preference on macOS.')

print(f'PASS {checks} standalone parity checks')
