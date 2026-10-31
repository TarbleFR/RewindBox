"""Build605: delivered604 plus reviewed achievement presentation changes.

Historical engine receipts retain their own source/build attribution. This
recipe compiles the entire application and installs a newly compiled Dolphin;
it never edits a historical validator's build number or reports old tests as new.
"""
import argparse
import hashlib
import json
import os
import plistlib
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for folder in ('build-utils', 'packages/dolphin_internal_bridge/ci', 'test'):
    sys.path.insert(0, str(ROOT / folder))
BUILD = 605
BASE = '60add3d79b3e4d9d76b68ef154cb5d3f8772c323'
BASE_RUN = 41122746325
BASE_JOB = 124293077616
DOLPHIN_SOURCE = '7cac54161659421ed95c2cd1c0b0746539a4cd38'
SCOPE = 'docs/evidence/achievement-translation-scope.json'
OUT = ROOT / 'build/delivery'
IDENTITY = 'Achievement-translation-build-identity.json'
PRODUCTS = ('lib', 'packages', 'native', 'assets', 'pubspec.yaml', 'pubspec.lock')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/TarbleFR/RewindBox/' + path], cwd=ROOT))


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')
    return value


def source_contract():
    scope = json.loads((ROOT / SCOPE).read_bytes())
    assert scope['baseline'] == BASE and scope['build'] == BUILD
    assert os.environ.get('BUILD_NUMBER', str(BUILD)) == str(BUILD)
    assert os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude'
    assert not git('diff', '--name-only'), 'Tracked files changed after checkout'
    assert git('write-tree') == git('rev-parse', 'HEAD^{tree}'), 'Staged files changed'
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    changed = git('diff', '--name-only', BASE, 'HEAD', '--', *PRODUCTS).splitlines()
    assert set(changed) == set(scope['productDelta']), 'Unexpected product delta from delivered604'
    for path, digest in scope['productDelta'].items():
        assert sha((ROOT / path).read_bytes()) == digest, 'Unreviewed product bytes: ' + path
    for path in ('native', 'assets', 'pubspec.lock'):
        assert git('rev-parse', BASE + ':' + path) == git('rev-parse', 'HEAD:' + path), path
    receipt_path = ROOT / 'docs/evidence/rewind604-delivery.json'
    assert sha(receipt_path.read_bytes()) == scope['baselineReceiptSHA256']
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt['result'] == 'passed' and receipt['source'] == BASE and receipt['run'] == BASE_RUN
    assert receipt['ipaSHA256'] == '50a248491142fdee7148f0d695d6716a385e780a621506367b78b4308326c095'
    return dict(build=BUILD, source=git('rev-parse', 'HEAD'), tree=git('rev-parse', 'HEAD^{tree}'),
                baseline=dict(build=604, source=BASE, run=BASE_RUN, ipaSHA256=receipt['ipaSHA256']),
                productDelta=scope['productDelta'], sourceScopeSHA256=sha((ROOT / SCOPE).read_bytes()),
                rebuiltEngines=['Dolphin'], retainedEngines=['RPCS3', 'MeloNX', 'ARMSX2', 'libretro'],
                physicalDeviceTested=False)


def contract():
    from delivery_contract_memo import reuse
    return save('achievement-host-contract.json', reuse('605-achievement-host', source_contract))


def baseline():
    result = contract()
    run, job = api(f'actions/runs/{BASE_RUN}'), api(f'actions/jobs/{BASE_JOB}')
    assert run['head_sha'] == job['head_sha'] == BASE
    assert run['conclusion'] == job['conclusion'] == 'success'
    assert run['run_attempt'] == job['run_attempt'] == 1 and job['run_id'] == BASE_RUN
    return save('achievement-baseline.json', dict(result='authenticated', contract=result,
                historicalRun=BASE_RUN, historicalJob=BASE_JOB, historicalChecksReexecuted=False))


def retained(operation):
    import rpcs3runtime604_core as rpc
    import rewind604_engine as engine
    from rewind604_baseline_delivery import download_engine
    if operation == 'download-core':
        value = rpc.download_core()
    elif operation == 'component-runs':
        value = dict(rpcs3=rpc.core_run(), melonx=engine.engine_run())
    elif operation == 'download-components':
        value = download_engine()
    elif operation == 'engine-evidence':
        value = engine.engine_evidence()
    else:
        raise ValueError(operation)
    return save('achievement-retained-' + operation + '.json',
                dict(build=BUILD, kind='retained component evidence', historicalResult=value,
                     enginesRecompiledHere=False, historicalTestsReexecuted=False))


