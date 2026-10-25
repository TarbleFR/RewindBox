#!/usr/bin/env python3
"""Twelve-language labels of the HD textures pages.

1. tools/textures/labels.py --check: generated files current, the twelve
   NeoStation languages complete, placeholders identical to English,
   Traditional Chinese distinct from Simplified Chinese.
2. Every label key the native code can show exists: literal keys of the page,
   every error key the store and the engine adapters produce (error.<key>),
   every identity problem of the identity reader (identity.<key>) and every
   activation reason (activation.<key>).
3. The Flutter rows use only keys of the generated Dart catalogue.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / 'packages/neo_texture_catalog/ios/Classes'


def fail(message):
    print('FAIL', message)
    raise SystemExit(1)


def main():
    result = subprocess.run([sys.executable, str(ROOT / 'tools/textures/labels.py'), '--check'], capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode:
        fail(result.stdout + result.stderr)
    labels = json.loads((ROOT / 'packages/neo_texture_catalog/ios/Resources/labels.json').read_text(encoding='utf-8'))
    english = set(labels['en'])
    checks = 0

    page = (CLASSES / 'NeoTextureHDPage.m').read_text(encoding='utf-8')
    literal = set(re.findall(r'\bText\(@"([A-Za-z0-9_.]+)"', page))
    # The argument of each " t:" message (up to its closing bracket or " with:"),
    # nested message sends removed: the keys a ternary chooses between.
    for match in re.finditer(r'\bt:', page):
        depth, i, argument = 0, match.end(), ''
        while i < len(page):
            c = page[i]
            if c == '[':
                depth += 1
            elif c == ']':
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                argument += c
            i += 1
        argument = argument.split(' with:')[0]
        literal |= {key for key in re.findall(r'@"([A-Za-z][A-Za-z0-9_.]*)"', argument) if not key.endswith('.')}
    missing = sorted(key for key in literal if key not in english)
    if missing:
        fail(f'page keys missing from labels: {missing}')
    checks += len(literal)

    # error.<key> for every key a PackError, an engine error or a delegated installer maps to.
    sources = ''.join(path.read_text(encoding='utf-8') for path in CLASSES.glob('*.m*'))
    errors = set(re.findall(r'PackError\([^,]+,\s*@"([A-Za-z]+)"', sources))
    errors |= set(re.findall(r'EngineError\(@"([A-Za-z]+)"\)', sources))
    store = (CLASSES / 'NeoTexturePackStore.mm').read_text(encoding='utf-8')
    mapping = re.search(r'map = @\{(.*?)\};', store, re.S).group(1)
    errors |= set(re.findall(r':\s*@"([A-Za-z]+)"', mapping))
    errors |= {'failed', 'catalogueUnavailable'}
    missing = sorted(key for key in errors if f'error.{key}' not in english)
    if missing:
        fail(f'error keys missing from labels: {missing}')
    checks += len(errors)

    identity = (CLASSES / 'NeoTextureIdentity.h').read_text(encoding='utf-8')
    problems = set(re.findall(r'r\.problem = "([A-Za-z]+)"', identity)) | {'unknown'}
    missing = sorted(key for key in problems if f'identity.{key}' not in english)
    if missing:
        fail(f'identity problems missing from labels: {missing}')
    checks += len(problems)

    engines = (CLASSES / 'NeoTextureEngines.mm').read_text(encoding='utf-8')
    reasons = set(re.findall(r'@"reason":\s*(?:[^@]*\?\s*)?@"([A-Za-z]+)"', engines))
    reasons |= set(re.findall(r'\?\s*@"(engineUnavailable)"', engines))
    missing = sorted(key for key in reasons if f'activation.{key}' not in english)
    if not reasons or missing:
        fail(f'activation reasons missing from labels: {missing or "none found"}')
    checks += len(reasons)

    for engine in ('dolphin', 'armsx2', 'ppsspp', 'azahar'):
        if f'importHelp.{engine}' not in english:
            fail(f'importHelp.{engine} missing')
    for reason in ('otherSerial', 'noSerial', 'region', 'crc', 'uncertain'):
        if f'reason.{reason}' not in english:
            fail(f'reason.{reason} missing')
    checks += 9

    dart_keys = set(re.findall(r"'([A-Za-z]+)': ", (ROOT / 'lib/l10n/texture_catalog_locale.dart').read_text(encoding='utf-8')))
    used = set()
    for path in (ROOT / 'lib').rglob('*.dart'):
        used |= set(re.findall(r"TextureCatalogLocale\.text\([^,]+,\s*'([A-Za-z]+)'\)", path.read_text(encoding='utf-8')))
    missing = sorted(used - dart_keys)
    if missing:
        fail(f'Flutter rows use unknown keys: {missing}')
    checks += len(used)
    print(f'PASS texture label coverage: {checks} key checks')


if __name__ == '__main__':
    main()
