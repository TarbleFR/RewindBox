#!/usr/bin/env python3
"""Build "GameCube Pocket — Original" and "Wii Pocket — Original" from the APPROVED boards.

The maintainer approved two iPhone boards (docs/design/pocket/approved-gamecube.png and
approved-wii.png). These packs reproduce them by using the boards' own pixels:

* the skin background is the board's phone SCREEN (portrait and landscape), without the
  phone frame, titles, presentation background, Dynamic Island, home indicator or the
  "Zone de jeu" text (the game window is navy; the host cuts the exact 4:3 game screen
  out of it at runtime, so the game is never stretched or cropped);
* every control is cut from the same pixels at its own place (normal state), so nothing
  is drawn twice; its pressed state is derived from it (darkened and pressed in, inside
  the control's own outline); each stick has a separate cap moved by the host, cut from
  the board, over a socket reconstructed from the surrounding ring;
* positions, sizes and margins are the board's. Only what the device imposes differs:
  the board is about 0.9 px per iPhone point, so the art is upscaled (softer than a native
  3x render); landscape is letterboxed by 7 pt top and bottom (board ratio 2.25 vs 2.17);
  touch areas get invisible extended edges up to 46.4 mapping pt (44 pt once fitted on
  a 375 pt-wide edge-to-edge iPhone), never over another control or the game screen; a few
  hit rectangles are trimmed where the board's shapes overlap (the drawing is unchanged).

The two earlier packs (wii-pocket, gamecube-pocket) are not touched: this script adds
only its two archives, their previews and their catalog entries. Requires the pinned
Pillow/numpy (requirements.txt). Run after build_pocket_skins.py / build_ps2_pocket.py.
"""
from __future__ import annotations

import argparse, hashlib, io, json, math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import build_pocket_skins as bp

ROOT = bp.ROOT
BOARDS = ROOT / 'docs/design/pocket'
UPSCALE = 3            # board pixels -> archive pixels
NAVY = (9, 22, 49)
# The approved boards show console wordmarks (e.g. "Wii"), so the shared label
# "third-party marks excluded" would be false here.
LICENSE_LABEL = 'RewindBox approved board; console names and marks belong to their owners'
LICENSE = """Original RewindBox artwork: the maintainer-approved Pocket board, used as the skin.
No third-party skin or game artwork is included. Console names and trademarks belong to
their respective owners. No third-party rights are granted.
Publication licensing is to be set by the project maintainer.
"""