def tests():
    # A later recipe-only commit may reuse a successful run only when every
    # transitive input of this scoped suite is identical to its actual source.
    paths = ['packages', 'lib', 'assets', 'pubspec.yaml', 'pubspec.lock',
             'pubspec_overrides.yaml', 'analysis_options.yaml', 'test/achievement_translation_test.dart',
             'test/achievement_translation_contract_test.py', 'test/retro_achievements_service_test.dart',
             'test/retro_achievements_credentials_test.dart', 'test/retro_achievements_repository_test.dart',
             'test/retro_achievements_resolver_test.dart', 'test/secondary_achievement_item_test.dart',
             'test/retro_achievements_layout_test.dart', 'test/database_test_helper.dart',
             '.github/workflows/achievement-translation.yml']
    started = time.monotonic()
    deadline = started + 1800
    discovery_deadline = started + 120
    while True:
        runs = api('actions/workflows/achievement-translation.yml/runs?branch=Claude&per_page=30')['workflow_runs']
        matching = [run for run in runs if not git('diff', '--name-only', run['head_sha'], 'HEAD', '--', *paths)]
        success = next((run for run in matching if run['status'] == 'completed' and run['conclusion'] == 'success'), None)
        if success:
            jobs = api(f"actions/runs/{success['id']}/jobs?per_page=100")['jobs']
            assert {job['name'] for job in jobs if job['conclusion'] == 'success'} >= {'swift', 'flutter'}
            return save('achievement-tests.json', dict(result='passed', source=success['head_sha'],
                        run=success['id'], attempt=success['run_attempt'], jobs=[job['id'] for job in jobs],
                        inputPaths=paths, inputsIdenticalToApplication=True, physicalDeviceTested=False))
        pending = any(run['status'] != 'completed' for run in matching)
        # A prerequisite can start before the Actions API lists the sibling
        # workflow from this push. Allow only a bounded empty-list discovery
        # window; known terminal failures still fail closed.
        discovering = not matching and time.monotonic() < discovery_deadline
        if (not pending and not discovering) or time.monotonic() >= deadline:
            raise RuntimeError('No successful Swift6/XCTest + Flutter run for these exact inputs: ' +
                               repr([(r['id'], r['status'], r['conclusion']) for r in matching]))
        print('Waiting for the matching Swift/Flutter validation run', flush=True)
        time.sleep(30)


def dolphin_run():
    """Wait without reserving an Apple build machine for a producer still running."""
    run_id = int(os.environ['DOLPHIN_CORE_RUN_ID'])
    producer = os.environ['DOLPHIN_CORE_HOST_SHA']
    deadline = time.monotonic() + 3600
    while True:
        run = api(f'actions/runs/{run_id}')
        assert run['head_sha'] == producer and run['head_branch'] == 'Claude'
        assert run['path'] == '.github/workflows/achievement-translation-dolphin.yml'
        if run['status'] == 'completed':
            assert run['conclusion'] == 'success', 'Dolphin compilation did not succeed'
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Dolphin compilation is still pending; no older core may substitute')
        print('Waiting for the newly compiled Dolphin presentation hook', flush=True)
        time.sleep(30)
    return run


def dolphin_ready():
    run = dolphin_run()
    return save('achievement-dolphin-producer-ready.json',
                dict(result='passed', source=run['head_sha'], run=run['id'], attempt=run['run_attempt']))


