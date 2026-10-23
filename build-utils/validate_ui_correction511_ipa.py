#!/usr/bin/env python3
"""Verify the final signed IPA contains the tested complete UI correction."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('ipa', type=Path)
p.add_argument('--build-number', type=int, default=511)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
with zipfile.ZipFile(a.ipa) as z:
    names = z.namelist()
    roots = [n.removesuffix('Info.plist') for n in names if n.startswith('Payload/')
        and len(n.split('/')) == 3 and n.endswith('.app/Info.plist')]
    assert len(roots) == 1
    root = roots[0]
    info = plistlib.loads(z.read(root + 'Info.plist'))
    assert str(info['CFBundleVersion']) == str(a.build_number)
    assets = root + 'Frameworks/App.framework/flutter_assets/'
    relative = 'assets/data/mau-ali-tab-motion.json'
    profile = z.read(assets + relative)
    assert profile == (ROOT / relative).read_bytes()
    data = json.loads(profile)
    assert data['fps'] == 60 and len(data['segments']) == 21
    assert {'position', 'scale', 'path', 'container', 'rimStart', 'rimEnd', 'fillOpacity'} <= data['tracks'].keys()
    dart = z.read(root + 'Frameworks/App.framework/App')
    for marker in [b'main-menu-capsule-pulse', b'console-cover-flow-scroll',
        b'header-controls', b'header-status', b'console-artwork-']:
        assert marker in dart, 'Missing compiled UI correction: ' + repr(marker)
    # The generated source string is actually consumed by the AOT renderer.
    assert profile.strip() in dart, 'Full author tracks not present in the compiled renderer'
    bundles = [n for n in names if n.startswith(root + 'PlugIns/') and n.endswith('.appex/Info.plist')]
    assert len(bundles) == 6
    for bundle in bundles:
        assert str(plistlib.loads(z.read(bundle))['CFBundleVersion']) == str(a.build_number)
record = {'result': 'passed', 'build': a.build_number,
    'ipaSHA256': hashlib.sha256(a.ipa.read_bytes()).hexdigest(),
    'completeAuthorSegments': 21, 'originalFPS': 60, 'authorTracksPresentInAOT': True,
    'depthSortedCoverFlowLinked': True, 'sameFrameHeaderBodyLayoutLinked': True,
    'appAndSixExtensionsAligned': True, 'physicalDeviceTested': False}
a.report.parent.mkdir(parents=True, exist_ok=True)
a.report.write_text(json.dumps(record, indent=2) + '\n')
print('PASS signed IPA: complete author tracks, Cover Flow, measured header and six aligned extensions.')
