#!/usr/bin/env python3
# Usage (repository root): python3 tools/skins/render_board_comparisons.py docs/evidence/pocket-originals/board-originals
"""Target board | pack on a 393 x 852 pt iPhone with the PREVIOUS floating buttons |
with the NEW placement (DOLSessionChromePolicy). Pack art = the archive's own preview."""
import json, sys, zipfile
from PIL import Image, ImageDraw
out = sys.argv[1]; K = 2  # pixels per point
CROPS = {'portrait': (160, 112, 506, 862), 'landscape': (582, 339, 1394, 700)}
def device(pid, o, mode):
    info = json.loads(zipfile.ZipFile(f'assets/skins/pocket/{pid}.manicskin').read('info.json'))
    L = info['representations']['iphone']['edgeToEdge'][o]; W, H = L['mappingSize']['width'], L['mappingSize']['height']
    dev = (393, 852) if o == 'portrait' else (852, 393)
    s = min(dev[0]/W, dev[1]/H); dx, dy = (dev[0]-W*s)/2, (dev[1]-H*s)/2
    c = Image.new('RGBA', (dev[0]*K, dev[1]*K), (0, 0, 0, 255))
    art = Image.open(f'assets/skins/pocket/{pid}-{o}.png').convert('RGBA').resize((round(W*s*K), round(H*s*K)), Image.Resampling.LANCZOS)
    c.alpha_composite(art, (round(dx*K), round(dy*K)))
    ov = Image.new('RGBA', c.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    def button(x, y, glyph):
        d.rounded_rectangle((x*K, y*K, (x+44)*K, (y+44)*K), 18*K, fill=(0, 0, 0, 140))
        w = (255, 255, 255, 255)
        if glyph == 'menu':
            for i in (-6, 0, 6):
                d.line(((x+14)*K, (y+22+i)*K, (x+30)*K, (y+22+i)*K), fill=w, width=2*K)
        else:
            d.line([((x+12+i*4)*K, (y+22+v)*K) for i, v in enumerate((6, 0, 3, -5, -1, -7))], fill=w, width=2*K)
    left, top = (0, 59) if o == 'portrait' else (59, 0)
    if mode == 'before':
        button(left+12, top+12, 'menu'); button(left+12+52, top+12, 'perf')
    else:
        sc = L['screens'][0]['outputFrame']
        button(dx+sc['x']*s+8, dy+sc['y']*s+8, 'perf')
    c.alpha_composite(ov); return c.convert('RGB')
def sheet(board, pid, o, name):
    t = Image.open(f'docs/design/pocket/{board}').convert('RGB').crop(CROPS[o])
    b, a = device(pid, o, 'before'), device(pid, o, 'after')
    t = t.resize((round(t.width*b.height/t.height), b.height), Image.Resampling.LANCZOS) if o == 'portrait' else \
        t.resize((b.width, round(t.height*b.width/t.width)), Image.Resampling.LANCZOS)
    cols = [('Cible : planche approuvee', t), ('Pack reel, anciens boutons flottants', b), ('Pack reel, placement corrige', a)]
    if o == 'portrait':
        Wt = sum(im.width for _, im in cols)+40; Ht = max(im.height for _, im in cols)+40
        c = Image.new('RGB', (Wt, Ht), (205, 210, 220)); d = ImageDraw.Draw(c); x = 0
        for lab, im in cols: d.text((x+6, 8), lab, fill=(0, 0, 0), font_size=22); c.paste(im, (x, 40)); x += im.width+20
    else:
        Wt = max(im.width for _, im in cols); Ht = sum(im.height+40 for _, im in cols)
        c = Image.new('RGB', (Wt, Ht), (205, 210, 220)); d = ImageDraw.Draw(c); y = 0
        for lab, im in cols: d.text((6, y+8), lab, fill=(0, 0, 0), font_size=22); c.paste(im, (0, y+40)); y += im.height+40
    c.thumbnail((1800, 1800)); c.save(f'{out}/{name}.png', optimize=True)
for board, pid, short in (('approved-gamecube.png', 'gamecube-pocket-original', 'gamecube'), ('approved-wii.png', 'wii-pocket-original', 'wii')):
    for o in ('portrait', 'landscape'):
        sheet(board, pid, o, f'{short}-{o}-comparison')
