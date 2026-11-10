#!/usr/bin/env python3
"""Build "GameCube Pocket — Original", "Wii Pocket — Original" and "PS2 Pocket — Original"
from the APPROVED boards.

The maintainer approved three iPhone boards (docs/design/pocket/approved-gamecube.png,
approved-wii.png and approved-ps2.png). These packs reproduce them by using the boards' own
pixels:

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

The earlier packs (wii-pocket, gamecube-pocket, ps2-pocket) are not touched: this script
adds only its own archives, their previews and their catalog entries. PS2 specifics: the
L3/R3 targets are the board's labels under the sticks (a touch area below the cap, the
label alone changes when pressed); the landscape board has no Menu, so the portrait
board's own Menu button is placed in the landscape body (bottom left, where the GameCube
and Wii boards have theirs) as the one documented addition. Requires the pinned
Pillow/numpy (requirements.txt). Run after build_pocket_skins.py / build_ps2_pocket.py.
"""
from __future__ import annotations

import argparse, hashlib, io, json, math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import build_pocket_skins as bp
import screen_opening

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
# a stick adds (cap centre x, y, r) by hand and, for GameCube and Wii, the whole cap
# measured on the board (centre x, y, radius; tools/skins/measure_stick_caps.py): the
# complete round stick, face, bevel and the side wall below it (the C-stick: its yellow top
# and darker yellow ring), as one circle. That whole circle moves.
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
                ('main', 'stick:left', (189, 530, 106, 106), (242, 584, 41), (241.32, 584.41, 39.9)),
                ('y', 'button', (325, 537, 63, 58)),  # the whole bean (its box overlaps A's; the shapes do not)
                ('a', 'button', (369, 574, 78, 77)), ('x', 'button', (450, 566, 50, 60)),
                ('b', 'button', (319, 622, 50, 50)),
                ('dpad', 'dpad', (200, 672, 91, 89)),
                ('cstick', 'stick:right', (377, 673, 104, 104), (429, 725, 39), (428.34, 728.18, 38.56)),
                ('menu', 'button', (194, 784, 48, 47)), ('start', 'button', (286, 786, 100, 42)),
            ],
        },
        'landscape': {
            'crop': (582, 339, 1394, 700), 'window': (778, 359, 1161, 664),
            'erase': [(586, 462, 630, 588)],  # the board's Dynamic Island
            'erase_rows': [(886, 682, 1086, 694)],  # the board's home indicator
            'items': [
                ('l', 'button', (639, 357, 101, 37)),
                ('main', 'stick:left', (648, 424, 103, 103), (695, 474, 38), (698.75, 474.24, 39.02)),
                ('dpad', 'dpad', (658, 553, 89, 86)), ('menu', 'button', (608, 621, 50, 50)),
                ('r', 'button', (1189, 357, 86, 37)), ('z', 'button', (1302, 360, 71, 32)),
                ('y', 'button', (1194, 413, 67, 59)),  # the whole bean
                ('a', 'button', (1240, 450, 83, 81)), ('x', 'button', (1326, 436, 53, 60)),
                ('b', 'button', (1187, 502, 52, 52)),
                ('cstick', 'stick:right', (1268, 554, 102, 102), (1322, 606, 39), (1322.61, 605.73, 38.61)),
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
                ('main', 'stick:left', (201, 524, 108, 108), (254, 577, 43), (253.75, 576.71, 42.38)),
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
                ('main', 'stick:left', (650, 429, 104, 104), (702, 480, 41), (701.99, 478.54, 40.86)),
                ('dpad', 'dpad', (655, 553, 95, 92)), ('menu', 'button', (608, 630, 47, 48)),
                ('minus', 'button', (1195, 357, 43, 43)), ('home', 'button', (1258, 357, 43, 43)),
                ('plus', 'button', (1322, 357, 44, 43)),
                ('a', 'button', (1239, 440, 87, 86)), ('b', 'button', (1233, 534, 95, 49)),
                ('one', 'button', (1207, 602, 61, 61)), ('two', 'button', (1298, 602, 61, 61)),
            ],
        },
    },
    'ps2': {
        'id': 'ps2-pocket-original', 'name': 'PS2 Pocket — Original',
        'board': 'approved-ps2.png', 'gameType': 'public.aoshuang.game.ps2',
        # item kinds also: 'label' = an L3/R3 label under a stick, (glyph box) + the stick item
        'portrait': {
            'crop': (160, 112, 506, 862), 'black_above': 205, 'spill': True, 'seam': True, 'window': (167, 213, 504, 454),
            'items': [
                ('l2', 'button', (171, 471, 58, 34)), ('l1', 'button', (238, 471, 58, 34)),
                ('r1', 'button', (377, 471, 59, 34)), ('r2', 'button', (444, 471, 57, 34)),
                ('dpad', 'dpad', (189, 535, 114, 111)),
                ('triangle', 'button', (400, 528, 50, 46)), ('square', 'button', (356, 566, 50, 46)),
                ('circle', 'button', (443, 566, 51, 46)), ('cross', 'button', (400, 607, 50, 47)),
                ('select', 'button', (260, 671, 59, 25)), ('start', 'button', (350, 671, 60, 25)),
                ('l3', 'label', (211, 796, 21, 14), 'lstick'),
                ('lstick', 'stick:left', (167, 691, 118, 118), (224, 749, 36)),
                ('r3', 'label', (442, 796, 22, 14), 'rstick'),
                ('rstick', 'stick:right', (389, 690, 118, 118), (448, 748, 36)),
                ('menu', 'button', (313, 777, 45, 44)),
            ],
        },
        'landscape': {
            'crop': (582, 339, 1394, 700), 'spill': True, 'seam': True, 'window': (785, 356, 1181, 642),
            'erase_fill': [(587, 463, 629, 588)], 'erase_rows': [(886, 682, 1086, 694)],
            # The portrait board's Menu button (centre, radius with its halo), at the landscape scale.
            'paste': [{'from': (335, 798, 27), 'to': (622, 660)}],
            'items': [
                ('l1', 'button', (619, 354, 70, 31)), ('l2', 'button', (700, 354, 67, 31)),
                ('r1', 'button', (1206, 354, 74, 31)), ('r2', 'button', (1291, 354, 75, 31)),
                ('dpad', 'dpad', (642, 415, 111, 111)),
                ('l3', 'label', (689, 633, 21, 14), 'lstick'),
                ('lstick', 'stick:left', (640, 530, 114, 114), (697, 587, 36)),
                ('select', 'button', (656, 656, 81, 31)),
                ('menu', 'button', (600, 638, 44, 44)),
                ('triangle', 'button', (1262, 405, 50, 44)), ('square', 'button', (1212, 446, 50, 44)),
                ('circle', 'button', (1312, 446, 50, 44)), ('cross', 'button', (1262, 486, 50, 46)),
                ('r3', 'label', (1264, 633, 22, 14), 'rstick'),
                ('rstick', 'stick:right', (1218, 530, 114, 114), (1275, 587, 37)),
                ('start', 'button', (1230, 656, 80, 31)),
            ],
        },
    },
}
INPUTS = {'gc': {'l', 'r', 'z', 'y', 'x', 'a', 'b', 'start', 'menu'},
          'wii': {'c', 'z', 'a', 'b', 'one', 'two', 'minus', 'home', 'plus', 'menu'},
          'ps2': {'cross', 'circle', 'square', 'triangle', 'l1', 'l2', 'r1', 'r2', 'select', 'start',
                  'l3', 'r3', 'menu'}}
