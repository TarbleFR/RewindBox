#!/usr/bin/env python3
"""Before / after sheets of the game's place in the RewindBox Pocket skins.

For each bundled pack, display type and orientation, composes on the host what the
overlays do on the phone (DOLSkinOverlay / ARMSX2SkinOverlay / MeloNXSkinOverlay): the
skin fitted in the screen with one scale and centred, the emulator's surface at
`screens[0].outputFrame` under the same transform (grown to whole points), the body cut
by the pack's `screenCutout` (or by the declared rectangle without one), the controls on
top. Two contents for the surface:

* a test pattern filling it (a band of its own colour along each edge);
* a synthetic game-like picture at the console's native ratio, fitted inside the surface
  the way the emulators' default display mode does (never stretched, never cropped).

`--before REV` is the git revision whose packs are the "before" column.

    python3 tools/skins/render_screen_framing.py --before <rev> --out docs/evidence/skins-screen-framing

Host composition, not a capture: no emulator runs here and nothing is observed on an
iPhone. The picture is drawn by this script; it is not a game.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import subprocess
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'assets/skins/pocket'
PX = 3  # pixels per point of the compositions

# pack id -> (label, native ratio of the console's picture)
PACKS = {
    'wii-pocket': ('Wii Pocket', 4 / 3),
    'gamecube-pocket': ('GameCube Pocket – Ivory', 4 / 3),
    'wii-pocket-original': ('Wii Pocket — Original', 4 / 3),
    'gamecube-pocket-original': ('GameCube Pocket — Original', 4 / 3),
    'ps2-pocket-original': ('PS2 Pocket — Original', 4 / 3),
    'ps2-pocket': ('PS2 Pocket — Noir mat', 4 / 3),
    'switch-pocket': ('Switch Pocket', 16 / 9),
}
# display type -> the iPhone screen it is chosen on (points, upright)
PHONES = {'edgeToEdge': (393, 852), 'standard': (375, 667)}
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def pack_bytes(pack: str, revision: str | None) -> bytes:
    if revision is None:
        return (ASSETS / f'{pack}.manicskin').read_bytes()
    return subprocess.run(['git', 'show', f'{revision}:assets/skins/pocket/{pack}.manicskin'], cwd=ROOT,
                          check=True, capture_output=True).stdout


def test_pattern(w: int, h: int) -> Image.Image:
    """A band along each edge (top red, bottom green, left blue, right yellow), 6 pt."""
    im = Image.new('RGB', (w, h), (128, 128, 128))
    d = ImageDraw.Draw(im)
    t = 6 * PX
    step = 20 * PX
    for x in range(0, w, step):
        d.line((x, 0, x, h), fill=(150, 150, 150))
    for y in range(0, h, step):
        d.line((0, y, w, y), fill=(150, 150, 150))
    d.line((w // 2, 0, w // 2, h), fill='white', width=PX)
    d.line((0, h // 2, w, h // 2), fill='white', width=PX)
    d.ellipse((w // 2 - h // 4, h // 4, w // 2 + h // 4, h - h // 4), outline='white', width=PX)
    d.rectangle((0, t, t - 1, h - t - 1), fill=(0, 0, 255))
    d.rectangle((w - t, t, w - 1, h - t - 1), fill=(255, 255, 0))
    d.rectangle((0, 0, w - 1, t - 1), fill=(255, 0, 0))
    d.rectangle((0, h - t, w - 1, h - 1), fill=(0, 255, 0))
    return im


def game_picture(w: int, h: int) -> Image.Image:
    """A synthetic game-like frame (drawn here): sky, hills, a HUD in each corner and a
    one-point white border, so that any cropping or stretching is visible."""
    y = np.linspace(0, 1, h)[:, None]
    sky = np.concatenate([70 + 110 * y, 140 + 80 * y, 230 - 30 * y], axis=1)
    a = np.repeat(sky[:, None, :], w, axis=1).astype(np.uint8)
    im = Image.fromarray(a, 'RGB')
    d = ImageDraw.Draw(im)
    d.ellipse((w * 0.70, h * 0.10, w * 0.70 + h * 0.22, h * 0.32), fill=(255, 236, 150))
    xs = np.arange(w + 1)
    for base, amp, colour in ((0.62, 0.10, (60, 140, 90)), (0.74, 0.07, (40, 110, 70)), (0.86, 0.04, (30, 80, 55))):
        top = (base + amp * np.sin(xs / w * 2 * math.pi * 1.5 + base * 9)) * h
        d.polygon([(0, h)] + [(int(x), int(t)) for x, t in zip(xs, top)] + [(w, h)], fill=colour)
    d.ellipse((w * 0.5 - h * 0.05, h * 0.60, w * 0.5 + h * 0.05, h * 0.70), fill=(220, 60, 60), outline='white', width=PX)
    font = ImageFont.truetype(FONT, max(8, round(h * 0.055)))
    m = round(h * 0.03)
    for text, anchor, xy in (('♥♥♥', 'la', (m, m)), ('00:42', 'ra', (w - m, m)), ('x12', 'ld', (m, h - m)),
                             ('MAP', 'rd', (w - m, h - m))):
        d.text(xy, text, font=font, fill='white', anchor=anchor, stroke_width=PX, stroke_fill=(20, 20, 40))
    d.rectangle((0, 0, w - 1, h - 1), outline='white', width=PX)
    return im


def compose(archive: bytes, display: str, orientation: str, content: str, ratio: float):
    """(image, details): one phone screen, or (None, None) when the pack has no such layout."""
    z = zipfile.ZipFile(io.BytesIO(archive))
    info = json.loads(z.read('info.json'))
    layout = info['representations']['iphone'].get(display, {}).get(orientation)
    if layout is None:
        return None, None
    w, h = PHONES[display] if orientation == 'portrait' else PHONES[display][::-1]
    m = layout['mappingSize']
    scale = min(w / m['width'], h / m['height'])
    ox, oy = (w - m['width'] * scale) / 2, (h - m['height'] * scale) / 2
    place = lambda f: (ox + f['x'] * scale, oy + f['y'] * scale, f['width'] * scale, f['height'] * scale)
    canvas = Image.new('RGBA', (w * PX, h * PX), (0, 0, 0, 255))

    # The emulator's surface: the declared frame, grown to whole points by the sessions.
    screen = layout['screens'][0]
    sx, sy, sw, sh = place(screen['outputFrame'])
    x0, y0, x1, y1 = math.floor(sx), math.floor(sy), math.ceil(sx + sw), math.ceil(sy + sh)
    surface = Image.new('RGB', ((x1 - x0) * PX, (y1 - y0) * PX), (0, 0, 0))
    if content == 'pattern':
        surface = test_pattern(*surface.size)
    else:
        # Fitted inside the surface at the console's ratio (the default display mode).
        gw = min(surface.width, round(surface.height * ratio))
        gh = min(surface.height, round(surface.width / ratio))
        surface.paste(game_picture(gw, gh), ((surface.width - gw) // 2, (surface.height - gh) // 2))
    canvas.paste(surface, (x0 * PX, y0 * PX))

    # The body, cut by the pack's cutout (scaled with it) or by the declared rectangle.
    box = (round(ox * PX), round(oy * PX), round((ox + m['width'] * scale) * PX), round((oy + m['height'] * scale) * PX))
    size = (box[2] - box[0], box[3] - box[1])
    body = Image.open(io.BytesIO(z.read(layout['assets']['large']))).convert('RGBA').resize(size, Image.Resampling.LANCZOS)
    if 'screenCutout' in screen:
        mask = Image.open(io.BytesIO(z.read(screen['screenCutout']))).convert('RGBA').getchannel('A')
        mask = mask.resize(size, Image.Resampling.BILINEAR)
    else:
        mask = Image.new('L', size, 255)
        ImageDraw.Draw(mask).rectangle((round(sx * PX) - box[0], round(sy * PX) - box[1],
                                        round((sx + sw) * PX) - box[0] - 1, round((sy + sh) * PX) - box[1] - 1), fill=0)
    body.putalpha(mask)
    canvas.alpha_composite(body, box[:2])
    for item in layout['items']:
        fx, fy, fw, fh = place(item['frame'])
        b = (round(fx * PX), round(fy * PX), round((fx + fw) * PX), round((fy + fh) * PX))
        sprite = Image.open(io.BytesIO(z.read(item['asset']['normal']))).convert('RGBA')
        canvas.alpha_composite(sprite.resize((b[2] - b[0], b[3] - b[1]), Image.Resampling.LANCZOS), b[:2])
        if 'thumbstick' in item:
            th = item['thumbstick']
            kw, kh = round(th['width'] * scale * PX), round(th['height'] * scale * PX)
            knob = Image.open(io.BytesIO(z.read(th['name']))).convert('RGBA').resize((kw, kh), Image.Resampling.LANCZOS)
            canvas.alpha_composite(knob, ((b[0] + b[2] - kw) // 2, (b[1] + b[3] - kh) // 2))
    details = {'phone': [w, h], 'scale': round(scale, 5), 'screenFrame': [round(v, 3) for v in (sx, sy, sw, sh)],
               'surface': [x0, y0, x1 - x0, y1 - y0], 'cutout': 'screenCutout' in screen}
    return canvas.convert('RGB'), details


def zoom(image: Image.Image, details: dict, corner: str) -> Image.Image:
    """The top-left or bottom-right corner of the surface, 36 x 36 pt around it, 3 times."""
    x, y, w, h = details['surface']
    cx, cy = (x, y) if corner == 'tl' else (x + w, y + h)
    r = 18
    return image.crop(((cx - r) * PX, (cy - r) * PX, (cx + r) * PX, (cy + r) * PX)).resize((r * 2 * PX * 3 // 2,) * 2, Image.Resampling.NEAREST)


def sheet(pack: str, display: str, before: bytes, after: bytes):
    label, ratio = PACKS[pack]
    font = ImageFont.truetype(FONT, 22)
    small = ImageFont.truetype(FONT, 17)
    rows, report = [], {}
    for orientation in ('portrait', 'landscape'):
        tiles = []
        for content in ('pattern', 'game'):
            for when, archive in (('before', before), ('after', after)):
                image, details = compose(archive, display, orientation, content, ratio)
                if image is None:
                    return None, None
                report.setdefault(orientation, {})[when] = details
                view = image.resize((image.width // 2, image.height // 2), Image.Resampling.LANCZOS)
                zooms = [zoom(image, details, c) for c in ('tl', 'br')]
                tile = Image.new('RGB', (view.width + zooms[0].width + 12, max(view.height, zooms[0].height * 2 + 12) + 34), 'white')
                ImageDraw.Draw(tile).text((4, 6), f"{when} · {'test pattern' if content == 'pattern' else 'game-like picture'}",
                                          font=small, fill='black')
                tile.paste(view, (0, 34))
                tile.paste(zooms[0], (view.width + 12, 34))
                tile.paste(zooms[1], (view.width + 12, 34 + zooms[0].height + 12))
                tiles.append(tile)
        per_row = 4 if orientation == 'portrait' else 2
        for i in range(0, len(tiles), per_row):
            group = tiles[i:i + per_row]
            row = Image.new('RGB', (sum(t.width + 16 for t in group), max(t.height for t in group)), 'white')
            x = 0
            for t in group:
                row.paste(t, (x, 0))
                x += t.width + 16
            rows.append(row)
    phone = PHONES[display]
    title = f"{label} ({pack}) · {display} · iPhone {phone[0]} x {phone[1]} pt · host composition, not a capture"
    out = Image.new('RGB', (max(r.width for r in rows) + 16, sum(r.height + 16 for r in rows) + 44), 'white')
    ImageDraw.Draw(out).text((8, 8), title, font=font, fill='black')
    y = 44
    for r in rows:
        out.paste(r, (8, y))
        y += r.height + 16
    return out, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--before', required=True, help='git revision of the previous packs')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--width', type=int, default=1800, help='largest width of a sheet, pixels')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {'before': subprocess.run(['git', 'rev-parse', args.before], cwd=ROOT, check=True, capture_output=True,
                                        text=True).stdout.strip(),
               'composition': 'host (tools/skins/render_screen_framing.py); no emulator, no iPhone', 'sheets': {}}
    for pack in PACKS:
        before, after = pack_bytes(pack, args.before), pack_bytes(pack, None)
        for display in PHONES:
            image, report = sheet(pack, display, before, after)
            if image is None:
                continue
            if image.width > args.width:
                image = image.resize((args.width, round(image.height * args.width / image.width)), Image.Resampling.LANCZOS)
            name = f'{pack}-{display}.jpg'
            image.save(args.out / name, quality=84, optimize=True)
            summary['sheets'][name] = {'unchangedPack': before == after, **report}
            print(name, image.size)
    (args.out / 'sheets.json').write_text(json.dumps(summary, indent=1) + '\n')


if __name__ == '__main__':
    main()
