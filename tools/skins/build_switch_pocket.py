#!/usr/bin/env python3
"""Build "Switch Pocket" (id `switch-pocket`) for the embedded MeloNX from the maintainer's
reference board RewindBox-Switch-Pocket-reference-exacte.png.

The reference (docs/design/pocket/approved-switch.png, 1 939 331 bytes, SHA-256
b89f7cce2180b92ca3ef65adccb862c06c086345af0e7a2469d96809136ae108) draws one iPhone in
portrait and one in landscape. Like the GameCube/Wii/PS2 Originals
(build_pocket_board_originals.py, whose functions this script uses), the pack is the
board's own pixels:

* the background is each phone's SCREEN without the phone frame, titles, captions, the
  drawn Dynamic Island, the home indicator or the "Zone de jeu" text; the game's place
  is the navy window itself (screen_opening.py: its cutout and bounding box), in which
  MeloNX keeps the picture's ratio (16:9 by default, never stretched unless chosen);
* every control is cut from its own place (normal state), the pressed state derived
  inside its own outline; both sticks move their whole dark cap (measured circles,
  measure_stick_caps.py) over a socket refilled from the ring around it;
* commands: L ZL ZR R, minus plus, the RewindBox session Menu (the board's ≡), the D-pad,
  A B X Y, both sticks, L3 R3 (the drawn pills), HOME and Capture. HOME and Capture are
  drawn as on the board but have no input in the embedded Core: they never look pressed
  and the session says so (MeloNXSkinSession), nothing reaches the game.

Necessary adaptations (documented, the drawing itself unchanged):
* the board's portrait phone is shorter than an iPhone (screen 352 x 682 px, ratio 0.516,
  against 393 x 852 pt, 0.461): its plain top band (between the drawn Dynamic Island
  and the shoulder buttons) is made taller so the skin fills the screen edge to edge;
  no control is resized or redrawn, all keep their place relative to the bottom of the
  screen (the board's home indicator falls where the iPhone's is);
* landscape keeps the board's ratio (2.26 against 2.17): letterboxed by about 8 pt above
  and below, as the other Originals;
* touch areas get invisible extended edges up to 46.4 mapping pt where free.

The pack is built from the original PNG only (its size and SHA-256 are checked; the
maintainer sent it in a ZIP on 9 November, after a chat copy had arrived re-encoded as WEBP).

    python3 tools/skins/build_switch_pocket.py
"""
from __future__ import annotations

import argparse, hashlib, io, json, sys
from pathlib import Path

import numpy as np
from PIL import Image

import build_pocket_skins as bp
import build_pocket_board_originals as bo

ROOT = bp.ROOT
BOARDS = ROOT / 'docs/design/pocket'
ORIGINAL = BOARDS / 'approved-switch.png'
ORIGINAL_SHA256 = 'b89f7cce2180b92ca3ef65adccb862c06c086345af0e7a2469d96809136ae108'
ORIGINAL_BYTES = 1939331
ASSETS = ROOT / 'assets/skins/pocket'

PACK_ID = 'switch-pocket'
NAME = 'Switch Pocket'
GAME_TYPE = 'public.aoshuang.game.switch'
LICENSE_LABEL = 'RewindBox approved board; console names and marks belong to their owners'
LICENSE = """Original RewindBox artwork: the maintainer's Switch Pocket reference board, used as
the skin. No third-party skin or game artwork is included. Console names and trademarks
belong to their respective owners. No third-party rights are granted.
Publication licensing is to be set by the project maintainer.
"""

# Portrait: the board's phone is shorter than an iPhone (393 x 852 pt). Its top band is
# plain beige between the drawn Dynamic Island (rows 152-180) and the shoulder buttons
# (row 188): STRETCH rows of it are inserted there (between rows 184 and 185, which are
# flat), so every control keeps its drawing and its place relative to the bottom of the
# screen (the board's home indicator falls where the iPhone's is).
PORTRAIT_SCREEN = (173, 144, 525, 826)          # the board's portrait phone screen
STRETCH = round((PORTRAIT_SCREEN[2] - PORTRAIT_SCREEN[0]) * 852 / 393) - (PORTRAIT_SCREEN[3] - PORTRAIT_SCREEN[1])
INSERT_AT, INSERT_BASE = 185, (183, 187)

