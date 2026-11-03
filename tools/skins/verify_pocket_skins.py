#!/usr/bin/env python3
"""Verify the two shipped Pocket archives and their iPhone geometry offline.

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
}


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
                return ("c" if console == "gc" else "pointer")+direction
    for direction in ("up", "down", "left", "right"):
        if key in (direction, "dpad"+direction):
            return direction
    aliases = {"pause": "menu", "options": "menu", "quicksave": "quickSave", "quickload": "quickLoad"}
    aliases.update({"r1": "z", "l2": "l", "r2": "r", "lefttrigger": "l", "righttrigger": "r"}
                   if console == "gc" else {"1": "one", "2": "two", "nunchukc": "c", "nunchukz": "z"})
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
    require(info["gameTypeIdentifier"].split(".")[-1] in ({"ngc", "gc", "gamecube"} if console == "gc" else {"wii"}), "wrong game type")
    images = {name: bitmap(content, name) for name, content in files.items() if name.endswith(".png")}
    require(images, "no raster artwork")
    source_bodies = json.loads((body_sources/"provenance.json").read_text())["files"]
    source_bindings = {}
    for name in ("body-portrait.png", "body-landscape.png"):
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
    for display in ("edgeToEdge", "standard"):
        for orientation in ("portrait", "landscape"):
            label = f"{console}/{display}/{orientation}"
            layout = representations[display][orientation]
            mapping = tuple(float(layout["mappingSize"][key]) for key in ("width", "height"))
            require(all(math.isfinite(v) and v > 0 for v in mapping), f"{label}: mapping size")
            require((mapping[0] < mapping[1]) == (orientation == "portrait"), f"{label}: wrong orientation")
            bounds = (0, 0, *mapping)
            backgrounds = layout["assets"]
            require(backgrounds, f"{label}: no backgrounds")
            for name in backgrounds.values():
                resource(name)
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
            require(stick_count == (2 if console == "gc" else 1), f"{label}: wrong movable stick count")
            layout_reports.append({"display": display, "orientation": orientation,
                                   "mappingSize": mapping, "controls": len(hits),
                                   "minimumMappingTargetPoints": min(min(hit[2:]) for hit in hits)})
    matrix = []
    for portrait in PHONES:
        display = "edgeToEdge" if max(portrait)/min(portrait) > 2 else "standard"
        for orientation in ("portrait", "landscape"):
            device = portrait if orientation == "portrait" else portrait[::-1]
            layout = representations[display][orientation]
            mapping = (layout["mappingSize"]["width"], layout["mappingSize"]["height"])
            hits = [fitted(hit_frame(item, layout), mapping, device) for item in layout["items"]]
            minimum = min(min(hit[2:]) for hit in hits)
            require(minimum >= 44-0.01, f"{console}/{device}: fitted target {minimum:.3f}pt below 44")
            tall = display == "edgeToEdge"
            # Reference iPhone insets; nativeBounds determines display
            # selection, and safeAreaInsets define these physical margins.
            if orientation == "portrait":
                top, right, bottom, left = (59 if portrait[0] >= 390 else 44, 0, 34, 0) if tall else (20, 0, 0, 0)
            else:
                inset = 59 if portrait[0] >= 390 else 44
                top, right, bottom, left = (0, inset, 21, inset) if tall else (0, 0, 0, 0)
            safe = (left, top, device[0]-left-right, device[1]-top-bottom)
            require(all(inside(hit, safe) for hit in hits), f"{console}/{device}: target enters reference unsafe inset")
            matrix.append({"devicePoints": device, "display": display, "orientation": orientation,
                           "minimumTargetPoints": round(minimum, 3), "referenceInsets": [top, right, bottom, left]})
    require(set(info.get("previewImages", {})) >= {"portrait", "landscape"}, f"{console}: missing complete preview references")
    require(set(row["previewAssets"]) == {"portrait", "landscape"}, f"{console}: manifest preview orientations")
    for orientation in ("portrait", "landscape"):
        name = info["previewImages"][orientation]
        picture = resource(name)
        asset = assets / manifest_path(row["previewAssets"][orientation], ".png")
        require(asset.read_bytes() == files[name], f"{console}: external preview differs from archive preview")
        require((picture.width < picture.height) == (orientation == "portrait"), "wrong preview orientation")
    return {"console": console, "archive": pack_path.name, "size": len(data), "sha256": row["sha256"],
            "approvedBodySha256": source_bindings, "gameWindowMode": "native even-odd background mask; raw body preserved",
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
        require(len(rows) == 2 and {row["console"] for row in rows} == {"gc", "wii"}, "expected exactly Wii and GameCube")
        require(len({row["id"] for row in rows}) == 2, "duplicate catalog id")
        result = {"status": "passed", "checks": ["manifest digests and sizes", "ZIP CRC and confined resources",
                  "all PNG decodes", "8 iPhone layouts", "4:3 game windows for native background masking", "all essential bindings",
                  "approved raw body byte identity and provenance SHA-256",
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
