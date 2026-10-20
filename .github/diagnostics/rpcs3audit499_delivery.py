"""Build 499: exact Build 498 product plus the rebuilt, independently proved SPU Core.

Read successful evidence for unchanged Dart, native hosts and other cores.
Never normalize or rewrite this newly built Core's authentic input identity.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'ef8b4b9db09ac142e801ee43e65221261d49cae4'
DELIVERED = '69176e02b6e2133075b2745dd06d6a70316674a4'
DELIVERED_RUN = 39464441422
CORE_SOURCE = '{{CORE_SOURCE}}'
CORE_RUN = '{{CORE_RUN}}'
FINAL_SOURCE = '{{FINAL_SOURCE}}'
PRODUCT = ['lib', 'assets', 'packages', 'native', 'ios', 'pubspec.yaml', 'pubspec.lock', 'build-utils/libretro']
ALLOWED = {'AGENTS.md', '.github/workflows/rpcs3-core.yml', '.github/workflows/rpcs3-audit-delivery.yml',
    '.github/workflows/retroarch-delivery.yml', '.github/workflows/neoswap-ipa.yml',
    '.github/diagnostics/rpcs3audit499_delivery.py', 'build-utils/delivery-499-recipient.pem',
    'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
    'test/neo_swap_core_pin_test.py', 'test/rpcs3_build487_core_diagnostics_test.py',
    'test/rpcs3_build499_spu_audit_test.py', 'test/native/rpcs3_build499_spu_audit_test.cpp'}


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def api(path):
    return json.loads(command(['gh', 'api', 'repos/TarbleFR/neostation-ios/' + path]))


def core_module():
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test
    return neo_swap_core_pin_test


@contextmanager
def rpc_core_input_view(pin):
    assert pin == CORE_SOURCE, 'Unexpected new Core pin'
    yield core_module(), ROOT


def validate_rpc_core_identity(identity):
    assert identity['host_commit'] == CORE_SOURCE
    core_module().validate_core_input_identity(identity)


def validate_rpc_core_pin(pin, paths):
    assert pin == CORE_SOURCE
    core = core_module()
    assert len(paths) == len(core.CORE_INPUTS) and set(paths) == set(core.CORE_INPUTS)
    core.validate_source_contract()
    core.validate_exact_pin(pin)
    print('PASS: every authentic Build 499 Core input and file mode matches its successful build')


def validate_psp_core_identity(identity, root):
    from hdnative498_delivery import validate_psp_core_identity as validate
    validate(identity, root)


def successful(run_id, sha, names):
    run = api(f'actions/runs/{run_id}')
    assert run['head_sha'] == sha and run['status'] == 'completed' and run['conclusion'] == 'success', run
    jobs = api(f'actions/runs/{run_id}/jobs?per_page=100')['jobs']
    for name in names:
        matches = [job for job in jobs if job['name'] == name]
        assert len(matches) == 1 and matches[0]['conclusion'] == 'success', name
    return {'source': sha, 'run': run_id, 'jobs': names, 'conclusion': 'success'}


def source_closure():
    source = os.environ.get('HD_FINAL_SOURCE', FINAL_SOURCE)
    assert len(source) == 40 and command(['git', 'rev-parse', 'HEAD']) == source
    for end in (['HEAD'], []):
        command(['git', 'diff', '--exit-code', BASE, *end, '--', *PRODUCT])
        changed = command(['git', 'diff', '--name-only', BASE, *end]).splitlines()
        assert all(path in ALLOWED or path.startswith('docs/') for path in changed), changed
    original = json.loads(command(['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json']))
    current = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_text())
    changed_core = set(current['optimizations_499']['changed_core_files'])
    assert changed_core == {'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp', 'rpcs3/Emu/Cell/SPUThread.cpp', 'rpcs3/Emu/CMakeLists.txt'}
    assert set(original['files_sha256']) == set(current['files_sha256'])
    differences = {name for name, digest in original['files_sha256'].items() if current['files_sha256'][name] != digest}
    assert differences == changed_core
    protected = {name: digest for name, digest in original['files_sha256'].items() if name not in changed_core}
    assert current['optimizations_499']['unchanged_core_files_sha256'] == protected
    core_module().validate_source_contract()
    core_module().validate_exact_pin(CORE_SOURCE)
    return {'source': source, 'baseline': BASE, 'productInputsByteIdenticalTo498': True,
        'changedCoreFiles': sorted(changed_core), 'unchangedCanonicalCoreFiles': len(protected),
        'coreABI': 30, 'neoSwapHostAndCoreClientsUnchanged': True, 'rebuiltCores': ['RPCS3']}


def core_evidence():
    record = successful(int(CORE_RUN), CORE_SOURCE, ['RPCS3 Core arm64 with NeoSwap client'])
    artifacts = api(f'actions/runs/{CORE_RUN}/artifacts?per_page=100')['artifacts']
    matches = [a for a in artifacts if a['name'] == 'RPCS3Core-diagnostics-' + CORE_SOURCE and not a['expired']]
    assert len(matches) == 1, 'Core diagnostic artifact is missing or ambiguous'
    with tempfile.TemporaryDirectory(prefix='rpcs3-499-proof-') as tmp:
        path = Path(tmp) / 'diagnostics.zip'
        with path.open('wb') as handle:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/neostation-ios/actions/artifacts/{matches[0]['id']}/zip"], stdout=handle, check=True)
        with zipfile.ZipFile(path) as archive:
            for name, needle in [('build499-proof.txt', 'PASS: Build 499 SHUFB masks'),
                ('spu-object-cache-proof.txt', 'PASS'), ('llvm-pipeline-proof.txt', 'PASS'),
                ('build487-core-proof.txt', 'PASS'), ('build487-host-proof.txt', 'PASS')]:
                text = archive.read(name).decode()
                assert needle in text, name
            identity = json.loads(archive.read('identity.json'))
            validate_rpc_core_identity(identity)
            record.update(artifact=matches[0]['id'], archiveSHA256=hashlib.sha256(path.read_bytes()).hexdigest(),
                coreSHA256=identity['sha256'], patchSHA256=identity['source_patch_sha256'],
                newSPUBehaviourProof=True, cacheRelocationProof=True, llvmPipelineProof=True)
    return record


def final_ipa(path, build):
    assert build == 499
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from validate_hd_textures_ipa import validate
    result = validate(path, build)
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith('/Frameworks/RPCS3Core.framework/RPCS3Core'))
        assert b'SPUCORE499 Building function' in archive.read(name)
        index = next(n for n in archive.namelist() if n.endswith('/Frameworks/neo_texture_catalog.framework/manifest.json.gz'))
        expected = (ROOT / 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
        assert archive.read(index) == expected
    sealed = json.loads((ROOT / 'build/delivery/signed-payload-identity.json').read_text())
    assert sealed['ipaSha256'] == hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert sealed['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True
    assert sealed['abiMetadataUnchangedBySigning'] is True
    identity = json.loads((ROOT / 'build/fast-native/rpcs3-core-identity.json').read_text())
    validate_rpc_core_identity(identity)
    result.update(source=command(['git', 'rev-parse', 'HEAD']), coreRun=int(CORE_RUN), coreSource=CORE_SOURCE,
        coreSHA256BeforeSigning=identity['sha256'], coreABI=30, neoSwapPreserved=True,
        compiledSPU499Marker=True, exact498Catalogue=True, rebuiltCores=['RPCS3'], physicalDeviceValidated=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--skin-session-evidence', action='store_true')
    parser.add_argument('--libretro-evidence', action='store_true')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('--ipa', type=Path)
    parser.add_argument('--build-number', type=int, default=499)
    parser.add_argument('--output', type=Path, default=Path('build/delivery/rpcs3-audit-validation.json'))
    parser.add_argument('core_paths', nargs='*')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    if args.ipa:
        record = final_ipa(args.ipa, args.build_number)
    else:
        record = {'result': 'passed', 'sourceClosure': source_closure()}
        if not args.source_only:
            record['reused498'] = successful(DELIVERED_RUN, DELIVERED, [
                'Private HD native IPA delivery / Closed candidate, catalogue and reusable CI provenance',
                'Private HD native IPA delivery / Exact native reuse and Foundation with the final catalogue',
                'Private HD native IPA delivery / Release device build • cold • HD native'])
            record['newCore'] = core_evidence()
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS: closed Build 499 source, reused unchanged Build 498 evidence and exact new RPCS3 Core' if not args.ipa else 'PASS: final signed Build 499 IPA with the rebuilt RPCS3 Core')


if __name__ == '__main__':
    main()
