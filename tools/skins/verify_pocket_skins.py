#!/usr/bin/env python3
"""Verify the shipped Pocket archives (Wii, GameCube, PS2 and the two approved-board
Originals) and their iPhone geometry offline.

Requires Pillow. This checks packaged files and the native renderer's layout
selection/aspect fit; it does not run an emulator or claim device play testing.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

from PIL import Image

PREFIX = "assets/skins/pocket/"
PHONES = ((375, 667), (375, 812), (390, 844), (393, 852), (430, 932))
ESSENTIALS = {
    "gc": {"a", "b", "x", "y", "z", "l", "r", "start", "menu",
           "up", "down", "left", "right", "stickUp", "stickDown", "stickLeft", "stickRight",
           "cUp", "cDown", "cLeft", "cRight"},
    "wii": {"a", "b", "c", "z", "one", "two", "plus", "minus", "home", "menu",
            "up", "down", "left", "right", "stickUp", "stickDown", "stickLeft", "stickRight"},
    # PS2 (ARMSX2): the logical names of ARMSX2SkinOverlay; the right stick is rstick*.
    "ps2": {"cross", "circle", "square", "triangle", "l1", "l2", "r1", "r2", "select", "start", "l3", "r3", "menu",
            "up", "down", "left", "right", "stickUp", "stickDown", "stickLeft", "stickRight",
            "rstickUp", "rstickDown", "rstickLeft", "rstickRight"},
    # Switch (MeloNX): MeloNXSkinOverlay's names; home / capture are drawn and said
    # (the embedded Core has no index for them), menu is the RewindBox session menu.
    "switch": {"a", "b", "x", "y", "l", "r", "zl", "zr", "minus", "plus", "l3", "r3", "home", "capture", "menu",
               "up", "down", "left", "right", "stickUp", "stickDown", "stickLeft", "stickRight",
               "rstickUp", "rstickDown", "rstickLeft", "rstickRight"},
}
STICKS = {"gc": 2, "wii": 1, "ps2": 2, "switch": 2}
GAME_TYPES = {"gc": {"ngc", "gc", "gamecube"}, "wii": {"wii"}, "ps2": {"ps2"}, "switch": {"switch"}}
RAW_BODY_CONSOLES = {"gc", "wii"}
BOARD_DIR = Path(__file__).resolve().parents[2]/"docs/design/pocket"
# Physical model for packs drawn from an approved board (device points, portrait
# orientation): sensor housing (w, h, distance from the top edge) and display corner
# radius. Those layouts reproduce the board's margins instead of the conservative
# safeAreaInsets rectangle, so they are checked against the hardware they avoid.
HOUSINGS = {(375, 812): ((209, 30, 0), 39), (390, 844): ((162, 33, 0), 47),
            (393, 852): ((126, 37, 11), 55), (430, 932): ((126, 37, 11), 55)}
# Board-faithful placements that a sensor housing partly covers in ONE landscape rotation
# (the boards draw the housing on the left; iOS also offers the opposite rotation).
# Closed list, keyed by (pack, orientation, first canonical input): any other intrusion
# fails. Each one is measured in the report and handed to the maintainer as a decision.
KNOWN_HOUSING_DEVIATIONS = {("gamecube-pocket-original", "landscape"): {"x", "cUp", "menu"},
                            ("ps2-pocket-original", "landscape"): {"circle"},
                            # Switch Pocket: the board draws a narrower housing over its left
                            # rail; the iPhone's (11-48 pt from the edge) reaches the outer
                            # corner of the left stick's and the D-pad's touch squares (their
                            # drawn cap and arms stay clear) and, in the opposite rotation,
                            # the right stick's square and the outer edge of A.
                            ("switch-pocket", "landscape"): {"a", "stickUp", "up", "rstickUp"}}
# Board-faithful targets the approved board leaves no room to grow to 44 pt (PS2
# Original landscape: L3/R3 labels stacked between the cap and SELECT/START, above the
# home-indicator band). Closed list keyed like the housing deviations, each with the
# smallest mapping size allowed; measured in the report, never presented as 44 pt.
KNOWN_SMALL_TARGETS = {("ps2-pocket-original", "landscape"): {"l3": 25.0, "r3": 25.0, "select": 38.0, "start": 38.0},
                       # Switch Pocket, touch areas grown into the free body (a side blocked by
                       # a neighbour gives its share to the other): portrait R3 sits on its
                       # stick's ring 7.7 pt above the home-indicator band, so it stops at
                       # 37.8 pt (growing more would cover the stick's square or enter the
                       # system gesture band); landscape L3 45.5 and R3 44.0 mapping pt
                       # (44 pt on a 393 pt iPhone, ~42-43 pt on a 375 pt one).
                       ("switch-pocket", "portrait"): {"r3": 37.5},
                       ("switch-pocket", "landscape"): {"l3": 45.0, "r3": 43.9}}
# Board placements drawn deeper than 3 pt into the home-indicator band (the PS2 board
# puts SELECT/START level with its own home bar, in the bottom corners, away from the
# centred indicator): closed list with the depth allowed, measured in the report.
KNOWN_BAND_DEPTHS = {("ps2-pocket-original", "landscape"): {"select": 5.5, "start": 5.5}}
EXPECTED_PACKS = {"wii-pocket": "wii", "gamecube-pocket": "gc", "ps2-pocket": "ps2",
                  "gamecube-pocket-original": "gc", "wii-pocket-original": "wii", "ps2-pocket-original": "ps2"}
# Switch Pocket (MeloNX), built from the maintainer's original reference board like the
# Originals (build_switch_pocket.py checks the PNG's SHA-256).
EXPECTED_PACKS["switch-pocket"] = "switch"
BOARD_PACKS = {"gamecube-pocket-original", "wii-pocket-original", "ps2-pocket-original", "switch-pocket"}
# Packs whose body draws a plain rectangular window, equal to the declared 4:3 screen.
# Every other pack ships the cutout of the opening its body draws (screens[].screenCutout).
RECTANGULAR_WINDOWS = {"ps2-pocket"}
# Drawn console buttons with no input in the embedded Core (MeloNX has no HOME/Capture
# index): they never look pressed, the session says so (MeloNXSkinSession).
INERT_CONTROLS = {"switch-pocket": {"home", "capture"}}


def game_opening(pack, layout, files, resource, mapping, label):
    """The layout's game screen is the opening its body draws: re-measured on the body,
    equal to the shipped cutout and to `outputFrame`. Returns the coverage (body pixels,
    1 = game). PS2 Pocket draws a plain rectangular window: no cutout, the 4:3 rectangle
    is that window exactly."""
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import screen_opening
    entry = layout["screens"][0]
    frame = entry["outputFrame"]
    body = resource(next(iter(layout["assets"].values()))).convert("RGB")
    kx, ky = body.width/mapping[0], body.height/mapping[1]
    measured = screen_opening.opening(body, ((frame["x"]+frame["width"]/2)*kx, (frame["y"]+frame["height"]/2)*ky))
    opening = screen_opening.frame(measured, mapping)
    if pack in RECTANGULAR_WINDOWS:
        require("screenCutout" not in entry, f"{label}: unexpected screen cutout")
        require(abs(frame["width"]/frame["height"]-4/3) < 0.001, f"{label}: screen is not 4:3")
        # Its body draws the window with square corners: the rectangle is the opening
        # (the smoothing of the measure rounds its corners by a few pixels at most).
        box = np.zeros(measured.shape, bool)
        box[round(frame["y"]*ky):round((frame["y"]+frame["height"])*ky), round(frame["x"]*kx):round((frame["x"]+frame["width"])*kx)] = True
        require(not ((measured > 0.5) & ~box).any(), f"{label}: the drawn window leaves the declared screen")
        # Within one body pixel (half a point) of its edge and the measure's corner smoothing.
        require((box & (measured < 0.5)).sum() < 0.003*box.sum(), f"{label}: the declared screen leaves the drawn window")
        return box.astype(np.float32)
    name = entry.get("screenCutout")
    require(isinstance(name, str) and name in files, f"{label}: missing screen cutout")
    safe_name(name)
    shipped = screen_opening.coverage_of(files[name])
    require(shipped.shape == measured.shape, f"{label}: the cutout is not the body's size")
    require(float(np.abs(shipped-measured).max()) <= 1/255+1e-6, f"{label}: the cutout is not the opening its body draws")
    require(all(abs(frame[k]-opening[k]) <= 0.0011 for k in ("x", "y", "width", "height")),
            f"{label}: outputFrame {frame} is not the opening's box {opening}")
    require(float((shipped > 0).mean()) > 0.05, f"{label}: no opening")
    return shipped


def over_opening(hit, coverage, mapping):
    """A touch area (mapping points) reaches the game opening (coverage, body pixels)."""
    kx, ky = coverage.shape[1]/mapping[0], coverage.shape[0]/mapping[1]
    x0, y0 = max(0, int(math.floor(hit[0]*kx))), max(0, int(math.floor(hit[1]*ky)))
    x1, y1 = int(math.ceil((hit[0]+hit[2])*kx)), int(math.ceil((hit[1]+hit[3])*ky))
    return bool((coverage[y0:y1, x0:x1] > 0).any())


def native_layout(representations, tall):
    # DOLSkinLayoutFor / ARMSX2SkinLayoutFor: edge-to-edge first on a tall iPhone,
    # standard first otherwise, then the other one.
    for display in (("edgeToEdge", "standard") if tall else ("standard", "edgeToEdge")):
        if display in representations:
            return display, representations[display]
    raise ValueError("no iPhone layout")


def housing_conflicts(hits, frames, device, orientation, portrait):
    """Fitted hit frames entering the sensor housing, the rounded display corners or the
    home-indicator band (34 pt portrait, 21 pt landscape) of a tall iPhone."""
    (hw, hh, gap), radius = HOUSINGS[portrait]
    W, H = device
    if orientation == "portrait":
        blocked = [((W-hw)/2, gap, hw, hh)]
        bottom = 34
    else:  # either landscape rotation: the housing can be on the left or on the right
        blocked = [(gap, (H-hw)/2, hh, hw), (W-gap-hh, (H-hw)/2, hh, hw)]
        bottom = 21
    problems, board_band, covered = [], [], []
    for index, ((x, y, w, h), frame) in enumerate(zip(hits, frames)):
        for b in blocked:
            if overlaps((x, y, w, h), b):
                problems.append((index, "sensor housing"))
                # largest strip of the touch area left uncovered beside the housing (w, h)
                strips = [(b[0]-x, h), (x+w-(b[0]+b[2]), h), (w, b[1]-y), (w, y+h-(b[1]+b[3]))]
                strip = max(((sw, sh) for sw, sh in strips if sw > 0 and sh > 0), key=lambda v: min(v), default=(0, 0))
                covered.append({"item": index, "side": "left" if b[0] < W/2 else "right",
                                "largestUncoveredStripPoints": [round(strip[0], 3), round(strip[1], 3)]})
        drawn_bottom = frame[1]+frame[3]
        if drawn_bottom > H-bottom+0.02:
            # The board itself places this control there: measured, reported as a deviation.
            board_band.append({"item": index, "drawnIntoBandPoints": round(drawn_bottom-(H-bottom), 3)})
        if y+h > max(H-bottom, drawn_bottom)+0.02:
            problems.append((index, "invisible extension in home indicator band"))
        for cx, cy in ((radius, radius), (W-radius, radius), (radius, H-radius), (W-radius, H-radius)):
            px, py = min(max(cx, x), x+w), min(max(cy, y), y+h)
            # nearest point of the hit frame to the corner centre, outside the corner square?
            corner_x = (px < radius) if cx == radius else (px > W-radius)
            corner_y = (py < radius) if cy == radius else (py > H-radius)
            far_x = x if cx == radius else x+w
            far_y = y if cy == radius else y+h
            if corner_x and corner_y and math.hypot(far_x-cx, far_y-cy) > radius+0.02:
                problems.append((index, "rounded corner"))
    return problems, board_band, covered


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rect(value):
    require(isinstance(value, dict), f"not a rectangle: {value!r}")
    result = tuple(float(value[key]) for key in ("x", "y", "width", "height"))
    require(all(math.isfinite(v) for v in result) and min(result[2:]) > 0, "invalid rectangle")
    return result


def inside(frame, bounds, epsilon=0.02):
    x, y, width, height = frame
    bx, by, bw, bh = bounds
    return x >= bx-epsilon and y >= by-epsilon and x+width <= bx+bw+epsilon and y+height <= by+bh+epsilon


def overlaps(a, b):
    return min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0]) > 0.02 and min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]) > 0.02


def safe_name(name):
    require(isinstance(name, str) and name and "\\" not in name, "invalid resource path")
    parsed = PurePosixPath(name)
    require(not parsed.is_absolute() and all(part not in ("..", ".", "") for part in name.split("/")),
            f"unsafe resource path: {name}")
    return name


def manifest_path(value, suffix):
    require(isinstance(value, str) and value.startswith(PREFIX), f"asset outside {PREFIX}: {value}")
    tail = value[len(PREFIX):]
    require(safe_name(tail) == tail and "/" not in tail and tail.endswith(suffix), f"bad asset: {value}")
    return tail


def raw_inputs(item):
    value = item.get("inputs")
    require(isinstance(value, (dict, list)), "control without inputs")
    values = list(value.values()) if isinstance(value, dict) else value
    require(values and all(isinstance(v, str) for v in values), "invalid inputs")
    return values


def canonical(console, raw):
    key = "".join(c.lower() for c in raw if c.isalnum())
    for prefix in ("leftthumbstick", "analogstick", "leftstick", "leftanalog", "analog", "thumbstick"):
        for direction in ("Up", "Down", "Left", "Right"):
            if key == prefix+direction.lower():
                return "stick"+direction
    for prefix in ("rightthumbstick", "rightstick", "rightanalog", "cstick", "c"):
        for direction in ("Up", "Down", "Left", "Right"):
            if key == prefix+direction.lower():
                return {"gc": "c", "wii": "pointer", "ps2": "rstick", "switch": "rstick"}[console]+direction
    for direction in ("up", "down", "left", "right"):
        if key in (direction, "dpad"+direction):
            return direction
    aliases = {"pause": "menu", "options": "menu", "quicksave": "quickSave", "quickload": "quickLoad"}
    if console == "gc":
        aliases.update({"r1": "z", "l2": "l", "r2": "r", "lefttrigger": "l", "righttrigger": "r"})
    elif console == "wii":
        aliases.update({"1": "one", "2": "two", "nunchukc": "c", "nunchukz": "z"})
    elif console == "switch":
        aliases = {"pause": "menu", "options": "menu", "select": "minus", "back": "minus", "start": "plus",
                   "leftstickclick": "l3", "lsclick": "l3", "ls": "l3", "rightstickclick": "r3", "rsclick": "r3",
                   "rs": "r3", "screenshot": "capture"}
    else:
        aliases = {"pause": "menu", "options": "menu"}
    result = aliases.get(key, key)
    require(result in ESSENTIALS[console] | {"quickSave", "quickLoad", "pointerUp", "pointerDown", "pointerLeft", "pointerRight"},
            f"unmapped {console} input: {raw}")
    return result


def hit_frame(item, layout):
    x, y, width, height = rect(item["frame"])
    fallback = layout.get("extendedEdges", {})
    edges = item.get("extendedEdges", {})
    left, top, right, bottom = (float(edges.get(side, fallback.get(side, 0))) for side in ("left", "top", "right", "bottom"))
    require(all(math.isfinite(v) and v >= 0 for v in (left, top, right, bottom)), "bad extended edges")
    return x-left, y-top, width+left+right, height+top+bottom


def fitted(frame, mapping, bounds):
    # DOLSkinAspectFit followed by DOLSkinScaled. Every shipped layout has
    # an explicit game screen, so the portrait controller-pinning branch
    # is not used (DOLSkinOverlay.mm layoutSubviews).
    scale = min(bounds[0]/mapping[0], bounds[1]/mapping[1])
    dx, dy = (bounds[0]-mapping[0]*scale)/2, (bounds[1]-mapping[1]*scale)/2
    return dx+frame[0]*scale, dy+frame[1]*scale, frame[2]*scale, frame[3]*scale


def bitmap(data, name):
    with Image.open(io.BytesIO(data)) as probe:
        require(probe.format == "PNG", f"not PNG: {name}")
        probe.verify()
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        require(min(source.size) > 0, f"empty PNG: {name}")
        result = source.convert("RGBA")
        require(result.getchannel("A").getextrema()[1] > 0, f"invisible PNG: {name}")
        return result


def _grid(rect_, mapping, per_point=2):
    import numpy as np
    g = np.zeros((int(math.ceil(mapping[1]*per_point)), int(math.ceil(mapping[0]*per_point))), bool)
    x0, y0, w, h = rect_
    g[max(0, int(math.floor(y0*per_point))):int(math.ceil((y0+h)*per_point)),
      max(0, int(math.floor(x0*per_point))):int(math.ceil((x0+w)*per_point))] = True
    return g


def drawn_rect(item, resource):
    """The opaque part (alpha >= 50 %) of an item's normal sprite, in mapping points."""
    x, y, w, h = rect(item["frame"])
    alpha = resource(item["asset"]["normal"]).getchannel("A")
    box = alpha.point(lambda v: 255 if v >= 128 else 0).getbbox()
    if box is None:
        return x, y, w, h
    sx, sy = w/alpha.width, h/alpha.height
    return x+box[0]*sx, y+box[1]*sy, (box[2]-box[0])*sx, (box[3]-box[1])*sy


