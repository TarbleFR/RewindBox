#!/usr/bin/env python3
"""Proof gates for the read-only NCL/native author crosswalk."""
import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('crosswalk', ROOT / 'tools/cheats/unified_native_artemis.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ppu = '0123456789abcdef0123456789abcdef01234567'
document = {'Version': 1.2, 'PPU-' + ppu: {'Infinite health': {
    'Games': {'Game': {'BLES00001': ['01.01']}}, 'Patch': [['be32', '0x00000010', 0x60000000]]}}}
game = {'revision': '01.01', 'identities': [
    {'type': 'serial', 'scheme': 'ps3-title-id', 'value': 'BLES00001'},
    {'type': 'ppu_hash', 'scheme': 'rpcs3-ppu-hash', 'value': ppu}],
    'cheats': [{'name': 'Infinite health', 'native_document': document}]}
index = module.authored_index([game])
assert index
ncl = b'Infinite health\n0\nAuthor\n0 00000010 60000000\n#\n'
matches, _ = module.crosswalk(ncl, 'Game BLES00001 v01.00 av01.01.ncl', index)
assert len(matches) == 1 and matches[0]['targets'][0]['native_document'] == document
for path in ('Game BLES00001 v01.01.ncl', 'Game BLES00001 01.00.ncl', 'Game BLES00002 01.01.ncl'):
    assert not module.crosswalk(ncl, path, index)[0]
for bad in (ncl.replace(b'\n0\n', b'\n1\n'), ncl.replace(b'0 00000010', b'6 00000010'),
            ncl.replace(b'60000000', b'60000001'), ncl.replace(b'Infinite health', b'Other cheat'),
            ncl.replace(b'\n#', b'\n0 00000014 60000000\n#')):
    assert not module.crosswalk(bad, 'Game BLES00001 01.01.ncl', index)[0]
bad_game = copy.deepcopy(game)
bad_game['cheats'][0]['native_document']['PPU-' + ppu]['Infinite health']['Games']['Game']['BLES00001'] = ['01.00']
assert not module.authored_index([bad_game])
assert module.native_writes([['load', [['be32', '0x10', 1]]]]) == ((16, 1),)
assert module.native_writes([['load', [['be32', '0x10', 1]], 16]]) is None
assert module.native_writes([['be32', '0x10', 1], ['be32', '0x10', 2]]) == ((16, 1), (16, 2))
print('PASS: exact NCL/native author crosswalk; edition, hash, mode, operations and full-program gates.')
