#!/usr/bin/env python3
"""Check completed-Core proof admission, exact routing delta and provenance."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3cell527_success as reuse


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fixture():
    performance = b'\n'.join(b'"' + marker + b' session=%llu"' for marker in reuse.PREFIXES)
    current = performance
    for marker in reuse.PREFIXES:
        current = current.replace(b'"' + marker, b'"COREPROF ' + marker)
    native = {reuse.PERFORMANCE: sha(performance), 'Utilities/JITLLVM.cpp': 'same-jit-source'}
    old_inputs = {'test/rpcs3_jit_publication527_test.py': 'same-jit-harness',
        'build-utils/rpcs3/canonical-source.json': 'old-canonical', 'test/fixtures/rpcs3_cell527.diff': 'old-fixture',
        '.github/diagnostics/rpcs3cell527_core.py': 'old-controller'}
    names = sorted(reuse.CASES | {'runtime-metrics', 'native-gate', 'partial-reuse-gate'})
    specs = [dict(name=name, script='test/' + name + '.py', args=[], timeout=300) for name in names]
    old_manifest = dict(upstream_commit='upstream', patch_sha256='old-patch', policy='Original policy.', files_sha256=native,
        cell527=dict(extra_inputs=list(old_inputs), tests=specs, scope='Original scope.', fixture_sha256='old-fixture', codegen={'PPU':'same','SPU':'same'}))
    manifest = copy.deepcopy(old_manifest)
    manifest['files_sha256'][reuse.PERFORMANCE] = sha(current)
    manifest.update(patch_sha256='new-patch', policy='Original policy. Routing metadata.')
    record = manifest['cell527']
    record.update(scope='Original scope. Bounded routing.', fixture_sha256='new-fixture')
    record['extra_inputs'] += [reuse.SELFTEST, reuse.ROUTE_SCRIPT, reuse.ROUTE_NATIVE]
    record['tests'] += [dict(name='host-routing', script=reuse.ROUTE_SCRIPT, args=[], timeout=300),
                        dict(name='completed-core-reuse-gate', script=reuse.SELFTEST, args=[], timeout=120)]
    current_inputs = dict(old_inputs)
    current_inputs.update({path:'new-input' for path in reuse.ADDED_INPUTS})
    for path in reuse.MUTABLE_INPUTS & set(current_inputs):
        current_inputs[path] = 'current-' + path
    environment = dict(machine='arm64', platform='known-runner', variables=dict(CXX='same-compiler'))
    files, states, reports = {}, {}, {}
    for spec in specs:
        name = spec['name']
        nested = dict(run=12345, individually_passed=True, container_conclusion='failure') if name.startswith('ppu-') else None
        payload = dict(passed=True)
        if nested:
            payload['reused_validation'] = nested
        report, output = name + '-result.json', name + '-output.txt'
        files[report] = json.dumps(payload).encode()
        files[output] = (name + ' passed').encode()
        state = dict(status='passed', returncode=0, executed_here=nested is None, report=report, output=output,
            report_sha256=sha(files[report]), output_sha256=sha(files[output]),
            command=['python3', spec['script'], reuse.HISTORICAL_SOURCE_PATH, '--report',
                     reuse.HISTORICAL_ROOT + '/build/rpcs3-core-diagnostics/' + report])
        if nested:
            state['reused_from'] = nested
        states[name] = state
        reports[report] = state['report_sha256']
    asm = 'ppu-sum527-asm/VSUM4UBS-after.s'
    files[asm] = b'authenticated assembly'
    states['ppu-sum-benchmark']['artifacts_sha256'] = {asm:sha(files[asm])}
    files['cell527-proof.txt'] = b'whole native campaign log'
    partial = dict(source=reuse.SOURCE, all_tests_passed=True, physical_device_tested=False,
        input_sha256=old_inputs, native_source_sha256=native, tests=states, environment=environment,
        environment_sha256=sha(reuse.canonical(environment)), log_sha256=sha(files['cell527-proof.txt']))
    files['cell527-partial.json'] = json.dumps(partial).encode()
    proof = dict(source=reuse.SOURCE, all_tests_passed=True, physical_device_tested=False,
        input_sha256=old_inputs, native_source_sha256=native, environment=environment,
        environment_sha256=partial['environment_sha256'], reports_sha256=reports,
        log_sha256=partial['log_sha256'], partial_receipt_sha256=sha(files['cell527-partial.json']))
    identity = dict(host_commit=reuse.SOURCE, abi_version=30, architectures=['arm64'], sha256=reuse.CORE_DYLIB_SHA,
        device_runtime_tested=False, source_commit='upstream', source_patch_sha256='old-patch',
        cell527_input_sha256=old_inputs, core_input_sha256=old_inputs, native_source_sha256=native)
    files['cell527-reuse.json'] = json.dumps(proof).encode()
    files['identity.json'] = json.dumps(identity).encode()
    return [files, 'metadata-sha', current_inputs, manifest, environment, old_inputs, old_manifest, current]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    checks, base = 0, fixture()
    admitted = reuse.validate(*base)
    assert set(admitted) == reuse.CASES
    assert admitted['ppu-sum-benchmark']['provenance']['upstream_reused_validation']['run'] == 12345
    assert admitted['ppu-sum-benchmark']['provenance']['original_execution']['executed_here'] is False
    assert all(item['provenance']['core_binary_reused'] is False for item in admitted.values())
    checks += 4
    def reject(mutate):
        nonlocal checks
        value = copy.deepcopy(base)
        mutate(value)
        try:
            reuse.validate(*value)
        except (AssertionError, KeyError):
            checks += 1
            return
        raise AssertionError('Invalid completed-Core proof admitted')
    def edit_file(value, name, mutate):
        payload = json.loads(value[0][name])
        mutate(payload)
        value[0][name] = json.dumps(payload).encode()
    reject(lambda v: edit_file(v, 'identity.json', lambda p:p.update(sha256='other-core')))
    reject(lambda v: edit_file(v, 'cell527-reuse.json', lambda p:p.update(all_tests_passed=False)))
    reject(lambda v: v[4].update(platform='different-environment'))
    reject(lambda v: v[2].update({'test/rpcs3_jit_publication527_test.py':'changed-reused-harness'}))
    reject(lambda v: v[3]['files_sha256'].update({'Utilities/JITLLVM.cpp':'other-jit-source'}))
    reject(lambda v: v.__setitem__(7, v[7].replace(b'COREPROF FRAMEPROF527', b'FRAMEPROF527')))
    def extra_native_change(v):
        v[7] += b'\nnew computation'
        v[3]['files_sha256'][reuse.PERFORMANCE] = sha(v[7])
    reject(extra_native_change)
    reject(lambda v: v[3]['cell527']['tests'][0]['args'].append('--new-command'))
    reject(lambda v: v[0].update({'jit-publication-result.json':b'{"passed":false}'}))
    reject(lambda v: v[0].update({'runtime-metrics-output.txt':b'changed unused original component'}))
    reject(lambda v: v[0].update({'ppu-sum527-asm/VSUM4UBS-after.s':b'changed assembly'}))
    reject(lambda v: edit_file(v, 'cell527-partial.json', lambda p:p['tests']['jit-publication'].update(returncode=1)))
    metadata = dict(run=dict(id=reuse.RUN, head_sha=reuse.SOURCE, status='completed', conclusion='success'))
    for key, identifier, size, name, digest in (
        ('artifact', reuse.ARTIFACT, reuse.BYTES, 'RPCS3Core-diagnostics-' + reuse.SOURCE, reuse.SHA),
        ('core_artifact', reuse.CORE_ARTIFACT, reuse.CORE_BYTES, 'RPCS3Core-' + reuse.SOURCE, reuse.CORE_ARCHIVE_SHA)):
        metadata[key] = dict(id=identifier, expired=False, size_in_bytes=size, name=name,
            digest='sha256:'+digest, workflow_run=dict(id=reuse.RUN, head_sha=reuse.SOURCE))
    reuse.metadata_contract(metadata)
    checks += 1
    for mutate in (lambda v:v['run'].update(conclusion='failure'), lambda v:v['core_artifact'].update(digest='sha256:wrong'),
                   lambda v:v['artifact'].update(expired=True)):
        value=copy.deepcopy(metadata);mutate(value)
        try:
            reuse.metadata_contract(value)
        except AssertionError:
            checks += 1
        else:
            raise AssertionError('Invalid successful-Core metadata admitted')
    report = dict(passed=True, checks=checks, reusedComponents=sorted(reuse.CASES),
        changedNativeOnlyFourRoutingPrefixes=True, completeNineReportProofChecked=True,
        originalNestedProvenancePreserved=True, oldCoreBinaryReused=False, physicalDeviceTested=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__=='__main__':
    main()