def board_touch_checks(layout, resource, label, inert=frozenset()):
    """Board Originals: what the eye sees, what the finger reaches and what a press
    changes are the control's own drawn shape (the defect seen on device: opaque
    rectangular sprites flashing a box around a pressed control, a stick cap off its
    touch centre)."""
    import numpy as np
    mapping = (float(layout["mappingSize"]["width"]), float(layout["mappingSize"]["height"]))
    background = resource(next(iter(layout["assets"].values()))).convert("RGB")
    scale = background.width / mapping[0]
    shapes, frames, hits = [], [], []
    for index, item in enumerate(layout["items"]):
        frame = rect(item["frame"])
        box = tuple(round(v*scale) for v in (frame[0], frame[1], frame[0]+frame[2], frame[1]+frame[3]))
        under = background.crop(box)
        normal, pressed = resource(item["asset"]["normal"]), resource(item["asset"]["pressed"])
        na, pa = np.asarray(normal.getchannel("A")), np.asarray(pressed.getchannel("A"))
        require(na.min() == 0, f"{label}/{index}: opaque rectangular sprite (no outline alpha)")
        require(np.array_equal(na, pa), f"{label}/{index}: pressed sprite covers more than the control's outline")
        def over(sprite):
            base = under.convert("RGBA")
            base.alpha_composite(sprite.resize(under.size, Image.Resampling.LANCZOS))
            return np.asarray(base.convert("RGB")).astype(np.int16)
        rest = np.abs(over(normal) - np.asarray(under).astype(np.int16)).sum(axis=2)
        if "thumbstick" in item:
            knob = item["thumbstick"]
            composed = under.convert("RGBA")
            composed.alpha_composite(normal.resize(under.size, Image.Resampling.LANCZOS))
            kw, kh = round(knob["width"]*scale), round(knob["height"]*scale)
            composed.alpha_composite(resource(knob["name"]).resize((kw, kh), Image.Resampling.LANCZOS),
                                     ((under.width-kw)//2, (under.height-kh)//2))
            # The cap drawn at the touch centre (DOLSkinOverlay knobFrame at rest) is the board's cap.
            capdiff = np.abs(np.asarray(composed.convert("RGB")).astype(np.int16) - np.asarray(under).astype(np.int16)).sum(axis=2)
            require(capdiff.mean() <= 6.0, f"{label}/{index}: stick cap at rest is off the board's cap ({capdiff.mean():.1f})")
        else:
            require(rest.mean() <= 1.5, f"{label}/{index}: the rest sprite differs from the board ({rest.mean():.2f})")
            inside = np.asarray(normal.resize(under.size).getchannel("A")) >= 250
            lum = lambda im: np.asarray(im.convert("RGB")).astype(np.float32).sum(axis=2)[inside].mean()
            if isinstance(item["inputs"], list) and set(item["inputs"]) <= inert:
                pass  # an inert control never looks pressed (checked in validate_pack)
            else:
                require(lum(Image.fromarray(over(pressed).astype(np.uint8))) < lum(under) * 0.9,
                        f"{label}/{index}: the press is not clearly visible")
        g = np.zeros((int(math.ceil(mapping[1]*2)), int(math.ceil(mapping[0]*2))), bool)
        x0, y0 = int(round(frame[0]*2)), int(round(frame[1]*2))
        w, h = max(1, int(round(frame[2]*2))), max(1, int(round(frame[3]*2)))
        a = np.asarray(normal.getchannel("A").resize((w, h), Image.Resampling.NEAREST)) >= 128
        g[y0:y0+h, x0:x0+w] = a[:g.shape[0]-y0, :g.shape[1]-x0]
        shapes.append(g)
        frames.append(_grid(frame, mapping))
        hits.append(_grid(hit_frame(item, layout), mapping))
    for i in range(len(shapes)):
        for j in range(i):
            require(not (shapes[i] & shapes[j]).any(), f"{label}: drawn shapes {i} and {j} overlap")
        extension = hits[i] & ~frames[i]
        for j in range(len(shapes)):
            if j != i:
                require(not (extension & (hits[j] | frames[j])).any(),
                        f"{label}/{i}: invisible extension reaches control {j}")


def validate_pack(assets, body_sources, row):
    console = row["console"]
    pack_path = assets / manifest_path(row["archiveAsset"], ".manicskin")
    data = pack_path.read_bytes()
    require(len(data) == row["size"], f"{console}: manifest size mismatch")
    require(hashlib.sha256(data).hexdigest() == row["sha256"], f"{console}: manifest SHA-256 mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        require(archive.testzip() is None, f"{console}: ZIP CRC failure")
        names = archive.namelist()
        require(len(names) == len(set(names)), f"{console}: duplicate archive entries")
        for entry in archive.infolist():
            safe_name(entry.filename.rstrip("/"))
            require(not stat.S_ISLNK(entry.external_attr >> 16), "ZIP symlink")
        files = {entry.filename: archive.read(entry.filename) for entry in archive.infolist() if not entry.is_dir()}
    require("info.json" in files, "missing info.json")
    info = json.loads(files["info.json"])
    require(info.get("author") == "RewindBox" and row.get("author") == "RewindBox", "missing RewindBox author")
    require(info["gameTypeIdentifier"].split(".")[-1] in GAME_TYPES[console], "wrong game type")
    images = {name: bitmap(content, name) for name, content in files.items() if name.endswith(".png")}
    require(images, "no raster artwork")
    require(EXPECTED_PACKS.get(row["id"]) == console, f"{row['id']}: unexpected pack or console")
    require(info.get("identifier") == f"org.rewindbox.{row['id']}" or row["id"] in ("wii-pocket", "gamecube-pocket", "ps2-pocket"),
            f"{row['id']}: identifier does not match the catalog id")
    board = info.get("provenance", {}).get("status") == "approved-board"
    require(board == (row["id"] in BOARD_PACKS), f"{row['id']}: approved-board provenance mismatch")
    board_binding = None
    if board:
        board_file = BOARD_DIR/Path(info["provenance"]["board"]).name
        board_binding = hashlib.sha256(board_file.read_bytes()).hexdigest()
        require(board_binding == info["provenance"]["boardSha256"], f"{row['id']}: approved board changed")
    source_bodies = json.loads((body_sources/"provenance.json").read_text())["files"]
    source_bindings = {}
    for name in (("body-portrait.png", "body-landscape.png") if console in RAW_BODY_CONSOLES and not board else ()):
        source = (body_sources/name).read_bytes()
        digest = hashlib.sha256(source).hexdigest()
        require(digest == source_bodies[name]["sha256"], f"{name}: source provenance digest mismatch")
        require(len(source) == source_bodies[name]["bytes"], f"{name}: source provenance size mismatch")
        require(files.get(name) == source, f"{console}: approved source body changed: {name}")
        source_bindings[name] = digest

    def resource(name):
        safe_name(name)
        require(name in images, f"missing PNG resource: {name}")
        return images[name]

    layout_reports = []
    representations = info["representations"]["iphone"]
    # Board Originals are edge-to-edge only (the boards are iPhone 14 Pro-class screens);
    # standard iPhones get them letterboxed through the native fallback, measured below.
    displays = ("edgeToEdge",) if board else ("edgeToEdge", "standard")
    require(set(representations) == set(displays), f"{row['id']}: unexpected iPhone representations")
    for display in displays:
        for orientation in ("portrait", "landscape"):
            label = f"{row['id']}/{display}/{orientation}"
            layout = representations[display][orientation]
            mapping = tuple(float(layout["mappingSize"][key]) for key in ("width", "height"))
            require(all(math.isfinite(v) and v > 0 for v in mapping), f"{label}: mapping size")
            require((mapping[0] < mapping[1]) == (orientation == "portrait"), f"{label}: wrong orientation")
            bounds = (0, 0, *mapping)
            backgrounds = layout["assets"]
            require(backgrounds, f"{label}: no backgrounds")
            for name in backgrounds.values():
                resource(name)
                if console in RAW_BODY_CONSOLES and not board:
                    require(name == f"body-{orientation}.png", f"{label}: changed approved body reference")
            screens = [rect(screen["outputFrame"]) for screen in layout["screens"]]
            require(len(screens) == 1, f"{label}: expected a single game screen")
            for screen in screens:
                require(inside(screen, bounds), f"{label}: screen outside mapping")
            # The game's container is the opening the body draws (screen_opening.py): the
            # approved raw body images stay byte-identical, the pack ships the cutout of
            # its opening and the overlays use it as the body's mask.
            coverage = game_opening(row["id"], layout, files, resource, mapping, label)
            hits, provided, stick_count = [], set(), 0
            for index, item in enumerate(layout["items"]):
                frame = rect(item["frame"])
                hit = hit_frame(item, layout)
                require(inside(hit, bounds), f"{label}/{index}: control outside mapping")
                small = KNOWN_SMALL_TARGETS.get((row["id"], orientation), {})
                first = canonical(console, raw_inputs(item)[0]) if raw_inputs(item) else None
                if first in small:
                    require(min(hit[2:]) >= small[first], f"{label}/{index}: known small target {first} below {small[first]}")
                else:
                    require(min(hit[2:]) >= 44-0.01, f"{label}/{index}: target below 44 mapping points")
                require(not over_opening(hit, coverage, mapping), f"{label}/{index}: target over game screen")
                if not board:
                    require(not any(overlaps(hit, earlier) for earlier in hits), f"{label}/{index}: overlapping control targets")
                hits.append(hit)
                provided.update(canonical(console, name) for name in raw_inputs(item))
                normal, pressed = item["asset"]["normal"], item["asset"]["pressed"]
                a, b = resource(normal), resource(pressed)
                inert = {canonical(console, name) for name in raw_inputs(item)} <= INERT_CONTROLS.get(row["id"], set())
                # An inert control (no Core input) must NOT look pressed; every other one must.
                require(a.size == b.size and (a.tobytes() == b.tobytes()) == inert,
                        f"{label}/{index}: pressed state {'shown on an inert control' if inert else 'not distinct'}")
                if "thumbstick" in item:
                    stick_count += 1
                    knob = item["thumbstick"]
                    resource(knob["name"])
                    require(knob["name"] not in (normal, pressed), f"{label}/{index}: knob baked into base")
                    require(0 < knob["width"] < frame[2] and 0 < knob["height"] < frame[3], f"{label}/{index}: no knob travel")
            if board:
                # Interlocking board shapes may share frame corners; the overlay answers
                # by the drawn shape (DOLSkinHitTest.h), so the shapes and every invisible
                # extension must be disjoint, and a press may change only the shape.
                board_touch_checks(layout, resource, label, INERT_CONTROLS.get(row["id"], frozenset()))
            require(ESSENTIALS[console] <= provided, f"{label}: missing controls {ESSENTIALS[console]-provided}")
            require(stick_count == STICKS[console], f"{label}: wrong movable stick count")
            menus = [item for item in layout["items"] if "menu" in [canonical(console, name) for name in raw_inputs(item)]]
            require(len(menus) == 1, f"{label}: expected exactly one visible Menu control, found {len(menus)}")
            opening = layout["screens"][0]["outputFrame"]
            layout_reports.append({"display": display, "orientation": orientation,
                                   "gameScreen": {"frame": opening, "ratio": round(opening["width"]/opening["height"], 4),
                                                  "cutout": layout["screens"][0].get("screenCutout"),
                                                  "openingPercentOfFrame": round(float((coverage > 0.5).mean()) * 100 * coverage.size / max(1.0, opening["width"]*opening["height"]*coverage.size/(mapping[0]*mapping[1])), 2)},
                                   "mappingSize": mapping, "controls": len(hits),
                                   "minimumMappingTargetPoints": min(min(hit[2:]) for hit in hits)})
    matrix = []
    for portrait in PHONES:
        tall = max(portrait)/min(portrait) > 2
        display, chosen = native_layout(representations, tall)
        for orientation in ("portrait", "landscape"):
            device = portrait if orientation == "portrait" else portrait[::-1]
            layout = chosen[orientation]
            mapping = (layout["mappingSize"]["width"], layout["mappingSize"]["height"])
            hits = [fitted(hit_frame(item, layout), mapping, device) for item in layout["items"]]
            small = KNOWN_SMALL_TARGETS.get((row["id"], orientation), {})
            is_small = [bool(raw_inputs(item)) and canonical(console, raw_inputs(item)[0]) in small for item in layout["items"]]
            minimum = min(min(hit[2:]) for hit, s in zip(hits, is_small) if not s)
            entry = {"devicePoints": device, "display": display, "orientation": orientation,
                     "minimumTargetPoints": round(minimum, 3)}
            if any(is_small):
                entry["knownSmallTargets"] = {canonical(console, raw_inputs(item)[0]): [round(v, 2) for v in hit[2:]]
                                              for item, hit, s in zip(layout["items"], hits, is_small) if s}
            if board and not tall:
                # Documented deviation: a home-button iPhone letterboxes the edge-to-edge
                # board layout. Measured and reported, never presented as meeting 44 pt.
                require(minimum >= 34, f"{row['id']}/{device}: letterboxed target {minimum:.3f}pt")
                entry.update({"letterboxedFallback": True, "meets44pt": minimum >= 44-0.01})
                matrix.append(entry)
                continue
            require(minimum >= 44-0.01, f"{row['id']}/{device}: fitted target {minimum:.3f}pt below 44")
            if board:
                # What is drawn: the opaque part of each sprite (its frame may hold transparent margin).
                frames = [fitted(drawn_rect(item, resource), mapping, device) for item in layout["items"]]
                problems, board_band, covered = housing_conflicts(hits, frames, device, orientation, portrait)
                allowed = KNOWN_HOUSING_DEVIATIONS.get((row["id"], orientation), set())
                key = lambda i: canonical(console, raw_inputs(layout["items"][i])[0])
                problems = [(i, why) for i, why in problems if not (why == "sensor housing" and key(i) in allowed)]
                require(not problems, f"{row['id']}/{device}/{orientation}: targets enter {problems}")
                if covered:
                    entry["knownHousingDeviation"] = [dict(c, control=key(c["item"])) for c in covered]
                depths = KNOWN_BAND_DEPTHS.get((row["id"], orientation), {})
                require(all(b["drawnIntoBandPoints"] <= depths.get(key(b["item"]), 3.0) for b in board_band),
                        f"{row['id']}/{device}/{orientation}: board control deep in home indicator band {board_band}")
                if board_band:
                    entry["boardPlacementIntoHomeIndicatorBand"] = board_band
                entry["physicalModel"] = "sensor housing both landscape sides, display corners, home indicator"
                matrix.append(entry)
                continue
            # Reference iPhone insets; nativeBounds determines display
            # selection, and safeAreaInsets define these physical margins.
            if orientation == "portrait":
                top, right, bottom, left = (59 if portrait[0] >= 390 else 44, 0, 34, 0) if tall else (20, 0, 0, 0)
            else:
                inset = 59 if portrait[0] >= 390 else 44
                top, right, bottom, left = (0, inset, 21, inset) if tall else (0, 0, 0, 0)
            safe = (left, top, device[0]-left-right, device[1]-top-bottom)
            require(all(inside(hit, safe) for hit in hits), f"{console}/{device}: target enters reference unsafe inset")
            entry["referenceInsets"] = [top, right, bottom, left]
            matrix.append(entry)
    require(set(info.get("previewImages", {})) >= {"portrait", "landscape"}, f"{console}: missing complete preview references")
    require(set(row["previewAssets"]) == {"portrait", "landscape"}, f"{console}: manifest preview orientations")
    for orientation in ("portrait", "landscape"):
        name = info["previewImages"][orientation]
        picture = resource(name)
        asset = assets / manifest_path(row["previewAssets"][orientation], ".png")
        require(asset.read_bytes() == files[name], f"{console}: external preview differs from archive preview")
        require((picture.width < picture.height) == (orientation == "portrait"), "wrong preview orientation")
    return {"id": row["id"], "console": console, "archive": pack_path.name, "size": len(data), "sha256": row["sha256"],
            "approvedBodySha256": source_bindings, "approvedBoardSha256": board_binding,
            "gameWindowMode": "native even-odd background mask; raw body preserved" if not board
            else "native even-odd background mask over the board's own navy window",
            "pngs": len(images), "layouts": layout_reports, "nativeFitMatrix": matrix}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, default=Path(__file__).resolve().parents[2]/"assets/skins/pocket")
    parser.add_argument("--body-textures-dir", type=Path, default=Path(__file__).resolve().with_name("body-textures"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        catalog = json.loads((args.assets_dir/"catalog.json").read_text())
        require(catalog.get("schemaVersion") == 1, "unsupported catalog schema")
        rows = catalog["skins"]
        require(len(rows) == len(EXPECTED_PACKS) and {row["id"]: row["console"] for row in rows} == EXPECTED_PACKS,
                "expected exactly the Wii, GameCube, PS2 Pocket packs, the three board Originals and Switch Pocket")
        result = {"status": "passed", "checks": ["manifest digests and sizes", "ZIP CRC and confined resources",
                  "all PNG decodes", "every iPhone layout", "game screen = the opening the body draws: shipped cutout re-measured on the body, outputFrame = its box (PS2 Pocket: its rectangular 4:3 window)", "all essential bindings", "exactly one Menu control in every layout",
                  "approved raw body byte identity and provenance SHA-256 (Pocket packs)",
                  "approved board SHA-256 binding (Originals)",
                  "Originals: sprites transparent outside the outline, press confined to it, rest = board, cap at the touch centre",
                  "Originals: drawn shapes disjoint, invisible extensions reach no other control", "native layout selection per iPhone",
                  "Originals: sensor housing (both landscape sides), corners, home indicator",
                  "Originals: letterboxed home-button iPhone targets measured, not claimed",
                  "PS2 Original landscape: L3/R3/SELECT/START below 44 pt (board-bound), measured, not claimed",
                  "distinct normal/pressed artwork", "separate movable stick caps", "no control overlaps",
                  "no control/game overlap", "44pt fitted targets on reference iPhones", "reference safe insets",
                  "internal/external complete preview references"],
                  "physicalDeviceTested": False, "runtimeGameplayTested": False,
                  "targetMetric": "short side of fitted item hit frame; a D-pad or stick is one directional cluster",
                  "packs": [validate_pack(args.assets_dir, args.body_textures_dir, row) for row in rows]}
        report = json.dumps(result, indent=2)+"\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report)
        print(report, end="")
        return 0
    except (KeyError, ValueError, OSError, zipfile.BadZipFile) as error:
        print(f"Pocket validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
