#!/usr/bin/env python3
"""The game opening a Pocket skin's body really draws, and the cutout made from it.

A RewindBox Pocket body draws a navy window for the game: rounded corners, sometimes a
part of the body reaching into it (Switch Pocket's top tab). The layouts used to declare a
4:3 (16:9) rectangle placed by hand inside that window: smaller than the opening (navy
bands), rectangular (it cut the frame's rounded corners), and on the home-button layouts
off by tens of points. The game's container is now the opening itself:

* `opening(body, seed)`: the navy window around `seed` (body pixels), as a coverage map
  (0 = body, 1 = game), antialiased from the art's own edge;
* `cutout(coverage)`: the PNG shipped in the pack (`screens[].screenCutout`): its alpha is
  where the BODY stays. The overlays use it as the body's mask, scaled with the body, so
  the hole is the drawn opening on every device (same transform as the skin);
* `frame(coverage, mapping)`: the opening's bounding box in mapping points
  (`screens[].outputFrame`): the emulator's surface. Whatever the surface draws outside
  the opening stays under the body.

Inside its container the emulator keeps the display mode the player chose (aspect ratio,
stretch): nothing here changes the picture's proportions.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

# Blueness (B - R) of a window pixel: the navy is 30-55, a white or black body about 0.
_NAVY_MIN = 10
_SMOOTH = 4    # body pixels: teeth narrower than twice this are not the opening's shape
_EDGE = 0.6    # body pixels: antialiasing of the cutout's edge


def _label(mask: np.ndarray, seed) -> np.ndarray:
    """Pixels of `mask` 4-connected to `seed` (x, y)."""
    from PIL import ImageDraw
    img = Image.fromarray(mask.astype(np.uint8) * 255, 'L').copy()
    if img.getpixel(seed) != 255:
        raise ValueError(f'no game window at {seed}')
    ImageDraw.floodfill(img, seed, 128)
    return np.asarray(img) == 128


def _erode(mask: np.ndarray, n: int, outside: bool = False) -> np.ndarray:
    """Erosion by an octagon of radius n (3x3 squares and crosses alternated); `outside`
    is what lies beyond the image."""
    m = mask.copy()
    for i in range(n):
        p = np.pad(m, 1, mode='constant', constant_values=outside)
        cross = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        m = cross if i % 2 else cross & p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:]
    return m


def _dilate(mask: np.ndarray, n: int) -> np.ndarray:
    return ~_erode(~mask, n, outside=True)


def _grow(mask: np.ndarray, n: int) -> np.ndarray:
    from PIL import ImageFilter
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255, 'L').filter(ImageFilter.MaxFilter(2 * n + 1))) > 127


def opening(body: Image.Image, seed) -> np.ndarray:
    """Coverage of the game opening around `seed` (x, y in body pixels), float 0..1."""
    a = np.asarray(body.convert('RGB')).astype(np.float32)
    blue = a[..., 2] - a[..., 0]
    navy = (blue > _NAVY_MIN) & (a[..., 0] < 80) & (a[..., 2] > 22) & (a[..., 2] < 110)
    region = _label(navy, (int(seed[0]), int(seed[1])))
    # Specks of noise inside the window belong to it.
    outside = _label(~region, (0, 0))
    region = ~outside
    # A clean outline that never leaves the drawn opening: a morphological opening by an
    # octagon of _SMOOTH pixels removes the teeth of a hand-drawn edge (highlights, the
    # antialiased border of a coloured rail) and keeps every corner wider than that.
    from PIL import ImageFilter
    smooth = Image.fromarray(_dilate(_erode(region, _SMOOTH), _SMOOTH).astype(np.uint8) * 255, 'L')
    # Antialiased edge (the body's mask is scaled with the body on the device).
    coverage = np.asarray(smooth.filter(ImageFilter.GaussianBlur(_EDGE))).astype(np.float32) / 255
    coverage[coverage < 0.02] = 0.0
    coverage[coverage > 0.98] = 1.0
    return coverage


def cutout(coverage: np.ndarray) -> bytes:
    """The pack's cutout PNG: alpha = where the body stays (255), 0 where the game shows."""
    alpha = np.round((1.0 - coverage) * 255).astype(np.uint8)
    image = Image.merge('LA', (Image.new('L', (alpha.shape[1], alpha.shape[0]), 0), Image.fromarray(alpha, 'L')))
    out = io.BytesIO()
    image.save(out, format='PNG', compress_level=9)
    return out.getvalue()


