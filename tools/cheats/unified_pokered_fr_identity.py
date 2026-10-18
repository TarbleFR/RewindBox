#!/usr/bin/env python3
"""Verify French Red/Blue cheat addresses from pinned text declarations.

This performs byte accounting of WRAM declarations, loops, unions and RAM
structure macros. It is not an assembler and produces no ROM or machine code.
By default all exact source text is in the regression fixture. --source-root
can additionally compare it to an independently downloaded source checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'test/fixtures/unified_cheats/pokered-fr-memory.json'
PIN = '7ddc547e22e4c84f3e492a3c04a92c26f7f2e877'


def evaluate(expression: str, constants: dict[str, int], variables=None) -> int:
    expression = re.sub(r'\$([a-fA-F0-9]+)', lambda match: str(int(match[1], 16)), expression.strip())
    expression = re.sub(r'\btiles\b', '* 16', expression)
    for name, value in (constants | (variables or {})).items():
        expression = re.sub(r'\b' + re.escape(name) + r'\b', str(value), expression)
    if not re.fullmatch(r'[0-9\s+*/()\-]+', expression):
        raise ValueError(f'Unresolved RAM-size expression: {expression}')
    # Only the arithmetic grammar above is accepted, with no identifiers/calls.
    return int(eval(expression, {'__builtins__': {}}))


def macro_lengths(source: str, constants: dict[str, int]) -> dict[str, int]:
    definitions = {}
    current = None
    for original in source.splitlines():
        line = original.split(';')[0].strip()
        found = re.fullmatch(r'MACRO\??\s+(\w+)', line)
        if found:
            current = found[1]
            definitions[current] = []
        elif line == 'ENDM':
            current = None
        elif current and line:
            definitions[current].append(line.split('::')[-1].strip())
    lengths = {}

    def length(name, visiting):
        if name in lengths:
            return lengths[name]
        if name in visiting:
            raise ValueError('Recursive RAM macro')
        total = 0
        for line in definitions[name]:
            if not line:
                continue
            op, _, argument = line.partition(' ')
            if op == 'db':
                total += 1
            elif op == 'dw':
                total += 2
            elif op == 'ds':
                total += evaluate(argument, constants)
            elif op in definitions:
                total += length(op, visiting | {name})
            else:
                raise ValueError(f'Unknown RAM macro operation: {line}')
        lengths[name] = total
        return total

    for name in definitions:
        if name != 'flag_array':
            length(name, set())
    return lengths


def addresses(source: str, layout: str, macros: dict[str, int], constants: dict[str, int]):
    origins = {}
    in_wram = False
    pending_origin = 0xC000
    for original in layout.splitlines():
        line = original.split(';')[0].strip()
        if line == 'WRAM0':
            in_wram = True
            continue
        if not in_wram:
            continue
        if line.startswith('org '):
            pending_origin = evaluate(line[4:], constants)
        elif line.startswith('"'):
            section = line.strip('"')
            if pending_origin is not None:
                origins[section] = pending_origin
            pending_origin = None
        elif line and line == line.upper():
            break
    lines = [line.split(';')[0].strip() for line in source.splitlines()]
    stop = next(index for index, line in enumerate(lines) if line.startswith('wWalkBikeSurfState::'))
    lines = lines[:stop + 1]
    labels, sections, unions = {}, [], []
    position = 0xC000

    def process(block, variables=None):
        nonlocal position
        variables = variables or {}
        index = 0
        while index < len(block):
            line = block[index]
            index += 1
            if not line:
                continue
            if line.startswith('FOR '):
                pieces = line[4:].split(',')
                variable = pieces[0].strip()
                bounds = [evaluate(value, constants, variables) for value in pieces[1:]]
                start, end = (0, bounds[0]) if len(bounds) == 1 else bounds
                body, nesting = [], 1
                while nesting:
                    nested = block[index]
                    index += 1
                    if nested.startswith('FOR '):
                        nesting += 1
                    if nested == 'ENDR':
                        nesting -= 1
                    if nesting:
                        body.append(nested)
                for value in range(start, end):
                    process(body, variables | {variable: value})
                continue
            if line.startswith('SECTION '):
                section = line.split('"')[1]
                position = origins.get(section, position)
                sections.append({'section': section, 'start': f'{position:04X}'})
                continue
            if line.startswith('ASSERT ') or line == 'ENDSECTION':
                continue
            if line == 'UNION':
                unions.append([position, position])
                continue
            if line == 'NEXTU':
                unions[-1][1] = max(unions[-1][1], position)
                position = unions[-1][0]
                continue
            if line == 'ENDU':
                _, maximum = unions.pop()
                position = max(position, maximum)
                continue
            if '::' in line:
                label, line = line.split('::', 1)
                label = re.sub(r'\{(?:02d|d):n\}', lambda match:
                               f'{variables["n"]:02}' if '02' in match[0] else str(variables['n']), label)
                labels[label] = position
                line = line.strip()
            if not line:
                continue
            op, _, argument = line.partition(' ')
            if op == 'db':
                position += 1
            elif op == 'dw':
                position += 2
            elif op == 'ds':
                position += evaluate(argument, constants, variables)
            elif op == 'flag_array':
                position += (evaluate(argument, constants, variables) + 7) // 8
            elif op in macros:
                position += macros[op]
            else:
                raise ValueError(f'Unknown WRAM operation: {line}')
    process(lines)
    if unions:
        raise ValueError('Unclosed WRAM union')
    return labels, sections


def decode_gameshark(code):
    if not re.fullmatch(r'01[0-9a-fA-F]{6}', code):
        raise ValueError('Expected a Game Boy 01VVLLHH byte write')
    return int(code[6:8] + code[4:6], 16), int(code[2:4], 16)


def verify(fixture_path=FIXTURE, source_root: Path | None = None):
    fixture = json.loads(Path(fixture_path).read_text())
    if fixture['commit'] != PIN:
        raise ValueError('French source revision changed without review')
    source = {}
    for name, record in fixture['source_files'].items():
        data = record['text'].encode()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError(f'Embedded source hash mismatch: {name}')
        if source_root and hashlib.sha256((source_root / name).read_bytes()).hexdigest() != record['sha256']:
            raise ValueError(f'Independent source hash mismatch: {name}')
        source[name] = record['text']
    for sha1 in fixture['rom_sha1'].values():
        if f'sha1: {sha1}' not in source['README.md']:
            raise ValueError('Target fingerprint not declared by the pinned author README')
    lengths = macro_lengths(source['macros/ram.asm'], fixture['constants'])
    if lengths['party_struct'] != fixture['constants']['PARTYMON_STRUCT_LENGTH']:
        raise ValueError('Party structure and constant disagree')
    symbols, sections = addresses(source['ram/wram.asm'], source['layout.link'], lengths, fixture['constants'])
    for symbol, expected in fixture['expected_addresses'].items():
        if symbols[symbol] != int(expected, 16):
            raise ValueError(f'Address mismatch for {symbol}: {symbols[symbol]:04X} != {expected}')
    programs = fixture['programs'] + [fixture['derived_program']]
    for program in programs:
        code = program.get('original_code', program.get('code'))
        writes = [decode_gameshark(line) for line in code.splitlines()]
        expected = [(symbols[program['symbol']] + offset, value)
                    for offset, value in zip(program['offsets'], program['values'], strict=True)]
        if writes != expected:
            raise ValueError(f'Program differs from its documented RAM field: {program["name"]}')
    return {'schema_version': 1, 'commit': PIN, 'method': fixture['method'],
            'rom_sha1': fixture['rom_sha1'], 'addresses': fixture['expected_addresses'],
            'verified_original_programs': len(fixture['programs']), 'verified_derived_programs': 1,
            'macro_sizes': lengths, 'sections': sections, 'gameplay_tested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--fixture', type=Path, default=FIXTURE)
    args = parser.parse_args()
    print(json.dumps(verify(args.fixture, args.source_root), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