# Board geometry in board pixels (1536 x 1024 boards), measured on the approved PNGs.
# item: (name, kind, (x, y, w, h)) ; kind 'button' | 'dpad' | 'stick:left' | 'stick:right'
# sticks also carry the cap circle (cx, cy, r).
PACKS = {
    'gc': {
        'id': 'gamecube-pocket-original', 'name': 'GameCube Pocket — Original',
        'board': 'approved-gamecube.png', 'gameType': 'public.aoshuang.game.ngc',
        'portrait': {
            'crop': (160, 112, 506, 862), 'black_above': 205, 'window': (167, 214, 503, 453),
            'items': [
                ('l', 'button', (187, 467, 95, 38)), ('r', 'button', (389, 467, 95, 38)),
                ('z', 'button', (420, 514, 69, 33)),
                ('main', 'stick:left', (189, 530, 106, 106), (242, 584, 41)),
                ('y', 'button', (326, 538, 43, 50)),  # trimmed at A's left edge (bean overlaps A's box)
                ('a', 'button', (369, 574, 78, 77)), ('x', 'button', (450, 566, 50, 60)),
                ('b', 'button', (319, 622, 50, 50)),
                ('dpad', 'dpad', (200, 672, 91, 89)),
                ('cstick', 'stick:right', (377, 673, 104, 104), (429, 725, 39)),
                ('menu', 'button', (194, 784, 48, 47)), ('start', 'button', (286, 786, 100, 42)),
            ],
        },
        'landscape': {
            'crop': (582, 339, 1394, 700), 'window': (778, 359, 1161, 664),
            'erase': [(586, 462, 630, 588)],  # the board's Dynamic Island
            'erase_rows': [(886, 682, 1086, 694)],  # the board's home indicator
            'items': [
                ('l', 'button', (639, 357, 101, 37)),
                ('main', 'stick:left', (648, 424, 103, 103), (695, 474, 38)),
                ('dpad', 'dpad', (658, 553, 89, 86)), ('menu', 'button', (608, 621, 50, 50)),
                ('r', 'button', (1189, 357, 86, 37)), ('z', 'button', (1302, 360, 71, 32)),
                ('y', 'button', (1195, 415, 45, 51)),  # trimmed at A's left edge
                ('a', 'button', (1240, 450, 83, 81)), ('x', 'button', (1326, 436, 53, 60)),
                ('b', 'button', (1187, 502, 52, 52)),
                ('cstick', 'stick:right', (1268, 554, 102, 102), (1322, 606, 39)),
                ('start', 'button', (1180, 624, 82, 41)),
            ],
        },
    },
    'wii': {
        'id': 'wii-pocket-original', 'name': 'Wii Pocket — Original',
        'board': 'approved-wii.png', 'gameType': 'public.aoshuang.game.wii',
        'portrait': {
            'crop': (160, 112, 506, 862), 'black_above': 205, 'window': (167, 214, 503, 455),
            'items': [
                ('c', 'button', (191, 472, 68, 36)), ('z', 'button', (411, 472, 67, 36)),
                ('main', 'stick:left', (201, 524, 108, 108), (254, 577, 43)),
                ('a', 'button', (372, 516, 94, 92)), ('b', 'button', (369, 617, 98, 52)),
                ('dpad', 'dpad', (204, 655, 102, 97)),
                ('one', 'button', (346, 695, 60, 60)), ('two', 'button', (424, 695, 60, 60)),
                ('minus', 'button', (190, 780, 49, 47)), ('home', 'button', (267, 780, 51, 47)),
                ('plus', 'button', (351, 780, 51, 47)), ('menu', 'button', (428, 780, 52, 47)),
            ],
        },
        'landscape': {
            'crop': (582, 339, 1394, 700), 'window': (783, 359, 1178, 665),
            'erase': [(586, 462, 630, 588)], 'erase_rows': [(886, 682, 1086, 694)],
            'items': [
                ('c', 'button', (634, 362, 56, 36)), ('z', 'button', (709, 362, 58, 36)),
                ('main', 'stick:left', (650, 429, 104, 104), (702, 480, 41)),
                ('dpad', 'dpad', (655, 553, 95, 92)), ('menu', 'button', (608, 630, 47, 48)),
                ('minus', 'button', (1195, 357, 43, 43)), ('home', 'button', (1258, 357, 43, 43)),
                ('plus', 'button', (1322, 357, 44, 43)),
                ('a', 'button', (1239, 440, 87, 86)), ('b', 'button', (1233, 534, 95, 49)),
                ('one', 'button', (1207, 602, 61, 61)), ('two', 'button', (1298, 602, 61, 61)),
            ],
        },
    },
}
INPUTS = {'gc': {'l', 'r', 'z', 'y', 'x', 'a', 'b', 'start', 'menu'},
          'wii': {'c', 'z', 'a', 'b', 'one', 'two', 'minus', 'home', 'plus', 'menu'}}
MAPPING_WIDTH = {'portrait': 393.0, 'landscape': 852.0}


def board_screen(board: Image.Image, spec: dict) -> Image.Image:
    """The phone screen of the board, hardware and placeholder text removed."""
    x0, y0, x1, y1 = spec['crop']
    im = board.crop((x0, y0, x1, y1)).convert('RGB')
    d = ImageDraw.Draw(im)
    if 'black_above' in spec:
        # Status area: plain black (the device draws its own Dynamic Island).
        d.rectangle((0, 0, im.width, spec['black_above'] - y0), fill=(0, 0, 0))
    a = np.asarray(im).astype(np.float32)
    # Dynamic Island and home indicator of the board: each column is refilled by linear
    # interpolation between the body just above and just below (no other control copied).
    for ex0, ey0, ex1, ey1 in spec.get('erase', []) + spec.get('erase_rows', []):
        cx0, cy0, cx1, cy1 = ex0 - x0, ey0 - y0, ex1 - x0, ey1 - y0
        top = a[cy0 - 3:cy0 - 1].mean(axis=0)[cx0:cx1]
        bottom = a[cy1 + 1:cy1 + 3].mean(axis=0)[cx0:cx1]
        for row in range(cy0, cy1):
            t = (row - cy0 + 1) / (cy1 - cy0 + 1)
            a[row, cx0:cx1] = top * (1 - t) + bottom * t
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')
    wx0, wy0, wx1, wy1 = spec['window']
    # The window becomes plain navy ("Zone de jeu" removed); its rounded corners are kept.
    a = np.asarray(im).astype(np.int16)
    box = a[wy0 - y0:wy1 - y0, wx0 - x0:wx1 - x0]
    navy = (box[..., 2] > 35) & (box[..., 0] < 60) & (box[..., 2] - box[..., 0] > 12)
    board_navy = box[navy].mean(axis=0).round().astype(np.int16)  # the board's own navy
    text = ~navy
    # Interior only (2 px in): the window's own light border stays.
    text[:3, :] = False; text[-3:, :] = False; text[:, :3] = False; text[:, -3:] = False
    box[navy | text] = board_navy
    a[wy0 - y0:wy1 - y0, wx0 - x0:wx1 - x0] = box
    return Image.fromarray(a.astype(np.uint8), 'RGB')


