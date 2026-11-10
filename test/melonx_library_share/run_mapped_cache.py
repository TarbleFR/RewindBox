#!/usr/bin/env python3
"""Lot 9: the memory of a loaded MoltenVK pipeline cache, copied (shipped) against referenced in a read-only mapping
(candidate), on the macOS runner's real Metal device.

IPA 718 Hogwarts: the 790 MiB main pipeline cache stays in the process's anonymous memory after its load (MoltenVK copies
every library's compressed MSL out of the cache data), about 0.8 GiB of the 5.4-5.5 GiB footprint at 4 % device memory
available. The candidate patch (build-utils/melonx/moltenvk/rewindbox-moltenvk.patch, third part) lets RewindBox pass a
private pNext structure so the cache references the mapped file instead: clean file-backed pages, outside the footprint
and reclaimable by the system.

One candidate MoltenVK build (macOS): mvk_library_share_test mapsave builds a cache of MVK_BENCH_ROUNDS rounds of distinct
shaders and writes it; then, each in a new process, mapload-copy and mapload-reference map the file read-only, create the
cache, create every pipeline again with FAIL_ON_PIPELINE_COMPILE_REQUIRED and write the data back. Required for both:
no pipeline missing, no MSL compiled from SPIR-V again, the written data identical to the file. Recorded: the footprint
before, after the creation and after the pipelines, in both modes. Writes dist/melonx-mapped-cache/report.json.
macOS runner, not an iPhone (iOS counts the footprint the same way: phys_footprint).
"""
import hashlib, json, os, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
CANDIDATE = ROOT / 'build-utils/melonx/moltenvk-candidates/rewindbox-moltenvk-mapped.patch'
OUT = ROOT / 'dist/melonx-mapped-cache'
WORK = ROOT / '.mapped-cache'
SHADERS = ROOT / 'test/melonx_metal_binary_archive/shaders.spvz'
ROUNDS = os.environ.get('MVK_BENCH_ROUNDS', '40')


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
    target = WORK / 'MoltenVK'
    if not (target / '.git').exists():
        sh(['git', 'init', '-q', target])
        sh(['git', '-C', target, 'remote', 'add', 'origin', PIN['repository']])
    sh(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', PIN['revision']])
    sh(['git', '-C', target, 'checkout', '-q', '--force', '--detach', 'FETCH_HEAD'])
    sh(['git', '-C', target, 'apply', CANDIDATE])
    sh([target / 'fetchDependencies', '--macos'], cwd=target, log='fetchDependencies.log')
    sh(['make', 'macos'], cwd=target, log='make-macos.log')
    library = target / 'Package/Latest/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib'
    binary = OUT / 'mvk_library_share_test'
    sh(['clang++', '-std=c++17', '-O1', '-Wall', '-Wno-unused-function', '-I', target / 'Package/Latest/MoltenVK/include',
        HERE / 'mvk_library_share_test.cpp', library, '-lz', '-o', binary, '-Wl,-rpath,' + str(library.parent)], log='build-test.log')
    salt = int(os.environ.get('GITHUB_RUN_ID', str(int(time.time())))) % 1_000_000_007
    environment = dict(os.environ, MVK_CONFIG_PERFORMANCE_TRACKING='1', MVK_CONFIG_LOG_LEVEL='1', MVK_BENCH_ROUNDS=ROUNDS)
    results = {}
    for strategy in ('mapsave', 'mapload-copy', 'mapload-reference', 'mapload-copy', 'mapload-reference'):
        output = OUT / (strategy + '.json' if strategy == 'mapsave' else f'{strategy}-{len([k for k in results if k.startswith(strategy)])}.json')
        run = subprocess.run([str(binary), str(SHADERS), str(salt), str(output), strategy],
                             capture_output=True, text=True, timeout=3600, env=environment)
        if run.returncode:
            print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
            raise SystemExit(f'{strategy}: exit {run.returncode}')
        result = json.loads(output.read_text())
        results[output.stem] = result
        print(output.stem, json.dumps(result), flush=True)
        if strategy != 'mapsave':
            assert result['missing'] == 0, f'{strategy}: every pipeline is found in the loaded cache'
            assert result['mvkSpirvToMsl']['count'] == 0, f'{strategy}: nothing converted from SPIR-V again'
            # MoltenVK writes its entries back in its own order after a load (not the file's), so the check is the
            # size here and, below, the same bytes from both modes loading the same file.
            assert result['writeResult'] == 0 and result['bytes'] == results['mapsave']['bytes'], f'{strategy}: the data written back has the file size'
    copy = [r for k, r in results.items() if k.startswith('mapload-copy')]
    for k, r in results.items():
        if k.startswith('mapload-reference'):
            assert r['dataHash'] == copy[0]['dataHash'], 'referenced and copied loads of the same file write the same bytes'
    ref = [r for k, r in results.items() if k.startswith('mapload-reference')]
    summary = {mode: [round(r['footprintAfterPipelinesMiB'] - r['footprintBeforeMiB'], 1) for r in rs] for mode, rs in (('copy', copy), ('reference', ref))}
    report = {'identity': {'moltenvk': {k: PIN[k] for k in ('repository', 'tag', 'revision')},
                           'candidatePatch': {'path': CANDIDATE.relative_to(ROOT).as_posix(), 'sha256': sha(CANDIDATE)},
                           'library': {'sha256': sha(library), 'bytes': library.stat().st_size},
                           'test': sha(HERE / 'mvk_library_share_test.cpp'), 'shaders': sha(SHADERS), 'rounds': int(ROUNDS),
                           'xcode': sh(['xcodebuild', '-version']).splitlines()[:2], 'os': sh(['sw_vers']).split()},
              'footprintGrowthMiB': summary, 'results': results}
    (OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('footprint growth MiB (load + pipelines):', summary, flush=True)


if __name__ == '__main__':
    main()
