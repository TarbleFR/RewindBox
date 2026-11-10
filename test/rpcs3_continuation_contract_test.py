#!/usr/bin/env python3
"""Authenticate this source lot and regenerate its already executed harnesses.

No compiler, native executable, Apple build, GPU driver or network is invoked.
This check ties recorded results to the materialized production source; it does
not turn a source/host result into an iPhone gameplay or performance result.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/rpcs3-continuation-20261030'
RECORD = EVIDENCE / 'source-record.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path, lf=False):
    data = path.read_bytes()
    return sha(data.replace(b'\r\n', b'\n') if lf else data)


def checked(condition, message):
    if not condition:
        raise AssertionError(message)


def run(command, cwd=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    checked(result.returncode == 0,
            f'Command failed: {command!r}\n{result.stdout}\n{result.stderr}')
    return result.stdout


def codegen_identities(source, evidence):
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    aliases_text = (source / 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake').read_text()
    aliases = {(path, actual): compatible for path, actual, compatible in re.findall(
        r'(?:if|elseif)\(source STREQUAL "([^"]+)" AND\s*'
        r'actual STREQUAL "([0-9a-f]{64})"\)\s*'
        r'set\(\$\{output\} "([0-9a-f]{64})" PARENT_SCOPE\)', aliases_text)}
    actual_inputs = {}
    external = []
    for name, expected in evidence['inputs'].items():
        path = source / 'rpcs3/Emu' / name
        if path.is_file():
            actual = file_sha(path)
        else:
            # The unchanged LLVM submodule was not downloaded in this source
            # review. Reuse its locked digest and disclose that boundary.
            checked(name == '../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp',
                    f'Missing codegen input: {name}')
            checked(expected['before'] == expected['after'], 'External backend changed')
            actual = expected['after']
            external.append(name)
        checked(actual == expected['after'], f'Codegen input differs: {name}')
        actual_inputs[name] = actual
    identities = {}
    for engine in ('PPU', 'SPU'):
        match = re.search(r'foreach\(NEOSTATION_' + engine +
                          r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S)
        checked(match is not None, f'Missing {engine} digest recipe')
        digest = ''.join(name + ':' + aliases.get((name, actual_inputs[name]), actual_inputs[name]) + ';'
                         for name in match.group(1).split())
        identities[engine] = sha(digest.encode())[:16]
    checked(identities == evidence['identities']['after'], 'Codegen identity mismatch')
    return identities, external


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='Materialized candidate RPCS3 source tree')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    record = json.loads(RECORD.read_text())
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_text())
    checked(manifest['upstream_commit'] == record['upstream_commit'], 'Upstream revision changed')
    patch = ROOT / 'build-utils/rpcs3/embedded-core.patch'
    checked(file_sha(patch) == manifest['patch_sha256'], 'Canonical patch digest mismatch')
    pin = (ROOT / 'test/neo_swap_core_pin_test.py').read_text()
    checked(f"PATCH_SHA256 = '{manifest['patch_sha256']}'" in pin, 'Patch pin mismatch')

    expected_postimages = dict(record['unchanged_core_postimages_sha256'])
    expected_postimages.update({name: item['after_lf_sha256']
                               for name, item in record['changed_core_files'].items()})
    checked(expected_postimages == manifest['files_sha256'], 'Unexpected canonical source change')
    for name, expected in expected_postimages.items():
        checked(file_sha(source / name, lf=True) == expected, f'Materialized source differs: {name}')
    for name, expected in record['repository_inputs_sha256'].items():
        checked(file_sha(ROOT / name) == expected, f'Reviewed repository input differs: {name}')

    fixture = ROOT / record['core_delta_fixture']
    checked(file_sha(fixture) == record['core_delta_sha256'], 'Inverse delta differs')
    generation_results = []
    with tempfile.TemporaryDirectory(prefix='rpcs3-continuation-contract-') as tmp:
        tmp = Path(tmp)
        baseline = tmp / 'baseline'
        baseline.mkdir()
        for name, item in record['changed_core_files'].items():
            checked(file_sha(source / name) == item['after_sha256'], f'Candidate bytes differ: {name}')
            destination = baseline / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination)
        run(['git', 'apply', '--reverse', '--check', str(fixture)], cwd=baseline)
        run(['git', 'apply', '--reverse', str(fixture)], cwd=baseline)
        for name, item in record['changed_core_files'].items():
            checked(file_sha(baseline / name) == item['before_sha256'], f'Baseline bytes differ: {name}')
        # The range-lock harness also extracts this unchanged fast-path header
        # from both versions. Its canonical hash was authenticated above.
        for name in ('rpcs3/Emu/Memory/vm_locking.h',):
            checked(name in record['unchanged_core_postimages_sha256'], 'Baseline support input changed')
            destination = baseline / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination)

        substitutions = {'{repo}': str(ROOT), '{source}': str(source),
                         '{baseline}': str(baseline), '{output}': str(tmp / 'generated')}

        def substitute(text):
            for token, value in substitutions.items():
                text = text.replace(token, value)
            return text

        for job in record['harness_generation_checks']:
            runner = ROOT / job['runner']
            checked(runner.is_relative_to(ROOT / 'test/rpcs3_continuation') and runner.suffix == '.py',
                    'Unexpected generation runner')
            arguments = [substitute(value) for value in job['arguments']]
            checked('--generate-only' in arguments, 'Native execution is not allowed in this contract')
            run([sys.executable, str(runner), *arguments], cwd=ROOT)
            generated_path = Path(substitute(job['generated_report']))
            generated = json.loads(generated_path.read_text())
            for checksum in job['checksums']:
                value = generated
                for key in checksum['key']:
                    value = value[key]
                checked(value == checksum['expected'], f"Harness bytes differ: {job['name']}")
            generation_results.append({'name': job['name'], 'matches_executed_harness': True,
                                       'compiled': False, 'executed': False})

    codegen, external_inputs = codegen_identities(source, json.loads((EVIDENCE / 'codegen-identity.json').read_text()))
    spec = importlib.util.spec_from_file_location('neoswap_bulk_contract', ROOT / 'test/neoswap_bulk_trim_test.py')
    neoswap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(neoswap)
    old_store = run(['git', 'show', record['baseline_commit'] + ':native/neoswap-storage/Store.cpp'], cwd=ROOT)
    store_program, store_methods = neoswap.harness(old_store, (ROOT / 'native/neoswap-storage/Store.cpp').read_text())
    for mode in ('plain', 'asan'):
        result = json.loads((EVIDENCE / f'neoswap-bulk-{mode}.json').read_text())
        checked(result['passed'], f'NeoSwap {mode} result failed')
        checked(file_sha(ROOT / 'native/neoswap-storage/Store.cpp') == result['sourceSHA256'],
                f'NeoSwap {mode} source differs')
        checked(file_sha(ROOT / 'test/native/neoswap_bulk_trim.inc') == result['fixtureSHA256'],
                f'NeoSwap {mode} fixture differs')
        checked(sha(store_program.encode()) == result['programSHA256'] and
                store_methods == result['methodSHA256'], f'NeoSwap {mode} generated program differs')
    report = {'passed': True, 'baseline_commit': record['baseline_commit'],
              'upstream_commit': record['upstream_commit'],
              'canonical_patch_sha256': manifest['patch_sha256'],
              'canonical_postimages_verified': len(expected_postimages),
              'changed_core_files_verified': len(record['changed_core_files']),
              'unchanged_core_postimages_verified': len(record['unchanged_core_postimages_sha256']),
              'repository_inputs_verified': len(record['repository_inputs_sha256']),
              'inverse_delta_verified': True, 'harness_generation': generation_results,
              'codegen_identities': codegen, 'unmaterialized_locked_codegen_inputs': external_inputs,
              'neoswap_program_generation_matches': True,
              'native_test_executed': False, 'apple_build': False, 'device_test': False,
              'fps_claim': False}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
