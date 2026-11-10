#!/usr/bin/env python3
"""The Dolphin session's floating menu / performance buttons never cover a skin control.

Compiles the production decision (DOLSessionChromePolicy.h) with the host C compiler
and applies it to the REAL shipped GameCube/Wii Pocket archives (catalog-bound), on
every tall iPhone in both orientations, with the native aspect fit (DOLSkinOverlay)
and the buttons' production geometry (DolphinInternalBridgePlugin.mm: 44 pt, 12 pt
from the safe area's top leading corner, the performance toggle 8 pt after the menu).

It also proves the defect it guards against: with the previous placement, the
floating buttons covered a control (L on the GameCube Original in landscape).
This is a host geometry test, not a UIKit run: the view controller itself is only
compiled in the IPA, so its wiring is checked on its source below.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
# (portrait width, height): safe area insets of edge-to-edge iPhones (portrait top,
# landscape leading/trailing), like tools/skins/verify_pocket_skins.py.
PHONES = {(375, 812): 44, (390, 844): 47, (393, 852): 59, (430, 932): 59}


def fail(message):
    raise SystemExit('dolphin session chrome: ' + message)


def overlaps(a, b):
    return min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) > 0.01 and min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) > 0.01


def inside(a, b):
    return a[0] >= b[0] - 0.01 and a[1] >= b[1] - 0.01 and a[0] + a[2] <= b[0] + b[2] + 0.01 and a[1] + a[3] <= b[1] + b[3] + 0.01


def fit(frame, mapping, device):
    scale = min(device[0] / mapping[0], device[1] / mapping[1])
    dx, dy = (device[0] - mapping[0] * scale) / 2, (device[1] - mapping[1] * scale) / 2
    return (dx + frame[0] * scale, dy + frame[1] * scale, frame[2] * scale, frame[3] * scale)


def main():
    source = (CLASSES / 'DolphinInternalBridgePlugin.mm').read_text()
    if not re.search(r'\[self placeRenderSurface\];\s*\[self placeSessionChrome\];', source):
        fail('syncSkinOverlay does not place the session buttons')
    for needle in ('DOLSessionChromePlace(', 'skin.hasMenuControl', 'menu.hidden = !placement.showMenuButton',
                   'constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:12.0',
                   'constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:12.0',
                   '[performance.leadingAnchor constraintEqualToAnchor:close.trailingAnchor constant:8.0]'):
        if needle not in source:
            fail('production wiring missing: ' + needle)
    if 'item.inputs containsObject:@"menu"' not in (CLASSES / 'DOLSkinOverlay.mm').read_text():
        fail('DOLSkinOverlay.hasMenuControl does not read the Menu control')
    with tempfile.TemporaryDirectory() as work:
        probe = Path(work) / 'probe'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', '-o', str(probe),
                        str(ROOT / 'test/orientation_policy/session_chrome_probe.c')], check=True)

        def place(shown, menu, screen):
            out = subprocess.run([str(probe), str(int(shown)), str(int(menu)), *(f'{v:.4f}' for v in screen)],
                                 check=True, capture_output=True, text=True).stdout.split()
            return bool(int(out[0])), bool(int(out[1])), float(out[2]), float(out[3])

        # decision table
        if place(False, True, (100, 0, 400, 300)) != (True, False, 0.0, 0.0):
            fail('no visible skin must keep both floating buttons')
        if place(True, False, (100, 0, 400, 300))[:2] != (True, True):
            fail('a skin without Menu keeps the floating menu')
        if place(True, True, (100, 20, 400, 300)) != (False, True, 108.0, 28.0):
            fail('a skin with Menu hides the floating menu, performance inside its screen')
        if place(True, True, (0, 0, 50, 50))[:2] != (False, False):
            fail('a screen too small keeps the performance toggle floating')

        catalog = json.loads((ROOT / 'assets/skins/pocket/catalog.json').read_text())
        before, checked = [], 0
        for row in catalog['skins']:
            if row['console'] not in ('gc', 'wii'):
                continue
            data = (ROOT / row['archiveAsset']).read_bytes()
            if hashlib.sha256(data).hexdigest() != row['sha256']:
                fail(row['id'] + ': archive differs from the catalog')
            info = json.loads(zipfile.ZipFile(ROOT / row['archiveAsset']).read('info.json'))
            reps = info['representations']['iphone']
            layouts = reps.get('edgeToEdge') or reps['standard']
            for orientation in ('portrait', 'landscape'):
                layout = layouts[orientation]
                mapping = (layout['mappingSize']['width'], layout['mappingSize']['height'])
                for phone, inset in PHONES.items():
                    device = phone if orientation == 'portrait' else phone[::-1]
                    left, top = (0, inset) if orientation == 'portrait' else (inset, 0)
                    hits = []
                    for item in layout['items']:
                        f, e = item['frame'], item.get('extendedEdges', {})
                        hits.append(fit((f['x'] - e.get('left', 0), f['y'] - e.get('top', 0),
                                         f['width'] + e.get('left', 0) + e.get('right', 0),
                                         f['height'] + e.get('top', 0) + e.get('bottom', 0)), mapping, device))
                    s = layout['screens'][0]['outputFrame']
                    screen = fit((s['x'], s['y'], s['width'], s['height']), mapping, device)
                    old_menu = (left + 12, top + 12, 44, 44)
                    old_perf = (left + 12 + 44 + 8, top + 12, 44, 44)
                    if any(overlaps(h, b) for h in hits for b in (old_menu, old_perf)):
                        before.append((row['id'], orientation, phone))
                    show_menu, in_screen, px, py = place(True, True, screen)
                    tag = f"{row['id']}/{orientation}/{phone}"
                    if show_menu:
                        fail(tag + ': the skin has a Menu, the floating one must hide')
                    if not in_screen:
                        fail(tag + ': performance toggle left floating')
                    perf = (px, py, 44, 44)
                    if not inside(perf, screen):
                        fail(tag + ': performance toggle outside the game screen')
                    if any(overlaps(perf, h) for h in hits):
                        fail(tag + ': performance toggle covers a control')
                    checked += 1
        if ('gamecube-pocket-original', 'landscape', (393, 852)) not in before:
            fail('expected the previous placement to cover L of the GameCube Original: %s' % before)
    print('dolphin session chrome: ok (%d layouts; previous placement covered controls in %d of them)'
          % (checked, len(before)))
    for entry in before:
        print('  previously covered:', *entry)


if __name__ == '__main__':
    sys.exit(main())
