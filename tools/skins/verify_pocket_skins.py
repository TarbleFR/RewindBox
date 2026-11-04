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
}
STICKS = {"gc": 2, "wii": 1, "ps2": 2}
GAME_TYPES = {"gc": {"ngc", "gc", "gamecube"}, "wii": {"wii"}, "ps2": {"ps2"}}
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
KNOWN_HOUSING_DEVIATIONS = {("gamecube-pocket-original", "landscape"): {"x", "cUp", "menu"}}
EXPECTED_PACKS = {"wii-pocket": "wii", "gamecube-pocket": "gc", "ps2-pocket": "ps2",
                  "gamecube-pocket-original": "gc", "wii-pocket-original": "wii"}


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
                return {"gc": "c", "wii": "pointer", "ps2": "rstick"}[console]+direction
    for direction in ("up", "down", "left", "right"):
        if key in (direction, "dpad"+direction):
            return direction
    aliases = {"pause": "menu", "options": "menu", "quicksave": "quickSave", "quickload": "quickLoad"}
    if console == "gc":
        aliases.update({"r1": "z", "l2": "l", "r2": "r", "lefttrigger": "l", "righttrigger": "r"})
    elif console == "wii":
        aliases.update({"1": "one", "2": "two", "nunchukc": "c", "nunchukz": "z"})
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
    require(board == row["id"].endswith("-original"), f"{row['id']}: approved-board provenance mismatch")
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
                require(abs(screen[2]/screen[3]-4/3) < 0.001, f"{label}: screen is not 4:3")
                # Approved raw body images stay byte-identical. Their game
                # windows are cut out by DOLSkinOverlay's even-odd layer mask
                # at runtime, rather than by altering the bitmap alpha.
            hits, provided, stick_count = [], set(), 0
            for index, item in enumerate(layout["items"]):
                frame = rect(item["frame"])
                hit = hit_frame(item, layout)
                require(inside(hit, bounds), f"{label}/{index}: control outside mapping")
                require(min(hit[2:]) >= 44-0.01, f"{label}/{index}: target below 44 mapping points")
                require(not any(overlaps(hit, screen) for screen in screens), f"{label}/{index}: target over game screen")
                require(not any(overlaps(hit, earlier) for earlier in hits), f"{label}/{index}: overlapping control targets")
                hits.append(hit)
                provided.update(canonical(console, name) for name in raw_inputs(item))
                normal, pressed = item["asset"]["normal"], item["asset"]["pressed"]
                a, b = resource(normal), resource(pressed)
                require(a.size == b.size and a.tobytes() != b.tobytes(), f"{label}/{index}: pressed state not distinct")
                if "thumbstick" in item:
                    stick_count += 1
                    knob = item["thumbstick"]
                    resource(knob["name"])
                    require(knob["name"] not in (normal, pressed), f"{label}/{index}: knob baked into base")
                    require(0 < knob["width"] < frame[2] and 0 < knob["height"] < frame[3], f"{label}/{index}: no knob travel")
            require(ESSENTIALS[console] <= provided, f"{label}: missing controls {ESSENTIALS[console]-provided}")
            require(stick_count == STICKS[console], f"{label}: wrong movable stick count")
            menus = [item for item in layout["items"] if "menu" in [canonical(console, name) for name in raw_inputs(item)]]
            require(len(menus) == 1, f"{label}: expected exactly one visible Menu control, found {len(menus)}")
            layout_reports.append({"display": display, "orientation": orientation,
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
            minimum = min(min(hit[2:]) for hit in hits)
            entry = {"devicePoints": device, "display": display, "orientation": orientation,
                     "minimumTargetPoints": round(minimum, 3)}
            if board and not tall:
                # Documented deviation: a home-button iPhone letterboxes the edge-to-edge
                # board layout. Measured and reported, never presented as meeting 44 pt.
                require(minimum >= 34, f"{row['id']}/{device}: letterboxed target {minimum:.3f}pt")
                entry.update({"letterboxedFallback": True, "meets44pt": minimum >= 44-0.01})
                matrix.append(entry)
                continue
            require(minimum >= 44-0.01, f"{row['id']}/{device}: fitted target {minimum:.3f}pt below 44")
            if board:
                frames = [fitted(rect(item["frame"]), mapping, device) for item in layout["items"]]
                problems, board_band, covered = housing_conflicts(hits, frames, device, orientation, portrait)
                allowed = KNOWN_HOUSING_DEVIATIONS.get((row["id"], orientation), set())
                key = lambda i: canonical(console, raw_inputs(layout["items"][i])[0])
                problems = [(i, why) for i, why in problems if not (why == "sensor housing" and key(i) in allowed)]
                require(not problems, f"{row['id']}/{device}/{orientation}: targets enter {problems}")
                if covered:
                    entry["knownHousingDeviation"] = [dict(c, control=key(c["item"])) for c in covered]
                require(all(b["drawnIntoBandPoints"] <= 1.0 for b in board_band),
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
                "expected exactly the Wii, GameCube, PS2 Pocket packs and the two board Originals")
        result = {"status": "passed", "checks": ["manifest digests and sizes", "ZIP CRC and confined resources",
                  "all PNG decodes", "every iPhone layout", "4:3 game windows for native background masking", "all essential bindings", "exactly one Menu control in every layout",
                  "approved raw body byte identity and provenance SHA-256 (Pocket packs)",
                  "approved board SHA-256 binding (Originals)", "native layout selection per iPhone",
                  "Originals: sensor housing (both landscape sides), corners, home indicator",
                  "Originals: letterboxed home-button iPhone targets measured, not claimed",
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
