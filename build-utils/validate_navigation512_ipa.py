"""Check the final signed IPA links the tested direct playlist and header UI."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import zipfile
from ipa_extension_versions import validate_extension_versions

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('ipa', type=Path)
parser.add_argument('--build-number', type=int, default=512)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
with zipfile.ZipFile(args.ipa) as z:
    roots = [n.removesuffix('Info.plist') for n in z.namelist()
        if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist')]
    assert len(roots) == 1
    root = roots[0]
    info = plistlib.loads(z.read(root + 'Info.plist'))
    assert str(info['CFBundleVersion']) == str(args.build_number)
    version = re.search(r'^version:\s*(\S+)', (ROOT / 'pubspec.yaml').read_text(), re.M).group(1).split('+')[0]
    assert info['CFBundleShortVersionString'] == version
    dart = z.read(root + 'Frameworks/App.framework/App')
    for marker in [b'switch-playlist-empty', b'header-controls', b'header-status',
        b'tabs-container', b'melonx-import-menu', b'main-menu-capsule-pulse',
        b'console-cover-flow-scroll']:
        assert marker in dart, 'Missing linked interface: ' + repr(marker)
    extension_count = validate_extension_versions(z, root, args.build_number)
record = {'result': 'passed', 'build': args.build_number, 'version': version,
    'ipaSHA256': hashlib.sha256(args.ipa.read_bytes()).hexdigest(),
    'directSwitchPlaylistAndImportLinked': True,
    'measuredLiquidGlassHeaderLinked': True, 'completeMotionAndCoverFlowRetained': True,
    'appAndExtensionVersionsAligned': True, 'alignedExtensionCount': extension_count, 'physicalDeviceTested': False}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(record, indent=2) + '\n')
print('PASS final signed IPA: direct Switch playlist, import and compact Liquid Glass header linked.')
