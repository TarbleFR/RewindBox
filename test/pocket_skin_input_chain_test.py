#!/usr/bin/env python3
"""Every visible control of the shipped Pocket skins (Wii, GameCube, PS2 and the three
approved-board Originals) reaches its engine.

Runs on the REAL archives (assets/skins/pocket/*.manicskin, bound by the catalog
SHA-256) and traces, for every layout (each iPhone representation the archive ships,
portrait and landscape) and every item: sprite -> touch target -> canonical command ->
engine command. The canonical table and the engine tables are read from the
native sources themselves (DOLSkinOverlay.mm for Dolphin, ARMSX2SkinOverlay.mm
for ARMSX2), so a drift between a skin, its table and its sender fails here.
It also exercises the touch model on the shipped geometry (press, drag between
controls, release; two fingers; a stick finger never presses L3/R3). The hit test is
the overlays' own C header, compiled: DOLSkinHitTest.h for Dolphin packs and its ARMSX2
pod copy ARMSX2SkinHitTest.h for PS2 packs (both proven equal to one mirror).

This is a host test of files and tables. It is not an UIKit run and not a game
run: physical iPhone play stays a separate, unobserved step.
"""
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets/skins/pocket'
DOL = (ROOT / 'packages/dolphin_internal_bridge/ios/Classes/DOLSkinOverlay.mm').read_text(encoding='utf-8')
A2 = (ROOT / 'packages/armsx2_internal_bridge/ios/Classes/ARMSX2SkinOverlay.mm').read_text(encoding='utf-8')
DIRECTIONS = ('Up', 'Down', 'Left', 'Right')
_spec = importlib.util.spec_from_file_location('verify_pocket_skins', ROOT / 'tools/skins/verify_pocket_skins.py')
VERIFY = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(VERIFY)
# Board-bound targets below 44 pt: the verifier's closed list (with its floors).
KNOWN_SMALL_TARGETS = VERIFY.KNOWN_SMALL_TARGETS


def fail(message):
    raise SystemExit('pocket skin input chain: ' + message)


def require(condition, message):
    if not condition:
        fail(message)


def key(raw):
    return re.sub(r'[^a-z0-9]', '', raw.lower())


def table(source, marker):
    """The `@"raw" : @"canonical"` rows between the dolphin-skins-table markers."""
    block = re.search(r'// dolphin-skins-table: %s\n(.*?)// dolphin-skins-table: end' % marker, source, re.S)
    require(block, 'table %s not found' % marker)
    return dict(re.findall(r'@"([^"]+)"\s*:\s*@"([^"]+)"', block.group(1)))


def common_canonical(raw, family_c):
    k = key(raw)
    for prefix in ('leftthumbstick', 'analogstick', 'leftstick', 'leftanalog', 'analog', 'thumbstick'):
        for d in DIRECTIONS:
            if k == prefix + d.lower():
                return 'stick' + d
    for prefix in ('rightthumbstick', 'rightstick', 'rightanalog', 'cstick', 'c'):
        for d in DIRECTIONS:
            if k == prefix + d.lower():
                return family_c + d
    for d in DIRECTIONS:
        if k in (d.lower(), 'dpad' + d.lower()):
            return d.lower()
    if k in ('menu', 'pause', 'options'):
        return 'menu'
    return None


GC_NAMES, WII_NAMES = table(DOL, 'gc'), table(DOL, 'wii')


def canonical(console, raw):
    if console == 'ps2':
        found = common_canonical(raw, 'rstick')
        if found:
            return found
        k = key(raw)
        return k if k in ENGINE_PS2 else None
    found = common_canonical(raw, 'c' if console == 'gc' else 'pointer')
    if found:
        return found
    if key(raw) == 'quicksave':
        return 'quickSave'
    if key(raw) == 'quickload':
        return 'quickLoad'
    return (GC_NAMES if console == 'gc' else WII_NAMES).get(key(raw))


# --- engine commands, read from the native senders --------------------------------------
def dict_block(source, name):
    m = re.search(r'%s\(BOOL wii\)\s*\{(.*?)\n\}' % name, source, re.S)
    require(m, name)
    return m.group(1)


