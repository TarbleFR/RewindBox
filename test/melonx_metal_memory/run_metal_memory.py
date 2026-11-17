#!/usr/bin/env python3
"""What a Vulkan image costs in Metal memory under MoltenVK, depth and stencil against color (macOS runner).

IPA 773, Hogwarts Legacy courtyard: MoltenVK's "GPU memory allocated" (MTLDevice currentAllocatedSize) rose from 718 MB
to 1 356 MB in 27 s and stayed there, while the engine's Vulkan device memory stayed at 679-766 MiB. MeloNX gives every
image its own VkDeviceMemory without a dedicated-allocation structure; MoltenVK v1.4.2 then makes a placement MTLHeap
of that size at vkAllocateMemory and places the image's texture in it, except for a depth or stencil image, whose texture
it creates from the device next to the heap. mvk_metal_memory.mm measures it on the runner's Metal device for 16
images of 1024 x 1024 per case (depth and stencil, depth, 16-bit depth, color; depth and stencil and color again with a
dedicated allocation), after the binds, after a first use (a clear, submitted and waited for, its content read back)
and after everything is freed.

MoltenVK v1.4.2 with the pinned recipe patch (build-utils/melonx/moltenvk/rewindbox-moltenvk.patch) is built for macOS.
When test/melonx_metal_memory/baseline.json names a patch other than the pinned one, both are built on the same
checkout and measured alternately, three times each; the report gives each case's medians per build. Writes
dist/melonx-metal-memory/report.json. macOS runner, not an iPhone: the runner's Metal device is recorded.
"""
import hashlib, json, os, statistics, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
PATCH = ROOT / PIN['patch']
OUT = ROOT / 'dist/melonx-metal-memory'
WORK = ROOT / '.metal-memory'
BASELINE = json.loads((HERE / 'baseline.json').read_text())
BASELINE_PATCH = ROOT / 'baseline' / BASELINE['patch']
NUMBERS = ('requirementMiB', 'allocatedAfterBindMiB', 'allocatedAfterUseMiB', 'allocatedAfterFreeMiB',
           'footprintAfterBindMiB', 'footprintAfterUseMiB', 'footprintAfterFreeMiB', 'allocatedPerImageOverRequirement')


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
    binary = folder / 'mvk_metal_memory'
    sh(['clang++', '-std=c++17', '-O2', '-Wall', '-x', 'objective-c++', '-I', target / 'Package/Latest/MoltenVK/include',
        HERE / 'mvk_metal_memory.mm', '-x', 'none', library, '-framework', 'Metal', '-framework', 'Foundation', '-o', binary,
        '-Wl,-rpath,' + str(folder)], log=f'build-test-{name}.log')
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
    result = json.loads(output.read_text())
    text = run.stdout + run.stderr
    result['gpuModel'] = next((line.split('model:', 1)[1].strip() for line in text.splitlines() if 'model:' in line), None)
    print(name, attempt, json.dumps(result), flush=True)
    return result


def medians(runs):
    out = []
    for index, case in enumerate(runs[0]['cases']):
        merged = {key: case[key] for key in ('name', 'format', 'dedicated', 'supported')}
        merged['contentMatches'] = all(run['cases'][index]['contentMatches'] for run in runs)
        for key in NUMBERS:
            merged[key] = statistics.median(run['cases'][index][key] for run in runs)
        out.append(merged)
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
    report = {'identity': {'moltenvk': {k: PIN[k] for k in ('repository', 'tag', 'revision')},
                           'patch': {'path': PATCH.relative_to(ROOT).as_posix(), 'sha256': sha(PATCH)},
                           'baseline': {'commit': BASELINE['commit'], 'sha256': BASELINE['patchSha256']} if compare else None,
                           'test': sha(HERE / 'mvk_metal_memory.mm'),
                           'libraries': {name: sha(library) for name, (library, _) in builds.items()},
                           'xcode': sh(['xcodebuild', '-version']).splitlines()[:2], 'os': sh(['sw_vers']).split()},
              'device': runs['candidate'][0]['device'], 'gpuModel': runs['candidate'][0]['gpuModel'],
              'placementHeaps': runs['candidate'][0]['placementHeaps'],
              'order': 'baseline then candidate, alternately, three times' if compare else 'candidate, three times',
              'medians': summary, 'runs': runs}
    (OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'device': report['device'], 'placementHeaps': report['placementHeaps'], 'medians': summary}, indent=1), flush=True)


if __name__ == '__main__':
    main()
