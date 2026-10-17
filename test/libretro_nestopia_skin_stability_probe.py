#!/usr/bin/env python3
"""100 real Nestopia sessions plus a negative 469 renderer/view reproduction.

This is a CI-only iPhone Simulator integration test: no commercial ROMs,
no author artwork in the shipping IPA, no physical iPhone claim.
It verifies the same production LibretroSession, real Nestopia, UIKit layer
renderer, emulation thread, close and relaunch. A process death is a failure.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

import libretro_simulator_probe as probe
import libretro_skin_press_probe as press

ORIGINAL_ID = '2cb17f0364a285dd'
ORIGINAL_GIT_BLOB = 'fb718dd0e9d7af717fcb5ca9123818b7acc22566'
ORIGINAL_URL = ('https://raw.githubusercontent.com/delta-skins/'
                'delta-skins.github.io/master/nes/NESThumbstick.deltaskin')
SECONDARY = 'press-complex'


def original_skin(app):
    request = urllib.request.Request(ORIGINAL_URL,
                                     headers={'User-Agent': 'NeoStation-Nestopia-Regression-CI'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(50 * 1024 * 1024 + 1)
    if not data or len(data) > 50 * 1024 * 1024:
        raise ValueError('Original NESThumbstick exceeds test fixture limit')
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != ORIGINAL_GIT_BLOB:
        raise ValueError('Original NESThumbstick upstream Git blob changed: ' + actual)
    folder = app / 'SkinFixtures' / ORIGINAL_ID
    folder.mkdir(parents=True)
    with zipfile.ZipFile(BytesIO(data)) as archive:
        for info in archive.infolist():
            name = Path(info.filename)
            if name.is_absolute() or '..' in name.parts or info.is_dir() and len(name.parts) > 6:
                raise ValueError('Unsafe original skin archive entry')
            if info.file_size > 64 * 1024 * 1024:
                raise ValueError('Original skin resource too large')
        archive.extractall(folder)
    if not (folder / 'info.json').is_file():
        raise ValueError('Original skin has no info.json')
    (folder / 'neostation-skin.json').write_text(json.dumps({
        'id': ORIGINAL_ID, 'consoles': ['nes'],
        'name': 'NESThumbstick (original delta-skins)', 'source': ORIGINAL_URL,
        'sha256': hashlib.sha256(data).hexdigest(),
    }, indent=2))
    return {'upstreamGitBlob': actual, 'archiveSha256': hashlib.sha256(data).hexdigest()}


def make_roms(app):
    content = app / 'content'
    for number, name in ((0xEA, 'nes-skin-loop-a.nes'), (0x18, 'nes-skin-loop-b.nes')):
        rom = bytearray([0xEA] * 16384)
        rom[:4] = bytes.fromhex('78 4c 01 80')  # SEI, JMP $8001
        if number == 0x18:
            # A distinct CPU/RAM workload, rather than an unused-byte change.
            rom[:7] = bytes.fromhex('78 e6 00 4c 01 80 ea')  # SEI; INC $00; JMP $8001
        rom[0x20] = number
        rom[-6:] = bytes.fromhex('01 80 00 80 01 80')
        (content / name).write_bytes(b'NES\x1a\x01\x01' + bytes(10) + rom + bytes(8192))
    # The second variant is also loaded from an actual ZIP like the report.
    with zipfile.ZipFile(content / 'nes-skin-loop-b.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.write(content / 'nes-skin-loop-b.nes', 'nes-skin-loop-b.nes')


def scenarios():
    names = ['nes-skin-loop-a.nes', 'nes-skin-loop-b.nes', 'nes-skin-loop-b.zip']
    tests = []
    for index in range(80):
        tests.append({'name':f'nestopia-original-{index + 1:02d}',
                      'core':'nestopia', 'console':'nes', 'content':'content/' + names[index % 3],
                      'skinSelection':ORIGINAL_ID, 'expect':'run', 'runSeconds':1.0,
                      'lifetimeProbe':index == 0, 'stabilityActions':1 <= index <= 5})
    for index in range(10):
        tests.append({'name':f'nestopia-default-{index + 1:02d}',
                      'core':'nestopia','console':'nes', 'content':'content/' + names[index % 2],
                      'skinSelection':'default','expect':'run','runSeconds':1.0})
    for index in range(8):
        tests.append({'name':f'nestopia-other-catalogue-{index + 1:02d}',
                      'core':'nestopia','console':'nes', 'content':'content/' + names[index % 3],
                      'skinSelection':SECONDARY,'expect':'run','runSeconds':1.0})
    # Return to the exact original skin after using another catalogue.
    for seconds in (10, 30):
      tests.append({'name':f'nestopia-original-restored-{seconds}s','core':'nestopia','console':'nes',
                  'content':'content/nes-skin-loop-a.nes',
                  'skinSelection':ORIGINAL_ID,'expect':'run','runSeconds':seconds})
    return tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('cores','inputs','evidence','label'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--baseline', action='store_true', help='reproduce only the terminal-lifetime defects using original 469 renderer/view bodies')
    parser.add_argument('--asan', action='store_true', help='instrument bridge/probe CPU memory access, 12 focused sessions')
    args = parser.parse_args()
    args.sources = None
    args.only = []
    args.lot1 = args.lot2 = args.official_shaders = False
    probe.REAL_CORES = ('nestopia',)
    probe.SCENARIOS = scenarios()
    if args.baseline:
        probe.SCENARIOS = [{**probe.SCENARIOS[0], 'lifetimeBaseline': True}]
    elif args.asan:
        all_tests = probe.SCENARIOS
        probe.SCENARIOS = all_tests[:6] + all_tests[80:83] + all_tests[90:93]
        os.environ['NEOSTATION_SIMULATOR_ASAN'] = '1'
        os.environ['SIMCTL_CHILD_ASAN_OPTIONS'] = 'detect_leaks=0:abort_on_error=1'
    output = Path(args.evidence)
    output.mkdir(parents=True, exist_ok=True)
    # Choose a notched iPhone instead of the default alphabetic iPhone SE:
    # the reported failure uses the author's edge-to-edge landscape layout.
    def pick_notched_iphone():
        listing = json.loads(probe.output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
        candidates = [(runtime, device['name'], device['udid'])
                      for runtime, devices in listing['devices'].items()
                      for device in devices if device.get('isAvailable') and device['name'].startswith('iPhone')]
        notched = [x for x in candidates if 'SE' not in x[1] and 'Pro' in x[1]]
        if not notched:
            raise RuntimeError('No notched iPhone Simulator is available for edgeToEdge fixture')
        runtime, name, udid = sorted(notched, reverse=True)[0]
        print(f'notched iPhone Simulator: {name} ({runtime}, {udid})', flush=True)
        return udid, name + ' ' + runtime
    probe.pick_device = pick_notched_iphone
    with tempfile.TemporaryDirectory(prefix='nestopia-skin-stability-') as temporary:
        sources = probe.BRIDGE
        if args.baseline:
            sources = Path(temporary) / 'baseline'
            shutil.copytree(probe.BRIDGE, sources)
            for name in ('LibretroSkinRenderer.m', 'LibretroGameViewController.m'):
                path = 'packages/libretro_internal_bridge/ios/Classes/' + name
                (sources / 'Classes' / name).write_bytes(subprocess.check_output([
                    'git', 'show', '69f2194acb415a4d68f7898428d42262ab2149da:' + path]))
        app, tests = probe.assemble(args, sources, Path(temporary))
        config_file = app / 'probe-config.json'
        config = json.loads(config_file.read_text())
        config['forceLandscape'] = True
        config_file.write_text(json.dumps(config, indent=2))
        skin_data = original_skin(app)
        press.REFERENCES = tuple(item for item in press.REFERENCES if item[0] == SECONDARY)
        press.fixtures(app)
        make_roms(app)
        probe.run(['codesign','--force','--sign','-','--timestamp=none',app])
        # 100 sessions in one actual process: detects repeated core create/unload,
        # asynchronous skin/image callbacks and replacements without faking launches.
        result = probe.run_in_simulator(app, output, 1500)
        cold_evidence, cold_failures = [], []
        if result['finished'] and not args.baseline and not args.asan:
            os.environ['SIMCTL_CHILD_NEOSTATION_COLD_LAUNCH'] = '1'
            try:
                for index in range(10):
                    cold_dir = output / f'cold-{index+1:02d}'
                    cold_dir.mkdir()
                    outcome = probe.run_in_simulator(app, cold_dir, 180, reset=False)
                    cold_report = cold_dir / 'probe.json'
                    payload = json.loads(cold_report.read_text()) if cold_report.exists() else {'results': []}
                    errors = probe.evaluate(payload, [tests[0]])
                    if not outcome['finished']: errors.append('process did not finish')
                    rows = payload.get('results', [])
                    journal = rows[0].get('journal', '') if len(rows) == 1 else ''
                    checks = rows[0].get('lifetimeChecks', []) if len(rows) == 1 else []
                    if len(checks) != 3 or any(not c.get('passed') for c in checks):
                        errors.append('terminal/deallocation checks failed or missing')
                    for marker in (f'"event":"active","identifier":"{ORIGINAL_ID}"',
                                   '"orientation":"landscape"', '"display":"edgeToEdge"',
                                   'video: frame=1 begin', 'metal: completed status=4'):
                        if marker not in journal: errors.append('missing ' + marker)
                    pid = re.search(r'\bpid=(\d+)\b', journal)
                    session = re.search(r'\bsession=([A-Fa-f0-9-]{36})\b', journal)
                    if not pid or not session: errors.append('process/session identity missing')
                    cold_evidence.append({'launch': index+1, 'pid': pid.group(1) if pid else None,
                                          'session': session.group(1) if session else None,
                                          'finished': outcome['finished'], 'failures': errors})
                    cold_failures.extend(f'cold-{index+1:02d}: {error}' for error in errors)
                    if errors: break
            finally:
                os.environ.pop('SIMCTL_CHILD_NEOSTATION_COLD_LAUNCH', None)
    report_path = output / ('probe.json' if (output/'probe.json').exists() else 'probe-partial.json')
    report = json.loads(report_path.read_text()) if report_path.exists() else {'results': []}
    failures = probe.evaluate(report, tests)
    failures.extend(cold_failures)
    if not result['finished']:
        failures.append(f'Simulator process did not finish all {len(tests)} sessions')
    for record in report.get('results', []):
        name = record['name']
        expected = ORIGINAL_ID if name.startswith('nestopia-original') else (
            SECONDARY if 'other-catalogue' in name else None)
        journal = record.get('journal', '')
        for check in record.get('lifetimeChecks', []):
            if not check.get('passed'): failures.append(f'{name}: ' + check['name'])
        if name == 'nestopia-original-01' and len(record.get('lifetimeChecks', [])) != 3:
            failures.append(f'{name}: terminal lifetime checks missing')
        scenario = next(s for s in tests if s['name'] == name)
        if scenario.get('stabilityActions') and len(record.get('lifetimeChecks', [])) != 7:
            failures.append(f'{name}: four live switches/rotations, terminal checks and deallocation required')
        if not args.baseline and expected == ORIGINAL_ID:
            for marker in ('session=', 'skin-renderer=', 'video: frame=1 begin', 'pitch=', 'metal: completed status=4'):
                if marker not in journal: failures.append(f'{name}: diagnostic missing {marker}')
        if expected and f'"event":"active","identifier":"{expected}"' not in journal:
            failures.append(f'{name}: expected selected original/cross-catalogue skin did not reach active')
        if expected == ORIGINAL_ID and ('"orientation":"landscape"' not in journal or
                                        '"display":"edgeToEdge"' not in journal):
            failures.append(f'{name}: the original skin was not rendered in landscape edgeToEdge')
        if expected == ORIGINAL_ID and 'skin-load ' not in journal:
            failures.append(f'{name}: no original skin lifecycle diagnostics')
        if expected is None and f'"event":"active","identifier":"{ORIGINAL_ID}"' in journal:
            failures.append(f'{name}: previous custom skin leaked into default selection')
    verdict = {
        'source':args.label,'originalSkin':skin_data,
        'attemptsOriginal':sum(s['skinSelection'] == ORIGINAL_ID for s in tests),
        'attemptsWithoutSkin':sum(s['skinSelection'] == 'default' for s in tests),
        'attemptsOtherCatalogue':sum(s['skinSelection'] == SECONDARY for s in tests),
        'baseline469Bodies':args.baseline,
        'addressSanitizer':args.asan,
        'prebuiltCoreInstrumented':False,
        'coldProcesses':len(cold_evidence), 'coldProcessEvidence':cold_evidence,
        'checks':sum(len(r.get('lifetimeChecks', [])) for r in report.get('results', [])),
        'allSessionsClosed':result['finished'],'failures':failures,
        'physicalDeviceValidated':False,'commercialROMUsed':False,
        'simulator':result.get('simulator'),
    }
    (output/'skin-stability-verdict.json').write_text(json.dumps(verdict,indent=2))
    (output/'run-outcome.json').write_text(json.dumps(result,indent=2))
    if failures:
        for failure in failures: print('FAILED:',failure,flush=True)
        for line in probe.crash_summary(output): print('CRASH:',line,flush=True)
        raise SystemExit(f'{len(failures)} distinct stability failures')
    print('PASS:', len(tests), 'real Nestopia sessions;', verdict, flush=True)


if __name__ == '__main__':
    main()