def engine_dolphin(console):
    wii = console == 'wii'
    ids = dict_block(DOL, 'DOLSkinButtonIds')
    branch = re.search(r'if \(wii\) \{\s*return @\{(.*?)\};\s*\}\s*return @\{(.*?)\};', ids, re.S)
    require(branch, 'DOLSkinButtonIds shape')
    buttons = dict(re.findall(r'@"(\w+)"\s*:\s*@(\d+)', branch.group(1 if wii else 2)))
    triggers = {} if wii else dict(re.findall(r'@"(\w+)"\s*:\s*@(\d+)', re.search(r'return wii \? @\{\} : @\{(.*?)\};', DOL, re.S).group(1)))
    families = {'stick': True, 'pointer': wii, 'c': not wii}
    return buttons, triggers, families


ENGINE_PS2 = set(re.findall(r'@"(\w+)"\s*:\s*@\d+', re.search(r'A2SkinButtonIds\(void\) \{(.*?)\n\}', A2, re.S).group(1)))
PS2_IDS = {name: int(number) for name, number in re.findall(
    r'@"(\w+)"\s*:\s*@(\d+)', re.search(r'A2SkinButtonIds\(void\) \{(.*?)\n\}', A2, re.S).group(1))}
# ARMSX2Bridge.h (upstream 9d989ca9, platforms/ios/app/src/main/cpp/ARMSX2Bridge.h) order of ARMSX2PadButton.
EXPECTED = {'wii-pocket': 'wii', 'gamecube-pocket': 'gc', 'ps2-pocket': 'ps2',
            'gamecube-pocket-original': 'gc', 'wii-pocket-original': 'wii', 'ps2-pocket-original': 'ps2'}
UPSTREAM_PS2 = ['up', 'down', 'left', 'right', 'cross', 'circle', 'square', 'triangle', 'l1', 'r1', 'l2', 'r2', 'start',
                'select', 'l3', 'r3']


def engine_command(console, name):
    """('button'|'trigger'|'stick'|'action', detail) or None."""
    if name == 'menu':
        require('menuHandler' in (DOL if console != 'ps2' else A2), 'menu handler')
        return ('action', 'menu')
    if console == 'ps2':
        if name in PS2_IDS:
            return ('button', PS2_IDS[name])
        m = re.fullmatch(r'(stick|rstick)(Up|Down|Left|Right)', name)
        return ('stick', m.group(1)) if m else None
    buttons, triggers, families = engine_dolphin(console)
    if name in buttons:
        return ('button', int(buttons[name]))
    if name in triggers:
        return ('trigger', int(triggers[name]))
    m = re.fullmatch(r'(stick|pointer|c)(Up|Down|Left|Right)', name)
    if m and families[m.group(1)]:
        return ('stick', m.group(1))
    if name in ('quickSave', 'quickLoad'):
        return ('action', name)
    return None


# --- the shipped archives ------------------------------------------------------------------
def load_pack(row):
    data = (ROOT / row['archiveAsset']).read_bytes()
    require(len(data) == row['size'] and hashlib.sha256(data).hexdigest() == row['sha256'],
            row['id'] + ': archive differs from the catalog')
    z = zipfile.ZipFile(io.BytesIO(data))
    sprites = {n: z.read(n) for n in z.namelist() if n.endswith('.png')}
    CURRENT['all_sprites'] = sprites
    return json.loads(z.read('info.json')), set(z.namelist())


def rect(f):
    return (f['x'], f['y'], f['x'] + f['width'], f['y'] + f['height'])


def inputs_of(item):
    value = item['inputs']
    return list(value.values()) if isinstance(value, dict) else list(value)


def hit_rect(item, layout=None):
    """frame grown by extendedEdges (DOLSkinOverlay hitFrame; a missing side comes
    from the layout's extendedEdges)."""
    fallback = (layout or {}).get('extendedEdges', {})
    edges = item.get('extendedEdges', {})
    left, top, right, bottom = (float(edges.get(side, fallback.get(side, 0))) for side in ('left', 'top', 'right', 'bottom'))
    x0, y0, x1, y1 = rect(item['frame'])
    return (x0 - left, y0 - top, x1 + right, y1 + bottom)


# DOLSkinOverlay itemAtPoint is DOLSkinHitTest.h: compiled once and run on the real
# frames, touch areas and sprite alpha maps (read the way DOLSkinAlphaMap reads them).
_PROBE = {}
_ALPHA = {}


