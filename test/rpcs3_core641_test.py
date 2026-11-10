#!/usr/bin/env python3
"""Host tests of RPCS3 Core 641 = Core 638 + build-utils/rpcs3/core641-from-638.patch.

Core 641 changes log text only (REWINDBOX_AUDIO_DIAGNOSTICS_EXPORT_641): the Core's three cumulative audio diagnostic
lines (cellAudio queue and producer, RemoteIO render callback), notice level and at most every 2 s, get the
COREPROF AUDIO641 prefix that the host log callback already writes to the device logs; IPA 640 logs held no runtime
audio counter for the Assassin's Creed audio stutters. This driver:
- authenticates the increment against its record and reverts it to the pinned Core 638 files;
- checks the source: exactly the three format strings change (prefix only, same arguments), nothing else;
- runs test/rpcs3_audio_diagnostics_export641_test.py (real host filter on the real formats);
- runs the Core 638 suite on the reverted tree (which runs the 636, 634, 630 and 627 suites in turn).
No audio, gameplay, iPhone or FPS claim.
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
DELTA = ROOT / 'build-utils/rpcs3/core641-from-638.patch'
RECORD = ROOT / 'build-utils/rpcs3/core641-delta.json'
FILES = ('rpcs3/Emu/Cell/Modules/cellAudio.cpp', 'rpcs3/Emu/Audio/IOS/IOSAudioBackend.cpp')
MARK = 'REWINDBOX_AUDIO_DIAGNOSTICS_EXPORT_641'

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha, build, execute, last_json)

require = core636.require


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core638']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core641-from-638.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) and increment['files'] == 2, 'core641 files')
    removed = [line[1:] for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    added = [line[1:] for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    require(len(removed) == 3, 'three changed lines: ' + repr(len(removed)))
    changed = [line for line in added if '.notice(' in line]
    require(len(changed) == 3 and all(line.split('"', 1)[1].startswith('COREPROF AUDIO641 part=') for line in changed),
            'the three notices carry the COREPROF AUDIO641 prefix')
    for old in removed:
        prefix, rest = old.split('.notice("', 1)
        tail = rest.split(' cumulative ', 1)[1]
        require(any(line.startswith(prefix + '.notice("COREPROF AUDIO641 part=') and line.endswith(tail) for line in changed),
                'only the prefix changes: ' + old[:80])
    require(all(line.lstrip().startswith('//') for line in added if line not in changed), 'other added lines are comments')
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 641 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'notices': 3}


def core638_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core638']
    tree = work / 'core638'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 638 tree cannot be rebuilt: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 638 SHA-256')
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
    with tempfile.TemporaryDirectory(prefix='core641-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree638 = core638_tree(source, work)
        require(MARK not in (tree638 / FILES[0]).read_text('utf-8', 'surrogateescape'), 'the Core 638 tree already exports')
        print('host admission of the audio lines')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_audio_diagnostics_export641_test.py')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        require(result.returncode == 0, 'audio export test fails:\n' + result.stdout[-2000:])
        report['export'] = result.stdout.strip().splitlines()[-1]
        print('core 638 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core638_test.py'), '--source', str(tree638), '--cxx', args.cxx,
                   '--report', str(work / 'core638.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 638' in result.stdout, 'the Core 638 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core638'] = json.loads((work / 'core638.json').read_text())
    print('PASS: Core 641 increment reverts to Core 638; the three audio notices carry the COREPROF AUDIO641 prefix only; '
          'the real host filter admits them; the Core 638 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
