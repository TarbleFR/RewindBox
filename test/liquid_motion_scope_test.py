#!/usr/bin/env python3
"""Close the frontend-only scope before skipping historical engine suites."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
ROOT = Path(__file__).resolve().parents[1]
record = json.loads((ROOT/'test/fixtures/motion507-scope.json').read_text())
changed = set(subprocess.check_output(['git','diff','--name-only',record['baseline'],'HEAD','--',
    'lib','packages','native','assets','ios','pubspec.yaml','pubspec.lock'],cwd=ROOT,text=True).splitlines())
assert changed == set(record['productPaths']), sorted(changed ^ set(record['productPaths']))
protected = ['lib/main.dart','lib/screens/app_screen.dart','lib/utils/nav_tabs.dart',
    'lib/services','lib/repositories','lib/models','lib/providers',
    'lib/widgets/rewind_startup.dart','lib/widgets/rewind_mark_path.dart',
    'lib/widgets/console_bubble_transition.dart', 'native',
    'packages/ui_refresh_rate/ios/Classes/UiRefreshRateEngineHook.m',
    'packages/ui_refresh_rate/ios/Classes/UiRefreshRateEngineHook.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTexturePackStore.mm',
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
    'pubspec.yaml','pubspec.lock']
subprocess.run(['git','diff','--exit-code',record['baseline'],'HEAD','--',*protected],cwd=ROOT,check=True)
profile=json.loads((ROOT/'assets/data/mau-ali-tab-motion.json').read_text())
asset=ROOT/'assets/data/mau-ali-tab-menu.lottie'
assert hashlib.sha256(asset.read_bytes()).hexdigest()==profile['sha256']
with zipfile.ZipFile(asset) as archive:
    scene=json.loads(archive.read('a/Main Scene.json'))
    assert scene['fr']==profile['fps']==60
    assert any(m['cm']=='PnW' and m['dr']==profile['frames'] for m in scene['markers'])
    assert len(json.loads(archive.read('manifest.json'))['stateMachines'])==2
assert 'Mau Ali' in (ROOT/'lib/screens/settings_screen/legal_credits_dialog.dart').read_text()
assert 'Lottie-Simple-License.txt' in (ROOT/'build-utils/embed_legal_bundle.py').read_text()
print('PASS: exact UI scope, startup/engines/services preserved, author asset and licence linked.')