# Board geometry in board pixels (1672 x 941 board), measured on it (tools/skins/
# measure_stick_caps.py for the stick caps); portrait_spec() moves the portrait ones
# below INSERT_AT down by STRETCH.
# item: (name, kind, (x, y, w, h)) ; sticks add (hand centre x, y, r) and the measured
# whole cap (centre x, y, radius).
SPEC = {
    'portrait': {
        'crop': PORTRAIT_SCREEN,
        'window': (176, 259, 521, 513), 'window_text': (280, 372, 418, 410), 'aspect': 16 / 9,
        'inert': ('home', 'capture'), 'extend_margin': 1, 'socket_cuts': {'lstick': ('l3',), 'rstick': ('r3',)},
        # A side blocked by a neighbour's frame gives its share to the free side (L3/R3:
        # their stick's square above, free body below), so the touch area can reach 44 pt
        # without moving the drawing or covering another control.
        'spill': True, 'spill_fine': True,
        # L/ZL and ZR/R touch on the board: the seam between them (board x) splits them.
        'cuts': [(224, 186, 224, 233), (471, 185, 471, 232)],
        'items': [
            ('l', 'button', (182, 191, 42, 38)), ('zl', 'button', (225, 191, 46, 38)),
            ('minus', 'button', (282, 196, 32, 28)), ('menu', 'button', (329, 195, 39, 29)),
            ('plus', 'button', (381, 195, 33, 29)),
            ('zr', 'button', (426, 190, 45, 38)), ('r', 'button', (472, 190, 44, 38)),
            ('home', 'button', (292, 235, 47, 32)), ('capture', 'button', (357, 235, 47, 32)),
            ('lstick', 'stick:left', (200, 530, 108, 108), (254, 584.5, 45), (253.39, 583.89, 44.41)),
            ('dpad', 'dpad', (205, 654, 121, 120)),
            ('x', 'button', (412, 530, 46, 47)), ('y', 'button', (372, 570, 46, 44)),
            ('a', 'button', (452, 569, 46, 45)), ('b', 'button', (412, 607, 46, 46)),
            ('rstick', 'stick:right', (381, 663, 109, 110), (435.5, 718, 45), (434.68, 717.09, 44.38)),
            # The L3/R3 pills, drawn after their stick (they sit on its socket ring).
            ('l3', 'button', (294, 615, 36, 25)), ('r3', 'button', (460, 762, 38, 25)),
        ],
    },
    'landscape': {
        'crop': (643, 326, 1526, 716),
        'window': (820, 394, 1327, 691), 'window_text': (1000, 512, 1152, 561), 'aspect': 16 / 9,
        'inert': ('home', 'capture'), 'extend_margin': 1, 'socket_cuts': {'lstick': ('l3',), 'rstick': ('r3',)},
        'spill': True, 'spill_fine': True,
        'cuts': [(770, 333, 770, 379), (1416, 333, 1416, 379)],
        'items': [
            ('l', 'button', (692, 337, 76, 38)), ('zl', 'button', (771, 338, 78, 37)),
            ('minus', 'button', (927, 339, 38, 35)), ('menu', 'button', (1002, 337, 44, 37)),
            ('home', 'button', (1085, 337, 44, 37)), ('capture', 'button', (1151, 337, 44, 37)),
            ('plus', 'button', (1231, 337, 37, 37)),
            ('zr', 'button', (1336, 338, 79, 37)), ('r', 'button', (1417, 338, 76, 37)),
            ('lstick', 'stick:left', (684, 414, 112, 112), (740, 470.5, 48), (739.79, 470.06, 47.55)),
            ('dpad', 'dpad', (681, 563, 120, 119)),
            ('x', 'button', (1398, 411, 51, 50)), ('y', 'button', (1354, 452, 51, 51)),
            ('a', 'button', (1442, 452, 51, 50)), ('b', 'button', (1398, 494, 52, 52)),
            ('rstick', 'stick:right', (1367, 565, 113, 114), (1423.5, 622, 48.5), (1423.17, 621.42, 48.45)),
            ('l3', 'button', (772, 512, 38, 27)), ('r3', 'button', (1342, 657, 39, 27)),
        ],
    },
}
INPUTS = {'a', 'b', 'x', 'y', 'l', 'r', 'zl', 'zr', 'minus', 'plus', 'l3', 'r3', 'menu', 'home', 'capture'}

# The board's own phone furniture, removed before cutting (board px): the drawn Dynamic
# Islands (each column refilled from the body above and below) and the home indicators
# (the body's shading continued over them: the bezel is right below).
ISLANDS = [(296, 149, 402, 184), (645, 477, 679, 576)]
INDICATORS = [(282, 817, 416, 826), (986, 700, 1162, 714)]


