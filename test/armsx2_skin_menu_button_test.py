#!/usr/bin/env python3
"""The ARMSX2 session's floating menu button never covers a PS2 skin control.

Armsx2InternalBridgePlugin.mm draws a 44 pt hamburger 12 pt from the safe area's top
leading corner. Over a visible skin whose current layout has its own Menu control
(ARMSX2SkinOverlay.hasMenuControl; that Menu opens the same session menu) it is hidden,
as Dolphin does (DOLSessionChromePolicy.h); without a visible skin, or over a layout
without Menu, it stays.

On the REAL shipped PS2 archives (catalog-bound), every tall iPhone, both orientations,
native aspect fit: every layout has a Menu (so the button hides), and the previous
always-shown button covered a control of PS2 Pocket — Original (L1 in landscape) — the
defect this guards against. Host geometry plus source wiring, not a UIKit run.
"""
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/armsx2_internal_bridge/ios/Classes'
_spec = importlib.util.spec_from_file_location('chrome', ROOT / 'test/dolphin_session_chrome_test.py')
chrome = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chrome)


def fail(message):
    raise SystemExit('armsx2 skin menu button: ' + message)


def main():
    plugin = (CLASSES / 'Armsx2InternalBridgePlugin.mm').read_text()
    overlay = (CLASSES / 'ARMSX2SkinOverlay.mm').read_text()
    header = (CLASSES / 'ARMSX2SkinOverlay.h').read_text()
    body = re.search(r'- \(void\)syncSkinOverlay \{(.*?)\n\}', plugin, re.S)
    if not body:
        fail('syncSkinOverlay not found')
    if 'self.menuButton.hidden = shown && skin.hasMenuControl;' not in body.group(1):
        fail('syncSkinOverlay does not hide the floating menu over a skin with its own Menu')
    if body.group(1).index('const BOOL shown') > body.group(1).index('self.menuButton.hidden'):
        fail('the menu button is decided before the skin visibility')
    for needle in ('[self.menuButton.leadingAnchor constraintEqualToAnchor:root.safeAreaLayoutGuide.leadingAnchor constant:12]',
                   '[self.menuButton.topAnchor constraintEqualToAnchor:root.safeAreaLayoutGuide.topAnchor constant:12]',
                   '[self.menuButton.widthAnchor constraintEqualToConstant:44]',
                   'skin.menuHandler = ^{ [weakSelf menuPressed]; };'):
        if needle not in plugin:
            fail('production wiring missing: ' + needle)
    if 'property(nonatomic, readonly) BOOL hasMenuControl' not in header or \
            not re.search(r'- \(BOOL\)hasMenuControl \{\s*for \(A2SkinItem\* item in _current\.items\) \{\s*'
                          r'if \(\[item\.inputs containsObject:@"menu"\]\) return YES;', overlay):
        fail('ARMSX2SkinOverlay.hasMenuControl does not read the current layout\'s Menu control')
    catalog = json.loads((ROOT / 'assets/skins/pocket/catalog.json').read_text())
    covered, checked = [], 0
    for row in catalog['skins']:
        if row['console'] != 'ps2':
            continue
        data = (ROOT / row['archiveAsset']).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            fail(row['id'] + ': archive differs from the catalog')
        reps = json.loads(zipfile.ZipFile(ROOT / row['archiveAsset']).read('info.json'))['representations']['iphone']
        layouts = reps.get('edgeToEdge') or reps['standard']
        for orientation in ('portrait', 'landscape'):
            layout = layouts[orientation]
            if not any('menu' in (it['inputs'] if isinstance(it['inputs'], list) else []) for it in layout['items']):
                fail(f"{row['id']}/{orientation}: no Menu control, the floating button would have to stay")
            mapping = (layout['mappingSize']['width'], layout['mappingSize']['height'])
            for phone, inset in chrome.PHONES.items():
                device = phone if orientation == 'portrait' else phone[::-1]
                left, top = (0, inset) if orientation == 'portrait' else (inset, 0)
                button = (left + 12, top + 12, 44, 44)
                for item in layout['items']:
                    f, e = item['frame'], item.get('extendedEdges', {})
                    hit = chrome.fit((f['x'] - e.get('left', 0), f['y'] - e.get('top', 0),
                                      f['width'] + e.get('left', 0) + e.get('right', 0),
                                      f['height'] + e.get('top', 0) + e.get('bottom', 0)), mapping, device)
                    if chrome.overlaps(hit, button):
                        name = item['inputs'][0] if isinstance(item['inputs'], list) else 'stick/dpad'
                        covered.append((row['id'], orientation, phone, name))
                checked += 1
    if not any(c[0] == 'ps2-pocket-original' and c[1] == 'landscape' and c[3] == 'l1' for c in covered):
        fail('expected the always-shown button to cover L1 of PS2 Pocket - Original in landscape: %s' % covered)
    print('armsx2 skin menu button: ok (%d PS2 layouts, each with its own Menu: the floating button hides; '
          'the previous always-shown button covered a control in %d of them)' % (checked, len({c[:3] for c in covered})))
    for entry in sorted(set(covered)):
        print('  previously covered:', *entry)


if __name__ == '__main__':
    sys.exit(main())
