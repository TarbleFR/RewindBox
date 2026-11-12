#!/usr/bin/env python3
"""The S2Arm checks of the pinned-engine component s2arm on the built application (components.s2arm.checks).

  check_app.py APP

Run by the recipe (`embed-engine s2arm APP`) after it proved the frameworks and extras are the pinned bytes and wrote
S2Arm-native-identity.json. What the recipe cannot know about S2Arm is checked here:
  - the JIT helper extension (built from sources: its contract, versions, script and executable)
  - the engine frameworks: one pinned Mach-O each, the engine's direct shader chain beside it
  - the system data tree S2ArmSystemData: exactly the files of its SHA256SUMS (the pinned one), data and licences only
  - the engine licence and notice texts in Legal/S2Arm: the legal gate's rule, the record of the identity
  - the engine bridge in Runner: its entry points defined, no rb_s2arm_* left undefined, rb_s2arm_engine_loaded in the
    export trie, neither the bridge nor the preparation library packaged on its own
"""
from __future__ import annotations

import json
import plistlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import engine_pin as pin_tool  # noqa: E402

PIN = 'build-utils/s2arm/engine-pin.json'
IDENTITY = 'S2Arm-native-identity.json'
HELPER = 'S2ArmJITHelper.appex'
HELPER_EXECUTABLE = 'S2ArmJITHelper'
HELPER_SCRIPT = 'packages/s2arm_jit_helper/ios/Resources/s2arm-universal.js'
STIKJIT = '@rpath/StikJIT.framework/StikJIT'
SYSTEM_DATA = 'S2ArmSystemData'
LEGAL_NOTICES = 'Legal/S2Arm'
ENGINE_LOADED = '_rb_s2arm_engine_loaded'
BRIDGE_PLUGIN = 'S2ArmEngineBridgePlugin'
PREPARE_ENTRY_POINTS = tuple('_rb_s2arm_' + name for name in (
    'caps', 'direct_skeleton', 'module_dir', 'ns2_detect', 'ns2_dump', 'prepare_code', 'resource_pack'))
RUNNER_DEFINES = ('_OBJC_CLASS_$_' + BRIDGE_PLUGIN, ENGINE_LOADED, '_rb_s2arm_engine_mark_loading') + PREPARE_ENTRY_POINTS
SEPARATE_IMAGES = ('s2arm_engine_bridge.framework', 'S2ArmPrepare.xcframework', 'libS2ArmPrepare.a')
BRIDGE_REGISTRANT = 'ios/Runner/GeneratedPluginRegistrant.m'
BRIDGE_REGISTERED = re.compile(r'\[\s*' + BRIDGE_PLUGIN + r'\s+registerWithRegistrar:\s*\[\s*registry\s+registrarForPlugin:'
                               r'\s*@"' + BRIDGE_PLUGIN + r'"\s*\]\s*\]\s*;')


def require(condition, message):
    pin_tool.require(condition, message)


def on_path():
    pin_tool.on_path()


def check_helper(read, names, host, source_script):
    on_path()
    from verify_ipa import macho
    import validate_single_ipa_distribution as distribution
    contract = distribution.S2ARM_EXTENSIONS[HELPER]
    root = f'PlugIns/{HELPER}/'
    info = plistlib.loads(read(root + 'Info.plist'))
    metadata = info.get('NSExtension', {})
    require(info.get('CFBundleExecutable') == HELPER_EXECUTABLE and info.get('CFBundlePackageType') == 'XPC!' and
            info.get('CFBundleIdentifier') == host['CFBundleIdentifier'] + contract['bundleSuffix'] and
            info.get(contract['marker']) == '1' and metadata.get('NSExtensionPrincipalClass') == contract['principalClass'] and
            metadata.get('NSExtensionPointIdentifier') == 'com.apple.share-services' and
            info.get('CFBundleVersion') == host['CFBundleVersion'] and
            info.get('CFBundleShortVersionString') == host['CFBundleShortVersionString'],
            f'{HELPER} does not carry the S2Arm helper contract or the host versions')
    require(read(root + 's2arm-universal.js') == source_script, f'{HELPER}/s2arm-universal.js differs from {HELPER_SCRIPT}')
    images = sorted(name for name in names if name.startswith(root) and read(name)[:4] in pin_tool.MACHO_MAGICS)
    require(images == [root + HELPER_EXECUTABLE], f'{HELPER} must hold one Mach-O image, its executable: {images}')
    executable = read(root + HELPER_EXECUTABLE)
    distribution.require_arm64_executable(executable, HELPER)
    image = macho(executable)
    require(any(item['path'] == STIKJIT for item in image['dependencies']) and
            '@executable_path/../../Frameworks' in image['rpaths'], f'{HELPER} does not link the shared StikJIT of the host')


