#!/usr/bin/env python3
"""Replay real CI observations at the catalogue publication boundary.

Akirus's first successful import used the wrong PAL target; its corrected
USA check and the flat Devil Kings archive remain publishable. A historical
NCAA pack-name false positive has no explicit contrary serial evidence.
No archive is downloaded or installed again by this check.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/textures'))
import build_catalogue as catalogue  # noqa: E402

entries, records = catalogue.load()
by_id = {entry['id']: entry for entry in entries}
history = json.loads((ROOT / 'tools/textures/research/target-400-superseded-records.json').read_text())['records']
identifier = 'ps2-ktx-dragon-ball-z-budokai-tenkaichi-3-akirus'
original = next(item['record'] for item in history
                if item['run'] == 39406754238 and item['record']['id'] == identifier)
message = io.StringIO()
try:
    with contextlib.redirect_stdout(message), contextlib.redirect_stderr(message):
        catalogue.build([copy.deepcopy(by_id[identifier])], {identifier: original})
except SystemExit as error:
    assert error.code == 1 and 'archive identifies another disc' in message.getvalue()
else:
    raise AssertionError('The wrong-disc CI success became a published pack')

for identifier in ('ps2-ktx-devil-kings-i-emu-play', identifier):
    record = records[identifier]
    pack = catalogue.build([copy.deepcopy(by_id[identifier])], {identifier: record})[0]['packs'][0]
    assert pack['download']['verified']['sha256'] == record['parts'][0]['sha256']
    target = pack['install']['folders'][0]['to']
    assert target == record['installed'][0]['to']
    assert target.startswith(pack['games'][0]['identities'][0]['value'] + '/')

identifier = 'ps2-ncaa-06-next-vanilla'
pack = catalogue.build([copy.deepcopy(by_id[identifier])], {identifier: records[identifier]})[0]['packs'][0]
assert pack['download']['parts'][0]['sha256'] == records[identifier]['parts'][0]['sha256']
print('PASS: real wrong-disc import withheld; corrected USA and existing NCAA profiles accepted')
