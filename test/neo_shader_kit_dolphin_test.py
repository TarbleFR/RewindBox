#!/usr/bin/env python3
"""Dolphin post-processing shaders checked like the embedded core uses them (macOS CI).

    test/neo_shader_kit_dolphin_test.py --dolphin-ios CHECKOUT [--extra LABEL=DIR ...]
        [--build-directory DIR] [--verdicts FILE]

For the official shaders of the Sys folder the application ships
(Data/Sys/Shaders of the pinned DolphiniOS revision) and for the extra
folders named (shaders a player may import, e.g. a Mattias CRT port at a
pinned commit: they are checked, never packaged):

1. NeoStation's reproduction of Dolphin's Metal pipeline translates the
   file (neoshader-tool dolphin: Dolphin's header, uniform block and
   GLSL -> SPIR-V -> MSL settings, iOS platform);
2. both MSL stages compile with the iPhone Metal compiler
   (xcrun -sdk iphoneos metal);
3. neoshader-dolphin-validate draws it through Dolphin's post-processing
   interface on the macOS Metal device (one triangle, Dolphin's uniform
   buffer and texture array) for three frames of a moving picture and
   compares the result with Dolphin's picture without an effect.

The verdicts of every file are written with --verdicts (the format
tools/shaders/build_dolphin_catalog.py reads with --metal-results). The
test fails when an entry of packages/neo_shader_kit/ios/Resources/
dolphin-catalog.json does not pass all three steps with the very file the
catalog pins; the other failures are listed (FAIL lines) for the
catalog's diagnostics.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'packages/neo_shader_kit/tools'
CATALOG = ROOT / 'packages/neo_shader_kit/ios/Resources/dolphin-catalog.json'
DOLPHIN_COMMIT = '7cac54161659421ed95c2cd1c0b0746539a4cd38'
SHADERS = 'Data/Sys/Shaders'
DEFAULT_SHADER = 'default_pre_post_process.glsl'
# The translator emits MSL 2.3; newer standards accept it.
IOS_STANDARDS = ('ios-metal2.3', 'ios-metal2.4', 'metal2.4')
GPU_ERROR_EXIT = 4


def run(*arguments, **options):
    print('+', ' '.join(str(argument) for argument in arguments), flush=True)
    return subprocess.run([str(argument) for argument in arguments], **options)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metal_compile(source, standard):
    result = subprocess.run(['xcrun', '-sdk', 'iphoneos', 'metal', f'-std={standard}', '-c', str(source), '-o',
                             str(source.with_suffix('.air'))], capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def ios_compile(tool, file, directory):
    """neoshader-tool dolphin (iOS MSL), then the iPhone Metal compiler on both stages."""
    directory.mkdir(parents=True)
    result = subprocess.run([str(tool), 'dolphin', str(file), '--msl', str(directory)], capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    record = json.loads(lines[-1]) if lines else {'ok': False, 'error': {'code': 'TOOL_FAILED',
                                                                         'detail': result.stderr[-500:]}}
    if not record['ok']:
        return 'ios-translate', record['error']['code'], record['error']['detail']
    for stage in ('fragment', 'vertex'):
        log = ''
        for standard in IOS_STANDARDS:
            compiled, log = metal_compile(directory / f'{stage}.metal', standard)
            if compiled:
                break
        else:
            return 'ios-metal', 'IOS_METAL_COMPILE', f'{stage}: {log[:1500]}'
    return None


def render(validator, files, temporary):
    """neoshader-dolphin-validate, a new process after a GPU error."""
    results = {}
    output = temporary / 'dolphin.jsonl'
    remaining = [str(file) for file in files]
    while remaining:
        listing = temporary / 'dolphin-list.txt'
        listing.write_text('\n'.join(remaining) + '\n', encoding='utf-8')
        before = len(results)
        try:
            process = run(validator, listing, output, timeout=900)
            outcome = f'exit {process.returncode}'
            if process.returncode in (2, 3):
                raise SystemExit('neoshader-dolphin-validate cannot run (no Metal device or bad arguments)')
        except subprocess.TimeoutExpired:
            outcome = 'timeout'
            process = None
        if output.exists():
            for line in output.read_text(encoding='utf-8').splitlines():
                record = json.loads(line)
                results[record['file']] = record
        if len(results) == before or (process is not None and process.returncode not in (0, 1, GPU_ERROR_EXIT)) \
                or outcome == 'timeout':
            stuck = next((file for file in remaining if file not in results), None)
            if stuck is not None and stuck not in results:
                results[stuck] = {'file': stuck, 'ok': False, 'stage': 'render',
                                  'code': 'VALIDATOR_TIMEOUT' if outcome == 'timeout' else 'VALIDATOR_CRASH',
                                  'detail': outcome}
                with output.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(results[stuck]) + '\n')
        remaining = [file for file in remaining if file not in results]
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dolphin-ios', type=Path, required=True)
    parser.add_argument('--extra', action='append', default=[], help='LABEL=DIR of .glsl files a player may import')
    parser.add_argument('--build-directory', type=Path)
    parser.add_argument('--verdicts', type=Path)
    arguments = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('The Dolphin shader validation runs on macOS.')
    checkout = arguments.dolphin_ios.resolve()
    head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                          text=True).stdout.strip()
    if head != DOLPHIN_COMMIT:
        raise SystemExit(f'dolphin-ios checkout is {head}, the delivery pins {DOLPHIN_COMMIT}')
    shaders = checkout / SHADERS
    # Keys: the path under Sys/Shaders for official files, LABEL/path for extras.
    files = {}
    for path in sorted(shaders.glob('*.glsl')):
        if path.name != DEFAULT_SHADER:
            files[path.name] = path
    extras = {}
    for item in arguments.extra:
        label, _, folder = item.partition('=')
        folder = Path(folder).resolve()
        for path in sorted(folder.rglob('*.glsl')):
            key = f'{label}/{path.relative_to(folder).as_posix()}'
            files[key] = path
            extras[key] = label

    with tempfile.TemporaryDirectory(prefix='neo-dolphin-shaders-') as temporary:
        temporary = Path(temporary)
        build = arguments.build_directory or temporary / 'build'
        jobs = str(os.cpu_count() or 2)
        run('cmake', '-S', TOOLS, '-B', build, '-DCMAKE_BUILD_TYPE=Release', check=True)
        run('cmake', '--build', build, '--parallel', jobs, '--target', 'neoshader-tool', 'neoshader-dolphin-validate',
            check=True)
        ios = {}
        for index, (key, path) in enumerate(files.items()):
            failure = ios_compile(build / 'neoshader-tool', path, temporary / f'msl-{index}')
            if failure is not None:
                ios[key] = failure
        rendered = render(build / 'neoshader-dolphin-validate', list(files.values()), temporary)

    verdicts, failures = {}, []
    for key, path in files.items():
        record = rendered.get(str(path), {'ok': False, 'stage': 'render', 'code': 'NOT_VALIDATED', 'detail': ''})
        if key in ios:
            stage, code, detail = ios[key]
        elif not record['ok']:
            stage, code, detail = record['stage'], record['code'], record.get('detail', '')
        else:
            stage = code = detail = ''
        verdict = {'status': 'failed' if code else 'rendered', 'sha256': sha256(path), 'size': path.stat().st_size}
        if code:
            verdict.update({'stage': stage, 'code': code, 'detail': detail[:300]})
            failures.append((stage, key, code, detail))
        for field in ('options', 'uniformBytes', 'compileSeconds', 'gpuMilliseconds', 'changedFraction',
                      'meanDifference', 'litFraction', 'colors'):
            if field in record:
                verdict[field] = record[field]
        if key in extras:
            verdict['source'] = extras[key]
        verdicts[key] = verdict
        print(f'{"ok  " if not code else "FAIL"} {key} {code} changed={record.get("changedFraction", 0):.4f} '
              f'gpu={record.get("gpuMilliseconds", 0):.3f}ms', flush=True)

    environment = (f'macOS {platform.mac_ver()[0]} Metal draw through Dolphin\'s post-processing interface + iPhone '
                   f'Metal compiler, GitHub run {os.environ.get("GITHUB_RUN_ID", "local")}')
    if arguments.verdicts:
        arguments.verdicts.parent.mkdir(parents=True, exist_ok=True)
        arguments.verdicts.write_text(json.dumps({'schema': 1, 'dolphinRevision': DOLPHIN_COMMIT,
                                                  'environment': environment, 'files': verdicts}, indent=1) + '\n',
                                      encoding='utf-8')
    for stage, key, code, detail in failures:
        first = detail.splitlines()[0][:200] if detail else ''
        print(f'FAIL {stage} {key} {code} {first}', flush=True)

    problems = []
    catalog = json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else None
    if catalog is None:
        problems.append('dolphin-catalog.json is missing')
    else:
        if catalog['source']['commit'] != DOLPHIN_COMMIT:
            problems.append(f'the catalog pins {catalog["source"]["commit"]}')
        for entry in catalog['entries']:
            path_in_sys, size, digest = catalog['files'][entry['files'][0]]
            key = path_in_sys.split('/', 1)[1]
            verdict = verdicts.get(key)
            if verdict is None:
                problems.append(f'{entry["id"]}: no such official shader')
            elif verdict['sha256'] != digest or verdict['size'] != size:
                problems.append(f'{entry["id"]}: the shipped file differs from the catalog')
            elif entry['validation'] == 'rendered' and verdict['status'] != 'rendered':
                problems.append(f'{entry["id"]}: {verdict["code"]}')
            elif entry['validation'] == 'translated' and verdict.get('stage') in ('ios-translate', 'ios-metal'):
                problems.append(f'{entry["id"]}: {verdict["code"]}')
    rendered_count = sum(1 for verdict in verdicts.values() if verdict['status'] == 'rendered')
    print(f'{len(files)} Dolphin shaders: {rendered_count} rendered, {len(failures)} failed', flush=True)
    for problem in problems:
        print('CATALOG', problem, flush=True)
    if problems:
        raise SystemExit(f'{len(problems)} catalog entries are not what the application can offer')
    print('PASS: every catalog entry translates, compiles for iPhone and draws visibly through Dolphin\'s interface',
          flush=True)


if __name__ == '__main__':
    main()
