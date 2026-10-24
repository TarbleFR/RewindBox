#!/usr/bin/env python3
"""Reject partial-proof mutations without requiring an artifact/network in unit tests."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3cell527_partial as partial


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture():
    source_hashes = {'rpcs3/Emu/Cell/PPUTranslator.cpp': 'translator',
        'rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h': 'helper',
        'rpcs3/Emu/RSX/VK/VKTextureCache.cpp': 'pool'}
    old_inputs = {'test/fixtures/rpcs3_ppu_dot526_before.inc': 'ppu-fixture',
        'test/fixtures/rpcs3_pool527.diff': 'pool-fixture',
        'test/native/rpcs3_pool527.cpp': 'pool-test',
        'test/rpcs3_ppu_sum527_test.py': 'old-unrelated-harness',
        'build-utils/rpcs3/canonical-source.json': 'old-manifest'}
    specs = []
    for name in sorted(partial.CASES):
        ppu = name == 'ppu-simd526-regression'
        script = 'test/rpcs3_ppu_simd526_test.py' if ppu else 'test/rpcs3_pool527_test.py'
        args = (['--require-llvm', '--artifacts', 'build/rpcs3-core-diagnostics/ppu-simd526-asm'] if ppu else
            ['--sanitize', '--require-core-compiler'] if name == 'recyclable-pool' else ['--benchmark', '--require-core-compiler'])
        specs.append(dict(name=name, script=script, args=args, timeout=600))
        old_inputs[script] = script + '-hash'
    old_manifest = dict(upstream_commit='upstream', patch_sha256='same-patch', files_sha256=source_hashes,
        cell527=dict(extra_inputs=list(old_inputs), tests=specs, codegen={'PPU': 'same', 'SPU': 'same'}))
    new_manifest = copy.deepcopy(old_manifest)
    new_manifest['cell527']['extra_inputs'].append(partial.SELFTEST)
    new_manifest['cell527']['tests'].append(dict(name='partial-reuse-gate', script=partial.SELFTEST, args=[], timeout=120))
    current_inputs = dict(old_inputs, **{partial.HELPER: 'new-helper', partial.SELFTEST: 'new-unit-test'})
    current_inputs['test/rpcs3_ppu_sum527_test.py'] = 'fixed-unrelated-harness'
    current_inputs['build-utils/rpcs3/canonical-source.json'] = 'new-manifest'
    files, tests = {}, {}
    hardware = {'hw.model': 'VirtualMac2,1', 'machdep.cpu.brand_string': 'Apple M1 (Virtual)'}
    for spec in specs:
        name = spec['name']
        if name == 'ppu-simd526-regression':
            payload = dict(schema=1, llvm_version='22.1.8', host_triple='arm64-apple-darwin24.6.0', hardware=hardware,
                game_or_device_tested=False, cases_per_operation=75941,
                production_translator_sha256='translator', production_helper_sha256='helper', before_fixture_sha256='ppu-fixture',
                operations=[dict(name=op, bit_exact=True, big_endian_exact=True) for op in ('VMSUMUBM', 'VMSUMMBM', 'VMSUMUHM', 'VMSUMSHM')],
                dotprod_hardware_proof=dict(hardware_verified=True, explicit_udot_controls=5))
        else:
            sanitized = name == 'recyclable-pool'
            commands = {}
            for variant in ('before', 'after'):
                argv = [partial.COMPILER, '-isysroot', partial.SDK, '-std=c++20', '-O3', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-DRPCS3_IOS',
                    '-I/var/folders/test/temp', '-I' + partial.HISTORICAL_SOURCE_PATH,
                    partial.HISTORICAL_ROOT + '/test/native/rpcs3_pool527.cpp', '-o', '/var/folders/test/temp/' + variant + '-bin']
                if sanitized:
                    argv += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
                commands[variant] = argv
            payload = dict(passed=True, sanitizers=sanitized, compiler='Homebrew clang version 22.1.8',
                commands=commands, after_sha256='pool', fixture_sha256='pool-fixture')
        report, output = name + '-result.json', name + '-output.txt'
        files[report] = json.dumps(payload).encode()
        files[output] = (name + ' directly passed\n').encode()
        tests[name] = dict(status='passed', returncode=0, executed_here=True, report=report, output=output,
            report_sha256=digest(files[report]), output_sha256=digest(files[output]),
            command=['python3', spec['script'], partial.HISTORICAL_SOURCE_PATH, *spec['args'], '--report',
                partial.HISTORICAL_ROOT + '/build/rpcs3-core-diagnostics/' + report])
    files['cell527-proof.txt'] = b'direct complete log'
    receipt = dict(source=partial.SOURCE, physical_device_tested=False, all_tests_passed=False,
        native_source_sha256=source_hashes, input_sha256=old_inputs, tests=tests, log_sha256=digest(files['cell527-proof.txt']))
    files['cell527-partial.json'] = json.dumps(receipt).encode()
    files['ppu-simd526-asm/test.s'] = b'fixture assembly'
    environment = dict(toolchain=dict(llvm_version='22.1.8', compiler=partial.COMPILER,
        compiler_version='Homebrew clang version 22.1.8', sdk=partial.SDK, machine='arm64', kernel_release='24.6.0', hardware=hardware))
    return [files, 'metadata-hash', current_inputs, new_manifest, environment, old_inputs, old_manifest]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    before = partial.PPU_ASM_SHA
    partial.PPU_ASM_SHA = {'ppu-simd-asm/test.s': digest(b'fixture assembly')}
    checks = 0
    try:
        base = fixture()
        admitted = partial.validate(*base)
        assert set(admitted) == partial.CASES
        assert all(item['provenance']['container_conclusion'] == 'failure' and item['provenance']['core_built'] is False for item in admitted.values())
        assert admitted['ppu-simd526-regression']['provenance']['toolchain']['full_historical_environment_captured'] is False
        checks += 3
        def reject(mutate):
            nonlocal checks
            value = copy.deepcopy(base)
            mutate(value)
            try:
                partial.validate(*value)
            except (AssertionError, KeyError):
                checks += 1
                return
            raise AssertionError('Partial mutation was admitted')
        def edit_receipt(value, mutate):
            payload = json.loads(value[0]['cell527-partial.json'])
            mutate(payload)
            value[0]['cell527-partial.json'] = json.dumps(payload).encode()
        reject(lambda v: edit_receipt(v, lambda p: p.update(all_tests_passed=True)))
        reject(lambda v: edit_receipt(v, lambda p: p['tests']['recyclable-pool'].update(status='failed')))
        reject(lambda v: edit_receipt(v, lambda p: p['tests']['recyclable-pool'].update(executed_here=False)))
        reject(lambda v: edit_receipt(v, lambda p: p['tests']['recyclable-pool']['command'].append('--changed-command')))
        reject(lambda v: v[2].update({'test/native/rpcs3_pool527.cpp': 'changed-reused-harness'}))
        reject(lambda v: v[3]['files_sha256'].update({'rpcs3/Emu/RSX/VK/VKTextureCache.cpp': 'changed-native'}))
        reject(lambda v: v[3]['cell527']['tests'][0]['args'].append('--new-option'))
        reject(lambda v: v[4]['toolchain'].update(sdk='different-sdk'))
        reject(lambda v: v[0].update({'recyclable-pool-result.json': b'{"passed":false}'}))
        reject(lambda v: v[0].update({'recyclable-pool-output.txt': b'changed output'}))
        reject(lambda v: v[0].update({'ppu-simd526-asm/test.s': b'changed assembly'}))
        reject(lambda v: v[3].update(patch_sha256='different-native-patch'))
        metadata = dict(run=dict(id=partial.RUN, head_sha=partial.SOURCE, status='completed', conclusion='failure'),
            artifact=dict(id=partial.ARTIFACT, expired=False, size_in_bytes=partial.BYTES,
                name='RPCS3Core-diagnostics-' + partial.SOURCE,
                workflow_run=dict(id=partial.RUN, head_sha=partial.SOURCE)))
        partial.metadata_contract(metadata)
        checks += 1
        for change in (lambda x: x['run'].update(conclusion='success'), lambda x: x['artifact'].update(expired=True)):
            value = copy.deepcopy(metadata)
            change(value)
            try:
                partial.metadata_contract(value)
            except AssertionError:
                checks += 1
            else:
                raise AssertionError('Invalid partial transport admitted')
    finally:
        partial.PPU_ASM_SHA = before
    report = dict(passed=True, checks=checks, narrow_direct_partial_cases=sorted(partial.CASES),
        sourceCommandsToolsAndReportsMutationRejected=True, fullHistoricalEnvironmentInvented=False,
        failedPreflightNeverTreatedAsCore=True, physicalDeviceTested=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
