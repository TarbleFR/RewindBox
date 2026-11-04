#!/usr/bin/env python3
"""Real ARMSX2SkinOverlay renders of PS2 Pocket — Original beside the approved maquette.

Usage (repository root):
  python3 tools/skins/render_real_overlay_comparison.py RENDERS_DIR OUT_DIR

RENDERS_DIR: the `renders/` folder that packages/armsx2_internal_bridge/ci/test_skin_overlay_ui.rb
uploads (UIKit renders of the production overlay in the iOS Simulator, 3x: rest, every
button held, sticks pushed, released). Prints how far the real drawing is from the host
composition of the archive (outside the game window) and writes one sheet per orientation:
maquette useful zone | real overlay at rest | every button held | sticks pushed.
A simulator render is not an iPhone screenshot.
"""
import sys
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image
import build_pocket_board_originals as b, render_touch_evidence as ev
R, OUT = sys.argv[1], sys.argv[2]
info, pngs = ev.load('assets/skins/pocket/ps2-pocket-original.manicskin')
board = Image.open('docs/design/pocket/approved-ps2.png').convert('RGB')
for o in ('portrait', 'landscape'):
    L = info['representations']['iphone']['edgeToEdge'][o]
    real = {s: Image.open(f'{R}/ps2-pocket-original-{o}-{s}.png').convert('RGB') for s in ('rest', 'buttons-pressed', 'sticks-pushed', 'released')}
    host = ev.compose(L, pngs).convert('RGB')
    r = real['rest']
    print(o, 'real', r.size, 'host', host.size)
    h2 = host.resize(r.size, Image.Resampling.LANCZOS)
    d = np.abs(np.asarray(r, float) - np.asarray(h2, float))
    # exclude the game window (black in the real render, board navy in the host one)
    s = L['screens'][0]['outputFrame']; k = r.width / L['mappingSize']['width']
    m = np.ones(d.shape[:2], bool); m[round(s['y']*k)-2:round((s['y']+s['height'])*k)+2, round(s['x']*k)-2:round((s['x']+s['width'])*k)+2] = False
    print('  real rest vs host compose: mean abs', round(float(d[m].mean()), 2), 'p99', round(float(np.percentile(d.max(axis=2)[m], 99)), 1))
    print('  released == rest:', np.array_equal(np.asarray(real['released']), np.asarray(r)))
    ref = board.crop(b.PACKS['ps2'][o]['crop']).resize(r.size, Image.Resampling.LANCZOS)
    dm = np.abs(np.asarray(r, float) - np.asarray(ref, float)).mean(axis=2)
    mm = m.copy()
    print('  real rest vs maquette useful zone (incl. removed island/home bar/status):', round(float(dm[mm].mean()), 2))
    cells = [ref, r, real['buttons-pressed'], real['sticks-pushed']]
    names = ['approved maquette (useful zone)', 'ARMSX2SkinOverlay at rest (simulator)', 'every button held (simulator)', 'sticks pushed (simulator)']
    from PIL import ImageDraw
    if o == 'portrait':
        W = sum(c.width for c in cells) + 30 * 3; H = cells[0].height + 40
        sheet = Image.new('RGB', (W, H), (235, 238, 244)); x = 0
        for c, n in zip(cells, names):
            sheet.paste(c, (x, 40)); ImageDraw.Draw(sheet).text((x + 6, 8), n, fill=(0, 0, 0), font_size=26); x += c.width + 30
    else:
        W = cells[0].width; H = sum(c.height + 40 for c in cells) + 30 * 3
        sheet = Image.new('RGB', (W, H), (235, 238, 244)); y = 0
        for c, n in zip(cells, names):
            ImageDraw.Draw(sheet).text((6, y + 8), n, fill=(0, 0, 0), font_size=26); sheet.paste(c, (0, y + 40)); y += c.height + 70
    sheet.thumbnail((2400, 2400)); sheet.save(f'{OUT}/real-overlay-ps2-{o}.png', optimize=True)
