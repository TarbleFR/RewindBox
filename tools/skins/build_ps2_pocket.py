#!/usr/bin/env python3
"""Build RewindBox's third original Pocket pack: PS2 Pocket - matte black.

Adds assets/skins/pocket/ps2-pocket.manicskin and its previews next to the two
existing packs, then adds (or replaces) only its catalog entry: the Wii and
GameCube archives, hashes and entries are not touched. Run build_pocket_skins.py
first when the output folder is new. Original artwork only (ps2_art.py); the
maintainer's reference picture was a visual brief, not an asset.
Requires the pinned Pillow/numpy dependencies (requirements.txt).
"""
from __future__ import annotations

import argparse, hashlib, io, json
from pathlib import Path

from PIL import Image

import build_pocket_skins as bp
import ps2_art

PID = 'ps2-pocket'
NAME = 'PS2 Pocket — Noir mat'
IDENTIFIER = 'org.rewindbox.ps2-pocket-matte-black'
GAME_TYPE = 'public.aoshuang.game.ps2'
FACES = ('triangle', 'circle', 'cross', 'square')
ORIENTATIONS = ('portrait', 'landscape')
DISPLAYS = ('edgeToEdge', 'standard')
EXPECTED = ({'cross', 'circle', 'square', 'triangle', 'l1', 'l2', 'r1', 'r2', 'select', 'start', 'l3', 'r3', 'menu',
             'up', 'down', 'left', 'right'}
            | {f'{side}Thumbstick{d}' for side in ('left', 'right') for d in ('Up', 'Down', 'Left', 'Right')})
LICENSE = """Original artwork and layouts prepared for RewindBox (PS2 Pocket - matte black).
Rendered procedurally for this project; no photograph, third-party skin or game artwork is included.
PlayStation and PS2 names and marks belong to their respective owners. No third-party rights are granted.
Publication licensing is to be set by the project maintainer.
"""


def b(name, x, y, w, h):
    return bp.button(name, x, y, w, h)


def stick(side, x, y, size):
    base = 'lstick' if side == 'left' else 'rstick'
    return {'frame': bp.rect(x, y, size, size),
            'inputs': {d: f'{side}Thumbstick{d.title()}' for d in ('up', 'down', 'left', 'right')},
            'asset': {'normal': f'controls/{base}-base.png', 'pressed': f'controls/{base}-base-pressed.png'},
            'thumbstick': {'name': 'controls/stick-knob.png', 'width': round(size * .62, 2), 'height': round(size * .62, 2)},
            'extendedEdges': dict(top=0, bottom=0, left=0, right=0)}


def face_cluster(cx_left, top, s):
    """True diamond: the boxes touch but never overlap (frame == s == step)."""
    return [b('triangle', cx_left + s, top, s, s), b('square', cx_left, top + s, s, s),
            b('circle', cx_left + 2 * s, top + s, s, s), b('cross', cx_left + s, top + 2 * s, s, s)]


