#!/usr/bin/env python3
"""The libretro bridge's isSessionActive answer, as Flutter really sends it (macOS).

Build 454. Build 453 answered `@(self.session.active || self.launching)`. In
an Objective-C file `a || b` is a C int, which `@()` boxes with
numberWithInt:, and Flutter's iOS codec writes an NSNumber that is not a
CFBoolean as an int32: Dart received 0 or 1, and `invokeMethod<bool>` threw
"type 'int' is not a subtype of type 'bool?' in type cast". The 3DS system
data import refused to run ("could not check whether a game is running").
The Dart tests mocked the channel with Dart booleans and never saw those
bytes.

This test builds test/libretro_channel_codec/main.m with the real
LibretroInternalBridgePlugin.m and every bridge source it links (plus the
Flutter-free sources of the external_display pod and the neo_shader_kit
pod, as test/libretro_simulator_probe.py does) against the real
Flutter.framework of the pinned SDK (Flutter.xcframework, iOS Simulator
slice, from `flutter precache --ios`), and runs it in an iOS Simulator. The
plugin answers in each state of a launch (idle, launching, running,
stopped) and FlutterStandardMethodCodec encodes each answer into the
success envelope the engine sends to Dart.

The bytes must equal those of test/libretro_session_envelopes.dart, the
file the Dart tests feed to the real MethodChannel: `fixedEnvelopes` for
this tree; with --expect unfixed (and --sources, the bridge tree of Build
453), `build453Envelopes`, the int32 of the defect. Either way a difference
fails the test: it shows that the test tells the two trees apart.

Results go to --evidence (codec.json, the harness output and its build log).
A simulator run is not an iPhone run.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/libretro_internal_bridge/ios'
HARNESS = ROOT / 'test/libretro_channel_codec/main.m'
ENVELOPES = ROOT / 'test/libretro_session_envelopes.dart'
sys.path.insert(0, str(ROOT / 'test'))
from libretro_simulator_probe import (  # noqa: E402
    DEFINES, EXTERNAL_DISPLAY, EXTERNAL_DISPLAY_SOURCES, FRAMEWORKS, TARGET, imports_shader_kit, pick_device,
    sdk_path, cheat_catalog_units)
from libretro_ios_syntax_test import stage_dependency_headers  # noqa: E402
from neo_shader_kit_ios_build import compile_kit, podspec_frameworks  # noqa: E402

FLUTTER_VERSION = '3.47.2'
STATES = ('idle', 'launching', 'running', 'stopped')
# Each state as the harness sets it: (launching, plugin holds a session,
# session's own `active` getter).
STATE_SETUP = {
    'idle': (False, False, False),
    'launching': (True, True, False),
    'running': (False, True, True),
    'stopped': (False, True, False),
}


def envelopes(name):
    """One map of test/libretro_session_envelopes.dart: {state: hex}."""
    text = ENVELOPES.read_text(encoding='utf-8')
    match = re.search(r'const Map<String, String> ' + re.escape(name) + r' = <String, String>\{\n(.*?)\n\};', text,
                      re.S)
    if match is None:
        raise SystemExit(f'{ENVELOPES.relative_to(ROOT)}: no map {name}')
    entries = dict(re.findall(r"^\s*'(\w+)': '([0-9a-f]+)',$", match.group(1), re.M))
    if tuple(entries) != STATES:
        raise SystemExit(f'{name}: states {list(entries)}, expected {list(STATES)}')
    return entries


def flutter_root(argument):
    if argument:
        return Path(argument)
    if os.environ.get('FLUTTER_ROOT'):
        return Path(os.environ['FLUTTER_ROOT'])
    flutter = shutil.which('flutter')
    if flutter is None:
        raise SystemExit('Flutter not found: pass --flutter-root or put flutter on PATH')
    return Path(flutter).resolve().parent.parent


def simulator_slice(root):
    """Folder holding the iOS Simulator Flutter.framework, and the SDK identity."""
    version = json.loads((root / 'bin/cache/flutter.version.json').read_text())
    if version.get('frameworkVersion') != FLUTTER_VERSION:
        raise SystemExit(f"Flutter {version.get('frameworkVersion')} at {root}, expected {FLUTTER_VERSION}")
    xcframework = root / 'bin/cache/artifacts/engine/ios/Flutter.xcframework'
    slices = sorted(path for path in xcframework.glob('ios-*simulator*') if (path / 'Flutter.framework/Flutter').is_file())
    if not slices:
        raise SystemExit(f'No iOS Simulator Flutter.framework under {xcframework} (run flutter precache --ios)')
    identity = {'frameworkVersion': version['frameworkVersion'], 'engineRevision': version.get('engineRevision'),
                'slice': slices[0].name}
    return slices[0], identity


def build(sources, flutter_slice, sdk, work, log):
    include = stage_dependency_headers(work)
    includes = [sources / 'Classes', sources / 'ThirdParty/include', sources / 'ThirdParty/include/libretro',
                sources / 'ThirdParty/rcheevos/include', sources / 'ThirdParty/rcheevos/src', include]
    base = ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', TARGET, '-isysroot', sdk, '-O1',
            '-Wno-deprecated-declarations', '-F', str(flutter_slice)]
    for path in includes:
        base += ['-I', str(path)]
    for define in DEFINES:
        base += ['-D', define]
    # Every bridge source, the plugin included (the probe leaves it out: it
    # has no Flutter.framework).
    units = sorted((sources / 'Classes').glob('*.m'))
    from libretro_ios_syntax_test import achievement_boundary_units
    units += achievement_boundary_units(sources)
    units += cheat_catalog_units(sources)
    if not any(unit.name == 'LibretroInternalBridgePlugin.m' for unit in units):
        raise SystemExit(f'{sources}: no LibretroInternalBridgePlugin.m')
    units += [EXTERNAL_DISPLAY / name for name in EXTERNAL_DISPLAY_SOURCES]
    units += sorted((sources / 'ThirdParty/rcheevos/src').rglob('*.c'))
    units.append(HARNESS)

    def compile_unit(index_unit):
        index, unit = index_unit
        target = work / f'{index:03d}_{unit.stem}.o'
        arguments = list(base)
        if unit.suffix == '.m':
            arguments += ['-fobjc-arc', '-fmodules']
        result = subprocess.run(arguments + ['-c', str(unit), '-o', str(target)], capture_output=True, text=True)
        return unit, target, result

    objects, failed = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
        for unit, target, result in pool.map(compile_unit, enumerate(units)):
            if result.stderr.strip():
                log.write(f'--- {unit}\n{result.stderr}\n')
            if result.returncode != 0:
                print(result.stderr, flush=True)
                failed.append(str(unit))
            objects.append(target)
    if failed:
        raise SystemExit('simulator compilation failed: ' + ', '.join(failed))
    print(f'compiled {len(units)} sources for the simulator against {flutter_slice}', flush=True)
    frameworks = list(FRAMEWORKS)
    libraries = ['-lz']
    if imports_shader_kit(sources):
        objects += compile_kit('iphonesimulator', TARGET, sdk, work / 'neo_shader_kit', plugin=False,
                               optimization='-O1')
        frameworks += [name for name in podspec_frameworks() if name not in frameworks]
        libraries.append('-lc++')
    executable = work / 'LibretroChannelCodec'
    link = ['xcrun', '--sdk', 'iphonesimulator', 'clang', '-target', TARGET, '-isysroot', sdk, '-fobjc-arc',
            *(str(item) for item in objects), '-F', str(flutter_slice), '-framework', 'Flutter']
    for framework in frameworks:
        link += ['-framework', framework]
    # Flutter.framework is loaded from the SDK's own slice (@rpath).
    link += [*libraries, '-Wl,-rpath,' + str(flutter_slice), '-o', str(executable)]
    result = subprocess.run(link, capture_output=True, text=True)
    log.write(f'--- link\n{result.stdout}\n{result.stderr}\n')
    if result.returncode != 0:
        print(result.stderr, flush=True)
        raise SystemExit('link of the codec harness failed')
    subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(executable)], check=True,
                   capture_output=True)
    return executable


def device_state(udid):
    listing = json.loads(subprocess.run(['xcrun', 'simctl', 'list', 'devices', '--json'], check=True,
                                        capture_output=True, text=True).stdout)
    for devices in listing['devices'].values():
        for device in devices:
            if device['udid'] == udid:
                return device.get('state')
    return None


def run_harness(executable, device, evidence):
    udid = device or pick_device()[0]
    booted_here = device_state(udid) != 'Booted'
    if booted_here:
        subprocess.run(['xcrun', 'simctl', 'boot', udid], capture_output=True)
        subprocess.run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], check=True, capture_output=True, timeout=600)
    try:
        started = time.monotonic()
        result = subprocess.run(['xcrun', 'simctl', 'spawn', udid, str(executable)], capture_output=True, text=True,
                                timeout=300)
        seconds = round(time.monotonic() - started, 1)
    finally:
        if booted_here:
            subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    (evidence / 'harness-stdout.txt').write_text(result.stdout)
    (evidence / 'harness-stderr.txt').write_text(result.stderr)
    lines = [line for line in result.stdout.splitlines() if line.startswith('CODEC-RESULT ')]
    if result.returncode != 0 or len(lines) != 1:
        print(result.stdout + result.stderr, flush=True)
        raise SystemExit(f'the codec harness failed in the simulator (exit {result.returncode})')
    report = json.loads(lines[0][len('CODEC-RESULT '):])
    report['simulator'] = udid
    report['seconds'] = seconds
    return report


def check(report, expected, label):
    problems = []
    states = report.get('states', {})
    for state in STATES:
        answer = states.get(state)
        if answer is None:
            problems.append(f'{state}: no answer')
            continue
        launching, has_session, session_active = STATE_SETUP[state]
        actual_setup = (answer.get('launching'), answer.get('hasSession'), answer.get('sessionActive'))
        if actual_setup != (launching, has_session, session_active):
            problems.append(f'{state}: state set as {actual_setup}, expected {(launching, has_session, session_active)}')
        if answer.get('replies') != 1:
            problems.append(f"{state}: {answer.get('replies')} replies, expected exactly one")
        if answer.get('envelope') != expected[state]:
            problems.append(f"{state}: envelope {answer.get('envelope')} ({answer.get('class')}, objCType "
                            f"'{answer.get('objCType')}', CFBoolean {answer.get('cfBoolean')}), expected {expected[state]}")
        print(f"  {state:9} launching={str(launching):5} session={str(has_session):5} active={str(session_active):5} "
              f"-> {answer.get('class')} '{answer.get('objCType')}' CFBoolean={answer.get('cfBoolean')} "
              f"envelope {answer.get('envelope')}", flush=True)
    if problems:
        print(f'\nCodec problems with {label}:', flush=True)
        for problem in problems:
            print('  - ' + problem, flush=True)
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sources', help='libretro bridge ios/ directory (default: this tree)')
    parser.add_argument('--expect', choices=('fixed', 'unfixed'), default='fixed')
    parser.add_argument('--label', default='this tree')
    parser.add_argument('--evidence', default='evidence/libretro-channel-codec')
    parser.add_argument('--flutter-root')
    parser.add_argument('--device', help='simulator UDID (default: the newest available iPhone)')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('The channel codec test runs on macOS (iOS Simulator).')
    expected = envelopes('fixedEnvelopes' if args.expect == 'fixed' else 'build453Envelopes')
    sources = Path(args.sources).resolve() if args.sources else BRIDGE
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    flutter_slice, identity = simulator_slice(flutter_root(args.flutter_root))
    print(f"Flutter {identity['frameworkVersion']} engine {identity['engineRevision']} ({identity['slice']})",
          flush=True)
    with tempfile.TemporaryDirectory(prefix='libretro-codec-') as temporary, \
            open(evidence / 'build.log', 'w') as log:
        executable = build(sources, flutter_slice, sdk_path(), Path(temporary), log)
        report = run_harness(executable, args.device, evidence)
    report.update({'label': args.label, 'sources': str(sources), 'expect': args.expect, 'flutter': identity,
                   'expected': expected})
    print(f"isSessionActive in the simulator ({args.label}, {report['seconds']} s, {report.get('flutterCodec')}):",
          flush=True)
    problems = check(report, expected, args.label)
    report['problems'] = problems
    (evidence / 'codec.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    if problems:
        raise SystemExit(f'{len(problems)} codec problem(s) with {args.label}')
    if args.expect == 'unfixed':
        print(f'REPRODUCED with {args.label}: every answer is an int32, never a Dart bool')
    else:
        print(f'All {len(STATES)} answers of {args.label} are Dart booleans on the wire')


if __name__ == '__main__':
    main()
