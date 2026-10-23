"""Verify the compiled Switch cleanup/deletion fix in the signed Build 509."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
from melonxdelete509_delivery import PRODUCT, DELIVERED, DELIVERED_RUN

RECEIPT = 'MeloNX-delete509-identity.json'
MARKERS = [b'retired_switch_reference_removed', b'MeloNX retirement:',
           b'deleteRetiredConfirm', b'deleteMixedConfirm']


def identity(build):
    return {'build': str(build), 'baseline': DELIVERED, 'baselineRun': DELIVERED_RUN,
        'productInputSHA256': {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(PRODUCT)},
        'retiredReferencesPurged': True, 'localGameDeletionRetained': True,
        'physicalDeviceTested': False}


def check_compiled(data):
    for marker in MARKERS:
        assert marker in data, 'Missing compiled deletion fix: ' + marker.decode()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('ipa', type=Path, nargs='?')
    p.add_argument('--embed', type=Path)
    p.add_argument('--build-number', default='509')
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    expected = identity(args.build_number)
    if args.embed:
        assert not args.ipa
        check_compiled((args.embed/'Frameworks/App.framework/App').read_bytes())
        (args.embed/RECEIPT).write_text(json.dumps(expected,indent=2)+'\n')
    else:
        assert args.ipa
        with zipfile.ZipFile(args.ipa) as z:
            roots = [n.removesuffix('Info.plist') for n in z.namelist()
                if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist')]
            assert len(roots) == 1
            root = roots[0]
            assert str(plistlib.loads(z.read(root+'Info.plist'))['CFBundleVersion']) == args.build_number
            assert json.loads(z.read(root+RECEIPT)) == expected
            check_compiled(z.read(root+'Frameworks/App.framework/App'))
    record = {'result':'passed', **expected}
    if args.ipa:
        record['ipaSHA256'] = hashlib.sha256(args.ipa.read_bytes()).hexdigest()
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