def layout(display, orientation):
    edge, portrait = display == 'edgeToEdge', orientation == 'portrait'
    W, H = (393, 852) if edge and portrait else (852, 393) if edge else (375, 667) if portrait else (667, 375)
    if edge and portrait:
        screen = bp.rect(8, 76, 377, 282.75)
        items = [b('l2', 20, 368, 72, 48), b('l1', 96, 368, 72, 48), b('r1', 225, 368, 72, 48), b('r2', 301, 368, 72, 48),
                 bp.dpad(24, 436, 132), *face_cluster(225, 432, 48),
                 b('select', 112, 592, 84, 48), b('start', 200, 592, 84, 48),
                 stick('left', 28, 650, 108), stick('right', 257, 650, 108),
                 b('l3', 52, 764, 60, 48), b('r3', 281, 764, 60, 48), b('menu', 170, 752, 52, 52)]
        analog = 700
    elif edge:
        screen = bp.rect(252, 66, 348, 261)
        items = [b('l1', 64, 12, 80, 48), b('l2', 148, 12, 80, 48), b('r1', 624, 12, 80, 48), b('r2', 708, 12, 80, 48),
                 b('menu', 400, 8, 52, 48),
                 bp.dpad(78, 66, 128), stick('left', 82, 198, 100), b('l3', 188, 252, 50, 48), b('select', 96, 320, 84, 48),
                 *face_cluster(624, 66, 48), stick('right', 668, 214, 100), b('r3', 610, 266, 50, 48), b('start', 684, 320, 84, 48)]
        analog = None
    elif portrait:
        screen = bp.rect(8, 48, 359, 269.25)
        items = [b('l2', 10, 324, 76, 44), b('l1', 90, 324, 76, 44), b('r1', 209, 324, 76, 44), b('r2', 289, 324, 76, 44),
                 bp.dpad(14, 376, 116), *face_cluster(234, 380, 44),
                 b('select', 110, 520, 70, 44), b('start', 190, 520, 70, 44),
                 stick('left', 16, 570, 84), stick('right', 275, 570, 84),
                 b('l3', 104, 596, 50, 44), b('r3', 221, 596, 50, 44), b('menu', 164, 600, 48, 48)]
        analog = 580
    else:
        screen = bp.rect(166, 50, 336, 252)
        items = [b('l1', 10, 6, 70, 44), b('l2', 84, 6, 70, 44), b('r1', 513, 6, 70, 44), b('r2', 587, 6, 70, 44),
                 b('menu', 310, 4, 48, 44),
                 bp.dpad(22, 54, 100), stick('left', 30, 160, 84), b('l3', 47, 248, 50, 44), b('select', 28, 312, 80, 44),
                 *face_cluster(518, 54, 44), stick('right', 546, 190, 84), b('r3', 563, 278, 50, 44), b('start', 544, 326, 80, 44)]
        analog = None
    return {'W': W, 'H': H, 'screen': screen, 'items': items, 'analog': analog}


def validate(reps, files):
    result = []
    for display, orientations in reps.items():
        for orientation, L in orientations.items():
            W, H = L['mappingSize'].values()
            screen = L['screens'][0]['outputFrame']
            provided, minsize = set(), 999
            for i, item in enumerate(L['items']):
                f = item['frame']; box = bp.box(f)
                assert 0 <= box[0] < box[2] <= W and 0 <= box[1] < box[3] <= H, (display, orientation, i, 'bounds')
                assert not bp.intersect(f, screen), (display, orientation, i, 'screen')
                for prev in L['items'][:i]:
                    assert not bp.intersect(f, prev['frame']), (display, orientation, i, 'overlap', prev['frame'])
                minsize = min(minsize, f['width'], f['height'])
                inputs = item['inputs']
                provided.update(inputs if isinstance(inputs, list) else inputs.values())
                for p in item['asset'].values():
                    assert p in files, p
                assert files[item['asset']['normal']] != files[item['asset']['pressed']], item['asset']
                if 'thumbstick' in item:
                    assert item['thumbstick']['name'] in files
            assert EXPECTED <= provided, (display, orientation, EXPECTED - provided)
            assert 'menu' in provided and sum('menu' in (i['inputs'] if isinstance(i['inputs'], list) else []) for i in L['items']) == 1
            assert abs(screen['width'] / screen['height'] - 4 / 3) < .0001
            if display == 'edgeToEdge':
                for aw, ah in [(375, 812), (390, 844), (393, 852), (430, 932)]:
                    if orientation == 'landscape':
                        aw, ah = ah, aw
                    assert minsize * min(aw / W, ah / H) >= 44, (orientation, aw, ah, minsize)
                if orientation == 'portrait':
                    assert all(bp.box(i['frame'])[1] >= 65 and bp.box(i['frame'])[3] <= H - 35 for i in L['items'])
                else:
                    assert all(bp.box(i['frame'])[0] >= 60 and bp.box(i['frame'])[2] <= W - 60 and bp.box(i['frame'])[3] <= H - 24
                               for i in L['items'])
            else:
                assert minsize >= 44
            result.append({'display': display, 'orientation': orientation, 'size': [W, H], 'items': len(L['items']),
                           'smallestTargetPoints': minsize})
    return result


