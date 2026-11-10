#!/usr/bin/env python3
"""Lot 9: the cost of MoltenVK's pipeline cache size query, shipped build against the candidate (macOS runner, real Metal).

RewindBox asks the main cache's data size during play (PipelineCacheManager.GetCacheDataSize; IPA 718 Hogwarts: 2 461 ms
for 4 667 entries, MoltenVK's own "Calculate pipeline cache size" 4 667 x 0.52 ms). MoltenVK v1.4.2 serializes every entry
again into a counting stream for each query after any change. The candidate patch
(build-utils/melonx/moltenvk/rewindbox-moltenvk.patch = the shipped drawable ownership patch + entry sizes counted once and
kept on each shader library) counts only new entries.

Both builds run mvk_library_share_test sizeprobe with the same salt: 8 rounds of distinct shaders in one cache, the size
asked after every creation. Required for each build: the data written into a buffer of the queried size returns
VK_SUCCESS with every byte used, a buffer 16 bytes short returns VK_INCOMPLETE, and the reloaded cache has the same size.
Across builds: the same size and the same data hash (the format is unchanged). Recorded: probe time in both builds.
Writes dist/melonx-cache-size/report.json. macOS runner, not an iPhone.
"""
import hashlib, json, os, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
SHIPPED = ROOT / PIN['patch']
CANDIDATE = ROOT / 'build-utils/melonx/moltenvk/rewindbox-moltenvk.patch'
OUT = ROOT / 'dist/melonx-cache-size'
WORK = ROOT / '.cache-size'
SHADERS = ROOT / 'test/melonx_metal_binary_archive/shaders.spvz'


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


def build(target, patch, name):
    sh(['git', '-C', target, 'checkout', '-q', '--force', '--detach', PIN['revision']])
    sh(['git', '-C', target, 'apply', patch])
    sh(['make', 'macos'], cwd=target, log=f'make-macos-{name}.log')
    library = target / 'Package/Latest/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib'
    kept = OUT / name
    kept.mkdir(parents=True, exist_ok=True)
    copy = kept / 'libMoltenVK.dylib'
    copy.write_bytes(library.read_bytes())
    binary = kept / 'mvk_library_share_test'
    sh(['clang++', '-std=c++17', '-O1', '-Wall', '-Wno-unused-function', '-I', target / 'Package/Latest/MoltenVK/include',
        HERE / 'mvk_library_share_test.cpp', copy, '-lz', '-o', binary, '-Wl,-rpath,' + str(kept)], log=f'build-test-{name}.log')
    return binary, copy


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert PIN['tag'] == 'v1.4.2' and sha(SHIPPED) == PIN['patchSha256'], 'the shipped patch is the pinned one'
    target = WORK / 'MoltenVK'
    if not (target / '.git').exists():
        sh(['git', 'init', '-q', target])
        sh(['git', '-C', target, 'remote', 'add', 'origin', PIN['repository']])
    sh(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', PIN['revision']])
    sh(['git', '-C', target, 'checkout', '-q', '--force', '--detach', 'FETCH_HEAD'])
    sh([target / 'fetchDependencies', '--macos'], cwd=target, log='fetchDependencies.log')
    salt = int(os.environ.get('GITHUB_RUN_ID', str(int(time.time())))) % 1_000_000_007
    environment = dict(os.environ, MVK_CONFIG_PERFORMANCE_TRACKING='1', MVK_CONFIG_LOG_LEVEL='1')
    results = {}
    for name, patch in (('shipped', SHIPPED), ('candidate', CANDIDATE)):
        binary, library = build(target, patch, name)
        runs = []
        for attempt in range(2):
            output = OUT / f'{name}-{attempt}.json'
            run = subprocess.run([str(binary), str(SHADERS), str(salt + attempt), str(output), 'sizeprobe'],
                                 capture_output=True, text=True, timeout=1800, env=environment)
            if run.returncode:
                print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
                raise SystemExit(f'{name}: exit {run.returncode}')
            result = json.loads(output.read_text())
            assert result['writeResult'] == 0 and result['written'] == result['bytes'], f'{name}: the queried size is what is written'
            assert result['shortWriteResult'] == 5, f'{name}: a short buffer returns VK_INCOMPLETE'
            assert result['reloadedBytes'] == result['bytes'], f'{name}: the reloaded cache has the same size'
            runs.append(result)
            print(name, attempt, json.dumps({k: result[k] for k in ('pipelines', 'probes', 'bytes', 'dataHash')}), flush=True)
        results[name] = {'library': {'sha256': sha(library), 'bytes': library.stat().st_size}, 'runs': runs}
    for attempt in range(2):
        a, b = results['shipped']['runs'][attempt], results['candidate']['runs'][attempt]
        assert a['bytes'] == b['bytes'] and a['dataHash'] == b['dataHash'], f'attempt {attempt}: same size and bytes in both builds'
    report = {'identity': {'moltenvk': {k: PIN[k] for k in ('repository', 'tag', 'revision')},
                           'shippedPatch': {'path': PIN['patch'], 'sha256': sha(SHIPPED)},
                           'candidatePatch': {'path': CANDIDATE.relative_to(ROOT).as_posix(), 'sha256': sha(CANDIDATE)},
                           'test': sha(HERE / 'mvk_library_share_test.cpp'), 'shaders': sha(SHADERS),
                           'xcode': sh(['xcodebuild', '-version']).splitlines()[:2], 'os': sh(['sw_vers']).split()},
              'results': results}
    (OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    for name in results:
        print(name, [r['probes'] for r in results[name]['runs']], flush=True)


if __name__ == '__main__':
    main()
