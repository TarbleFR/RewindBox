"""Reuse six direct527 passes from an explicitly failed preflight, never a Core.

Attempt1 did not capture its full environment. Its compiler/SDK commands and
ARM64 hardware report are available and source-bound. Only those relevant
properties can be matched; do not invent a historical full-environment hash.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import zipfile
from rpcs3arm526_core import PPU_ASM_SHA

SOURCE = '04006a1e40d69ea3a9b2f564dab6b2acf30c1018'
RUN = 40131950958
ARTIFACT = 12575407117
BYTES = 99358931
SHA = '2f1cda59cfcfe4eb1746587880b91d27bbed318dfdcedd7c9ba00231dca6254e'
CASES = frozenset({'ppu-simd526-regression', 'recyclable-pool', 'recyclable-pool-benchmark'})
SECOND_SOURCE = '03171f5a803df1d4ab7062f978884b4b6037aa2c'
SECOND_RUN = 40132602213
SECOND_ARTIFACT = 12575573279
SECOND_BYTES = 200563850
SECOND_SHA = 'd7780a4e187c68d3e7d264ce0b34ed425cf1e0821f1113d0d532327f086e4055'
SECOND_CASES = frozenset({'ppu-sum-sanitized', 'ppu-sum-benchmark', 'runtime-metrics'})
ALL_CASES = CASES | SECOND_CASES
SECOND_MUTABLE_INPUTS = frozenset({'.github/diagnostics/rpcs3cell527_core.py',
    '.github/diagnostics/rpcs3cell527_partial.py', 'test/rpcs3_cell527_partial_test.py',
    'test/rpcs3_jit_publication527_test.py', 'test/native/rpcs3_jit_publication527_llvm.cpp'})
PIN1 = dict(source=SOURCE, run=RUN, artifact=ARTIFACT, size=BYTES, sha256=SHA, label='attempt1')
PIN2 = dict(source=SECOND_SOURCE, run=SECOND_RUN, artifact=SECOND_ARTIFACT,
            size=SECOND_BYTES, sha256=SECOND_SHA, label='attempt2')
HELPER = '.github/diagnostics/rpcs3cell527_partial.py'
SELFTEST = 'test/rpcs3_cell527_partial_test.py'
MUTABLE_INPUTS = frozenset({'.github/diagnostics/rpcs3cell527_core.py',
    'build-utils/rpcs3/canonical-source.json', 'test/rpcs3_jit_publication527_test.py',
    'test/native/rpcs3_jit_publication527_llvm.cpp', 'test/rpcs3_runtime_metrics527_test.py',
    'test/rpcs3_ppu_sum527_test.py', 'test/native/rpcs3_ppu_sum527.cpp',
    'test/rpcs3_cell527_gate_test.py'})
ADDED_INPUTS = frozenset({HELPER, SELFTEST})
HISTORICAL_SOURCE_PATH = '/Users/runner/work/_temp/cell527-source-preflight'
HISTORICAL_ROOT = '/Users/runner/work/RewindBox/RewindBox'
COMPILER = '/opt/homebrew/Cellar/llvm@22/22.1.8/bin/clang++'
SDK = '/Applications/Xcode_16.4.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX15.5.sdk'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def current_toolchain():
    def text(argv):
        return subprocess.check_output(argv, text=True, timeout=30).strip()
    config = shlex.split(os.environ['LLVM_CONFIG'])
    compiler = str(Path(text(config + ['--bindir'])) / 'clang++')
    assert Path(compiler).is_file(), 'Actual LLVM22 compiler missing'
    return dict(llvm_version=text(config + ['--version']), compiler=compiler,
        compiler_version=text([compiler, '--version']).splitlines()[0],
        sdk=os.environ.get('HOST_MACOS_SDK'), machine=platform.machine(),
        kernel_release=platform.release(),
        hardware={key: text(['sysctl', '-n', key]) for key in ('hw.model', 'machdep.cpu.brand_string')})


def metadata_contract(value, pin=PIN1):
    run, artifact = value['run'], value['artifact']
    assert run['id'] == pin['run'] and run['head_sha'] == pin['source']
    assert run['status'] == 'completed' and run['conclusion'] == 'failure'
    assert artifact['id'] == pin['artifact'] and artifact['expired'] is False
    assert artifact['size_in_bytes'] == pin['size'] and artifact['name'] == 'RPCS3Core-diagnostics-' + pin['source']
    assert artifact['workflow_run']['id'] == pin['run'] and artifact['workflow_run']['head_sha'] == pin['source']


def sum_assembly_names(name):
    assert name in ('ppu-sum-sanitized', 'ppu-sum-benchmark')
    directory = 'ppu-sum527-sanitized-asm' if name == 'ppu-sum-sanitized' else 'ppu-sum527-asm'
    return tuple(directory + '/' + operation + '-' + variant + '.s'
                 for operation in ('VSUM4UBS', 'VSUM4SBS', 'VSUM4SHS') for variant in ('before', 'after', 'fallback'))


def bundle(gate, download, pin=PIN1, cases=CASES):
    # Transport archives are intentionally outside the recursively uploaded
    # diagnostic directory. Keep tiny metadata records in the output instead.
    directory = gate.ROOT / ('build/cell527-evidence-cache/partial527-' + pin['label'])
    directory.mkdir(parents=True, exist_ok=True)
    path, metadata_path = directory / 'artifact.zip', directory / 'metadata.json'
    if download:
        def api(suffix):
            return json.loads(gate.command('gh', 'api', 'repos/TarbleFR/RewindBox/' + suffix))
        metadata = dict(run=api('actions/runs/' + str(pin['run'])), artifact=api('actions/artifacts/' + str(pin['artifact'])))
        metadata_contract(metadata, pin)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        if not path.is_file() or path.stat().st_size != pin['size'] or file_sha(path) != pin['sha256']:
            with path.open('wb') as stream:
                subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{pin['artifact']}/zip"],
                               cwd=gate.ROOT, stdout=stream, check=True, timeout=300)
    metadata = json.loads(metadata_path.read_bytes())
    metadata_contract(metadata, pin)
    assert path.stat().st_size == pin['size'] and file_sha(path) == pin['sha256']
    diagnostics = gate.ROOT / 'build/rpcs3-core-diagnostics'
    diagnostics.mkdir(parents=True, exist_ok=True)
    (diagnostics / ('evidence-partial527-' + pin['label'] + '-metadata.json')).write_bytes(metadata_path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        members = ['cell527-partial.json', 'cell527-proof.txt']
        members += [name + suffix for name in sorted(cases) for suffix in ('-result.json', '-output.txt')]
        if cases == CASES:
            members += [name.replace('ppu-simd-asm/', 'ppu-simd526-asm/') for name in PPU_ASM_SHA]
        else:
            assert cases == SECOND_CASES
            for name in ('ppu-sum-sanitized', 'ppu-sum-benchmark'):
                members += list(sum_assembly_names(name))
        files = {name: archive.read(name) for name in members}
    return files, sha(metadata_path.read_bytes())


def pool_command_contract(payload, *, sanitized):
    assert payload['compiler'] == 'Homebrew clang version 22.1.8'
    assert payload['passed'] is True and payload['sanitizers'] is sanitized
    for variant in ('before', 'after'):
        argv = payload['commands'][variant]
        assert argv[:4] == [COMPILER, '-isysroot', SDK, '-std=c++20']
        assert argv[4:11] == ['-O3', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-DRPCS3_IOS']
        assert len(argv) == (18 if sanitized else 16)
        assert argv[11].startswith('-I/var/folders/')
        assert argv[12] == '-I' + HISTORICAL_SOURCE_PATH
        assert argv[13] == HISTORICAL_ROOT + '/test/native/rpcs3_pool527.cpp'
        assert argv[14] == '-o' and argv[15].endswith('/' + variant + '-bin')
        if sanitized:
            assert argv[16:] == ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']


def toolchain_contract(files, environment):
    pool = json.loads(files['recyclable-pool-result.json'])
    bench = json.loads(files['recyclable-pool-benchmark-result.json'])
    ppu = json.loads(files['ppu-simd526-regression-result.json'])
    pool_command_contract(pool, sanitized=True)
    pool_command_contract(bench, sanitized=False)
    assert ppu['llvm_version'] == '22.1.8' and ppu['host_triple'] == 'arm64-apple-darwin24.6.0'
    expected = dict(llvm_version='22.1.8', compiler=COMPILER,
        compiler_version='Homebrew clang version 22.1.8', sdk=SDK,
        machine='arm64', kernel_release='24.6.0', hardware=ppu['hardware'])
    assert ppu['hardware'] == {'hw.model': 'VirtualMac2,1', 'machdep.cpu.brand_string': 'Apple M1 (Virtual)'}
    assert environment['toolchain'] == expected, 'Relevant historical compiler, SDK or hardware changed'
    return dict(relevant_toolchain=expected, relevant_toolchain_sha256=sha(canonical(expected)),
        full_historical_environment_captured=False,
        scope='Only compiler/SDK/hardware evidenced by original reports and unchanged workflow; full historical environment is unavailable')


def validate(files, metadata_sha, current_inputs, current_manifest, environment, historical_inputs, historical_manifest):
    prior = json.loads(files['cell527-partial.json'])
    assert prior['source'] == SOURCE and prior['physical_device_tested'] is False
    assert prior['all_tests_passed'] is False, 'This pin is an explicitly failed preflight'
    assert prior['input_sha256'] == historical_inputs
    assert sha(files['cell527-proof.txt']) == prior['log_sha256']
    assert prior['native_source_sha256'] == historical_manifest['files_sha256'] == current_manifest['files_sha256'], 'Native source changed'
    assert historical_manifest['upstream_commit'] == current_manifest['upstream_commit']
    assert set(historical_inputs) <= set(current_inputs)
    assert set(current_inputs) - set(historical_inputs) <= ADDED_INPUTS
    changed = {path for path in historical_inputs if current_inputs[path] != historical_inputs[path]}
    assert changed <= MUTABLE_INPUTS, 'Unreviewed changed inputs: ' + str(sorted(changed - MUTABLE_INPUTS))
    # New orchestration metadata/test is admitted, never a different native
    # policy, codegen identity, production patch or existing test command.
    old_record, new_record = historical_manifest['cell527'], current_manifest['cell527']
    assert set(old_record['extra_inputs']) <= set(new_record['extra_inputs'])
    assert set(new_record['extra_inputs']) - set(old_record['extra_inputs']) <= ADDED_INPUTS
    old_specs, new_specs = ({row['name']: row for row in value['tests']} for value in (old_record, new_record))
    assert set(old_specs) <= set(new_specs)
    assert all(new_specs[name] == spec for name, spec in old_specs.items())
    assert all(spec['script'] == SELFTEST for name, spec in new_specs.items() if name not in old_specs)
    expected_record = dict(old_record, extra_inputs=new_record['extra_inputs'], tests=new_record['tests'])
    assert new_record == expected_record
    expected_manifest = dict(historical_manifest, cell527=new_record)
    assert current_manifest == expected_manifest, 'Canonical source/options changed'
    tools = toolchain_contract(files, environment)
    admitted = {}
    for name in sorted(CASES):
        state = prior['tests'][name]
        assert state['status'] == 'passed' and state['returncode'] == 0 and state['executed_here'] is True
        assert 'reused_from' not in state, 'Transitive partial reuse forbidden'
        assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
        expected_command = ['python3', old_specs[name]['script'], HISTORICAL_SOURCE_PATH,
            *old_specs[name].get('args', []), '--report', HISTORICAL_ROOT + '/build/rpcs3-core-diagnostics/' + state['report']]
        assert state['command'] == expected_command, 'Original native command changed'
        report, output = files[state['report']], files[state['output']]
        assert sha(report) == state['report_sha256'] and sha(output) == state['output_sha256']
        payload = json.loads(report)
        assert payload.get('passed') is not False and payload.get('result') not in ('failed', 'failure', 'error')
        assert 'reused_validation' not in payload
        if name == 'ppu-simd526-regression':
            assert payload['game_or_device_tested'] is False and payload['cases_per_operation'] == 75941
            assert payload['production_translator_sha256'] == current_manifest['files_sha256']['rpcs3/Emu/Cell/PPUTranslator.cpp']
            assert payload['production_helper_sha256'] == current_manifest['files_sha256']['rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h']
            assert payload['before_fixture_sha256'] == current_inputs['test/fixtures/rpcs3_ppu_dot526_before.inc']
            assert len(payload['operations']) == 4 and all(row['bit_exact'] and row['big_endian_exact'] for row in payload['operations'])
            hardware = payload['dotprod_hardware_proof']
            assert hardware['hardware_verified'] is True and hardware['explicit_udot_controls'] == 5
        else:
            assert payload['after_sha256'] == current_manifest['files_sha256']['rpcs3/Emu/RSX/VK/VKTextureCache.cpp']
            assert payload['fixture_sha256'] == current_inputs['test/fixtures/rpcs3_pool527.diff']
        provenance = dict(source=SOURCE, run=RUN, artifact=ARTIFACT, archive_sha256=SHA,
            archive_bytes=BYTES, metadata_sha256=metadata_sha, partial_receipt_sha256=sha(files['cell527-partial.json']),
            original_report_sha256=state['report_sha256'], original_output_sha256=state['output_sha256'],
            individually_passed=True, container_conclusion='failure', core_built=False,
            toolchain=tools, current_environment_sha256=sha(canonical(environment)),
            source_scope='All native sources identical; only unrelated failed harnesses and controller metadata may differ')
        item = dict(report=report, output=output, provenance=provenance)
        if name == 'ppu-simd526-regression':
            assembly = {path.replace('ppu-simd-asm/', 'ppu-simd526-asm/'): digest for path, digest in PPU_ASM_SHA.items()}
            assert all(sha(files[path]) == digest for path, digest in assembly.items())
            item['artifacts'] = {path: files[path] for path in assembly}
            provenance['assembly_sha256'] = assembly
        admitted[name] = item
    return admitted


def admitted(gate, current_inputs, environment, download):
    files, metadata_sha = bundle(gate, download)
    prior = json.loads(files['cell527-partial.json'])
    historical_inputs = {path: sha(gate.command('git', 'show', SOURCE + ':' + path)) for path in prior['input_sha256']}
    historical_manifest = json.loads(gate.command('git', 'show', SOURCE + ':build-utils/rpcs3/canonical-source.json'))
    # Use the already source-pinned526 assembly table; all12 outputs are equal
    # and are nevertheless checked independently against the527 transport.
    assert PPU_ASM_SHA == gate.previous.PPU_ASM_SHA
    return validate(files, metadata_sha, current_inputs, gate.manifest(), environment, historical_inputs, historical_manifest)


def validate_second(files, metadata_sha, current_inputs, current_manifest, environment,
                    historical_inputs, historical_manifest):
    prior = json.loads(files['cell527-partial.json'])
    assert prior['source'] == SECOND_SOURCE and prior['physical_device_tested'] is False
    assert prior['all_tests_passed'] is False, 'Attempt2 remains an explicitly failed preflight'
    assert prior['input_sha256'] == historical_inputs
    assert sha(files['cell527-proof.txt']) == prior['log_sha256']
    assert prior['native_source_sha256'] == current_manifest['files_sha256'] == historical_manifest['files_sha256']
    assert current_manifest == historical_manifest, 'Attempt2 native policy/registry changed'
    assert set(current_inputs) == set(historical_inputs), 'Attempt2 input set changed'
    changed = {path for path in historical_inputs if current_inputs[path] != historical_inputs[path]}
    assert changed <= SECOND_MUTABLE_INPUTS, 'Attempt2 reused harness/dependency changed: ' + str(sorted(changed - SECOND_MUTABLE_INPUTS))
    assert prior['environment'] == environment, 'Attempt2 full captured environment changed'
    assert prior['environment_sha256'] == sha(canonical(environment)), 'Attempt2 environment fingerprint invalid'
    specs = {entry['name']: entry for entry in current_manifest['cell527']['tests']}
    admitted = {}
    for name in sorted(SECOND_CASES):
        state = prior['tests'][name]
        assert state['status'] == 'passed' and state['returncode'] == 0 and state['executed_here'] is True
        assert 'reused_from' not in state, 'Attempt2 transitive partial reuse forbidden'
        assert state['report'] == name + '-result.json' and state['output'] == name + '-output.txt'
        expected_command = ['python3', specs[name]['script'], HISTORICAL_SOURCE_PATH,
            *specs[name].get('args', []), '--report', HISTORICAL_ROOT + '/build/rpcs3-core-diagnostics/' + state['report']]
        assert state['command'] == expected_command, 'Attempt2 original case command changed'
        report, output = files[state['report']], files[state['output']]
        assert sha(report) == state['report_sha256'] and sha(output) == state['output_sha256']
        payload = json.loads(report)
        assert payload.get('passed') is not False and payload.get('result') not in ('failed', 'failure', 'error')
        assert 'reused_validation' not in payload
        provenance = dict(source=SECOND_SOURCE, run=SECOND_RUN, artifact=SECOND_ARTIFACT,
            archive_sha256=SECOND_SHA, archive_bytes=SECOND_BYTES, metadata_sha256=metadata_sha,
            partial_receipt_sha256=sha(files['cell527-partial.json']),
            original_report_sha256=state['report_sha256'], original_output_sha256=state['output_sha256'],
            individually_passed=True, container_conclusion='failure', core_built=False,
            full_historical_environment_captured=True, environment_sha256=prior['environment_sha256'],
            source_scope='All native sources, complete manifest and these exact harnesses unchanged; only JIT failure test/controller changed')
        item = dict(report=report, output=output, provenance=provenance)
        if name.startswith('ppu-sum-'):
            sanitized = name == 'ppu-sum-sanitized'
            assert payload['game_or_device_tested'] is False and payload['cases_per_operation'] == 76284
            assert payload['llvm_version'] == '22.1.8' and payload['sanitized_harness'] is sanitized
            assert payload['generated_code_sanitized'] is False
            assert payload['production_translator_sha256'] == current_manifest['files_sha256']['rpcs3/Emu/Cell/PPUTranslator.cpp']
            assert payload['production_helper_sha256'] == current_manifest['files_sha256']['rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h']
            assert payload['before_fixture_sha256'] == current_inputs['test/fixtures/rpcs3_ppu_sum527_before.inc']
            assert len(payload['operations']) == 3 and all(row['bit_exact'] and row['sticky_sat_exact'] and row['big_endian_exact'] for row in payload['operations'])
            if sanitized:
                control = payload['sanitizer_boundary_proof']
                assert all(control[key] is True for key in ('jit_function_metadata_check_exempt_only_at_invoke_jit',
                    'ordinary_indirect_function_check_present', 'signed_overflow_check_present', 'asan_load_check_present'))
            artifacts = {path: files[path] for path in sum_assembly_names(name)}
            item['artifacts'] = artifacts
            provenance['assembly_sha256'] = {path: sha(data) for path, data in artifacts.items()}
        else:
            assert name == 'runtime-metrics' and payload['passed'] is True and payload['sanitized'] is True
            assert payload['physical_device_tested'] is False
            assert payload['input_sha256'] == {path: current_manifest['files_sha256'][path]
                for path in ('rpcs3/ios/IOSRuntimeMetrics.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp')}
            cxx = shlex.split(environment['variables']['CXX'])
            assert payload['command'][:len(cxx)] == cxx and '-fsanitize=address,undefined' in payload['command']
            position = payload['command'].index('-isysroot')
            assert payload['command'][position + 1] == environment['variables']['HOST_MACOS_SDK']
        admitted[name] = item
    return admitted


def admitted_second(gate, current_inputs, environment, download):
    files, metadata_sha = bundle(gate, download, PIN2, SECOND_CASES)
    prior = json.loads(files['cell527-partial.json'])
    historical_inputs = {path: sha(gate.command('git', 'show', SECOND_SOURCE + ':' + path)) for path in prior['input_sha256']}
    historical_manifest = json.loads(gate.command('git', 'show', SECOND_SOURCE + ':build-utils/rpcs3/canonical-source.json'))
    return validate_second(files, metadata_sha, current_inputs, gate.manifest(), environment, historical_inputs, historical_manifest)
