#!/usr/bin/env python3
"""Every entry of NeoStation's slang catalog, checked against the pinned repository (macOS CI).

    test/neo_shader_kit_catalog_test.py --slang-shaders CHECKOUT [--build-directory DIR] [--verdicts FILE]

For packages/neo_shader_kit/ios/Resources/slang-catalog.json:

1. the checkout is the commit the catalog pins, and every listed file has
   the size and SHA-256 the catalog records (what the application will
   download and verify);
2. every entry translates for iOS with the application's core
   (neoshader-tool, SPIRV-Cross iOS platform) and every distinct MSL source
   compiles with the iPhone Metal compiler (xcrun -sdk iphoneos metal);
3. every entry goes through the application's Metal runtime on the macOS
   device (neoshader-metal-validate: NeoSlangRenderer.mm compiles it,
   renders three frames of a moving picture, reads the result back) and
   must visibly change the picture compared with a plain nearest upscale.

The presets of each later addition ("additions" of the catalog) get the
same three checks against the commit that addition pins, fetched here.

A catalog entry is offered as "rendered" only because this test passes on
it. Failures are listed one per line ("FAIL <stage> <preset> <code>
<detail>") so they can be excluded from the catalog with their reason; the
verdicts of every entry can be written as JSON (--verdicts) in the format
tools/shaders/build_slang_catalog.py reads with --metal-results.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'packages/neo_shader_kit/ios/Resources/slang-catalog.json'
TOOLS = ROOT / 'packages/neo_shader_kit/tools'
IOS_STANDARDS = ('ios-metal2.4', 'metal2.4')
# One validator process handles this many presets; a crash or a hang only
# costs the preset being validated, recorded as such.
CHUNK = 60
CHUNK_TIMEOUT = 900
# neoshader-metal-validate stops after a GPU error (timeout, hang).
GPU_ERROR_EXIT = 4


def run(*arguments, **options):
    print('+', ' '.join(str(argument) for argument in arguments), flush=True)
    return subprocess.run([str(argument) for argument in arguments], **options)


def check_files(catalog, checkout):
    problems = []
    for path, size, digest in catalog['files']:
        file = checkout / path
        if not file.is_file():
            problems.append(f'{path}: missing')
            continue
        data = file.read_bytes()
        if len(data) != size:
            problems.append(f'{path}: {len(data)} bytes, catalog says {size}')
        elif hashlib.sha256(data).hexdigest() != digest:
            problems.append(f'{path}: SHA-256 differs from the catalog')
    return problems


def addition_checkout(checkout, source):
    """The repository at the commit a later addition pins, fetched next to the first checkout."""
    target = checkout.with_name(f'{checkout.name}-{source["commit"][:12]}')
    if not (target / '.git').exists():
        run('git', 'init', '-q', target, check=True)
        run('git', '-C', target, 'fetch', '-q', '--depth', '1', source['repository'], source['commit'], check=True)
        run('git', '-C', target, 'checkout', '-q', 'FETCH_HEAD', check=True)
    head = subprocess.run(['git', '-C', str(target), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                          text=True).stdout.strip()
    if head != source['commit']:
        raise SystemExit(f'addition checkout is {head}, the catalog pins {source["commit"]}')
    return target


def metal_compile(source, standard):
    result = subprocess.run(['xcrun', '-sdk', 'iphoneos', 'metal', f'-std={standard}', '-c', str(source), '-o',
                             str(source.with_suffix('.air'))], capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def ios_standard(probe):
    log = ''
    for standard in IOS_STANDARDS:
        compiled, log = metal_compile(probe, standard)
        if compiled:
            return standard, log
    return None, log


def validate_ios(tool, checkout, presets, temporary, jobs):
    """iOS translation, then the iPhone Metal compiler on each distinct MSL source."""
    listing = temporary / 'ios-presets.txt'
    listing.write_text('\n'.join(presets) + '\n', encoding='utf-8')
    tree = temporary / 'ios-msl'
    tree.mkdir()
    output = temporary / 'ios.jsonl'
    run(tool, 'slang-batch', checkout, listing, output, '--msl-tree', tree, check=True)
    verdicts, sources = {}, {}
    for line in output.read_text(encoding='utf-8').splitlines():
        record = json.loads(line)
        preset = record['preset']
        if not record['ok']:
            verdicts[preset] = ('ios-translate', record['error']['code'], record['error']['detail'])
            continue
        for vertex, fragment in record.get('msl', []):
            sources.setdefault(f'{vertex}.vertex.metal', []).append(preset)
            sources.setdefault(f'{fragment}.fragment.metal', []).append(preset)
    files = sorted(sources)
    if not files:
        return verdicts, None
    standard, log = ios_standard(tree / files[0])
    if standard is None:
        print(log, flush=True)
        run('xcodebuild', '-downloadComponent', 'MetalToolchain', check=False)
        standard, log = ios_standard(tree / files[0])
    if standard is None:
        raise SystemExit('No iPhone Metal compiler:\n' + log)
    print(f'Compiling {len(files)} distinct MSL sources with xcrun -sdk iphoneos metal -std={standard}', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        compiled = dict(zip(files, pool.map(lambda name: metal_compile(tree / name, standard), files)))
    for name, (ok, log) in compiled.items():
        if ok:
            continue
        for preset in sources[name]:
            verdicts.setdefault(preset, ('ios-metal', 'IOS_METAL_COMPILE', f'{name}: {log[:1500]}'))
    return verdicts, standard


def validate_metal(validator, checkout, presets, temporary):
    """Runs the validator in chunks; a preset whose process died is recorded."""
    results = {}
    output = temporary / 'metal.jsonl'
    remaining = list(presets)
    while remaining:
        chunk = remaining[:CHUNK]
        listing = temporary / 'metal-chunk.txt'
        listing.write_text('\n'.join(chunk) + '\n', encoding='utf-8')
        before = len(results)
        restart = False
        try:
            process = run(validator, checkout, listing, output, timeout=CHUNK_TIMEOUT)
            outcome = f'exit {process.returncode}'
            if process.returncode in (2, 3):
                raise SystemExit('neoshader-metal-validate cannot run (no Metal device or bad arguments)')
            # After a GPU error the preset that caused it has its result and
            # macOS would ignore this process's later GPU work: a new process
            # takes the presets left.
            restart = process.returncode == GPU_ERROR_EXIT
        except subprocess.TimeoutExpired:
            outcome = 'timeout'
        for line in output.read_text(encoding='utf-8').splitlines():
            record = json.loads(line)
            results[record['preset']] = record
        done = [preset for preset in chunk if preset in results]
        if len(results) == before or (len(done) < len(chunk) and not restart):
            # The process stopped on the first preset without a result.
            stuck = next(preset for preset in chunk if preset not in results)
            if outcome == 'timeout':
                code = 'VALIDATOR_TIMEOUT'
            elif outcome in ('exit 0', 'exit 1'):
                code = 'VALIDATOR_STOPPED'
            else:
                code = 'VALIDATOR_CRASH'
            results[stuck] = {'preset': stuck, 'ok': False, 'stage': 'render', 'code': code, 'detail': outcome}
            with output.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(results[stuck]) + '\n')
        remaining = [preset for preset in remaining if preset not in results]
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--slang-shaders', type=Path, required=True)
    parser.add_argument('--build-directory', type=Path)
    parser.add_argument('--verdicts', type=Path, help='write every verdict (JSON, --metal-results format)')
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 2)
    arguments = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('The catalog Metal validation runs on macOS.')

    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    checkout = arguments.slang_shaders.resolve()
    head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                          text=True).stdout.strip()
    commit = catalog['source']['commit']
    if head != commit:
        raise SystemExit(f'slang-shaders checkout is {head}, the catalog pins {commit}')
    # The catalog's own source, then each later addition against its own pinned commit.
    sources = [(commit, checkout, catalog)]
    for addition in catalog.get('additions', []):
        sources.append((addition['source']['commit'], addition_checkout(checkout, addition['source']), addition))
    for source_commit, source_checkout, layer in sources:
        problems = check_files(layer, source_checkout)
        for problem in problems:
            print('FILE', problem, flush=True)
        if problems:
            raise SystemExit(f'{len(problems)} catalog files differ from the pinned repository at {source_commit}')
        print(f'{len(layer["files"])} catalog files match {source_commit}', flush=True)

    total = failed = 0
    with tempfile.TemporaryDirectory(prefix='neo-shader-catalog-') as temporary:
        temporary = Path(temporary)
        build = arguments.build_directory or temporary / 'build'
        run('cmake', '-S', TOOLS, '-B', build, '-DCMAKE_BUILD_TYPE=Release', check=True)
        run('cmake', '--build', build, '--parallel', str(arguments.jobs), '--target', 'neoshader-tool',
            'neoshader-metal-validate', check=True)
        for index, (source_commit, source_checkout, layer) in enumerate(sources):
            presets = [entry['id'] for entry in layer['entries']]
            work = temporary / f'source-{index}'
            work.mkdir()
            started = time.monotonic()
            ios, standard = validate_ios(build / 'neoshader-tool', source_checkout, presets, work, arguments.jobs)
            ios_seconds = time.monotonic() - started
            started = time.monotonic()
            metal = validate_metal(build / 'neoshader-metal-validate', source_checkout, presets, work)
            metal_seconds = time.monotonic() - started

            verdicts, failures = {}, []
            for preset in presets:
                record = metal.get(preset, {'ok': False, 'stage': 'render', 'code': 'NOT_VALIDATED', 'detail': ''})
                if preset in ios:
                    stage, code, detail = ios[preset]
                elif not record['ok']:
                    stage, code, detail = record['stage'], record['code'], record.get('detail', '')
                else:
                    stage = code = detail = ''
                status = 'rendered' if not code else 'failed'
                verdict = {'status': status}
                if code:
                    verdict.update({'stage': stage, 'code': code, 'detail': detail[:300]})
                    failures.append((stage, preset, code, detail))
                for key in ('passes', 'compileSeconds', 'gpuMilliseconds', 'changedFraction', 'meanDifference',
                            'litFraction', 'colors'):
                    if key in record:
                        verdict[key] = record[key]
                verdicts[preset] = verdict

            for stage, preset, code, detail in failures:
                first = detail.splitlines()[0][:200] if detail else ''
                print(f'FAIL {stage} {preset} {code} {first}', flush=True)
            # One line per entry of an addition: a log is enough to transcribe its verdicts.
            if index:
                for preset in presets:
                    print(f'VERDICT {source_commit[:12]} {preset} {verdicts[preset]["status"]}', flush=True)
            environment = (f'macOS {platform.mac_ver()[0]} Metal render + iPhone Metal compiler '
                           f'(-std={standard}), GitHub run {os.environ.get("GITHUB_RUN_ID", "local")}')
            if arguments.verdicts:
                # The catalog's own source keeps the given name; an addition adds its commit to it.
                target = arguments.verdicts if not index else arguments.verdicts.with_name(
                    f'{arguments.verdicts.stem}-{source_commit[:12]}{arguments.verdicts.suffix}')
                target.write_text(json.dumps({'schema': 1, 'slangCommit': source_commit, 'environment': environment,
                                              'presets': verdicts}, indent=1) + '\n', encoding='utf-8')
            print(f'{source_commit[:12]}: {len(presets)} catalog entries: {len(presets) - len(failures)} rendered, '
                  f'{len(failures)} failed (iOS translation and Metal compile {ios_seconds:.0f} s, '
                  f'Metal render {metal_seconds:.0f} s)', flush=True)
            total += len(presets)
            failed += len(failures)
    if failed:
        raise SystemExit(1)
    print(f'PASS: every catalog entry ({total}) compiles for iPhone and renders visibly with Metal', flush=True)


if __name__ == '__main__':
    main()
