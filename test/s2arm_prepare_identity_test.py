#!/usr/bin/env python3
"""The preparation of a Switch 2 game is kept across deliveries that change neither its code nor the engine (python3 + cc).

Journal of an iPhone17,2, 13 Nov, first launch of Mario Kart World after IPA 734 was installed: the preparation ran
again from scratch, 92 s (RomFS view 25.2 s, code 3.1 s, pack walk 19.9 s, pack hashing 43.4 s), and the engine then
wrote its RomFS index again (126.9 s with that IPA). The preparation's fingerprint held the app's build number, which
changes with every delivery, whatever the delivery contains.

The fingerprint now holds the identity of the compiled code instead: the LC_UUID of the image that holds the
preparation library (it is linked into the app's binary with the plugin) and of the engine framework's binary. A linker
derives that UUID from the image's content, so it changes whenever the code does. The build number stays the identity
when either UUID cannot be read.

The reader (S2ArmCodeIdentity.c) is plain C over bytes and is compiled and run here over Mach-O headers built by this
test: found among other commands, the same from memory, from a file and with the commands' size taken from a loaded
header; refused when truncated, malformed, fat or without a UUID. What a real delivery's two UUIDs are, and whether two
builds of the same code give the same ones, is only known from a device journal (its `identity` field says `code` or
`build`; `prepare reused` after an update is the gain).

    python3 -B test/s2arm_prepare_identity_test.py
"""
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'packages/s2arm_engine_bridge/ios/Classes'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def macho(commands, magic=0xfeedfacf, count=None, size=None):
    """A 64-bit Mach-O header followed by `commands` (each already encoded)."""
    body = b''.join(commands)
    return struct.pack('<IiiIIIII', magic, 0x0100000c, 0, 6, len(commands) if count is None else count, len(body) if size is None else size, 0, 0) + body


def command(kind, payload):
    return struct.pack('<II', kind, 8 + len(payload)) + payload


UUID = bytes(range(0x10, 0x20))
TEXT = '10111213-1415-1617-1819-1A1B1C1D1E1F'
segment = command(0x19, b'__TEXT'.ljust(64, b'\0'))
uuid = command(0x1b, UUID)
cases = [   # name, bytes, expected text ('' = refused)
    ('a UUID among other commands', macho([segment, command(0x32, b'\0' * 16), uuid, segment]), TEXT),
    ('a UUID first', macho([uuid]), TEXT),
    ('no UUID command', macho([segment, segment]), ''),
    ('not a Mach-O', b'\x7fELF' + b'\0' * 60, ''),
    ('a 32-bit Mach-O', macho([uuid], magic=0xfeedface), ''),
    ('a fat binary', struct.pack('>II', 0xcafebabe, 1) + b'\0' * 56, ''),
    ('commands cut short', macho([segment, uuid])[:-10], ''),
    ('a command of length 0', macho([struct.pack('<II', 0x19, 0), uuid]), ''),
    ('a command running past the commands', macho([struct.pack('<II', 0x19, 4096) + b'\0' * 16, uuid]), ''),
    ('a UUID command too short', macho([struct.pack('<II', 0x1b, 12) + b'\0' * 4]), ''),
    ('more commands announced than present', macho([segment], count=5), ''),
    ('a header alone', macho([])[:20], ''),
    ('commands larger than a megabyte announced', macho([uuid], size=(1 << 20) + 1), ''),
]

DRIVER = r'''
#include "S2ArmCodeIdentity.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
// argv: mode (memory | loaded | file) path. Prints "1 <uuid>" or "0 ".
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    char out[S2ARM_UUID_TEXT] = "x";
    int found;
    if (!strcmp(argv[1], "file")) found = s2arm_macho_uuid_file(argv[2], out);
    else {
        FILE *f = fopen(argv[2], "rb");
        if (!f) return 2;
        fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
        unsigned char *bytes = malloc(n ? (size_t)n : 1);   // exactly n bytes: a read past them is a heap overflow the sanitizer names
        if (fread(bytes, 1, (size_t)n, f) != (size_t)n) return 2;
        fclose(f);
        found = !strcmp(argv[1], "loaded") ? s2arm_macho_uuid_loaded(bytes, out) : s2arm_macho_uuid(bytes, (size_t)n, out);
        free(bytes);
    }
    printf("%d %s\n", found, out);
    return 0;
}
'''