def harmonic(a: np.ndarray, box, open_bottom: bool = False) -> None:
    """A smooth fill of `box` from the pixels around it (open_bottom: not from below)."""
    x0, y0, x1, y1 = box
    patch = a[y0 - 1:y1 + 1, x0 - 1:x1 + 1].copy()
    inner = patch[1:-1, 1:-1]
    sides = [patch[0], patch[:, 0], patch[:, -1]] + ([] if open_bottom else [patch[-1]])
    inner[:] = np.concatenate(sides).mean(axis=0)
    for _ in range(3000):
        if open_bottom:
            patch[-1, 1:-1] = patch[-2, 1:-1]
        inner[:] = (patch[:-2, 1:-1] + patch[2:, 1:-1] + patch[1:-1, :-2] + patch[1:-1, 2:]) / 4
    a[y0:y1, x0:x1] = inner


def indicator_fill(a: np.ndarray, box) -> None:
    """Each column of `box` continues the row above it with the vertical shading of the
    body just left and right of it (a wide, short bar right above the bezel)."""
    x0, y0, x1, y1 = box
    sides = np.concatenate([a[y0 - 1:y1, x0 - 3:x0], a[y0 - 1:y1, x1:x1 + 3]], axis=1).mean(axis=1)
    delta = sides[1:] - sides[0]
    a[y0:y1, x0:x1] = a[y0 - 1, x0:x1][None] + delta[:, None]


def cleaned(source: Image.Image) -> np.ndarray:
    a = np.asarray(source.convert('RGB')).astype(np.float32)
    for x0, y0, x1, y1 in ISLANDS:
        # Each column from the body just above the island to the body just below it
        # (the rails' edges are vertical there, so the landscape cyan rail continues).
        top, bottom = a[y0 - 3:y0 - 1].mean(axis=0)[x0:x1], a[y1 + 1:y1 + 3].mean(axis=0)[x0:x1]
        t = ((np.arange(y1 - y0) + 1) / (y1 - y0 + 1))[:, None, None]
        a[y0:y1, x0:x1] = top[None] * (1 - t) + bottom[None] * t
    for box in INDICATORS:
        indicator_fill(a, box)
    return a


def portrait_board(a: np.ndarray) -> Image.Image:
    """STRETCH rows of the plain top band inserted at INSERT_AT: the band's own colour
    (the mean of its flat rows INSERT_BASE) with its fine grain (seeded), so no line or
    streak shows."""
    base = a[INSERT_BASE[0]:INSERT_BASE[1]]
    x0, _, x1, _ = PORTRAIT_SCREEN
    plain = base[:, x0 + 40:x1 - 40]
    grain = float((plain - plain.mean(axis=0, keepdims=True)).std())
    rng = np.random.default_rng(20261109)
    strip = np.repeat(base.mean(axis=0)[None], STRETCH, axis=0)
    strip = strip + rng.normal(0, grain, strip.shape[:2])[..., None]
    out = np.concatenate([a[:INSERT_AT], strip, a[INSERT_AT:]], axis=0)
    return Image.fromarray(np.clip(out, 0, 255).round().astype(np.uint8), 'RGB')


def portrait_spec() -> dict:
    """SPEC['portrait'] in the portrait board's coordinates (rows from INSERT_AT moved down)."""
    down = lambda y: y + STRETCH if y >= INSERT_AT else y
    spec = dict(SPEC['portrait'])
    x0, y0, x1, y1 = spec['crop']
    spec['crop'] = (x0, y0, x1, y1 + STRETCH)
    spec['window'] = tuple(v if i % 2 == 0 else down(v) for i, v in enumerate(spec['window']))
    spec['window_text'] = tuple(v if i % 2 == 0 else down(v) for i, v in enumerate(spec['window_text']))
    spec['cuts'] = [(cx0, down(cy0), cx1, down(cy1)) for cx0, cy0, cx1, cy1 in spec['cuts']]
    items = []
    for entry in spec['items']:
        name, kind, (bx, by, bw, bh) = entry[:3]
        moved = [name, kind, (bx, down(by), bw, bh)]
        for circle in entry[3:]:
            moved.append((circle[0], down(circle[1]), circle[2]))
        items.append(tuple(moved))
    spec['items'] = items
    return spec


PILLS = ('minus', 'menu', 'plus', 'home', 'capture', 'l3', 'r3')


def pill_extent(board: Image.Image, box) -> tuple[int, int, int, int]:
    """A light pill's drawn outline (board px, right/bottom exclusive): the darkest line
    near each edge of its measured box, on the rows/columns through its middle (the
    glyph is in the middle, away from the edges searched)."""
    L = np.asarray(board.convert('L')).astype(np.float64)
    bx, by, bw, bh = box
    cx, cy = bx + bw // 2, by + bh // 2
    row, col = L[cy - 1:cy + 2].mean(axis=0), L[:, cx - 1:cx + 2].mean(axis=1)
    near = lambda prof, at: at - 5 + int(np.argmin(prof[at - 5:at + 6]))
    return near(row, bx), near(col, by), near(row, bx + bw - 1) + 1, near(col, by + bh - 1) + 1


