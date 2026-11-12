#!/usr/bin/env python3
"""Check the rewriter's output for the synthetic module without executing it.

Usage: check_rewrite.py <output dir> <rewriter log> [--digest <file>]
Fails unless: no gap, an Apple-target layout, the two gates (svc 0x26, cntpct
x5), every redirected instruction replaced by a branch, and brk left in place.
"""
import hashlib
import json
import pathlib
import re
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import make_synth_nso as synth

FILES = ['main.patched.bin', 'main.fixups.tsv', 'main.gates.tsv', 'main.sites.tsv', 'main.gaps.tsv']


def main():
    out, log = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]).read_text(errors='replace')
    errors = []
    missing = [name for name in FILES if not (out / name).is_file()]
    if missing:
        sys.exit(f'missing outputs: {missing}')
    summary = re.findall(r'PFRW mod=main need=\d+ gaps=(\d+) fatal=(\d+)', log)
    if summary != [('0', '0')]:
        errors.append(f'expected one PFRW line with gaps=0 fatal=0, got {summary}')
    header = {}
    for line in (out / 'main.fixups.tsv').read_text().splitlines():
        if line.startswith('# '):
            key, _, value = line[2:].partition('\t')
            header.setdefault(key, value)
    for key in ('PATCH_OFF', 'KEY_PAGE_OFF', 'KEY_PAGE_SIZE', 'TEXT_END', 'KEY_K18_IDX', 'KEY_KTLS_IDX',
                'KEY_KTLR_IDX', 'KEY_KGATE_IDX'):
        if key not in header:
            errors.append(f'fixups header lacks {key}')
    if 'TARGET' in header:
        errors.append('fixups header carries TARGET: not an Apple-target output')
    gates = []
    for line in (out / 'main.gates.tsv').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 4 and not line.startswith('#'):
            gates.append((fields[1], int(fields[2]), int(fields[3], 16)))
    code_at = synth.CODE_AT
    want = {('svc', 0x26, code_at + 4 * synth.CODE.index(0xD40004C1)),
            ('cntpct', 5, code_at + 4 * synth.CODE.index(0xD53BE025))}
    if set(gates) != want:
        errors.append(f'gates {sorted(gates)} differ from expected {sorted(want)}')
    image = (out / 'main.patched.bin').read_bytes()
    redirected = {0xD53BD041, 0xD51BD042, 0xD53BD063, 0xAA0203F2, 0x91002244, 0xD53BE025, 0xD53B0026,
                  0xD40004C1, 0xD53BD047}
    words = struct.unpack_from('<%dI' % len(synth.CODE), image, code_at)
    for index, (before, after) in enumerate(zip(synth.CODE, words)):
        at = code_at + 4 * index
        if before in redirected:
            # An x18 use directly after a redirected x18 instruction may be moved with it as one unit.
            grouped = before == 0x91002244 and words[index - 1] >> 26 == 0b000101
            if after >> 26 != 0b000101 and not grouped:
                errors.append(f'{at:#x}: {before:#010x} not replaced by a branch (now {after:#010x})')
        elif before != after:
            errors.append(f'{at:#x}: {before:#010x} changed to {after:#010x} although it needs no redirection')
    digests = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in FILES}
    report = {'header': header, 'gates': sorted(gates), 'sha256': digests, 'errors': errors}
    print(json.dumps(report, indent=2))
    if '--digest' in sys.argv:
        pathlib.Path(sys.argv[sys.argv.index('--digest') + 1]).write_text(json.dumps(digests, sort_keys=True) + '\n')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
