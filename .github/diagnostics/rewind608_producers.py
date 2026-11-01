"""Create and authenticate same-run608 producer artifacts, never older fallbacks."""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import rewind608_baseline as tree

ROOT = tree.ROOT
OUT = ROOT / 'build/delivery'
WORKFLOW = '.github/workflows/rewind608-retro-achievements-delivery.yml'
DOLPHIN_SOURCE = '7cac54161659421ed95c2cd1c0b0746539a4cd38'
JOBS = {
    'flutter': 'Build608 source and Flutter tests',
    'native': 'Build608 Xcode16.4 native tests',
    'dolphin': 'Build608 Dolphin arm64',
    'armsx2': 'Build608 ARMSX2 ABI9 arm64',
}
REQUIRED_STEPS = {
    'flutter': {'Run source contracts and Flutter behavior'},
    'native': {'Run actual Xcode16.4 tests and host compilation'},
    'dolphin': {'Patch and compile Dolphin Core', 'Materialize and validate Dolphin framework',
                'Bind608 native inputs and compiled payload'},
    'armsx2': {'Compile native core and verify binary ABI', 'Bind608 native inputs and compiled payload'},
}
DOLPHIN_EXPORTS = {
    '_neostation_dolphin_initialize', '_neostation_dolphin_launch',
    '_neostation_dolphin_menu_snapshot', '_neostation_dolphin_cheats_snapshot',
    '_neostation_dolphin_set_cheats_enabled', '_neostation_dolphin_set_cheat_enabled',
    '_neostation_dolphin_download_gecko_codes', '_neostation_dolphin_set_achievement_presenter',
    '_neostation_dolphin_configure_achievements',
    '_neostation_dolphin_configure_achievements_session',
    '_neostation_dolphin_achievements_snapshot',
}
require, sha = tree.require, tree.sha


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return value


def execution():
    source = os.environ['GITHUB_SHA']
    require(re.fullmatch('[0-9a-f]{40}', source) and source == tree.git('rev-parse', 'HEAD'),
            'Producer checkout differs from the workflow SHA')
    return dict(source=source, tree=tree.git('rev-parse', 'HEAD^{tree}'),
                run=int(os.environ['GITHUB_RUN_ID']), attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))


def input_paths(kind):
    shared = {WORKFLOW, '.github/diagnostics/rewind608_producers.py'}
    if kind == 'dolphin':
        paths = shared | {'build-utils/patch_dolphin_internal_core_v2.py',
            'packages/dolphin_internal_bridge/ci/build_support.py',
            'packages/dolphin_internal_bridge/ci/verify_ipa.py'}
        folders = ('packages/dolphin_internal_bridge/core',)
    elif kind == 'armsx2':
        paths = shared | {'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h'}
        folders = ('build-utils/armsx2', 'packages/armsx2_internal_bridge/core')
    else:
        raise ValueError(kind)
    for folder in folders:
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    return sorted(paths)


def input_hashes(kind):
    return {name: sha((ROOT / name).read_bytes()) for name in input_paths(kind)}


def member_hashes(folder, excluded=()):
    result = {}
    for path in sorted(folder.rglob('*')):
        require(not path.is_symlink(), 'Native artifact contains a symlink: ' + str(path))
        if path.is_file():
            name = path.relative_to(folder).as_posix()
            if name not in excluded:
                result[name] = sha(path.read_bytes())
    return result


def retain_patched_sources(source, destination):
    """Keep actual modified upstream files, including generated untracked units."""
    paths = set(subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=source, text=True).splitlines())
    paths.update(subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'],
                                        cwd=source, text=True).splitlines())
    paths = sorted(p for p in paths if p.startswith(('Source/', 'Externals/', 'common/', 'cmake/', 'CMake/',
                                                     'pcsx2/', 'platforms/')) or p == 'CMakeLists.txt')
    require(paths, 'No actual patched native sources captured')
    captured = {}
    for name in paths:
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts, 'Unsafe upstream source path')
        original = source / path
        require(original.is_file() and not original.is_symlink(), 'Unsupported patched source entry: ' + name)
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        captured[name] = sha(original.read_bytes())
    return captured


