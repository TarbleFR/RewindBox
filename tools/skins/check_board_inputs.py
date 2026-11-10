#!/usr/bin/env python3
"""Bind the maintainer's original PNG targets to the boards the Originals are built from.

Usage: python3 tools/skins/check_board_inputs.py DIR   (DIR = the extracted
rewindbox-skins-original-png-20261104.zip, with its SHA256SUMS)

Checks the SHA-256 of each target, finds where it sits in the repository board, and
requires every RGBA pixel of the overlap to be identical, the overlap to cover every
region build_pocket_board_originals.py reads (crops, sprites, caps). Then the packs are
made from the maintainer's own pixels. Prints the offsets as JSON.
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pocket_board_originals as b  # noqa: E402

TARGETS = {'gc': ('01-target-gamecube-pocket.png', '78890512441cb3accfd80a295001923481de1e6a59f07202263bd5d746697f9d'),
           'wii': ('03-target-wii-pocket.png', 'bfb4da275b897abc3637f0dd0f3aecc412c1fbf1133c8ef63ffa62c7cd05e0b6')}


def offset_of(target, board):
    """Exact placement of target inside board (target is a crop), else None."""
    th, tw = target.shape[:2]
    for dy in range(board.shape[0] - th + 1):
        for dx in range(board.shape[1] - tw + 1):
            if np.array_equal(board[dy:dy + th, dx:dx + tw], target):
                return dx, dy
    return None


def target_board(console, folder):
    """The maintainer's target in the board's coordinates (pasted at its exact offset),
    for comparisons made against the original PNG itself."""
    name, _ = TARGETS[console]
    target = Image.open(Path(folder) / name).convert('RGB')
    board = Image.open(b.BOARDS / b.PACKS[console]['board'])
    where = offset_of(np.asarray(target.convert('RGBA')), np.asarray(board.convert('RGBA')))
    if where is None:
        raise SystemExit(f'{name}: not a crop of {b.PACKS[console]["board"]}')
    canvas = Image.new('RGB', board.size, (0, 0, 0))
    canvas.paste(target, where)
    return canvas


def main():
    folder = Path(sys.argv[1])
    report = {}
    for console, (name, digest) in TARGETS.items():
        data = (folder / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit(f'{name}: SHA-256 differs from the relayed identity')
        target = np.asarray(Image.open(folder / name).convert('RGBA'))
        pack = b.PACKS[console]
        board = np.asarray(Image.open(b.BOARDS / pack['board']).convert('RGBA'))
        where = offset_of(target, board)
        if where is None:
            raise SystemExit(f'{name}: not a pixel-identical crop of {pack["board"]}')
        dx, dy = where
        cover = (dx, dy, dx + target.shape[1], dy + target.shape[0])
        regions = []
        for o in ('portrait', 'landscape'):
            spec = pack[o]
            regions.append(spec['crop'])
            for item in spec['items']:
                x, y, w, h = item[2]
                regions.append((x, y, x + w, y + h))
        outside = [r for r in regions if r[0] < cover[0] or r[1] < cover[1] or r[2] > cover[2] or r[3] > cover[3]]
        if outside:
            raise SystemExit(f'{name}: builder reads outside the maintainer image: {outside}')
        report[console] = {'target': name, 'sha256': digest, 'targetSize': [target.shape[1], target.shape[0]],
                           'board': f'docs/design/pocket/{pack["board"]}', 'offsetInBoard': [dx, dy],
                           'identicalRGBAPixels': int(target.shape[0] * target.shape[1]),
                           'builderRegionsCovered': len(regions)}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
