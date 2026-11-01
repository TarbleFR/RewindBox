"""Retained components of a standard delivery: authenticated, never rebuilt.

Two kinds, both pinned by the build manifest (build-utils/delivery/<N>.json):

- retained natives (the 608 Dolphin and ARMSX2 Cores): the original
  successful producer job of its run, its uploaded archive (id, name, size,
  digest), the delivered receipt that consumed that exact archive, the
  producer record of compiled inputs (rewind608_producers.input_paths and
  rewind608_reuse.original_input_hashes stay the definition of those inputs),
  the patched upstream source snapshot, the Mach-O and its signed payload
  fingerprint. Ported from rewind610_delivery.native and
  rewind609_delivery.reused_origin/fetch_reused with every pin from the manifest.
- retained archives (the libretro cores and the MeloNX native dependencies):
  the producer run and artifact, then the archive's own identity.

A component may also come from a republished bundle: a later delivery
re-uploads the exact archive it authenticated (original.zip) next to a record
(republication.json) binding it to the original producer. The bundle is
accepted only if the record matches the manifest's original pin and the
content digest equals the original artifact digest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for _part in ('.github/diagnostics', 'build-utils', 'packages/dolphin_internal_bridge/ci'):
    if str(ROOT / _part) not in sys.path:
        sys.path.insert(0, str(ROOT / _part))

REPOSITORY = 'TarbleFR/RewindBox'
CACHE = ROOT / 'build/components-retained'
NATIVES = ('dolphin', 'armsx2')
ARCHIVES = ('libretro', 'melonx-dependencies')
STANDARD_WORKFLOW = '.github/workflows/standard-delivery.yml'
REPUBLISH_ROOT = 'build/republish'
REPUBLISHED_MEMBERS = {'original.zip', 'republication.json'}
CORE_NAMES = {'dolphin': 'DolphinCore', 'armsx2': 'ARMSX2Core'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def gh_api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/' + endpoint], cwd=ROOT, timeout=120))


def gh_download(artifact, path):
    with open(path, 'wb') as output:
        subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{artifact}/zip'],
                       stdout=output, cwd=ROOT, check=True, timeout=600)


def safe_extract(archive_path, destination):
    from rewind606_engine import safe_members
    if destination.exists():
        shutil.rmtree(destination)
    with zipfile.ZipFile(archive_path) as archive:
        safe_members(archive)
        archive.extractall(destination)
    return destination


def fetch_artifact(artifact, size, digest, path, download=None):
    """Download one artifact ZIP once; the bytes must equal the pinned size and digest."""
    download = download or gh_download
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size != size or sha_file(path) != digest:
        temporary = path.with_suffix('.part')
        download(artifact, temporary)
        require(temporary.stat().st_size == size and sha_file(temporary) == digest,
                f'Downloaded artifact {artifact} differs from its pinned size or digest')
        temporary.replace(path)
    return path


# --- Republication -----------------------------------------------------------------------------

ORIGIN_KEYS = ('workflow', 'source', 'run', 'attempt', 'job', 'artifact', 'name', 'bytes', 'sha256')


def original_binding(origin):
    return {key: origin.get(key) for key in ORIGIN_KEYS}


def republication_record(kind, origin, content_path, republisher):
    return dict(schema=1, kind=kind, original=original_binding(origin), content='original.zip',
                contentSHA256=sha_file(content_path), contentBytes=Path(content_path).stat().st_size,
                republisher=dict(republisher), retentionDays=90,
                note='Open-source component archive authenticated and re-uploaded unchanged; never an IPA.')


def stage_republication(kind, origin, archive_path, republisher, root=ROOT):
    """Write build/republish/<kind>/{original.zip, republication.json} for one authenticated archive."""
    archive_path = Path(archive_path)
    require(archive_path.is_file() and archive_path.stat().st_size == origin['bytes'] and
            sha_file(archive_path) == origin['sha256'], 'Republication input differs from its authenticated archive: ' + kind)
    folder = Path(root) / REPUBLISH_ROOT / kind
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    shutil.copy2(archive_path, folder / 'original.zip')
    record = republication_record(kind, origin, folder / 'original.zip', republisher)
    (folder / 'republication.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def republished_archive(kind, origin, republished, path, api=None, download=None):
    """Accept a republished bundle as the origin of `origin`; write the original archive to `path`.

    `republished` pins the republished artifact (artifact, name, bytes, sha256) and its republisher
    (build, source, run, attempt, job). The bundle holds exactly original.zip and republication.json.
    """
    api = api or gh_api
    run = api(f"actions/runs/{republished['run']}")
    require(run['id'] == republished['run'] and run['head_sha'] == republished['source'] and
            run['path'] == STANDARD_WORKFLOW and run['head_branch'] == 'Claude' and
            run['run_attempt'] >= republished['attempt'], 'Wrong republishing delivery run: ' + kind)
    job = api('actions/jobs/' + str(republished['job']))
    step = republish_step(kind)
    require(job['run_id'] == republished['run'] and job['head_sha'] == republished['source'] and
            job['run_attempt'] == republished['attempt'] and job['name'] == 'application' and
            step in {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'The republishing application job did not upload ' + kind)
    artifact = api('actions/artifacts/' + str(republished['artifact']))
    require(artifact['id'] == republished['artifact'] and artifact['name'] == republished['name'] and
            artifact['size_in_bytes'] == republished['bytes'] and
            artifact['digest'] == 'sha256:' + republished['sha256'] and not artifact['expired'] and
            artifact['workflow_run']['id'] == republished['run'] and
            artifact['workflow_run']['head_sha'] == republished['source'], 'Wrong republished artifact: ' + kind)
    bundle = fetch_artifact(republished['artifact'], republished['bytes'], republished['sha256'],
                            Path(path).with_name(Path(path).name + '.republished.zip'), download)
    with zipfile.ZipFile(bundle) as archive:
        from rewind606_engine import safe_members
        names = safe_members(archive)
        require(set(names) == REPUBLISHED_MEMBERS and len(names) == 2, 'Unexpected republished members: ' + kind)
        record = json.loads(archive.read('republication.json'))
        content = archive.read('original.zip')
    require(record.get('schema') == 1 and record.get('kind') == kind and record.get('content') == 'original.zip' and
            record.get('original') == original_binding(origin) and record.get('contentSHA256') == origin['sha256'] and
            record.get('contentBytes') == origin['bytes'] and len(content) == origin['bytes'] and
            sha(content) == origin['sha256'], 'Republished content is not the original authenticated archive: ' + kind)
    expected_republisher = {key: republished[key] for key in ('build', 'source', 'run', 'attempt')}
    require({key: record['republisher'].get(key) for key in expected_republisher} == expected_republisher,
            'Republication record names another delivery: ' + kind)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)
    return dict(republished=dict(republished), record=record)


def republish_step(kind):
    """Constant step name of the standard workflow that uploads one republished archive."""
    return f'Republish the authenticated {kind} archive'


# --- Retained 608 natives -------------------------------------------------------------------------

def native_origin(kind, spec, api=None):
    """The original successful producer job and archive of a retained native Core."""
    api = api or gh_api
    require(kind in NATIVES and spec.get('mode') == 'retain', 'Not a retained native component: ' + kind)
    origin = spec['origin']
    run = api(f"actions/runs/{origin['run']}/attempts/{origin['attempt']}")
    require(run['id'] == origin['run'] and run['head_sha'] == origin['source'] and run['head_branch'] == 'Claude' and
            run['path'] == origin['workflow'] and run['run_attempt'] == origin['attempt'] and
            run['status'] == 'completed' and run['conclusion'] == origin['runConclusion'],
            'The original producer run of ' + kind + ' changed')
    job = api('actions/jobs/' + str(origin['job']))
    require(job['id'] == origin['job'] and job['run_id'] == origin['run'] and job['head_sha'] == origin['source'] and
            job['run_attempt'] == origin['attempt'] and job['status'] == 'completed' and
            job['conclusion'] == 'success' and job['name'] == origin['jobName'], 'Original producer job changed: ' + kind)
    require(set(origin['steps']) <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'Original producer omitted a required step: ' + kind)
    artifact = api('actions/artifacts/' + str(origin['artifact']))
    republished = spec.get('republished')
    require(artifact['id'] == origin['artifact'] and artifact['name'] == origin['name'] and
            artifact['size_in_bytes'] == origin['bytes'] and artifact['digest'] == 'sha256:' + origin['sha256'] and
            (republished is not None or not artifact['expired']) and
            artifact['workflow_run']['id'] == origin['run'] and artifact['workflow_run']['head_sha'] == origin['source'],
            'Original producer archive changed or expired: ' + kind)
    consumer = spec['consumedBy']
    raw = (ROOT / consumer['receipt']).read_bytes()
    require(sha(raw) == consumer['sha256'], 'The consuming delivery receipt changed: ' + consumer['receipt'])
    delivered = json.loads(raw)
    original = delivered['reusedEvidence']['originalArchives'][kind]
    execution = dict(source=origin['source'], tree=origin['tree'], run=origin['run'], attempt=origin['attempt'])
    require(original['job'] == origin['job'] and original['artifact'] == origin['artifact'] and
            original['archiveSHA256'] == origin['sha256'] and original['originalJobConclusion'] == 'success' and
            delivered['reusedEvidence']['execution'] == execution,
            f"Delivered{consumer['build']} did not consume this exact archive: {kind}")
    return dict(result='authenticated', evidenceMode='reused', retainedFrom=spec['retainedSince'], kind=kind,
                execution=execution, job=origin['job'], artifact=origin['artifact'], artifactName=origin['name'],
                archiveSHA256=origin['sha256'], archiveBytes=origin['bytes'], expiresAt=artifact['expires_at'],
                republished=republished)


def native_archive(kind):
    return CACHE / f'{kind}.zip'


def fetch_native(kind, spec, api=None, download=None):
    value = native_origin(kind, spec, api)
    path = native_archive(kind)
    if spec.get('republished'):
        republished_archive(kind, spec['origin'], spec['republished'], path, api, download)
    else:
        fetch_artifact(value['artifact'], value['archiveBytes'], value['archiveSHA256'], path, download)
    require(sha_file(path) == value['archiveSHA256'], 'Retained native archive digest differs: ' + kind)
    return value, safe_extract(path, CACHE / kind)


def install_native(kind, spec):
    """Install a retained 608 Dolphin/ARMSX2 Core exactly as IPA609 and IPA610 did (same producer, same checks)."""
    import rewind608_producers as producers608
    import rewind608_reuse as reuse608
    from verify_ipa import macho
    from delivery_benchmark import payload_fingerprint
    value, directory = fetch_native(kind, spec)
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
    core_name = CORE_NAMES[kind]
    raw = (directory / f'{core_name}.framework/{core_name}').read_bytes()
    require(sha(raw) == identity['sha256'], 'Native binary differs from its compiled identity')
    image = macho(raw)
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
            image['id'] == f'@rpath/{core_name}.framework/{core_name}', 'Wrong retained608 native Mach-O')
    fingerprint = payload_fingerprint(raw)
    require(fingerprint == spec['payloadFingerprint'], 'Retained Core differs from its delivered signed payload: ' + kind)
    if kind == 'dolphin':
        require(record['upstreamRevision'] == identity['source_revision'] == producers608.DOLPHIN_SOURCE ==
                spec['upstreamRevision'] and identity['achievement_session_policy'] == 1 and
                identity['achievement_presenter'] == 1 and identity['use_retro_achievements'] is True and
                identity['source_inputs'] == original_inputs, 'Wrong retained608 Dolphin policy provenance')
        require(producers608.DOLPHIN_EXPORTS <= set(image['definedSymbols']), 'Missing additive Dolphin RA exports')
        replacements = ((directory / 'DolphinCore.framework',
                         ROOT / 'packages/dolphin_internal_bridge/ios/Frameworks/DolphinCore.framework'),
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
        require(identity['revision'] == record['upstreamRevision'] == source['revision'] == spec['upstreamRevision'] and
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
    return dict(value, identity=identity, payloadFingerprint=fingerprint, sourceInputs=record['inputs'],
                candidateSourceInputs=current, compiledSourcePostimages=record['compiledSourcePostimages'],
                coreRecompiled=False, retainedSince=spec['retainedSince'], physicalDeviceTested=False)


def embed_native_notices(kind, spec, app):
    directory = CACHE / kind
    destination = Path(app) / 'Legal' / spec['legalFolder']
    shutil.copytree(directory / 'patched-source608', destination / 'patched-source', dirs_exist_ok=True)
    for name in ('producer608.json', 'identity.json'):
        shutil.copy2(directory / name, destination / name)
    return str(destination.relative_to(app))


# --- Retained producer archives (libretro cores, MeloNX native dependencies) ----------------------

def archive_origin(kind, spec, api=None):
    api = api or gh_api
    require(kind in ARCHIVES and spec.get('mode') == 'retain-archive', 'Not a retained archive component: ' + kind)
    origin = spec['origin']
    run = api(f"actions/runs/{origin['run']}")
    require(run['id'] == origin['run'] and run['head_sha'] == origin['source'] and run['path'] == origin['workflow'] and
            run['head_branch'] == origin['branch'] and run['status'] == 'completed' and
            run['conclusion'] == origin['runConclusion'], 'The retained archive producer run changed: ' + kind)
    artifact = api('actions/artifacts/' + str(origin['artifact']))
    republished = spec.get('republished')
    require(artifact['id'] == origin['artifact'] and artifact['name'] == origin['name'] and
            artifact['size_in_bytes'] == origin['bytes'] and artifact['digest'] == 'sha256:' + origin['sha256'] and
            artifact['workflow_run']['id'] == origin['run'] and artifact['workflow_run']['head_sha'] == origin['source'] and
            (republished is not None or not artifact['expired']), 'Retained runtime archive changed or expired: ' + kind)
    return dict(result='authenticated', kind=kind, artifact=origin['artifact'], run=origin['run'],
                source=origin['source'], name=origin['name'], bytes=origin['bytes'], sha256=origin['sha256'],
                destination=spec['destination'], workflow=origin['workflow'], expiresAt=artifact['expires_at'],
                republished=republished)


def retained_archive(kind):
    return CACHE / f'retained-{kind}.zip'


def download_archive(kind, spec, api=None, download=None):
    value = archive_origin(kind, spec, api)
    path = retained_archive(kind)
    if spec.get('republished'):
        republished_archive(kind, spec['origin'], spec['republished'], path, api, download)
    else:
        fetch_artifact(value['artifact'], value['bytes'], value['sha256'], path, download)
    require(sha_file(path) == value['sha256'], 'Retained archive digest differs: ' + kind)
    safe_extract(path, ROOT / spec['destination'])
    return value


def verify_libretro(spec):
    """The retained libretro runtime: digests, source identity and exported ABI (delivered inline check)."""
    sys.path[:0] = [str(ROOT / 'packages/dolphin_internal_bridge/ci'), str(ROOT / 'build-utils')]
    from verify_ipa import macho
    root = ROOT / spec['destination']
    identity = json.loads((root / 'identity.json').read_text())
    manifest = json.loads((ROOT / 'build-utils/libretro/cores.json').read_text())
    require(identity['host_commit'] == spec['origin']['source'], 'Wrong libretro producer source: ' + identity['host_commit'])
    require([core['id'] for core in identity['cores']] == [core['id'] for core in manifest['cores']],
            'Libretro core inventory differs from build-utils/libretro/cores.json')
    require(identity['moltenVK']['files'] == manifest['moltenVK']['files'], 'Libretro MoltenVK files differ')
    for relative, digest in identity['files'].items():
        require(sha((root / relative).read_bytes()) == digest, 'Libretro file differs: ' + relative)
    required = {'_retro_api_version', '_retro_init', '_retro_deinit', '_retro_run', '_retro_load_game',
                '_retro_unload_game'}
    for core in identity['cores']:
        binary = root / 'Frameworks' / f"{core['id']}_libretro.framework" / f"{core['id']}_libretro"
        require(sha(binary.read_bytes()) == core['sha256'], 'Libretro core differs: ' + core['id'])
        image = macho(binary.read_bytes())
        require(image['platform'] == 2 and image['fileType'] == 6, 'Wrong libretro Mach-O: ' + core['id'])
        require(required <= set(image['definedSymbols']), 'Libretro ABI export missing: ' + core['id'])
        binary.chmod(0o755)
    (root / 'Frameworks/MoltenVK.framework/MoltenVK').chmod(0o755)
    fast_path = ROOT / 'build/fast-native/identity.json'
    fast = json.loads(fast_path.read_text())
    fast.update({'libretroCoresHostCommit': identity['host_commit'], 'libretroCoresRun': str(spec['origin']['run']),
                 'libretroCores': {core['id']: core['sha256'] for core in identity['cores']}})
    fast_path.write_text(json.dumps(fast, indent=2) + '\n')
    return dict(result='verified', cores=len(identity['cores']), files=len(identity['files']),
                hostCommit=identity['host_commit'], run=spec['origin']['run'])


# --- Inputs of retained components ----------------------------------------------------------------

def input_paths(kind, spec, listing):
    """Repository paths a retained component was built from (`listing(prefix) -> paths`)."""
    inputs = spec.get('inputs')
    if inputs == 'rewind608_producers.input_paths':
        import rewind608_producers as producers608
        shared = {producers608.WORKFLOW, '.github/diagnostics/rewind608_producers.py'}
        if kind == 'dolphin':
            paths = shared | {'build-utils/patch_dolphin_internal_core_v2.py',
                              'packages/dolphin_internal_bridge/ci/build_support.py',
                              'packages/dolphin_internal_bridge/ci/verify_ipa.py'}
            folders = ('packages/dolphin_internal_bridge/core',)
        else:
            paths = shared | {'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h'}
            folders = ('build-utils/armsx2', 'packages/armsx2_internal_bridge/core')
        for folder in folders:
            paths.update(p for p in listing(folder + '/') if '__pycache__' not in Path(p).parts)
        return sorted(paths)
    paths = set()
    for item in inputs or ():
        paths.update(listing(item) if item.endswith('/') else [item])
    return sorted(paths)


def same_definition_as_producers608(kind):
    """input_paths() above must enumerate exactly what rewind608_producers.input_paths does (working tree)."""
    import rewind608_producers as producers608

    def listing(prefix):
        folder = ROOT / prefix
        return [str(p.relative_to(ROOT)) for p in folder.rglob('*') if p.is_file()]
    return input_paths(kind, {'inputs': 'rewind608_producers.input_paths'}, listing) == producers608.input_paths(kind)


if __name__ == '__main__':
    print(json.dumps({'natives': NATIVES, 'archives': ARCHIVES}, indent=2))