source, header = PKG / 'S2ArmCodeIdentity.c', PKG / 'S2ArmCodeIdentity.h'
check(source.is_file() and header.is_file(), 'S2ArmCodeIdentity.c and .h exist in the plugin (the podspec compiles every Classes/**/*.c)')
text = source.read_text(encoding='utf-8') if source.is_file() else ''
check('#include <mach' not in text and '#import' not in text, 'the reader needs no Apple header (it is compiled and run here)')
compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
check(bool(compiler), 'a C compiler is available (cc, clang or gcc)')
ran = 0
if compiler and source.is_file():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        (work / 'driver.c').write_text(DRIVER)
        binary = work / 'identity'
        build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                                '-I', str(PKG), '-o', str(binary), str(work / 'driver.c'), str(source)], capture_output=True, text=True)
        if build.returncode:   # a compiler without the sanitizers: the same checks without them
            build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1', '-I', str(PKG), '-o', str(binary), str(work / 'driver.c'), str(source)],
                                   capture_output=True, text=True)
        check(build.returncode == 0, 'the reader compiles without a warning: ' + build.stderr[-700:])
        if build.returncode == 0:
            for index, (name, data, expected) in enumerate(cases):
                path = work / f'case{index}.bin'
                path.write_bytes(data)
                for mode in ('memory', 'file'):
                    run = subprocess.run([str(binary), mode, str(path)], capture_output=True, text=True, timeout=30)
                    want = f'1 {expected}' if expected else '0 '
                    check(run.returncode == 0 and run.stdout.rstrip('\n') == want, f'{name} ({mode}): expected {want!r}, got {run.stdout!r} {run.stderr[-300:]}')
                    ran += 1
            # A loaded image: only the header says how long the commands are. Read from a buffer that ends with them.
            good = work / 'loaded.bin'
            good.write_bytes(macho([segment, uuid]))
            run = subprocess.run([str(binary), 'loaded', str(good)], capture_output=True, text=True, timeout=30)
            check(run.returncode == 0 and run.stdout.strip() == f'1 {TEXT}', f'a loaded header: {run.stdout!r} {run.stderr[-300:]}')
            run = subprocess.run([str(binary), 'file', str(work / 'missing.bin')], capture_output=True, text=True, timeout=30)
            check(run.returncode == 0 and run.stdout.rstrip('\n') == '0 ', f'a missing file: {run.stdout!r}')
            ran += 2

prep = (PKG / 'S2ArmGamePreparation.m').read_text(encoding='utf-8')
check('#import "S2ArmCodeIdentity.h"' in prep and '#import <dlfcn.h>' in prep, 'the preparation imports the reader and dladdr')
check('[text appendFormat:@"%@\\nchain %@\\nexport %@\\n", preparationCodeIdentity(identityKind), chain, exportDir];' in prep
      and '@"build %@\\nchain %@' not in prep, 'the fingerprint holds the code identity where it held the build number')
check('s2arm_journal("prepare", "reused", "\\"gid\\":\\"%s\\",\\"identity\\":\\"%s\\"", gid.UTF8String, identityKind);' in prep
      and 's2arm_journal("prepare", "begin", "\\"gid\\":\\"%s\\",\\"identity\\":\\"%s\\"", gid.UTF8String, identityKind);' in prep,
      'the journal says which identity a preparation was judged by (code or build)')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'runs': ran}))
sys.exit(1 if failures else 0)
