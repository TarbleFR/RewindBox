#!/usr/bin/env python3
"""Host tests of RPCS3 Core 638 = Core 636 + build-utils/rpcs3/core638-from-636.patch.

Core 638 adds instrumentation only, for one decision the logs cannot make (REWINDBOX_READBACK_PREDICTION_638):
God of War III reads one 1280x720x4 surface back per frame (Build 622: READBACK555 fault_read 132 per 5 s window,
554 ms) after early submission (585) and asynchronous submits (587). READBACK555 counts only sections still
unsynchronized at the read, so whether RPCS3's speculative readback copied them ahead, wasted such copies or never
fired is unknown. Five counters at the texture cache's existing predictor signals, one COREPROF READPREDICT638 line
per window. This driver:
- authenticates the increment against its record, checks it adds lines only and reverts it to the pinned Core 636 files;
- checks the source: each counter at its one signal site under RPCS3_IOS, the line with its five fields, nothing else;
- runs test/rpcs3_core638/readback_prediction_test.cpp on the real section methods extracted from this tree
  (plain, then ThreadSanitizer and ASan/UBSan);
- runs the Core 636 suite on the reverted tree (which runs the 634, 630 and 627 suites in turn).
No gameplay, iPhone or FPS claim.
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
HERE = ROOT / 'test/rpcs3_core638'
DELTA = ROOT / 'build-utils/rpcs3/core638-from-636.patch'
RECORD = ROOT / 'build-utils/rpcs3/core638-delta.json'
UTILS = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
HEADER = 'rpcs3/ios/IOSReadbackPrediction.h'
MARK = 'REWINDBOX_READBACK_PREDICTION_638'
FIELDS = ('flushes', 'speculative_copies', 'flushes_after_speculation', 'mispredictions', 'misses')

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha, build, execute, last_json)

require = core636.require


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core636']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core638-from-636.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    require(sorted(files) == sorted(increment['files_after_sha256']) and increment['files'] == len(files) == 3, 'core638 files')
    removed = [line for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    require(not removed and increment['insertions_only'], 'the Core 638 increment removes lines: ' + repr(removed[:3]))
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 638 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'insertions_only': True}


def core636_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core636']
    tree = work / 'core636'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 636 tree cannot be rebuilt: ' + result.stdout[-2000:])
    require(not (tree / HEADER).exists(), HEADER + ' survives the reversal')
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 636 SHA-256')
    return tree


def body(text: str, signature: str) -> str:
    start = text.index(signature)
    open_brace = text.index('{', start)
    depth = 0
    for index in range(open_brace, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[start:index + 1]
    raise ValueError(signature)


def check_source(source: Path) -> dict:
    utils = (source / UTILS).read_text('utf-8', 'surrogateescape')
    perf = (source / PERF).read_text('utf-8', 'surrogateescape')
    sites = {
        'void on_flush()': ('prediction::count(prediction::flushes);', 'if (speculatively_flushed) prediction::count(prediction::flushes_after_speculation);'),
        'void on_speculative_flush()': ('prediction::count(rpcs3::ios::readback::prediction::speculative_copies)',),
        'void on_miss()': ('prediction::count(rpcs3::ios::readback::prediction::misses)',),
        'void touch(u64 tag)': ('prediction::count(rpcs3::ios::readback::prediction::mispredictions)',),
    }
    for signature, needles in sites.items():
        require(utils.count(signature) == 1, signature + ' is not unique')
        method = body(utils, signature)
        require(all(method.count(needle) == 1 for needle in needles) and '#ifdef RPCS3_IOS' in method, signature + ' lacks its counter')
    require(utils.count('rpcs3::ios::readback::prediction::count(') + utils.count('prediction::count(prediction::') == 5,
            'a counter outside its signal site')
    flushes_after = body(utils, 'void on_flush()')
    require(flushes_after.index('flushes_after_speculation') < flushes_after.index('speculatively_flushed = false;'),
            'the speculation flag is read after it is cleared')
    misprediction = body(utils, 'void touch(u64 tag)')
    require(misprediction.index('mispredictions') > misprediction.index('if (speculatively_flushed)'),
            'a misprediction is counted outside the speculated case')
    line = re.search(r'COREPROF READPREDICT638 session=%llu window=%llu (.*?) scope=', perf, re.S)
    require(line is not None and perf.count('COREPROF READPREDICT638') == 1, 'one READPREDICT638 line')
    named = re.findall(r'(\w+)=%llu', line.group(1).replace('"\n', ' ').replace('"', ''))
    require(tuple(named) == FIELDS, 'READPREDICT638 fields: ' + repr(named))
    require(perf.index('COREPROF READPREDICT638') > perf.index('COREPROF READBACK555'), 'READPREDICT638 follows READBACK555')
    require('#include "IOSReadbackPrediction.h"' in perf and '#include "ios/IOSReadbackPrediction.h"' in utils, 'includes')
    return {'sites': len(sites), 'fields': list(FIELDS)}


def fixture(source: Path, cxx: str, folder: Path, sanitize: bool) -> dict:
    folder.mkdir(parents=True)
    utils = (source / UTILS).read_text('utf-8', 'surrogateescape')
    methods = '\n'.join(body(utils, signature) for signature in
                        ('void on_flush()', 'void on_speculative_flush()', 'void on_miss()', 'void touch(u64 tag)'))
    (folder / 'section_methods.inc').write_text(methods + '\n', 'utf-8', 'surrogateescape')
    sets = {'plain': ['-O1', '-g']}
    if sanitize:
        sets['tsan'] = ['-O1', '-g', '-fsanitize=thread'] + ([] if 'clang' in Path(cxx).name else ['-Wno-tsan'])
        sets['asan'] = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined', '-fno-omit-frame-pointer']
    report = {}
    for name, flags in sets.items():
        output = folder / ('readback_prediction-' + name)
        core636.build(cxx, [HERE / 'readback_prediction_test.cpp'], output, [source / 'rpcs3', folder],
                      flags + ['-DRPCS3_IOS=1', '-Wall', '-Wextra', '-Werror'])
        code, text = core636.execute([str(output)])
        require(code == 0 and core636.last_json(text).get('failures') == 0, f'readback prediction ({name}) failed:\n' + text[-3000:])
        report[name] = core636.last_json(text)
    return report


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
    with tempfile.TemporaryDirectory(prefix='core638-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree636 = core636_tree(source, work)
        print('source')
        report['source'] = check_source(source)
        require(MARK not in (tree636 / UTILS).read_text('utf-8', 'surrogateescape'), 'the Core 636 tree already counts')
        print('readback prediction fixture')
        report['fixture'] = fixture(source, args.cxx, work / 'fixture', sanitize)
        print('core 636 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core636_test.py'), '--source', str(tree636), '--cxx', args.cxx,
                   '--report', str(work / 'core636.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 636' in result.stdout, 'the Core 636 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core636'] = json.loads((work / 'core636.json').read_text())
    print('PASS: Core 638 increment reverts to Core 636; lines added only; five counters at their signal sites and one '
          'READPREDICT638 line; the real section methods counted; the Core 636 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
