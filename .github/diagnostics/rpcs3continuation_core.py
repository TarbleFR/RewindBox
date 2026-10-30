#!/usr/bin/env python3
"""Validate the 30 October continuation through the unchanged runtime592 recipe.

Only affected source-extracted programs execute on Apple ARM64. Historical
results retain their original scope; the new iPhone Core is compiled once by
the established workflow after this gate. No device/FPS result is implied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
OUT = ROOT / 'build/rpcs3-core-diagnostics'
PROOF = OUT / 'runtime592-proof.json'
GATE = '.github/diagnostics/rpcs3continuation_core.py'
ROUTE = '.github/diagnostics/rpcs3runtime592_core.py'
WORKFLOW = '.github/workflows/rpcs3-runtime592-core.yml'
BUILD = 'build-utils/build_rpcs3_embedded_core.sh'
MANIFEST = 'build-utils/rpcs3/canonical-source.json'
PATCH = 'build-utils/rpcs3/embedded-core.patch'
EVIDENCE = 'docs/evidence/rpcs3-continuation-20261030/'
RECORD = EVIDENCE + 'source-record.json'
CONTRACT = 'test/rpcs3_continuation_contract_test.py'
BASE = 'de8169848ecfa9c95946fc957861263a9fd1b879'
HIST = 'e97137b1d907b4c0b0c102435d55b1f96d891d38'
RUN = 40963062736
PATCH_SHA = '099651cae54c7bc567ff325735acde0cf3e931ed6e25b2b5bbcc14e5f5ecf33b'
RECORD_SHA = '12d321b8dd64164af40fd297dff520eec12d183723a6a9d95134909faae231d5'
HIST_PATCH = '5ba1424bcd40afc96f3263e236d84ed643cb7aac15cbcd1fb513e85d24e27ec8'
HIST_CORE = '9b0af4f1bae9daa3b0da1641682ef72e37b9cbe703ab4af8d9ca94a80c63d192'
HIST_IDENTITY = '12db3b29c38d3e16bd3440470a05e4f614b523c576291dd84f0095b552fa055c'
HIST_PROOF = 'd8e6bb907802225d99133065d810bcf8cee9e4814131218f4b52d61bd2a4e996'
ARCHIVES = {
    'core': (12937551950, 29286994, '9a4b8fa8a3a072ed80898e85416d71af464a0b60bb5786dfd6da1d51002dd3e9'),
    'diagnostics': (12938490405, 593953, 'cac2db7c91bbdefb27a596aa5bca50914f3f6aaa87ac7155494c5b061f36abe6'),
}
CODEGEN = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
ROUTE_BLOCK = '''    if 'continuation_20261030' in manifest():
        # Keep the established workflow and compiler recipe unchanged.
        import rpcs3continuation_core as continuation
        if a.write_core_identity:
            continuation.identity(a.write_core_identity)
        elif a.source and a.verify_reuse:
            continuation.verify(a.verify_reuse, a.source.resolve())
        elif a.source:
            continuation.prepare(a.source.resolve())
        else:
            p.error('continuation source requires --source or --write-core-identity')
        raise SystemExit
'''

# Conservatively retain only families whose complete production input files
# are unchanged. Tests touching a changed file remain historical, even when
# an individual old helper may be unchanged; they are not relabeled current.
UNCHANGED = {
    'array': ['rpcs3/Emu/RSX/Common/simple_array.hpp'],
    'coverage': ['rpcs3/Emu/RSX/Common/surface_store.h', 'Utilities/address_range.h'],
    'shader': ['rpcs3/Emu/RSX/Program/ShaderParam.h',
               'rpcs3/Emu/RSX/Program/VertexProgramDecompiler.cpp',
               'rpcs3/Emu/RSX/Program/FragmentProgramDecompiler.cpp', 'Utilities/StrUtil.h'],
    'async': ['rpcs3/Emu/RSX/VK/VKAsyncScheduler.h', 'rpcs3/Emu/RSX/VK/VKAsyncScheduler.cpp'],
    'barriers': ['rpcs3/Emu/RSX/VK/vkutils/image_helpers.cpp'],
    'arena': ['Utilities/JITArenaAllocator.h'],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def command(*args, cwd=ROOT):
    return subprocess.check_output([str(x) for x in args], cwd=cwd, timeout=300)


def at(commit, path):
    return command('git', 'show', commit + ':' + path)


def file_sha(path):
    return sha(Path(path).read_bytes())


def run_checked(argv, log, env=None, timeout=300):
    result = subprocess.run([str(x) for x in argv], cwd=ROOT, env=env,
                            capture_output=True, timeout=timeout)
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    Path(log).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        print((result.stdout + result.stderr).decode(errors='replace'), flush=True)
        raise RuntimeError(f'Command failed ({result.returncode}): {argv}; log: {log}')
    return result.stdout


def inputs():
    import neo_swap_core_pin_test as pin
    import neoswap_bulk_trim_test as bulk
    record = load(ROOT / RECORD)
    paths = set(pin.CORE_INPUTS) | set(record['repository_inputs_sha256'])
    paths.update(bulk.store_input_hashes())
    paths.update((GATE, ROUTE, WORKFLOW, RECORD, CONTRACT,
                  EVIDENCE + 'codegen-identity.json', 'test/neoswap_bulk_trim_test.py',
                  'test/native/neoswap_bulk_trim.inc'))
    # All files consumed by historical-scope verification are also frozen.
    paths.update(('test/rpcs3_device595_test.py', 'test/rpcs3_surface_coverage_test.py',
                  'test/rpcs3_shader_token_test.py', 'test/rpcs3_async_sync_pool_test.py',
                  'test/rpcs3_texture_barrier_test.py', 'test/rpcs3_jit_arena_merge_test.py'))
    return {p: file_sha(ROOT / p) for p in sorted(paths)}


def source_contract(source):
    import neo_swap_core_pin_test as pin
    manifest = load(ROOT / MANIFEST)
    assert file_sha(ROOT / RECORD) == RECORD_SHA
    record = load(ROOT / RECORD)
    assert manifest['patch_sha256'] == file_sha(ROOT / PATCH) == PATCH_SHA
    assert record['baseline_commit'] == BASE
    before = json.loads(at(BASE, MANIFEST))
    assert before == json.loads(at(HIST, MANIFEST))
    assert before['patch_sha256'] == HIST_PATCH
    assert manifest['continuation_20261030']['baseline_commit'] == BASE
    assert manifest['continuation_20261030']['codegen_identities'] == CODEGEN
    assert manifest['policy'] == before['policy'] + (
        ' The 30 October source continuation preserves prior work and adds reviewed DMA/MMIO fixes '
        'with an exact compatible-SPU-cache alias, shader invalidation and GPU ownership fixes, '
        'bounded texture work and memory-pressure improvements. Host regression evidence is scoped '
        'in docs/rpcs3-continuation-2026-10-30.md; no Apple build, device FPS claim or release is implied.')
    assert dict(manifest, files_sha256=before['files_sha256'], patch_sha256=before['patch_sha256'], policy=before['policy']) == dict(
        before, continuation_20261030=manifest['continuation_20261030'])
    changed = {p for p, h in manifest['files_sha256'].items() if before['files_sha256'].get(p) != h}
    assert changed == set(record['changed_core_files']) and len(changed) == 8
    assert len(manifest['files_sha256']) == len(before['files_sha256']) == 319
    for path, digest in manifest['files_sha256'].items():
        assert sha((source / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    for path, digest in record['repository_inputs_sha256'].items():
        assert file_sha(ROOT / path) == digest, path
    for path in (WORKFLOW, BUILD):
        assert (ROOT / path).read_bytes() == at(HIST, path), 'Historical recipe changed: ' + path
    old_route = at(HIST, ROUTE).decode()
    anchor = "    if 'deep_audit_20261029' in manifest():\n"
    assert old_route.count(anchor) == 1
    assert (ROOT / ROUTE).read_text() == old_route.replace(anchor, ROUTE_BLOCK + anchor, 1)
    for path in set(pin.CORE_INPUTS) - {MANIFEST, PATCH, 'test/neo_swap_core_pin_test.py'}:
        assert (ROOT / path).read_bytes() == at(HIST, path), path
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    assert len(exports) == len(set(exports)) == 88
    return manifest, record, exports


def historical_reference(source, download=False):
    directory = OUT / 'reference-e97137b1'
    directory.mkdir(parents=True, exist_ok=True)
    if download:
        state = json.loads(command('gh', 'api', f'repos/TarbleFR/RewindBox/actions/runs/{RUN}'))
        assert state['head_sha'] == HIST and state['status'] == 'completed' and state['conclusion'] == 'success'
        assert state['path'] == WORKFLOW
        save(directory / 'run.json', state)
    state = load(directory / 'run.json')
    assert state['head_sha'] == HIST and state['id'] == RUN and state['conclusion'] == 'success'
    paths = {}
    for name, (artifact, size, digest) in ARCHIVES.items():
        path = directory / (name + '.zip')
        if download and not path.exists():
            with path.open('wb') as output:
                subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{artifact}/zip'],
                               cwd=ROOT, stdout=output, check=True, timeout=300)
        assert path.stat().st_size == size and file_sha(path) == digest, name
        paths[name] = path
    with zipfile.ZipFile(paths['core']) as core, zipfile.ZipFile(paths['diagnostics']) as diagnostics:
        identity_raw = diagnostics.read('identity.json')
        proof_raw = diagnostics.read('deep-audit-proof.json')
        assert sha(identity_raw) == HIST_IDENTITY and sha(proof_raw) == HIST_PROOF
        assert core.read('identity.json') == identity_raw
        assert sha(core.read('libRPCS3Core.dylib')) == HIST_CORE
        identity, proof = json.loads(identity_raw), json.loads(proof_raw)
        assert identity['host_commit'] == proof['source'] == HIST
        assert identity['sha256'] == HIST_CORE and identity['abi_version'] == 30
        assert proof['all_tests_passed'] and len(proof['tests']) == 31
        assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
        assert identity['native_source_sha256'] == proof['native_source_sha256'] == json.loads(at(HIST, MANIFEST))['files_sha256']
        reused = {}
        for name, scopes in UNCHANGED.items():
            hashes = {p: sha((source / p).read_bytes().replace(b'\r\n', b'\n')) for p in scopes}
            assert all(h == proof['native_source_sha256'][p] for p, h in hashes.items()
                       if p in proof['native_source_sha256']), name
            for mode in (('plain',) if name == 'barriers' else ('plain', 'asan-ubsan')):
                key = name + '-' + mode
                item = proof['tests'][key]
                raw = diagnostics.read(key + '-result.json')
                assert item['passed'] and sha(raw) == item['report_sha256'], key
                report = json.loads(raw)
                assert report['passed'] and '-UNDEBUG' in report['flags']
                assert sha(diagnostics.read(item['program'])) == item['program_sha256'] == report['program_sha256']
                assert sha(diagnostics.read(key + '-output.txt')) == report['output_sha256']
                # Evidence/fixtures used for this historical result remain the
                # exact successful-revision inputs; the source scopes above
                # must also be byte-identical in the current candidate.
                evidence_path = report['evidence']
                evidence = json.loads(at(HIST, evidence_path))
                expected = evidence['sourceSHA256']
                if isinstance(expected, str):
                    expected = {scopes[0]: expected}
                assert hashes == expected
                assert report['canonical_program_sha256'] == evidence['harnessSHA256']
                reused[key] = dict(passed=True, reused_from=dict(source=HIST, run=RUN),
                                   source_scope_sha256=hashes, report_sha256=sha(raw),
                                   program_sha256=report['program_sha256'], native_executed_now=False)
    assert len(reused) == 11
    return dict(source=HIST, run=RUN, archive_sha256={k: v[2] for k, v in ARCHIVES.items()},
                core_sha256=HIST_CORE, proof_sha256=HIST_PROOF,
                historical_modes=31, reused_current_modes=reused,
                other_modes_remain_historical=True, old_binary_reused=False)


def baseline_tree(source, target, record):
    target.mkdir(parents=True, exist_ok=True)
    for path in [*record['changed_core_files'], 'rpcs3/Emu/Memory/vm_locking.h']:
        dest = target / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, dest)
    fixture = ROOT / record['core_delta_fixture']
    command('git', 'apply', '--reverse', '--check', fixture, cwd=target)
    command('git', 'apply', '--reverse', fixture, cwd=target)
    for path, item in record['changed_core_files'].items():
        assert file_sha(target / path) == item['before_sha256'], path
    return target


def generate_programs(source, baseline, directory, record):
    substitutions = {'{repo}': str(ROOT), '{source}': str(source),
                     '{baseline}': str(baseline), '{output}': str(directory)}
    def substitute(value):
        for token, replacement in substitutions.items():
            value = value.replace(token, replacement)
        return value
    for job in record['harness_generation_checks']:
        args = [substitute(x) for x in job['arguments']]
        assert '--generate-only' in args
        run_checked([sys.executable, ROOT / job['runner'], *args], OUT / (job['name'] + '-generation.txt'))
        generated = load(substitute(job['generated_report']))
        for check in job['checksums']:
            actual = generated
            for key in check['key']:
                actual = actual[key]
            assert actual == check['expected'], job['name']
    paths = {
        'dma-list': directory / 'dma-list/dma-list-program.cpp',
        'vm-mmio': directory / 'vm-mmio/vm-mmio-program.cpp',
        'dma-mmio': directory / 'dma-mmio/dma-mmio-program.cpp',
        'pipeline': directory / 'pipeline/pipeline.cpp',
        'gpu-wait': directory / 'gpu-wait/gpu-wait.cpp',
        'dma-ownership': directory / 'dma-ownership/dma-ownership.cpp',
        'pressure': directory / 'texture-lifetimes/pressure.cpp',
        'depth': directory / 'texture-lifetimes/depth.cpp',
        'pressure-baseline': directory / 'texture-baseline/pressure.cpp',
        'depth-baseline': directory / 'texture-baseline/depth.cpp',
        'atlas': directory / 'atlas/atlas.cpp',
        'atlas-area': directory / 'atlas-area/atlas_area.cpp',
    }
    import neoswap_bulk_trim_test as bulk
    program, _ = bulk.harness(at(BASE, bulk.STORE).decode(), (ROOT / bulk.STORE).read_text())
    assert sha(program.encode()) == load(ROOT / (EVIDENCE + 'neoswap-bulk-plain.json'))['programSHA256']
    paths['neoswap-trim'] = directory / 'neoswap-trim.cpp'
    paths['neoswap-trim'].write_text(program)
    result = {}
    for name, path in paths.items():
        target = OUT / (name + '-program.cpp')
        shutil.copyfile(path, target)
        result[name] = target
    return result


def expected_result(name):
    evidence = ROOT / EVIDENCE
    if name in ('dma-list', 'vm-mmio', 'dma-mmio'):
        path = {'dma-list': 'plain-result.json', 'vm-mmio': 'vm-plain-result.json',
                'dma-mmio': 'dma-mmio-plain-result.json'}[name]
        return load(evidence / 'cpu/evidence' / path)['results']
    if name in ('pipeline', 'gpu-wait', 'dma-ownership'):
        path = {'pipeline': 'candidate.json', 'gpu-wait': 'wait-candidate-asan.json',
                'dma-ownership': 'dma-wait-comparison.json'}[name]
        data = load(evidence / 'renderer' / path)
        if name == 'dma-ownership':
            return {k: data[k] for k in ('baseline', 'candidate')}
        return {k: v for k, v in data.items() if type(v) is int}
    if name == 'pressure':
        data = load(evidence / 'texture/results/pressure-final/report.json')['reports'][0]
    elif name == 'depth':
        data = load(evidence / 'texture/results/candidate/report.json')['reports'][1]
    elif name.endswith('-baseline'):
        group = 'pressure-baseline-final' if name == 'pressure-baseline' else 'baseline'
        reports = load(evidence / f'texture/results/{group}/report.json')['reports']
        data = next(r for r in reports if r['case'] == ('retired_image_pressure' if name.startswith('pressure') else 'unnormalized_depth'))
    elif name == 'atlas-area':
        data = load(evidence / 'texture/results/atlas-area-asan/report.json')
    else:
        raise AssertionError('No fixed output oracle: ' + name)
    return {k: v for k, v in data.items() if (type(v) is int or k == 'case')}


def validate_result(name, result):
    if name == 'atlas':
        assert result['case'] == 'atlas_coverage'
        assert result['helper_allocations'] == 0 and result['unsafe_fallbacks'] == 14
        # std::shuffle intentionally permits different libc++ permutations.
        # Every layout still runs the complete independent texel-painter oracle.
        assert result['cases'] >= 60000 and result['checks'] > result['cases']
        assert result['newly_omitted_color_clears'] > 0 and result['unchanged_clear_cases'] > 0
        assert result['newly_omitted_color_clears'] + result['unchanged_clear_cases'] == result['cases']
    elif name == 'neoswap-trim':
        assert result['passed'] and result['cases'] == 2400 and result['sweeps'] == 12000
        assert result['dynamicUnpinCases'] == 16 and result['trimAllocations'] == 0
        assert result['baselineRamScans'] == result['candidateRamScans'] == 12000
        assert result['baselineSelectionVisits'] > 0 and result['candidateSelectionVisits'] > 0
        assert result['benchmarks'] == []
    else:
        assert result == expected_result(name), (name, result, expected_result(name))


def modes(name):
    if name.endswith('-baseline'):
        return ('plain',)
    if name in ('gpu-wait', 'dma-ownership'):
        return ('asan-ubsan',)
    return ('plain', 'asan-ubsan')


def program_hashes():
    checks = {j['name']: [c['expected'] for c in j['checksums']]
              for j in load(ROOT / RECORD)['harness_generation_checks']}
    result = {n: checks[n][0] for n in ('dma-list', 'vm-mmio', 'dma-mmio', 'pipeline',
                                       'gpu-wait', 'dma-ownership', 'atlas', 'atlas-area')}
    result.update(pressure=checks['texture-lifetimes'][0], depth=checks['texture-lifetimes'][1])
    result['pressure-baseline'], result['depth-baseline'] = checks['texture-baseline']
    result['neoswap-trim'] = load(ROOT / (EVIDENCE + 'neoswap-bulk-plain.json'))['programSHA256']
    return result


def flags(name, mode, sdk=None):
    result = ['-std=c++20', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
              '-pthread', '-isysroot', sdk or os.environ['HOST_MACOS_SDK'],
              '-O1' if mode == 'asan-ubsan' else '-O2']
    if name in ('pipeline', 'gpu-wait', 'dma-ownership', 'pressure', 'depth',
                'pressure-baseline', 'depth-baseline'):
        result.append('-DRPCS3_IOS')
    if mode == 'asan-ubsan':
        result += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
    if name.endswith('-baseline'):
        result.append('-DEXPECT_BASELINE')
    if name == 'depth':
        # The unchanged adapter counts baseline failures for its alternate mode.
        # This warning-only exception does not alter its candidate assertions.
        result.append('-Wno-unused-but-set-variable')
    if name in ('neoswap-trim', 'store-full'):
        result.append('-Wno-misleading-indentation')
    if name == 'neoswap-trim':
        result.append('-Wno-mismatched-new-delete')
    if name == 'atlas-area':
        # Do not rely on the compiler's treatment of undefined old arithmetic.
        # The frozen fixture already supports candidate-only execution; the
        # sanitizer run separately proves the old signed overflow is detected.
        result.append('-DVERIFY_CANDIDATE_ONLY')
    return result


def prepare(source):
    assert platform.system() == 'Darwin' and platform.machine() == 'arm64'
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, record, exports = source_contract(source)
    current = inputs()
    compiler = shlex.split(os.environ['CXX'])
    version = command(*compiler, '--version').decode().splitlines()[0]
    assert re.search(r'clang version 22\.', version), version
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    contract_path = OUT / 'continuation-source-contract.json'
    run_checked([sys.executable, ROOT / CONTRACT, '--source', source, '--report', contract_path],
                OUT / 'continuation-source-contract.txt')
    contract = load(contract_path)
    assert contract['passed'] and contract['codegen_identities'] == CODEGEN
    proof = dict(schema=1, type='rpcs3-continuation-20261030',
                 source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                 source_root=str(source), source_patch_sha256=PATCH_SHA,
                 input_sha256=current, native_source_sha256=manifest['files_sha256'],
                 exported_symbols=exports, codegen=CODEGEN,
                 host=dict(system='Darwin', machine='arm64', compiler=version,
                           macos_sdk=os.environ['HOST_MACOS_SDK']),
                 historical=historical_reference(source, download=True),
                 source_contract_sha256=file_sha(contract_path), tests={}, all_tests_passed=False,
                 physical_device_tested=False, gameplay_measured=False, public_release=False,
                 neoswap_host_component_packaged=False)
    save(PROOF, proof)
    with tempfile.TemporaryDirectory(prefix='rpcs3-continuation-apple-') as temporary:
        work = Path(temporary)
        baseline = baseline_tree(source, work / 'baseline', record)
        programs = generate_programs(source, baseline, work / 'generated', record)
        assert {name: file_sha(path) for name, path in programs.items()} == program_hashes()
        for name, cpp in programs.items():
            for mode in modes(name):
                key = name + '-' + mode
                print('RUN ' + key, flush=True)
                argv = flags(name, mode)
                executable = work / key
                compile_log, output_log = OUT / (key + '-compile.txt'), OUT / (key + '-output.txt')
                run_checked([*compiler, *argv, cpp, '-o', executable], compile_log, env)
                result = json.loads(run_checked([executable], output_log, env))
                validate_result(name, result)
                report = dict(passed=True, name=name, mode=mode, results=result,
                              program=cpp.name, program_sha256=file_sha(cpp), compiler=version, flags=argv,
                              output_sha256=file_sha(output_log), compile_sha256=file_sha(compile_log),
                              physical_device_tested=False, gpu_executed=False)
                if name == 'atlas-area' and mode == 'asan-ubsan':
                    probe = subprocess.run([str(executable), '--baseline-overflow-probe'],
                                           cwd=ROOT, env=env, capture_output=True, timeout=30)
                    probe_path = OUT / (key + '-baseline-overflow.txt')
                    probe_path.write_bytes(probe.stdout + probe.stderr)
                    assert probe.returncode != 0 and b'signed integer overflow' in probe.stderr
                    report['baseline_overflow_sha256'] = file_sha(probe_path)
                report_path = OUT / (key + '-result.json')
                save(report_path, report)
                proof['tests'][key] = dict(passed=True, report_sha256=file_sha(report_path))
                save(PROOF, proof)
        # The Store changed too. Validate its actual Apple compression/POSIX
        # paths once, while explicitly recording that a Core does not package it.
        for mode in ('plain', 'asan-ubsan'):
            key = 'store-full-' + mode
            argv = [f for f in flags('store-full', mode) if f != '-Werror']
            argv += ['-DNEOSWAP_STORAGE_TESTING', '-Inative/neoswap-storage']
            executable = work / key
            run_checked([*compiler, *argv, 'native/neoswap-storage/Store.cpp',
                         'native/neoswap-storage/tests/store_test.cpp', '-lcompression', '-lz',
                         '-o', executable], OUT / (key + '-compile.txt'), env)
            result = run_checked([executable, work / (key + '-cache')], OUT / (key + '-output.txt'), env)
            assert result.startswith(b'PASS: real POSIX file round trips')
            report = dict(passed=True, name='store-full', mode=mode, flags=argv, compiler=version,
                          output_sha256=sha(result), compile_sha256=file_sha(OUT / (key + '-compile.txt')))
            save(OUT / (key + '-result.json'), report)
            proof['tests'][key] = dict(passed=True, report_sha256=file_sha(OUT / (key + '-result.json')))
            save(PROOF, proof)
    assert inputs() == current
    proof['all_tests_passed'] = True
    save(PROOF, proof)
    verify(PROOF, source)
    print(f"PASS: {len(proof['tests'])} affected Apple modes and 11 unchanged historical modes; compile the Core once", flush=True)


def verify(path, source):
    proof = load(path)
    manifest, _, exports = source_contract(source)
    assert proof['schema'] == 1 and proof['type'] == 'rpcs3-continuation-20261030'
    assert proof['all_tests_passed'] is True
    assert proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert proof['source_patch_sha256'] == PATCH_SHA and proof['input_sha256'] == inputs()
    assert proof['native_source_sha256'] == manifest['files_sha256'] and proof['exported_symbols'] == exports
    assert proof['codegen'] == CODEGEN and proof['physical_device_tested'] is False
    assert proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
    assert re.search(r'clang version 22\.', proof['host']['compiler'])
    assert proof['historical'] == historical_reference(source)
    assert file_sha(OUT / 'continuation-source-contract.json') == proof['source_contract_sha256']
    names = ('dma-list', 'vm-mmio', 'dma-mmio', 'pipeline', 'gpu-wait', 'dma-ownership',
             'pressure', 'depth', 'pressure-baseline', 'depth-baseline', 'atlas', 'atlas-area', 'neoswap-trim')
    expected = {n + '-' + m for n in names for m in modes(n)} | {'store-full-plain', 'store-full-asan-ubsan'}
    assert set(proof['tests']) == expected
    program_sha256 = program_hashes()
    for key, item in proof['tests'].items():
        report_path = OUT / (key + '-result.json')
        assert item['passed'] and file_sha(report_path) == item['report_sha256']
        report = load(report_path)
        assert report['passed'] and report['compiler'] == proof['host']['compiler']
        expected_flags = flags(report['name'], report['mode'], proof['host']['macos_sdk'])
        if report['name'] == 'store-full':
            expected_flags = [f for f in expected_flags if f != '-Werror']
            expected_flags += ['-DNEOSWAP_STORAGE_TESTING', '-Inative/neoswap-storage']
        assert report['flags'] == expected_flags
        assert '-UNDEBUG' in report['flags'] and not any(f.startswith('-DNDEBUG') for f in report['flags'])
        assert ('-fsanitize=address,undefined' in report['flags']) is (report['mode'] == 'asan-ubsan')
        assert file_sha(OUT / (key + '-compile.txt')) == report['compile_sha256']
        assert file_sha(OUT / (key + '-output.txt')) == report['output_sha256']
        if report['name'] == 'store-full':
            assert (OUT / (key + '-output.txt')).read_bytes().startswith(b'PASS: real POSIX file round trips')
        else:
            assert file_sha(OUT / report['program']) == report['program_sha256'] == program_sha256[report['name']]
            assert json.loads((OUT / (key + '-output.txt')).read_bytes()) == report['results']
            validate_result(report['name'], report['results'])
        if 'baseline_overflow_sha256' in report:
            assert file_sha(OUT / (key + '-baseline-overflow.txt')) == report['baseline_overflow_sha256']
    print('PASS: continuation Apple proof matches source and unchanged build recipe', flush=True)
    return proof


def identity(directory):
    proof = verify(PROOF, Path(load(PROOF)['source_root']))
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    import neo_swap_core_pin_test as pin
    data = (directory / 'libRPCS3Core.dylib').read_bytes()
    image = macho(data)
    assert image['platform'] == 2 and set(image['definedSymbols']) == set(proof['exported_symbols'])
    log = (OUT / 'build.log').read_text()
    for kind, expected in CODEGEN.items():
        assert re.findall('NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log) == [expected]
    manifest = load(ROOT / MANIFEST)
    for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'):
        assert hook in log
    archive = manifest['cell587']['moltenvk_archive']
    assert archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log
    assert not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(
        command('nm', '-u', directory / 'libRPCS3Core.dylib').decode().split())
    assert command('lipo', '-archs', directory / 'libRPCS3Core.dylib').decode().strip() == 'arm64'
    assert (directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest['upstream_commit']
    assert (directory / 'RPCS3_IOS_ABI.txt').read_text().strip() == '30'
    record = dict(schema_version=1, type='rpcs3-ios-continuation-source-candidate',
                  host_commit=proof['source'], native_source_commit=proof['source'], source_commit=manifest['upstream_commit'],
                  sha256=sha(data), abi_version=30, architectures=['arm64'], source_patch_sha256=PATCH_SHA,
                  core_input_sha256=pin.core_input_hashes(), continuation_input_sha256=proof['input_sha256'],
                  native_source_sha256=manifest['files_sha256'], exported_symbols=proof['exported_symbols'],
                  codegen=CODEGEN, physical_device_tested=False, gameplay_measured=False, public_release=False,
                  neoswap_host_component_packaged=False)
    save(directory / 'identity.json', record)
    save(OUT / 'identity.json', record)
    shutil.copyfile(PROOF, directory / PROOF.name)
    print('PASS: actual iPhone ARM64 continuation Core, ABI30, 88 exports, compatible PPU/SPU identities', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--verify-reuse', type=Path)
    parser.add_argument('--write-core-identity', type=Path)
    args = parser.parse_args()
    if args.write_core_identity:
        identity(args.write_core_identity)
    elif args.source and args.verify_reuse:
        verify(args.verify_reuse, args.source.resolve())
    elif args.source:
        prepare(args.source.resolve())
    else:
        parser.error('--source or --write-core-identity is required')
