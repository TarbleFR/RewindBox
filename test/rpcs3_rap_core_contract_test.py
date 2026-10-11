#!/usr/bin/env python3
"""Provenance guard for the RAP licence import (Build 438).

NeoStation installs RAP licences from Dart, without the Core, at
<support>/NeoStation/RPCS3/Data/dev_hdd0/home/00000001/exdata/<CONTENT_ID>.rap.
That path is only right for the pinned Core, where (XITRIX/rpcs3 22f1152):

- rpcs3/Emu/system_utils.cpp get_rap_file_path scans every user of
  get_hdd0_dir() + "home" and opens <user>/exdata/<content_id>.rap;
- get_hdd0_dir() is $(EmulatorDir)dev_hdd0/ (vfs_config.h) and the emulator
  directory is the config directory, i.e. the support path the bridge passes;
- rpcs3/ios/RPCS3IOS.cpp always calls Emu.SetUsr("00000001").

The NeoStation patch must not touch any of these. A Core rebase (new upstream
commit) must re-check them in the new sources, then update this guard and
docs/rpcs3-rap-import-build438.md.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPOSITORY = 'XITRIX/rpcs3'
UPSTREAM_COMMIT = '22f1152783cef1f7e04af7b1c895173e28fd5b03'

# Symbols and paths of the RAP lookup, the user selection and the VFS root.
RAP_LOOKUP_TERMS = (
    'get_rap_file_path',
    'GetKeyFromRap',
    'rap_to_rif',
    'npDrmIsAvailable',
    'SetUsr',
    'GetUsr',
    'm_usr',
    'check_user',
    'is_valid_content_id',
    'exdata',
    'get_hdd0_dir',
    'get_emu_dir',
    'dev_hdd0',
    'vfs_config',
    'cfg_vfs',
    'g_cfg_vfs',
    'g_ios_config_dir',
    '.rap"',
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('RAP contract: ' + message)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def check_pinned_core() -> None:
    source = json.loads(read('build-utils/rpcs3/canonical-source.json'))
    require(
        source.get('upstream_repository') == UPSTREAM_REPOSITORY
        and source.get('upstream_commit') == UPSTREAM_COMMIT,
        'the RPCS3 Core was rebased; re-check get_rap_file_path, '
        'Emu.SetUsr and the dev_hdd0 VFS root in the new sources before '
        'updating this guard',
    )


def changed_patch_lines() -> list[tuple[str, str]]:
    patch = read('build-utils/rpcs3/embedded-core.patch')
    current = ''
    lines: list[tuple[str, str]] = []
    for line in patch.splitlines():
        if line.startswith('+++ '):
            current = line[4:].strip()
            continue
        if line.startswith('--- '):
            continue
        if line.startswith(('+', '-')):
            lines.append((current, line))
    require(lines, 'embedded-core.patch has no changed lines')
    return lines


def check_patch_leaves_lookup_alone() -> None:
    offenders = [
        f'{name}: {line.strip()[:120]}'
        for name, line in changed_patch_lines()
        for term in RAP_LOOKUP_TERMS
        if term in line
    ]
    require(
        not offenders,
        'embedded-core.patch now changes the RAP lookup, the user or the '
        'VFS root:\n' + '\n'.join(offenders),
    )
    config_dir = [
        line
        for _, line in changed_patch_lines()
        if line.startswith('+') and 'set_config_dir(' in line
    ]
    require(config_dir, 'the patch no longer sets the iOS config directory')
    for line in config_dir:
        require(
            'application_support_path' in line,
            'the iOS config directory is no longer the support path: ' + line,
        )


def check_support_path() -> None:
    service = read('lib/services/rpcs3_internal_service.dart')
    require(
        re.search(
            r"Directory\(path\.join\(support\.path, 'NeoStation', 'RPCS3'\)\)",
            service,
        )
        is not None,
        'rootDirectory is no longer <support>/NeoStation/RPCS3',
    )
    require(
        re.search(
            r"dataDirectory\(\) async \{\s*final root = await rootDirectory\(\);"
            r"\s*final directory = Directory\(path\.join\(root\.path, 'Data'\)\);",
            service,
        )
        is not None,
        'dataDirectory is no longer <root>/Data',
    )
    initialize = service.index('Rpcs3InternalBridge.initialize(')
    require(
        'supportPath: data.path' in service[initialize:initialize + 200]
        and 'final data = await dataDirectory();' in service[:initialize],
        'the Core no longer receives dataDirectory() as its support path',
    )


def check_dart_installer() -> None:
    licence = read('lib/services/rpcs3_rap_licence_service.dart')
    for expected in (
        "static const String activeUserId = '00000001';",
        'static const int rapByteLength = 16;',
        "static const String extension = '.rap';",
        "p.join(dataRoot, 'dev_hdd0', 'home', activeUserId, 'exdata')",
        "File(p.join(dataRoot, 'vfs.yml'))",
    ):
        require(expected in licence, 'RAP installer constant changed: ' + expected)
    # Installing a licence never prepares the Core, JIT or library.
    for forbidden in (
        'ensureManagementInitialized',
        'ensureInitialized',
        'ensureGameplayInitialized',
        'prepareJit',
        'Rpcs3LibraryService',
        'syncInternalLibrary',
        'installRap',
        'rpcs3_ios_install_rap',
    ):
        require(forbidden not in licence, 'RAP installer must not call ' + forbidden)


def check_documentation() -> None:
    doc = read('docs/rpcs3-rap-import-build438.md')
    for expected in (UPSTREAM_COMMIT[:7], 'get_rap_file_path', 'SetUsr', '00000001'):
        require(expected in doc, 'docs/rpcs3-rap-import-build438.md lacks ' + expected)


def main() -> None:
    check_pinned_core()
    check_patch_leaves_lookup_alone()
    check_support_path()
    check_dart_installer()
    check_documentation()
    print('RPCS3 RAP licence contract: OK')


if __name__ == '__main__':
    main()
