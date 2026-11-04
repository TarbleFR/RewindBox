#!/usr/bin/env python3
"""Touch evidence sheets for the board Originals, before and after the touch fix.

Usage (repository root):
  python3 tools/skins/render_touch_evidence.py BEFORE_DIR AFTER_DIR OUT_DIR

Draws each archive the way DOLSkinOverlay composes it (background, every item sprite in
its frame, the stick cap at knobFrame) and, from DOLSkinOverlay's own hit test
(DOLSkinHitTest.h through the input-chain mirror proven equal to it):
- zones-*.png: every point tinted with the control a touch there reaches, item frames
  outlined, over the rendered skin (where a touch goes vs what is drawn);
- press-*.png: each control at rest / pressed / released, magnified 3x, before and after
  (a box around the pressed control is the reported "carreaux");
- stick-*.png: the cap for the vectors (0,0) (1,0) (0.71,0.71) (0,-1) (-1,0), with the
  touch centre and the full-deflection circle.
Host renders of the archives' own files, not iPhone screenshots.
"""
import colorsys, importlib.util, io, json, sys, zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('chain', ROOT / 'test/pocket_skin_input_chain_test.py')
chain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)
PX = 3  # pixels per mapping point


def load(path):
    z = zipfile.ZipFile(path)
    return json.loads(z.read('info.json')), {n: z.read(n) for n in z.namelist() if n.endswith('.png')}


def compose(layout, pngs, pressed=(), vectors=None):
    W, H = layout['mappingSize']['width'], layout['mappingSize']['height']
    canvas = Image.open(io.BytesIO(pngs[layout['assets']['large']])).convert('RGBA').resize((round(W * PX), round(H * PX)), Image.Resampling.LANCZOS)
    for i, item in enumerate(layout['items']):
        f = item['frame']
        box = (round(f['x'] * PX), round(f['y'] * PX), round((f['x'] + f['width']) * PX), round((f['y'] + f['height']) * PX))
        sprite = Image.open(io.BytesIO(pngs[item['asset']['pressed' if i in pressed else 'normal']])).convert('RGBA')
        canvas.alpha_composite(sprite.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS), box[:2])
        if 'thumbstick' in item:
            k = item['thumbstick']
            vx, vy = (vectors or {}).get(i, (0, 0))
            tx, ty = (f['width'] - k['width']) / 2, (f['height'] - k['height']) / 2
            cx, cy = f['x'] + f['width'] / 2 + vx * tx, f['y'] + f['height'] / 2 + vy * ty
            knob = Image.open(io.BytesIO(pngs[k['name']])).convert('RGBA').resize((round(k['width'] * PX), round(k['height'] * PX)), Image.Resampling.LANCZOS)
            canvas.alpha_composite(knob, (round((cx - k['width'] / 2) * PX), round((cy - k['height'] / 2) * PX)))
    return canvas


def zones(layout, pngs):
    chain._ALPHA.clear()
    W, H = layout['mappingSize']['width'], layout['mappingSize']['height']
    base = compose(layout, pngs)
    n = len(layout['items'])
    colours = [tuple(int(c * 255) for c in colorsys.hsv_to_rgb(i / n, 0.85, 1.0)) for i in range(n)]
    tint = Image.new('RGBA', base.size, (0, 0, 0, 0))
    px = tint.load()
    step = 1 / PX
    for y in range(base.height):
        for x in range(base.width):
            i = chain._mirror(layout['items'], (x + 0.5) * step, (y + 0.5) * step, layout, pngs)
            if i >= 0:
                px[x, y] = colours[i] + (110,)
    base.alpha_composite(tint)
    d = ImageDraw.Draw(base)
    for i, item in enumerate(layout['items']):
        f = item['frame']
        d.rectangle((f['x'] * PX, f['y'] * PX, (f['x'] + f['width']) * PX, (f['y'] + f['height']) * PX), outline=colours[i] + (255,), width=2)
    return base


def label(img, text):
    out = Image.new('RGBA', (img.width, img.height + 26), (235, 238, 244, 255))
    out.paste(img, (0, 26))
    ImageDraw.Draw(out).text((4, 4), text, fill=(0, 0, 0, 255), font_size=18)
    return out


