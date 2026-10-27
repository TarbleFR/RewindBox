#!/usr/bin/env python3
"""Switch keyboard text and the L3/R3 touch buttons in the MeloNX host.

Protocol: MeloNX's AlertHelper (pinned engine source) sends "show_text_input"
through its callback registry and blocks until "show_text_input_result_<id>"
is invoked; RewindBox never registered it, so a game asking for text waited
forever. The real MeloNXTextInput.swift runs in UIKit on an iOS simulator
against a registry double (macOS only, where xcrun exists); the wiring, the
engine protocol and the twelve-language strings are checked everywhere.
No game, engine or iPhone runs here.
"""
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
FIXTURES = ROOT / 'test/melonx_text_input'
SOURCE = CLASSES / 'MeloNXTextInput.swift'
checks = 0


def check(condition, message):
    global checks
    assert condition, message
    checks += 1


def pinned(name, env):
    for candidate in [os.environ.get(env), ROOT / '.native-sources' / name]:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


text_input = SOURCE.read_text()
controller = (CLASSES / 'MeloNXMetalSessionViewController.swift').read_text()
runtime = (CLASSES / 'MeloNXRuntimeAPI.swift').read_text()

# Engine protocol, from the pinned MeloNX source when it is materialized.
engine = pinned('MeloNX', 'MELONX_SOURCE_DIR')
if engine:
    revision = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())['revision']
    if (engine / '.git').exists():
        check(subprocess.check_output(['git', '-C', str(engine), 'rev-parse', 'HEAD'], text=True).strip() == revision, 'engine revision')
    alert = (engine / 'src/Ryujinx.Library/Native/AlertHelper.cs').read_text()
    check('var resultCallback = $"show_text_input_result_{callbackId}";' in alert, 'result name')
    check('CallbackRegistry.Invoke("show_text_input", bytes)' in alert, 'request name')
    request = alert[alert.index('internal sealed class TextInputRequest'):]
    for name in ['Title', 'Message', 'Placeholder', 'CallbackId']:
        check(f'public string {name} {{ get; set; }}' in request and f'"{name}"' in text_input, name)
    check('JsonNamingPolicy' not in alert and 'PropertyNamingPolicy' not in alert, 'JSON names are the property names')
    window = (engine / 'src/Ryujinx.Library/Window/WindowBase.cs').read_text()
    dialog = window[window.index('public bool DisplayInputDialog('):window.index('public void SendStatistics(')]
    check('AlertHelper.ShowAlertWithTextInput(args.HeaderText, args.SubtitleText, args.GuideText' in dialog
          and 'inputReceived.Wait();' in dialog, 'the keyboard applet blocks on the native answer')
    registry = (engine / 'src/Ryujinx.Common/Callbacks/CallbackRegistry.cs').read_text()
    check('public delegate void SwiftDataCallback(ref CallbackData data, nint userData);' in registry, 'callback signature')
    check(re.search(r'public struct CallbackData\s*\{\s*public nint Ptr;\s*public int\s+Len;', registry), 'CallbackData layout')
    check('public static byte InvokeCallback(nint namePtr, nint dataPtr, int dataLen)' in registry, 'invoke signature')
    check('if (dataPtr == nint.Zero || dataLen == 0)\n                return Invoke(name) ? (byte)1 : (byte)0;' in registry, 'empty answer')
    passthrough = (engine / 'src/Ryujinx.Library/UnmanagedPassthrough.cs').read_text()
    check('[UnmanagedCallersOnly(EntryPoint = "RegisterCallback")]\n        public static void RegisterCallback(nint namePtr, nint callbackPtr, nint userData)' in passthrough, 'register export')
    check('[UnmanagedCallersOnly(EntryPoint = "InvokeCallback")]\n        public static byte InvokeCallback(nint namePtr, nint dataPtr, int dataLen)' in passthrough, 'invoke export')
    applet = (engine / 'src/Ryujinx.HLE/HOS/Applets/SoftwareKeyboard/SoftwareKeyboardApplet.cs').read_text()
    check('_textValue ??= initialText ?? DefaultInputText;' in applet, 'an empty answer keeps the initial text')

