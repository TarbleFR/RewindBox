"""Private IPA610: delivered609 with the RA credentials fix and the RPCS3 Core 610 lot.

Fresh for this build: the Flutter application and the RPCS3 Core 610
(authenticated from its own Core route; never recompiled here). The
Flutter/source and Xcode16.4 native test groups ran fresh on these exact
product sources in the first 610 delivery run (41341797604, whose application
job failed in a MeloNX packaging check outside the tested sources); this
recipe-only retry authenticates those jobs and re-runs the delivery contract,
which reads the recipe, fresh. Retained with their original provenance: the
liveness MeloNX Core of IPA609, the Dolphin session and ARMSX2 ABI9 Cores of
IPA608, the libretro cores and the MeloNX native dependencies.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile

import rewind610_baseline as tree
import rewind610_checks as checks
import rewind609_engine as engine
import rewind609_delivery as delivered609
import rewind608_producers as producers608
import rpcs3core610_delivery as rpc
# Stateless Mach-O/container parsers already used for delivered607 to 609.
from rewind607_delivery import app_payloads, zip_payloads

ROOT, BUILD = tree.ROOT, 610
OUT = ROOT / 'build/delivery'
CACHE = ROOT / 'build/components610'
IDENTITY = 'RewindBox610-build-identity.json'
WORKFLOW = '.github/workflows/rewind610-delivery.yml'
WORKFLOW609 = '.github/workflows/rewind609-hogwarts-liveness-delivery.yml'
WORKFLOW608 = '.github/workflows/rewind608-retro-achievements-delivery.yml'
EVIDENCE609 = 'docs/evidence/rewind609'
JOBS = {'flutter': 'Build610 source and Flutter tests', 'native': 'Build610 Xcode16.4 native tests'}
REQUIRED_STEPS = {'flutter': {'Run source contracts and Flutter behavior'},
                  'native': {'Run actual Xcode16.4 tests and host compilation'}}
# Fresh610 test evidence of the first 610 delivery run on the same product sources.
# Its Flutter and Xcode16.4 jobs succeeded; only the application job failed, in the
# retained MeloNX packaging check (concurrent source-only MeloNX inputs). A retry that
# changes nothing but the delivery recipe authenticates these jobs instead of
# re-running about 18 minutes of tests.
REUSED_TESTS = dict(source='6d17e6d601171ed50263d5c11c02188994e34b8c', run=41341797604, attempt=1,
    jobs={'flutter': 124953301162, 'native': 124953301200},
    artifacts={'flutter': (13097786571, 'a14e2509375dbf9764e1c3a14d8cfb503241b275a3d6b9244edd66d7d2e3119d'),
               'native': (13097848476, '07d9f8fa0b00309a6209484abb65443ad95e6a0d11e97c4a5485ab3bd60e9221')})
# The only paths a recipe-only retry may change after the tested source. The delivery
# contract reads all of them, so it is re-run fresh by this run (preflight and tests).
RECIPE_PATHS = ('.github/diagnostics/rewind610_delivery.py', '.github/workflows/rewind610-delivery.yml',
                'build-utils/rewind610-source-scope.json', 'test/rewind610_delivery_contract_test.py')
CONTRACT_TEST = ('python3', '-B', 'test/rewind610_delivery_contract_test.py')
RETAINED_CORES = delivered609.RETAINED_CORES
sha, git, require = tree.sha, tree.git, tree.require
_retained_melonx_divergence = {}


def _inputs_match_retained(inputs, source):
    """rewind609_engine.inputs_match for the retained609 MeloNX Core.

    Every producer input must still equal its bytes at the producer source
    commit. The current checkout may differ only for the reviewed concurrent
    MeloNX diagnostics inputs (exact bytes of their commit); those changes are
    present in the source but not compiled into this IPA's retained MeloNX Core.
    """
    require(bool(inputs), 'Empty producer input inventory')
    concurrent = tree.concurrent_uncompiled()
    for path, expected in inputs.items():
        require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe input path')
        require(sha(engine.original_bytes(source, path)) == expected, 'Producer input changed: ' + path)
        current = sha((ROOT / path).read_bytes())
        if current != expected:
            require(path in concurrent and current == concurrent[path], 'Producer input changed: ' + path)
            _retained_melonx_divergence[path] = dict(producerSHA256=expected, headSHA256=current,
                commit=tree.CONCURRENT_UNCOMPILED[path], compiledIntoIPA610=False)


engine.inputs_match = _inputs_match_retained


def reviewed_adaptation(name, digest, expected, concurrent):
    """The digest package_runtime may accept for one retained609 adaptation input.

    Equal bytes pass unchanged. A divergent input passes only when it is a reviewed
    concurrent MeloNX input carrying exactly its commit's bytes; the retained Core
    was compiled from the producer bytes, which the caller verifies separately.
    """
    if digest == expected:
        return False
    require(name in concurrent and digest == concurrent[name], 'Engine adaptation mismatch: ' + name)
    return True


def melonx_materialize():
    """package_runtime.materialize for the retained609 liveness MeloNX Core.

    The packaging check requires every engine adaptation input of the checkout to
    equal the bytes the retained Core was compiled from. The reviewed concurrent
    MeloNX inputs (source-only in 610) differ; for those, the bytes at the
    producer commit must equal the recorded digest, and the divergence is
    recorded. Every other path and every other check of materialize is unchanged.
    """
    sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
    import package_runtime as runtime
    identity = json.loads((runtime.CORE / 'ios-arm64/identity.json').read_bytes())
    require(identity['host'] == engine.pin()['source'], 'Retained609 Core identity of another producer')
    adaptations = identity['adaptations']
    concurrent = tree.concurrent_uncompiled()
    accepted = {}
    actual_sha = runtime.sha

    def checked_sha(path):
        digest = actual_sha(path)
        try:
            name = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            return digest
        if name not in adaptations or not reviewed_adaptation(name, digest, adaptations[name], concurrent):
            return digest
        require(sha(engine.original_bytes(identity['host'], name)) == adaptations[name],
                'Retained609 producer bytes differ: ' + name)
        accepted[name] = dict(producerSHA256=adaptations[name], headSHA256=digest,
                              commit=tree.CONCURRENT_UNCOMPILED[name], compiledIntoIPA610=False)
        return adaptations[name]

    runtime.sha = checked_sha
    try:
        runtime.materialize()
    finally:
        runtime.sha = actual_sha
    return save('rewind610-melonx-materialize.json', dict(result='materialized', retainedFrom=609,
        producerSource=identity['host'], sourceInputsChangedAfterProducerNotCompiled=accepted))


def check_recipe_only(changed):
    extra = sorted(set(changed) - set(RECIPE_PATHS))
    require(not extra, 'A tested input changed after the reused610 test run: ' + repr(extra))
    return sorted(set(changed))


@lru_cache(maxsize=None)
def reuse_equivalence():
    """The tested source and this checkout differ only in the delivery recipe."""
    source = REUSED_TESTS['source']
    subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'HEAD'], cwd=ROOT, check=True, timeout=60)
    # Working tree against the tested commit: committed and uncommitted tracked changes.
    changed = check_recipe_only(git('diff', '--name-only', '--no-renames', source).splitlines())
    tested_raw = subprocess.check_output(['git', 'show', source + ':' + tree.CONFIG], cwd=ROOT, timeout=60)
    tested, current = json.loads(tested_raw), json.loads((ROOT / tree.CONFIG).read_bytes())
    require(tested['productDelta'] == current['productDelta'] and tested['productReview'] == current['productReview'],
            'The reviewed product delta differs from the tested one')
    return dict(source=source, changedRecipePaths=changed, testedScopeSHA256=sha(tested_raw),
                productDeltaIdentical=True)


def contract_rerun():
    """The delivery contract reads the recipe: run it fresh on this exact checkout."""
    process = subprocess.run(CONTRACT_TEST, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    require(process.returncode == 0, 'The delivery contract failed on this recipe:\n' + process.stdout.decode(errors='replace')[-4000:])
    return dict(command=' '.join(CONTRACT_TEST), exitCode=0, logSHA256=sha(process.stdout),
                execution=checks.execution() if os.environ.get('GITHUB_SHA') else None)


def reuse_check():
    """Preflight: fail within a minute when the reused test evidence does not apply."""
    return save('rewind610-reuse-check.json', dict(result='authenticated',
        reused={kind: origin(kind) for kind in JOBS}, contract=contract_rerun()))


def save(name, value):
    return producers608.save(OUT / name, value)


def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint], cwd=ROOT, timeout=120))


def evidence609(name):
    """A committed delivered609 receipt, bound by the pinned609 delivery receipt."""
    raw = (ROOT / EVIDENCE609 / name).read_bytes()
    return raw, json.loads(raw)


def inventory():
    value = json.loads((ROOT / tree.INVENTORY).read_bytes())
    raw, reference = evidence609('signed-payload-identity.json')
    require(sha(raw) == value['inventoryReferenceSHA256'], 'Delivered609 image inventory reference changed')
    original = set(reference['images'])
    require(value['schema'] == 1 and value['build'] == BUILD and value['baselineBuild'] == 609 and
            len(original) == 90 and set(value['baselineImages']) == original and len(value['baselineImages']) == 90 and
            value['addedImages'] == [] and value['removedImages'] == [] and value['expectedImageCount'] == 90 and
            reference['ipaSha256'] == tree.BASELINE['ipaSHA256'], '610 keeps exactly the delivered609 native images')
    return original


def validate_inventory(names):
    expected_names = inventory()
    actual = set(names)
    require(actual == expected_names and len(names) == len(expected_names),
            'Native image inventory differs: missing=' + repr(sorted(expected_names - actual)) +
            ' extra=' + repr(sorted(actual - expected_names)))
    return len(actual)


def seal():
    import delivery_benchmark as benchmark
    app = ROOT / 'build/ios/dolphin-unsigned/Payload/NeoStation.app'
    before = app_payloads(app)
    validate_inventory(before)
    benchmark.seal()
    after = app_payloads(app)
    ipa = ROOT / 'dist/NeoStation.ipa'
    packaged = zip_payloads(ipa)
    require(before == after == packaged, 'Signing/export changed compiled code, data, ABI or an architecture container')
    receipt = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    complete = {name: record['fingerprint'] for name, record in before.items()}
    require(set(receipt['images']) <= set(complete) and
            all(complete[name] == digest for name, digest in receipt['images'].items()),
            'Signer receipt disagrees with the full native inventory')
    require(receipt['ipaSha256'] == sha(ipa.read_bytes()) and receipt['ipaBytes'] == ipa.stat().st_size and
            receipt['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
            receipt['abiMetadataUnchangedBySigning'] is True, 'Wrong signed610 export identity')
    signature = json.loads((OUT / 'signature.json').read_bytes())
    signed_targets = {'.' if name == 'Runner' else name if name.endswith('.dylib') else Path(name).parent.as_posix()
                      for name in before}
    require(len(signed_targets) == 90 and len(signature['signatures']) == 90 and
            all(item['signatureVerified'] is True for item in signature['signatures']) and
            {item['bundle'] for item in signature['signatures']} == signed_targets,
            'Missing, duplicated or failed actual macOS signature verification')
    receipt.update(build=BUILD, images=complete, imageCount=90, retainedImageNames=90, addedImageNames=0,
        architectureContainers={name: record['container'] for name, record in before.items()},
        singleArm64FatImages=sum(record['container'].startswith('single-arm64-fat') for record in before.values()),
        completeNativeInventoryCheckedBeforeAndAfterSigning=True, completeNativeInventoryCheckedInFinalZIP=True)
    return save('signed-payload-identity.json', receipt)


def contract():
    return save('rewind610-host-contract.json', tree.verify())


def baseline():
    result = contract()
    base = tree.BASELINE
    run = api(f"actions/runs/{base['run']}/attempts/{base['attempt']}")
    job = api('actions/jobs/' + str(base['job']))
    require(run['head_sha'] == job['head_sha'] == tree.BASE and
            run['conclusion'] == job['conclusion'] == 'success' and
            run['run_attempt'] == job['run_attempt'] == base['attempt'] and
            job['run_id'] == run['id'] == base['run'] and run['head_branch'] == 'Claude' and
            run['path'] == WORKFLOW609, 'Wrong actual delivered609 run/job')
    return save('rewind610-baseline.json', dict(result='authenticated-run-and-reviewed-source',
        application=result, delivered609=base, previousPrivateIPADownloadedByThisRun=False,
        previousIPAMetadataOrigin='Verified delivery609 receipt committed by the integrator; the private IPA is not a runtime donor.',
        historicalTestsReexecuted=False))


@lru_cache(maxsize=None)
def origin(kind):
    """The fresh610 test job of the first 610 delivery run, on these product sources."""
    require(kind in JOBS, 'Unknown610 test producer')
    reused = REUSED_TESTS
    equivalence = reuse_equivalence()
    run = api(f"actions/runs/{reused['run']}/attempts/{reused['attempt']}")
    require(run['id'] == reused['run'] and run['head_sha'] == reused['source'] and run['head_branch'] == 'Claude' and
            run['path'] == WORKFLOW and run['run_attempt'] == reused['attempt'] and
            run['event'] in ('push', 'workflow_dispatch'), 'Wrong reused610 test run')
    job = api('actions/jobs/' + str(reused['jobs'][kind]))
    require(job['name'] == JOBS[kind] and job['head_sha'] == reused['source'] and job['run_id'] == reused['run'] and
            job['run_attempt'] == reused['attempt'] and job['status'] == 'completed' and
            job['conclusion'] == 'success', 'The reused610 test job did not succeed: ' + kind)
    require(REQUIRED_STEPS[kind] <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'The reused610 test job omitted a required step: ' + kind)
    artifact_id, digest = reused['artifacts'][kind]
    artifact = api('actions/artifacts/' + str(artifact_id))
    expected_name = f"RewindBox610-{kind}-{reused['source']}-attempt{reused['attempt']}"
    require(artifact['name'] == expected_name and artifact['digest'] == 'sha256:' + digest and
            not artifact['expired'] and artifact['workflow_run']['id'] == reused['run'] and
            artifact['workflow_run']['head_sha'] == reused['source'], 'Wrong reused610 artifact binding: ' + kind)
    execution = dict(source=reused['source'], tree=git('rev-parse', reused['source'] + '^{tree}'),
                     run=reused['run'], attempt=reused['attempt'])
    return dict(result='authenticated', evidenceMode='reused-identical-product-sources', kind=kind,
                execution=execution, job=job['id'], artifact=artifact_id, artifactName=expected_name,
                archiveSHA256=digest, archiveBytes=artifact['size_in_bytes'], sourceEquivalence=equivalence)


def fetch(kind):
    value = origin(kind)
    path = CACHE / f'{kind}.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size != value['archiveBytes'] or sha(path.read_bytes()) != value['archiveSHA256']:
        temporary = path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"],
                           stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == value['archiveBytes'] and sha(temporary.read_bytes()) == value['archiveSHA256'],
                'Fresh610 test archive digest/size mismatch: ' + kind)
        temporary.replace(path)
    target = CACHE / kind
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(path) as archive:
        engine.safe_members(archive)
        archive.extractall(target)
    return value, target


def tests():
    checked = {}
    for kind in ('flutter', 'native'):
        value, directory = fetch(kind)
        receipt = json.loads((directory / 'validation.json').read_bytes())
        require(receipt['result'] == 'passed' and receipt['group'] == kind and receipt['execution'] == value['execution'],
                'Wrong610 test execution receipt')
        require(receipt['sourceScopeSHA256'] == value['sourceEquivalence']['testedScopeSHA256'],
                'Tests were run on another reviewed source scope')
        require(receipt['commands'] and all(c['exitCode'] == 0 for c in receipt['commands']),
                'A required610 test command did not succeed')
        require([c['name'] for c in receipt['commands']] == checks.command_names(kind),
                'A required610 command was omitted or replaced')
        for command in receipt['commands']:
            require(sha((directory / command['log']).read_bytes()) == command['logSHA256'], '610 command log changed')
        if kind == 'native':
            require(receipt['xcodeVersion'].startswith('Xcode 16.4\n'), 'Wrong targeted native compiler')
            require('Apple Swift version 6.' in receipt['swiftVersion'], 'Translation was not compiled with Swift6')
            checks.checks608.validate_central_receipt(receipt['centralSessionXCTest'])
        checked[kind] = dict(value, receipt=receipt, testsReexecutedInThisRun=False)
    checked['deliveryContract'] = contract_rerun()
    return save('rewind610-tests.json', checked)


def native(kind):
    """Install a retained608 Dolphin/ARMSX2 Core exactly as IPA609 did (same producer, same checks)."""
    value, directory = delivered609.fetch_reused(kind)
    import rewind608_reuse as reuse608
    record = json.loads((directory / 'producer608.json').read_bytes())
    original_inputs = reuse608.original_input_hashes(kind)
    require(record['schema'] == 1 and record['build'] == 608 and record['kind'] == kind and
            record['execution'] == value['execution'] and record['inputs'] == original_inputs,
            'Retained608 native compiled inputs differ')
    current = producers608.input_hashes(kind)
    recipes = {producers608.WORKFLOW, '.github/diagnostics/rewind608_producers.py'}
    require(set(current) == set(original_inputs) and
            all(current[path] == digest for path, digest in original_inputs.items() if path not in recipes),
            'A native ' + kind + ' source input changed since the retained608 Core was compiled')
    require(record['files'] == producers608.member_hashes(directory, ('producer608.json',)),
            'Retained608 native artifact member changed, missing or added')
    require(record['compiledSourcePostimages'] == producers608.member_hashes(directory / 'patched-source608'),
            'Actual patched upstream source snapshot differs')
    identity = json.loads((directory / 'identity.json').read_bytes())
    require(identity['host_commit'] == value['execution']['source'] and identity['architectures'] == ['arm64'],
            'Wrong retained608 native host/architecture')
    sys.path[:0] = [str(ROOT / 'packages/dolphin_internal_bridge/ci'), str(ROOT / 'build-utils')]
    from verify_ipa import macho
    from delivery_benchmark import payload_fingerprint
    core_name = 'DolphinCore' if kind == 'dolphin' else 'ARMSX2Core'
    raw = (directory / f'{core_name}.framework/{core_name}').read_bytes()
    require(sha(raw) == identity['sha256'], 'Native binary differs from its compiled identity')
    image = macho(raw)
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
            image['id'] == f'@rpath/{core_name}.framework/{core_name}', 'Wrong retained608 native Mach-O')
    fingerprint = payload_fingerprint(raw)
    require(fingerprint == RETAINED_CORES[kind], 'Retained Core differs from the delivered608/609 signed payload: ' + kind)
    if kind == 'dolphin':
        require(record['upstreamRevision'] == identity['source_revision'] == producers608.DOLPHIN_SOURCE and
                identity['achievement_session_policy'] == 1 and identity['achievement_presenter'] == 1 and
                identity['use_retro_achievements'] is True and identity['source_inputs'] == original_inputs,
                'Wrong retained608 Dolphin policy provenance')
        require(producers608.DOLPHIN_EXPORTS <= set(image['definedSymbols']), 'Missing additive Dolphin RA exports')
        replacements = ((directory / 'DolphinCore.framework', ROOT / 'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework'),
                        (directory / 'Sys', ROOT / 'ios/Runner/Sys'))
        for source, destination in replacements:
            require(source.is_dir(), 'Dolphin runtime resource missing')
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        shutil.copy2(directory / 'cacert.pem', ROOT / 'ios/Runner/cacert.pem')
        (ROOT / 'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework/DolphinCore').chmod(0o755)
    else:
        source = json.loads((ROOT / 'build-utils/armsx2/source.json').read_bytes())
        require(identity['revision'] == record['upstreamRevision'] == source['revision'] and
                identity['abi_version'] == source['abi_version'] == 9 and
                identity['release'] == source['release'] == 'iOSv2.6.0' and
                identity['shader_chains'] is True and identity['performance_overlays'] is True,
                'Wrong ARMSX2 ABI9/release/shader contract')
        require(set(image['definedSymbols']) == {'_NeoARMSX2_GetAPI'}, 'ARMSX2 exported ABI changed')
        producers608.validate_armsx2_shaders(identity, record['files'],
                                             producers608.member_hashes(directory / 'ARMSX2Core.framework/shaders'))
        destination = ROOT / 'dist/armsx2'
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(directory, destination)
        (destination / 'ARMSX2Core.framework/ARMSX2Core').chmod(0o755)
    fast_path = ROOT / 'build/fast-native/identity.json'
    fast = json.loads(fast_path.read_bytes())
    prefix = 'dolphin' if kind == 'dolphin' else 'armsx2'
    fast.update({prefix + 'CoreSha256': identity['sha256'], prefix + 'CoreHostCommit': value['execution']['source'],
                 prefix + 'CoreRunId': value['execution']['run'], prefix + 'SourceRevision': record['upstreamRevision']})
    if kind == 'dolphin':
        fast.update(dolphinAchievementPresentationVersion=1, dolphinAchievementSessionPolicyVersion=1)
    producers608.save(fast_path, fast)
    return save(f'rewind610-{kind}.json', dict(value, identity=identity, payloadFingerprint=fingerprint,
        sourceInputs=record['inputs'], candidateSourceInputs=current,
        compiledSourcePostimages=record['compiledSourcePostimages'], coreRecompiled=False,
        retainedThrough=[608, 609], physicalDeviceTested=False))


def download_retained_archive(kind):
    value = delivered609.retained_archive_origin(kind)
    path = CACHE / f'retained-{kind}.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size != value['bytes'] or sha(path.read_bytes()) != value['sha256']:
        temporary = path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"],
                           stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == value['bytes'] and sha(temporary.read_bytes()) == value['sha256'],
                'Downloaded retained runtime archive differs: ' + kind)
        temporary.replace(path)
    destination = ROOT / value['destination']
    if destination.exists():
        shutil.rmtree(destination)
    with zipfile.ZipFile(path) as archive:
        engine.safe_members(archive)
        archive.extractall(destination)
    return save('rewind610-retained-' + kind + '.json', value)


def retained_ready():
    baseline()
    return save('rewind610-retained-producers.json', dict(
        rpcs3Core610=rpc.core_run(), melonx=engine.producer('core'),
        reusedPrerequisites={kind: delivered609.reused_origin(kind) for kind in ('dolphin', 'armsx2')},
        runtimeArchives={kind: delivered609.retained_archive_origin(kind) for kind in delivered609.RETAINED_ARCHIVES},
        priorNativeSuitesReexecuted=False, priorCoresRecompiled=False))


def retained(operation):
    if operation == 'download-core':
        value = rpc.download_core()
    elif operation == 'component-runs':
        value = dict(rpcs3=rpc.core_run(), melonx=engine.producer('core'))
    elif operation == 'download-components':
        value = engine.download('core')
    elif operation == 'engine-evidence':
        value = engine.engine_evidence()
    else:
        raise ValueError(operation)
    return save('rewind610-' + operation + '.json', value)


def expected():
    application = json.loads((OUT / 'rewind610-host-contract.json').read_bytes())
    require(application['source'] == git('rev-parse', 'HEAD') and application['build'] == BUILD,
            'Application checkout changed after the contract')
    tests_value = json.loads((OUT / 'rewind610-tests.json').read_bytes())
    require(set(tests_value) == {'flutter', 'native', 'deliveryContract'} and
            tests_value['deliveryContract']['exitCode'] == 0, 'Fresh610 test evidence is absent')
    for kind in JOBS:
        value, current = tests_value[kind], origin(kind)
        require(all(value.get(key) == current[key] for key in current), 'Fresh610 test evidence changed: ' + kind)
    cores = {kind: json.loads((OUT / f'rewind610-{kind}.json').read_bytes()) for kind in ('dolphin', 'armsx2')}
    for kind, value in cores.items():
        reused = delivered609.reused_origin(kind)
        require(all(value.get(key) == reused[key] for key in reused if key != 'expiresAt'),
                'Retained608 Core differs from its authenticated original producer: ' + kind)
    _, delivered = evidence609('signed-payload-identity.json')
    rpc_receipt = rpc.core_receipt()
    require(rpc_receipt['corePayloadFingerprint'] != delivered['images']['Frameworks/libRPCS3Core.dylib'],
            '610 must replace the delivered RPCS3 payload with Core 610')
    packaging = json.loads((OUT / 'rewind610-melonx-materialize.json').read_bytes())
    require(packaging['result'] == 'materialized', 'The retained MeloNX Core was not materialized by this recipe')
    return dict(schema=1, build=BUILD, application=application, testEvidence=tests_value,
        evidenceMode='reused-identical-product-sources', melonxPackaging=packaging,
        **cores, newRPCS3=rpc_receipt,
        retainedMeloNX=dict(engine.engine_evidence(), retainedFrom=609,
                            sourceInputsChangedAfterProducerNotCompiled=dict(_retained_melonx_divergence)),
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False,
        raCredentialsFixDeviceTested=False)


def embed(app):
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(str(info['CFBundleVersion']) == str(BUILD), 'Wrong610 embedding build')
    value = expected()
    (app / IDENTITY).write_text(json.dumps(value, indent=2) + '\n')
    for kind in ('dolphin', 'armsx2'):
        directory = delivered609.CACHE / kind
        destination = app / 'Legal' / ('Dolphin-session608' if kind == 'dolphin' else 'ARMSX2-session608')
        shutil.copytree(directory / 'patched-source608', destination / 'patched-source', dirs_exist_ok=True)
        for name in ('producer608.json', 'identity.json'):
            shutil.copy2(directory / name, destination / name)
    return save('rewind610-embedded.json', dict(result='embedded', identity=value))


def structure(ipa):
    import validate_rpcs3_ipa as structural
    # The Core 610 identity is authenticated by its own module; the structural
    # validator, expected610 build, 88 exports, ABI30 and exact binary guards still run.
    previous = structural.validate_core_identity
    structural.validate_core_identity = rpc.validate_core_identity
    try:
        value = structural.validate_ipa(Path(ipa), str(BUILD), git('rev-parse', 'HEAD'),
                    ROOT / 'dist/rpcs3-native/identity.json', rpc.PIN['source'], str(rpc.PIN['run']))
    finally:
        structural.validate_core_identity = previous
    return save('rewind610-rpcs3-structure.json', value)


def validate(ipa):
    from validate_rpcs3_core604_ipa import compare_core
    from delivery_benchmark import payload_fingerprint
    from validate_neoplay_ipa import validate as neoplay
    from validate_shader_compiler_ipa import validate as shaders
    from verify_ipa import macho
    receipt = expected()
    complete = zip_payloads(ipa)
    validate_inventory(complete)
    signature = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    require({name: record['fingerprint'] for name, record in complete.items()} == signature['images'] and
            signature['ipaSha256'] == sha(Path(ipa).read_bytes()), 'Final ZIP differs from sealed610 payloads')
    _, delivered = evidence609('signed-payload-identity.json')
    for name in ('Frameworks/DolphinCore.framework/DolphinCore', 'Frameworks/ARMSX2Core.framework/ARMSX2Core',
                 'Frameworks/MeloNXCore.framework/MeloNXCore'):
        require(complete[name]['fingerprint'] == delivered['images'][name], 'Retained609 engine payload changed: ' + name)
    require(complete['Frameworks/libRPCS3Core.dylib']['fingerprint'] == receipt['newRPCS3']['corePayloadFingerprint'] !=
            delivered['images']['Frameworks/libRPCS3Core.dylib'], 'The RPCS3 Core 610 payload is not the packaged one')
    with zipfile.ZipFile(ipa) as archive:
        engine.safe_members(archive)
        root = 'Payload/NeoStation.app/'
        require(json.loads(archive.read(root + IDENTITY)) == receipt, 'Packaged610 identity differs')
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        require(str(info['CFBundleVersion']) == str(BUILD) and info['MinimumOSVersion'] == '18.0',
                'Wrong application version/deployment target')
        rpc_result = compare_core(archive.read(root + 'Frameworks/libRPCS3Core.dylib'), rpc.raw_core(), signed=True)
        source_record = json.loads(archive.read(root + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        source_zip = archive.read(root + 'Legal/RPCS3-current-core/compiled-host-inputs.zip')
        require(source_record['compiledInputsZipSHA256'] == sha(source_zip) and
                source_record['coreSHA256'] == rpc.PIN['core_sha256'] and source_record['coreSource'] == rpc.PIN['source'],
                'Core 610 source notice identity differs')
        with zipfile.ZipFile(io.BytesIO(source_zip)) as sources:
            require({n: sha(sources.read(n)) for n in sources.namelist()} == source_record['inputs'] == rpc._compiled_inputs(),
                    'RPCS3 actual compiled source notice changed')
        melonx_result = engine.engine_ipa(archive, root)
        for kind, name in (('dolphin', 'DolphinCore'), ('armsx2', 'ARMSX2Core')):
            raw = archive.read(root + f'Frameworks/{name}.framework/{name}')
            image = macho(raw)
            require(payload_fingerprint(raw) == receipt[kind]['payloadFingerprint'] == RETAINED_CORES[kind] and
                    image['codeSignature'] is True, 'Signed610 native Core differs from retained608: ' + kind)
            exports = set(image['definedSymbols'])
            require(producers608.DOLPHIN_EXPORTS <= exports if kind == 'dolphin' else exports == {'_NeoARMSX2_GetAPI'},
                    'Packaged610 native exports differ: ' + kind)
            folder = 'Legal/Dolphin-session608/' if kind == 'dolphin' else 'Legal/ARMSX2-session608/'
            require(json.loads(archive.read(root + folder + 'identity.json')) == receipt[kind]['identity'],
                    'Retained608 Core source identity notice differs')
            for path, digest in receipt[kind]['compiledSourcePostimages'].items():
                require(sha(archive.read(root + folder + 'patched-source/' + path)) == digest,
                        'Retained608 patched native source notice differs: ' + path)
        plugin = archive.read(root + 'Frameworks/achievement_translation.framework/achievement_translation')
        translation = macho(plugin)
        require(translation['platform'] == 2 and translation['fileType'] == 6 and translation['minimumOS'].startswith('18.'),
                'Wrong compiled Translation plugin')
        for marker in (b'AchievementTranslationPlugin', b'RBAchievementText', b'RBAchievementToast',
                       b'rewindbox/achievement_translation', b'RBAchievementPresent'):
            require(marker in plugin, 'Missing actual Translation implementation')
        plugin = archive.read(root + 'Frameworks/retro_achievements_session.framework/retro_achievements_session')
        central = macho(plugin)
        require(central['platform'] == 2 and central['fileType'] == 6 and central['minimumOS'].startswith('18.') and
                central['codeSignature'] is True, 'Wrong actual central session framework')
        require({'_RBRATakeLaunchConfiguration', '_RBRAPublishSessionState', '_RBRAEndSession', '_RBRALocalizedText'} <=
                set(central['definedSymbols']), 'Central RA facade is not exported')
        for marker in (b'RetroAchievementsSessionPlugin', b'rewindbox/retro_achievements_session'):
            require(marker in plugin, 'Missing compiled central account implementation')
        for consumer in ('armsx2_internal_bridge', 'dolphin_internal_bridge', 'libretro_internal_bridge'):
            image = macho(archive.read(root + f'Frameworks/{consumer}.framework/{consumer}'))
            require(image['minimumOS'].startswith('18.') and any(d['path'] ==
                    '@rpath/retro_achievements_session.framework/retro_achievements_session' for d in image['dependencies']),
                    'Native consumer does not link the central session pod: ' + consumer)
        helper = 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js'
        require(archive.read(root + helper) == (ROOT / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes(),
                'Delivered609 MeloNX helper changed')
        host = archive.read(root + 'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for marker in (b'Hogwarts GPU policy:', b'occlusionQuerySync', b'relaxQueryFlushing',
                       b'original core SHA256 prefix', b'inspectUnreal'):
            require(marker in host, 'Delivered609 Hogwarts host behavior missing')
    return save('rewind610-ipa-validation.json', dict(result='passed', build=BUILD,
        ipaSHA256=sha(Path(ipa).read_bytes()), ipaBytes=Path(ipa).stat().st_size, identity=receipt,
        nativeImages=90, baselineImageNamesPreserved=90, addedImages=0,
        newRPCS3Payload=rpc_result, retainedMeloNXPayload=melonx_result,
        retainedDolphinAndARMSX2PayloadsVerified=True, actualTranslationAndSessionPluginsPresent=True,
        retainedNeoPlay=neoplay(Path(ipa), str(BUILD), git('rev-parse', 'HEAD')),
        shaderCompilerIsolation=shaders(Path(ipa), str(BUILD)),
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False))


def replace_once(text, before, after):
    require(text.count(before) == 1, 'The reviewed workflow anchor changed: ' + before[:100])
    return text.replace(before, after, 1)


def test_jobs(original608):
    """The 608 Flutter and native prerequisite jobs, retargeted to the fresh610 groups."""
    start, end = original608.index('  flutter:\n'), original608.index('  dolphin:\n')
    block = original608[start:end]
    for before, after in (
        ("    if: ${{ !(inputs.reuse_0279198 || (github.event_name == 'push' && contains(github.event.head_commit.message, '[rewind608-reuse0279198]'))) }}\n", ''),
        ('    name: Build608 source and Flutter tests', '    name: ' + JOBS['flutter']),
        ('    name: Build608 Xcode16.4 native tests', '    name: ' + JOBS['native']),
        ('run: python3 -B .github/diagnostics/rewind608_checks.py flutter', 'run: python3 -B .github/diagnostics/rewind610_checks.py flutter'),
        ('run: python3 -B .github/diagnostics/rewind608_checks.py native', 'run: python3 -B .github/diagnostics/rewind610_checks.py native'),
        ('name: RewindBox608-flutter-', 'name: RewindBox610-flutter-'),
        ('name: RewindBox608-native-', 'name: RewindBox610-native-'),
        ('name: RewindBox608-XCTest-', 'name: RewindBox610-XCTest-'),
        ('path: build/validation608/flutter/', 'path: build/validation610/flutter/'),
        ('path: build/validation608/native/', 'path: build/validation610/native/'),
    ):
        count = block.count(before)
        require(count >= 1, 'The reviewed608 test job anchor changed: ' + before[:80])
        block = block.replace(before, after)
    block = block.replace('Checkout exact608 candidate and history', 'Checkout exact610 candidate and history')
    block = block.replace('Preserve actual608 command results', 'Preserve actual610 command results')
    # The reused 608 translation helper still writes build/AchievementTranslation608.xcresult.
    require('608' not in block.replace('Xcode16.4', '').replace('AchievementTranslation608', '') and 'reuse' not in block,
            'A608 selection remains in the test jobs')
    return block


def expected_workflow(original609, original608):
    """Exact text transform of the delivered609 workflow plus the 608 test jobs."""
    value = original609
    header = value[:value.index('jobs:\n')]
    new_header = (header
        .replace('name: RewindBox private IPA609 - liveness MeloNX Core',
                 'name: RewindBox private IPA610 - RA credentials fix and RPCS3 Core 610')
        .replace('run-name: RewindBox Build609 - liveness MeloNX Core - ${{ github.sha }}',
                 'run-name: RewindBox Build610 - RA fix and RPCS3 Core 610 - ${{ github.sha }}')
        .replace('  group: rewindbox-liveness609-${{ github.ref }}', '  group: rewindbox-build610-${{ github.ref }}')
        .replace("  BUILD_NUMBER: '609'", "  BUILD_NUMBER: '610'"))
    require(new_header.count('610') == 6 and '609' not in new_header, 'The reviewed609 workflow header changed')
    value = new_header + value[len(header):]
    for before, after in (
        ('    name: Build609 authenticate delivered608 and immutable retained engines',
         '    name: Build610 authenticate delivered609, the Core 610 run and retained engines'),
        ("'[rewind609-delivery]')) }}", "'[rewind610-delivery]')) }}"),
        ('    - name: Checkout exact609 candidate and history', '    - name: Checkout exact610 candidate and history'),
        ('    - name: Require reviewed608 delta and authenticated retained producer archives\n'
         '      run: python3 -B .github/diagnostics/rewind609_delivery.py retained-ready',
         '    - name: Require reviewed609 delta and authenticated producers\n'
         '      run: python3 -B .github/diagnostics/rewind610_delivery.py retained-ready\n'
         '    - name: Authenticate the reused fresh610 test jobs and re-run the delivery contract\n'
         '      run: python3 -B .github/diagnostics/rewind610_delivery.py reuse-check'),
        ('    name: Build609 full Flutter IPA with the liveness MeloNX Core and exact608 retained engines',
         '    name: Build610 full Flutter IPA with RPCS3 Core 610 and retained engines'),
        ("      BUILD_NUMBER: '609'", "      BUILD_NUMBER: '610'"),
        ('      DELIVERY_RECIPIENT: build-utils/delivery-609-recipient.pem', '      DELIVERY_RECIPIENT: build-utils/delivery-610-recipient.pem'),
        ('      ARTIFACT_NAME: RewindBox-Build609-', '      ARTIFACT_NAME: RewindBox-Build610-'),
        ("      RPCS3_CORE_HOST_SHA: a4ae86d085c231e3c5c93f7f72d2eced0f38ec24\n      RPCS3_CORE_RUN_ID: '41243687649'\n",
         f"      RPCS3_CORE_HOST_SHA: {rpc.PIN['source']}\n      RPCS3_CORE_RUN_ID: '{rpc.PIN['run']}'\n"),
        ('    - name: Authenticate delivered608 and the exact reviewed609 source delta',
         '    - name: Authenticate delivered609 and the exact reviewed610 source delta'),
        ('Extract authenticated donor527 resources; application product baseline remains608',
         'Extract authenticated donor527 resources; application product baseline remains609'),
        ('    - name: Download original failed-run diagnostics and authenticate compiled RPCS3 bytes',
         '    - name: Download and authenticate the compiled RPCS3 Core 610 bytes'),
        ('    - name: Verify and install the authenticated RPCS3 runtime candidate with unchanged ABI checks',
         '    - name: Verify and install the authenticated RPCS3 Core 610 with unchanged ABI checks'),
        ('        from rpcs3runtime607_core import validate_rpc_core_identity as validate_core_input_identity\n'
         '        from rpcs3runtime607_core import validate_core_identity, compatibility\n',
         '        from rpcs3core610_delivery import validate_rpc_core_identity as validate_core_input_identity\n'
         '        from rpcs3core610_delivery import validate_core_identity, compatibility\n'),
        ('Download and authenticate the exact libretro runtime retained from608',
         'Download and authenticate the exact libretro runtime retained from609'),
        ('    - name: Download the reviewed liveness MeloNX Core producer',
         '    - name: Download the liveness MeloNX Core producer retained from609'),
        ('    - name: Authenticate the liveness Core inputs, fresh gates and runtime evidence',
         '    - name: Authenticate the retained609 liveness Core inputs, gates and runtime evidence'),
        ('Download and authenticate the exact native MeloNX dependencies retained from608',
         'Download and authenticate the exact native MeloNX dependencies retained from609'),
        ("        Path('build/delivery/neoswap-host-source609.json')", "        Path('build/delivery/neoswap-host-source610.json')"),
        ('    - name: Authenticate the retained608 test evidence and original command logs',
         '    - name: Authenticate the reused fresh610 test jobs, command logs and the fresh delivery contract'),
        ('        python3 build-utils/melonx/package_runtime.py\n',
         '        python3 -B .github/diagnostics/rewind610_delivery.py melonx-materialize\n'),
        ('      run: python3 .github/diagnostics/rpcs3runtime607_core.py --embed-source',
         '      run: python3 .github/diagnostics/rpcs3core610_delivery.py --embed-source'),
        ('    - name: Embed609 identity, the new MeloNX Core proof and exact retained608 provenance',
         '    - name: Embed610 identity, the Core 610 proof and exact retained provenance'),
        ('    - name: Verify all90 signed images, the new MeloNX Core and retained608 payloads',
         '    - name: Verify all90 signed images, the Core 610 payload and retained609 payloads'),
    ):
        value = replace_once(value, before, after)
    require(value.count('rewind609_delivery.py') == 15, 'Unexpected609 application operation inventory')
    value = value.replace('rewind609_delivery.py', 'rewind610_delivery.py')
    # No test jobs: the fresh610 Flutter/native evidence of REUSED_TESTS is authenticated
    # in preflight and in the application job (test_jobs documents what those jobs ran).
    require('rewind609' not in value and 'rpcs3runtime607_core.py' not in value and "'609'" not in value,
            'A609 recipe call remains')
    return value


def workflow():
    """Local integration only: write the reviewed transform; the contract test checks equality."""
    require(not os.environ.get('CI') and not os.environ.get('GITHUB_ACTIONS'), 'The workflow may not be generated in CI')
    value = expected_workflow((ROOT / WORKFLOW609).read_text(), (ROOT / WORKFLOW608).read_text())
    (ROOT / WORKFLOW).write_text(value)
    return dict(result='written', path=WORKFLOW, sha256=sha(value.encode()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['contract', 'baseline', 'retained-ready', 'tests', 'workflow',
        'reuse-check', 'melonx-materialize',
        'download-core', 'component-runs', 'download-components', 'engine-evidence',
        'download-libretro', 'download-melonx-dependencies', 'dolphin', 'armsx2',
        'embed', 'structure', 'validate', 'seal'])
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args()
    if args.operation in ('embed', 'structure', 'validate'):
        require(args.path is not None, 'Missing application or IPA path')
        result = globals()[args.operation](args.path)
    elif args.operation in ('download-libretro', 'download-melonx-dependencies'):
        result = download_retained_archive(args.operation.removeprefix('download-'))
    elif args.operation in ('download-core', 'component-runs', 'download-components', 'engine-evidence'):
        result = retained(args.operation)
    elif args.operation in ('dolphin', 'armsx2'):
        result = native(args.operation)
    elif args.operation == 'retained-ready':
        result = retained_ready()
    elif args.operation == 'reuse-check':
        result = reuse_check()
    elif args.operation == 'melonx-materialize':
        result = melonx_materialize()
    else:
        result = globals()[args.operation]()
    print(json.dumps(result, indent=2, default=str))
