#!/usr/bin/env python3
"""Compile the registered route-only Swift plugin against the actual iPhone SDK.

This verifies the Swift/Flutter/Apple API boundary, not a Switch session.
"""
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
flutter = Path(shutil.which('flutter')).resolve().parent.parent
subprocess.run(['flutter', 'precache', '--ios'], check=True, cwd=ROOT)
frameworks = flutter / 'bin/cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64'
assert (frameworks / 'Flutter.framework/Flutter').is_file(), frameworks
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
sources = [ROOT / 'packages/stikjit_bridge/ios/Classes' / name for name in
           ['NeoStationStikjitBridgePlugin.swift', 'LocalDevVpnRouteProbe.swift']]
pod = ROOT / 'packages/stikjit_bridge/ios'
spec = (pod / 'stikjit_bridge.podspec').read_text()
excluded = re.findall(r"'([^']+)'", re.search(r's\.exclude_files = \[([^\]]+)\]', spec)[1])
selected = set((pod / 'Classes').glob('*.swift')) - {pod / p for p in excluded}
assert selected == set(sources), selected
subprocess.run(['xcrun', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk,
                '-target', 'arm64-apple-ios18.0', '-F', str(frameworks), *map(str, sources)], check=True, cwd=ROOT)
receipt = {
    'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'swiftInputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    'xcode': subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
    'sdk': subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'], text=True).strip(),
    'flutter': subprocess.check_output(['flutter', '--version', '--machine'], text=True).strip(),
    'iphoneSdkTypecheck': True,
    'switchEngineCompiled': False,
    'gameplayTested': False,
}
out = ROOT / 'build/melonx-retirement-sdk.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print('Registered Swift route plugin: iPhone SDK type-check passed; no Switch engine/gameplay claim.')
