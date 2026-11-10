"""Retain the MeloNX Core87 already delivered in IPA596.

Only immutable producer metadata, original payload bytes and the host boundary
are checked here. The delivered596 receipt owns the source/Apple/simulator
proofs; no historical source contract, test suite or compiler is replayed.
The existing596 module supplies constants and pure Mach-O parsing helpers.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import rewind596_engine as retained

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / 'dist/melonx'
BUILD = 597
BASELINE = 596
BASELINE_SOURCE = 'd5c5f107f7b514980033d1b95218aa9d2f640609'
BASELINE_RUN = 40968162236
BASELINE_IPA_SHA256 = 'b8d665ab4503fc4f3492b80bb46ed582dcfed71e99982f82a8c2a8a04a842d07'
BASELINE_RECEIPT = 'docs/evidence/rewind596-delivery.json'
BASELINE_RECEIPT_SHA256 = '1965bfdf5ab2f93f26302ebb3314d6b0e42f574c71486e503f09a1bc8a079808'
PACKAGED_FINGERPRINT = '937b2a47a4d8413eca146a8afb0423a9ecffb7b4913de069f7c07074ab914e56'

MELONX_SOURCE = retained.MELONX_SOURCE
MELONX_VALIDATION_SOURCE = retained.MELONX_VALIDATION_SOURCE
MELONX_RUN = retained.MELONX_RUN
MELONX_JOB = retained.MELONX_JOB
MELONX_WORKFLOW = retained.MELONX_WORKFLOW
MELONX_COMPILE_RUN = retained.MELONX_COMPILE_RUN
MELONX_COMPILE_JOB = retained.MELONX_COMPILE_JOB
MELONX_ARTIFACT_ID = retained.MELONX_ARTIFACT_ID
MELONX_ARTIFACT_NAME = retained.MELONX_ARTIFACT_NAME
MELONX_ARTIFACT_BYTES = retained.MELONX_ARTIFACT_BYTES
MELONX_ARTIFACT_SHA256 = retained.MELONX_ARTIFACT_SHA256
MELONX_ARTIFACT = (MELONX_ARTIFACT_ID, MELONX_ARTIFACT_SHA256)
PACKAGED_ID = retained.PACKAGED_ID
BINARY_SHA256 = retained.BINARY_SHA256
BINARY_BYTES = retained.BINARY_BYTES
IDENTITY_SHA256 = retained.IDENTITY_SHA256
EXPORTS = retained.EXPORTS
ENGINE_COMMITS = retained.ENGINE_COMMITS
check_image = retained.check_image
image_info = retained.image_info
normalized_payload_fingerprint = retained.normalized_payload_fingerprint


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(endpoint):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint],
        cwd=ROOT, timeout=120))


@lru_cache(maxsize=1)
def baseline_component():
    """Read only the immediately delivered baseline, without importing its recipe."""
    raw = (ROOT / BASELINE_RECEIPT).read_bytes()
    require(sha(raw) == BASELINE_RECEIPT_SHA256, 'Delivered596 receipt changed')
    receipt = json.loads(raw)
    require(receipt['result'] == 'passed' and receipt['build'] == BASELINE and
            receipt['source'] == BASELINE_SOURCE and receipt['run']['id'] == BASELINE_RUN and
            receipt['run']['conclusion'] == 'success' and
            receipt['ipa']['sha256'] == BASELINE_IPA_SHA256,
            'Wrong delivered baseline for retained MeloNX')
    item = receipt['melonx']
    require(item['source'] == MELONX_SOURCE and item['run'] == MELONX_RUN and
            item['job'] == MELONX_JOB and item['artifact']['id'] == MELONX_ARTIFACT_ID and
            item['artifact']['bytes'] == MELONX_ARTIFACT_BYTES and
            item['artifact']['sha256'] == MELONX_ARTIFACT_SHA256 and
            item['packagedCoreFingerprint'] == PACKAGED_FINGERPRINT and
            item['originalPayloadMatched'] is True,
            'Retained engine pins differ from delivered596')
    for runtime in BINARY_SHA256:
        image = item['images'][runtime]
        require(image['sha256'] == BINARY_SHA256[runtime] and
                image['bytes'] == BINARY_BYTES[runtime] and
                image['identitySHA256'] == IDENTITY_SHA256[runtime],
                'Retained image differs from delivered596: ' + runtime)
    return item


def _query_engine_run():
    baseline_component()
    run = api(f'actions/runs/{MELONX_RUN}')
    require(run['id'] == MELONX_RUN and run['head_sha'] == MELONX_SOURCE and
            run['path'] == MELONX_WORKFLOW and run['run_attempt'] == 1 and
            run['run_number'] == 87 and run['status'] == 'completed' and
            run['conclusion'] == 'success', 'Wrong retained MeloNX producer run')
    job = api(f'actions/jobs/{MELONX_JOB}')
    require(job['id'] == MELONX_JOB and job['run_id'] == MELONX_RUN and
            job['head_sha'] == MELONX_SOURCE and job['run_attempt'] == 1 and
            job['status'] == 'completed' and job['conclusion'] == 'success',
            'Wrong retained MeloNX producer job')
    artifact = api(f'actions/artifacts/{MELONX_ARTIFACT_ID}')
    require(artifact['id'] == MELONX_ARTIFACT_ID and artifact['name'] == MELONX_ARTIFACT_NAME and
            artifact['size_in_bytes'] == MELONX_ARTIFACT_BYTES and not artifact['expired'] and
            artifact['digest'] == 'sha256:' + MELONX_ARTIFACT_SHA256 and
            artifact['workflow_run']['id'] == MELONX_RUN and
            artifact['workflow_run']['head_sha'] == MELONX_SOURCE,
            'Retained MeloNX artifact changed or expired')
    return dict(result='passed', source=MELONX_SOURCE, run=MELONX_RUN, job=MELONX_JOB,
                runAttempt=1, compileRun=MELONX_COMPILE_RUN,
                originalRunConclusion='success', validationSource=MELONX_VALIDATION_SOURCE,
                artifact=MELONX_ARTIFACT_ID, artifactSHA256=MELONX_ARTIFACT_SHA256,
                retainedFromDelivery=BASELINE, baselineReceiptSHA256=BASELINE_RECEIPT_SHA256,
                engineRecompiled=False, priorGatesReexecuted=False)


def engine_run():
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse('597-melonx-run', _query_engine_run)


def engine_identity(runtime='ios-arm64'):
    """Keep the producer identity bytes; its fixed hash already seals all inputs."""
    baseline_component()
    require(runtime in BINARY_SHA256, 'Unknown MeloNX runtime')
    raw = (NEW / runtime / 'identity.json').read_bytes()
    require(sha(raw) == IDENTITY_SHA256[runtime], 'Retained MeloNX identity bytes changed')
    identity = json.loads(raw)
    require(identity['host'] == MELONX_SOURCE and identity['runtimeIdentifier'] == runtime and
            identity['sha256'] == BINARY_SHA256[runtime] and identity['size'] == BINARY_BYTES[runtime] and
            identity['embeddedLibraryAbi'] == 2 and identity['embeddedSessionImplemented'] is True and
            identity['embeddedSessionDeviceVerified'] is False and
            sorted(identity['exports']) == sorted(EXPORTS), 'Retained MeloNX identity mismatch')
    # Current host compatibility is small; the enclosing597 product contract
    # separately proves that Store.cpp is the only product change since596.
    source = (ROOT / 'build-utils/melonx/source.json').read_bytes()
    require(sha(source) == retained.SOURCE_CONFIG_SHA256 and identity['source'] == json.loads(source),
            'MeloNX source boundary changed')
    for path, expected in retained.RUNTIME_SHA256.items():
        if path.startswith('packages/'):
            require(sha((ROOT / path).read_bytes()) == expected, 'MeloNX runtime boundary changed: ' + path)
    return identity


def engine_evidence():
    """A small delivery binding; the unchanged Apple proofs remain in baseline596."""
    metadata = engine_run()
    identity = engine_identity()
    raw = (NEW / 'ios-arm64/Ryujinx.Library.dylib').read_bytes()
    require(len(raw) == BINARY_BYTES['ios-arm64'] and sha(raw) == BINARY_SHA256['ios-arm64'],
            'Retained iPhone engine payload changed')
    image = check_image(raw, 'ios-arm64')
    fingerprint = normalized_payload_fingerprint(raw)
    require(fingerprint == PACKAGED_FINGERPRINT, 'Retained engine differs from delivered596 payload')
    return dict(result='passed', build=BUILD, baseline=BASELINE, source=MELONX_SOURCE,
                run=MELONX_RUN, job=MELONX_JOB, compileRun=MELONX_COMPILE_RUN,
                originalRunConclusion='success', validationSource=MELONX_VALIDATION_SOURCE,
                metadata=metadata, artifact=MELONX_ARTIFACT_ID,
                expectedArchiveSHA256=MELONX_ARTIFACT_SHA256,
                images={'ios-arm64': dict(sha256=identity['sha256'], bytes=len(raw),
                    identitySHA256=IDENTITY_SHA256['ios-arm64'], platform=image['platform'],
                    requiredExports=len(EXPORTS))},
                baselineReceipt=dict(path=BASELINE_RECEIPT, sha256=BASELINE_RECEIPT_SHA256,
                    source=BASELINE_SOURCE, run=BASELINE_RUN, ipaSHA256=BASELINE_IPA_SHA256),
                authoritativePayload='ios-arm64/Ryujinx.Library.dylib',
                originalPayloadFingerprint=fingerprint, originalCompileIdentitiesPreserved=True,
                retainedProducerProofs=True, engineRecompiled=False, priorGatesReexecuted=False,
                historicalContractsReplayed=False, rootPayloadUsed=False,
                physicalDeviceTested=False, gameTested=False, fpsGainMeasured=False)