def frame(coverage: np.ndarray, mapping) -> dict:
    """Bounding box of the opening in mapping points (never smaller than the hole)."""
    ys, xs = np.nonzero(coverage > 0)
    kx, ky = coverage.shape[1] / mapping[0], coverage.shape[0] / mapping[1]
    x0, y0 = math.floor(xs.min() / kx * 1000) / 1000, math.floor(ys.min() / ky * 1000) / 1000
    x1, y1 = math.ceil((xs.max() + 1) / kx * 1000) / 1000, math.ceil((ys.max() + 1) / ky * 1000) / 1000
    return dict(x=x0, y=y0, width=round(x1 - x0, 3), height=round(y1 - y0, 3))


def coverage_of(cutout_png: bytes) -> np.ndarray:
    """Coverage (0..1) read back from a cutout PNG."""
    with Image.open(io.BytesIO(cutout_png)) as im:
        return 1.0 - np.asarray(im.convert('RGBA').getchannel('A')).astype(np.float32) / 255


# --- The opening at the game's own ratio (maintainer, 10 November) -------------------
#
# The drawn openings are not exactly 4:3 (16:9 on Switch Pocket): a picture fitted in them
# kept bands, stretching it would deform it. `reframe` redraws the opening at the game's
# ratio: the largest rounded rectangle of that ratio inside the drawn opening, centred on
# it, with the drawn opening's corner radius; where it is smaller, the skin's frame comes
# forward. The frame is synthesised from the body itself:
#
# * the rim of the window (its bevel, highlight and shadow) is the drawn rim, measured
#   side by side as a profile across the edge (median over the straight part of each
#   side) and laid along the new edge at the same distance;
# * beyond the rim, the body is the body around the opening, carried inward (normalised
#   convolution of the body ring, coarse to fine, controls and lettering left out as
#   outliers) with the body's own fine grain (seeded noise of the ring's measured spread);
# * the whole rim is redrawn from its own profile, so the opening is exactly the
#   rectangle on every side; nothing outside the drawn opening and 7 points around it
#   changes (callers check that no control is touched).

_RIM_IN, _RIM_OUT = 2.5, 3.0   # points, across the edge: the rim laid along the new edge
_REPAINT, _FEATHER = 5.0, 2.0  # points beyond the drawn edge: fully repainted, then blended


def _rounded_rect_sdf(X, Y, x0, y0, w, h, r):
    """Signed distance (points, > 0 outside) to a rounded rectangle."""
    cx, cy = x0 + w / 2, y0 + h / 2
    qx = np.abs(X - cx) - (w / 2 - r)
    qy = np.abs(Y - cy) - (h / 2 - r)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    return outside + np.minimum(np.maximum(qx, qy), 0) - r


def _corner_radius(inside, kx, ky, box):
    """Radius (points) of the drawn opening's corners, from the area they cut off."""
    x0, y0, x1, y1 = box
    n = int(round(30 * kx)), int(round(30 * ky))
    radii = []
    for sx, sy in ((x0, y0), (x1 - n[0], y0), (x0, y1 - n[1]), (x1 - n[0], y1 - n[1])):
        missing = (~inside[sy:sy + n[1], sx:sx + n[0]]).sum() / (kx * ky)
        radii.append(math.sqrt(missing / (1 - math.pi / 4)))
    return float(np.median(radii))


def _profile(a, s, select, step):
    """Median colour per signed distance bin over the selected pixels (bins of `step`)."""
    lo, hi = -_RIM_IN - 0.5, _RIM_OUT + 0.5
    grid = np.arange(lo, hi + step, step)
    vals = np.full((len(grid), 3), np.nan, np.float32)
    ss, cols = s[select], a[select]
    idx = np.round((ss - lo) / step).astype(int)
    for i in range(len(grid)):
        m = idx == i
        if m.sum() >= 8:
            vals[i] = np.median(cols[m], axis=0)
    good = ~np.isnan(vals[:, 0])
    for c in range(3):
        vals[:, c] = np.interp(grid, grid[good], vals[good, c])
    return grid, vals


