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
