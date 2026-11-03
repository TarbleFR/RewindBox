#!/usr/bin/env python3
"""Every visible control of the three shipped Pocket skins reaches its engine.

Runs on the REAL archives (assets/skins/pocket/*.manicskin, bound by the catalog
SHA-256) and traces, for every layout (iPhone edgeToEdge and standard, portrait
and landscape) and every item: sprite -> touch target -> canonical command ->
engine command. The canonical table and the engine tables are read from the
native sources themselves (DOLSkinOverlay.mm for Dolphin, ARMSX2SkinOverlay.mm
for ARMSX2), so a drift between a skin, its table and its sender fails here.
It also exercises the touch model on the shipped geometry (press, drag between
controls, release; two fingers; a stick finger never presses L3/R3).

This is a host test of files and tables. It is not an UIKit run and not a game
run: physical iPhone play stays a separate, unobserved step.
"""
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets/skins/pocket'
DOL = (ROOT / 'packages/dolphin_internal_bridge/ios/Classes/DOLSkinOverlay.mm').read_text(encoding='utf-8')
A2 = (ROOT / 'packages/armsx2_internal_bridge/ios/Classes/ARMSX2SkinOverlay.mm').read_text(encoding='utf-8')
DIRECTIONS = ('Up', 'Down', 'Left', 'Right')


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
    return json.loads(z.read('info.json')), set(z.namelist())


def rect(f):
    return (f['x'], f['y'], f['x'] + f['width'], f['y'] + f['height'])


def inputs_of(item):
    value = item['inputs']
    return list(value.values()) if isinstance(value, dict) else list(value)


def item_at(items, x, y):
    """DOLSkinOverlay itemAtPoint: last drawn first, drawn frame, then hit frame."""
    for use_hit in (False, True):
        for index in range(len(items) - 1, -1, -1):
            f = rect(items[index]['frame'])
            if f[0] <= x < f[2] and f[1] <= y < f[3]:
                return index
    return -1


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
    rows = {row['console']: row for row in catalog['skins']}
    require(set(rows) == {'gc', 'wii', 'ps2'}, 'the catalog must carry exactly Wii, GameCube and PS2')
    require(UPSTREAM_PS2 == [n for n, _ in sorted(PS2_IDS.items(), key=lambda kv: kv[1])],
            'ARMSX2 pad indices differ from ARMSX2Bridge.h: %s' % PS2_IDS)
    report = []
    for console, row in sorted(rows.items()):
        info, names = load_pack(row)
        require(info['gameTypeIdentifier'].split('.')[-1] in {'gc': {'ngc'}, 'wii': {'wii'}, 'ps2': {'ps2'}}[console],
                console + ': game type')
        reps = info['representations']['iphone']
        for display in ('edgeToEdge', 'standard'):
            for orientation in ('portrait', 'landscape'):
                layout = reps[display][orientation]
                tag = '%s/%s/%s' % (console, display, orientation)
                items = layout['items']
                menu_items = []
                seen = set()
                for index, item in enumerate(items):
                    # sprite
                    for state in ('normal', 'pressed'):
                        require(item['asset'][state] in names, tag + ': missing sprite ' + item['asset'][state])
                    require(item['asset']['normal'] != item['asset']['pressed'], tag + ': same sprite for both states')
                    # touch target
                    f = item['frame']
                    require(min(f['width'], f['height']) >= 44, tag + ': target under 44 points')
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
                    # L3 / R3 are targets of their own: a finger on a stick never presses them.
                    for item in items:
                        if 'thumbstick' in item:
                            f = item['frame']
                            for dx in (0.1, 0.5, 0.9):
                                for dy in (0.1, 0.5, 0.9):
                                    p = press(items, console, f['x'] + dx * f['width'], f['y'] + dy * f['height'])[0]
                                    require(all(c[0] == 'stick' for c in p), tag + ': a stick finger pressed ' + str(p))
                    # multitouch: stick + face button + shoulder at once are three distinct controls
                    def centre(name):
                        for it in items:
                            if name in inputs_of(it):
                                f = it['frame']; return f['x'] + f['width'] / 2, f['y'] + f['height'] / 2
                    fingers = [centre('cross'), centre('l1'), centre('leftThumbstickUp')]
                    sets = [press(items, console, *p)[1] for p in fingers]
                    require(len(set(sets)) == 3 and -1 not in sets, tag + ': simultaneous fingers collide')
                report.append(tag)
    # menu path on the sender side: press opens the menu through the session, once.
    require(re.search(r'if \(!pressed\) return;\s*if \(\[canonical isEqualToString:@"menu"\]', DOL), 'Dolphin menu sender')
    require('if (pressed && [canonical isEqualToString:@"menu"])' in A2, 'ARMSX2 menu sender')
    require(A2.count('dispatch_async(dispatch_get_main_queue()') >= 1, 'menu after the touch event')
    print('pocket skin input chain: ok (%d layouts, 3 packs)' % len(report))


if __name__ == '__main__':
    sys.exit(main())