def native_manifest(kind, source):
    require(kind in ('dolphin', 'armsx2'), 'Not a native producer')
    folder = ROOT / ('dist/dolphin' if kind == 'dolphin' else 'dist/armsx2')
    origin = execution()
    pinned = (DOLPHIN_SOURCE if kind == 'dolphin' else
              json.loads((ROOT / 'build-utils/armsx2/source.json').read_bytes())['revision'])
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    require(actual == pinned, 'Wrong native upstream checkout')
    patched = folder / 'patched-source608'
    if patched.exists():
        shutil.rmtree(patched)
    changed = retain_patched_sources(source, patched)
    if kind == 'armsx2':
        patch = (ROOT / 'build-utils/armsx2/neostation-core.patch').read_text()
        expected = set(re.findall(r'^diff --git a/(\S+) b/\S+$', patch, re.MULTILINE))
        require(expected and expected <= set(changed),
                'The actual ARMSX2 source notice omitted a patched upstream file')
    identity_path = folder / 'identity.json'
    identity = json.loads(identity_path.read_bytes())
    require(identity['host_commit'] == origin['source'], 'Native identity compiled another host')
    if kind == 'dolphin':
        require(identity['source_revision'] == pinned and identity['achievement_presenter'] == 1 and
                identity['use_retro_achievements'] is True, 'Dolphin RA compile identity differs')
        identity.update(achievement_session_policy=1, source_inputs=input_hashes(kind))
        save(identity_path, identity)
    else:
        require(identity['revision'] == pinned and identity['abi_version'] == 9,
                'ARMSX2 producer did not compile ABI9')
    value = dict(schema=1, build=608, kind=kind, execution=origin, upstreamRevision=pinned,
        inputs=input_hashes(kind), compiledSourcePostimages=changed,
        files=member_hashes(folder, ('producer608.json',)), physicalDeviceTested=False)
    return save(folder / 'producer608.json', value)


@lru_cache(maxsize=64)
def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/TarbleFR/RewindBox/' + endpoint],
                                             cwd=ROOT, timeout=120))


def origin(kind):
    current = execution()
    require(kind in JOBS, 'Unknown608 producer')
    run = api('actions/runs/' + str(current['run']))
    require(run['head_sha'] == current['source'] and run['head_branch'] == 'Claude' and
            run['path'] == WORKFLOW and run['run_attempt'] == current['attempt'] and
            run['event'] in ('push', 'workflow_dispatch'), 'Wrong same-run608 origin')
    # The application is still running. Authenticate completed prerequisite jobs,
    # never require or pretend that the whole delivery run already succeeded.
    jobs = api(f"actions/runs/{current['run']}/attempts/{current['attempt']}/jobs?per_page=100")
    require(jobs['total_count'] <= 100, 'Unexpected producer job pagination')
    matching = [j for j in jobs['jobs'] if j['name'] == JOBS[kind]]
    require(len(matching) == 1, 'Missing or duplicated608 producer job: ' + kind)
    job = matching[0]
    require(job['head_sha'] == current['source'] and job['run_id'] == current['run'] and
            job['run_attempt'] == current['attempt'] and job['status'] == 'completed' and
            job['conclusion'] == 'success', '608 prerequisite did not succeed: ' + kind)
    successful = {s['name'] for s in job['steps'] if s['conclusion'] == 'success'}
    require(REQUIRED_STEPS[kind] <= successful, '608 producer omitted a required step: ' + kind)
    artifact_id = int(os.environ[kind.upper() + '_ARTIFACT_ID'])
    digest = os.environ[kind.upper() + '_ARTIFACT_DIGEST'].removeprefix('sha256:')
    require(re.fullmatch('[0-9a-f]{64}', digest), 'Missing upload-artifact digest')
    artifact = api('actions/artifacts/' + str(artifact_id))
    expected_name = f"RewindBox608-{kind}-{current['source']}-attempt{current['attempt']}"
    require(artifact['name'] == expected_name and artifact['digest'] == 'sha256:' + digest and
            not artifact['expired'] and artifact['workflow_run']['id'] == current['run'] and
            artifact['workflow_run']['head_sha'] == current['source'], 'Wrong608 artifact binding: ' + kind)
    return dict(result='authenticated', kind=kind, execution=current, job=job['id'],
                artifact=artifact_id, artifactName=expected_name,
                archiveSHA256=digest, archiveBytes=artifact['size_in_bytes'])


def fetch(kind):
    value = origin(kind)
    archive_path = ROOT / f'build/components608/{kind}.zip'
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if (not archive_path.is_file() or archive_path.stat().st_size != value['archiveBytes'] or
            sha(archive_path.read_bytes()) != value['archiveSHA256']):
        temporary = archive_path.with_suffix('.part')
        with temporary.open('wb') as output:
            subprocess.run(['gh', 'api', f"repos/TarbleFR/RewindBox/actions/artifacts/{value['artifact']}/zip"],
                           stdout=output, cwd=ROOT, check=True, timeout=600)
        require(temporary.stat().st_size == value['archiveBytes'] and
                sha(temporary.read_bytes()) == value['archiveSHA256'], '608 archive digest/size mismatch')
        temporary.replace(archive_path)
    target = ROOT / f'build/components608/{kind}'
    if target.exists():
        shutil.rmtree(target)
    from rewind606_engine import safe_members
    with zipfile.ZipFile(archive_path) as archive:
        safe_members(archive)
        archive.extractall(target)
    return value, target