def _probe(engine=None):
    """The compiled hit test of the overlay that draws the layout being checked."""
    engine = engine or CURRENT.get('engine', 'dolphin')
    if engine not in _PROBE:
        out = Path(tempfile.mkdtemp()) / f'skin_hit_probe_{engine}'
        flags = ['-DARMSX2_HIT'] if engine == 'armsx2' else []
        subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', *flags, '-o', str(out),
                        str(ROOT / 'test/orientation_policy/skin_hit_probe.c')], check=True)
        _PROBE[engine] = out
    return _PROBE[engine]


def check_hit_headers():
    """ARMSX2SkinHitTest.h is DOLSkinHitTest.h with the pod's own prefix: same code."""
    def code(path, prefix):
        text = (ROOT / path).read_text(encoding='utf-8').replace(prefix, 'SkinHit')
        text = re.sub(r'//[^\n]*', '', text)
        return [line.strip() for line in text.splitlines() if line.strip()]
    dol = code('packages/dolphin_internal_bridge/ios/Classes/DOLSkinHitTest.h', 'DOLSkinHit')
    a2 = code('packages/armsx2_internal_bridge/ios/Classes/ARMSX2SkinHitTest.h', 'A2SkinHit')
    require(dol == a2, 'ARMSX2SkinHitTest.h differs from DOLSkinHitTest.h beyond its prefix and comments')
    require('#import "ARMSX2SkinHitTest.h"' in A2 and 'A2SkinHitIndex(hits.data()' in A2 and 'A2SkinAlphaMap(item.assetPath' in A2,
            'ARMSX2SkinOverlay itemAtPoint does not run ARMSX2SkinHitTest.h on the sprite alpha')


def alpha_map(png):
    """DOLSkinAlphaMap: alpha at most 192 px on the long side, None if fully opaque."""
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert('RGBA')
        s = min(1.0, 192.0 / max(im.size))
        w, h = max(1, round(im.width * s)), max(1, round(im.height * s))
        a = im.getchannel('A').resize((w, h), Image.Resampling.NEAREST)
        data = bytes(a.tobytes())
    return None if min(data) >= 128 else (w, h, data)


def items_at(items, points, layout=None, sprites=None):
    """itemAtPoint for many points at once."""
    lines = [str(len(items))]
    for item in items:
        x0, y0, x1, y1 = rect(item['frame'])
        h = hit_rect(item, layout)
        active = 1 if inputs_of(item) else 0
        amap = None
        if sprites is not None and isinstance(item.get('asset'), dict) and item['asset'].get('normal') in sprites:
            name = item['asset']['normal']
            if name not in _ALPHA:
                _ALPHA[name] = alpha_map(sprites[name])
            amap = _ALPHA[name]
        if amap is None:
            lines.append(f'{x0} {y0} {x1 - x0} {y1 - y0} {h[0]} {h[1]} {h[2] - h[0]} {h[3] - h[1]} {active} 0 0')
        else:
            w, hh, data = amap
            lines.append(f'{x0} {y0} {x1 - x0} {y1 - y0} {h[0]} {h[1]} {h[2] - h[0]} {h[3] - h[1]} {active} {w} {hh}')
            lines.append(' '.join(str(b) for b in data))
    lines.append(str(len(points)))
    lines.extend(f'{x} {y}' for x, y in points)
    out = subprocess.run([str(_probe())], input='\n'.join(lines) + '\n', capture_output=True, text=True, check=True)
    return [int(v) for v in out.stdout.split()]


CURRENT = {}  # the layout and sprites item_at answers for


def _mirror(items, x, y, layout, sprites):
    """DOLSkinHitIndex in Python, proven equal to the compiled header on a full grid
    of every layout (check_mirror)."""
    def amap(item):
        name = item.get('asset', {}).get('normal') if isinstance(item.get('asset'), dict) else None
        if sprites is None or name not in sprites: return None
        if name not in _ALPHA: _ALPHA[name] = alpha_map(sprites[name])
        return _ALPHA[name]

    def inside(r):
        return r[0] <= x < r[2] and r[1] <= y < r[3]
    for i in range(len(items) - 1, -1, -1):
        item = items[i]
        if not inputs_of(item): continue
        f = rect(item['frame'])
        if not inside(f): continue
        m = amap(item)
        if m is None: return i
        w, h, data = m
        u = min(max(int((x - f[0]) / (f[2] - f[0]) * w), 0), w - 1)
        v = min(max(int((y - f[1]) / (f[3] - f[1]) * h), 0), h - 1)
        if data[v * w + u] >= 128: return i
    for use_hit in (False, True):
        best, distance = -1, None
        for i in range(len(items) - 1, -1, -1):
            item = items[i]
            if not inputs_of(item): continue
            r = hit_rect(item, layout) if use_hit else rect(item['frame'])
            if not inside(r): continue
            f = rect(item['frame'])
            d = (x - (f[0] + f[2]) / 2) ** 2 + (y - (f[1] + f[3]) / 2) ** 2
            if best < 0 or d < distance: best, distance = i, d
        if best >= 0: return best
    return -1


