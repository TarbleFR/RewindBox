#!/usr/bin/env python3
"""Read-only, proof-gated Artemis NCL -> authored RPCS3 YAML crosswalk.

This tool never synthesizes a PPU hash or a new patch from a game title. Its
output links an exact NCL block to an existing author-ported native document.
Pointer, conditional, scan and continuous-write programs are not translated.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

NCL_PIN = 'd79b41e525e20251bd0d919100039ac0a6433956'
SERIAL = re.compile(r'\b[BN][A-Z]{3}\d{5}\b')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def name_key(value):
    return ' '.join(value.casefold().split())


def source_editions(path):
    """Keep explicit APP_VER or the bare serial/version convention only.

    A filename's v01.00 can be disc VERSION rather than APP_VER. When av01.01
    is present it is authoritative; v-only editions remain ambiguous here.
    """
    stem = PurePosixPath(path).stem
    occurrences = list(SERIAL.finditer(stem))
    result = []
    for index, item in enumerate(occurrences):
        end = occurrences[index + 1].start() if index + 1 < len(occurrences) else len(stem)
        suffix = stem[item.end():end]
        explicit = re.findall(r'(?i)\bav(\d{2}\.\d{2})\b', suffix)
        bare = re.match(r'\s+(\d{2}\.\d{2})\b', suffix)
        if len(explicit) == 1:
            result.append((item[0], explicit[0], 'explicit-app-ver'))
        elif not explicit and bare and len(re.findall(r'\d{2}\.\d{2}', suffix)) == 1:
            result.append((item[0], bare[1], 'bare-serial-version'))
    return result


def native_writes(rows):
    """Return full ordered static be32 writes; flatten load only at offset zero."""
    if not isinstance(rows, list) or not rows or len(rows) > 8192:
        return None
    result = []
    for row in rows:
        if not isinstance(row, list) or not row:
            return None
        if row[0] == 'load' and len(row) in (2, 3) and (len(row) == 2 or row[2] in (0, '0', '0x0')):
            nested = native_writes(row[1])
            if nested is None:
                return None
            result.extend(nested)
        elif len(row) == 3 and row[0] == 'be32':
            pair = []
            for operand in row[1:]:
                if isinstance(operand, bool):
                    return None
                if isinstance(operand, int):
                    value = operand
                elif isinstance(operand, str) and re.fullmatch(r'0x[0-9a-fA-F]{1,8}', operand):
                    value = int(operand, 16)
                else:
                    return None
                if not 0 <= value <= 0xFFFFFFFF:
                    return None
                pair.append(value)
            result.append(tuple(pair))
        else:
            return None
        if len(result) > 8192:
            return None
    return tuple(result)


def authored_index(games):
    result = {}
    for game in games:
        version = game.get('revision', '')
        if not re.fullmatch(r'\d{2}\.\d{2}', version):
            continue
        serials = [row['value'] for row in game.get('identities', [])
                   if row.get('type') == 'serial' and row.get('scheme') == 'ps3-title-id'
                   and re.fullmatch(r'[BN][A-Z]{3}\d{5}', row.get('value', ''))]
        hashes = [row['value'] for row in game.get('identities', [])
                  if row.get('type') == 'ppu_hash' and row.get('scheme') == 'rpcs3-ppu-hash'
                  and re.fullmatch(r'[a-fA-F0-9]{40}', row.get('value', ''))]
        for program in game.get('cheats', []):
            document = program.get('native_document', {})
            for ppu in hashes:
                for label, patch in document.get('PPU-' + ppu, {}).items():
                    writes = native_writes(patch.get('Patch'))
                    if writes is None or patch.get('Configurable Values') or program.get('parameters'):
                        continue
                    for serial in serials:
                        # Cross-check the native document's Games constraints,
                        # rather than trusting only the surrounding metadata.
                        if not any(version in editions.get(serial, [])
                                   for editions in patch.get('Games', {}).values()):
                            continue
                        key = (serial, version, name_key(program.get('source_name', label)), writes)
                        result.setdefault(key, []).append({
                            'ppu_hash': ppu, 'serial': serial, 'app_version': version,
                            'native_name': label, 'native_document_sha256': digest(document),
                            'native_document': document,
                        })
    return result


def crosswalk(data, path, index):
    editions = source_editions(path)
    matches, counts = [], {'blocks': 0, 'missing_exact_edition': 0,
                           'unsupported_mode_or_body': 0, 'no_authored_equivalent': 0}
    try:
        raw = data.decode('utf-8-sig', errors='strict')
        encoding = 'utf-8-sig'
    except UnicodeDecodeError:
        # The original database includes Windows-1252 apostrophes. Decode
        # explicitly without replacing bytes or modifying instruction tokens.
        raw = data.decode('cp1252', errors='strict')
        encoding = 'cp1252'
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    for block in raw.split('#'):
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        counts['blocks'] += 1
        if not editions:
            counts['missing_exact_edition'] += 1
            continue
        if len(lines) < 4 or lines[1] != '0':
            counts['unsupported_mode_or_body'] += 1
            continue
        instructions = [re.fullmatch(r'0 ([0-9a-fA-F]{8}) ([0-9a-fA-F]{8})', row)
                        for row in lines[3:]]
        if not instructions or not all(instructions):
            counts['unsupported_mode_or_body'] += 1
            continue
        writes = tuple((int(row[1], 16), int(row[2], 16)) for row in instructions)
        targets = []
        for serial, version, evidence in editions:
            for target in index.get((serial, version, name_key(lines[0]), writes), []):
                targets.append({**target, 'edition_evidence': evidence})
        if not targets:
            counts['no_authored_equivalent'] += 1
            continue
        matches.append({'path': path, 'source_revision': NCL_PIN, 'source_encoding': encoding,
                        'source_file_sha256': hashlib.sha256(data).hexdigest(), 'source_name': lines[0],
                        'source_author': lines[2], 'source_mode': '0',
                        'source_block': block.strip(), 'ordered_be32_writes': writes,
                        'targets': targets})
    return matches, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ncl_archive', type=Path)
    parser.add_argument('authored_games_json', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    authored = json.loads(args.authored_games_json.read_text())
    index = authored_index(authored['games'] if isinstance(authored, dict) else authored)
    matches, totals = [], {}
    with tarfile.open(args.ncl_archive) as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith('.ncl'):
                continue
            if not member.name.startswith('ArtemisPS3-' + NCL_PIN + '/'):
                raise ValueError('NCL archive does not declare the pinned source revision')
            if member.size > 4 * 1024 * 1024:
                raise ValueError('NCL source member exceeds the bounded audit input')
            found, counts = crosswalk(archive.extractfile(member).read(), member.name, index)
            matches.extend(found)
            for key, count in counts.items():
                totals[key] = totals.get(key, 0) + count
    unique = {target['native_document_sha256'] for match in matches for target in match['targets']}
    report = {'schema_version': 1, 'kind': 'authored-native-crosswalk',
              'ncl_revision': NCL_PIN,
              'ncl_archive_sha256': hashlib.sha256(args.ncl_archive.read_bytes()).hexdigest(),
              'authored_input_sha256': hashlib.sha256(args.authored_games_json.read_bytes()).hexdigest(),
              'matches': matches,
              'metrics': {**totals, 'matched_source_blocks': len(matches),
                          'existing_native_documents': len(unique), 'new_unique_programs': 0}}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['metrics'], sort_keys=True))


if __name__ == '__main__':
    main()
