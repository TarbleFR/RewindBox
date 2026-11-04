#!/usr/bin/env python3
"""Host tests of RPCS3 Core 645 = Core 641 + build-utils/rpcs3/core645-from-641.patch.

Core 645 (REWINDBOX_AUDIO_TIMEOUT_MIX_645, iOS): a cellAudio period whose wait for a port the game has not written timed
out is no longer advanced without output; it is mixed (touched ports' PCM, untouched ports silent), or output as its
silent block (no port touched), or recorded as a missing block (time stretching), and advanced as before. IPA 643
Assassin's Creed logs: every starved 2 s window followed such timeouts (597 periods dropped in 3.2 minutes). This driver:
- authenticates the increment against its record and reverts it to the pinned Core 641 file;
- checks the source: insertions only, one guarded `continue` with its comment in the timeout branch;
- runs test/rpcs3_audio_timeout_mix645_test.py (real decision block of both trees, real refill controller) on the
  reverted Core 641 tree (control) and this tree (candidate);
- runs the Core 641 suite on the reverted tree (which runs the 638, 636, 634, 630 and 627 suites in turn).
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
DELTA = ROOT / 'build-utils/rpcs3/core645-from-641.patch'
RECORD = ROOT / 'build-utils/rpcs3/core645-delta.json'
FILES = ('rpcs3/Emu/Cell/Modules/cellAudio.cpp',)
MARK = 'REWINDBOX_AUDIO_TIMEOUT_MIX_645'

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha, build, execute, last_json)

require = core636.require


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core641']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core645-from-641.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) and increment['files'] == 1, 'core645 files')
    removed = [line for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    added = [line[1:].strip() for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    require(not removed, 'insertions only')
    code = [line for line in added if line and not line.startswith('//')]
    require(code == ['#ifdef RPCS3_IOS', 'if (!g_cfg.audio.disable_sampling_skip)', '{', 'continue;', '}', '#endif'],
            'one guarded continue: ' + repr(code))
    require(any(MARK in line for line in added), 'the change is marked')
    context = text.split('@@', 2)[2]
    require('++ringbuffer->diagnostics.timeout_advances;' in context and 'untouched_expected = untouched;' in context,
            'the change sits in the timeout branch, after untouched_expected is set')
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 645 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'added_code_lines': len(code)}


def core641_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core641']
    tree = work / 'core641'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 641 tree cannot be rebuilt: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 641 SHA-256')
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
    with tempfile.TemporaryDirectory(prefix='core645-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree641 = core641_tree(source, work)
        require(MARK not in (tree641 / FILES[0]).read_text('utf-8', 'surrogateescape'), 'the Core 641 tree already has the change')
        print('timeout mix: real decision block, control 641 and candidate 645')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_audio_timeout_mix645_test.py'), '--control', str(tree641),
                                 '--candidate', str(source), '--cxx', args.cxx, '--report', str(work / 'timeout-mix.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
        require(result.returncode == 0, 'timeout mix test fails:\n' + result.stdout[-3000:])
        report['timeoutMix'] = json.loads((work / 'timeout-mix.json').read_text())
        print('core 641 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core641_test.py'), '--source', str(tree641), '--cxx', args.cxx,
                   '--report', str(work / 'core641.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 641' in result.stdout, 'the Core 641 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core641'] = json.loads((work / 'core641.json').read_text())
    print('PASS: Core 645 increment reverts to Core 641; a timed-out cellAudio period is output instead of dropped (real decision '
          'block and refill controller); the Core 641 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
