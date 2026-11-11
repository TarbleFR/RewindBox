#!/usr/bin/env python3
"""The runtime marker rule of the packaged RPCS3 Core, before and after Core 927.

.github/diagnostics/rpcs3_core_component.py checks, at delivery, that the packaged Core carries the runtime markers of
the asynchronous MoltenVK submits. Until Core 926 three of them belonged to the boot record (the record's file name, the
canary= field of COREPROF OPT587, the "stay off" message). Core 927 removes the record on the maintainer's order: such a
Core must carry none of the three and must carry what replaced them. This test runs the rule on byte images built from
the markers themselves; no Core binary is read.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for path in ('.github/diagnostics', 'build-utils'):
    sys.path.insert(0, str(ROOT / path))
import rpcs3_core_component as component  # noqa: E402
import validate_rpcs3_core604_ipa as core604  # noqa: E402

MARKERS = core604.candidate.CORE_MARKERS


def refused(image: bytes, text: str) -> bool:
    try:
        component.check_runtime_markers(image, MARKERS)
    except ValueError as error:
        return text in str(error)
    return False


def main() -> None:
    record = [m for m in MARKERS if component.CANARY_MARKER.fullmatch(m) or m in component.BOOT_RECORD_MARKERS]
    kept = [m for m in MARKERS if m not in record]
    assert len(record) == 3 and len(kept) == len(MARKERS) - 3, 'three markers belong to the boot record'

    # A Core up to 926: every marker, the record's file name under the number of its Core.
    before = b'\0'.join(kept + [b'canary=%s confirmed=%u exec_queues=%u', b'rewindbox-mvk-async-926.txt', component.BOOT_RECORD_MARKERS[1]])
    assert component.check_runtime_markers(before, MARKERS) is False
    assert refused(before.replace(b'rewindbox-mvk-async-926.txt', b''), 'canary file name')
    assert refused(before.replace(b'canary=%s confirmed=%u exec_queues=%u', b''), 'Core runtime marker missing')

    # A Core from 927: none of the record's markers, all of what replaced them.
    after = b'\0'.join(kept + [component.DEFINITIVE_927, *component.DEFINITIVE_927_MARKERS])
    assert component.check_runtime_markers(after, MARKERS) is True
    for leftover in (b'rewindbox-mvk-async-926.txt', b'canary=%s confirmed=%u exec_queues=%u', component.BOOT_RECORD_MARKERS[1]):
        assert refused(after + b'\0' + leftover, 'still carries a marker of it'), leftover
    for marker in component.DEFINITIVE_927_MARKERS:
        assert refused(after.replace(marker, b'x' * len(marker)), 'Core runtime marker missing'), marker
    for marker in kept:
        assert refused(after.replace(marker, b'x' * len(marker)), 'Core runtime marker missing'), marker

    # The markers named here are the strings of the Core 927 source.
    build = (ROOT / 'build-utils/rpcs3/core927-from-926.patch').read_bytes()
    for marker in (component.DEFINITIVE_927, *component.DEFINITIVE_927_MARKERS):
        assert marker in build, marker
    print('PASS: runtime marker rule (boot record required up to Core 926, refused from Core 927 with its replacements required)')


if __name__ == '__main__':
    main()