def control_mask(crop: Image.Image) -> Image.Image:
    """The control inside its rectangle: everything not connected to the rectangle's border
    through body-coloured pixels (the outline encloses the face)."""
    a = np.asarray(crop.convert('RGB')).astype(np.int16)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    body = np.median(border, axis=0)
    diff = np.abs(a - body).sum(axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    like = ((diff < 26) & (sat < 22)).astype(np.uint8) * 255
    seed = Image.fromarray(like, 'L')
    marker = Image.new('L', seed.size, 0)
    # Flood the body-like region from every border pixel.
    flood = seed.copy()
    w, h = flood.size
    for x in range(w):
        for y in (0, h - 1):
            if flood.getpixel((x, y)) == 255: ImageDraw.floodfill(flood, (x, y), 128)
    for y in range(h):
        for x in (0, w - 1):
            if flood.getpixel((x, y)) == 255: ImageDraw.floodfill(flood, (x, y), 128)
    background = np.asarray(flood) == 128
    mask = Image.fromarray(((~background) * 255).astype(np.uint8), 'L')
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    return mask


def pressed_sprite(normal: Image.Image, mask: Image.Image, scale: int) -> Image.Image:
    """Pressed in: the control darkens and sinks a little inside its own outline."""
    shift = max(1, round(1.4 * scale))
    sunk = Image.new('RGB', normal.size)
    sunk.paste(normal, (0, shift))
    sunk.paste(normal.crop((0, 0, normal.width, shift)), (0, 0))
    dark = Image.eval(sunk, lambda v: int(v * 0.82))
    inner = mask.filter(ImageFilter.GaussianBlur(2.5 * scale))
    shade = Image.composite(dark, sunk, ImageChops.multiply(mask, ImageChops.invert(inner)).point(lambda v: min(255, v * 3)))
    shade = Image.blend(shade, dark, 0.55)
    return Image.composite(shade, normal, mask)


def socket_fill(base: Image.Image, cx: float, cy: float, r: float) -> Image.Image:
    """Removes the cap from a stick base: the hole is filled from the ring around it,
    darker toward the centre, so the moving cap never leaves a copy of itself."""
    a = np.asarray(base.convert('RGB')).astype(np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    dist = np.hypot(xx - cx, yy - cy)
    angle = np.arctan2(yy - cy, xx - cx)
    ring = (dist > r * 1.06) & (dist < r * 1.18)
    bins = 72
    idx = ((angle + math.pi) / (2 * math.pi) * bins).astype(int) % bins
    colours = np.zeros((bins, 3), np.float32)
    for b in range(bins):
        sel = ring & (idx == b)
        colours[b] = a[sel].mean(axis=0) if sel.any() else a[ring].mean(axis=0)
    inside = dist <= r * 1.08
    t = np.clip(dist / (r * 1.08), 0, 1)[..., None]
    fill = colours[idx] * (0.55 + 0.45 * t)
    a[inside] = fill[inside]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


def cap_sprite(board_screen_up: Image.Image, cx: float, cy: float, r: float) -> Image.Image:
    d = 2 * r
    crop = board_screen_up.crop((round(cx - r), round(cy - r), round(cx - r + d), round(cy - r + d))).convert('RGBA')
    alpha = Image.new('L', (crop.width * 4, crop.height * 4), 0)
    ImageDraw.Draw(alpha).ellipse((2, 2, alpha.width - 3, alpha.height - 3), fill=255)
    crop.putalpha(alpha.resize(crop.size, Image.Resampling.LANCZOS))
    return crop


def representation(console: str, orientation: str, spec: dict, board: Image.Image, files: dict) -> dict:
    x0, y0, x1, y1 = spec['crop']
    screen = board_screen(board, spec)
    k = MAPPING_WIDTH[orientation] / (x1 - x0)            # board px -> mapping points
    up = screen.resize((screen.width * UPSCALE, screen.height * UPSCALE), Image.Resampling.LANCZOS)
    up = up.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    name = f'body-{orientation}.png'
    files[name] = bp.png(up)
    W, H = MAPPING_WIDTH[orientation], round((y1 - y0) * k, 3)
    wx0, wy0, wx1, wy1 = spec['window']
    ww, wh = wx1 - wx0, wy1 - wy0
    if ww / wh > 4 / 3:
        sw, sh = wh * 4 / 3, wh
    else:
        sw, sh = ww, ww * 3 / 4
    sx, sy = wx0 + (ww - sw) / 2, wy0 + (wh - sh) / 2
    screen_rect = bp.rect(round((sx - x0) * k, 3), round((sy - y0) * k, 3), round(sw * k, 3), round(sh * k, 3))
    items = []
    for entry in spec['items']:
        label, kind, (bx, by, bw, bh) = entry[:3]
        frame = bp.rect(round((bx - x0) * k, 3), round((by - y0) * k, 3), round(bw * k, 3), round(bh * k, 3))
        box = tuple(v * UPSCALE for v in (bx - x0, by - y0, bx - x0 + bw, by - y0 + bh))
        normal = up.crop(box)
        key = f'{orientation}-{label}'
        if kind.startswith('stick'):
            cx, cy, r = entry[3]
            lcx, lcy, lr = (cx - bx) * UPSCALE, (cy - by) * UPSCALE, r * UPSCALE
            base = socket_fill(normal, lcx, lcy, lr)
            files[f'controls/{key}-base.png'] = bp.png(base)
            ring = Image.new('L', base.size, 0)
            ImageDraw.Draw(ring).ellipse((2, 2, base.width - 3, base.height - 3), fill=255)
            files[f'controls/{key}-base-pressed.png'] = bp.png(pressed_sprite(base, ring.filter(ImageFilter.GaussianBlur(2)), UPSCALE))
            files[f'controls/{key}-knob.png'] = bp.png(cap_sprite(up, (cx - x0) * UPSCALE, (cy - y0) * UPSCALE, lr))
            side = kind.split(':')[1]
            item = {'frame': frame,
                    'inputs': {d: f'{side}Thumbstick{d.title()}' for d in ('up', 'down', 'left', 'right')},
                    'asset': {'normal': f'controls/{key}-base.png', 'pressed': f'controls/{key}-base-pressed.png'},
                    'thumbstick': {'name': f'controls/{key}-knob.png', 'width': round(2 * r * k, 3), 'height': round(2 * r * k, 3)}}
        else:
            mask = control_mask(normal)
            files[f'controls/{key}.png'] = bp.png(normal)
            files[f'controls/{key}-pressed.png'] = bp.png(pressed_sprite(normal, mask, UPSCALE))
            inputs = {d: d for d in ('up', 'down', 'left', 'right')} if kind == 'dpad' else [label]
            item = {'frame': frame, 'inputs': inputs,
                    'asset': {'normal': f'controls/{key}.png', 'pressed': f'controls/{key}-pressed.png'}}
        item['extendedEdges'] = dict(top=0, bottom=0, left=0, right=0)
        items.append(item)
    # No invisible extension into the home-indicator band of the smallest edge-to-edge
    # iPhone (34 pt portrait = 36 mapping pt; 21 pt landscape, 7 pt of it letterbox).
    extend_targets(items, W, H, screen_rect, bottom_limit=H - (36 if orientation == 'portrait' else 15))
    return {'assets': {'small': name, 'medium': name, 'large': name}, 'mappingSize': {'width': W, 'height': H},
            'screens': [{'outputFrame': screen_rect}], 'items': items, 'translucent': False}


def hit(item):
    f, e = item['frame'], item['extendedEdges']
    return (f['x'] - e['left'], f['y'] - e['top'], f['x'] + f['width'] + e['right'], f['y'] + f['height'] + e['bottom'])


def overlaps(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > 0.01 and min(a[3], b[3]) - max(a[1], b[1]) > 0.01


def extend_targets(items, W, H, screen, target=46.4, bottom_limit=None):
    """Invisible extended edges until each touch area reaches `target` mapping pt (44 pt fitted
    on the smallest edge-to-edge iPhone, 375 x 812), never over another
    control, the game screen or outside the mapping."""
    scr = (screen['x'], screen['y'], screen['x'] + screen['width'], screen['y'] + screen['height'])
    for item in items:
        f = item['frame']
        for axis, (lo, hi), size in (('x', ('left', 'right'), f['width']), ('y', ('top', 'bottom'), f['height'])):
            need = max(0.0, target - size) / 2
            if need <= 0: continue
            step = need / 20
            for _ in range(20):
                for side in (lo, hi):
                    item['extendedEdges'][side] = round(item['extendedEdges'][side] + step, 3)
                    h = hit(item)
                    floor = H if bottom_limit is None else max(bottom_limit, f['y'] + f['height'])
                    if (h[0] < 0 or h[1] < 0 or h[2] > W or h[3] > floor or overlaps(h, scr) or
                            any(overlaps(h, hit(o)) for o in items if o is not item)):
                        item['extendedEdges'][side] = round(item['extendedEdges'][side] - step, 3)


def compose(L, files, pressed=False, scale=bp.SCALE):
    """Preview of a representation from its own files, like the native overlay draws it
    (bp.compose with non-integer mapping sizes)."""
    W, H = L['mappingSize']['width'], L['mappingSize']['height']
    im = Image.open(io.BytesIO(files[L['assets']['large']])).convert('RGBA').resize(
        (round(W * scale), round(H * scale)), Image.Resampling.LANCZOS)
    # The window is already the board's navy in the background (the game shows there).
    for item in L['items']:
        f = item['frame']
        b = (round(f['x'] * scale), round(f['y'] * scale), round((f['x'] + f['width']) * scale), round((f['y'] + f['height']) * scale))
        sprite = Image.open(io.BytesIO(files[item['asset']['pressed' if pressed else 'normal']])).convert('RGBA')
        im.alpha_composite(sprite.resize((b[2] - b[0], b[3] - b[1]), Image.Resampling.LANCZOS), (b[0], b[1]))
        if 'thumbstick' in item:
            th = item['thumbstick']
            w, h = round(th['width'] * scale), round(th['height'] * scale)
            knob = Image.open(io.BytesIO(files[th['name']])).convert('RGBA').resize((w, h), Image.Resampling.LANCZOS)
            dx = round(f['width'] * .12 * scale) if pressed else 0
            im.alpha_composite(knob, ((b[0] + b[2] - w) // 2 + dx, (b[1] + b[3] - h) // 2))
    return im


def build(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    catalog_path = out / 'catalog.json'
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {'schemaVersion': 1, 'skins': []}
    receipts = {}
    for console, pack in PACKS.items():
        board_path = BOARDS / pack['board']
        board = Image.open(board_path).convert('RGB')
        files = {'LICENSE.txt': LICENSE.encode()}
        reps = {'edgeToEdge': {o: representation(console, o, pack[o], board, files) for o in ('portrait', 'landscape')}}
        for orientation in ('portrait', 'landscape'):
            image = bp.png(compose(reps['edgeToEdge'][orientation], files))
            files[f'previews/{orientation}.png'] = image
            (out / f'{pack["id"]}-{orientation}.png').write_bytes(image)
            (out / f'{pack["id"]}-{orientation}-pressed.png').write_bytes(
                bp.png(compose(reps['edgeToEdge'][orientation], files, pressed=True)))
        info = {'name': pack['name'], 'identifier': f'org.rewindbox.{pack["id"]}', 'author': 'RewindBox',
                'gameTypeIdentifier': pack['gameType'], 'version': 1, 'license': LICENSE_LABEL,
                'previewImages': {o: f'previews/{o}.png' for o in ('portrait', 'landscape')},
                'provenance': {'status': 'approved-board', 'board': f'docs/design/pocket/{pack["board"]}',
                               'boardSha256': hashlib.sha256(board_path.read_bytes()).hexdigest(),
                               'generator': 'tools/skins/build_pocket_board_originals.py',
                               'note': 'edge-to-edge iPhone layouts; standard iPhones reuse them letterboxed'},
                'representations': {'iphone': reps}}
        files['info.json'] = (json.dumps(info, indent=2, ensure_ascii=False) + '\n').encode()
        for path, data in files.items():
            if path.endswith('.png'):
                with Image.open(io.BytesIO(data)) as im: im.verify()
        target = out / f'{pack["id"]}.manicskin'
        bp.archive(target, files)
        entry = {'id': pack['id'], 'name': pack['name'], 'console': console,
                 'archiveAsset': f'assets/skins/pocket/{pack["id"]}.manicskin',
                 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'size': target.stat().st_size,
                 'previewAssets': {o: f'assets/skins/pocket/{pack["id"]}-{o}.png' for o in ('portrait', 'landscape')},
                 'author': 'RewindBox', 'license': LICENSE_LABEL}
        catalog['skins'] = [s for s in catalog['skins'] if s['id'] != pack['id']] + [entry]
        receipts[pack['id']] = {'archiveSha256': entry['sha256'], 'archiveBytes': entry['size'],
                                'board': pack['board'], 'boardSha256': info['provenance']['boardSha256']}
        print(json.dumps(entry, ensure_ascii=False))
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    (out / 'validation-board-originals.json').write_text(json.dumps(receipts, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/skins/pocket')
    build(parser.parse_args().output)
