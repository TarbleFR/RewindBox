#!/usr/bin/env python3
"""Measures the whole cap of each GameCube/Wii stick on the approved Pocket boards.

The cap is the complete round stick seen on the board (face, bevel and the side wall
seen below it; for the C-stick the yellow top and its darker yellow ring): everything that
moves together on a real stick. Its outline is the outermost strong edge where the cap
meets its socket or gate, read along 180 rays from the hand-measured centre (luminance for
the grey caps, yellowness R - B for the C-stick), then fitted with an axis-aligned ellipse
(least squares, points more than 1.5 px off rejected twice).

    python3 tools/skins/measure_stick_caps.py [--json out.json] [--sheet out.png]

The builder (build_pocket_board_originals.py) declares these values in its stick entries;
this tool reproduces them and draws them on the boards for review.
"""
import argparse, json, math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / 'docs/design/pocket'

# (board, label, hand centre x, y, hand radius, channel)
STICKS = [
    ('approved-gamecube.png', 'gamecube portrait main', 242, 584, 41, 'grey'),
    ('approved-gamecube.png', 'gamecube portrait cstick', 429, 725, 39, 'yellow'),
    ('approved-gamecube.png', 'gamecube landscape main', 695, 474, 38, 'grey'),
    ('approved-gamecube.png', 'gamecube landscape cstick', 1322, 606, 39, 'yellow'),
    ('approved-wii.png', 'wii portrait main', 254, 577, 43, 'grey'),
    ('approved-wii.png', 'wii landscape main', 702, 480, 41, 'grey'),
    # Switch Pocket: dark caps in a light socket ring (the edge is a rise outward).
    ('approved-switch.png', 'switch portrait lstick', 254, 584.5, 45, 'dark'),
    ('approved-switch.png', 'switch portrait rstick', 435.5, 718, 45, 'dark'),
    ('approved-switch.png', 'switch landscape lstick', 740, 470.5, 48, 'dark'),
    ('approved-switch.png', 'switch landscape rstick', 1423.5, 622, 48.5, 'dark'),
]
def board_file(name: str) -> Path:
    return DESIGN / name


def channel(img: Image.Image, kind: str) -> np.ndarray:
    a = np.asarray(img.convert('RGB')).astype(np.float64)
    if kind == 'yellow':
        return np.clip(a[..., 0] - a[..., 2], 0, None)
    if kind == 'dark':
        return -a.mean(axis=2)
    return a.mean(axis=2)