def check_mirror(items, layout, sprites, tag, step=1.0):
    """The compiled DOLSkinHitTest.h and the mirror agree on a `step`-point grid."""
    W, H = layout['mappingSize']['width'], layout['mappingSize']['height']
    points = [(x * step + step / 4, y * step + step / 4) for y in range(int(H / step)) for x in range(int(W / step))]
    native = items_at(items, points, layout, sprites)
    for (x, y), n in zip(points, native):
        m = _mirror(items, x, y, layout, sprites)
        require(m == n, '%s: mirror %d != %s %d at (%.2f, %.2f)' % (
            tag, m, 'ARMSX2SkinHitTest.h' if CURRENT.get('engine') == 'armsx2' else 'DOLSkinHitTest.h', n, x, y))
    return len(points)


def check_rectangle_equivalence(items, layout, tag, step=2.0):
    """Layouts without overlapping frames (every pack but the Originals): the drawn-shape
    hit test answers exactly like the previous rectangle-only one (frame, then extended
    edges, last drawn wins), so their touch behaviour did not change."""
    W, H = layout['mappingSize']['width'], layout['mappingSize']['height']
    points = [(x * step + step / 4, y * step + step / 4) for y in range(int(H / step)) for x in range(int(W / step))]

    def previous(x, y):
        for use_hit in (False, True):
            for i in range(len(items) - 1, -1, -1):
                if not inputs_of(items[i]): continue
                r = hit_rect(items[i], layout) if use_hit else rect(items[i]['frame'])
                if r[0] <= x < r[2] and r[1] <= y < r[3]: return i
        return -1
    for (x, y), n in zip(points, items_at(items, points, layout, CURRENT['all_sprites'])):
        require(previous(x, y) == n, '%s: the hit test changed at (%.2f, %.2f): %d, previously %d' % (tag, x, y, n, previous(x, y)))
    return len(points)


def item_at(items, x, y):
    """DOLSkinOverlay itemAtPoint (DOLSkinHitTest.h) on the layout being checked."""
    return _mirror(items, x, y, CURRENT.get('layout'), CURRENT.get('sprites'))


def press(items, console, x, y):
    """Commands pressed by one finger at (x, y) on the item under it."""
    index = item_at(items, x, y)
    if index < 0:
        return set(), None
    item = items[index]
    if isinstance(item['inputs'], dict):
        if 'thumbstick' in item:
            return {('stick', canonical(console, next(iter(item['inputs'].values()))))}, index
        return {('dpad', index)}, index
    return {canonical(console, name) for name in item['inputs']}, index