def dolphin():
    from verify_ipa import macho
    from delivery_benchmark import payload_fingerprint
    run = dolphin_run()
    run_id = int(os.environ['DOLPHIN_CORE_RUN_ID'])
    producer = os.environ['DOLPHIN_CORE_HOST_SHA']
    artifacts = api(f'actions/runs/{run_id}/artifacts?per_page=100')['artifacts']
    found = [a for a in artifacts if a['name'] == 'DolphinCore-AchievementTranslation-' + producer]
    assert len(found) == 1 and not found[0]['expired']
    artifact = found[0]
    assert artifact['workflow_run']['head_sha'] == producer and artifact['workflow_run']['id'] == run_id
    archive = ROOT / 'build/delivery/dolphin-compiled.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open('wb') as handle:
        subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{artifact['id']}/zip"],
                       stdout=handle, cwd=ROOT, check=True, timeout=600)
    assert archive.stat().st_size == artifact['size_in_bytes']
    assert 'sha256:' + sha(archive.read_bytes()) == artifact['digest']
    destination = ROOT / 'dist/dolphin-achievement'
    if destination.exists():
        shutil.rmtree(destination)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist()))
        for name in z.namelist():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts and '\\' not in name
        z.extractall(destination)
    identity = json.loads((destination / 'identity.json').read_bytes())
    assert identity['host_commit'] == producer and identity['source_revision'] == DOLPHIN_SOURCE
    assert identity['architectures'] == ['arm64'] and identity['achievement_presenter'] == 1
    assert identity['use_retro_achievements'] is True and identity['device_runtime_tested'] is False
    inputs = [ROOT / 'build-utils/patch_dolphin_internal_core_v2.py',
              *sorted((ROOT / 'packages/dolphin_internal_bridge/core').glob('*.inc'))]
    assert identity['source_inputs'] == {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in inputs}
    core = destination / 'DolphinCore.framework/DolphinCore'
    raw = core.read_bytes()
    assert sha(raw) == identity['sha256']
    image = macho(raw)
    assert image['platform'] == 2 and image['fileType'] == 6
    assert '_neostation_dolphin_set_achievement_presenter' in image['definedSymbols']
    core.chmod(0o755)
    for source, target in ((destination / 'DolphinCore.framework', ROOT / 'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework'),
                           (destination / 'Sys', ROOT / 'ios/Runner/Sys')):
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    shutil.copy2(destination / 'cacert.pem', ROOT / 'ios/Runner/cacert.pem')
    fast_path = ROOT / 'build/fast-native/identity.json'
    fast = json.loads(fast_path.read_bytes())
    fast.update(dolphinCoreSha256=identity['sha256'], dolphinCoreHostCommit=producer,
                dolphinSourceRevision=DOLPHIN_SOURCE, dolphinCoreRunId=run_id,
                dolphinAchievementPresentationVersion=1)
    fast_path.write_text(json.dumps(fast, indent=2) + '\n')
    return save('achievement-dolphin.json', dict(result='authenticated', producer=producer, run=run_id,
                attempt=run['run_attempt'], artifact=artifact['id'], archiveSHA256=artifact['digest'],
                identity=identity, payloadFingerprint=payload_fingerprint(raw), physicalDeviceTested=False))


def expected():
    host = json.loads((OUT / 'achievement-host-contract.json').read_bytes())
    assert host['source'] == git('rev-parse', 'HEAD') and host['build'] == BUILD
    import rpcs3runtime604_core as rpc
    import rewind604_engine as engine
    from validate_hogwarts604_ipa import PATHS
    for path in PATHS:
        assert (ROOT / path).read_bytes() == subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
    return dict(schema=1, build=BUILD, application=host,
                translationTests=json.loads((OUT / 'achievement-tests.json').read_bytes()),
                dolphin=json.loads((OUT / 'achievement-dolphin.json').read_bytes()),
                retainedRPCS3=rpc.core_receipt(), retainedMeloNX=engine.engine_evidence(),
                unchangedHogwartsHost={p: sha((ROOT / p).read_bytes()) for p in PATHS},
                unchangedHogwartsEvidenceSource=BASE, priorTestsReexecuted=False,
                translationModelsTestedOnDevice=False, physicalDeviceTested=False)


def embed(app):
    app = Path(app)
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    assert str(info['CFBundleVersion']) == str(BUILD)
    value = expected()
    (app / IDENTITY).write_text(json.dumps(value, indent=2) + '\n')
    target = app / 'Legal/Dolphin-achievement-presentation'
    shutil.copytree(ROOT / 'dist/dolphin-achievement/patched-source', target, dirs_exist_ok=True)
    shutil.copy2(ROOT / 'dist/dolphin-achievement/identity.json', target / 'identity.json')
    return save('achievement-embedded.json', dict(result='embedded', identity=value))


def structure(ipa):
    import rpcs3runtime604_core as rpc
    import validate_rpcs3_ipa as structural
    # Same explicit identity adaptation as604. Every structural/ABI guard runs;
    # no historical build number or test result is modified.
    previous = structural.validate_core_identity
    structural.validate_core_identity = rpc.validate_core_identity
    try:
        value = structural.validate_ipa(Path(ipa), str(BUILD), git('rev-parse', 'HEAD'),
                    ROOT / 'dist/rpcs3-native/identity.json', rpc.CORE_SOURCE, str(rpc.CORE_RUN))
    finally:
        structural.validate_core_identity = previous
    return save('achievement-rpcs3-structure.json', value)


