#!/usr/bin/env python3
"""Sharpness detail of the board Originals at the same magnification.

Usage: python3 tools/skins/render_board_detail.py OUT_DIR MAINTAINER_PNG_DIR
For a control cluster per layout: the maintainer's PNG pixels (nearest-neighbour, so
the source detail is shown as it is), the same pixels resampled to iPhone 3x, and the
pack's own background art at the resolution it ships, all at one size in points.
"""
import io, json, sys, zipfile
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pocket_board_originals as b  # noqa: E402
import check_board_inputs as ci  # noqa: E402

out, targets = Path(sys.argv[1]), sys.argv[2]
# clusters in board pixels: (console, orientation, region, label)
CLUSTERS = [('gc', 'portrait', (310, 530, 505, 680), 'GameCube portrait: Y/A/X/B'),
            ('gc', 'landscape', (1180, 405, 1385, 545), 'GameCube landscape: Y/A/X/B'),
            ('wii', 'portrait', (185, 515, 470, 640), 'Wii portrait: stick/A'),
            ('wii', 'landscape', (1195, 430, 1370, 590), 'Wii landscape: A/B')]
rows = []
for console, o, region, label in CLUSTERS:
    pack = b.PACKS[console]; spec = pack[o]; crop = spec['crop']
    source = ci.target_board(console, targets).crop(region)
    z = zipfile.ZipFile(f'assets/skins/pocket/{pack["id"]}.manicskin')
    layout = json.loads(z.read('info.json'))['representations']['iphone']['edgeToEdge'][o]
    art = Image.open(io.BytesIO(z.read(layout['assets']['large']))).convert('RGB')
    k = layout['mappingSize']['width'] / (crop[2] - crop[0])       # points per board pixel
    s = art.width / layout['mappingSize']['width']                 # shipped pixels per point
    pts = ((region[0]-crop[0])*k, (region[1]-crop[1])*k, (region[2]-crop[0])*k, (region[3]-crop[1])*k)
    shipped = art.crop(tuple(round(v*s) for v in pts))
    size = (round((pts[2]-pts[0])*6), round((pts[3]-pts[1])*6))    # 6 px per point on the sheet
    cells = [('PNG original (pixels source)', source.resize(size, Image.Resampling.NEAREST)),
             ('PNG original reechantillonne a 3x', source.resize((round((pts[2]-pts[0])*3), round((pts[3]-pts[1])*3)), Image.Resampling.LANCZOS).resize(size, Image.Resampling.NEAREST)),
             (f'Pack livre ({s:.2f} px/pt)', shipped.resize(size, Image.Resampling.NEAREST))]
    rows.append((label, cells, size))
W = max(3*sz[0]+40 for _, _, sz in rows); H = sum(sz[1]+70 for _, _, sz in rows)
sheet = Image.new('RGB', (W, H), (205, 210, 220)); d = ImageDraw.Draw(sheet); y = 0
for label, cells, size in rows:
    d.text((6, y+4), label, fill=(0, 0, 0), font_size=22); x = 0
    for name, im in cells:
        d.text((x+6, y+32), name, fill=(40, 40, 40), font_size=18); sheet.paste(im, (x, y+56)); x += size[0]+20
    y += size[1]+70
sheet.thumbnail((2400, 2400)); sheet.save(out/'sharpness-detail.png', optimize=True)
print(out/'sharpness-detail.png')
