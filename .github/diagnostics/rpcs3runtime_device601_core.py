#!/usr/bin/env python3
"""Follow up device601 logs without replaying the unchanged device597 suite.

The local source contract authenticates historical receipts, not unavailable
Apple artifacts. A future authorized native build additionally authenticates
the original archives, then executes only the new affected regression modes.
No command in this module dispatches CI, pushes code or publishes a release.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

import rpcs3runtime_device597_core as support

ROOT = support.ROOT
OUT = support.OUT
PROOF = support.PROOF
KEY = 'device601_20261030'
GATE = '.github/diagnostics/rpcs3runtime_device601_core.py'
RECORD = 'docs/evidence/rpcs3-device601-20261030/source-contract.json'
DELTA = 'test/fixtures/rpcs3_device601.diff'
BASE = 'f41eb5ef4ce87cab08a18781c2e09a55a8319773'
HIST = '378509e82d360bc2cb2fcc9fb23d4d9d98787506'
RECEIPT = 'docs/evidence/rpcs3-device597-20261030/apple-core.json'
CODEGEN = 'docs/evidence/rpcs3-device597-20261030/cpu/codegen-review-final.json'
HOST_CODEGEN = 'test/rpcs3_device601_codegen_test.py'
HOST_CODEGEN_REPORT = 'docs/evidence/rpcs3-device601-20261030/cpu/decrementer-codegen.json'
MANIFEST = support.MANIFEST
PATCH = support.PATCH
ROUTE = support.ROUTE
WORKFLOW = support.WORKFLOW
BUILD = support.BUILD
ROUTE_BLOCK = '''    if 'device601_20261030' in manifest():
        # New affected tests only; preserve device597's historical Apple scope.
        import rpcs3runtime_device601_core as device601
        if a.write_core_identity:
            device601.identity(a.write_core_identity)
        elif a.source and a.verify_reuse:
            device601.verify(a.verify_reuse, a.source.resolve())
        elif a.source:
            device601.prepare(a.source.resolve())
        else:
            p.error('device601 follow-up requires --source or --write-core-identity')
        raise SystemExit
'''
require, sha, file_sha, load, save = support.require, support.sha, support.file_sha, support.load, support.save
command, at, relative_file = support.command, support.at, support.relative_file


def map_contract(manifest, baseline, record):
    require(baseline['patch_sha256'] == '68234e0ead31d40c61c2b3b29c0c962f89d8687407e0cc60eb45d60b68dd71e8'
            and len(baseline['files_sha256']) == 325, 'Wrong compiled device597 baseline')
    require(manifest['upstream_commit'] == baseline['upstream_commit'], 'Upstream changed')
    changes = record['native_changes']
    require(isinstance(changes, dict) and changes, 'Empty native change set')
    expected = dict(baseline['files_sha256'])
    for name, entry in changes.items():
        if name in expected:
            require(entry['before'] == expected[name] and 'upstream_preimage_blob' not in entry, 'Wrong baseline native hash: ' + name)
        else:
            require(isinstance(entry.get('upstream_preimage_blob'), str) and len(entry['upstream_preimage_blob']) == 40,
                    'New canonical path requires its pinned upstream preimage: ' + name)
        require(entry['after'] != entry['before'], 'Unchanged native path declared changed: ' + name)
        expected[name] = entry['after']
    require(manifest['files_sha256'] == expected, 'Native change outside reviewed paths or wrong postimage')
    expected_manifest = dict(baseline, files_sha256=expected, patch_sha256=record['canonical_patch_sha256'])
    suffix = record['policy_append']
    require(isinstance(suffix, str) and suffix.startswith(' Device601 log follow-up (30 October 2026):'), 'Unreviewed policy note')
    expected_manifest['policy'] = baseline['policy'] + suffix
    expected_manifest[KEY] = manifest.get(KEY)
    require(manifest == expected_manifest, 'Unrelated canonical metadata changed')
    require(manifest['patch_sha256'] == record['canonical_patch_sha256'], 'Unreviewed canonical patch')


def source_contract(source, baseline_out=None):
    record = load(ROOT / RECORD)
    manifest = load(ROOT / MANIFEST)
    require(record['phase'] == 'reboot-timer-feedback', 'Wrong follow-up source phase')
    baseline = json.loads(at(BASE, MANIFEST))
    require(record['baseline_app_commit'] == BASE and record['historical_core_source'] == HIST, 'Wrong reference commits')
    require(manifest.get(KEY) == {'source_contract': RECORD, 'source_contract_sha256': file_sha(ROOT / RECORD)},
            'Manifest does not bind this source contract')
    map_contract(manifest, baseline, record)
    require(file_sha(ROOT / PATCH) == manifest['patch_sha256'], 'Canonical patch bytes changed')
    require(command('git', '-C', source, 'rev-parse', 'HEAD').decode().strip() == manifest['upstream_commit'], 'Wrong upstream checkout')
    for name, entry in record['native_changes'].items():
        if name not in baseline['files_sha256']:
            blob = command('git', '-C', source, 'rev-parse', 'HEAD:' + name).decode().strip()
            require(blob == entry['upstream_preimage_blob'] and sha(command('git', '-C', source, 'show', 'HEAD:' + name)) == entry['before'],
                    'Wrong pinned upstream preimage: ' + name)
    for name, digest in manifest['files_sha256'].items():
        require(sha(relative_file(source, name).read_bytes().replace(b'\r\n', b'\n')) == digest, 'Wrong native postimage: ' + name)
    for name in (WORKFLOW, BUILD):
        require((ROOT / name).read_bytes() == at(BASE, name), 'Build recipe changed: ' + name)
    old_route = at(BASE, ROUTE).decode()
    anchor = "    if 'device597_20261030' in manifest():\n"
    require(old_route.count(anchor) == 1 and (ROOT / ROUTE).read_text() == old_route.replace(anchor, ROUTE_BLOCK + anchor, 1),
            'Dispatcher changed beyond the leading follow-up route')
    for name, digest in record['repository_inputs'].items():
        require(file_sha(relative_file(ROOT, name)) == digest, 'Repository input changed: ' + name)
    require((ROOT / RECEIPT).read_bytes() == at(BASE, RECEIPT), 'Historical Apple receipt changed')
    receipt = load(ROOT / RECEIPT)
    require(receipt['source'] == HIST and receipt['canonicalPatchSHA256'] == baseline['patch_sha256']
            and receipt['validation']['freshAppleNativeModes'] == 28
            and receipt['validation']['allPassed'] is True, 'Wrong historical Apple attestation')
    # A new SPU host-only alias needs its own exact body/recipe proof; all
    # other physical identity inputs must still equal the historical inputs.
    codegen = load(ROOT / CODEGEN)
    require((ROOT / CODEGEN).read_bytes() == at(BASE, CODEGEN), 'Historical codegen proof changed')
    for name, entry in codegen['inputs'].items():
        if name in codegen['externalInputs']:
            require(entry['before'] == entry['after'], 'External LLVM input changed')
        else:
            expected = record['native_changes']['rpcs3/Emu/Cell/SPUThread.cpp']['after'] if name == 'Cell/SPUThread.cpp' else entry['after']
            require(file_sha(source / 'rpcs3/Emu' / name) == expected, 'Codegen input changed: ' + name)
    for name in ('rpcs3/Emu/CMakeLists.txt',
                 'rpcs3/ios/RPCS3IOS.exports', 'rpcs3/ios/RPCS3IOS.h'):
        require(manifest['files_sha256'][name] == baseline['files_sha256'][name], 'Codegen/ABI boundary changed: ' + name)
    exports = sorted((source / 'rpcs3/ios/RPCS3IOS.exports').read_text().split())
    require(len(exports) == len(set(exports)) == 88, 'ABI surface changed')
    # Invert only this small lot. Baseline test trees need no full clone or rebuild.
    require(file_sha(ROOT / DELTA) == record['delta_sha256'], 'Follow-up delta changed')
    with tempfile.TemporaryDirectory(prefix='rpcs3-followup-inverse-') as tmp:
        before = Path(tmp)
        for name, entry in record['baseline_support'].items():
            raw = relative_file(source, name).read_bytes()
            blob = command('git', '-C', source, 'rev-parse', 'HEAD:' + name).decode().strip()
            require(sha(raw) == entry['sha256'] and blob == entry['upstream_blob'] and
                    sha(command('git', '-C', source, 'show', 'HEAD:' + name)) == entry['sha256'], 'Unchanged baseline support changed: ' + name)
        for name in set(manifest['files_sha256']) | set(record['baseline_support']):
            destination = before / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((source / name).read_bytes())
        support.run(['git', 'apply', '--reverse', '--unsafe-paths', '--directory', before, ROOT / DELTA],
                    OUT / 'device601-inverse-delta.txt')
        for name, entry in record['native_changes'].items():
            require(file_sha(before / name) == entry['before'], 'Inverse delta misses compiled baseline: ' + name)
        sys.path.insert(0, str(ROOT / 'test'))
        import rpcs3_device601_codegen_test as host_codegen
        reproduced = host_codegen.audit(source, before, ROOT)
        require(reproduced == load(ROOT / HOST_CODEGEN_REPORT), 'Host-only alias/codegen audit changed')
        require(record['host_codegen_audit'] == {'runner': HOST_CODEGEN, 'report': HOST_CODEGEN_REPORT,
                                               'report_sha256': file_sha(ROOT / HOST_CODEGEN_REPORT)}, 'Wrong host codegen audit binding')
        if baseline_out is not None:
            shutil.copytree(before, baseline_out)
    inputs = {name: file_sha(ROOT / name) for name in record['repository_inputs']}
    for name in (RECORD, MANIFEST, PATCH):
        inputs[name] = file_sha(ROOT / name)
    return manifest, record, inputs, exports, reproduced['codegen']


def historical_archives(download=False):
    """Verify real original Apple reports when building, never on local source review."""
    receipt = load(ROOT / RECEIPT)
    directory = OUT / 'reference-device597'
    directory.mkdir(parents=True, exist_ok=True)
    archives = {}
    for key, label in [('artifact', 'core'), ('diagnosticsArtifact', 'diagnostics')]:
        expected = receipt[key]
        path = directory / (label + '.zip')
        if download and not path.exists():
            with path.open('wb') as output:
                import subprocess
                subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{expected['id']}/zip"],
                               cwd=ROOT, stdout=output, check=True, timeout=300)
        require(path.is_file() and path.stat().st_size == expected['bytes'] and file_sha(path) == expected['sha256'],
                'Original Apple archive missing or changed: ' + label)
        archives[label] = path
    with zipfile.ZipFile(archives['core']) as core, zipfile.ZipFile(archives['diagnostics']) as diagnostics:
        require(core.testzip() is None and diagnostics.testzip() is None, 'Historical ZIP CRC failure')
        identity_raw, proof_raw = core.read('identity.json'), core.read('runtime592-proof.json')
        require(sha(identity_raw) == receipt['core']['identitySHA256']
                and sha(proof_raw) == receipt['core']['proofSHA256'], 'Historical identity/proof changed')
        require(diagnostics.read('identity.json') == identity_raw and diagnostics.read('runtime592-proof.json') == proof_raw,
                'Original archives disagree on proof')
        require(sha(core.read('libRPCS3Core.dylib')) == receipt['core']['sha256'], 'Historical binary changed')
        proof = json.loads(proof_raw)
        require(proof['source'] == HIST and proof['all_tests_passed'] is True, 'Historical Apple run did not pass')
        old_manifest = json.loads(at(BASE, MANIFEST))
        require(proof['native_source_sha256'] == old_manifest['files_sha256']
                and proof['source_patch_sha256'] == old_manifest['patch_sha256'], 'Historical native source mismatch')
        for name, digest in proof['input_sha256'].items():
            require(sha(at(HIST, name)) == digest, 'Historical repository input changed: ' + name)
        jobs = old_manifest['device597_20261030']['apple_validation']['jobs']
        require(set(proof['tests']) == {job['name'] for job in jobs}, 'Historical modes incomplete')
        native = 0
        for job in jobs:
            item = proof['tests'][job['name']]
            require(item['passed'] is True and item['returncode'] == 0
                    and item['spec_sha256'] == sha(json.dumps(job, sort_keys=True).encode()), 'Historical job mismatch')
            for member in ('report', 'output', 'compile_trace'):
                require(sha(diagnostics.read(item[member])) == item[member + '_sha256'], 'Historical job artifact mismatch')
            support.check_report(json.loads(diagnostics.read(item['report'])), job)
            native += item['native_executed_now'] is True
        require(native == 28, 'Historical native execution count changed')
    return dict(source=HIST, run=receipt['run'], original_native_modes=28, native_executed_now=0,
                receipt_sha256=file_sha(ROOT / RECEIPT), archives_authenticated=True,
                validates_new_paths=False, old_binary_reused=False)


def jobs(record):
    result = record['apple_validation_jobs']
    require(result and len({job['name'] for job in result}) == len(result), 'Missing or duplicate new jobs')
    for job in result:
        require(job['mode'] in ('plain', 'asan-ubsan') and job['argv'][0] == 'python3'
                and job['argv'][1].replace('{repo}/', '') in record['repository_inputs'], 'Unbound native runner')
    return result


def prepare(source):
    compiler, version = support.compiler_identity()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='device601-baseline-') as tmp:
        baseline = Path(tmp) / 'baseline'
        manifest, record, inputs, exports, codegen = source_contract(source, baseline)
        wrapper = OUT / 'device601-cxx-wrapper.py'
        wrapper.write_text(support.WRAPPER_SOURCE)
        wrapper.chmod(0o755)
        proof = dict(schema=1, type=KEY, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
                     source_root=str(source), baseline_root=str(baseline), source_patch_sha256=manifest['patch_sha256'],
                     native_source_sha256=manifest['files_sha256'], input_sha256=inputs, exported_symbols=exports,
                     codegen=codegen, historical=historical_archives(download=True),
                     upstream_dependencies=support.upstream_dependencies(source, manifest),
                     host={'system': 'Darwin', 'machine': 'arm64', 'compiler': version, 'compiler_argv': compiler},
                     tests={}, all_tests_passed=False, physical_device_tested=False, gameplay_measured=False, public_release=False,
                     neoswap_host_component_packaged=False)
        save(PROOF, proof)
        for job in jobs(record):
            directory = OUT / 'device601' / job['name']
            directory.mkdir(parents=True, exist_ok=True)
            values = dict(repo=str(ROOT), source=str(source), baseline=str(baseline), output=str(directory))
            argv = [support.expand(arg, values) for arg in job['argv']]
            report = Path(support.expand(job['report'], values))
            require(report.resolve().is_relative_to(directory.resolve()), 'Native report escapes output')
            report.unlink(missing_ok=True)
            trace = directory / 'compiler.jsonl'
            trace.write_text('')
            env = dict(os.environ, CXX=str(wrapper), RPCS3_DEVICE597_REAL_CXX=json.dumps(compiler),
                       RPCS3_DEVICE597_CXX_TRACE=str(trace), RPCS3_DEVICE597_COMPILE_INPUTS=str(directory / 'compiled-inputs'),
                       ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1', PYTHONOPTIMIZE='0')
            log = directory / 'output.txt'
            support.run(argv, log, env, 900)
            support.check_report(load(report), job)
            count = support.check_compile_trace(trace, job, compiler)
            item = dict(passed=True, mode=job['mode'], argv=argv, native_executed_now=True, compile_count=count)
            for member, path in [('report', report), ('output', log), ('compile_trace', trace)]:
                item[member] = str(path.relative_to(OUT))
                item[member + '_sha256'] = file_sha(path)
            proof['tests'][job['name']] = item
            save(PROOF, proof)
        proof['all_tests_passed'] = True
        save(PROOF, proof)
    verify(PROOF, source)


def verify(path, source):
    proof = load(path)
    manifest, record, inputs, exports, codegen = source_contract(source)
    require(proof['schema'] == 1 and proof['type'] == KEY and proof['all_tests_passed'] is True, 'Wrong/incomplete native proof')
    require(proof['source'] == command('git', 'rev-parse', 'HEAD').decode().strip(), 'Proof source commit changed')
    require(proof['source_patch_sha256'] == manifest['patch_sha256'] and proof['native_source_sha256'] == manifest['files_sha256']
            and proof['input_sha256'] == inputs and proof['codegen'] == codegen and proof['exported_symbols'] == exports, 'Proof source closure changed')
    require(proof['historical'] == historical_archives(), 'Historical archive authentication changed')
    require(proof['upstream_dependencies'] == support.upstream_dependencies(source, manifest), 'Upstream support changed')
    require(all(proof[key] is False for key in ('physical_device_tested', 'gameplay_measured', 'public_release', 'neoswap_host_component_packaged')), 'Mis-scoped proof')
    require(proof['host']['system'] == 'Darwin' and proof['host']['machine'] == 'arm64'
            and re.search(r'clang version 22\.', proof['host']['compiler']), 'Wrong native host/compiler')
    require(set(proof['tests']) == {job['name'] for job in jobs(record)}, 'New native modes incomplete')
    for job in jobs(record):
        item = proof['tests'][job['name']]
        require(item['passed'] is True and item['mode'] == job['mode'] and item['native_executed_now'] is True, 'Native mode changed')
        values = dict(repo=str(ROOT), source=proof['source_root'], baseline=proof['baseline_root'],
                      output=str(OUT / 'device601' / job['name']))
        require(item['argv'] == [support.expand(arg, values) for arg in job['argv']], 'Native command changed')
        for member in ('report', 'output', 'compile_trace'):
            require(file_sha(relative_file(OUT, item[member])) == item[member + '_sha256'], 'Native artifact changed')
        support.check_report(load(OUT / item['report']), job)
        require(support.check_compile_trace(OUT / item['compile_trace'], job, proof['host']['compiler_argv']) == item['compile_count'],
                'Native compiler observations changed')
    print('PASS device601: new native modes only; historical 28 Apple modes not replayed; no device result')
    return proof


def identity(directory):
    # Reuse the mature ABI/actual-binary inspection, not its frozen source gate.
    # The function reads these names in its own module; avoid global mutation by
    # retaining the explicit small binary boundary here.
    proof = verify(PROOF, Path(load(PROOF)['source_root']))
    sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
    from verify_ipa import macho
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test as pin
    data = (directory / 'libRPCS3Core.dylib').read_bytes()
    require(macho(data)['platform'] == 2 and set(macho(data)['definedSymbols']) == set(proof['exported_symbols']), 'Wrong iPhone ABI/exports')
    require(command('lipo', '-archs', directory / 'libRPCS3Core.dylib').decode().strip() == 'arm64', 'Wrong architecture')
    require((directory / 'RPCS3_IOS_ABI.txt').read_text().strip() == '30', 'Wrong ABI version')
    manifest = load(ROOT / MANIFEST)
    require((directory / 'RPCS3_SOURCE_COMMIT.txt').read_text().strip() == manifest['upstream_commit'], 'Wrong upstream identity')
    log = (OUT / 'build.log').read_text()
    for kind, expected in proof['codegen'].items():
        import re
        require(re.findall('NeoStation ' + kind + r' codegen identity: ([0-9a-f]{16})', log) == [expected], 'Compiled codegen identity changed')
    for hook in ('MoltenVK compile QoS hook linked', 'MoltenVK encoding-queue hook linked'):
        require(hook in log, 'Missing MoltenVK hook')
    archive = manifest['cell587']['moltenvk_archive']
    require(archive['input_sha256'] + ' -> ' + archive['patched_sha256'] in log, 'Wrong MoltenVK archive transform')
    require(not {'_rbx_mvk_compile_qos_queue', '_rbx_mvk_exec_q_create'} & set(command('nm', '-u', directory / 'libRPCS3Core.dylib').decode().split()), 'Unresolved MoltenVK hook')
    item = dict(schema_version=1, type='rpcs3-ios-device601-followup', host_commit=proof['source'], native_source_commit=proof['source'],
                source_commit=manifest['upstream_commit'], sha256=sha(data), abi_version=30, architectures=['arm64'],
                source_patch_sha256=manifest['patch_sha256'], core_input_sha256=pin.core_input_hashes(),
                device601_input_sha256=proof['input_sha256'], native_source_sha256=manifest['files_sha256'],
                exported_symbols=proof['exported_symbols'], codegen=proof['codegen'], physical_device_tested=False,
                gameplay_measured=False, public_release=False, neoswap_host_component_packaged=False)
    save(directory / 'identity.json', item)
    save(OUT / 'identity.json', item)
    shutil.copyfile(PROOF, directory / PROOF.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--verify-reuse', type=Path)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--write-core-identity', type=Path)
    args = parser.parse_args()
    if args.source_only:
        manifest, record, inputs, exports, codegen = source_contract(args.source.resolve())
        print(json.dumps(dict(passed=True, phase=record['phase'], current_postimages=len(manifest['files_sha256']), changed_paths=sorted(record['native_changes']),
                              codegen=codegen, abi_exports=len(exports), historical_receipt_authenticated=True,
                              historical_archives_authenticated=False, native_executed_now=0, apple_executed_now=0), indent=2))
    elif args.write_core_identity:
        identity(args.write_core_identity)
    elif args.verify_reuse:
        verify(args.verify_reuse, args.source.resolve())
    else:
        prepare(args.source.resolve())
