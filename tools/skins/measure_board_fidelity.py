#!/usr/bin/env python3
"""Fidelity of the board Originals (tools/skins/build_pocket_board_originals.py): pack preview brought back to the board's own scale vs the board crop, outside the
areas removed on purpose (status band, game window, island, home bar)."""
import sys, json; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from PIL import Image
import numpy as np
import build_pocket_board_originals as b
import check_board_inputs as ci
# optional: the folder of the maintainer's original PNGs (compare against them directly)
TARGETS = sys.argv[1] if len(sys.argv) > 1 else None
out = {'target': 'maintainer original PNGs' if TARGETS else 'repository boards'}
# PS2: docs/design/pocket/approved-ps2.png is the approved maquette itself (byte copy,
# SHA-256 e37c95a5...), so it is always the target.
for console, pid, board in (('gc', 'gamecube-pocket-original', 'approved-gamecube.png'), ('wii', 'wii-pocket-original', 'approved-wii.png'),
                            ('ps2', 'ps2-pocket-original', 'approved-ps2.png')):
    B = ci.target_board(console, TARGETS) if TARGETS and console != 'ps2' else Image.open('docs/design/pocket/' + board).convert('RGB')
    for o in ('portrait', 'landscape'):
        spec = b.PACKS[console][o]; c = spec['crop']; t = B.crop(c)
        p = Image.open(f'assets/skins/pocket/{pid}-{o}.png').convert('RGB').resize(t.size, Image.Resampling.LANCZOS)
        A = np.asarray(t, float); P = np.asarray(p, float); mask = np.ones(A.shape[:2], bool)
        def cut(r):
            x0, y0, x1, y1 = r; mask[max(0, y0-c[1]-3):y1-c[1]+3, max(0, x0-c[0]-3):x1-c[0]+3] = False
        cut(spec['window'])
        for r in (spec.get('erase') or []) + (spec.get('erase_rows') or []) + (spec.get('erase_fill') or []): cut(r)
        for paste in spec.get('paste') or []:  # a control added on purpose (PS2 landscape Menu)
            (tx, ty), r = paste['to'], paste['from'][2] * 1.2
            cut((round(tx - r), round(ty - r), round(tx + r), round(ty + r)))
        if spec.get('black_above'): mask[:spec['black_above']-c[1]+3, :] = False
        mse = ((A-P)[mask]**2).mean()
        g = lambda X: np.hypot(*np.gradient(np.asarray(Image.fromarray(X.astype('uint8')).convert('L'), float)))[mask].mean()
        out[f'{pid}/{o}'] = {'comparedPixels': int(mask.sum()), 'meanAbsDiff': round(float(np.abs(A-P)[mask].mean()), 2),
                             'psnrDb': round(float(10*np.log10(255**2/mse)), 1), 'gradientRatioPackOverBoard': round(float(g(P)/g(A)), 3)}
print(json.dumps(out, indent=1))