def reframe(body: Image.Image, coverage: np.ndarray, mapping, ratio: float, seed=0):
    """(new body, outputFrame): the opening redrawn at `ratio` (width / height, points)."""
    from scipy import ndimage
    a = np.asarray(body.convert('RGB')).astype(np.float32)
    H, W = coverage.shape
    kx, ky = W / mapping[0], H / mapping[1]
    inside = coverage >= 0.5
    ys, xs = np.nonzero(inside)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    bx0, by0, bx1, by1 = box[0] / kx, box[1] / ky, box[2] / kx, box[3] / ky
    w, h = bx1 - bx0, by1 - by0
    if w / ratio <= h:
        nw, nh = round(w, 3), round(w / ratio, 3)
    else:
        nw, nh = round(h * ratio, 3), round(h, 3)
    nx0, ny0 = round((bx0 + bx1) / 2 - nw / 2, 3), round((by0 + by1) / 2 - nh / 2, 3)
    frame_pt = dict(x=nx0, y=ny0, width=nw, height=nh)
    r = _corner_radius(inside, kx, ky, box)
    X = ((np.arange(W) + 0.5) / kx)[None, :]
    Y = ((np.arange(H) + 0.5) / ky)[:, None]
    sampling = (1 / ky, 1 / kx)
    s_old = np.where(inside, -ndimage.distance_transform_edt(inside, sampling=sampling),
                     ndimage.distance_transform_edt(~inside, sampling=sampling)).astype(np.float32)
    s_new = _rounded_rect_sdf(X, Y, nx0, ny0, nw, nh, r).astype(np.float32)

    # The drawn rim, side by side, over the straight part of each edge.
    step = 0.5 / max(kx, ky)
    first_row = np.where(inside.any(axis=0), inside.argmax(axis=0), -1)
    last_row = np.where(inside.any(axis=0), H - 1 - inside[::-1].argmax(axis=0), -1)
    first_col = np.where(inside.any(axis=1), inside.argmax(axis=1), -1)
    last_col = np.where(inside.any(axis=1), W - 1 - inside[:, ::-1].argmax(axis=1), -1)
    band = (s_old > -_RIM_IN - 0.5) & (s_old < _RIM_OUT + 0.5)
    rows, colsg = np.indices((H, W))
    cxp, cyp = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    profiles = {}
    for side, edge, along, near in (
            ('top', first_row, slice(box[0], box[2]), rows < cyp),
            ('bottom', last_row, slice(box[0], box[2]), rows >= cyp),
            ('left', first_col, slice(box[1], box[3]), colsg < cxp),
            ('right', last_col, slice(box[1], box[3]), colsg >= cxp)):
        e = edge[along]
        valid = e >= 0
        mode = np.bincount(e[valid]).argmax()
        straight = np.zeros(len(edge), bool)
        straight[along] = valid & (np.abs(e - mode) <= 1)
        # The corners are not the straight edge.
        m = int(round((r + 4) * (kx if side in ('top', 'bottom') else ky)))
        idx = np.nonzero(straight)[0]
        if len(idx) > 2 * m:
            straight[:idx.min() + m] = False
            straight[idx.max() - m + 1:] = False
        sel = band & near & (straight[None, :] if side in ('top', 'bottom') else straight[:, None])
        profiles[side] = _profile(a, s_old, sel, step)

    def rim(s, side):
        grid, vals = profiles[side]
        return np.stack([np.interp(s, grid, vals[:, c]) for c in range(3)], axis=-1)

    # Which sides a pixel faces on the new rectangle (blend at the corners).
    cxn, cyn = nx0 + nw / 2, ny0 + nh / 2
    qx = np.abs(X - cxn) - (nw / 2 - r)
    qy = np.abs(Y - cyn) - (nh / 2 - r)
    wx = np.clip(qx, 0, None) + 1e-6 * (qx >= qy)
    wy = np.clip(qy, 0, None) + 1e-6 * (qy > qx)
    wx, wy = np.broadcast_to(wx, (H, W)), np.broadcast_to(wy, (H, W))
    wsum = wx + wy
    horiz = np.where(X < cxn, 0, 1)   # 0 left, 1 right
    vert = np.where(Y < cyn, 0, 1)    # 0 top, 1 bottom
    sn = np.clip(s_new, -_RIM_IN, _RIM_OUT)
    lr = np.where(np.broadcast_to(horiz, (H, W))[..., None] == 0, rim(sn, 'left'), rim(sn, 'right'))
    tb = np.where(np.broadcast_to(vert, (H, W))[..., None] == 0, rim(sn, 'top'), rim(sn, 'bottom'))
    rimc = (lr * wx[..., None] + tb * wy[..., None]) / wsum[..., None]

    # The body beyond the rim, carried in from the ring around the drawn opening.
    ring = (s_old > _REPAINT + _FEATHER) & (s_old < _REPAINT + _FEATHER + 4)

    def carry(mask):
        est = None
        for sigma in (48, 24, 12, 6, 3, 1.5):
            sg = (sigma * ky, sigma * kx)
            den = ndimage.gaussian_filter(mask.astype(np.float32), sg)
            num = np.stack([ndimage.gaussian_filter(a[..., c] * mask, sg) for c in range(3)], -1)
            cur = num / np.maximum(den, 1e-6)[..., None]
            if est is None:
                est = cur
            else:
                wgt = np.clip(den / 0.2, 0, 1)[..., None]
                est = wgt * cur + (1 - wgt) * est
        return est

    fill = carry(ring)
    # Controls, lettering and coloured trims (Switch Pocket's rails) are not the frame.
    median = np.median(a[ring], axis=0) if ring.any() else np.zeros(3)
    clean = ring & (np.abs(a - fill).mean(axis=-1) < 24) & (np.abs(a - median).max(axis=-1) < 45)
    fill = carry(clean)
    grain = a - np.stack([ndimage.gaussian_filter(a[..., c], 1.0) for c in range(3)], -1)
    spread = grain[clean].std(axis=0) if clean.any() else np.zeros(3)
    noise = np.random.default_rng(seed).standard_normal((H, W, 1)).astype(np.float32)
    noise = ndimage.gaussian_filter(noise[..., 0], 0.5)[..., None]
    noise *= (spread.mean() / max(float(noise.std()), 1e-6))
    t = np.clip((s_new - _RIM_OUT) / 1.0, 0, 1)[..., None]
    synth = (1 - t) * rimc + t * (fill + noise)

    # Where to repaint: the drawn opening's rim and whatever of it the new window leaves.
    reach = np.clip((_REPAINT + _FEATHER - s_old) / _FEATHER, 0, 1)
    keep_navy = (s_new < -_RIM_IN)  # inside the new window: the drawn navy stays
    weight = np.where(keep_navy, 0, reach)[..., None]
    out = a * (1 - weight) + synth * weight
    image = Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), 'RGB')
    changed = weight[..., 0] > 0
    return image, frame_pt, changed


def native_frame(coverage: np.ndarray, mapping, ratio: float) -> dict:
    """The game's surface (mapping points) at exactly `ratio`, over the opening's visible
    part (coverage >= 0.5): centred on it, the smallest rectangle of that ratio covering
    it (the drawn opening is that ratio within a fraction of a point)."""
    ys, xs = np.nonzero(coverage >= 0.5)
    kx, ky = coverage.shape[1] / mapping[0], coverage.shape[0] / mapping[1]
    x0, x1 = xs.min() / kx, (xs.max() + 1) / kx
    y0, y1 = ys.min() / ky, (ys.max() + 1) / ky
    h = max(y1 - y0, (x1 - x0) / ratio)
    w = h * ratio
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = round(w, 3), round(w / ratio, 3)
    return dict(x=round(cx - w / 2, 3), y=round(cy - h / 2, 3), width=w, height=h)
