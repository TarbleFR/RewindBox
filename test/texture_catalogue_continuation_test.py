#!/usr/bin/env python3
"""Continuation check of the published HD texture catalogue for PS1, 3DS and PSP.

tools/textures/check_ps1_expansion.py proves the PS1 publication of its own
revision and stays frozen. This check keeps relative invariants on the current
hosted and bundled manifests instead, without counts, downloads or
installations: every PS1 pack runs on Beetle, names its discs by SYSTEM.CNF
serial (SLUS-00067), declares only the regions the app gives their prefixes,
installs into the loaded game's own folder ({id}) and is offered only for
confirmation when it is manual; every 3DS pack runs on Azahar, names base
titles (application or demo) and installs only into its own title ID folders;
every PSP pack runs on PPSSPP and names PARAM.SFO disc IDs (ULUS10041) typed
disc_id. Each of these pairs is the one the app's reader gives a game of the
system (NeoTextureIdentity.h). The generator must reject each violation with
its message, and no source may declare an availability other than the
published one.
"""
import contextlib
import copy
import gzip
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/textures'))
import build_catalogue as catalogue  # noqa: E402

raw = catalogue.HOSTED.read_bytes()
assert raw == catalogue.BUNDLED.read_bytes(), 'Hosted and bundled catalogues differ'
index = json.loads(gzip.decompress(raw))
catalogue.validate(index)

# The generator's PS1 regions are the app's (NeoTextureIdentity.h: serial prefix -> region).
header = (ROOT / 'packages/neo_texture_catalog/ios/Classes/NeoTextureIdentity.h').read_text(encoding='utf-8')
body = re.search(r'inline std::string PS2Region\(const std::string& serial\) \{(.*?)\n\}', header, re.S)
assert body, 'PS2Region not found in NeoTextureIdentity.h'
app_regions = {prefix: region for prefixes, region in re.findall(r'if \(([^)]*)\) return "(\w+)";', body.group(1))
               for prefix in re.findall(r'"([A-Z]{4})"', prefixes)}
app_regions.update(re.findall(r'letters == "([A-Z]{4})" \? "(\w+)"', header))
assert app_regions == catalogue.PS1_REGIONS, f'PS1 regions of the generator differ from the app: {app_regions}'
# The type and scheme the app's reader gives each system's games: a pack can only match by ID what
# the reader produces (a PSP disc ID typed game_id matched no PSP pack by ID).
readers = {system: (kind, scheme)
           for system, kind, scheme in re.findall(r'r\.system = "(\w+)"; r\.type = "(\w+)"; r\.scheme = "([\w-]+)";', header)}
for system, pair in catalogue.IDENTITY_SCHEMES.items():
    assert readers.get(system) == pair, f'{system}: the app reads {readers.get(system)}, the generator requires {pair}'
assert 'psp' in catalogue.IDENTITY_SCHEMES, 'PSP packs must name the disc ID the app reads'


def systems(pack):
    return pack.get('systems') or [pack['system']]


ps1 = [pack for pack in index['packs'] if 'ps1' in systems(pack)]
assert ps1, 'No PS1 pack published'
serials, confirmed = set(), 0
for pack in ps1:
    where = pack['id']
    assert pack['engine'] == 'beetle', f'{where}: engine {pack["engine"]}'
    for game in pack['games']:
        found = {}
        for identity in game['identities']:
            assert (identity['type'], identity['scheme']) == ('serial', 'ps1-disc-serial'), f'{where}: {identity}'
            assert re.fullmatch(r'[A-Z]{4}-[0-9]{5}', identity['value']), f'{where}: serial {identity["value"]}'
            found[identity['value']] = app_regions.get(identity['value'][:4])
        serials |= set(found)
        if game.get('regions'):
            assert None not in found.values() and set(game['regions']) == set(found.values()), \
                f'{where}: regions {game["regions"]} for {found}'
        if pack['availability'] == 'manual':
            # Manual PS1 packs are only offered for an explicit confirmation (the rule check_ps1_expansion.py set).
            assert game.get('confirm') is True, f'{where}: {game["title"]} is not offered for confirmation'
            confirmed += 1
    for folder in (pack.get('install') or {}).get('folders', []):
        assert folder['to'] == '{id}', f'{where}: installs into {folder["to"]}'

n3ds = [pack for pack in index['packs'] if '3ds' in systems(pack)]
assert n3ds, 'No 3DS pack published'
title_ids = set()
for pack in n3ds:
    where = pack['id']
    assert pack['engine'] == 'azahar', f'{where}: engine {pack["engine"]}'
    own = set()
    for game in pack['games']:
        for identity in game['identities']:
            assert (identity['type'], identity['scheme']) == ('title_id', '3ds-title-id'), f'{where}: {identity}'
            assert re.fullmatch(r'0004000[02][0-9A-F]{8}', identity['value']), f'{where}: title ID {identity["value"]}'
            own.add(identity['value'])
    title_ids |= own
    for folder in (pack.get('install') or {}).get('folders', []):
        assert '{id}' in folder['to'] or folder['to'] in own, f'{where}: installs into {folder["to"]}'

