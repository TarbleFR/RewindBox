"""Original RewindBox Pocket sprites reconstructed after workspace maintenance.

These are new deterministic renders, not recovered bytes from the lost renderer.
Surface heights are derived from signed distances; their normals drive a small
orthographic material shader. Background photographs are never altered here.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONT = HERE / "fonts" / "DejaVuSans.ttf"
BOLD = HERE / "fonts" / "DejaVuSans-Bold.ttf"
N = 384


def font(size: float, bold: bool = False):
    return ImageFont.truetype(str(BOLD if bold else FONT), max(8, round(size)))


def png(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.save(out, format="PNG", compress_level=9)
    return out.getvalue()


def grid(w=N, h=N):
    yy, xx = np.mgrid[:h, :w].astype(np.float64)
    return xx - (w - 1) / 2, yy - (h - 1) / 2


def circle(x, y, radius):
    return np.hypot(x, y) - radius


def rounded_box(x, y, half_x, half_y, radius):
    qx, qy = np.abs(x) - half_x + radius, np.abs(y) - half_y + radius
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius


def octagon(x, y, radius):
    # Intersection of eight half planes; metric is exact along each bevel.
    return np.maximum.reduce([x*np.cos(a)+y*np.sin(a)-radius for a in np.arange(8)*np.pi/4])


def smoothstep(low, high, x):
    t = np.clip((x-low)/(high-low), 0, 1)
    return t*t*(3-2*t)


def shader(distance, color, *, height=18, bevel=10, dome=2.6,
           roughness=.32, metallic=.04, depressed=False):
    """Height-field normals with a broad softbox and a small glossy reflection."""
    inside = np.maximum(-distance, 0)
    edge = np.clip(inside/bevel, 0, 1)
    profile = np.sin(edge*np.pi/2)
    z = height*profile + dome*(1-np.exp(-inside/38))
    zy, zx = np.gradient(z)
    normal = np.stack((-zx, -zy, np.ones_like(z)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    light = np.array([-.40, -.58, .71]); light /= np.linalg.norm(light)
    half = light + np.array([0, 0, 1]); half /= np.linalg.norm(half)
    lambert = np.maximum(normal @ light, 0)
    spec = np.maximum(normal @ half, 0) ** (28 + 115*(1-roughness))
    x, y = grid(distance.shape[1], distance.shape[0])
    # A second broad reflected light gives lacquer its softer, realistic sheen.
    softbox = np.exp(-((x+65)/130)**2 - ((y+95)/67)**2)
    base = np.array(color, dtype=np.float64)[None, None, :]
    shade = .65 + .47*lambert
    shade *= 1 - (y / max(distance.shape))*.15
    if depressed:
        shade *= .88
    rgb = base*shade[..., None] + (spec*(60+metallic*75)+softbox*24)[..., None]
    # The bevel is a real normal transition; a thin contact rim remains darker.
    rgb *= (.77+.23*smoothstep(0, 3.5, inside))[..., None]
    alpha = np.clip(.5-distance, 0, 1)
    return Image.fromarray(np.dstack((np.clip(rgb, 0, 255).astype(np.uint8),
                                    (alpha*255).astype(np.uint8))), "RGBA")


def shadow(distance, offset=8, opacity=.35, blur=6):
    mask = Image.fromarray((np.clip(.5-distance, 0, 1)*255).astype(np.uint8), "L")
    mask = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda a: round(a*opacity))
    layer = Image.new("RGBA", mask.size, (26, 28, 33, 0))
    layer.putalpha(mask)
    result = Image.new("RGBA", mask.size)
    result.alpha_composite(layer, (0, offset))
    return result


def ring(im, distance, inset, color, thickness=2):
    strength = np.clip(thickness/2+.5-np.abs(distance+inset), 0, 1)
    layer = np.zeros((*distance.shape, 4), dtype=np.uint8)
    layer[..., :3] = color[:3]
    layer[..., 3] = np.asarray(strength*color[3], dtype=np.uint8)
    im.alpha_composite(Image.fromarray(layer, "RGBA"))


def label(im, text, size, *, center=None, color=(66, 70, 74, 255), bold=True):
    x, y = center or (im.width/2, im.height/2)
    d = ImageDraw.Draw(im)
    # A minute engraving highlight beneath the ink avoids a flat printed look.
    d.text((x, y+1.3), text, font=font(size, bold), anchor="mm", fill=(255, 255, 255, 90))
    d.text((x, y), text, font=font(size, bold), anchor="mm", fill=color)


def control(name, console, pressed=False):
    pill = name in {"l", "r", "c", "z", "start"} or (name == "b" and console == "wii")
    w, h = (N, 230) if pill else (N, N)
    x, y = grid(w, h)
    y = y - (5 if pressed else -2)
    if name == "dpad":
        a = rounded_box(x, y, 52, 152, 10)
        b = rounded_box(x, y, 152, 52, 10)
        distance = np.minimum(a, b)
    elif name in {"x", "y"} and console == "gc":
        angle = np.deg2rad(-23 if name == "y" else 20)
        u, v = x*np.cos(angle)+y*np.sin(angle), -x*np.sin(angle)+y*np.cos(angle)
        if name == "y":
            # Bent oblong: convex outside and a modest concave inner shoulder.
            v = v + .0018*u*u
            distance = rounded_box(u, v, 155, 101, 95)
        else:
            u = u - .0018*v*v
            distance = rounded_box(u, v, 101, 155, 95)
    elif pill:
        distance = rounded_box(x, y, 162, 77, 73)
    else:
        distance = circle(x, y, 155)

    color = (241, 241, 237)
    if name == "dpad":
        color = (169, 174, 179)
    elif console == "gc":
        color = {"a": (29, 178, 126), "b": (212, 49, 56), "z": (130, 96, 198),
                 "x": (206, 208, 209), "y": (211, 212, 212)}.get(name, color)
    im = shadow(distance, 4 if pressed else 9, .40, 5 if pressed else 7)
    # Dark seat, polished lower wall, and domed top are distinct material bands.
    im.alpha_composite(shader(distance-3, (101, 104, 107), height=4, bevel=4, dome=0))
    im.alpha_composite(shader(distance, color, height=5 if pressed else 17,
                              bevel=12, dome=3 if pressed else 10,
                              roughness=.24 if console == "gc" and name in {"a", "b", "z"} else .42,
                              depressed=pressed))
    ring(im, distance, 5, (255, 255, 255, 110 if pressed else 185), 2)
    ring(im, distance, 10, (255, 255, 255, 36), 1)
    cy = h/2 + (5 if pressed else -2)
    fg = (248, 251, 250, 255) if console == "gc" and name in {"a", "b", "z"} else (69, 72, 75, 255)
    if name == "dpad":
        d = ImageDraw.Draw(im)
        ink = (105, 112, 118, 170)
        for ax, ay, angle in [(0,-112,0),(0,112,180),(-112,0,270),(112,0,90)]:
            points = [(-9,6),(0,-6),(9,6)]
            a = np.deg2rad(angle)
            points = [(w/2+ax+px*np.cos(a)-py*np.sin(a),cy+ay+px*np.sin(a)+py*np.cos(a)) for px,py in points]
            d.polygon(points, fill=ink)
        d.ellipse((w/2-10,cy-10,w/2+10,cy+10),fill=(164,170,175,255),outline=(131,139,145,255),width=2)
    elif name == "home":
        d = ImageDraw.Draw(im); cx=w/2
        points=[(cx-44,cy-2),(cx,cy-42),(cx+44,cy-2),(cx+29,cy-2),(cx+29,cy+35),(cx-29,cy+35),(cx-29,cy-2)]
        d.polygon(points,fill=(43,160,216,255)); d.rounded_rectangle((cx-8,cy+10,cx+8,cy+35),2,fill=(229,231,229,255))
    elif name == "menu":
        d=ImageDraw.Draw(im)
        for dy in (-25,0,25):d.rounded_rectangle((w/2-48,cy+dy-5,w/2+48,cy+dy+5),4,fill=fg)
    else:
        text={"one":"1","two":"2","minus":"−","plus":"+","start":"START"}.get(name,name.upper())
        size = 56 if name == "start" else 87 if pill else 104 if name in {"a","b"} else 90
        label(im,text,size,center=(w/2,cy),color=fg)
    return im


def base(pressed=False, cstick=False):
    x,y=grid(); radius=np.hypot(x,y)
    outer = circle(x,y,175)
    im=shadow(outer,7,.27,9)
    im.alpha_composite(shader(outer,(236,236,232),height=11,bevel=11,dome=2,roughness=.5))
    ring(im,outer,6,(255,255,255,210),3)
    # A recessed socket. No cap is baked into this base: the native knob moves.
    socket = circle(x,y-2,143)
    wall = shader(socket,(115,120,125),height=5,bevel=20,dome=-3,roughness=.39)
    im.alpha_composite(wall)
    if cstick:
        gate=octagon(x,y-2,119)
        im.alpha_composite(shader(gate,(164,137,67),height=6,bevel=7,dome=0,roughness=.35,metallic=.23))
        ring(im,gate,4,(229,209,150,210),3)
        cavity=octagon(x,y-2,100)
    else:
        ring(im,socket,4,(239,240,239,210),3)
        ring(im,socket,16,(77,84,91,180),3)
        cavity=circle(x,y-2,116)
    im.alpha_composite(shader(cavity,(100,105,111),height=0,bevel=8,dome=-1,roughness=.8))
    if pressed: ring(im,outer,3,(112,158,181,180),3)
    return im


def knob(cstick=False):
    x,y=grid(); distance=circle(x,y,180)
    im=shadow(distance,8,.44,8)
    color=(241,187,29) if cstick else (167,174,185)
    im.alpha_composite(shader(distance,(151,108,13) if cstick else (104,111,121),height=9,bevel=7,dome=0,roughness=.38))
    top=circle(x,y+5,167)
    im.alpha_composite(shader(top,color,height=18,bevel=13,dome=3.7,roughness=.24 if cstick else .6,metallic=.10))
    ring(im,top,4,(255,246,198,180) if cstick else (239,243,250,205),3)
    if cstick:
        ring(im,top,14,(211,151,11,180),2)
        label(im,"C",110,center=(N/2,N/2-3),color=(154,111,9,255))
    else:
        # A shallow dished rubber cap and concentric fine tactile ridges.
        inner=circle(x,y+5,135)
        im.alpha_composite(shader(inner,(186,191,201),height=3,bevel=10,dome=-1.7,roughness=.72))
        for inset in (5,11,17): ring(im,inner,inset,(232,236,245,45),1)
        ring(im,inner,2,(135,145,160,150),2)
    return im
