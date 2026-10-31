#!/usr/bin/env python3
"""Execute production Swift/ObjC diagnostic writers with Foundation on macOS.

No UIKit, engine or gameplay claim. --require-native refuses a skipped run.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--require-native', action='store_true')
parser.add_argument('--receipt', type=Path)
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
LIBRETRO = ROOT / 'packages/libretro_internal_bridge/ios/Classes'
inputs = [CLASSES / 'MeloNXSessionHost.swift', CLASSES / 'MeloNXStandaloneParity.swift',
          ROOT / 'test/diagnostics_routing/SwiftJournal.swift', Path(__file__),
          LIBRETRO / 'LibretroSessionJournal.m', LIBRETRO / 'LibretroSessionJournal.h',
          ROOT / 'test/libretro_host/frontend/diagnostic_routing_test.m']
if not shutil.which('xcrun'):
    if args.require_native:
        raise SystemExit('Foundation native diagnostics checks require macOS with xcrun')
    print('SKIP actual Foundation diagnostics checks: xcrun unavailable')
    raise SystemExit(0)

def execute(command, timeout=60):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise AssertionError(result.stdout[-12000:] + '\n' + result.stderr[-12000:])
    return result.stdout

with tempfile.TemporaryDirectory(prefix='rewindbox-diagnostics-') as temporary:
    work = Path(temporary)
    host = inputs[0].read_text()
    # The complete production launch writer, without unrelated native FFI.
    launch = host[:host.index('\nenum MeloNXHostError:')]
    parity = inputs[1].read_text()
    hook = '''\nextension MeloNXStdioCapture {
    static func fixtureHoldAppend() { appendLock.lock() }
    static func fixtureReleaseAppend() { appendLock.unlock() }
}\n'''
    production = work / 'Production.swift'
    production.write_text(launch + '\n' + parity + hook)
    shutil.copy2(inputs[2], work / 'main.swift')
    executable = work / 'swift-routing'
    execute(['xcrun', 'swiftc', '-swift-version', '5', production, work / 'main.swift', '-o', executable])
    swift = json.loads(execute([executable, work / 'swift-logs'], timeout=30).strip().splitlines()[-1])
    assert swift['result'] == 'passed' and swift['actualProductionSwift'] and swift['fullPipeConcurrentEnd']
    objc_executable = work / 'libretro-routing'
    execute(['xcrun', 'clang', '-fobjc-arc', '-fblocks', '-O1', '-Wall', '-Werror',
             '-I', LIBRETRO, inputs[4], inputs[6], '-framework', 'Foundation', '-o', objc_executable])
    objc_text = execute([objc_executable, work / 'libretro-logs'])
    count = re.search(r'^PASS (\d+) native journal routing checks;', objc_text, re.MULTILINE)
    assert count, objc_text
    objc = dict(result='passed', checks=int(count.group(1)), actualProductionObjC=True)
    receipt = dict(result='passed', actualFoundation=True, gameplayTested=False,
                   swift=swift, libretro=objc,
                   inputs={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