# Host signatures match that protocol.
check('typealias Register = @convention(c) (UnsafePointer<CChar>?, UnsafeRawPointer?, UnsafeMutableRawPointer?) -> Void' in text_input, 'register')
check('typealias Invoke = @convention(c) (UnsafePointer<CChar>?, UnsafeRawPointer?, Int32) -> UInt8' in text_input, 'invoke')
check('struct CallbackData { var pointer: UnsafeMutableRawPointer?; var length: Int32 }' in text_input, 'layout')
check('typealias CallbackRegister = @convention(c) (UnsafePointer<CChar>?, UnsafeRawPointer?, UnsafeMutableRawPointer?) -> Void' in runtime
      and 'typealias CallbackInvoke = @convention(c) (UnsafePointer<CChar>?, UnsafeRawPointer?, Int32) -> UInt8' in runtime, 'runtime types')
# Optional exports: an older engine still loads. The smoke app compiles the
# runtime API without this file.
check('registerCallback = dlsym(handle, "RegisterCallback").map' in runtime and 'invokeCallback = dlsym(handle, "InvokeCallback").map' in runtime, 'optional exports')
check('MeloNXTextInput' not in runtime, 'runtime API depends on the text input file')
check(text_input.count('Data(bytes: pointer, count: Int(value.length))') == 1
      and text_input.index('let bytes = Data(') < text_input.index('DispatchQueue.main.async { MeloNXTextInput.shared.enqueue(request) }'),
      'request bytes copied before leaving the engine thread')
check('let detail = text.map {' in text_input and '\\(text' not in text_input, 'entered text journaled')

# Session wiring: attached with the controls, answered before every stop.
install = controller[controller.index('private func installControls'):controller.index('private func startPerfJournal')]
check(install.index('guard let runtime else { return }') < install.index('MeloNXTextInput.shared.attach(register:runtime.registerCallback,invoke:runtime.invokeCallback,presenter:self)'), 'attach')
for stop in ['router?.close(); MeloNXTextInput.shared.detach(self); host.requestStop(); updateMemoryGraph()',
             'if isBeingDismissed || presentingViewController == nil { router?.close(); MeloNXTextInput.shared.detach(self); host.requestStop() }',
             '        router?.close(); MeloNXTextInput.shared.detach(self); host.requestStop()\n    }',
             'self?.router?.close(); MeloNXTextInput.shared.detach(self); self?.closing = true']:
    check(controller.count(stop) == 1, 'detach before stop: ' + stop)
check(controller.count('host.requestStop()') == 3 and controller.count('MeloNXTextInput.shared.detach(self)') == 4, 'every stop answers first')

# L3/R3: Melo-Controller's own stick buttons behind its renamed preference.
vendor = (ROOT / 'build-utils/melonx/vendor_controller.py').read_text()
check("for key in ['On-ScreenControllerScale', 'stickButton']:" in vendor and "'@AppStorage(\"rewindbox.melonx.' + key + '\")'" in vendor, 'renamed preference')
check('static let stickButtonsKey = "rewindbox.melonx.stickButton"' in controller, 'menu key')
menu = controller[controller.index('@objc private func showMenu()'):controller.index('private func updateMemoryGraph()')]
check(menu.index('MeloNXText("Edit touch controls")') < menu.index('MeloNXText("Stick buttons (L3/R3)")') < menu.index('MeloNXText("Close game")'), 'menu entry')
check('Self.stickButtons.toggle(); self?.refreshControls(); self?.setPause("menu",enabled:false)' in menu, 'overlay rebuilt with the new value')
melo = pinned('Melo-Controller', 'MELO_CONTROLLER_DIR')
if melo:
    view = (melo / 'Sources/Melo-Controller/ControllerView.swift').read_text()
    check(view.count('@AppStorage("stickButton") private var stickButton = false') == 1, 'original preference')
    check(view.count('editableButton(.leftStick)') == 2 and view.count('editableButton(.rightStick)') == 2 and view.count('if stickButton {') == 2,
          'both layouts show L3/R3 when enabled')
vendored = CLASSES.parent / 'Controller/ControllerView.swift'
if vendored.exists():
    check('@AppStorage("rewindbox.melonx.stickButton") private var stickButton = false' in vendored.read_text(), 'vendored key')
mapping = (CLASSES / 'MeloNXInputRouter.swift').read_text()
check('setButton(pad: 1, source: "touch", index: Int32(button.rawValue), pressed: true)' in mapping, 'touch buttons reach the engine by index')

