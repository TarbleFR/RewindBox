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

NativeAOT's frozen literals are not always followed by a NUL character: in the pinned engine a literal is its
4-byte length, then its UTF-16LE characters, and the next record can start right after the last character's low
byte (IPA 746: `s2a_vpad_read_ex` ended `78 | 69 13 e8 0d …`). The first form of this tool asked for that NUL and so
missed every C# lookup that was not also part of a longer message: InputPump's s2a_vpad_read* / s2a_pad_* (no
controller or touch input reached any game), s2a_guest_tick_hz (the C# clock fell back to 19.2 MHz), the rest of
s2a_tail_* (the window-tail allocator) among 24. So a C# literal is also recognised by its length prefix (the
characters the length names, the last one's high byte not required), and the engine's sources are read too when the
tool runs at the root of S2Arm's tree (guest.mk runs it there): every name a C# GetExport / TryGetExport or a C /
Objective-C dlsym asks for with a literal is kept. REQUIRED names (the input pump, the clock, the tail allocator) must
be kept whenever the unrestricted link exports them, else the tool refuses.

A name the engine builds at run time is not found this way. The pinned tree has two such lookups, both outside a
release session: hud.c picks between two literal names (both strings, so both kept), nvn_mtl.m's DM_NVN_UB
measurement takes a variable name from the environment (its comment says release iOS builds cannot resolve those).

    export_list.py BINARY NM_OUTPUT LIST REPORT

BINARY is the unrestricted link, NM_OUTPUT its `nm -gU` output; LIST is written for -Wl,-exported_symbols_list (one
symbol per line, sorted), REPORT as JSON. Refused (exit 1): a guest entry point that the unrestricted link does not
export, a REQUIRED name the unrestricted link exports but the list would hide, and a kept symbol that names glslang.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GUEST_ENTRY_POINTS = ('s2a_rb_guest_configure', 's2a_rb_guest_make_view_controller', 's2a_rb_guest_start',
                      's2a_rb_guest_stop', 's2a_rb_guest_fatal',
                      # patch 0010: the host resumes the game Quit parked (S2ArmEngineBridgePlugin.m resumeParkedGame)
                      's2a_rb_guest_parked', 's2a_rb_guest_view_controller', 's2a_rb_guest_resume',
                      # patch 0078: the in-game menu changes the frame-rate limit during play (S2ArmEngineBridgePlugin.m applyLiveSetting)
                      's2a_rb_guest_set_fps_limit')
IDENTIFIER = re.compile(rb'[A-Za-z_][A-Za-z0-9_$.]{1,255}')
UTF16_IDENTIFIER = re.compile(rb'(?:[A-Za-z_]\x00)(?:[A-Za-z0-9_$.]\x00){1,255}')
# A run of UTF-16LE identifier characters whose last character's high byte is not looked at (see the module text)
UTF16_RUN = re.compile(rb'[A-Za-z_]\x00(?:[A-Za-z0-9_$.]\x00){0,254}[A-Za-z0-9_$.]')
SOURCE_LOOKUPS = (('services', '.cs', re.compile(r'(?:Try)?GetExport\s*\([^,()]+,\s*"([A-Za-z_][A-Za-z0-9_]*)"')),
                  ('compat/tree/src', '.cs', re.compile(r'(?:Try)?GetExport\s*\([^,()]+,\s*"([A-Za-z_][A-Za-z0-9_]*)"')),
                  ('runtime', ('.c', '.m'), re.compile(r'dlsym\s*\([^,()]+,\s*"([A-Za-z_][A-Za-z0-9_]*)"')),
                  ('ios', ('.c', '.m'), re.compile(r'dlsym\s*\([^,()]+,\s*"([A-Za-z_][A-Za-z0-9_]*)"')),
                  ('graphics', ('.c', '.m'), re.compile(r'dlsym\s*\([^,()]+,\s*"([A-Za-z_][A-Za-z0-9_]*)"')))
# Looked up by name and needed for the game to work: kept or the tool refuses (when the unrestricted link exports them)
REQUIRED = ('s2a_vpad_read', 's2a_vpad_read_ex', 's2a_vpad_read_touch', 's2a_vpad_touch_wanted', 's2a_vpad_touch_configured',
            's2a_pad_wait', 's2a_pad_wake', 's2a_pad_now_us', 's2a_pad_record_commit', 's2a_pad_get_latency',
            's2a_guest_tick_hz', 's2a_tail_map', 's2a_tail_unmap', 's2a_tail_has')
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
    for match in UTF16_RUN.finditer(data):   # a length-prefixed literal: the length names how many characters it has
        start = match.start()
        if start < 4:
            continue
        length = int.from_bytes(data[start - 4:start], 'little')
        run = match.group()
        chars = (len(run) + 1) // 2
        if 2 <= length <= chars:
            found.add((run + b'\x00')[:2 * length].decode('utf-16-le'))
    return found


def source_lookups(root: Path) -> set[str]:
    """Names the engine's sources look up with a literal: C# GetExport / TryGetExport, C and Objective-C dlsym."""
    found = set()
    for folder, suffixes, pattern in SOURCE_LOOKUPS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in base.rglob('*'):
            if path.is_file() and path.suffix in (suffixes if isinstance(suffixes, tuple) else (suffixes,)):
                found.update(pattern.findall(path.read_text(errors='replace')))
    return found


def compute(data: bytes, nm_output: str, sources: set[str] | None = None) -> dict:
    exports = exported_names(nm_output)
    strings = binary_strings(data)
    sources = set(sources or ())
    missing = [name for name in GUEST_ENTRY_POINTS if '_' + name not in exports]
    looked_up = {name for name in exports if name.startswith('_') and (name[1:] in strings or name[1:] in sources)}
    keep = sorted(looked_up | {'_' + name for name in GUEST_ENTRY_POINTS if '_' + name in exports})
    refused = [name for name in keep if REFUSED_IN_KEPT.search(name)]
    hidden_required = [name for name in REQUIRED if '_' + name in exports and '_' + name not in keep]
    dropped = sorted(exports - set(keep))
    return dict(exportsBefore=len(exports), kept=len(keep), dropped=len(dropped),
                guestEntryPoints=list(GUEST_ENTRY_POINTS), missingGuestEntryPoints=missing,
                required=list(REQUIRED), hiddenRequired=hidden_required,
                keptFromSourcesOnly=sorted(name for name in looked_up if name[1:] not in strings),
                refusedKept=refused, keep=keep,
                droppedGlslang=sum(1 for name in dropped if REFUSED_IN_KEPT.search(name)),
                droppedCxx=sum(1 for name in dropped if name.startswith('__Z')),
                droppedObjcClasses=sum(1 for name in dropped if name.startswith('_OBJC_CLASS_$_')))


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-6], file=sys.stderr)
        return 2
    binary, nm_output, list_path, report_path = (Path(item) for item in argv)
    result = compute(binary.read_bytes(), nm_output.read_text(errors='replace'), source_lookups(Path.cwd()))
    report = {key: value for key, value in result.items() if key != 'keep'} | dict(keptSymbols=result['keep'])
    report_path.write_text(json.dumps(report, indent=1) + '\n')
    errors = []
    if result['missingGuestEntryPoints']:
        errors.append('guest entry points not exported by the unrestricted link: ' +
                      ', '.join(result['missingGuestEntryPoints']))
    if result['hiddenRequired']:
        errors.append('names the engine looks up and needs, exported by the unrestricted link but not kept: ' +
                      ', '.join(result['hiddenRequired']))
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
