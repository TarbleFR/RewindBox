"""Authenticate and install the standalone Dolphin/Wiimmfi producer."""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import retained_components as retained
from delivery_benchmark import payload_fingerprint
from rewind608_producers import DOLPHIN_EXPORTS, member_hashes, save
from verify_ipa import macho

ROOT = retained.ROOT
WORKFLOW = '.github/workflows/achievement-translation-dolphin.yml'
JOB = 'Build Dolphin Core arm64'
STEPS = ('Patch and compile Dolphin Core', 'Materialize and validate Dolphin framework', 'Upload Dolphin Core')
IMAGE = 'Frameworks/DolphinCore.framework/DolphinCore'
INPUTS = ('build-utils/patch_dolphin_internal_core_v2.py', 'build-utils/dolphin_wiimmfi.py',
          'packages/dolphin_internal_bridge/core/')
WIIMMFI_BRIDGE_HEADER = 'packages/dolphin_internal_bridge/ios/Classes/DOLWiimmfi.h'
WIIMMFI_EXPORTS = {'_neostation_dolphin_wiimmfi_' + name for name in
                   ('abi', 'import', 'nand_ready', 'configure', 'import_progress', 'cancel_import', 'interrupt_boot')}


def wiimmfi_bridge_contract():
    header = (ROOT / WIIMMFI_BRIDGE_HEADER).read_text(encoding='utf-8')
    predicates = re.findall(r'\bDOLWiimmfiSupported\s*\(\s*\)\s*\{([^{}]*)\}', header)
    retained.require(len(predicates) == 1, 'Cannot identify the Wiimmfi bridge support predicate')
    predicate, = predicates
    versions = re.findall(r'\b(?:DOLWiimmfiABI|abi)\s*\(\s*\)\s*==\s*([1-9][0-9]*)\b', predicate)
    retained.require(len(versions) == 1, 'Cannot identify the Wiimmfi bridge ABI')
    symbols = re.findall(r'\bdlsym\s*\(\s*RTLD_DEFAULT\s*,\s*"(neostation_dolphin_wiimmfi_\w+)"\s*\)',
                         predicate)
    retained.require(len(symbols) == len(re.findall(r'\bdlsym\s*\(', predicate)),
                     'Cannot identify the required Wiimmfi bridge symbols')
    return int(versions[0]), WIIMMFI_EXPORTS | {'_' + name for name in symbols}


def input_bytes(source=None):
    folder = 'packages/dolphin_internal_bridge/core/'
    if source is None:
        paths = [str(p.relative_to(ROOT)) for p in sorted((ROOT / folder).glob('*.inc'))]
        read = lambda path: (ROOT / path).read_bytes()
    else:
        paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', source, '--', folder],
                                        cwd=ROOT, text=True).splitlines()
        paths = [p for p in paths if p.endswith('.inc')]
        read = lambda path: subprocess.check_output(['git', 'show', f'{source}:{path}'], cwd=ROOT)
    return {path: read(path) for path in [*INPUTS[:2], *paths]}


def authenticate(spec, api=None):
    api = api or retained.gh_api
    origin = spec['origin']
    run = api(f"actions/runs/{origin['run']}/attempts/{origin['attempt']}")
    retained.require(run['id'] == origin['run'] and run['head_sha'] == origin['source'] and
                     run['head_branch'] == 'Claude' and run['path'] == origin['workflow'] == WORKFLOW and
                     run['run_attempt'] == origin['attempt'] and run['status'] == 'completed' and
                     run['conclusion'] == 'success', 'Wrong Dolphin producer run')
    job = api(f"actions/jobs/{origin['job']}")
    retained.require(job['id'] == origin['job'] and job['run_id'] == origin['run'] and
                     job['head_sha'] == origin['source'] and job['run_attempt'] == origin['attempt'] and
                     job['name'] == JOB and job['conclusion'] == 'success' and
                     set(STEPS) <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
                     'Wrong Dolphin producer job or incomplete verification')
    try:
        artifact = api(f"actions/artifacts/{origin['artifact']}")
    except subprocess.CalledProcessError as error:
        retained.require(spec.get('republished') and b'HTTP 404' in (error.stderr or b''),
                         'Dolphin producer archive is unavailable')
        artifact = None
    if artifact is not None:
        retained.require(artifact['id'] == origin['artifact'] and artifact['name'] == origin['name'] and
                         artifact['size_in_bytes'] == origin['bytes'] and
                         artifact['digest'] == 'sha256:' + origin['sha256'] and
                         artifact['workflow_run']['id'] == origin['run'] and
                         artifact['workflow_run']['head_sha'] == origin['source'] and
                         (not artifact['expired'] or spec.get('republished')), 'Wrong Dolphin archive')
    return dict(result='authenticated', kind='dolphin',
                execution={k: origin[k] for k in ('source', 'tree', 'run', 'attempt')},
                job=origin['job'], artifact=origin['artifact'], archiveSHA256=origin['sha256'],
                archiveBytes=origin['bytes'], artifactName=origin['name'], republished=spec.get('republished'))