def tests():
    checked = {}
    for kind in ('flutter', 'native'):
        value, directory = fetch(kind)
        receipt = json.loads((directory / 'validation.json').read_bytes())
        require(receipt['result'] == 'passed' and receipt['group'] == kind and
                receipt['execution'] == execution(), 'Wrong608 test execution receipt')
        require(receipt['sourceScopeSHA256'] == sha((ROOT / tree.CONFIG).read_bytes()),
                'Tests were run on another reviewed source scope')
        require(receipt['commands'] and all(c['exitCode'] == 0 for c in receipt['commands']),
                'A required608 test command did not succeed')
        from rewind608_checks import command_names
        require([c['name'] for c in receipt['commands']] == command_names(kind),
                'A required608 command was omitted or replaced')
        for command in receipt['commands']:
            require(sha((directory / command['log']).read_bytes()) == command['logSHA256'],
                    '608 command log changed')
        if kind == 'native':
            require(receipt['xcodeVersion'].startswith('Xcode 16.4\n'), 'Wrong targeted native compiler')
            require('Apple Swift version 6.' in receipt['swiftVersion'], 'Translation was not compiled with Swift6')
        checked[kind] = dict(value, receipt=receipt)
    return save(OUT / 'rewind608-tests.json', checked)


def native(kind):
    value, directory = fetch(kind)
    record = json.loads((directory / 'producer608.json').read_bytes())
    require(record['schema'] == 1 and record['build'] == 608 and record['kind'] == kind and
            record['execution'] == execution() and record['inputs'] == input_hashes(kind),
            'Native608 compiled inputs differ')
    require(record['files'] == member_hashes(directory, ('producer608.json',)),
            'Native608 artifact member changed, missing or added')
    require(record['compiledSourcePostimages'] == member_hashes(directory / 'patched-source608'),
            'Actual patched upstream source snapshot differs')
    identity = json.loads((directory / 'identity.json').read_bytes())
    require(identity['host_commit'] == execution()['source'] and identity['architectures'] == ['arm64'],
            'Wrong608 native host/architecture')
    sys.path[:0] = [str(ROOT / 'packages/dolphin_internal_bridge/ci'), str(ROOT / 'build-utils')]
    from verify_ipa import macho
    from delivery_benchmark import payload_fingerprint
    core_name = 'DolphinCore' if kind == 'dolphin' else 'ARMSX2Core'
    core = directory / f'{core_name}.framework/{core_name}'
    raw = core.read_bytes()
    require(sha(raw) == identity['sha256'], 'Native binary differs from its compiled identity')
    image = macho(raw)
    require(image['architecture'] == 'arm64' and image['platform'] == 2 and image['fileType'] == 6 and
            image['id'] == f'@rpath/{core_name}.framework/{core_name}', 'Wrong native608 Mach-O')
    if kind == 'dolphin':
        require(record['upstreamRevision'] == identity['source_revision'] == DOLPHIN_SOURCE and
                identity['achievement_session_policy'] == 1 and identity['achievement_presenter'] == 1 and
                identity['use_retro_achievements'] is True and identity['source_inputs'] == input_hashes(kind),
                'Wrong608 Dolphin policy provenance')
        require(DOLPHIN_EXPORTS <= set(image['definedSymbols']), 'Missing additive Dolphin RA exports')
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
        shaders = directory / 'ARMSX2Core.framework/shaders'
        require(identity['bundled_shader_presets'] == 12 and identity['bundled_shader_files'] == 28 and
                len(list(shaders.rglob('*.slangp'))) == 12 and
                identity['bundled_shader_sha256'] == member_hashes(shaders), 'ARMSX2 shader resources differ')
        destination = ROOT / 'dist/armsx2'
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(directory, destination)
        (destination / 'ARMSX2Core.framework/ARMSX2Core').chmod(0o755)
    fast_path = ROOT / 'build/fast-native/identity.json'
    fast = json.loads(fast_path.read_bytes())
    prefix = 'dolphin' if kind == 'dolphin' else 'armsx2'
    fast.update({prefix + 'CoreSha256': identity['sha256'], prefix + 'CoreHostCommit': execution()['source'],
                 prefix + 'CoreRunId': execution()['run'], prefix + 'SourceRevision': record['upstreamRevision']})
    if kind == 'dolphin':
        fast.update(dolphinAchievementPresentationVersion=1, dolphinAchievementSessionPolicyVersion=1)
    save(fast_path, fast)
    return save(OUT / f'rewind608-{kind}.json', dict(value, identity=identity,
        payloadFingerprint=payload_fingerprint(raw), sourceInputs=record['inputs'],
        compiledSourcePostimages=record['compiledSourcePostimages'], physicalDeviceTested=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['manifest', 'tests', 'install'])
    parser.add_argument('kind', nargs='?', choices=['dolphin', 'armsx2'])
    parser.add_argument('--upstream', type=Path)
    args = parser.parse_args()
    if args.operation == 'manifest':
        require(args.kind and args.upstream, 'Native manifest needs kind and upstream source')
        result = native_manifest(args.kind, args.upstream)
    elif args.operation == 'install':
        require(args.kind, 'Native install needs kind')
        result = native(args.kind)
    else:
        result = tests()
    print(json.dumps(result, indent=2))
