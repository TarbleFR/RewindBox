#!/usr/bin/env python3
"""Lot 8: MoltenVK v1.4.2 (the revision MeloNX embeds, unpatched) built for macOS, and mvk_library_share_test run on the
runner's real Metal device with each library publication strategy, each strategy twice with salts no other run uses
(Metal sources never compiled on this machine). Writes dist/melonx-library-share/report.json. Fails only when the
program cannot run or MoltenVK's statistics are missing; every measured value is recorded.
"""
import hashlib, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
OUT = ROOT / 'dist/melonx-library-share'
WORK = ROOT / '.library-share'
SHADERS = ROOT / 'test/melonx_metal_binary_archive/shaders.spvz'
STRATEGIES = ['none', 'one', 'merge', 'reset', 'every8', 'concurrent']


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
    assert sh(['git', '-C', target, 'rev-parse', 'HEAD']).strip() == PIN['revision'], 'not the pinned MoltenVK revision'
    assert PIN['patch'] is None, 'MeloNX MoltenVK carries no patch'
    assert sh(['git', '-C', target, 'status', '--porcelain']).strip() == '', 'unpatched source'
    sh([target / 'fetchDependencies', '--macos'], cwd=target, log='fetchDependencies.log')
    sh(['make', 'macos'], cwd=target, log='make-macos.log')
    package = target / 'Package/Latest/MoltenVK'
    library = package / 'dynamic/dylib/macOS/libMoltenVK.dylib'
    binary = OUT / 'mvk_library_share_test'
    sh(['clang++', '-std=c++17', '-O1', '-Wall', '-Wno-unused-function', '-I', package / 'include', HERE / 'mvk_library_share_test.cpp',
        library, '-lz', '-o', binary, '-Wl,-rpath,' + str(library.parent)], log='build-test.log')
    base = int(os.environ.get('GITHUB_RUN_ID', str(int(time.time())))) % 1_000_000_007
    environment = dict(os.environ, MVK_CONFIG_PERFORMANCE_TRACKING='1', MVK_CONFIG_LOG_LEVEL='1')
    runs = []
    for round_index in range(2):
        for index, strategy in enumerate(STRATEGIES):
            salt = base + 100 * round_index + index
            output = OUT / f'{strategy}-{round_index}.json'
            run = subprocess.run(['/usr/bin/time', '-l', str(binary), str(SHADERS), str(salt), str(output), strategy],
                                 capture_output=True, text=True, timeout=1800, env=environment)
            if run.returncode:
                print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
                raise SystemExit(f'{strategy}: exit {run.returncode}')
            result = json.loads(output.read_text())
            peak = [line for line in run.stderr.splitlines() if 'peak memory footprint' in line]
            result['peakFootprintMiB'] = round(int(peak[0].split()[0]) / 1048576, 1) if peak else None
            result['round'], result['salt'] = round_index, salt
            assert 'mvkMslCompile' in result, 'MoltenVK statistics missing'
            if strategy == 'concurrent':
                assert result['overlappingOwnPairs'] >= 12, 'the concurrent scenario did not overlap its own compilations'
            runs.append(result)
            print(strategy, round_index, json.dumps({k: result.get(k) for k in ('mainHits', 'ownCompiles', 'merges', 'peakFootprintMiB')}),
                  'msl', result['mvkMslCompile'], 'spirv', result['mvkSpirvToMsl']['count'], flush=True)
    identity = {'moltenvk': {k: PIN[k] for k in ('repository', 'tag', 'revision')}, 'patch': None,
                'library': {'sha256': sha(library), 'bytes': library.stat().st_size},
                'test': sha(HERE / 'mvk_library_share_test.cpp'), 'shaders': sha(SHADERS),
                'xcode': sh(['xcodebuild', '-version']).splitlines()[:2],
                'os': sh(['sw_vers']).split()}
    (OUT / 'report.json').write_text(json.dumps({'identity': identity, 'runs': runs}, indent=1) + '\n')


if __name__ == '__main__':
    main()
