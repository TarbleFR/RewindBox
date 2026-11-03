"""Original RewindBox PS2 Pocket (matte black) artwork, rendered procedurally.

Everything here is new, deterministic artwork drawn from signed distances with
the shader of pocket_art.py: no photograph, no third-party skin or game asset.
The reference picture supplied by the maintainer was used as a visual brief only.
Controls are separate sprites (normal / pressed); the body carries no control,
only housing, wells, vents, the PS2 wordmark and the non-interactive ANALOG
indicator. Sticks have a socket base and a separate knob moved by the host.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from pocket_art import (N, circle, font, grid, label, ring, rounded_box, shader, shadow)

GLYPH = {
    "triangle": (62, 201, 163),
    "circle": (237, 92, 98),
    "cross": (96, 146, 240),
    "square": (236, 134, 190),
}
FACE = (38, 39, 44)
PLATE = (31, 32, 36)
INK = (214, 218, 226, 255)
BLUE = (70, 118, 236)
# Canonical sprite ratio (width : height) of each rectangular control.
RATIO = {"l1": (3, 2), "l2": (3, 2), "r1": (3, 2), "r2": (3, 2), "select": (7, 4), "start": (7, 4),
         "l3": (5, 4), "r3": (5, 4)}
TEXT = {"l1": "L1", "l2": "L2", "r1": "R1", "r2": "R2", "select": "SELECT", "start": "START",
        "l3": "L3", "r3": "R3"}


def _glyph(im, name, cx, cy, radius, color):
    d = ImageDraw.Draw(im)
    width = max(8, round(radius * 0.17))
    if name == "triangle":
        pts = [(cx, cy - radius), (cx + radius * .94, cy + radius * .74), (cx - radius * .94, cy + radius * .74)]
        d.line(pts + [pts[0]], fill=color, width=width, joint="curve")
    elif name == "circle":
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=width)
    elif name == "square":
        r = radius * .86
        d.rounded_rectangle((cx - r, cy - r, cx + r, cy + r), 8, outline=color, width=width)
    else:
        r = radius * .86
        d.line((cx - r, cy - r, cx + r, cy + r), fill=color, width=width)
        d.line((cx - r, cy + r, cx + r, cy - r), fill=color, width=width)


def _dish(distance, pressed, color, height=16):
    im = shadow(distance, 3 if pressed else 8, .5, 4 if pressed else 7)
    im.alpha_composite(shader(distance - 3, (14, 14, 17), height=4, bevel=4, dome=0))
    shade = tuple(max(0, c - (10 if pressed else 0)) for c in color)
    im.alpha_composite(shader(distance, shade, height=4 if pressed else height, bevel=12,
                              dome=2 if pressed else 8, roughness=.8, metallic=.0, depressed=pressed))
    ring(im, distance, 4, (255, 255, 255, 38 if not pressed else 22), 2)
    if pressed:
        ring(im, distance, 9, BLUE + (170,), 3)
    return im


def control(name: str, pressed: bool = False) -> Image.Image:
    """Sprite of one PS2 control: face buttons, shoulders, select/start, L3/R3, menu, D-pad."""
    shift = 5 if pressed else -2
    if name in GLYPH:
        x, y = grid(N, N)
        y = y - (5 if pressed else -2)
        im = _dish(circle(x, y, 155), pressed, FACE)
        _glyph(im, name, N / 2, N / 2 + shift, 82, GLYPH[name] + (255,))
        return im
    if name == "menu":
        x, y = grid(N, N)
        y = y - (5 if pressed else -2)
        im = _dish(circle(x, y, 155), pressed, FACE)
        d = ImageDraw.Draw(im)
        for dy in (-34, 0, 34):
            d.rounded_rectangle((N / 2 - 62, N / 2 + shift + dy - 8, N / 2 + 62, N / 2 + shift + dy + 8), 8, fill=INK)
        return im
    if name == "dpad":
        x, y = grid(N, N)
        y = y - (5 if pressed else -2)
        distance = np.minimum(rounded_box(x, y, 54, 156, 12), rounded_box(x, y, 156, 54, 12))
        im = _dish(distance, pressed, (30, 31, 35), height=14)
        d = ImageDraw.Draw(im)
        cy = N / 2 + shift
        for ax, ay, angle in [(0, -112, 0), (0, 112, 180), (-112, 0, 270), (112, 0, 90)]:
            a = np.deg2rad(angle)
            pts = [(-14, 9), (0, -9), (14, 9)]
            pts = [(N / 2 + ax + px * np.cos(a) - py * np.sin(a), cy + ay + px * np.sin(a) + py * np.cos(a))
                   for px, py in pts]
            d.polygon(pts, fill=(150, 156, 168, 230))
        d.ellipse((N / 2 - 15, cy - 15, N / 2 + 15, cy + 15), fill=(20, 21, 24, 255), outline=(70, 74, 82, 255), width=2)
        return im
    if name in RATIO:
        rw, rh = RATIO[name]
        w, h = N, round(N * rh / rw)
        x, y = grid(w, h)
        y = y - (5 if pressed else -2)
        small = name in {"select", "start", "l3", "r3"}
        half_y = h / 2 - 22
        distance = rounded_box(x, y, w / 2 - 22, half_y, half_y)
        im = _dish(distance, pressed, FACE if not small else (34, 35, 40), height=14)
        label(im, TEXT[name], 74 if small and len(TEXT[name]) > 2 else 112 if len(TEXT[name]) <= 2 else 74,
              center=(w / 2, h / 2 + shift), color=INK[:3] + (255,))
        return im
    raise KeyError(name)


def stick_base(pressed: bool = False) -> Image.Image:
    x, y = grid()
    outer = circle(x, y, 175)
    im = shadow(outer, 7, .5, 9)
    im.alpha_composite(shader(outer, (44, 46, 52), height=11, bevel=11, dome=2, roughness=.7))
    ring(im, outer, 6, (255, 255, 255, 60), 3)
    socket = circle(x, y - 2, 143)
    im.alpha_composite(shader(socket, (16, 17, 20), height=5, bevel=20, dome=-3, roughness=.8))
    ring(im, socket, 4, (120, 126, 138, 120), 3)
    ring(im, socket, 16, (60, 64, 72, 150), 3)
    if pressed:
        ring(im, outer, 3, BLUE + (190,), 3)
    return im


def stick_knob() -> Image.Image:
    x, y = grid()
    distance = circle(x, y, 180)
    im = shadow(distance, 8, .55, 8)
    im.alpha_composite(shader(distance, (28, 29, 33), height=9, bevel=7, dome=0, roughness=.7))
    top = circle(x, y + 5, 167)
    im.alpha_composite(shader(top, (66, 69, 77), height=18, bevel=13, dome=3.7, roughness=.55, metallic=.05))
    ring(im, top, 4, (190, 196, 208, 140), 3)
    inner = circle(x, y + 5, 135)
    im.alpha_composite(shader(inner, (46, 48, 55), height=3, bevel=10, dome=-1.7, roughness=.8))
    for inset in (5, 11, 17):
        ring(im, inner, inset, (170, 176, 190, 45), 1)
    return im


def _noise(h, w, seed):
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1.6, (h, w, 1)).astype(np.float32)


def body(W, H, screen, items, *, orientation, analog_y=None, scale=2, seed=1) -> Image.Image:
    """Matte black housing of one layout, 4:3 window cut area in navy, no control drawn."""
    w, h = round(W * scale), round(H * scale)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :, None]
    base = np.array((26, 27, 31), np.float32)[None, None, :] * (1 - yy) + np.array((15, 16, 18), np.float32)[None, None, :] * yy
    base = base + (1 - xx * xx) * 5 + _noise(h, w, seed)
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)

    def px(r):
        return (r["x"] * scale, r["y"] * scale, (r["x"] + r["width"]) * scale, (r["y"] + r["height"]) * scale)

    sx0, sy0, sx1, sy1 = px(screen)
    pad = 6 * scale
    bezel = (210, 214, 224, 255) if orientation == "portrait" else (62, 65, 73, 255)
    d.rounded_rectangle((sx0 - pad, sy0 - pad, sx1 + pad, sy1 + pad), 14 * scale, fill=(12, 12, 14, 255),
                        outline=bezel, width=max(2, round(2.2 * scale)))
    d.rectangle((sx0, sy0, sx1 - 1, sy1 - 1), fill=(9, 22, 49, 255))  # window; the host cuts it out

    def well(cx, cy, r, tone=(11, 12, 14)):
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(2.2 * scale))
        layer = Image.new("RGBA", im.size, tone + (255,))
        layer.putalpha(mask)
        im.alpha_composite(layer)
        ImageDraw.Draw(im).ellipse((cx - r, cy - r, cx + r, cy + r), outline=(52, 55, 62, 255), width=max(1, scale))

    faces = [i["frame"] for i in items if i["inputs"] and isinstance(i["inputs"], list) and i["inputs"][0] in GLYPH]
    if faces:
        x0 = min(f["x"] for f in faces); x1 = max(f["x"] + f["width"] for f in faces)
        y0 = min(f["y"] for f in faces); y1 = max(f["y"] + f["height"] for f in faces)
        well((x0 + x1) / 2 * scale, (y0 + y1) / 2 * scale, max(x1 - x0, y1 - y0) / 2 * scale * 1.02, PLATE)
    for item in items:
        f = item["frame"]
        cx, cy = (f["x"] + f["width"] / 2) * scale, (f["y"] + f["height"] / 2) * scale
        if isinstance(item["inputs"], dict) and "up" in item["inputs"] and "thumbstick" not in item:
            well(cx, cy, f["width"] / 2 * scale * 1.05, PLATE)
        elif "thumbstick" in item:
            well(cx, cy, f["width"] / 2 * scale * 1.1)
    # Vents and the wordmark: housing details between the shoulders (portrait) or under the window.
    d = ImageDraw.Draw(im)
    if orientation == "portrait":
        cx, cy = W / 2 * scale, (sy1 / scale + 56) * scale
        logo = (cx, cy)
        vy = cy + 20 * scale
        vents = [(cx - 22 * scale, vy + i * 4 * scale, cx + 22 * scale, vy + i * 4 * scale) for i in range(3)]
    else:
        cx, cy = W / 2 * scale, (sy1 / scale + 21) * scale
        logo = (cx, cy)
        vents = [(cx - 190 * scale, cy + (i - 1) * 4 * scale, cx - 50 * scale, cy + (i - 1) * 4 * scale) for i in range(3)] + \
                [(cx + 50 * scale, cy + (i - 1) * 4 * scale, cx + 190 * scale, cy + (i - 1) * 4 * scale) for i in range(3)]
    for v in vents:
        d.line(v, fill=(44, 46, 52, 255), width=max(1, scale))
    d.text(logo, "PS2", font=font(15 * scale, True), anchor="mm", fill=BLUE + (255,))
    if orientation == "portrait":
        # ANALOG indicator: a lamp of the housing, not a control.
        ax, ay = W / 2 * scale, (analog_y or 700) * scale
        d.text((ax, ay - 16 * scale), "ANALOG", font=font(7.5 * scale, False), anchor="mm", fill=(118, 122, 132, 255))
        d.rounded_rectangle((ax - 12 * scale, ay - 4 * scale, ax + 12 * scale, ay + 4 * scale), 4 * scale,
                            fill=(60, 106, 232, 255), outline=(20, 30, 70, 255), width=max(1, scale))
    return im.convert("RGB")
