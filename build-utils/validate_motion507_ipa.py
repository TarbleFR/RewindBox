#!/usr/bin/env python3
"""Inspect the final signed IPA for the actual motion assets and linked views."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import zipfile
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser();p.add_argument('ipa', type=Path);p.add_argument('--report',type=Path,required=True)
a = p.parse_args()
with zipfile.ZipFile(a.ipa) as z:
    names = z.namelist();assert len(names)==len(set(names)), 'Duplicate ZIP entries'
    info = [n for n in names if len(PurePosixPath(n).parts)==3 and n.startswith('Payload/') and n.endswith('.app/Info.plist')]
    assert len(info)==1, info
    prefix = info[0].removesuffix('Info.plist')
    main = plistlib.loads(z.read(info[0])); assert str(main['CFBundleVersion'])=='507', main
    assets = prefix+'Frameworks/App.framework/flutter_assets/'
    digests = {}
    for relative in ['assets/data/mau-ali-tab-menu.lottie','assets/data/mau-ali-tab-motion.json',
                     'assets/legal/Lottie-Simple-License.txt','assets/legal/Mau-Ali-Tab-Motion.txt']:
        data = z.read(assets+relative);assert data==(ROOT/relative).read_bytes(), relative
        digests[relative]=hashlib.sha256(data).hexdigest()
    for name in ['Lottie-Simple-License.txt','Mau-Ali-Tab-Motion.txt']:
        assert z.read(prefix+'Legal/'+name)==(ROOT/'assets/legal'/name).read_bytes(), name
    dart = z.read(prefix+'Frameworks/App.framework/App')
    for token in [b'neostation/ui_refresh_rate/power', b'console-perspective-', b'header-device-battery']:
        assert token in dart, 'Missing compiled Dart component: '+repr(token)
    native = []
    for name in names:
        if name==prefix+main['CFBundleExecutable'] or ('.framework/' in name and name.rsplit('/',1)[-1]==name.rsplit('.framework/',1)[0].rsplit('/',1)[-1]):
            native.append((name,z.read(name)))
    assert any(b'RBLiquidProgressView' in data and b'liquidTick:' in data for _,data in native), 'UIKit liquid view is not linked'
    assert any(b'neostation/ui_refresh_rate/power' in data for _,data in native), 'Native power event channel is not linked'
    extensions=[n for n in names if n.startswith(prefix+'PlugIns/') and n.endswith('.appex/Info.plist')]
    assert len(extensions)==6, extensions
    for name in extensions: assert str(plistlib.loads(z.read(name))['CFBundleVersion'])=='507', name
record={'result':'passed','build':507,'ipaSHA256':hashlib.sha256(a.ipa.read_bytes()).hexdigest(),
        'assets':digests,'nativeLiquidViewLinked':True,'nativePowerChannelLinked':True,
        'compiledDartMotionPresent':True,'appAndSixExtensionVersionsMatched':True,'deviceTested':False}
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(record,indent=2)+'\n')
print('PASS final signed IPA: author asset/profile, full notices, Dart components, UIKit material and power channel.')