def validate(ipa):
    import io
    import plistlib
    import rpcs3runtime604_core as rpc
    from validate_rpcs3_core604_ipa import compare_core
    from validate_melonx_engine604_ipa import engine_ipa
    from delivery_benchmark import payload_fingerprint
    from validate_neoplay_ipa import validate as neoplay
    from validate_shader_compiler_ipa import validate as shaders
    from verify_ipa import macho
    receipt = expected()
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        assert len(names) == len(set(names)) and z.testzip() is None
        root = 'Payload/NeoStation.app/'
        assert json.loads(z.read(root + IDENTITY)) == receipt
        info = plistlib.loads(z.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(BUILD) and info['MinimumOSVersion'] == '18.0'
        core_result = compare_core(z.read(root + 'Frameworks/libRPCS3Core.dylib'), rpc.raw_core(), signed=True)
        source_record = json.loads(z.read(root + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        source_zip = z.read(root + 'Legal/RPCS3-current-core/compiled-host-inputs.zip')
        assert source_record['compiledInputsZipSHA256'] == sha(source_zip)
        assert source_record['coreSHA256'] == rpc.CORE_SHA256 and source_record['coreSource'] == rpc.CORE_SOURCE
        with zipfile.ZipFile(io.BytesIO(source_zip)) as sources:
            assert {n: sha(sources.read(n)) for n in sources.namelist()} == source_record['inputs'] == rpc._core_contract()[1]
        melonx_result = engine_ipa(z, root)
        dolphin_raw = z.read(root + 'Frameworks/DolphinCore.framework/DolphinCore')
        assert payload_fingerprint(dolphin_raw) == receipt['dolphin']['payloadFingerprint']
        assert '_neostation_dolphin_set_achievement_presenter' in macho(dolphin_raw)['definedSymbols']
        assert macho(dolphin_raw)['codeSignature'] is True
        plugin = z.read(root + 'Frameworks/achievement_translation.framework/achievement_translation')
        image = macho(plugin)
        assert image['platform'] == 2 and image['fileType'] == 6 and image['minimumOS'].startswith('18.')
        for marker in (b'AchievementTranslationPlugin', b'RBAchievementText', b'RBAchievementToast',
                       b'rewindbox/achievement_translation', b'RBAchievementPresent'):
            assert marker in plugin, 'Missing compiled translation implementation: ' + repr(marker)
        assert any('Translation.framework' in d['path'] for d in image['dependencies'])
        helper_path = 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js'
        assert z.read(root + helper_path) == (ROOT / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes()
        host = z.read(root + 'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for marker in (b'Hogwarts GPU policy:', b'occlusionQuerySync', b'relaxQueryFlushing',
                       b'original core SHA256 prefix', b'inspectUnreal'):
            assert marker in host, 'Retained Hogwarts host marker missing: ' + repr(marker)
    neoplay_result = neoplay(Path(ipa), str(BUILD), git('rev-parse', 'HEAD'))
    shader_result = shaders(Path(ipa), str(BUILD))
    return save('achievement-ipa-validation.json', dict(result='passed', build=BUILD,
                ipaSHA256=sha(Path(ipa).read_bytes()), ipaBytes=Path(ipa).stat().st_size,
                identity=receipt, retainedRPCS3Payload=core_result, retainedMeloNXPayload=melonx_result,
                newDolphinPayloadPreserved=True, actualTranslationPluginPresent=True,
                retainedNeoPlay=neoplay_result, shaderCompilerIsolation=shader_result,
                physicalDeviceTested=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['contract', 'baseline', 'tests', 'dolphin', 'dolphin-ready', 'download-core',
                        'component-runs', 'download-components', 'engine-evidence', 'embed', 'structure', 'validate'])
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args()
    if args.operation in ('embed', 'structure', 'validate'):
        assert args.path is not None
        result = globals()[args.operation](args.path)
    elif args.operation in ('download-core', 'component-runs', 'download-components', 'engine-evidence'):
        result = retained(args.operation)
    elif args.operation == 'dolphin-ready':
        result = dolphin_ready()
    else:
        result = globals()[args.operation]()
    print(json.dumps(result, indent=2))