MAPPING_WIDTH = {'portrait': 393.0, 'landscape': 852.0}
PACKS_CROP_WIDTH = {'portrait': 346, 'landscape': 812}  # crop widths shared by every board (same phone template)


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
    # A tall island on a curved grip (PS2 landscape): a smooth (harmonic) fill from the
    # body all around it, so neither a row nor a column streak crosses the grip's curves.
    for ex0, ey0, ex1, ey1 in spec.get('erase_fill', []):
        cx0, cy0, cx1, cy1 = ex0 - x0, ey0 - y0, ex1 - x0, ey1 - y0
        patch = a[cy0 - 1:cy1 + 1, cx0 - 1:cx1 + 1].copy()
        inner = patch[1:-1, 1:-1]
        inner[:] = patch[[0, -1]].mean(axis=(0, 1))
        for _ in range(4000):
            inner[:] = (patch[:-2, 1:-1] + patch[2:, 1:-1] + patch[1:-1, :-2] + patch[1:-1, 2:]) / 4
        a[cy0:cy1, cx0:cx1] = inner
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')
    for paste in spec.get('paste', []):
        # A control the board draws in the other orientation only (PS2 landscape Menu): its
        # own pixels, at this orientation's scale, blended into the body by a soft disc.
        sx, sy, sr = paste['from']
        tx, ty = paste['to']
        scale = (MAPPING_WIDTH['portrait'] / (PACKS_CROP_WIDTH['portrait'])) / (
            MAPPING_WIDTH['landscape'] / (x1 - x0))
        source = board.crop((sx - sr, sy - sr, sx + sr, sy + sr)).convert('RGB')
        size = round(2 * sr * scale)
        source = source.resize((size, size), Image.Resampling.LANCZOS)
        disc = Image.new('L', (size * 4, size * 4), 0)
        ImageDraw.Draw(disc).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
        disc = disc.resize((size, size), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(size * 0.06))
        im.paste(source, (round(tx - x0 - size / 2), round(ty - y0 - size / 2)), disc)
    wx0, wy0, wx1, wy1 = spec['window']
    # The window becomes plain navy ("Zone de jeu" removed); its rounded corners are kept.
    a = np.asarray(im).astype(np.int16)
    box = a[wy0 - y0:wy1 - y0, wx0 - x0:wx1 - x0]
    navy = (box[..., 2] > 35) & (box[..., 0] < 60) & (box[..., 2] - box[..., 0] > 12)
    board_navy = box[navy].mean(axis=0).round().astype(np.int16)  # the board's own navy
    text = ~navy
    # Interior only (2 px in): the window's own light border stays.
    text[:3, :] = False; text[-3:, :] = False; text[:, :3] = False; text[:, -3:] = False
    if 'window_text' in spec:
        # Only the placeholder text's own box (a window shaped around another part of
        # the body, e.g. the Switch board's top tab, keeps that part).
        tx0, ty0, tx1, ty1 = spec['window_text']
        keep = np.zeros_like(text)
        keep[ty0 - wy0:ty1 - wy0, tx0 - wx0:tx1 - wx0] = True
        text &= keep
    box[navy | text] = board_navy
    a[wy0 - y0:wy1 - y0, wx0 - x0:wx1 - x0] = box
    return Image.fromarray(a.astype(np.uint8), 'RGB')


def _flood_from(free: np.ndarray, seeds) -> np.ndarray:
    """Pixels of `free` connected to any of `seeds` (4-connectivity, PIL flood fill)."""
    img = Image.fromarray(free.astype(np.uint8) * 255, 'L').copy()  # own buffer: fromarray may share a read-only one
    for x, y in seeds:
        if img.getpixel((x, y)) == 255:
            ImageDraw.floodfill(img, (x, y), 128)
    return np.asarray(img) == 128


