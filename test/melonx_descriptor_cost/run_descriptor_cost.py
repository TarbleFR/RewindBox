#!/usr/bin/env python3
"""Lot 9: what a texture descriptor set write costs in MoltenVK, against binding one already written (macOS runner).

IPA 718 Hogwarts in play: the render thread's draw descriptors take 9.6 ms per frame and compute descriptors 3.1 ms;
its counters give 5.39 M descriptors written per 5 s (63 517 texture sets, about 74 descriptors each). MoltenVK v1.4.2
with the pinned recipe patch (build-utils/melonx/moltenvk/rewindbox-moltenvk.patch) is built for macOS and
mvk_descriptor_cost.cpp measures, for sets of 8, 32 and 74 combined image samplers: template writes (alternating
contents, repeated content), plain writes, and binds of an already written set. Required: the device reports Metal3
argument buffers as on the iPhone. Writes dist/melonx-descriptor-cost/report.json. macOS runner, not an iPhone.
"""
import hashlib, json, os, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
PATCH = ROOT / PIN['patch']
OUT = ROOT / 'dist/melonx-descriptor-cost'
WORK = ROOT / '.descriptor-cost'


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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert PIN['tag'] == 'v1.4.2' and sha(PATCH) == PIN['patchSha256'], 'the pinned recipe patch'
    target = WORK / 'MoltenVK'
    if not (target / '.git').exists():
        sh(['git', 'init', '-q', target])
        sh(['git', '-C', target, 'remote', 'add', 'origin', PIN['repository']])
    sh(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', PIN['revision']])
    sh(['git', '-C', target, 'checkout', '-q', '--force', '--detach', 'FETCH_HEAD'])
    sh(['git', '-C', target, 'apply', PATCH])
    sh([target / 'fetchDependencies', '--macos'], cwd=target, log='fetchDependencies.log')
    sh(['make', 'macos'], cwd=target, log='make-macos.log')
    library = OUT / 'libMoltenVK.dylib'
    library.write_bytes((target / 'Package/Latest/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib').read_bytes())
    binary = OUT / 'mvk_descriptor_cost'
    sh(['clang++', '-std=c++17', '-O2', '-Wall', '-I', target / 'Package/Latest/MoltenVK/include', HERE / 'mvk_descriptor_cost.cpp',
        library, '-o', binary, '-Wl,-rpath,' + str(OUT)], log='build-test.log')
    environment = dict(os.environ, MVK_CONFIG_LOG_LEVEL='3')
    runs = []
    for attempt in range(3):
        output = OUT / f'run-{attempt}.json'
        run = subprocess.run([str(binary), str(output)], capture_output=True, text=True, timeout=1800, env=environment)
        (OUT / f'run-{attempt}.log').write_text(run.stdout + run.stderr)
        if run.returncode:
            print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
            raise SystemExit(f'exit {run.returncode}')
        if attempt == 0:
            assert 'Metal3 argument buffers' in run.stdout + run.stderr, 'MoltenVK must use Metal3 argument buffers, as on the iPhone'
        runs.append(json.loads(output.read_text()))
        print(attempt, json.dumps(runs[-1]), flush=True)
    report = {'identity': {'moltenvk': {k: PIN[k] for k in ('repository', 'tag', 'revision')},
                           'patch': {'path': PATCH.relative_to(ROOT).as_posix(), 'sha256': sha(PATCH)},
                           'test': sha(HERE / 'mvk_descriptor_cost.cpp'), 'library': sha(library),
                           'xcode': sh(['xcodebuild', '-version']).splitlines()[:2], 'os': sh(['sw_vers']).split()},
              'runs': runs}
    (OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main()
