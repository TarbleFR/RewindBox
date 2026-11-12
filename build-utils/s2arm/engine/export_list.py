#!/usr/bin/env python3
"""Exported symbol list of S2ArmEngine.framework (RewindBox guest link, guest.mk).

S2ArmEngine is loaded RTLD_NOW | RTLD_GLOBAL in RewindBox's process. Unrestricted, it exports about 5,300 symbols,
third-party C and C++ libraries among them (glslang, SPIRV-Cross, libvpx, opus, dav1d...). DolphinCore carries its own
glslang with weak definitions: exported weak definitions are coalesced by dyld across images, so a Switch 2 session
after a GameCube/Wii one (or the reverse) would run one engine's glslang code with the other's. Only what the process
looks up by name stays exported:

  - the guest entry points RewindBox's host bridge looks up with dlsym on the engine handle (GUEST_ENTRY_POINTS);
  - every exported symbol whose name appears in the unrestricted binary as a string: the engine looks up its own
    functions by name, from C and Objective-C (dlsym(RTLD_DEFAULT, "name"), NUL-terminated UTF-8 strings) and from
    C# (NativeLibrary.TryGetExport(NativeLibrary.GetMainProgramHandle(), "name"), UTF-16LE strings of NativeAOT's
    frozen string literals; GetMainProgramHandle is dlopen(NULL), which dyld answers with RTLD_DEFAULT).

A name the engine builds at run time is not found this way. The pinned tree has two such lookups, both outside a
release session: hud.c picks between two literal names (both strings, so both kept), nvn_mtl.m's DM_NVN_UB
measurement takes a variable name from the environment (its comment says release iOS builds cannot resolve those).

    export_list.py BINARY NM_OUTPUT LIST REPORT

BINARY is the unrestricted link, NM_OUTPUT its `nm -gU` output; LIST is written for -Wl,-exported_symbols_list (one
symbol per line, sorted), REPORT as JSON. Refused (exit 1): a guest entry point that the unrestricted link does not
export, and a kept symbol that names glslang.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GUEST_ENTRY_POINTS = ('s2a_rb_guest_configure', 's2a_rb_guest_make_view_controller', 's2a_rb_guest_start',
                      's2a_rb_guest_stop', 's2a_rb_guest_fatal',
                      # patch 0010: the host resumes the game Quit parked (S2ArmEngineBridgePlugin.m resumeParkedGame)
                      's2a_rb_guest_parked', 's2a_rb_guest_view_controller', 's2a_rb_guest_resume')
IDENTIFIER = re.compile(rb'[A-Za-z_][A-Za-z0-9_$.]{1,255}')
UTF16_IDENTIFIER = re.compile(rb'(?:[A-Za-z_]\x00)(?:[A-Za-z0-9_$.]\x00){1,255}')
REFUSED_IN_KEPT = re.compile(r'glslang', re.IGNORECASE)


def exported_names(nm_output: str) -> set[str]:
    """Defined external symbols of `nm -gU` lines (`<address> <type> <name>`)."""
    names = set()
    for line in nm_output.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            names.add(parts[2])
    return names


def binary_strings(data: bytes) -> set[str]:
    """Identifier-like NUL-terminated UTF-8 strings and UTF-16LE runs of the binary, exactly as stored."""
    found = set()
    for token in data.split(b'\0'):
        if IDENTIFIER.fullmatch(token):
            found.add(token.decode('ascii'))
    for match in UTF16_IDENTIFIER.finditer(data):
        found.add(match.group().decode('utf-16-le'))
    return found


def compute(data: bytes, nm_output: str) -> dict:
    exports = exported_names(nm_output)
    strings = binary_strings(data)
    missing = [name for name in GUEST_ENTRY_POINTS if '_' + name not in exports]
    looked_up = {name for name in exports if name.startswith('_') and name[1:] in strings}
    keep = sorted(looked_up | {'_' + name for name in GUEST_ENTRY_POINTS if '_' + name in exports})
    refused = [name for name in keep if REFUSED_IN_KEPT.search(name)]
    dropped = sorted(exports - set(keep))
    return dict(exportsBefore=len(exports), kept=len(keep), dropped=len(dropped),
                guestEntryPoints=list(GUEST_ENTRY_POINTS), missingGuestEntryPoints=missing,
                refusedKept=refused, keep=keep,
                droppedGlslang=sum(1 for name in dropped if REFUSED_IN_KEPT.search(name)),
                droppedCxx=sum(1 for name in dropped if name.startswith('__Z')),
                droppedObjcClasses=sum(1 for name in dropped if name.startswith('_OBJC_CLASS_$_')))


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-6], file=sys.stderr)
        return 2
    binary, nm_output, list_path, report_path = (Path(item) for item in argv)
    result = compute(binary.read_bytes(), nm_output.read_text(errors='replace'))
    report = {key: value for key, value in result.items() if key != 'keep'} | dict(keptSymbols=result['keep'])
    report_path.write_text(json.dumps(report, indent=1) + '\n')
    errors = []
    if result['missingGuestEntryPoints']:
        errors.append('guest entry points not exported by the unrestricted link: ' +
                      ', '.join(result['missingGuestEntryPoints']))
    if result['refusedKept']:
        errors.append('kept symbols that name glslang: ' + ', '.join(result['refusedKept'][:20]))
    if errors:
        for error in errors:
            print('export_list: ' + error, file=sys.stderr)
        return 1
    list_path.write_text(''.join(name + '\n' for name in result['keep']))
    print(f"export_list: {result['kept']} of {result['exportsBefore']} exports kept "
          f"({result['dropped']} hidden, {result['droppedGlslang']} of them glslang)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