def _border(shape):
    h, w = shape
    return [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]


def _grow(mask: np.ndarray, n: int) -> np.ndarray:
    if n <= 0: return mask
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255, 'L').filter(ImageFilter.MaxFilter(2 * n + 1))) > 127


def _shrink(mask: np.ndarray, n: int) -> np.ndarray:
    if n <= 0: return mask
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255, 'L').filter(ImageFilter.MinFilter(2 * n + 1))) > 127


def _segment(screen: Image.Image, box, pad: int, close: int, cuts=()):
    bx, by, bw, bh = box
    x0, y0 = max(0, bx - pad), max(0, by - pad)
    x1, y1 = min(screen.width, bx + bw + pad), min(screen.height, by + bh + pad)
    a = np.asarray(screen.crop((x0, y0, x1, y1)).convert('RGB')).astype(np.int16)
    lum, sat = a.mean(axis=2), a.max(axis=2) - a.min(axis=2)
    edge = np.concatenate([lum[0], lum[-1], lum[:, 0], lum[:, -1]])
    body = np.median(edge)
    # The control's stroke: darker than the body around it (22 levels on the white boards;
    # 40 % of the body's level on a dark one, whose outlines are near black) or coloured.
    stroke = (lum < body - min(22, 0.4 * body)) | (sat > 60)
    barrier = _grow(stroke, close)
    outside = _flood_from(~barrier, _border(lum.shape))
    inside = ~outside
    holes = ~_flood_from(~inside, _border(lum.shape)) & ~inside
    filled = inside | holes
    mask = _shrink(filled, close) | (stroke & filled)
    # Seams between controls drawn touching (screen px): no outline crosses them.
    for cx0, cy0, cx1, cy1 in cuts:
        line = Image.new('L', (mask.shape[1], mask.shape[0]), 0)
        ImageDraw.Draw(line).line((cx0 - x0, cy0 - y0, cx1 - x0, cy1 - y0), fill=255, width=1)
        mask &= np.asarray(line) == 0
    mask = _flood_from(mask, [(bx + bw // 2 - x0, by + bh // 2 - y0)])
    return x0, y0, mask


def shape_mask(screen: Image.Image, box, reach: int = 10, cuts=()):
    """The control's real outline in the board screen (board pixels): everything enclosed
    by its drawn stroke (or its coloured face), reached from the centre of `box` (the
    box measured by hand on the board). Several margins and gap closings are tried; the
    accepted outline covers at least 45 % of the box and leaves it by `reach` pixels at
    most (a leak into the body or a neighbour is refused). Returns (x0, y0, mask)."""
    bx, by, bw, bh = box
    best = None
    for pad in (8, 12, 22):
        for close in (1, 2, 3):
            x0, y0, mask = _segment(screen, box, pad, close, cuts)
            ys, xs = np.nonzero(mask)
            if xs.size == 0: continue
            left, top, right, bottom = x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1
            out = max(bx - left, by - top, right - (bx + bw), bottom - (by + bh), 0)
            cover = mask[max(0, by - y0):by - y0 + bh, max(0, bx - x0):bx - x0 + bw].mean()
            if cover < 0.45 or out > reach: continue
            score = (out, -cover)
            if best is None or score < best[0]:
                best = (score, x0, y0, mask)
    if best is None:
        raise ValueError(f'no control outline found in {box}')
    _, x0, y0, mask = best
    # One board pixel inside the outer edge: the soft drop shadow below a control is
    # body, not control, and must not darken when it is pressed.
    return x0, y0, _shrink(mask, 1)


def pill_mask(extent, x0: int, y0: int):
    """A stadium (rounded ends of half its height) through a measured outline (board
    px, exclusive right/bottom), one pixel inside it, as (x, y, mask) in screen px."""
    ex0, ey0, ex1, ey1 = extent
    w, h, ss = ex1 - ex0, ey1 - ey0, 4
    big = Image.new('L', (w * ss, h * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=h * ss / 2, fill=255)
    m = np.asarray(big.resize((w, h), Image.Resampling.BOX)) >= 128
    return ex0 - x0, ey0 - y0, _shrink(m, 1)


def layout_masks(screen: Image.Image, spec: dict, x0: int, y0: int, margin: int = 4) -> dict:
    """Every button's outline in one layout, made disjoint: each one stays within its
    measured box (plus `margin`), and a pixel claimed by two controls (a shared drop
    shadow) goes to the one whose box centre is nearer."""
    boxes, masks = {}, {}
    for entry in spec['items']:
        label, kind, (bx, by, bw, bh) = entry[:3]
        if kind.startswith('stick') or kind == 'label': continue
        box = (bx - x0, by - y0, bw, bh)
        cuts = [(cx0 - x0, cy0 - y0, cx1 - x0, cy1 - y0) for cx0, cy0, cx1, cy1 in spec.get('cuts', ())]
        if label in spec.get('shapes', {}):
            # A light 3D pill whose faint upper outline no stroke threshold closes (Switch
            # Pocket): its outline measured on the board (pill_extent), one pixel inside.
            mx, my, m = pill_mask(spec['shapes'][label], x0, y0)
        else:
            mx, my, m = shape_mask(screen, box, reach=10, cuts=cuts)
        full = np.zeros((screen.height, screen.width), bool)
        full[my:my + m.shape[0], mx:mx + m.shape[1]] = m
        clip = np.zeros_like(full)
        clip[max(0, box[1] - margin):box[1] + bh + margin, max(0, box[0] - margin):box[0] + bw + margin] = True
        masks[label], boxes[label] = full & clip, box
    yy, xx = np.mgrid[:screen.height, :screen.width]
    labels = list(masks)
    for i, a in enumerate(labels):
        for b in labels[:i]:
            both = masks[a] & masks[b]
            if not both.any(): continue
            ca = (boxes[a][0] + boxes[a][2] / 2, boxes[a][1] + boxes[a][3] / 2)
            cb = (boxes[b][0] + boxes[b][2] / 2, boxes[b][1] + boxes[b][3] / 2)
            to_a = np.hypot(xx - ca[0], yy - ca[1]) <= np.hypot(xx - cb[0], yy - cb[1])
            masks[b] &= ~(both & to_a)
            masks[a] &= ~(both & ~to_a)
    # Neighbours that still touch (PS2 face buttons, rims nearly meeting; spec 'seam'): a
    # one-pixel seam between them, taken from both, so no sampling of the sprites can make
    # two drawn shapes meet. (GameCube/Wii keep their reviewed outlines unchanged.)
    for i, a in enumerate(labels if spec.get('seam') else []):
        for b in labels[:i]:
            seam = (_grow(masks[a], 1) & masks[b]) | (_grow(masks[b], 1) & masks[a])
            if not seam.any(): continue
            masks[a] &= ~seam
            masks[b] &= ~seam
    out = {}
    for label, full in masks.items():
        ys, xs = np.nonzero(full)
        ox, oy = xs.min(), ys.min()
        out[label] = (ox, oy, full[oy:ys.max() + 1, ox:xs.max() + 1])
    return out


def socket_radius(screen: Image.Image, cx: float, cy: float, r: float) -> float:
    """Outer radius of a stick's socket (its dark rim), in board pixels."""
    lum = np.asarray(screen.convert('L')).astype(np.float32)
    yy, xx = np.mgrid[:lum.shape[0], :lum.shape[1]]
    d = np.hypot(xx - cx, yy - cy)
    prof = [float(lum[(d >= k) & (d < k + 1)].mean()) for k in range(int(r * 2))]
    body = float(np.median(prof[int(r * 1.7):]))
    darkest = int(r) + int(np.argmin(prof[int(r):int(r * 1.7)]))
    outer = next(k for k in range(darkest, len(prof)) if prof[k] > body - 20)
    return float(outer)


def cap_radius(r: float) -> float:
    """The moving cap: the circle measured on the board fits its face; 12 % more takes
    its bevel and lower lip, so nothing of the cap stays behind when it moves (and at
    rest the cap sprite over its socket is the board itself)."""
    return r * 1.12


def pressed_face(normal: Image.Image, alpha: Image.Image, scale: int) -> Image.Image:
    """The control pushed into its well, inside its own outline only (same alpha as the
    normal sprite, so nothing outside the outline ever changes).

    What a real button does when a thumb pushes it, seen from above with the board's
    light (upper left): the whole cap, label and bevel included, moves down and away
    (shifted 1.3 board pixels, 3 % smaller); the wall of the well appears above it, in
    shadow; the lip of the well shades the cap's upper left; the cap's lower lip and its
    drop shadow go under the outline; the face loses a little light and its highlights."""
    w, h = normal.size
    rgb = normal.convert('RGB')
    a = np.asarray(rgb).astype(np.float32)
    m = np.asarray(alpha).astype(np.float32) / 255
    shrink, drop = 0.97, 1.3 * scale
    # The cap, smaller around its centre and lower.
    sw, sh = max(1, round(w * shrink)), max(1, round(h * shrink))
    ox, oy = (w - sw) // 2, (h - sh) // 2 + round(drop)
    cap = Image.new('RGB', (w, h))
    cap.paste(rgb.resize((sw, sh), Image.Resampling.LANCZOS), (ox, oy))
    cap_alpha = Image.new('L', (w, h), 0)
    cap_alpha.paste(alpha.resize((sw, sh), Image.Resampling.LANCZOS), (ox, oy))
    c = np.asarray(cap).astype(np.float32)
    ca = np.asarray(cap_alpha).astype(np.float32) / 255
    # The well behind it: the control's own colours in deep shade, darkest at the top.
    ramp = np.linspace(0.34, 0.52, h, dtype=np.float32)[:, None, None]
    well = a * ramp
    # The well's lip shades the cap from the upper left; the cap's own contact shadow
    # falls on the wall just around it.
    outside = Image.fromarray(((1 - m) * 255).astype(np.uint8), 'L')
    lip = np.asarray(ImageChops.offset(outside, round(1.2 * scale), round(2.2 * scale)).filter(
        ImageFilter.GaussianBlur(1.8 * scale))).astype(np.float32) / 255
    face = c * (0.88 - 0.34 * np.clip(lip * 1.5, 0, 1))[..., None]
    lum = face.mean(axis=2, keepdims=True)
    face = np.where(lum > 190, 190 + (face - 190) * 0.6, face)  # a pushed-in face catches less light
    soft = np.asarray(cap_alpha.filter(ImageFilter.GaussianBlur(0.9 * scale))).astype(np.float32) / 255
    well = well * (1 - 0.35 * np.clip(soft - ca, 0, 1))[..., None]
    out = face * ca[..., None] + well * (1 - ca[..., None])
    rgba = np.dstack([np.clip(out, 0, 255).astype(np.uint8), np.asarray(alpha)])
    return Image.fromarray(rgba, 'RGBA')


def with_alpha(image: Image.Image, alpha: Image.Image) -> Image.Image:
    rgba = image.convert('RGB').copy()
    rgba.putalpha(alpha)
    return rgba


def socket_fill(base: Image.Image, cx: float, cy: float, r: float) -> Image.Image:
    """Removes the cap from a stick base: the hole is filled from the ring around it,
    darker toward the centre, so the moving cap never leaves a copy of itself."""
    a = np.asarray(base.convert('RGB')).astype(np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    dist = np.hypot(xx - cx, yy - cy)
    angle = np.arctan2(yy - cy, xx - cx)
    # The socket floor just outside the cap and its lower lip, sampled per angle.
    ring = (dist > r * 1.01) & (dist < r * 1.09)
    bins = 72
    idx = ((angle + math.pi) / (2 * math.pi) * bins).astype(int) % bins
    colours = np.zeros((bins, 3), np.float32)
    for b in range(bins):
        sel = ring & (idx == b)
        px = a[sel] if sel.any() else a[ring]
        # The socket's floor, not its light bevel: the darker quarter of the band, so the
        # fill seen beside the moving cap never reads as a second cap edge.
        lum = px.mean(axis=1)
        colours[b] = px[lum <= np.percentile(lum, 25)].mean(axis=0)
    inside = dist <= r  # the whole cap (cap_radius), lip included
    t = np.clip(dist / r, 0, 1)[..., None]
    fill = colours[idx] * (0.55 + 0.45 * t)
    a[inside] = fill[inside]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


# A measured whole cap (GameCube/Wii): the knob takes the cap up to its outline plus its
# own antialiased edge; the socket under it is refilled a little wider, so no edge pixel of
# the cap stays behind when it moves (board px).
CAP_EDGE = 0.4
CAP_FILL = 1.2


def _jacobi(a: np.ndarray, mask: np.ndarray, iterations: int) -> np.ndarray:
    for _ in range(iterations):
        p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode='edge')
        avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 4
        a[mask] = avg[mask]
    return a


def recess_fill(base: Image.Image, cx: float, cy: float, r: float) -> Image.Image:
    """Removes a whole cap from its socket (GameCube/Wii): the circle is refilled from the
    socket or gate pixels all round it (a harmonic fill, so one homogeneous floor with no
    disc edge, no streak and no copy of the cap), a little darker toward the middle."""
    a = np.asarray(base.convert('RGB')).astype(np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    inside = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) <= r
    # Coarse solve (board resolution), then refine at full resolution.
    small = (max(1, w // UPSCALE), max(1, h // UPSCALE))
    sa = np.asarray(Image.fromarray(a.astype(np.uint8)).resize(small, Image.Resampling.BOX)).astype(np.float32)
    sm = np.asarray(Image.fromarray(inside.astype(np.uint8) * 255).resize(small, Image.Resampling.BOX)) > 0
    sa[sm] = sa[~sm].mean(axis=0)
    sa = _jacobi(sa, sm, 2500)
    init = np.asarray(Image.fromarray(np.clip(sa, 0, 255).astype(np.uint8)).resize((w, h), Image.Resampling.BICUBIC)).astype(np.float32)
    a[inside] = init[inside]
    a = _jacobi(a, inside, 400)
    t = np.clip(np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) / r, 0, 1)
    a[inside] *= (0.88 + 0.12 * t[inside] ** 2)[:, None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


def cap_sprite(board_screen_up: Image.Image, cx: float, cy: float, r: float) -> Image.Image:
    d = 2 * r
    crop = board_screen_up.crop((round(cx - r), round(cy - r), round(cx - r + d), round(cy - r + d))).convert('RGBA')
    alpha = Image.new('L', (crop.width * 4, crop.height * 4), 0)
    ImageDraw.Draw(alpha).ellipse((2, 2, alpha.width - 3, alpha.height - 3), fill=255)
    crop.putalpha(alpha.resize(crop.size, Image.Resampling.LANCZOS))
    return crop


def circle_sprite(board_screen_up: Image.Image, ux: int, uy: int, ud: int) -> Image.Image:
    """The whole cap: a ud x ud crop at whole upscaled pixels, a circle with an antialiased
    edge inscribed in it (its declared size is exactly ud / UPSCALE board px)."""
    crop = board_screen_up.crop((ux, uy, ux + ud, uy + ud)).convert('RGBA')
    alpha = Image.new('L', (ud * 4, ud * 4), 0)
    ImageDraw.Draw(alpha).ellipse((0, 0, ud * 4 - 1, ud * 4 - 1), fill=255)
    crop.putalpha(alpha.resize((ud, ud), Image.Resampling.LANCZOS))
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
    aspect = spec.get('aspect', 4 / 3)  # the game's own ratio (Switch: 16:9)
    if ww / wh > aspect:
        sw, sh = wh * aspect, wh
    else:
        sw, sh = ww, ww / aspect
    sx, sy = wx0 + (ww - sw) / 2, wy0 + (wh - sh) / 2
    screen_rect = bp.rect(round((sx - x0) * k, 3), round((sy - y0) * k, 3), round(sw * k, 3), round(sh * k, 3))
    masks = layout_masks(screen, spec, x0, y0)
    pills = label_targets(spec, masks, x0, y0, k, H, orientation)
    items, shapes = [], []
    for entry in spec['items']:
        label, kind, (bx, by, bw, bh) = entry[:3]
        key = f'{orientation}-{label}'
        if kind.startswith('stick'):
            # The cap's centre on the board is the stick's centre for drawing, touch and
            # vector alike: a square frame centred on it, as wide as the socket (inside its
            # outer rim), so the cap travels inside its socket and saturates at the rim.
            cx, cy, hand_r = entry[3]
            top = entry[4] if len(entry) > 4 else None
            outer = socket_radius(screen, cx - x0, cy - y0, hand_r)
            if top is None:
                # The whole cap moves (PS2: a dome and its crown seen from above).
                kcx, kcy, r, off = cx, cy, cap_radius(hand_r), 0.0
            else:
                # GameCube/Wii: the whole measured cap moves, as one circle (device
                # recordings of 4-5 Nov: a 1.12 r disc took socket texture with it, a top
                # face left its side wall behind). Snapped to whole upscaled pixels with an
                # even diameter, so the knob, its declared size and the frame share one
                # centre exactly.
                mcx, mcy, cap_r = top
                ud = 2 * round((cap_r + CAP_EDGE) * UPSCALE)
                ux, uy = round((mcx - x0) * UPSCALE - ud / 2), round((mcy - y0) * UPSCALE - ud / 2)
                kcx, kcy, r = x0 + (ux + ud / 2) / UPSCALE, y0 + (uy + ud / 2) / UPSCALE, ud / 2 / UPSCALE
                off = math.hypot(kcx - cx, kcy - cy)
            # Travel = half - cap radius: up to the socket's rim, and never less than 22 %
            # of the cap (a tight octagonal C-stick socket would otherwise hold it still;
            # at full deflection it then rides on its rim, as a real cap does).
            half = max(outer - 2 - off, r * 1.22)
            if top is not None:
                half = round(half * UPSCALE) / UPSCALE
            fx0, fy0, fw, fh = kcx - x0 - half, kcy - y0 - half, 2 * half, 2 * half
            box = tuple(round(v * UPSCALE) for v in (fx0, fy0, fx0 + fw, fy0 + fh))
            lcx, lcy, lr = (kcx - x0) * UPSCALE - box[0], (kcy - y0) * UPSCALE - box[1], r * UPSCALE
            if top is None:
                base = socket_fill(up.crop(box), lcx, lcy, lr)
            else:
                base = recess_fill(up.crop(box), (mcx - x0) * UPSCALE - box[0], (mcy - y0) * UPSCALE - box[1],
                                   (cap_r + CAP_FILL) * UPSCALE)
            disk = Image.new('L', (base.width * 4, base.height * 4), 0)
            ImageDraw.Draw(disk).ellipse((2, 2, disk.width - 3, disk.height - 3), fill=255)
            disk = disk.resize(base.size, Image.Resampling.LANCZOS)
            for target, (px0, py0, px1, py1, stick) in pills.items():
                if stick != label: continue
                # The label's touch area below the cap belongs to the label (its own sprite):
                # the socket leaves it out, so the drawn shapes never overlap.
                cut = Image.new('L', base.size, 0)
                ImageDraw.Draw(cut).rectangle(tuple(round(v * UPSCALE) - o for v, o in zip(
                    (px0, py0, px1, py1), (box[0], box[1], box[0], box[1]))), fill=255)
                disk = ImageChops.subtract(disk, cut)
            for other in spec.get('socket_cuts', {}).get(label, ()):
                # A control drawn on this stick's socket ring (Switch L3/R3 pills): the
                # socket leaves out its outline (one board pixel wider), so the drawn
                # shapes never overlap and the pill answers its own touches.
                ox, oy, m = masks[other]
                grown = Image.fromarray(_grow(m, 1).astype(np.uint8) * 255, 'L')
                grown = grown.resize((grown.width * UPSCALE, grown.height * UPSCALE), Image.Resampling.NEAREST)
                cut = Image.new('L', base.size, 0)
                cut.paste(grown, (ox * UPSCALE - box[0], oy * UPSCALE - box[1]))
                disk = ImageChops.subtract(disk, cut)
            files[f'controls/{key}-base.png'] = bp.png(with_alpha(base, disk))
            # Held: the socket only darkens a little under the moving cap (no other change).
            held = Image.fromarray(np.clip(np.asarray(base).astype(np.float32) * 0.9, 0, 255).astype(np.uint8), 'RGB')
            files[f'controls/{key}-base-pressed.png'] = bp.png(with_alpha(held, disk))
            if top is None:
                files[f'controls/{key}-knob.png'] = bp.png(cap_sprite(up, (kcx - x0) * UPSCALE, (kcy - y0) * UPSCALE, lr))
            else:
                files[f'controls/{key}-knob.png'] = bp.png(circle_sprite(up, ux, uy, ud))
            side = kind.split(':')[1]
            frame = bp.rect(round(fx0 * k, 3), round(fy0 * k, 3), round(fw * k, 3), round(fh * k, 3))
            item = {'frame': frame,
                    'inputs': {d: f'{side}Thumbstick{d.title()}' for d in ('up', 'down', 'left', 'right')},
                    'asset': {'normal': f'controls/{key}-base.png', 'pressed': f'controls/{key}-base-pressed.png'},
                    'thumbstick': {'name': f'controls/{key}-knob.png', 'width': round(2 * r * k, 3), 'height': round(2 * r * k, 3)}}
            alpha = disk
        elif kind == 'label':
            # PS2 L3/R3: the board's label under a stick. Its touch area is a rounded band
            # just below the cap at rest; the sprite is the board itself (invisible at rest)
            # and a press dims the label's letters only.
            px0, py0, px1, py1, _ = pills[label]
            box = tuple(round(v * UPSCALE) for v in (px0, py0, px1, py1))
            normal = up.crop(box)
            band = Image.new('L', (normal.width * 4, normal.height * 4), 0)
            radius = min(band.width, band.height) // 2
            ImageDraw.Draw(band).rounded_rectangle((0, 0, band.width - 1, band.height - 1), radius=radius, fill=255)
            alpha = band.resize(normal.size, Image.Resampling.LANCZOS)
            files[f'controls/{key}.png'] = bp.png(with_alpha(normal, alpha))
            a = np.asarray(normal).astype(np.float32)
            gx0, gy0 = round((bx - x0) * UPSCALE) - box[0], round((by - y0) * UPSCALE) - box[1]
            glyph = np.zeros(a.shape[:2], bool)
            glyph[max(0, gy0):gy0 + bh * UPSCALE, max(0, gx0):gx0 + bw * UPSCALE] = True
            glyph &= a.mean(axis=2) > 110
            soft = np.asarray(Image.fromarray(glyph.astype(np.uint8) * 255, 'L').filter(
                ImageFilter.GaussianBlur(0.6 * UPSCALE))).astype(np.float32)[..., None] / 255
            dim = a * (1 - 0.6 * np.clip(soft * 1.4, 0, 1))
            pressed = np.dstack([np.clip(dim, 0, 255).astype(np.uint8), np.asarray(alpha)])
            files[f'controls/{key}-pressed.png'] = bp.png(Image.fromarray(pressed, 'RGBA'))
            frame = bp.rect(round(px0 * k, 3), round(py0 * k, 3), round((px1 - px0) * k, 3), round((py1 - py0) * k, 3))
            item = {'frame': frame, 'inputs': [label],
                    'asset': {'normal': f'controls/{key}.png', 'pressed': f'controls/{key}-pressed.png'}}
        else:
            # The control's real outline: frame = its bounding box (never trimmed), sprites
            # transparent outside it, so the rest state is the board and a press changes
            # only the control itself.
            mx, my, m = masks[label]
            ys, xs = np.nonzero(m)
            fx0, fy0, fx1, fy1 = mx + xs.min(), my + ys.min(), mx + xs.max() + 1, my + ys.max() + 1
            full = np.zeros((fy1 - fy0, fx1 - fx0), bool)
            full[ys + my - fy0, xs + mx - fx0] = True
            box = tuple(v * UPSCALE for v in (fx0, fy0, fx1, fy1))
            normal = up.crop(box)
            alpha = Image.fromarray(full.astype(np.uint8) * 255, 'L').resize(normal.size, Image.Resampling.BILINEAR)
            alpha = alpha.filter(ImageFilter.GaussianBlur(0.35 * UPSCALE))
            files[f'controls/{key}.png'] = bp.png(with_alpha(normal, alpha))
            # An inert control (Switch HOME/Capture: no Core input) does not look pressed.
            files[f'controls/{key}-pressed.png'] = bp.png(
                with_alpha(normal, alpha) if label in spec.get('inert', ()) else pressed_face(normal, alpha, UPSCALE))
            inputs = {d: d for d in ('up', 'down', 'left', 'right')} if kind == 'dpad' else [label]
            frame = bp.rect(round(fx0 * k, 3), round(fy0 * k, 3), round((fx1 - fx0) * k, 3), round((fy1 - fy0) * k, 3))
            item = {'frame': frame, 'inputs': inputs,
                    'asset': {'normal': f'controls/{key}.png', 'pressed': f'controls/{key}-pressed.png'}}
        item['extendedEdges'] = dict(top=0, bottom=0, left=0, right=0)
        items.append(item)
        shapes.append(np.asarray(alpha) >= 128)
    # No invisible extension into the home-indicator band of the smallest edge-to-edge
    # iPhone (34 pt portrait = 36 mapping pt; 21 pt landscape, 7 pt of it letterbox).
    extend_targets(items, shapes, W, H, screen_rect, bottom_limit=H - (36 if orientation == 'portrait' else 15),
                   spill=spec.get('spill', False), margin=spec.get('extend_margin', 0),
                   fine=spec.get('spill_fine', False))
    # The game's container is the window the board draws (its rounded corners), redrawn at
    # the picture's own ratio (screen_opening.reframe: the frame comes forward where the
    # drawn window is wider or taller than the game); `screen_rect` only kept the touch
    # extensions clear, unchanged.
    seed = ((sx + sw / 2 - x0) * UPSCALE, (sy + sh / 2 - y0) * UPSCALE)
    drawn = screen_opening.opening(up, seed)
    body, _, changed = screen_opening.reframe(up, drawn, (W, H), aspect)
    kx, ky = up.width / W, up.height / H
    for index, item in enumerate(items):
        f, e = item['frame'], item.get('extendedEdges', {})
        bx0, by0 = int((f['x'] - e.get('left', 0)) * kx), int((f['y'] - e.get('top', 0)) * ky)
        bx1 = int((f['x'] + f['width'] + e.get('right', 0)) * kx) + 1
        by1 = int((f['y'] + f['height'] + e.get('bottom', 0)) * ky) + 1
        assert not changed[max(0, by0):by1, max(0, bx0):bx1].any(), (console, orientation, index, 'control under the redrawn window')
    files[name] = bp.png(body)
    coverage = screen_opening.opening(body, seed)
    files[f'screens/{orientation}.png'] = screen_opening.cutout(coverage)
    opening = {'outputFrame': screen_opening.native_frame(coverage, (W, H), aspect), 'screenCutout': f'screens/{orientation}.png'}
    return {'assets': {'small': name, 'medium': name, 'large': name}, 'mappingSize': {'width': W, 'height': H},
            'screens': [opening], 'items': items, 'translucent': False}


def label_targets(spec, masks, x0, y0, k, H, orientation):
    """PS2 L3/R3 touch areas (screen board pixels): a band centred on the label, from just
    below its stick's cap at rest (the cap is the stick's) down to the first control under it
    or the home-indicator band, 46.4 mapping pt wide and tall at most. Returns
    {label: (x0, y0, x1, y1, stick)}."""
    sticks = {e[0]: (e[3][0] - x0, e[3][1] - y0, cap_radius(e[3][2])) for e in spec['items'] if e[1].startswith('stick')}
    want = 46.4 / k
    limit = (H - (36 if orientation == 'portrait' else 15)) / k
    pills = {}
    for entry in spec['items']:
        label, kind, (bx, by, bw, bh) = entry[:3]
        if kind != 'label': continue
        scx, scy, rc = sticks[entry[3]]
        cx = bx - x0 + bw / 2
        width = max(want, bw + 8)
        left, right = cx - width / 2, cx + width / 2
        top = scy + rc + 0.1
        bottom = min(top + want, limit)
        for name, (mx, my, m) in masks.items():
            ys, xs = np.nonzero(m)
            ox0, ox1, oy0 = mx + xs.min(), mx + xs.max() + 1, my + ys.min()
            if ox1 > left and ox0 < right and oy0 > top:
                bottom = min(bottom, oy0 - 1)
        pills[label] = (left, top, right, bottom, entry[3])
    return pills


def hit(item):
    f, e = item['frame'], item['extendedEdges']
    return (f['x'] - e['left'], f['y'] - e['top'], f['x'] + f['width'] + e['right'], f['y'] + f['height'] + e['bottom'])


def overlaps(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > 0.01 and min(a[3], b[3]) - max(a[1], b[1]) > 0.01


GRID = 4  # samples per mapping point for the shape-aware target checks


def _raster(rect, W, H):
    g = np.zeros((int(math.ceil(H * GRID)), int(math.ceil(W * GRID))), bool)
    x0, y0, x1, y1 = (max(0, int(math.floor(v * GRID))) for v in rect)
    g[y0:int(math.ceil(rect[3] * GRID)), x0:int(math.ceil(rect[2] * GRID))] = True
    return g


def _shape_raster(item, shape, W, H):
    """An item's drawn shape (sprite alpha) on the mapping grid."""
    f = item['frame']
    g = np.zeros((int(math.ceil(H * GRID)), int(math.ceil(W * GRID))), bool)
    x0, y0 = int(round(f['x'] * GRID)), int(round(f['y'] * GRID))
    w, h = max(1, int(round(f['width'] * GRID))), max(1, int(round(f['height'] * GRID)))
    s = np.asarray(Image.fromarray(shape.astype(np.uint8) * 255, 'L').resize((w, h), Image.Resampling.NEAREST)) > 127
    y1, x1 = min(g.shape[0], y0 + h), min(g.shape[1], x0 + w)
    g[y0:y1, x0:x1] = s[:y1 - y0, :x1 - x0]
    return g


def extend_targets(items, shapes, W, H, screen, target=46.4, bottom_limit=None, spill=False, margin=0, fine=False):
    """Invisible extended edges until each touch area reaches `target` mapping pt (44 pt fitted
    on the smallest edge-to-edge iPhone, 375 x 812). An extension never covers another
    control's frame or touch area (frames may overlap where the board's shapes interlock;
    DOLSkinOverlay resolves those by the drawn shape), the game screen or the outside.
    `spill` (PS2): what a blocked side cannot take goes to the opposite side (SELECT/START
    between the D-pad and the sticks); without it the two sides grow alike only."""
    scr = (screen['x'], screen['y'], screen['x'] + screen['width'], screen['y'] + screen['height'])
    rasters = [None] * len(items)

    def others(i):
        g = np.zeros((int(math.ceil(H * GRID)), int(math.ceil(W * GRID))), bool)
        for j, o in enumerate(items):
            if j != i: g |= _raster(hit(o), W, H)
        # `margin` grid cells of clearance (Switch Pocket's tightly packed top band): two
        # extensions never meet in a coarser sampling either.
        return _grow(g, margin) if margin else g
    for i, item in enumerate(items):
        f = item['frame']
        frame = _raster((f['x'], f['y'], f['x'] + f['width'], f['y'] + f['height']), W, H)
        for axis, (lo, hi), size in (('x', ('left', 'right'), f['width']), ('y', ('top', 'bottom'), f['height'])):
            need = max(0.0, target - size) / 2
            if need <= 0: continue
            step = need / 20
            blocked = others(i)
            for _ in range(20):
                for side in (lo, hi):
                    item['extendedEdges'][side] = round(item['extendedEdges'][side] + step, 3)
                    h = hit(item)
                    floor = H if bottom_limit is None else max(bottom_limit, f['y'] + f['height'])
                    extension = _raster(h, W, H) & ~frame
                    if (h[0] < 0 or h[1] < 0 or h[2] > W or h[3] > floor or overlaps(h, scr) or
                            (extension & blocked).any()):
                        item['extendedEdges'][side] = round(item['extendedEdges'][side] - step, 3)
            if not spill: continue
            for _ in range(40):
                h = hit(item)
                if (h[2] - h[0] if axis == 'x' else h[3] - h[1]) >= target - 0.01: break
                grown = False
                for side in (lo, hi):
                    item['extendedEdges'][side] = round(item['extendedEdges'][side] + step, 3)
                    h = hit(item)
                    floor = H if bottom_limit is None else max(bottom_limit, f['y'] + f['height'])
                    extension = _raster(h, W, H) & ~frame
                    if (h[0] < 0 or h[1] < 0 or h[2] > W or h[3] > floor or overlaps(h, scr) or
                            (extension & blocked).any()):
                        item['extendedEdges'][side] = round(item['extendedEdges'][side] - step, 3)
                    else:
                        grown = True
                        break
                if not grown and fine and step > need / 160:
                    step /= 2  # `fine` (Switch Pocket): the last free fraction of a step too
                    continue
                if not grown: break


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
                'gameTypeIdentifier': pack['gameType'], 'version': 3, 'license': LICENSE_LABEL,
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