def thin_arm64(raw):
    if raw[:4] in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        wide = raw[:4] == b'\xca\xfe\xba\xbf'
        stride, size = (32, 8) if wide else (20, 4)
        for index in range(int.from_bytes(raw[4:8], 'big')):
            at = 8 + index * stride
            if int.from_bytes(raw[at:at + 4], 'big') == 0x0100000C:
                offset = int.from_bytes(raw[at + 8:at + 8 + size], 'big')
                return raw[offset:offset + int.from_bytes(raw[at + 8 + size:at + 8 + 2 * size], 'big')]
        raise pin_tool.PinError('S2Arm engine pin: the Runner has no arm64 image')
    return raw


def check_runner(raw, label):
    on_path()
    from verify_ipa import macho
    from validate_shader_compiler_ipa import exported_symbols
    image = macho(raw)
    missing = [name for name in RUNNER_DEFINES if name not in set(image['definedSymbols'])]
    require(not missing, f'{label} does not define {missing}: the engine bridge or S2ArmPrepare is not linked into it')
    left = sorted({name for name in image['undefinedSymbols'] if name.startswith('_rb_s2arm_')})
    require(not left, f'{label} leaves {left} undefined')
    require(ENGINE_LOADED in exported_symbols(thin_arm64(raw)), f'{label} does not export {ENGINE_LOADED} (dyld export trie)')


def check_app(app, root=ROOT):
    app, root = Path(app), Path(root)
    pin = json.loads((root / PIN).read_text())
    identity = json.loads((app / IDENTITY).read_bytes())
    require(identity.get('component') == 's2arm' and identity.get('packagedFingerprint') == pin['packagedFingerprint'],
            f'{IDENTITY} is not the pinned engine\'s')
    names = [path.relative_to(app).as_posix() for path in app.rglob('*') if path.is_file()]

    def read(relative):
        return (app / relative).read_bytes()
    host = plistlib.loads(read('Info.plist'))
    check_helper(read, names, host, (root / HELPER_SCRIPT).read_bytes())
    for label, expected in pin['binaries'].items():
        folder, _, image = label.partition('/')
        if folder.endswith('.framework') and image == folder[:-len('.framework')]:
            data = read('Frameworks/' + label)
            require(pin_tool.sha(data) == expected['sha256'], f'Frameworks/{label} is not the pinned image')
    chain = read('Frameworks/S2ArmEngine.framework/' + pin_tool.DIRECT_CHAIN).decode('utf-8', errors='replace').strip()
    require(re.fullmatch(r'[0-9a-f]{1,12}', chain), f'{pin_tool.DIRECT_CHAIN} is not a direct shader chain version')
    prefix = SYSTEM_DATA + '/'
    tree = {name[len(prefix):]: read(name) for name in names if name.startswith(prefix)}
    require(pin_tool.sha(tree.get(pin_tool.SYSDATA_SUMS, b'')) == pin['producers']['sysdata']['members'][pin_tool.SYSDATA_SUMS],
            f'{SYSTEM_DATA}/{pin_tool.SYSDATA_SUMS} is not the pinned one')
    pin_tool.check_sysdata(tree, SYSTEM_DATA)
    notices = {name[len(LEGAL_NOTICES) + 1:]: read(name) for name in names if name.startswith(LEGAL_NOTICES + '/')}
    record = identity.get('licenses')
    errors = pin_tool.licence_errors(notices, record, identity.get('sourceIdentity', {}).get('s2arm_commit'))
    require(not errors and record == pin['identity']['licenses'], f'{LEGAL_NOTICES}: ' + '; '.join(errors or ['not the pinned record']))
    separate = sorted(name for name in names if any(marker in name for marker in SEPARATE_IMAGES))
    require(not separate, f'The bridge or S2ArmPrepare is packaged on its own ({separate[:3]}): both are linked into Runner')
    executable = str(host.get('CFBundleExecutable', ''))
    require(executable in names, f'The application has no executable {executable!r}')
    check_runner(read(executable), executable)
    registrant = root / BRIDGE_REGISTRANT
    if registrant.is_file():
        require(len(BRIDGE_REGISTERED.findall(registrant.read_text(errors='replace'))) == 1,
                f'{BRIDGE_REGISTRANT} does not register {BRIDGE_PLUGIN} once')
    return f'S2Arm app OK: helper, frameworks, {len(tree) - 1} system data files, {len(notices)} notices, Runner bridge'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    require(len(argv) == 1, 'usage: check_app.py APP')
    print(check_app(argv[0]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