def with_shapes(spec: dict, board: Image.Image) -> dict:
    boxes = {e[0]: e[2] for e in spec['items']}
    return spec | {'shapes': {name: pill_extent(board, boxes[name]) for name in PILLS}}


def source_board() -> tuple[Path, Image.Image, str]:
    if not ORIGINAL.is_file():
        sys.exit(f'{ORIGINAL} is missing: the pack is built from the original PNG only '
                 f'({ORIGINAL_BYTES} bytes, SHA-256 {ORIGINAL_SHA256})')
    data = ORIGINAL.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != ORIGINAL_SHA256 or len(data) != ORIGINAL_BYTES:
        sys.exit(f'{ORIGINAL} is not the maintainer\'s reference ({len(data)} bytes, {digest})')
    return ORIGINAL, Image.open(io.BytesIO(data)), 'approved-board'


def build(out: Path) -> dict:
    path, source, status = source_board()
    if source.size != (1672, 941):
        sys.exit(f'unexpected board size {source.size}')
    clean = cleaned(source)
    boards = {'portrait': portrait_board(clean),
              'landscape': Image.fromarray(np.clip(clean, 0, 255).round().astype(np.uint8), 'RGB')}
    out.mkdir(parents=True, exist_ok=True)
    files = {'LICENSE.txt': LICENSE.encode()}
    specs = {'portrait': with_shapes(portrait_spec(), boards['portrait']),
             'landscape': with_shapes(SPEC['landscape'], boards['landscape'])}
    reps = {'edgeToEdge': {o: bo.representation('switch', o, specs[o], boards[o], files) for o in ('portrait', 'landscape')}}
    for orientation in ('portrait', 'landscape'):
        image = bp.png(bo.compose(reps['edgeToEdge'][orientation], files))
        files[f'previews/{orientation}.png'] = image
        (out / f'{PACK_ID}-{orientation}.png').write_bytes(image)
        (out / f'{PACK_ID}-{orientation}-pressed.png').write_bytes(
            bp.png(bo.compose(reps['edgeToEdge'][orientation], files, pressed=True)))
    used = {i for rep in reps['edgeToEdge'].values() for item in rep['items'] if isinstance(item['inputs'], list)
            for i in item['inputs']}
    if used != INPUTS:
        sys.exit(f'commands {sorted(used)} differ from {sorted(INPUTS)}')
    board_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    info = {'name': NAME, 'identifier': f'org.rewindbox.{PACK_ID}', 'author': 'RewindBox',
            'gameTypeIdentifier': GAME_TYPE, 'version': 3, 'license': LICENSE_LABEL,
            'previewImages': {o: f'previews/{o}.png' for o in ('portrait', 'landscape')},
            'provenance': {'status': status, 'board': f'docs/design/pocket/{path.name}', 'boardSha256': board_sha,
                           'generator': 'tools/skins/build_switch_pocket.py',
                           'note': 'edge-to-edge iPhone layouts; portrait top band lengthened to the iPhone ratio; '
                                   'HOME and Capture drawn, no Core input'},
            'representations': {'iphone': reps}}
    files['info.json'] = (json.dumps(info, indent=2, ensure_ascii=False) + '\n').encode()
    for name, data in files.items():
        if name.endswith('.png'):
            with Image.open(io.BytesIO(data)) as im: im.verify()
    target = out / f'{PACK_ID}.manicskin'
    bp.archive(target, files)
    entry = {'id': PACK_ID, 'name': NAME, 'console': 'switch',
             'archiveAsset': f'assets/skins/pocket/{PACK_ID}.manicskin',
             'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'size': target.stat().st_size,
             'previewAssets': {o: f'assets/skins/pocket/{PACK_ID}-{o}.png' for o in ('portrait', 'landscape')},
             'author': 'RewindBox', 'license': LICENSE_LABEL}
    receipt = {'archiveSha256': entry['sha256'], 'archiveBytes': entry['size'], 'board': path.name,
               'boardSha256': board_sha, 'status': status, 'portraitTopBandRowsAdded': STRETCH,
               'pillOutlines': {o: specs[o]['shapes'] for o in specs}}
    catalog_path = out / 'catalog.json'
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {'schemaVersion': 1, 'skins': []}
    catalog['skins'] = [s for s in catalog['skins'] if s['id'] != PACK_ID] + [entry]
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    (out / f'validation-{PACK_ID}.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(entry, ensure_ascii=False))
    return entry


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ASSETS)
    build(parser.parse_args().output)
