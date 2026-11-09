#!/usr/bin/env python3
"""Run the stand-alone Metal binary archive probe (metal_probe.mm) on this Mac's Metal device and write its report.

Lot 7. Every "session" is a new process. Metal keeps its own caches per process name (the report lists the
com.apple.metal directories it finds), so each role runs under its own executable name: a role that never ran starts with
a cold system cache, and its second run is warm. The salt (from the run identifier) makes the shader sources of this run
unknown to anything the machine already held.

Writes dist/melonx-metal-archive-probe/report.json and prints a summary. It fails only when the probe cannot run or a
binary archive fact the design depends on is contradicted; every measured value is recorded either way.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/melonx-metal-archive-probe'
SOURCE = ROOT / 'test/melonx_metal_binary_archive/metal_probe.mm'


def run(name, mode, work, salt, *extra):
    binary = OUT / 'bin' / name
    if not binary.exists():
        shutil.copy2(OUT / 'bin/metal_probe', binary)
    start = time.time()
    result = subprocess.run([str(binary), mode, str(work), str(salt), *map(str, extra)], capture_output=True, text=True, timeout=1800)
    entry = {'process': name, 'mode': mode, 'salt': salt, 'extra': list(map(str, extra)), 'returncode': result.returncode,
             'seconds': round(time.time() - start, 2)}
    lines = [line for line in result.stdout.splitlines() if line.startswith('{')]
    if lines:
        entry['report'] = json.loads(lines[-1])
    if result.returncode or not lines:
        entry['stderr'] = result.stderr[-3000:]
        entry['stdout'] = result.stdout[-1000:]
    return entry


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / 'bin').mkdir(parents=True)
    work = OUT / 'work'
    build = subprocess.run(['clang++', '-std=c++17', '-fobjc-arc', '-O1', '-Wall', '-framework', 'Metal', '-framework', 'Foundation',
                            '-framework', 'CoreGraphics', str(SOURCE), '-o', str(OUT / 'bin/metal_probe')], capture_output=True, text=True)
    (OUT / 'build.log').write_text(build.stdout + build.stderr)
    if build.returncode:
        print(build.stderr[-6000:])
        raise SystemExit('the probe does not build')
    base = int(os.environ.get('GITHUB_RUN_ID', str(int(time.time())))) % 1_000_000_007
    size = os.environ.get('PROBE_SET', '12 6 24').split()
    runs = []

    def step(label, *args):
        entry = run(*args)
        entry['label'] = label
        runs.append(entry)
        report = entry.get('report', {})
        keys = ('libraries', 'createRender', 'createCompute', 'addAfterCreateRender', 'addAfterCreateCompute', 'save', 'archiveLoad', 'strictRender',
                'strictCompute', 'absentVariant', 'normalWithArchiveOfferedRender', 'twoArchivesStrictHits', 'addMissedAndSave', 'addFirstRender',
                'createFromFreshArchiveRender', 'strictFailures', 'damaged', 'servedByNormalCompilation', 'threads', 'result', 'errors',
                'footprintDeltaMiB', 'saveToMissingDirectory', 'systemCacheRemoved')
        print(label, '| rc', entry['returncode'], '|', json.dumps({k: report[k] for k in keys if k in report}), flush=True)
        if entry['returncode']:
            print(entry.get('stderr', ''), flush=True)
        return entry

    # Reference without any archive: three cold samples (three salts), then the first one again (warm).
    for index in range(3):
        step(f'baseline cold {index + 1}', 'probe-baseline', 'baseline', work / f'unused{index}', base + index, *size)
    step('baseline warm (same process name, same salt as cold 1)', 'probe-baseline', 'baseline', work / 'unused0', base, *size)
    # Collection: the same set as "baseline cold 1", under another process name.
    step('collect (create, then add, then save)', 'probe-collect', 'collect', work / 'archive', base, *size)
    # Reuse in a new process whose system cache never saw these shaders, then again (warm), then with its cache removed.
    step('reuse 1 (new process name)', 'probe-reuse', 'reuse', work / 'archive', base, *size)
    step('reuse 2 (same process name)', 'probe-reuse', 'reuse', work / 'archive', base, *size)
    step('reuse 3 (its system cache removed first)', 'probe-reuse', 'reuse', work / 'archive', base, *size, '--clear-system-cache')
    step('damaged copies', 'probe-damaged', 'damaged', work / 'archive', base, *size)
    step('threads', 'probe-threads', 'threads', work / 'archive', base, *size)
    # The other collection order, on a set nothing has seen.
    step('collect, add first (cold)', 'probe-addfirst', 'collect-addfirst', work / 'addfirst', base + 100, *size)
    step('collect, create first (cold, for comparison)', 'probe-createfirst', 'collect', work / 'createfirst', base + 200, *size)

    first = runs[0].get('report', {})
    summary = {'device': first.get('device'), 'osVersion': first.get('osVersion'), 'osBuild': first.get('osBuild'), 'set': first.get('set'),
               'xcode': subprocess.run(['xcodebuild', '-version'], capture_output=True, text=True).stdout.split('\n')[:2],
               'runs': runs}
    (OUT / 'report.json').write_text(json.dumps(summary, indent=1) + '\n')
    shutil.rmtree(OUT / 'bin', ignore_errors=True)

    failures = []
    by = {entry['label']: entry for entry in runs}
    for entry in runs:
        if entry['returncode']:
            failures.append(entry['label'] + ': exit ' + str(entry['returncode']))
    collect = by['collect (create, then add, then save)'].get('report', {})
    reuse = by['reuse 1 (new process name)'].get('report', {})
    if not collect.get('archiveCreated'):
        failures.append('no binary archive on this device')
    if reuse.get('strictRender', {}).get('misses', 1) or not reuse.get('strictRender', {}).get('hits'):
        failures.append('covered render pipelines are not all served by the archive')
    if reuse.get('absentVariant', {}).get('strictSucceeded', True) or not reuse.get('absentVariant', {}).get('normalSucceeded'):
        failures.append('the variant left out does not miss, or the normal compilation does not serve it')
    baseline = by['baseline cold 1'].get('report', {}).get('result')
    if baseline and reuse.get('result') and (baseline['drawHash'] != reuse['result']['drawHash'] or baseline['computeHash'] != reuse['result']['computeHash']):
        failures.append('a pipeline from the archive does not draw or compute the baseline result')
    print(json.dumps({'device': summary['device'], 'osBuild': summary['osBuild'], 'failures': failures}), flush=True)
    if failures:
        raise SystemExit('; '.join(failures))


if __name__ == '__main__':
    main()
