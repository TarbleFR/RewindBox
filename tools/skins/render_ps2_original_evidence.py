#!/usr/bin/env python3
"""Evidence sheets for PS2 Pocket — Original (a new pack: there is no "before").

Usage (repository root):
  python3 tools/skins/render_ps2_original_evidence.py ARCHIVE_DIR OUT_DIR

From ARCHIVE_DIR/ps2-pocket-original.manicskin, drawn the way ARMSX2SkinOverlay composes
it (its twin DOLSkinOverlay's order: background, every item sprite in its frame, the cap at
knobFrame) and with the overlays' shape-aware hit test (DOLSkinHitTest.h /
ARMSX2SkinHitTest.h, through the input-chain mirror proven equal to both):
- maquette-*.png: the approved maquette's useful zone (docs/design/pocket/approved-ps2.png,
  phone frame excluded) beside the archive at rest and with every control pressed;
- zones-*.png: every point tinted with the control a touch there reaches, frames outlined;
- press-*.png: each button at rest / pressed / released, magnified;
- stick-*.png: each cap for the vectors (0,0) (1,0) (0.71,0.71) (0,-1) (-1,0).
Host renders of the archive's own files, not iPhone screenshots.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pocket_board_originals as b  # noqa: E402
import render_touch_evidence as ev  # noqa: E402

PID = 'ps2-pocket-original'


def press_sheet(layout, pngs):
    rows = []
    for i, item in enumerate(layout['items']):
        if not isinstance(item['inputs'], list) and 'thumbstick' in item: continue
        f = item['frame']
        pad = 6
        box = (round((f['x'] - pad) * ev.PX), round((f['y'] - pad) * ev.PX),
               round((f['x'] + f['width'] + pad) * ev.PX), round((f['y'] + f['height'] + pad) * ev.PX))
        cells = []
        for state, pressed in (('rest', ()), ('pressed', (i,)), ('released', ())):
            crop = ev.compose(layout, pngs, pressed).crop(box)
            cells.append(ev.label(crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.NEAREST), state))
        name = ' / '.join(item['inputs'] if isinstance(item['inputs'], list) else item['inputs'].values())
        row = Image.new('RGBA', (sum(c.width for c in cells) + 10 * len(cells), max(c.height for c in cells) + 30), (255, 255, 255, 255))
        ImageDraw.Draw(row).text((4, 4), name, fill=(0, 0, 0, 255), font_size=22)
        x = 0
        for c in cells:
            row.paste(c, (x, 30)); x += c.width + 10
        rows.append(row)
    sheet = Image.new('RGBA', (max(r.width for r in rows), sum(r.height for r in rows)), (255, 255, 255, 255))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y)); y += r.height
    return sheet


def maquette_sheet(orientation, layout, pngs):
    board = Image.open(b.BOARDS / b.PACKS['ps2']['board']).convert('RGB')
    rest = ev.compose(layout, pngs).convert('RGB')
    pressed = ev.compose(layout, pngs, tuple(i for i, it in enumerate(layout['items']) if 'thumbstick' not in it)).convert('RGB')
    ref = board.crop(b.PACKS['ps2'][orientation]['crop'])
    ref = ref.resize(rest.size, Image.Resampling.LANCZOS)
    cells = [ev.label(ref.convert('RGBA'), f'{orientation}: approved maquette (useful zone)'),
             ev.label(rest.convert('RGBA'), f'{orientation}: archive at rest'),
             ev.label(pressed.convert('RGBA'), f'{orientation}: every button pressed')]
    if orientation == 'portrait':
        sheet = Image.new('RGBA', (sum(c.width for c in cells) + 40, max(c.height for c in cells)), (255, 255, 255, 255))
        x = 0
        for c in cells:
            sheet.paste(c, (x, 0)); x += c.width + 20
    else:
        sheet = Image.new('RGBA', (max(c.width for c in cells), sum(c.height for c in cells) + 40), (255, 255, 255, 255))
        y = 0
        for c in cells:
            sheet.paste(c, (0, y)); y += c.height + 20
    return sheet


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    info, pngs = ev.load(src / f'{PID}.manicskin')
    for o in ('portrait', 'landscape'):
        layout = info['representations']['iphone']['edgeToEdge'][o]
        for name, img, limit in (('maquette', maquette_sheet(o, layout, pngs), (2400, 2400)),
                                 ('zones', ev.label(ev.zones(layout, pngs), f'ps2 original {o}: touch zones'), (2400, 2400)),
                                 ('press', press_sheet(layout, pngs), (2400, 12000)),
                                 ('stick', ev.stick_sheet(layout, pngs, 'ps2'), (2400, 2400))):
            img.thumbnail(limit)
            img.convert('RGB').save(out / f'{name}-ps2-{o}.png', optimize=True)
        print('ps2', o, 'done')


if __name__ == '__main__':
    main()
