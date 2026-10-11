#!/usr/bin/env python3
"""Contract of assets/data/libretro_bios_requirements.json (BIOS checker,
Build 438).

Without --cores (any host), against the vendored public reference data
test/fixtures/libretro_bios/core_info_5a74858a.json (firmware lines and notes
md5 of the 14 embedded cores' .info files at libretro-core-info 5a74858a, and
the matching System.dat rows at libretro-database f206bf65):
- every firmware line of a packaged core's .info is described by an entry
  (same core, name and folder) or excluded with a reason, and every entry
  claim names a real firmware line;
- every md5 the .info notes give is a known dump of the entry, every dump
  taken from System.dat matches its row exactly, and every System.dat row of
  an entry's name and folder is a known dump;
- the PlayStation rows carry exactly the names of NeoStation's launch rule
  (LibretroCore.biosAnyOf), each in one region row;
- consoles, cores and systems exist in LibretroCoreCatalog, every text key
  exists in the English LibretroLocale map, no BIOS byte is shipped;
- the --cores check itself passes on a synthetic artifact holding every
  string and fails when one is missing.

With --cores DIR (the pinned LibretroCores artifact, macOS CI), also requires
that every name each entry says a core reads appears in that core's binary,
that both Beetle PSX binaries offer OpenBIOS when the data says they fall
back to it, and that the bundled PPSSPP files exist with the SHA-256
identity.json records.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / 'assets/data/libretro_bios_requirements.json'
FIXTURE = ROOT / 'test/fixtures/libretro_bios/core_info_5a74858a.json'
CORE_INFO_COMMIT = '5a74858ab2f7a50cebb5a6330895bc38899531c0'
SYSTEM_DAT_COMMIT = 'f206bf65'


def fail(message):
    raise SystemExit('libretro BIOS requirements: ' + message)


def require(condition, message):
    if not condition:
        fail(message)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dart_catalog():
    text = (ROOT / 'lib/services/libretro_core_catalog.dart').read_text(encoding='utf-8')
    cores_block = text[text.index('Map<String, LibretroCore> cores'):text.index('Map<String, LibretroSystemBinding> systems')]
    starts = list(re.finditer(r"^\s*'([a-z0-9_]+)': LibretroCore\(", cores_block, re.M))
    bios = {}
    for index, start in enumerate(starts):
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(cores_block)
        block = cores_block[start.end():stop]
        match = re.search(r'biosAnyOf:\s*\[([^\]]*)\]', block)
        bios[start.group(1)] = re.findall(r"'([^']+)'", match.group(1)) if match else []
    systems_block = text[text.index('Map<String, LibretroSystemBinding> systems'):text.index('Map<String, LibretroConsole> consoles')]
    systems = {}
    for match in re.finditer(r"'([a-z0-9-]+)': LibretroSystemBinding\(coreId: '([a-z0-9_]+)', console: '([a-z0-9]+)'(?:, alternatives: \[([^\]]*)\])?", systems_block):
        systems[match.group(1)] = {
            'core': match.group(2),
            'console': match.group(3),
            'alternatives': re.findall(r"'([^']+)'", match.group(4) or ''),
        }
    consoles_block = text[text.index('Map<String, LibretroConsole> consoles'):]
    consoles = re.findall(r"^\s*'([a-z0-9]+)': LibretroConsole\(", consoles_block, re.M)
    return bios, systems, consoles


def english_keys():
    source = (ROOT / 'lib/l10n/libretro_locale.dart').read_text(encoding='utf-8')
    start = source.index("    'en': {")
    end = source.index('\n    },', start)
    return set(re.findall(r"^\s*'([A-Za-z0-9_]+)':", source[start:end], re.M))


def location_dir(location):
    if location == 'system':
        return ''
    if location.startswith('system/'):
        return location[len('system/'):]
    return None


def info_path_matches(entry, path):
    directory, _, name = path.rpartition('/')
    names = set(entry['names'])
    for alternatives in entry.get('coreNames', {}).values():
        names.update(alternatives)
    return name in names and directory in {location_dir(location) for location in entry['locations']}


def check_data(requirements, fixture):
    findings = []
    cores_info = fixture['coreInfo']['cores']
    dat = fixture['systemDat']['roms']
    entries = requirements['entries']
    excluded = {(item['core'], item['path']): item['reason'] for item in requirements.get('excluded', [])}
    bios, systems, consoles = dart_catalog()
    english = english_keys()
    manifest = read_json(ROOT / 'build-utils/libretro/cores.json')
    packaged = [core['id'] for core in manifest['cores']]

    require(requirements['schema'] == 1, 'schema 1 expected')
    require(requirements['sources']['coreInfo']['commit'] == CORE_INFO_COMMIT == fixture['coreInfo']['commit'],
            'core-info revision differs from the fixture')
    require(requirements['sources']['systemDat']['commit'] == SYSTEM_DAT_COMMIT == fixture['systemDat']['commit'],
            'System.dat revision differs from the fixture')
    require(sorted(cores_info) == sorted(packaged), 'the fixture covers exactly the packaged cores')
    require(sorted(bios) == sorted(packaged), 'LibretroCoreCatalog lists exactly the packaged cores')
    require(isinstance(requirements['flags'].get('beetleOpenBiosFallback'), bool), 'OpenBIOS flag missing')

    ids = [entry['id'] for entry in entries]
    require(len(ids) == len(set(ids)), 'duplicate entry ids')
    require(sorted(requirements['consoles']) == sorted(consoles), 'one console section per embedded console')

    # 1. .info firmware lines <-> entries.
    claimed = set()
    for entry in entries:
        for console in entry['consoles']:
            if console not in consoles:
                findings.append(f"{entry['id']}: unknown console {console}")
        for core in entry['cores']:
            if core not in bios:
                findings.append(f"{entry['id']}: unknown core {core}")
                continue
            if not any(binding['console'] in entry['consoles'] and
                       (binding['core'] == core or core in binding['alternatives']) for binding in systems.values()):
                findings.append(f"{entry['id']}: {core} never runs a game of {entry['consoles']}")
        for system in set(entry.get('gameFolderSystems', [])) | {
                system for clause in (entry.get('condition') or {}).get('games', []) for system in clause['systems']}:
            if system not in systems:
                findings.append(f"{entry['id']}: unknown system {system}")
        for claim in entry.get('info', []):
            core, path = claim['core'], claim['path']
            firmware = [item['path'] for item in cores_info.get(core, {}).get('firmware', [])]
            if path not in firmware:
                findings.append(f"{entry['id']}: {core} .info has no firmware {path}")
            if core not in entry['cores']:
                findings.append(f"{entry['id']}: claims {core} {path} without that core")
            if not info_path_matches(entry, path):
                findings.append(f"{entry['id']}: {path} is not one of its names and folders")
            claimed.add((core, path))
    for core, info in cores_info.items():
        for item in info['firmware']:
            key = (core, item['path'])
            if key in claimed and key in excluded:
                findings.append(f'{core} {item["path"]} is both described and excluded')
            elif key not in claimed and key not in excluded:
                findings.append(f'{core} {item["path"]} is neither described nor excluded')
        if info['firmware'] and not any(core in entry['cores'] for entry in entries):
            findings.append(f'{core}: firmware listed but no entry')
    for (core, path), reason in excluded.items():
        if not reason.strip():
            findings.append(f'{core} {path}: exclusion without a reason')

    # 2. Checksums: .info notes and System.dat.
    by_hash = {(row['size'], row['md5'], row['sha1']): row for row in dat}
    for entry in entries:
        dumps = entry.get('knownDumps', [])
        md5s = {dump.get('md5') for dump in dumps}
        for claim in entry.get('info', []):
            note = cores_info[claim['core']]['notes_md5'].get(claim['path'].rpartition('/')[2])
            if note and note not in md5s:
                findings.append(f"{entry['id']}: .info md5 {note} of {claim['path']} is not a known dump")
        for dump in dumps:
            for field, length in (('md5', 32), ('sha1', 40), ('crc', 8)):
                value = dump.get(field)
                if value is not None and not re.fullmatch(rf'[0-9a-f]{{{length}}}', value):
                    findings.append(f"{entry['id']}: bad {field} {value}")
            if dump['source'] == 'System.dat':
                row = by_hash.get((dump['size'], dump.get('md5'), dump.get('sha1')))
                if row is None or row['crc'] != dump.get('crc'):
                    findings.append(f"{entry['id']}: {dump['label']} does not match a System.dat row")
        paths = {
            (location_dir(location) + '/' if location_dir(location) else '') + name
            for location in entry['locations'] if location_dir(location) is not None
            for name in entry['names']
        }
        for row in dat:
            if row['name'] in paths and not any(
                    dump['size'] == row['size'] and dump.get('md5') == row['md5'] for dump in dumps):
                findings.append(f"{entry['id']}: System.dat row {row['name']} ({row['md5']}) is not a known dump")

    # 3. NeoStation's PlayStation launch rule.
    gate_rows = [entry for entry in entries if entry.get('gate') == 'psx']
    gate_names = {name for entry in gate_rows for core in entry['cores'] for name in bios[core]}
    require(gate_names == {'scph5500.bin', 'scph5501.bin', 'scph5502.bin'},
            f'PS1 launch names {sorted(gate_names)} differ from LibretroCore.biosAnyOf')
    for name in gate_names:
        rows = [entry['id'] for entry in gate_rows if name in entry['names']]
        if len(rows) != 1:
            findings.append(f'{name} is in {rows}, expected one PlayStation row')
    for entry in gate_rows:
        if entry['level'] != 'required' or not entry.get('psxChecksumScan'):
            findings.append(f"{entry['id']}: PlayStation rows are required and scanned by checksum")

    # 4. Texts and shipped bytes.
    keys = {key for console in requirements['consoles'].values() for key in console.get('noteKeys', [])}
    for entry in entries:
        keys.update(entry.get('noteKeys', []))
        if entry.get('condition'):
            keys.add(entry['condition']['key'])
        if entry['level'] == 'conditional' and not entry.get('condition'):
            findings.append(f"{entry['id']}: conditional without condition")
        for core in entry.get('binaryStrings', {}):
            if core not in entry['cores']:
                findings.append(f"{entry['id']}: binary strings for {core}, which does not read it")
    for key in sorted(keys - english):
        findings.append(f'LibretroLocale key {key} missing from the English map')

    def strings(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('data', 'bytes', 'content', 'base64'):
                    findings.append(f'field {key} could carry file bytes')
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, str):
            yield value
    for text in strings(requirements):
        if len(text) > 400:
            findings.append(f'unexpectedly long value: {text[:40]}...')
    return findings


def check_cores(requirements, artifact):
    """Findings of the pinned-binary contract for the artifact at [artifact]."""
    findings = []
    identity = read_json(artifact / 'identity.json')
    manifest = read_json(ROOT / 'build-utils/libretro/cores.json')
    if [core['id'] for core in identity['cores']] != [core['id'] for core in manifest['cores']]:
        findings.append('artifact cores differ from the manifest')
    binaries = {}

    def binary(core):
        if core not in binaries:
            path = artifact / 'Frameworks' / f'{core}_libretro.framework' / f'{core}_libretro'
            binaries[core] = path.read_bytes() if path.is_file() else None
            if binaries[core] is None:
                findings.append(f'{core}: binary missing at {path}')
        return binaries[core]

    checked = 0
    for entry in requirements['entries']:
        for core, names in entry.get('binaryStrings', {}).items():
            data = binary(core)
            if data is None:
                continue
            for name in names:
                checked += 1
                if name.encode() not in data:
                    findings.append(f"{entry['id']}: {core} binary does not contain {name!r}")
    if requirements['flags']['beetleOpenBiosFallback']:
        for core in ('mednafen_psx_hw', 'mednafen_psx'):
            data = binary(core)
            if data is not None and b'openbios\0' not in data:
                findings.append(f'{core}: no OpenBIOS in the pinned binary, but the data says discs fall back to it')
    files = identity.get('files', {})
    for entry in requirements['entries']:
        bundled = entry.get('bundledPath')
        if not bundled:
            continue
        path = artifact / 'LibretroSystem' / bundled
        recorded = files.get('LibretroSystem/' + bundled)
        if not path.is_file():
            findings.append(f'{bundled}: missing from LibretroSystem')
        elif recorded != hashlib.sha256(path.read_bytes()).hexdigest():
            findings.append(f'{bundled}: SHA-256 differs from identity.json')
    return findings, checked


def self_test_cores(requirements):
    """Runs check_cores on a synthetic artifact: complete, then with one
    string removed, so the CI-only path is exercised on every host."""
    manifest = read_json(ROOT / 'build-utils/libretro/cores.json')
    with tempfile.TemporaryDirectory() as directory:
        artifact = Path(directory)
        wanted = {}
        for entry in requirements['entries']:
            for core, names in entry.get('binaryStrings', {}).items():
                wanted.setdefault(core, set()).update(names)
        for core in ('mednafen_psx_hw', 'mednafen_psx'):
            wanted.setdefault(core, set()).add('openbios')
        for core in manifest['cores']:
            framework = artifact / 'Frameworks' / f"{core['id']}_libretro.framework"
            framework.mkdir(parents=True)
            body = b'\0'.join(name.encode() for name in sorted(wanted.get(core['id'], ()))) + b'\0'
            (framework / f"{core['id']}_libretro").write_bytes(b'\xcf\xfa\xed\xfe' + body)
        files = {}
        for entry in requirements['entries']:
            if entry.get('bundledPath'):
                path = artifact / 'LibretroSystem' / entry['bundledPath']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'synthetic ' + entry['id'].encode())
                files['LibretroSystem/' + entry['bundledPath']] = hashlib.sha256(path.read_bytes()).hexdigest()
        (artifact / 'identity.json').write_text(json.dumps({'cores': manifest['cores'], 'files': files}))
        findings, checked = check_cores(requirements, artifact)
        require(not findings and checked > 40, f'--cores self-test on a complete artifact: {findings} ({checked})')
        target = artifact / 'Frameworks/picodrive_libretro.framework/picodrive_libretro'
        target.write_bytes(target.read_bytes().replace(b'us_scd2_9306', b'xx_xxxx_xxxx'))
        mednafen = artifact / 'Frameworks/mednafen_psx_libretro.framework/mednafen_psx_libretro'
        mednafen.write_bytes(mednafen.read_bytes().replace(b'openbios\0', b'xxxxxxxx\0'))
        findings, _ = check_cores(requirements, artifact)
        require(any('us_scd2_9306' in finding for finding in findings) and any('OpenBIOS' in finding for finding in findings),
                f'--cores self-test missed a removed string: {findings}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cores', type=Path, help='LibretroCores artifact directory (Frameworks/, LibretroSystem/, identity.json)')
    args = parser.parse_args()
    requirements = read_json(REQUIREMENTS)
    fixture = read_json(FIXTURE)
    findings = check_data(requirements, fixture)
    require(not findings, '\n  ' + '\n  '.join(findings))
    self_test_cores(requirements)
    entries = len(requirements['entries'])
    firmware = sum(len(core['firmware']) for core in fixture['coreInfo']['cores'].values())
    if args.cores is None:
        print(f'BIOS requirements: {entries} entries cover the {firmware} firmware lines of core-info '
              f'{CORE_INFO_COMMIT[:8]} ({len(requirements.get("excluded", []))} excluded with a reason); '
              'pinned-binary contract needs --cores')
        return
    findings, checked = check_cores(requirements, args.cores)
    require(not findings, '\n  ' + '\n  '.join(findings))
    print(f'BIOS requirements match the pinned cores: {checked} names found in their binaries, '
          f'OpenBIOS fallback {"confirmed" if requirements["flags"]["beetleOpenBiosFallback"] else "not claimed"}, '
          'bundled PPSSPP files identical to identity.json')


if __name__ == '__main__':
    main()