def main():
    catalog = json.loads((ASSETS / 'catalog.json').read_text())
    rows = {row['id']: row for row in catalog['skins']}
    require({i: r['console'] for i, r in rows.items()} == EXPECTED, 'the catalog must carry exactly %s' % EXPECTED)
    require(UPSTREAM_PS2 == [n for n, _ in sorted(PS2_IDS.items(), key=lambda kv: kv[1])],
            'ARMSX2 pad indices differ from ARMSX2Bridge.h: %s' % PS2_IDS)
    check_hit_headers()
    report = []
    for pack_id, row in sorted(rows.items()):
        console = row['console']
        CURRENT['engine'] = 'armsx2' if console == 'ps2' else 'dolphin'
        info, names = load_pack(row)
        require(info['gameTypeIdentifier'].split('.')[-1] in {'gc': {'ngc'}, 'wii': {'wii'}, 'ps2': {'ps2'}}[console],
                console + ': game type')
        reps = info['representations']['iphone']
        # Board Originals ship edge-to-edge only (the native layout lookup falls back to it).
        displays = ('edgeToEdge',) if pack_id.endswith('-original') else ('edgeToEdge', 'standard')
        require(set(reps) == set(displays), pack_id + ': iPhone representations')
        for display in displays:
            for orientation in ('portrait', 'landscape'):
                layout = reps[display][orientation]
                tag = '%s/%s/%s' % (pack_id, display, orientation)
                items = layout['items']
                CURRENT.update(layout=layout, sprites=CURRENT['all_sprites'])
                CURRENT['grid'] = CURRENT.get('grid', 0) + check_mirror(items, layout, CURRENT['all_sprites'], tag,
                                                                  1.0 if pack_id.endswith('-original') else 2.0)
                if not pack_id.endswith('-original'):
                    CURRENT['unchanged'] = CURRENT.get('unchanged', 0) + check_rectangle_equivalence(items, layout, tag)
                menu_items = []
                seen = set()
                for index, item in enumerate(items):
                    # sprite
                    for state in ('normal', 'pressed'):
                        require(item['asset'][state] in names, tag + ': missing sprite ' + item['asset'][state])
                    require(item['asset']['normal'] != item['asset']['pressed'], tag + ': same sprite for both states')
                    # touch target: what itemAtPoint accepts, the drawn frame grown by extendedEdges
                    f = item['frame']
                    h = hit_rect(item, layout)
                    small = KNOWN_SMALL_TARGETS.get((pack_id, orientation), {})
                    first = canonical(console, inputs_of(item)[0]) if isinstance(item['inputs'], list) else None
                    require(min(h[2] - h[0], h[3] - h[1]) >= small.get(first, 44), tag + ': target under 44 points')
                    # every point of its touch area outside the other controls' frames reaches
                    # this control and no other (inside another frame, the drawn shape decides:
                    # checked below on every opaque point of every sprite)
                    for px in (h[0] + 0.01, (h[0] + h[2]) / 2, h[2] - 0.01):
                        for py in (h[1] + 0.01, (h[1] + h[3]) / 2, h[3] - 0.01):
                            others = [o for j, o in enumerate(items) if j != index and
                                      rect(o['frame'])[0] <= px < rect(o['frame'])[2] and rect(o['frame'])[1] <= py < rect(o['frame'])[3]]
                            if others: continue
                            require(item_at(items, px, py) == index,
                                    '%s: point (%.1f, %.1f) of item %d reaches item %d' % (tag, px, py, index, item_at(items, px, py)))
                    # every opaque point of the drawn control reaches it (centre and contour)
                    amap = alpha_map(CURRENT['sprites'][item['asset']['normal']])
                    if amap is not None:
                        aw, ah, adata = amap
                        fx0, fy0, fx1, fy1 = rect(f)
                        for v in range(ah):
                            for u in range(aw):
                                if adata[v * aw + u] < 128: continue
                                px = fx0 + (u + 0.5) / aw * (fx1 - fx0)
                                py = fy0 + (v + 0.5) / ah * (fy1 - fy0)
                                got = item_at(items, px, py)
                                require(got == index, '%s: drawn point (%.1f, %.1f) of item %d reaches item %d'
                                        % (tag, px, py, index, got))
                                CURRENT['shape_points'] = CURRENT.get('shape_points', 0) + 1
                    # canonical + engine
                    for raw in inputs_of(item):
                        name = canonical(console, raw)
                        require(name is not None, '%s: %r has no canonical command' % (tag, raw))
                        command = engine_command(console, name)
                        require(command is not None, '%s: %s has no engine command' % (tag, name))
                        seen.add(name)
                        if name == 'menu':
                            menu_items.append(index)
                    # centre of every visible control presses exactly that control
                    cx, cy = f['x'] + f['width'] / 2, f['y'] + f['height'] / 2
                    pressed, hit = press(items, console, cx, cy)
                    require(hit == index and pressed, '%s: centre of item %d presses item %s' % (tag, index, hit))
                    if isinstance(item['inputs'], list):
                        require(pressed == {canonical(console, n) for n in item['inputs']}, tag + ': centre press set')
                        # press -> release: nothing remains under a point outside every control
                        require(press(items, console, -5, -5)[0] == set(), tag + ': stray press')
                require(len(menu_items) == 1, '%s: exactly one Menu control expected, found %d' % (tag, len(menu_items)))
                menu = items[menu_items[0]]['frame']
                screen = layout['screens'][0]['outputFrame']
                require(not (rect(menu)[0] < rect(screen)[2] and rect(menu)[2] > rect(screen)[0]
                             and rect(menu)[1] < rect(screen)[3] and rect(menu)[3] > rect(screen)[1]),
                        tag + ': Menu overlaps the game screen')
                # nothing visible is decoration: every item has at least one command
                if console == 'ps2':
                    for needed in ('cross', 'circle', 'square', 'triangle', 'l1', 'l2', 'r1', 'r2', 'select', 'start',
                                   'l3', 'r3', 'menu', 'up', 'down', 'left', 'right', 'stickUp', 'rstickUp'):
                        require(needed in seen, '%s: %s missing' % (tag, needed))
                    # L3 / R3 are targets of their own: a finger on a stick never presses them
                    # (inside another control's frame, e.g. the Original's L3 label under the
                    # cap, the drawn shape decides: checked above on every drawn point).
                    for item in items:
                        if 'thumbstick' in item:
                            f = item['frame']
                            for dx in (0.1, 0.5, 0.9):
                                for dy in (0.1, 0.5, 0.9):
                                    px, py = f['x'] + dx * f['width'], f['y'] + dy * f['height']
                                    if any(o is not item and rect(o['frame'])[0] <= px < rect(o['frame'])[2]
                                           and rect(o['frame'])[1] <= py < rect(o['frame'])[3] for o in items):
                                        continue
                                    p = press(items, console, px, py)[0]
                                    require(all(c[0] == 'stick' for c in p), tag + ': a stick finger pressed ' + str(p))
                    # multitouch: stick + face button + shoulder at once are three distinct controls
                    def centre(name):
                        for it in items:
                            if name in inputs_of(it):
                                f = it['frame']; return f['x'] + f['width'] / 2, f['y'] + f['height'] / 2
                    fingers = [centre('cross'), centre('l1'), centre('leftThumbstickUp')]
                    sets = [press(items, console, *p)[1] for p in fingers]
                    require(len(set(sets)) == 3 and -1 not in sets, tag + ': simultaneous fingers collide')
                else:
                    # Dolphin: a stick finger stays on its stick only (DOLSkinOverlay touchesMoved),
                    # and stick + face button + shoulder are three distinct, simultaneous controls.
                    def centre_of(raw):
                        for it in items:
                            if raw in inputs_of(it):
                                f = it['frame']; return f['x'] + f['width'] / 2, f['y'] + f['height'] / 2
                        fail('%s: no control for %s' % (tag, raw))
                    shoulder = 'l' if console == 'gc' else 'c'
                    fingers = [centre_of('leftThumbstickUp'), centre_of('a'), centre_of(shoulder)]
                    sets = [press(items, console, *p)[1] for p in fingers]
                    require(len(set(sets)) == 3 and -1 not in sets, tag + ': simultaneous fingers collide')
                    for item in items:
                        if 'thumbstick' in item:
                            f = item['frame']
                            for dx in (0.1, 0.5, 0.9):
                                for dy in (0.1, 0.5, 0.9):
                                    p = press(items, console, f['x'] + dx * f['width'], f['y'] + dy * f['height'])[0]
                                    require(all(c[0] == 'stick' for c in p), tag + ': a stick finger pressed ' + str(p))
                    # release / cancel: a point on no control and outside the screen presses nothing
                    W, H = layout['mappingSize']['width'], layout['mappingSize']['height']
                    corners = [(0.5, 0.5), (W - 0.5, 0.5), (0.5, H - 0.5), (W - 0.5, H - 0.5)]
                    require(any(item_at(items, *c) < 0 for c in corners), tag + ': no neutral point')
                report.append(tag)
    # menu path on the sender side: press opens the menu through the session, once.
    require(re.search(r'if \(!pressed\) return;\s*if \(\[canonical isEqualToString:@"menu"\]', DOL), 'Dolphin menu sender')
    require('if (pressed && [canonical isEqualToString:@"menu"])' in A2, 'ARMSX2 menu sender')
    require(A2.count('dispatch_async(dispatch_get_main_queue()') >= 1, 'menu after the touch event')
    print('pocket skin input chain: ok (%d layouts, %d packs; DOLSkinHitTest.h / ARMSX2SkinHitTest.h compiled and matched on %d grid points; '
          '%d drawn sprite points reach their own control; earlier packs answer as the previous rectangle test on %d points)'
          % (len(report), len(rows), CURRENT['grid'], CURRENT.get('shape_points', 0), CURRENT.get('unchanged', 0)))


if __name__ == '__main__':
    sys.exit(main())
