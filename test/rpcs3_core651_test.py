#!/usr/bin/env python3
"""Host tests of RPCS3 Core 651 = Core 645 + build-utils/rpcs3/core651-from-645.patch.

Core 651 (REWINDBOX_AUDIO_LOW_RING_MIX_651, iOS): the wait for a port the game has not written also ends when the output
ring holds under two blocks after the period is due, and the period is output as on a Core 645 timeout. One counter
(low_ring_mixes) is appended to the AUDIO641 queue line. This driver:
- authenticates the increment against its record and reverts it to the pinned Core 645 files;
- checks the source: the low-ring condition, its counter and the appended log field, nothing else;
- runs test/rpcs3_audio_low_ring_mix651_test.py (real decision block of both trees, real refill controller) on the
  reverted Core 645 tree (control) and this tree (candidate), and the AUDIO641 host-admission test;
- runs the Core 645 suite on the reverted tree (which runs the 641, 638, 636, 634, 630 and 627 suites in turn).
No audio-quality, gameplay, iPhone or FPS claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DELTA = ROOT / 'build-utils/rpcs3/core651-from-645.patch'
RECORD = ROOT / 'build-utils/rpcs3/core651-delta.json'
FILES = ('rpcs3/Emu/Cell/Modules/cellAudio.cpp', 'rpcs3/ios/IOSAudioDiagnostics.h')
MARK = 'REWINDBOX_AUDIO_LOW_RING_MIX_651'

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha, build, execute, last_json)

require = core636.require


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core645']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core651-from-645.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) and increment['files'] == 2, 'core651 files')
    removed = [line[1:].strip() for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    added = [line[1:].strip() for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    code = [line for line in added if line and not line.startswith('//')]
    # Replaced lines: the queue format and its arguments gain low_ring_mixes; the timeout condition gains the low-ring term.
    require(len(removed) == 3, 'three replaced lines: ' + repr(removed))
    require(any('low_ring_mixes=%llu' in line for line in code) and any('diagnostics.low_ring_mixes);' in line for line in code),
            'the queue line carries low_ring_mixes')
    require('std::uint64_t low_ring_mixes = 0;' in code and 'bool rewindbox_low_ring = false;' in code and
            'enqueued_playtime < static_cast<u64>(cfg.audio_block_period) * 2;' in code, 'the low-ring rule and its counter')
    require(any(MARK in line for line in added), 'the change is marked')
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 651 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'added_code_lines': len(code)}


def core645_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core645']
    tree = work / 'core645'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 645 tree cannot be rebuilt: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 645 SHA-256')
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    sanitize = not args.no_sanitizers
    report: dict = {'cxx': args.cxx}
    with tempfile.TemporaryDirectory(prefix='core651-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree645 = core645_tree(source, work)
        require(MARK not in (tree645 / FILES[0]).read_text('utf-8', 'surrogateescape'), 'the Core 645 tree already has the change')
        print('low-ring mix: real decision block, control 645 and candidate 651')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_audio_low_ring_mix651_test.py'), '--control', str(tree645),
                                 '--candidate', str(source), '--cxx', args.cxx, '--report', str(work / 'low-ring.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
        require(result.returncode == 0, 'low-ring test fails:\n' + result.stdout[-3000:])
        report['lowRing'] = json.loads((work / 'low-ring.json').read_text())
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_audio_diagnostics_export641_test.py')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        require(result.returncode == 0, 'AUDIO641 host admission fails:\n' + result.stdout[-2000:])
        print('core 645 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core645_test.py'), '--source', str(tree645), '--cxx', args.cxx,
                   '--report', str(work / 'core645.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 645' in result.stdout, 'the Core 645 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core645'] = json.loads((work / 'core645.json').read_text())
    print('PASS: Core 651 increment reverts to Core 645; the late-port wait ends when the output ring holds under two blocks '
          '(real decision block and refill controller); AUDIO641 still admitted; the Core 645 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