def build(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    files = {'LICENSE.txt': LICENSE.encode()}
    reps = {}
    for display in DISPLAYS:
        reps[display] = {}
        for orientation in ORIENTATIONS:
            spec = layout(display, orientation)
            name = f'body-{"edge" if display == "edgeToEdge" else "standard"}-{orientation}.png'
            files[name] = bp.png(ps2_art.body(spec['W'], spec['H'], spec['screen'], spec['items'], orientation=orientation,
                                              analog_y=spec['analog']))
            reps[display][orientation] = {
                'assets': {'small': name, 'medium': name, 'large': name},
                'mappingSize': {'width': spec['W'], 'height': spec['H']},
                'screens': [{'outputFrame': spec['screen']}], 'items': spec['items'], 'translucent': False}
    names = set()
    for orientations in reps.values():
        for L in orientations.values():
            for item in L['items']:
                if isinstance(item['inputs'], list):
                    names.update(item['inputs'])
    names.add('dpad')
    for n in sorted(names):
        for held in (False, True):
            files[f'controls/{n}{"-pressed" if held else ""}.png'] = bp.png(ps2_art.control(n, held))
    for side in ('lstick', 'rstick'):
        for held in (False, True):
            files[f'controls/{side}-base{"-pressed" if held else ""}.png'] = bp.png(ps2_art.stick_base(held))
    files['controls/stick-knob.png'] = bp.png(ps2_art.stick_knob())
    for orientation in ORIENTATIONS:
        image = bp.png(bp.compose(reps['edgeToEdge'][orientation], files))
        files[f'previews/{orientation}.png'] = image
        (out / f'{PID}-{orientation}.png').write_bytes(image)
        (out / f'{PID}-{orientation}-pressed.png').write_bytes(bp.png(bp.compose(reps['edgeToEdge'][orientation], files, pressed=True)))
        (out / f'{PID}-standard-{orientation}.png').write_bytes(bp.png(bp.compose(reps['standard'][orientation], files)))
    info = {'name': NAME, 'identifier': IDENTIFIER, 'author': 'RewindBox', 'gameTypeIdentifier': GAME_TYPE, 'version': 1,
            'license': bp.LICENSE_LABEL, 'previewImages': {o: f'previews/{o}.png' for o in ORIENTATIONS},
            'provenance': {'status': 'original-procedural', 'generator': 'tools/skins/build_ps2_pocket.py',
                           'reference': 'maintainer visual brief only; no asset reused', 'layoutVersion': 1},
            'representations': {'iphone': reps}}
    files['info.json'] = (json.dumps(info, indent=2, ensure_ascii=False) + '\n').encode()
    checks = validate(reps, files)
    for path, data in files.items():
        if path.endswith('.png'):
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
    target = out / f'{PID}.manicskin'
    bp.archive(target, files)
    entry = {'id': PID, 'name': NAME, 'console': 'ps2', 'archiveAsset': f'assets/skins/pocket/{PID}.manicskin',
             'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'size': target.stat().st_size,
             'previewAssets': {o: f'assets/skins/pocket/{PID}-{o}.png' for o in ORIENTATIONS},
             'author': 'RewindBox', 'license': bp.LICENSE_LABEL}
    catalog_path = out / 'catalog.json'
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {'schemaVersion': 1, 'skins': []}
    catalog['skins'] = [s for s in catalog['skins'] if s['id'] != PID] + [entry]
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    receipt = {'layouts': checks, 'archiveSha256': entry['sha256'], 'archiveBytes': entry['size'],
               'files': {p: {'sha256': hashlib.sha256(d).hexdigest(), 'bytes': len(d)} for p, d in sorted(files.items())},
               'physicalDeviceTested': False}
    (out / 'validation-ps2.json').write_text(json.dumps({'generator': 'tools/skins/build_ps2_pocket.py', 'scale': bp.SCALE,
                                                           'skins': {PID: receipt}}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(out), 'skin': entry}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=bp.ROOT / 'assets/skins/pocket')
    build(parser.parse_args().output)
