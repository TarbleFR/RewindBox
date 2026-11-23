#!/usr/bin/env python3
"""Derives the dedicated libretro JIT helper from RewindBox's RPCS3 helper.

The RPCS3 helper is the reference implementation of the integrated JIT path the
S2Arm helper was copied from (packages/s2arm_jit_helper/copy-of-rpcs3.json):
RemotePairing over manual LocalDevVPN, StikJIT attached to the RewindBox PID by an
app extension, the generic universal script (commands 0 detach, 1 prepare region,
2 extra script, 3 nonce probe) and the host-side nonce probe. Only identity strings
differ. The libretro host drives the commands itself from
packages/libretro_internal_bridge/ios/Classes/LibretroJitArena.m before any core
code runs; it asks for the universal handshake by OS version (iOS 26.0 and later).

    python3 tools/libretro/derive_jit_helper.py           # writes the files and the record
    python3 tools/libretro/derive_jit_helper.py --check   # fails on any drift

Dedicated identities: bundle suffix `.libretrojithelper`, target `LibretroJITHelper`,
marker `NeoStationLibretroJITHelper`, principal class `LibretroJITRequestHandler`,
request type `com.neogamelab.neostation.libretro-jit-request`, script
`libretro-universal.js`, library folder `NeoStationLibretroStikJIT`, attach marker
`NEOSTATION_LIBRETRO_DEBUGGER_ATTACHED_V1`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / 'packages/libretro_jit_helper/copy-of-rpcs3.json'

RPCS3_COMMENT = (
    "      // RPCS3 selects its mirrored Universal arena by OS version, not TXM\n"
    "      // detection. Even a non-TXM device on iOS 26 needs this script running\n"
    "      // when Core constructors request their executable regions.\n")
LIBRETRO_COMMENT = (
    "      // The libretro host asks for the universal handshake by OS version\n"
    "      // (iOS 26.0 and later), not TXM detection, and issues the commands\n"
    "      // itself while it prepares the session's code arena.\n")

# output: (source, [(old, new, occurrences in the text at that step), ...]) applied in order.
FILES = {
    'packages/libretro_jit_helper/ios/Classes/LibretroJITRequestHandlerBase.swift': (
        'packages/rpcs3_jit_helper/ios/Classes/Rpcs3JITRequestHandlerBase.swift', [
            ['rpcs3RequestType', 'libretroRequestType', 3],
            ['com.neogamelab.neostation.rpcs3-jit-request', 'com.neogamelab.neostation.libretro-jit-request', 1],
            ['com.neogamelab.neostation.rpcs3.jit-helper', 'com.neogamelab.neostation.libretro.jit-helper', 2],
            ['Rpcs3JITRequestHandlerBase', 'LibretroJITRequestHandlerBase', 2],
            ['Rpcs3HelperReporter', 'LibretroHelperReporter', 3],
            ['Rpcs3HelperError', 'LibretroHelperError', 11],
            ['NeoStationRPCS3StikJIT', 'NeoStationLibretroStikJIT', 1],
            ['NeoStationRPCS3JIT', 'NeoStationLibretroJIT', 1],
            ['rpcs3-universal', 'libretro-universal', 2],
            ['NEOSTATION_DEBUGGER_ATTACHED_V1', 'NEOSTATION_LIBRETRO_DEBUGGER_ATTACHED_V1', 1],
            [RPCS3_COMMENT, LIBRETRO_COMMENT, 1],
            ['embedded RPCS3 engine', 'embedded libretro cores', 1],
            ['RPCS3', 'libretro', 8],
        ]),
    'packages/libretro_jit_helper/ios/Classes/LibretroHelperJournal.swift': (
        'packages/rpcs3_jit_helper/ios/Classes/Rpcs3HelperJournal.swift', [
            ['Rpcs3HelperJournal', 'LibretroHelperJournal', 1],
            ['NEOSTATION_RPCS3_PREPARE_', 'NEOSTATION_LIBRETRO_PREPARE_', 1],
            ['NEOSTATION_DEBUGGER_', 'NEOSTATION_LIBRETRO_DEBUGGER_', 1],
            ['RPCS3_', 'LIBRETRO_', 2],
        ]),
    'packages/libretro_jit_helper/ios/Resources/libretro-universal.js': (
        'packages/rpcs3_jit_helper/ios/Resources/rpcs3-universal.js', [
            ['NEOSTATION_STIKJIT_UNIVERSAL_V1', 'NEOSTATION_LIBRETRO_STIKJIT_UNIVERSAL_V1', 3],
            ['NEOSTATION_DEBUGGER_ATTACHED_V1', 'NEOSTATION_LIBRETRO_DEBUGGER_ATTACHED_V1', 1],
            ['NEOSTATION_DEBUGGER_PROBE_V1', 'NEOSTATION_LIBRETRO_DEBUGGER_PROBE_V1', 1],
        ]),
    'packages/libretro_jit_helper/ios/libretro_jit_helper.podspec': (
        'packages/rpcs3_jit_helper/ios/rpcs3_jit_helper.podspec', [
            ['rpcs3_jit_helper', 'libretro_jit_helper', 2],
            ['helper for RewindBox RPCS3.', 'helper for RewindBox libretro cores.', 1],
            ['embedded PlayStation 3\nengine.', 'embedded libretro\ncores.', 1],
        ]),
    'packages/libretro_jit_helper/extension/LibretroJITExtensionEntry.swift': (
        'native/rpcs3_internal_helper/Rpcs3JITExtensionEntry.swift', [
            ['import rpcs3_jit_helper', 'import libretro_jit_helper', 1],
            ['Rpcs3JITRequestHandler', 'LibretroJITRequestHandler', 3],
        ]),
    'packages/libretro_jit_helper/extension/Info.plist': (
        'native/rpcs3_internal_helper/Info.plist', [
            ['RewindBox RPCS3 JIT Helper', 'RewindBox Libretro JIT Helper', 1],
            ['NeoStationRPCS3JITHelper', 'NeoStationLibretroJITHelper', 1],
            ['Rpcs3JITRequestHandler', 'LibretroJITRequestHandler', 1],
        ]),
    'packages/libretro_jit_helper/LICENSE': (
        'packages/rpcs3_jit_helper/LICENSE', [
            ['rpcs3_jit_helper', 'libretro_jit_helper', 1],
        ]),
}


def derive(source_text: str, replacements) -> str:
    text = source_text
    for old, new, count in replacements:
        found = text.count(old)
        if found != count:
            raise SystemExit(f'expected {count} occurrence(s) of {old[:60]!r}, found {found}')
        text = text.replace(old, new)
    return text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='fail if a written file differs from its derivation')
    args = parser.parse_args(argv)
    record = {
        'schema': 1,
        'purpose': ('Every file of this package is the RPCS3 JIT helper file named here with exactly these '
                    'replacements, applied in order (old text, new text, occurrences of the old text at that step), '
                    'written by tools/libretro/derive_jit_helper.py. The debugger protocol (BRK #0xf00d commands '
                    '0 detach, 1 prepare region, 2 new breakpoints, 3 probe with nonce+1), the request fields and the '
                    'reporter events are not renamed.'),
        'files': {},
    }
    drift = []
    for output, (source, replacements) in FILES.items():
        source_bytes = (ROOT / source).read_bytes()
        text = derive(source_bytes.decode('utf-8'), replacements)
        record['files'][output] = {
            'source': source,
            'sourceSha256': hashlib.sha256(source_bytes).hexdigest(),
            'replacements': replacements,
        }
        target = ROOT / output
        if args.check:
            if not target.is_file() or target.read_text(encoding='utf-8') != text:
                drift.append(output)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
    record_text = json.dumps(record, indent=2, ensure_ascii=False) + '\n'
    if args.check:
        if not RECORD.is_file() or RECORD.read_text(encoding='utf-8') != record_text:
            drift.append(str(RECORD.relative_to(ROOT)))
        if drift:
            print('libretro JIT helper drift: ' + ', '.join(drift), file=sys.stderr)
            return 1
        print('libretro JIT helper matches its RPCS3 sources')
        return 0
    RECORD.write_text(record_text, encoding='utf-8')
    print('wrote ' + ', '.join(list(FILES) + [str(RECORD.relative_to(ROOT))]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
