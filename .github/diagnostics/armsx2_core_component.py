"""Provenance and installation of the standalone RewindBox ARMSX2 Core producer."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import retained_components as retained
from rewind608_producers import execution, member_hashes, retain_patched_sources, save
from verify_ipa import macho
from delivery_benchmark import payload_fingerprint

ROOT = retained.ROOT
WORKFLOW = '.github/workflows/armsx2-core.yml'
RECORD = 'producer.json'
IMAGE = 'Frameworks/ARMSX2Core.framework/ARMSX2Core'
JOB = 'Compile pinned ARMSX2 iOS framework'
STEPS = ('Compile native core and verify binary ABI', 'Bind ARMSX2 inputs and compiled payload')
INPUTS = (
    WORKFLOW, '.github/diagnostics/armsx2_core_component.py',
    'build-utils/armsx2/', 'packages/armsx2_internal_bridge/core/',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2GraphicsHacks.h',
    'test/armsx2_core_build_test.py',
)


def input_hashes(tree=None):
    if tree is None:
        listing = lambda prefix: (str(p.relative_to(ROOT)) for p in (ROOT / prefix).rglob('*')
                                  if p.is_file() and '__pycache__' not in p.parts)
        read = lambda path: (ROOT / path).read_bytes()
    else:
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=ROOT)
        listing = lambda prefix: git('ls-tree', '-r', '--name-only', tree, '--', prefix).decode().splitlines()
        read = lambda path: git('show', f'{tree}:{path}')
    return {path: retained.sha(read(path)) for path in
            retained.input_paths('armsx2', {'inputs': INPUTS}, listing)}


def bind(source):
    folder = ROOT / 'dist/armsx2'
    origin = execution()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    identity = json.loads((folder / 'identity.json').read_bytes())
    retained.require(identity['host_commit'] == origin['source'] and identity['revision'] == revision,
                     'ARMSX2 Core was compiled from a different checkout')
    postimages = retain_patched_sources(source, folder / 'patched-source')
    expected = set(re.findall(r'^diff --git a/(\S+) b/\S+$',
                              (ROOT / 'build-utils/armsx2/neostation-core.patch').read_text(), re.MULTILINE))
    retained.require(expected and expected == set(postimages), 'ARMSX2 patched source inventory differs')
    save(folder / RECORD, dict(schema=1, kind='armsx2', execution=origin, inputs=input_hashes(),
                               compiledSourcePostimages=postimages, files=member_hashes(folder, (RECORD,))))


def authenticate(spec, api=None):
    api = api or retained.gh_api
    origin = spec['origin']
    run = api(f"actions/runs/{origin['run']}/attempts/{origin['attempt']}")
    retained.require(run['id'] == origin['run'] and run['head_sha'] == origin['source'] and
                     run['head_branch'] == 'Claude' and run['path'] == origin['workflow'] == WORKFLOW and
                     run['status'] == 'completed' and run['conclusion'] == 'success',
                     'Wrong ARMSX2 producer run')
    job = api(f"actions/jobs/{origin['job']}")
    retained.require(job['id'] == origin['job'] and job['run_id'] == origin['run'] and
                     job['head_sha'] == origin['source'] and job['run_attempt'] == origin['attempt'] and
                     job['name'] == JOB and job['conclusion'] == 'success' and
                     {*STEPS, 'Upload authenticated ARMSX2 Core'} <=
                     {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
                     'Wrong ARMSX2 producer job or incomplete verification')
    try:
        artifact = api(f"actions/artifacts/{origin['artifact']}")
    except subprocess.CalledProcessError as error:
        retained.require(spec.get('republished') and b'HTTP 404' in (error.stderr or b''),
                         'ARMSX2 producer archive is unavailable')
        artifact = None
    if artifact is not None:
        retained.require(artifact['id'] == origin['artifact'] and artifact['name'] == origin['name'] and
                         artifact['size_in_bytes'] == origin['bytes'] and
                         artifact['digest'] == 'sha256:' + origin['sha256'] and
                         artifact['workflow_run']['id'] == origin['run'] and
                         artifact['workflow_run']['head_sha'] == origin['source'] and
                         (not artifact['expired'] or spec.get('republished')), 'Wrong ARMSX2 archive')
    return dict(result='authenticated', kind='armsx2',
                execution={k: origin[k] for k in ('source', 'tree', 'run', 'attempt')},
                job=origin['job'], artifact=origin['artifact'], archiveSHA256=origin['sha256'],
                archiveBytes=origin['bytes'], artifactName=origin['name'], republished=spec.get('republished'))


def verify(directory, compiled, spec):
    record = json.loads((directory / RECORD).read_bytes())
    expected = input_hashes(compiled['execution']['source'])
    retained.require(record['schema'] == 1 and record['kind'] == 'armsx2' and
                     record['execution'] == compiled['execution'] and record['inputs'] == expected == input_hashes(),
                     'ARMSX2 compiled inputs differ from the effective checkout')
    retained.require(record['files'] == member_hashes(directory, (RECORD,)) and
                     record['compiledSourcePostimages'] == member_hashes(directory / 'patched-source'),
                     'ARMSX2 archive or patched source inventory differs')
    identity = json.loads((directory / 'identity.json').read_bytes())
    pin = json.loads((ROOT / 'build-utils/armsx2/source.json').read_bytes())
    retained.require(all(identity.get(k) == pin[k] for k in pin) and identity['abi_version'] == 9 and
                     identity['revision'] == spec['upstreamRevision'] and
                     identity['host_commit'] == compiled['execution']['source'] and
                     identity['architectures'] == ['arm64'] and identity['shader_chains'] is True and
                     identity['performance_overlays'] is True, 'Wrong ARMSX2 version, ABI or features')
    raw = (directory / 'ARMSX2Core.framework/ARMSX2Core').read_bytes()
    image = macho(raw)
    fingerprint = payload_fingerprint(raw)
    retained.require(retained.sha(raw) == identity['sha256'] and fingerprint == spec['payloadFingerprint'] and
                     image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
                     image['id'] == '@rpath/ARMSX2Core.framework/ARMSX2Core' and image['codeSignature'] is True and
                     set(image['definedSymbols']) == {'_NeoARMSX2_GetAPI'} and
                     pin['revision'].encode() in raw, 'Invalid ARMSX2 binary identity or ABI')
    assets = identity['bundled_shader_sha256']
    retained.require(len(assets) == identity['bundled_shader_files'] and
                     sum(name.startswith('presets/') and name.endswith('.slangp') for name in assets) >= 10 and
                     all(record['files'].get('ARMSX2Core.framework/shaders/' + name) == digest
                         for name, digest in assets.items()), 'Missing or altered ARMSX2 shader assets')
    return dict(compiled, identity=identity, payloadFingerprint=fingerprint, sourceInputs=expected,
                compiledSourcePostimages=record['compiledSourcePostimages'], physicalDeviceTested=False)


def install(spec, install=True):
    origin = spec['origin']
    compiled = authenticate(spec)
    path = retained.native_archive('armsx2')
    if spec.get('republished'):
        retained.republished_archive('armsx2', origin, spec['republished'], path)
    else:
        retained.fetch_artifact(origin['artifact'], origin['bytes'], origin['sha256'], path)
    directory = retained.safe_extract(path, retained.CACHE / 'armsx2')
    result = verify(directory, compiled, spec)
    if install:
        destination = ROOT / 'dist/armsx2'
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(directory, destination)
        (destination / 'ARMSX2Core.framework/ARMSX2Core').chmod(0o755)
        fast_path = ROOT / 'build/fast-native/identity.json'
        fast = json.loads(fast_path.read_bytes())
        fast.update(armsx2CoreSha256=result['identity']['sha256'], armsx2CoreHostCommit=origin['source'],
                    armsx2CoreRunId=origin['run'], armsx2SourceRevision=spec['upstreamRevision'])
        save(fast_path, fast)
    return dict(result, installed=install, coreRecompiled=spec['mode'] == 'replace')


def embed_notices(spec, app):
    directory = retained.CACHE / 'armsx2'
    destination = Path(app) / 'Legal' / spec['legalFolder']
    shutil.copytree(directory / 'patched-source', destination / 'patched-source', dirs_exist_ok=True)
    for name in (RECORD, 'identity.json'):
        shutil.copy2(directory / name, destination / name)
    return str(destination.relative_to(app))


if __name__ == '__main__':
    bind(Path(sys.argv[1]))
