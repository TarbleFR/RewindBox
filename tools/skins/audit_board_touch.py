#!/usr/bin/env python3
"""Before/after audit of the touch defects reported on the GameCube/Wii Pocket Originals.

Usage (repository root):
  python3 tools/skins/audit_board_touch.py BEFORE_DIR AFTER_DIR [--output report.json]
Each DIR holds gamecube-pocket-original.manicskin and wii-pocket-original.manicskin.

Ground truth is the control outlines cut from the approved boards (the alpha of the AFTER
sprites, verified by verify_pocket_skins.py). For each archive it measures, with
DOLSkinOverlay's own hit test (DOLSkinHitTest.h, run through the input-chain test's
mirror that is proven equal to it):
- misrouted: share of each control's drawn points that the touch sends to another control;
- pressed box: share of the pressed sprite's rectangle border that changes when it is
  composited over the background (a lit/dark box around the control: the "carreaux");
- cap offset: distance between the stick's touch/cap centre and the board's cap centre.
"""
import argparse, importlib.util, io, json, sys, zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pocket_board_originals as b  # noqa: E402

spec = importlib.util.spec_from_file_location('chain', ROOT / 'test/pocket_skin_input_chain_test.py')
chain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)


def load(path):
    z = zipfile.ZipFile(path)
    return json.loads(z.read('info.json')), {n: z.read(n) for n in z.namelist() if n.endswith('.png')}


def name_of(item):
    if isinstance(item['inputs'], list): return item['inputs'][0]
    if 'thumbstick' in item:
        return 'mainStick' if item['inputs']['up'].startswith('left') else 'cStick'
    return 'dpad'


def audit(before_dir, after_dir):
    report = {}
    for console, pack in b.PACKS.items():
        if console not in ('gc', 'wii'): continue  # the GameCube/Wii Originals (main / cstick)
        pid = pack['id']
        old_info, old_png = load(Path(before_dir) / f'{pid}.manicskin')
        new_info, new_png = load(Path(after_dir) / f'{pid}.manicskin')
        for orientation in ('portrait', 'landscape'):
            old = old_info['representations']['iphone']['edgeToEdge'][orientation]
            new = new_info['representations']['iphone']['edgeToEdge'][orientation]
            x0, y0, x1, _ = pack[orientation]['crop']
            k = b.MAPPING_WIDTH[orientation] / (x1 - x0)
            hand = {e[0]: e for e in pack[orientation]['items']}
            rows = {}
            for label, (oi, ni) in enumerate(zip(old['items'], new['items'])):
                name = name_of(ni)
                assert name == name_of(oi), (name, name_of(oi))
                # Ground-truth drawn points of the control (the new sprite's alpha).
                f = chain.rect(ni['frame'])
                amap = chain.alpha_map(new_png[ni['asset']['normal']])
                points = []
                if amap is not None:
                    aw, ah, data = amap
                    for v in range(0, ah, 2):
                        for u in range(0, aw, 2):
                            if data[v * aw + u] >= 128:
                                points.append((f[0] + (u + 0.5) / aw * (f[2] - f[0]), f[1] + (v + 0.5) / ah * (f[3] - f[1])))
                row = {}
                for tag, layout, pngs, item_index in (('before', old, old_png, label), ('after', new, new_png, label)):
                    chain._ALPHA.clear()  # sprite names are the same in both archives
                    got = [chain._mirror(layout['items'], px, py, layout, pngs) for px, py in points]
                    wrong = sum(1 for g in got if g != item_index)
                    row[f'misroutedPercent_{tag}'] = round(100 * wrong / max(1, len(got)), 2)
                    item = layout['items'][item_index]
                    bg = Image.open(io.BytesIO(pngs[layout['assets']['large']])).convert('RGB')
                    s = bg.width / layout['mappingSize']['width']
                    fr = item['frame']
                    box = tuple(round(v * s) for v in (fr['x'], fr['y'], fr['x'] + fr['width'], fr['y'] + fr['height']))
                    under = bg.crop(box).convert('RGBA')
                    pressed = under.copy()
                    pressed.alpha_composite(Image.open(io.BytesIO(pngs[item['asset']['pressed']])).convert('RGBA').resize(under.size))
                    d = np.abs(np.asarray(pressed.convert('RGB')).astype(int) - np.asarray(under.convert('RGB')).astype(int)).sum(axis=2)
                    # Ground-truth outline (the board's control, from the after sprite) on this
                    # frame's pixels, grown by 2 px: a change outside it is a box around the control.
                    truth = Image.new('L', bg.size, 0)
                    nf = ni['frame']
                    nbox = tuple(round(v * s) for v in (nf['x'], nf['y'], nf['x'] + nf['width'], nf['y'] + nf['height']))
                    truth.paste(Image.open(io.BytesIO(new_png[ni['asset']['normal']])).getchannel('A')
                                .resize((nbox[2] - nbox[0], nbox[3] - nbox[1])), nbox[:2])
                    from PIL import ImageFilter
                    truth = np.asarray(truth.filter(ImageFilter.MaxFilter(5)).crop(box)) > 0
                    outside = ~truth
                    row[f'pressedChangesOutsideOutlinePercent_{tag}'] = round(100 * float((d[outside] > 24).mean()), 2) if outside.any() else 0.0
                    if 'thumbstick' in item:
                        # The moving part's centre on the board: the whole cap measured on
                        # the board when the pack declares one (GameCube/Wii), else the hand cap.
                        spec_entry = hand[{'leftThumbstickUp': 'main', 'rightThumbstickUp': 'cstick'}[item['inputs']['up']]]
                        cx, cy = (spec_entry[4] if len(spec_entry) > 4 else spec_entry[3])[:2]
                        bx, by = (cx - x0) * k, (cy - y0) * k
                        tx, ty = fr['x'] + fr['width'] / 2, fr['y'] + fr['height'] / 2
                        row[f'capOffsetFromBoardPoints_{tag}'] = round(float(np.hypot(tx - bx, ty - by)), 2)
                        row[f'travelPoints_{tag}'] = round((fr['width'] - item['thumbstick']['width']) / 2, 2)
                        row[f'fullDeflectionRadiusPoints_{tag}'] = round(fr['width'] / 2, 2)
                rows[name] = row
            report[f'{pid}/{orientation}'] = rows
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before'); parser.add_argument('after')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit(args.before, args.after)
    text = json.dumps(report, indent=1) + '\n'
    if args.output: args.output.write_text(text)
    for layout, rows in report.items():
        print(layout)
        for name, row in rows.items():
            print('  %-6s' % name, ' '.join(f'{k}={v}' for k, v in row.items()))


if __name__ == '__main__':
    main()