psp = [pack for pack in index['packs'] if 'psp' in systems(pack)]
assert psp, 'No PSP pack published'
disc_ids = set()
for pack in psp:
    where = pack['id']
    assert pack['engine'] == 'ppsspp', f'{where}: engine {pack["engine"]}'
    for game in pack['games']:
        for identity in game['identities']:
            assert (identity['type'], identity['scheme']) == ('disc_id', 'psp-param-sfo-disc-id'), f'{where}: {identity}'
            assert re.fullmatch(r'[A-Z]{4}[0-9]{5}', identity['value']), f'{where}: disc ID {identity["value"]}'
            disc_ids.add(identity['value'])


def outcome(pack):
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            catalogue.validate({'packs': [pack]})
    except SystemExit as error:
        assert error.code == 1, output.getvalue()
        return output.getvalue()
    return None


def changed(pack, change):
    pack = copy.deepcopy(pack)
    change(pack)
    return pack


def first_identity(pack, value):
    pack['games'][0]['identities'][0]['value'] = value


cases = 0


def rejected(pack, message):
    global cases
    result = outcome(pack)
    assert result and message in result, f'{pack["id"]}: expected "{message}", got {result!r}'
    cases += 1


linked = next(pack for pack in n3ds if not pack.get('install'))
for value in ('0004000E000EC300', '0004008C000EC300', '000EC300', '00040000000ec300', '00040000000EC3000'):
    rejected(changed(linked, lambda pack: first_identity(pack, value)), f'3DS title ID {value} is not 16 upper-case hex digits')
for value in ('00040000000EC300', '00040002000EC300'):
    assert outcome(changed(linked, lambda pack: first_identity(pack, value))) is None, value
rejected(changed(linked, lambda pack: pack['games'][0]['identities'][0].update(scheme='ctr-title-id')),
         'identity title_id/ctr-title-id, expected title_id/3ds-title-id')
fixed = next(pack for pack in n3ds if any('{id}' not in folder['to'] for folder in (pack.get('install') or {}).get('folders', [])))
target = next(folder for folder in fixed['install']['folders'] if '{id}' not in folder['to'])['to']
rejected(changed(fixed, lambda pack: next(folder for folder in pack['install']['folders'] if folder['to'] == target)
                 .update(to='0004000000000000')), 'to 0004000000000000 is not one of its title IDs')

installed = next(pack for pack in ps1 if pack.get('install') and all(game.get('regions') for game in pack['games']))
serial = installed['games'][0]['identities'][0]['value']
rejected(changed(installed, lambda pack: first_identity(pack, serial.replace('-', ''))),
         f'PS1 serial {serial.replace("-", "")} is not in the form SLUS-00067')
rejected(changed(installed, lambda pack: first_identity(pack, serial.lower())), f'PS1 serial {serial.lower()} is not')
other = next(region for region in ('USA', 'Europe', 'Japan') if region not in installed['games'][0]['regions'])
rejected(changed(installed, lambda pack: pack['games'][0].update(regions=[other])), f'regions [\'{other}\'] of')
rejected(changed(installed, lambda pack: first_identity(pack, 'ABCD' + serial[4:])),
         f'no region is known for the prefix of ABCD{serial[4:]}: declare no regions')
assert outcome(changed(installed, lambda pack: [first_identity(pack, 'ABCD' + serial[4:]), pack['games'][0].pop('regions')])) is None
rejected(changed(installed, lambda pack: pack['games'][0]['identities'][0].update(scheme='ps2-disc-serial')),
         'identity serial/ps2-disc-serial, expected serial/ps1-disc-serial')
rejected(changed(installed, lambda pack: pack['install']['folders'][0].update(to=serial)),
         f'to {serial}: a Beetle pack installs into the folder of the game it is chosen for')
rejected(changed(installed, lambda pack: pack.update(engine='mednafen')), 'engine mednafen does not run ps1')

disc = psp[0]
for value in ('ULUS-10041', 'ulus10041', 'ULUS1004', 'UL0S10041', 'ULUS100410'):
    rejected(changed(disc, lambda pack: first_identity(pack, value)), f'PSP disc ID {value} is not four letters and five digits')
assert outcome(changed(disc, lambda pack: first_identity(pack, 'ULUS10041'))) is None
rejected(changed(disc, lambda pack: pack['games'][0]['identities'][0].update(type='game_id')),
         'psp identity game_id/psp-param-sfo-disc-id, expected disc_id/psp-param-sfo-disc-id')

entries, _ = catalogue.load()
stale = catalogue.declared_availability(entries, index)
assert not stale, stale
available = next(pack for pack in index['packs'] if pack['availability'] == 'available')
assert catalogue.declared_availability([{'id': available['id'], 'availability': 'manual'}, {'id': available['id']},
                                        {'id': 'not-published', 'availability': 'available'}], index) == \
    [f'{available["id"]} declares manual, published available']
published = {pack['id'] for pack in index['packs']}
compared = sum(1 for entry in entries if 'availability' in entry and entry['id'] in published)

print(f'PASS: {len(ps1)} PS1 packs ({len(serials)} serials, {confirmed} manual games offered for confirmation), '
      f'{len(n3ds)} 3DS packs ({len(title_ids)} title IDs) and {len(psp)} PSP packs ({len(disc_ids)} disc IDs, typed as the app '
      f'reads them) of {index["revision"]} keep their continuation invariants; '
      f'{cases} synthetic violations rejected; {compared} declared availabilities match the published ones')