def bilinear(c: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    v00, v10 = c[y0, x0], c[y0, x0 + 1]
    v01, v11 = c[y0 + 1, x0], c[y0 + 1, x0 + 1]
    return (v00 * (1 - fx) + v10 * fx) * (1 - fy) + (v01 * (1 - fx) + v11 * fx) * fy


def edge_points(c: np.ndarray, cx: float, cy: float, r0: float, rays: int = 180,
                lo: float = 0.80, hi: float = 1.16, step: float = 0.2):
    """Per ray: the steepest outward drop between lo*r0 and hi*r0 (the cap's outline)."""
    t = np.arange(lo * r0, hi * r0, step)
    kernel = np.exp(-0.5 * (np.arange(-6, 7) * step / 0.6) ** 2)
    kernel /= kernel.sum()
    pts = []
    for k in range(rays):
        th = 2 * math.pi * k / rays
        x, y = cx + t * math.cos(th), cy + t * math.sin(th)
        v = np.convolve(bilinear(c, x, y), kernel, mode='same')
        d = np.gradient(v, step)
        d[:6], d[-6:] = 0, 0
        i = int(np.argmin(d))
        pts.append((float(x[i]), float(y[i]), float(-d[i])))
    return pts


def fit_ellipse(pts):
    """Axis-aligned ellipse A x^2 + C y^2 + D x + E y = 1; returns cx, cy, a, b, residuals."""
    p = np.array([(x, y) for x, y, _ in pts])
    keep = np.ones(len(p), bool)
    for _ in range(3):
        x, y = p[keep, 0], p[keep, 1]
        sol, *_ = np.linalg.lstsq(np.stack([x * x, y * y, x, y], 1), np.ones_like(x), rcond=None)
        A, C, D, E = sol
        cx, cy = -D / (2 * A), -E / (2 * C)
        G = 1 + A * cx * cx + C * cy * cy
        a, b = math.sqrt(G / A), math.sqrt(G / C)
        th = np.arctan2((p[:, 1] - cy) / b, (p[:, 0] - cx) / a)
        ex, ey = cx + a * np.cos(th), cy + b * np.sin(th)
        res = np.hypot(p[:, 0] - cx, p[:, 1] - cy) - np.hypot(ex - cx, ey - cy)
        keep = np.abs(res) <= 1.5
    return cx, cy, a, b, res, keep


def measure():
    out = {}
    for board, label, hx, hy, hr, kind in STICKS:
        img = Image.open(board_file(board))
        pts = edge_points(channel(img, kind), hx, hy, hr)
        cx, cy, a, b, res, keep = fit_ellipse(pts)
        out[label] = {
            'board': board_file(board).name, 'channel': kind, 'hand': [hx, hy, hr],
            'centre': [round(cx, 2), round(cy, 2)], 'semiAxes': [round(a, 2), round(b, 2)],
            'extents': [round(cx - a, 1), round(cy - b, 1), round(cx + a, 1), round(cy + b, 1)],
            'rays': len(pts), 'raysKept': int(keep.sum()),
            'residualP90': round(float(np.percentile(np.abs(res[keep]), 90)), 2),
            'points': [[round(x, 2), round(y, 2)] for x, y, _ in pts],
            'kept': keep.tolist(),
        }
    return out


def sheet(m, path: Path):
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20)
    cells, Z = [], 6
    for label, v in m.items():
        img = Image.open(board_file(v['board'])).convert('RGB')
        (cx, cy), (a, b) = v['centre'], v['semiAxes']
        R = int(max(a, b) * 1.35)
        x0, y0 = int(cx) - R, int(cy) - R
        c = img.crop((x0, y0, x0 + 2 * R, y0 + 2 * R)).resize((2 * R * Z, 2 * R * Z), Image.Resampling.NEAREST)
        d = ImageDraw.Draw(c)
        P = lambda x, y: ((x - x0) * Z, (y - y0) * Z)
        e0, e1 = P(cx - a, cy - b), P(cx + a, cy + b)
        d.ellipse((*e0, *e1), outline=(0, 210, 70), width=3)
        for (x, y), k in zip(v['points'], v['kept']):
            px, py = P(x, y)
            d.ellipse((px - 3, py - 3, px + 3, py + 3), fill=(230, 30, 30) if k else (40, 40, 255))
        o = Image.new('RGB', (c.width, c.height + 30), 'white')
        o.paste(c, (0, 30))
        ImageDraw.Draw(o).text((6, 4), f"{label}: {2 * a:.1f} x {2 * b:.1f} px", fill='black', font=font)
        cells.append(o)
    rows = [cells[i:i + 3] for i in range(0, len(cells), 3)]
    W = max(sum(c.width + 10 for c in r) for r in rows)
    H = sum(max(c.height for c in r) + 10 for r in rows)
    out = Image.new('RGB', (W, H), (205, 210, 220))
    y = 0
    for r in rows:
        x = 0
        for c in r:
            out.paste(c, (x, y))
            x += c.width + 10
        y += max(c.height for c in r) + 10
    out.thumbnail((2400, 2400))
    out.save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--json', type=Path)
    ap.add_argument('--sheet', type=Path)
    args = ap.parse_args()
    m = measure()
    for label, v in m.items():
        print(f"{label:28s} centre {v['centre']} semi-axes {v['semiAxes']} extents {v['extents']} "
              f"kept {v['raysKept']}/{v['rays']} p90 {v['residualP90']} px")
    if args.json:
        args.json.write_text(json.dumps(m, indent=1) + '\n')
    if args.sheet:
        sheet(m, args.sheet)


if __name__ == '__main__':
    main()
