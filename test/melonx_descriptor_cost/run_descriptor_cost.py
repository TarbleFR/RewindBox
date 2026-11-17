#!/usr/bin/env python3
"""Lot 9: what a texture descriptor set write costs in MoltenVK, against binding one already written (macOS runner).

IPA 718 Hogwarts in play: the render thread's draw descriptors take 9.6 ms per frame and compute descriptors 3.1 ms;
its counters give 5.39 M descriptors written per 5 s (63 517 texture sets, about 74 descriptors each). MoltenVK v1.4.2
with the pinned recipe patch (build-utils/melonx/moltenvk/rewindbox-moltenvk.patch) is built for macOS and
mvk_descriptor_cost.cpp measures, for sets of 8, 32 and 74 combined image samplers: template writes (alternating
contents, repeated content), plain writes, and binds of an already written set. Required: the device reports Metal3
argument buffers as on the iPhone. Writes dist/melonx-descriptor-cost/report.json. macOS runner, not an iPhone.

17 Nov (recipe patch, seventh part): when test/melonx_descriptor_cost/baseline.json names a patch other than the pinned
one, both are built in this job on the same checkout and dependencies (the baseline from that commit, checked out by
the workflow in baseline/), and the measure runs alternately on each build, three times; the report gives each field's
median per build and the candidate's ratio to the baseline.
"""
import hashlib, json, os, statistics, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
PATCH = ROOT / PIN['patch']
OUT = ROOT / 'dist/melonx-descriptor-cost'
WORK = ROOT / '.descriptor-cost'
BASELINE = json.loads((HERE / 'baseline.json').read_text())
BASELINE_PATCH = ROOT / 'baseline' / BASELINE['patch']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sh(args, cwd=None, log=None):
    start = time.time()
    result = subprocess.run([str(a) for a in args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    if log:
        (OUT / log).write_text(result.stdout)
    print(f"$ {' '.join(str(a) for a in args)}  [{result.returncode}, {time.time() - start:.0f} s]", flush=True)
    if result.returncode:
        print('\n'.join(result.stdout.splitlines()[-80:]), flush=True)
        raise SystemExit(f'{args[0]} failed')
    return result.stdout


def build_library(target, patch, name):
    sh(['git', '-C', target, 'apply', patch])
    sh(['make', 'macos'], cwd=target, log=f'make-macos-{name}.log')
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    library = folder / 'libMoltenVK.dylib'
    library.write_bytes((target / 'Package/Latest/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib').read_bytes())
    binary = folder / 'mvk_descriptor_cost'
    sh(['clang++', '-std=c++17', '-O2', '-Wall', '-I', target / 'Package/Latest/MoltenVK/include', HERE / 'mvk_descriptor_cost.cpp',
        library, '-o', binary, '-Wl,-rpath,' + str(folder)], log=f'build-test-{name}.log')
    sh(['git', '-C', target, 'apply', '-R', patch])
    return library, binary


def run_once(binary, name, attempt):
    environment = dict(os.environ, MVK_CONFIG_LOG_LEVEL='3')
    output = OUT / f'run-{name}-{attempt}.json'
    run = subprocess.run([str(binary), str(output)], capture_output=True, text=True, timeout=1800, env=environment)
    (OUT / f'run-{name}-{attempt}.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
        raise SystemExit(f'exit {run.returncode}')
    assert 'Metal3 argument buffers' in run.stdout + run.stderr, 'MoltenVK must use Metal3 argument buffers, as on the iPhone'
    result = json.loads(output.read_text())
    print(name, attempt, json.dumps(result), flush=True)
    return result


def medians(runs):
    """Each group's (sizes, viewSizes, buffers) fields, as the median of the runs."""
    out = {}
    for group in ('sizes', 'viewSizes', 'buffers'):
        rows = []
        for index, row in enumerate(runs[0].get(group, [])):
            merged = {'descriptors': row['descriptors']}
            for key in row:
                if key != 'descriptors':
                    merged[key] = statistics.median(run[group][index][key] for run in runs)
            rows.append(merged)
        out[group] = rows
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert PIN['tag'] == 'v1.4.2' and sha(PATCH) == PIN['patchSha256'], 'the pinned recipe patch'
    compare = BASELINE['patchSha256'] != PIN['patchSha256']
    if compare:
        assert BASELINE_PATCH.exists() and sha(BASELINE_PATCH) == BASELINE['patchSha256'], 'the baseline patch of baseline.json'
    target = WORK / 'MoltenVK'
    if not (target / '.git').exists():
        sh(['git', 'init', '-q', target])
        sh(['git', '-C', target, 'remote', 'add', 'origin', PIN['repository']])
    sh(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', PIN['revision']])
    sh(['git', '-C', target, 'checkout', '-q', '--force', '--detach', 'FETCH_HEAD'])
    sh([target / 'fetchDependencies', '--macos'], cwd=target, log='fetchDependencies.log')
    builds = {}
    if compare:
        builds['baseline'] = build_library(target, BASELINE_PATCH, 'baseline')
    builds['candidate'] = build_library(target, PATCH, 'candidate')
    runs = {name: [] for name in builds}
    for attempt in range(3):
        for name, (_, binary) in builds.items():
            runs[name].append(run_once(binary, name, attempt))
    summary = {name: medians(found) for name, found in runs.items()}
    ratios = {}
    if compare:
        for group in ('sizes', 'viewSizes', 'buffers'):
            ratios[group] = [{'descriptors': c['descriptors'],
                              **{key: round(c[key] / b[key], 3) for key in c if key != 'descriptors' and b[key]}}
                             for c, b in zip(summary['candidate'][group], summary['baseline'][group])]
    report = {'identity': {'moltenvk': {k: PIN[k] for k in ('repository', 'tag', 'revision')},
                           'patch': {'path': PATCH.relative_to(ROOT).as_posix(), 'sha256': sha(PATCH)},
                           'baseline': {'commit': BASELINE['commit'], 'sha256': BASELINE['patchSha256']} if compare else None,
                           'test': sha(HERE / 'mvk_descriptor_cost.cpp'),
                           'libraries': {name: sha(library) for name, (library, _) in builds.items()},
                           'xcode': sh(['xcodebuild', '-version']).splitlines()[:2], 'os': sh(['sw_vers']).split()},
              'order': 'baseline then candidate, alternately, three times' if compare else 'candidate, three times',
              'medians': summary, 'candidateOverBaseline': ratios, 'runs': runs}
    (OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'medians': summary, 'candidateOverBaseline': ratios}, indent=1), flush=True)


if __name__ == '__main__':
    main()