# Strings, twelve languages, used by the host.
strings = json.loads((ROOT / 'build-utils/melonx/ui-strings.json').read_text())
for key, french in [('Text input', 'Saisie de texte'), ('Stick buttons (L3/R3)', 'Boutons des sticks (L3/R3)')]:
    row = strings['rows'][key]
    check(len(row) == 12 and all(value.strip() for value in row) and row[1] == french, key)
    check(f'MeloNXText("{key}")' in text_input + controller, key + ' unused')
check(all(f'MeloNXText("{key}")' in text_input for key in ['Cancel', 'OK']), 'alert actions')

report = None
if shutil.which('xcrun'):
    def run(*args):
        return subprocess.check_output(list(map(str, args)), stderr=subprocess.STDOUT, text=True, timeout=300).strip()
    sdk = run('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
    runtimes = json.loads(run('xcrun', 'simctl', 'list', 'runtimes', '-j'))['runtimes']
    simulator = next(r['identifier'] for r in reversed(runtimes) if r.get('isAvailable') and '.iOS-' in r['identifier'])
    device = run('xcrun', 'simctl', 'create', 'MeloNX text input ' + uuid.uuid4().hex[:8], 'com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro', simulator)
    bundle = 'com.neogamelab.neostation.textinput'
    try:
        run('xcrun', 'simctl', 'boot', device); run('xcrun', 'simctl', 'bootstatus', device, '-b')
        with tempfile.TemporaryDirectory(prefix='melonx-text-input-') as temporary:
            app = Path(temporary) / 'TextInput.app'; app.mkdir()
            (app / 'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleExecutable='TextInput', CFBundleIdentifier=bundle,
                CFBundleName='TextInput', CFBundlePackageType='APPL', CFBundleVersion='1', CFBundleShortVersionString='1',
                MinimumOSVersion='18.0', LSRequiresIPhoneOS=True, UIDeviceFamily=[1, 2], UILaunchScreen={},
                UIApplicationSceneManifest={'UIApplicationSupportsMultipleScenes': False, 'UISceneConfigurations': {}})))
            try:
                run('xcrun', 'swiftc', '-swift-version', '5', '-target', 'arm64-apple-ios18.0-simulator', '-sdk', sdk,
                    '-framework', 'UIKit', SOURCE, FIXTURES / 'Doubles.swift', FIXTURES / 'App.swift', '-o', app / 'TextInput')
                run('codesign', '--force', '--sign', '-', app)
                run('xcrun', 'simctl', 'install', device, app)
                run('xcrun', 'simctl', 'launch', device, bundle)
            except subprocess.CalledProcessError as error:
                print(error.output, flush=True); raise
            container = Path(run('xcrun', 'simctl', 'get_app_container', device, bundle, 'data'))
            result = container / 'Documents/textinput.json'
            deadline = time.monotonic() + 120
            while not result.exists() and time.monotonic() < deadline:
                time.sleep(.5)
            if not result.exists():
                print(run('xcrun', 'simctl', 'spawn', device, 'log', 'show', '--last', '3m', '--predicate', 'process == "TextInput"')[-16000:])
                raise AssertionError('UIKit text input probe did not report')
            report = json.loads(result.read_text())
            print(json.dumps(report, indent=2), flush=True)
            check(report['result'] == 'passed', report.get('error'))
            check(report['checks'] == 19, report['checks'])
    finally:
        subprocess.run(['xcrun', 'simctl', 'shutdown', device], check=False, capture_output=True)
        subprocess.run(['xcrun', 'simctl', 'delete', device], check=False, capture_output=True)

inputs = [SOURCE, CLASSES / 'MeloNXMetalSessionViewController.swift', CLASSES / 'MeloNXRuntimeAPI.swift',
          ROOT / 'build-utils/melonx/ui-strings.json', Path(__file__), *sorted(FIXTURES.glob('*'))]
receipt = dict(result='passed', checks=checks, engineProtocolChecked=engine is not None, controllerSourceChecked=melo is not None,
               uikitProbe=report, inputs={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
               physicalDeviceTested=False, gameTested=False)
out = ROOT / 'dist/melonx-host'; out.mkdir(parents=True, exist_ok=True)
(out / 'text-input.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
print(f'PASS {checks} checks: Switch text input protocol and wiring, L3/R3 toggle'
      + ('; real UIKit keyboard probe executed.' if report else '; UIKit probe needs macOS (not run here).'))