def verify(directory, compiled, spec):
    identity = json.loads((directory / 'identity.json').read_bytes())
    source = compiled['execution']['source']
    tree = subprocess.check_output(['git', 'rev-parse', source + '^{tree}'], cwd=ROOT, text=True).strip()
    expected = {p: retained.sha(raw) for p, raw in input_bytes(source).items()}
    current = {p: retained.sha(raw) for p, raw in input_bytes().items()}
    abi, wiimmfi_exports = wiimmfi_bridge_contract()
    retained.require(tree == compiled['execution']['tree'] and identity['host_commit'] == source and
                     identity['source_revision'] == spec['upstreamRevision'] and identity['wiimmfi_abi'] == abi and
                     identity['architectures'] == ['arm64'] and identity['achievement_presenter'] == 1 and
                     identity['use_retro_achievements'] is True and identity['source_inputs'] == expected == current,
                     'Dolphin compiled inputs, ABI or effective checkout differ')
    raw = (directory / 'DolphinCore.framework/DolphinCore').read_bytes()
    image = macho(raw)
    fingerprint = payload_fingerprint(raw)
    retained.require(retained.sha(raw) == identity['sha256'] and fingerprint == spec['payloadFingerprint'] and
                     image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
                     image['id'] == '@rpath/DolphinCore.framework/DolphinCore' and
                     (DOLPHIN_EXPORTS | wiimmfi_exports) <= set(image['definedSymbols']),
                     'Invalid Dolphin binary identity or exports')
    postimages = member_hashes(directory / 'patched-source')
    retained.require(set(postimages) == {'AchievementManager.cpp', 'NeoStationBridge.mm'} and
                     (directory / 'Sys').is_dir() and (directory / 'cacert.pem').is_file(),
                     'Missing Dolphin runtime resources or producer source notices')
    return dict(compiled, identity=identity, payloadFingerprint=fingerprint, sourceInputs=expected,
                compiledSourcePostimages=postimages, compiledHostInputs=expected, physicalDeviceTested=False)


def install(spec, install=True):
    origin = spec['origin']
    compiled = authenticate(spec)
    path = retained.native_archive('dolphin')
    if spec.get('republished'):
        retained.republished_archive('dolphin', origin, spec['republished'], path)
    else:
        retained.fetch_artifact(origin['artifact'], origin['bytes'], origin['sha256'], path)
    directory = retained.safe_extract(path, retained.CACHE / 'dolphin')
    result = verify(directory, compiled, spec)
    if install:
        replacements = ((directory / 'DolphinCore.framework',
                         ROOT / 'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework'),
                        (directory / 'Sys', ROOT / 'ios/Runner/Sys'))
        for source, destination in replacements:
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        shutil.copy2(directory / 'cacert.pem', ROOT / 'ios/Runner/cacert.pem')
        (replacements[0][1] / 'DolphinCore').chmod(0o755)
        fast_path = ROOT / 'build/fast-native/identity.json'
        fast = json.loads(fast_path.read_bytes())
        fast.update(dolphinCoreSha256=result['identity']['sha256'], dolphinCoreHostCommit=origin['source'],
                    dolphinCoreRunId=origin['run'], dolphinSourceRevision=spec['upstreamRevision'],
                    dolphinAchievementPresentationVersion=1, dolphinAchievementSessionPolicyVersion=1)
        save(fast_path, fast)
    return dict(result, installed=install, coreRecompiled=spec['mode'] == 'replace')


def embed_notices(spec, app):
    directory = retained.CACHE / 'dolphin'
    destination = Path(app) / 'Legal' / spec['legalFolder']
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(directory / 'patched-source', destination / 'patched-source', dirs_exist_ok=True)
    shutil.copy2(directory / 'identity.json', destination / 'identity.json')
    contents = input_bytes(spec['origin']['source'])
    with zipfile.ZipFile(destination / 'compiled-host-inputs.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in contents.items():
            archive.writestr(name, raw)
    save(destination / 'source-provenance.json', dict(source=spec['origin']['source'],
         upstreamRevision=spec['upstreamRevision'], inputs={p: retained.sha(raw) for p, raw in contents.items()},
         note='Host patch inputs and the two patched source files included by the authenticated producer.'))
    return str(destination.relative_to(app))


def verify_notices(archive, prefix, component):
    with zipfile.ZipFile(io.BytesIO(archive.read(prefix + 'compiled-host-inputs.zip'))) as inputs:
        names = inputs.namelist()
        retained.require(len(names) == len(set(names)) and
                         {name: retained.sha(inputs.read(name)) for name in names} == component['compiledHostInputs'] ==
                         component['identity']['source_inputs'], 'Dolphin compiled host input notices differ')
    record = json.loads(archive.read(prefix + 'source-provenance.json'))
    retained.require(record['source'] == component['execution']['source'] and
                     record['upstreamRevision'] == component['identity']['source_revision'] and
                     record['inputs'] == component['compiledHostInputs'], 'Dolphin source provenance notice differs')
