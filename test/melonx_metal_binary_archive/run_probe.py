#!/usr/bin/env python3
"""Run the stand-alone Metal binary archive probe (metal_probe.mm) on this Mac's Metal device and write its report.

Lot 7. Every "session" is a new process. The salt (from the run identifier) makes the shader sources of this run
unknown to anything the machine already held, so a first run is cold. Metal's own caches (com.apple.metal directories)
are found by comparing the user's cache and temporary directories before and after the first run; a "system cache
removed" step deletes exactly the directories this probe made grow, so the next process meets a cold system cache with
the binary archive still on disk. (First run of this probe, 9 Nov: the caches are not per process name.)

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


def metal_caches():
    """Every com.apple.metal* directory under the user's cache and temporary directories: path -> (bytes, files)."""
    roots = []
    for name in ('DARWIN_USER_CACHE_DIR', 'DARWIN_USER_TEMP_DIR'):
        value = subprocess.run(['getconf', name], capture_output=True, text=True).stdout.strip()
        if value:
            roots.append(Path(value))
    roots.append(Path.home() / 'Library/Caches')
    found = {}
    for root in roots:
        if not root.is_dir():
            continue
        for directory, names, _ in os.walk(root):
            depth = len(Path(directory).relative_to(root).parts)
            if depth >= 5:
                names[:] = []
                continue
            for name in list(names):
                if name.startswith('com.apple.metal'):
                    names.remove(name)
                    path = Path(directory) / name
                    files = [f for f in path.rglob('*') if f.is_file()]
                    try:
                        found[str(path)] = (sum(f.stat().st_size for f in files), len(files))
                    except OSError:
                        found[str(path)] = (-1, len(files))
    return found


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
                'footprintDeltaMiB', 'saveToMissingDirectory')
        print(label, '| rc', entry['returncode'], '|', json.dumps({k: report[k] for k in keys if k in report}), flush=True)
        if entry['returncode']:
            print(entry.get('stderr', ''), flush=True)
        return entry

    caches = {'before': metal_caches()}

    def remove_system_cache():
        """Delete the Metal cache directories this probe made grow (never anything it did not touch)."""
        removed = []
        for path in grown:
            if Path(path).is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path)
        caches.setdefault('removals', []).append(removed)
        return removed

    # Reference without any archive: three cold samples (three salts), then the first one again (warm).
    step('baseline cold 1', 'probe-baseline', 'baseline', work / 'unused0', base, *size)
    caches['afterFirstRun'] = metal_caches()
    grown = sorted(path for path, value in caches['afterFirstRun'].items() if caches['before'].get(path) != value)
    caches['grown'] = grown
    print('system Metal cache directories that changed:', json.dumps({p: caches['afterFirstRun'][p] for p in grown}), flush=True)
    for index in (1, 2):
        step(f'baseline cold {index + 1}', 'probe-baseline', 'baseline', work / f'unused{index}', base + index, *size)
    step('baseline warm (same process name, same salt as cold 1)', 'probe-baseline', 'baseline', work / 'unused0', base, *size)
    remove_system_cache()
    step('baseline, system cache removed (same salt as cold 1)', 'probe-baseline', 'baseline', work / 'unused0', base, *size)
    # Collection: the same set as "baseline cold 1" (system cache warm again from the step above).
    step('collect (create, then add, then save)', 'probe-collect', 'collect', work / 'archive', base, *size)
    # Reuse in a new process: system cache warm, then removed (the archive stays), then warm again.
    step('reuse 1 (system cache warm)', 'probe-reuse', 'reuse', work / 'archive', base, *size)
    remove_system_cache()
    step('reuse 2 (system cache removed, archive kept)', 'probe-reuse', 'reuse', work / 'archive', base, *size)
    remove_system_cache()
    step('reuse 3 (system cache removed again, archive kept)', 'probe-reuse', 'reuse', work / 'archive', base, *size)
    step('reuse 4 (system cache warm)', 'probe-reuse', 'reuse', work / 'archive', base, *size)
    step('damaged copies', 'probe-damaged', 'damaged', work / 'archive', base, *size)
    step('threads', 'probe-threads', 'threads', work / 'archive', base, *size)
    caches['atEnd'] = metal_caches()
    # The other collection order, on a set nothing has seen.
    step('collect, add first (cold)', 'probe-addfirst', 'collect-addfirst', work / 'addfirst', base + 100, *size)
    step('collect, create first (cold, for comparison)', 'probe-createfirst', 'collect', work / 'createfirst', base + 200, *size)

    first = runs[0].get('report', {})
    summary = {'device': first.get('device'), 'osVersion': first.get('osVersion'), 'osBuild': first.get('osBuild'), 'set': first.get('set'),
               'xcode': subprocess.run(['xcodebuild', '-version'], capture_output=True, text=True).stdout.split('\n')[:2],
               'systemMetalCaches': {'grown': caches.get('grown'), 'removals': caches.get('removals'),
                                     'atEnd': {p: caches['atEnd'][p] for p in caches.get('grown', []) if p in caches['atEnd']}},
               'runs': runs}
    (OUT / 'report.json').write_text(json.dumps(summary, indent=1) + '\n')
    shutil.rmtree(OUT / 'bin', ignore_errors=True)

    failures = []
    by = {entry['label']: entry for entry in runs}
    for entry in runs:
        if entry['returncode']:
            failures.append(entry['label'] + ': exit ' + str(entry['returncode']))
    collect = by['collect (create, then add, then save)'].get('report', {})
    reuse = by['reuse 1 (system cache warm)'].get('report', {})
    for label in ('reuse 2 (system cache removed, archive kept)', 'reuse 3 (system cache removed again, archive kept)'):
        other = by[label].get('report', {})
        if other.get('strictRender', {}).get('misses', 1) or (other.get('result') or {}).get('drawHash') != (reuse.get('result') or {}).get('drawHash'):
            failures.append(label + ': the archive does not serve every render pipeline with the same result')
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