def press_sheet(layout_before, png_before, layout_after, png_after):
    rows = []
    for i, (ib, ia) in enumerate(zip(layout_before['items'], layout_after['items'])):
        if not isinstance(ia['inputs'], list): continue
        cells = []
        for tag, layout, pngs, item in (('before', layout_before, png_before, ib), ('after', layout_after, png_after, ia)):
            f = item['frame']
            pad = 6
            box = (round((f['x'] - pad) * PX), round((f['y'] - pad) * PX), round((f['x'] + f['width'] + pad) * PX), round((f['y'] + f['height'] + pad) * PX))
            for state, pressed in (('rest', ()), ('pressed', (i,)), ('released', ())):
                crop = compose(layout, pngs, pressed).crop(box)
                cells.append(label(crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.NEAREST), f'{tag} {state}'))
        h = max(c.height for c in cells)
        row = Image.new('RGBA', (sum(c.width for c in cells) + 10 * len(cells), h + 30), (255, 255, 255, 255))
        ImageDraw.Draw(row).text((4, 4), ' / '.join(ia['inputs']), fill=(0, 0, 0, 255), font_size=22)
        x = 0
        for c in cells:
            row.paste(c, (x, 30)); x += c.width + 10
        rows.append(row)
    sheet = Image.new('RGBA', (max(r.width for r in rows), sum(r.height for r in rows)), (255, 255, 255, 255))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y)); y += r.height
    return sheet


def stick_sheet(layout, pngs, tag):
    cells = []
    for i, item in enumerate(layout['items']):
        if 'thumbstick' not in item: continue
        f = item['frame']
        pad = 14
        box = (round((f['x'] - pad) * PX), round((f['y'] - pad) * PX), round((f['x'] + f['width'] + pad) * PX), round((f['y'] + f['height'] + pad) * PX))
        for v in ((0, 0), (1, 0), (0.7071, 0.7071), (0, -1), (-1, 0)):
            img = compose(layout, pngs, (i,) if v != (0, 0) else (), {i: v}).crop(box)
            d = ImageDraw.Draw(img)
            cx, cy = (f['width'] / 2 + pad) * PX, (f['height'] / 2 + pad) * PX
            r = f['width'] / 2 * PX
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 0, 120, 255), width=2)
            d.line((cx - 8, cy, cx + 8, cy), fill=(255, 0, 120, 255), width=2)
            d.line((cx, cy - 8, cx, cy + 8), fill=(255, 0, 120, 255), width=2)
            cells.append(label(img, f'{tag} {item["inputs"]["up"][:-7]} v={v}'))
    sheet = Image.new('RGBA', (sum(c.width for c in cells) + 8 * len(cells), max(c.height for c in cells)), (255, 255, 255, 255))
    x = 0
    for c in cells:
        sheet.paste(c, (x, 0)); x += c.width + 8
    return sheet


def main():
    before, after, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    for pid, short in (('gamecube-pocket-original', 'gamecube'), ('wii-pocket-original', 'wii')):
        ib, pb = load(before / f'{pid}.manicskin')
        ia, pa = load(after / f'{pid}.manicskin')
        for o in ('portrait', 'landscape'):
            lb, la = (i['representations']['iphone']['edgeToEdge'][o] for i in (ib, ia))
            zb, za = label(zones(lb, pb), f'{short} {o}: BEFORE (shipped) touch zones'), label(zones(la, pa), f'{short} {o}: AFTER touch zones')
            if o == 'portrait':
                sheet = Image.new('RGBA', (zb.width + za.width + 20, max(zb.height, za.height)), (255, 255, 255, 255))
                sheet.paste(zb, (0, 0)); sheet.paste(za, (zb.width + 20, 0))
            else:
                sheet = Image.new('RGBA', (max(zb.width, za.width), zb.height + za.height + 20), (255, 255, 255, 255))
                sheet.paste(zb, (0, 0)); sheet.paste(za, (0, zb.height + 20))
            sheet.thumbnail((2400, 2400)); sheet.convert('RGB').save(out / f'zones-{short}-{o}.png', optimize=True)
            ps = press_sheet(lb, pb, la, pa); ps.thumbnail((2400, 9000)); ps.convert('RGB').save(out / f'press-{short}-{o}.png', optimize=True)
            sb, sa = stick_sheet(lb, pb, 'before'), stick_sheet(la, pa, 'after')
            st = Image.new('RGBA', (max(sb.width, sa.width), sb.height + sa.height + 12), (255, 255, 255, 255))
            st.paste(sb, (0, 0)); st.paste(sa, (0, sb.height + 12))
            st.thumbnail((2400, 2400)); st.convert('RGB').save(out / f'stick-{short}-{o}.png', optimize=True)
            print(short, o, 'done')


if __name__ == '__main__':
    main()
