#!/usr/bin/env python3
"""Offline, independent authentication of the exact MeloNX Core84 artifact.

This reads Git objects, supplied GitHub metadata and archive bytes. It never
executes a gate, builds a library, loads native code, creates an IPA or polls CI.
Only the existing Mach-O parser functions and check_image are reused, through
an AST selection that excludes all IPA behavior and all engine82 binary pins.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import sys
import tarfile
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
SOURCE = '5045889ff9f1a872d238435293c50cacd7c127b5'
RUN = 40895446303
JOB = 123523168026
ATTEMPT = 1
REPOSITORY = 'TarbleFR/RewindBox'
REPOSITORY_ID = 1329032710
WORKFLOW = '.github/workflows/melonx-core.yml'
PROOF = 'docs/evidence/melonx-hogwarts-followup-20261029/'
PARSER = 'packages/dolphin_internal_bridge/ci/verify_ipa.py'
DIAGNOSTIC = '.github/diagnostics/rewind594_engine.py'
RUNTIMES = ('ios-arm64', 'iossimulator-arm64')
GATES = (
    'tracking-snapshot-checks.json', 'multirange-slice-checks.json',
    'texture-group-callbacks-checks.json', 'texture-region-cursor-checks.json',
    'auto-ownership-checks.json', 'converted-cache-checks.json',
    'kernel-wait-lifetime-checks.json', 'ipc-request-lifetime-checks.json',
    'kernel-timer-allocations-checks.json', 'allocator-blocks-checks.json',
    'indirect-cache-key-checks.json', 'texture-handle-dependencies-checks.json',
    'fragmented-upload-slice-checks.json',
)
SMOKE_INPUTS = (
    'packages/melonx_internal_bridge/ios/Classes/MeloNXSessionHost.swift',
    'packages/melonx_internal_bridge/ios/Classes/MeloNXRuntimeAPI.swift',
    'test/melonx_runtime_smoke.py',
)
FINAL_INPUTS = (
    WORKFLOW, 'build-utils/melonx/build_core.sh', 'build-utils/melonx/build_libhac.py',
    'build-utils/melonx/reuse_core_baseline.py', 'build-utils/melonx/core-baseline.json',
    'build-utils/melonx/verify_core_candidate.py',
)
STATIC_GATE_FIELDS = (
    'postimages', 'compiledSources', 'compiledSourceInputs', 'compiledInputs',
    'extraction', 'callerInputs', 'preparedBaselineInputs',
    'controlCacheSha256', 'extractedAddDependantSha256', 'extractedMethodSha256',
    'wrapperMethodSha256',
)
REVIEWED_FIXTURE_UPDATES = {
    'test/melonx_texture_region_cursor_test.py':
        ('7a780d0b6b8bbce874849580b22151ff87b997fb88fad676320d976f362251f8',
         '5272fa1419dc07d091dfbc2f1831cb45f95181c6fad2a149fe18da4309560a56'),
    'test/melonx_kernel_wait_lifetime_test.py':
        ('d0b16713ab92b342faf6bab1ddaec72f698c7db0cbc913297a09c9859a108746',
         '7536a5fd5d9aef83104d2ca36037611bbac514c1264d9d5cfb63b7488be1eb2f'),
    'test/melonx_ipc_request_lifetime_test.py':
        ('5a85b28e6bdbba12e55360d98eeabc9f985ccbb2d2ce1c07b3ff02448750d1a2',
         '7c2ad35017f98a0d41a6a27bb62368c3d77ed7e7c8c4fd1578798dfe8408ce00'),
    'test/melonx_kernel_timer_allocations_test.py':
        ('a1003a77372e4ecd54e99a8cdceb87b301152f750ad9883e068c1fe8211d5b61',
         '778e91a49cb377e33486da92e82bb7a92571d3ac571f932b20aea1766d56b2ce'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git_blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def document(data):
    return json.loads(data, object_pairs_hook=unique_object)


def relative(path):
    require(isinstance(path, str) and path and not path.startswith('/') and
            '\\' not in path and '\0' not in path and
            all(p not in ('', '.', '..') for p in path.rstrip('/').split('/')),
            'Unsafe relative path: ' + repr(path))
    return path


class GitSource:
    def __init__(self, repo, supplied=None):
        self.repo = repo
        self.cache = {}
        self.blobs = {}
        self.supplied = supplied or {}

    def command(self, *args):
        # Explicitly disable lazy network access in this partial checkout.
        env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
        return subprocess.check_output(
            ['git', '-c', 'remote.origin.promisor=false', '-c',
             'remote.origin.url=/nonexistent/core84-offline', *args],
            cwd=self.repo, env=env, timeout=30, stderr=subprocess.PIPE)

    def blob_id(self, path):
        relative(path)
        if path not in self.blobs:
            entry = self.command('ls-tree', SOURCE, '--', path).decode().strip()
            require(entry.endswith('\t' + path), 'Missing pinned Git entry: ' + path)
            head = entry.split('\t', 1)[0].split()
            require(head[1] == 'blob' and head[0] in ('100644', '100755'),
                    'Unexpected source entry: ' + path)
            self.blobs[path] = head[2]
        return self.blobs[path]

    def read(self, path):
        if path not in self.cache:
            oid = self.blob_id(path)
            data = (self.supplied[path].read_bytes() if path in self.supplied else
                    self.command('cat-file', 'blob', oid))
            require(git_blob_sha(data) == oid, 'Corrupt Git source blob: ' + path)
            self.cache[path] = data
        return self.cache[path]

    def json(self, path):
        return document(self.read(path))

    def hashes(self, paths):
        return {p: sha(self.read(p)) for p in paths}

    def paths(self, prefix):
        return self.command('ls-tree', '-r', '--name-only', SOURCE, '--', prefix).decode().splitlines()


class Archive:
    """Read and hash every member, validating CRCs without extracting files."""
    def __init__(self, source, label):
        self.label = label
        self.zip = zipfile.ZipFile(source)
        entries = self.zip.infolist()
        require(len(entries) <= 50000, label + ': too many archive members')
        seen, total = set(), 0
        self.hashes = {}
        for entry in entries:
            name = relative(entry.filename)
            require(name not in seen, label + ': duplicate member: ' + name)
            seen.add(name)
            mode = entry.external_attr >> 16
            require(not stat.S_ISLNK(mode) and not entry.flag_bits & 1,
                    label + ': linked or encrypted member: ' + name)
            if entry.is_dir():
                continue
            require(entry.file_size <= 512 * 1024 * 1024, label + ': oversized member: ' + name)
            total += entry.file_size
            require(total <= 2 * 1024 * 1024 * 1024, label + ': excessive expanded size')
            with self.zip.open(entry) as stream:
                self.hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()

    def read(self, path):
        relative(path)
        require(path in self.hashes, self.label + ': missing file: ' + path)
        return self.zip.read(path)

    def json(self, path):
        return document(self.read(path))

    def sha(self, path):
        require(path in self.hashes, self.label + ': missing digest: ' + path)
        return self.hashes[path]

    def nested(self, path):
        return Archive(io.BytesIO(self.read(path)), self.label + '/' + path)


def tar_inventory(data, label):
    hashes, metadata, seen = {}, {}, set()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        members = archive.getmembers()
        require(len(members) <= 20000, label + ': excessive source inventory')
        total = 0
        for member in members:
            name = relative(member.name.rstrip('/'))
            require(name not in seen and (member.isfile() or member.isdir()),
                    label + ': duplicate or non-regular source entry: ' + name)
            seen.add(name)
            require('.git' not in PurePosixPath(name).parts, label + ': fabricated Git state')
            if member.isdir():
                continue
            total += member.size
            require(member.size <= 32 * 1024 * 1024 and total <= 512 * 1024 * 1024,
                    label + ': excessive source size')
            with archive.extractfile(member) as stream:
                hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
            metadata[name] = {'sha256': hashes[name], 'mode': member.mode, 'bytes': member.size}
        return hashes, metadata, dict(archive.pax_headers)


def extract_functions(data, names, namespace, label):
    tree = ast.parse(data, filename=label)
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    require({n.name for n in selected} == set(names), 'Missing parser functions: ' + label)
    # No module imports, assignments, workflow logic or __main__ branch execute.
    exec(compile(ast.Module(body=selected, type_ignores=[]), label, 'exec'), namespace)
    return {n.name: sha(ast.get_source_segment(data.decode(), n).encode()) for n in selected}


def machinery(git):
    parser = (HERE / 'verify_ipa.py').read_bytes()
    require(git_blob_sha(parser) == git.blob_id(PARSER), 'Mach-O parser differs from pinned Git blob')
    tree = ast.parse(parser)
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('ARM64', 'LOAD_DYLIB'):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    ns = {'struct': struct, **constants}
    parser_methods = extract_functions(parser, ('demand', 'macho'), ns, PARSER)
    exports = []
    for line in git.read('build-utils/melonx/build_core.sh').decode().splitlines():
        if re.match(r'^required (?:\+)?= \[', line):
            values = ast.literal_eval(line.split('=', 1)[1].strip())
            exports.extend(values)
    require(len(exports) == len(set(exports)) == 47, 'Pinned build does not require 47 unique exports')
    ns['image_info'] = ns['macho']
    ns['SYMBOLS'] = ['_' + name for name in exports]
    image_methods = extract_functions(git.read(DIAGNOSTIC), ('check_image',), ns, DIAGNOSTIC)
    provenance = {'parserGitBlob': git.blob_id(PARSER), 'parserSha256': sha(parser),
                  'parserMethods': parser_methods, 'checkImageMethods': image_methods,
                  'engine82DiagnosticPinsUsedForCandidate': False}
    return ns['check_image'], exports, provenance


def source_contract(git):
    pin = git.json('build-utils/melonx/source.json')
    baseline = git.json('build-utils/melonx/core-baseline.json')
    inputs = git.json(PROOF + 'embedded-inputs.json')
    integration = git.json(PROOF + 'integration.json')
    require(len(inputs) == 86 and inputs == git.hashes(inputs), '86 pinned preparation inputs do not match Git')
    require(sha(git.read(PROOF + 'embedded-inputs.json')) == baseline['expectedInputsSha256'],
            'Reviewed preparation receipt digest differs from source contract')
    require(integration['result'] == 'passed' and len(integration['sourceDelta']) == 17 and
            integration['preparedArchive']['fileCount'] == 127 and
            integration['preparationInputs'] == inputs, 'Wrong reviewed integration contract')
    expected_gates = {name: git.json(PROOF + name) for name in GATES[:-1]}
    refreshed = set()
    for name, record in expected_gates.items():
        actual_inputs = git.hashes(record['inputs'])
        for path, digest in record['inputs'].items():
            if actual_inputs[path] != digest:
                require(REVIEWED_FIXTURE_UPDATES.get(path) == (digest, actual_inputs[path]),
                        'Unreviewed gate input changed: ' + name + '/' + path)
                refreshed.add(path)
        record['inputs'] = actual_inputs
    require(refreshed == set(REVIEWED_FIXTURE_UPDATES), 'Expected four fixture updates are missing')
    # The current cursor gate adds the final Slice to both its compilation and
    # input inventory. Other extracted cursor/overlap methods remain identical.
    cursor = expected_gates['texture-region-cursor-checks.json']
    slice_adapter = 'build-utils/melonx/adapt_multirange_slice.py'
    cursor['inputs'][slice_adapter] = sha(git.read(slice_adapter))
    slice_path = 'src/Ryujinx.Memory/Range/MultiRange.cs'
    cursor['postimages'][slice_path] = integration['sourceDelta'][slice_path]['after']
    extra_inputs = [
        'build-utils/melonx/adapt_gpu_allocations.py', 'build-utils/melonx/adapt_upload_lifetime.py',
        'build-utils/melonx/adapt_fragmented_uploads.py', 'build-utils/melonx/adapt_session.py',
        'build-utils/melonx/source.json', 'test/melonx_fragmented_uploads_test.py',
        *[p for p in git.paths('test/melonx_fragmented_uploads') if
          PurePosixPath(p).parent == PurePosixPath('test/melonx_fragmented_uploads') and p.endswith('.cs')],
        'build-utils/melonx/adapt_multirange_slice.py', 'test/melonx_fragmented_upload_slice_test.py',
        'test/melonx_fragmented_uploads_slice/CompositionProbe.cs',
    ]
    expected_gates[GATES[-1]] = {'inputs': git.hashes(extra_inputs)}
    return pin, baseline, inputs, integration, expected_gates


def check_metadata(git, archive_path, run, job, artifact, artifact_id):
    require(run['id'] == RUN and run['head_sha'] == SOURCE and run['run_attempt'] == ATTEMPT and
            run['head_branch'] == 'Claude' and run['path'] == WORKFLOW and run['event'] == 'push' and
            run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['repository']['id'] == REPOSITORY_ID and run['repository']['full_name'] == REPOSITORY,
            'Wrong or unsuccessful Core84 run metadata')
    require(job['id'] == JOB and job['run_id'] == RUN and job['head_sha'] == SOURCE and
            job['run_attempt'] == ATTEMPT and job['name'] == 'core' and
            job['status'] == 'completed' and job['conclusion'] == 'success',
            'Wrong or unsuccessful Core84 job metadata')
    names = re.findall(r'^    - name: (.+)$', git.read(WORKFLOW).decode(), re.M)
    require(len(names) == len(set(names)) and len(names) >= 24, 'Unexpected pinned workflow step inventory')
    previous = 0
    for name in names:
        matches = [s for s in job['steps'] if s['name'] == name]
        require(len(matches) == 1, 'Ambiguous or missing successful step: ' + name)
        step = matches[0]
        require(step['status'] == 'completed' and step['conclusion'] == 'success' and
                step['number'] > previous and step['started_at'] and step['completed_at'],
                'Required build/gate step was not freshly successful: ' + name)
        previous = step['number']
    origin = artifact['workflow_run']
    require(artifact['id'] == artifact_id and artifact_id > 0 and
            artifact['name'] == 'MeloNX-engine-' + SOURCE and artifact['expired'] is False and
            origin['id'] == RUN and origin['head_sha'] == SOURCE and origin['head_branch'] == 'Claude' and
            origin['repository_id'] == REPOSITORY_ID, 'Wrong Core84 artifact provenance')
    digest = file_sha(archive_path)
    require(artifact['digest'] == 'sha256:' + digest and artifact['size_in_bytes'] == archive_path.stat().st_size,
            'Actual Core84 ZIP does not match independently supplied API size/SHA256')
    return {'sha256': digest, 'bytes': archive_path.stat().st_size, 'id': artifact_id,
            'requiredSuccessfulSteps': names}


def check_baseline(current, previous, baseline, inputs, integration, pin):
    history = current.json('baseline-engine82/authentication/result.json')
    require(history['result'] == 'authenticated' and history['repository'] == REPOSITORY and
            history['run'] == baseline['run'] and history['job'] == baseline['job'] and
            history['artifact'] == baseline['artifact'] and history['archiveSha256'] == baseline['archiveSha256'] and
            history['engineSource'] == baseline['engineSource'] and history['unchangedPreparationInputs'] == 73 and
            history['oldPreparationInputs'] == 74 and history['candidatePreparationInputs'] == 86 and
            history['expectedCandidateInputs'] == inputs and history['newAdapters'] == baseline['newAdapters'] and
            history['historicalTestsReexecuted'] is False and history['historicalResultsCoverNewBodies'] is False,
            'Baseline history is missing or overclaims current coverage')
    base_run = current.json('baseline-engine82/authentication/run.json')
    base_job = current.json('baseline-engine82/authentication/job.json')
    base_artifact = current.json('baseline-engine82/authentication/artifact.json')
    require(base_run['id'] == baseline['run'] and base_run['head_sha'] == baseline['source'] and
            base_run['run_attempt'] == baseline['runAttempt'] and base_run['head_branch'] == baseline['branch'] and
            base_run['event'] == 'push' and base_run['path'] == baseline['workflow'] and
            base_run['status'] == 'completed' and base_run['conclusion'] == 'success' and
            base_run['repository']['id'] == baseline['repositoryId'], 'Wrong retained baseline validation run')
    require(base_job['id'] == baseline['job'] and base_job['run_id'] == baseline['run'] and
            base_job['run_attempt'] == baseline['runAttempt'] and base_job['head_sha'] == baseline['source'] and
            base_job['name'] == baseline['jobName'] and base_job['status'] == 'completed' and
            base_job['conclusion'] == 'success', 'Wrong retained baseline validation job')
    for name in baseline['requiredSuccessfulSteps']:
        matches = [step for step in base_job['steps'] if step['name'] == name]
        require(len(matches) == 1 and matches[0]['status'] == 'completed' and matches[0]['conclusion'] == 'success',
                'Missing retained baseline validation step: ' + name)
    origin = base_artifact['workflow_run']
    require(base_artifact['id'] == baseline['artifact'] and base_artifact['name'] == baseline['artifactName'] and
            base_artifact['size_in_bytes'] == baseline['archiveBytes'] and
            base_artifact['digest'] == 'sha256:' + baseline['archiveSha256'] and
            origin['id'] == baseline['run'] and origin['head_sha'] == baseline['source'] and
            origin['head_branch'] == baseline['branch'] and origin['repository_id'] == baseline['repositoryId'],
            'Wrong retained baseline artifact identity')
    def retained(name):
        top = '/' not in name and PurePosixPath(name).suffix in ('.json', '.log', '.txt')
        proof = name.startswith(('runtime-validation/', 'runtime-smoke/', 'runtime-smoke-engine82-original-failure/'))
        identity = name.startswith(tuple(r + '/' for r in RUNTIMES)) and PurePosixPath(name).suffix in ('.json', '.txt')
        return top or proof or identity or name == 'embedded-adapted-source.zip'
    expected_history = {p: h for p, h in previous.hashes.items() if retained(p)}
    require(history['historicalReports'] == expected_history, 'Retained baseline report inventory changed')
    for name, digest in expected_history.items():
        require(current.sha('baseline-engine82/' + name) == digest,
                'Retained historical evidence is not identical to authenticated ZIP82: ' + name)
    old = previous.json('embedded-inputs.json')
    recipe = 'build-utils/melonx/prepare_embedded.py'
    require(len(old) == 74 and set(inputs) == set(old) | set(baseline['newAdapters']) and
            len(baseline['newAdapters']) == 12 and old[recipe] == baseline['oldPreparationSha256'] and
            inputs[recipe] == baseline['newPreparationSha256'] and
            all(inputs[p] == h for p, h in old.items() if p != recipe),
            'Engine82 plus twelve-adapter preparation inventory changed')
    old_validation = previous.json('runtime-validation/result.json')
    require(old_validation['result'] == 'passed' and old_validation['engineSource'] == baseline['engineSource'] and
            old_validation['originalRunConclusion'] == 'failure' and old_validation['engineRecompiled'] is False,
            'Historical original failure/separate validation provenance changed')
    require(previous.json('runtime-smoke-engine82-original-failure/actual-runtime.json')['result'] == 'failed' and
            previous.json('runtime-smoke/actual-runtime.json')['result'] == 'passed', 'Historical smoke history missing')
    upstream, upstream_meta, headers = tar_inventory(current.read('upstream-source.tar.gz'), 'new upstream')
    old_upstream, old_upstream_meta, old_headers = tar_inventory(previous.read('upstream-source.tar.gz'), 'old upstream')
    require(upstream_meta == old_upstream_meta and headers == old_headers and headers['comment'] == pin['revision'],
            'Current upstream source archive is not the exact authenticated pinned source')
    old_adapted = previous.nested('embedded-adapted-source.zip')
    adapted = current.nested('embedded-adapted-source.zip')
    expected_adapted = dict(old_adapted.hashes)
    for path, change in integration['sourceDelta'].items():
        require(old_adapted.hashes.get(path, upstream.get(path)) == change['before'],
                'Reviewed baseline source differs: ' + path)
        expected_adapted[path] = change['after']
    require(len(adapted.hashes) == 127 and adapted.hashes == expected_adapted,
            'Prepared 127-source content inventory is not exact baseline plus reviewed postimages')
    final_sources = dict(upstream, **adapted.hashes)
    require(len(set(adapted.hashes) - set(integration['sourceDelta'])) == 110, 'Wrong unchanged adapted-source count')
    return history, old_validation, upstream, adapted, final_sources


def check_libhac_and_dependencies(current, previous, baseline, pin, history, old_validation):
    lock = pin['libHac']
    package = 'libhac-feed/' + lock['package'] + '.' + lock['version'] + '.nupkg'
    operational = [package, 'libhac-identity.json', 'libhac-upstream-source.tar', 'libhac-generated-source.zip']
    require(history['copiedLibHacFiles'] == operational, 'Unexpected copied baseline operational files')
    for path in operational:
        require(current.sha(path) == previous.sha(path), 'Changed reused LibHac bytes: ' + path)
    identity = current.json('libhac-identity.json')
    require(identity['source'] == lock and identity['reconstructed'] is True and
            identity['originalPackageRecovered'] is False and
            current.sha(package) == identity['packageSha256'] == baseline['libHac']['packageSha256'] and
            len(current.read(package)) == identity['packageBytes'] and
            current.sha('libhac-upstream-source.tar') == identity['upstreamSourceSha256'] == baseline['libHac']['sourceSha256'] and
            current.sha('libhac-generated-source.zip') == baseline['libHac']['generatedSha256'], 'LibHac identity mismatch')
    generated = current.nested('libhac-generated-source.zip')
    require(generated.hashes == identity['generatedInputs'], 'LibHac generated source digests differ')
    libhac_files, _, _ = tar_inventory(current.read('libhac-upstream-source.tar'), 'LibHac source')
    reused = current.json('libhac-authenticated-reuse.json')
    prior = previous.json('libhac-reuse.json')
    require(reused['result'] == 'authenticated' and reused['baselineArtifact'] == baseline['artifact'] and
            reused['baselineRun'] == baseline['run'] and reused['archiveSha256'] == baseline['archiveSha256'] and
            reused['source'] == lock and reused['packageSha256'] == current.sha(package) and
            reused['originalLayoutProof'] == prior and reused['testsReexecuted'] is False and
            reused['dependencyRecompiled'] is False and reused['originalPackageRecovered'] is False,
            'LibHac reuse proof mismatch')
    require(prior['run'] == baseline['libHac']['layoutRun'] and prior['job'] == baseline['libHac']['layoutJob'] and
            prior['layoutTestsPassed'] == baseline['libHac']['layoutTestsPassed'] == 5 and
            prior['libHacSource'] == lock['revision'] and prior['packageSha256'] == current.sha(package) and
            prior['runConclusion'] == 'failure' and prior['reused'] is True and prior['testsReexecuted'] is False,
            'Original five-test LibHac proof changed')
    native = current.json('native-dependencies-reused.json')
    require(native['result'] == 'authenticated' and native['baselineArtifact'] == baseline['artifact'] and
            native['archiveSha256'] == baseline['archiveSha256'] and
            native['nativeDependencies'] == old_validation['nativeDependencies'] and
            native['nativeDependenciesRecompiled'] is False, 'Native dependency reuse proof changed')
    names = {'MeloNXMoltenVK', 'MeloNXSDL3', 'MeloNXAvUtil', 'MeloNXAvCodec', 'MeloNXJitSupport'}
    expected_names = {f'{platform}/{name}.framework/{name}' for platform in ('ios', 'iossimulator') for name in names}
    require(set(native['nativeDependencies']['binaries']) == expected_names, 'Ten-framework identity inventory missing')
    return {'package': {'path': package, 'sha256': current.sha(package), 'bytes': identity['packageBytes']},
            'sourceFiles': len(libhac_files), 'generatedFiles': generated.hashes,
            'historicalLayoutTests': 5, 'nativeDependencies': native['nativeDependencies'],
            'nativeFrameworkBytesIncludedInCoreArtifact': False}


def check_gates(git, current, expected_gates, pin, upstream, final_sources, integration):
    index = current.json('core-validation/gates.json')
    require(set(index['receipts']) == set(GATES) and index['newAdapterGates'] == 12 and
            index['additionalCompositionGates'] == 1 and index['historicalGatesReexecuted'] is False and
            index['physicalDeviceTested'] is False, 'Wrong fresh gate inventory/scope')
    exceptions = {(x['receipt'], x['path']): x for x in integration['postimageCompositionExceptions']}
    count, input_count, upstream_count, used = 0, 0, 0, []
    for name in GATES:
        receipt = current.json(name)
        require(current.sha(name) == index['receipts'][name] and receipt['result'] == 'passed' and
                receipt['upstreamRevision'] == pin['revision'] and receipt['physicalDeviceTested'] is False,
                'Failed, foreign or modified gate: ' + name)
        reference = expected_gates[name]
        require(receipt['inputs'] == reference['inputs'] == git.hashes(receipt['inputs']),
                'Gate input inventory does not match pinned Git: ' + name)
        require(bool(receipt['upstreamInputs']), 'Missing upstream gate inputs: ' + name)
        for path, digest in receipt['upstreamInputs'].items():
            require(upstream[path] == digest, 'Gate upstream input differs: ' + name + '/' + path)
        if name != GATES[-1]:
            require(receipt['upstreamInputs'] == reference['upstreamInputs'], 'Upstream gate inventory changed: ' + name)
            for field in STATIC_GATE_FIELDS:
                if field in reference:
                    require(receipt.get(field) == reference[field], 'Changed production/extraction proof: ' + name + '/' + field)
        for path, digest in receipt.get('callerInputs', {}).items():
            require(upstream[path] == digest, 'Native caller source differs: ' + path)
        input_count += len(receipt['inputs'])
        upstream_count += len(receipt['upstreamInputs'])
        images = receipt['postimages'].get('candidate', receipt['postimages'])
        require(bool(images), 'Empty candidate postimage map: ' + name)
        for path, digest in images.items():
            actual = final_sources[path]
            if actual != digest:
                exception = exceptions.get((name, path))
                require(exception and exception['fixturePostimage'] == digest and exception['finalPostimage'] == actual,
                        'Unreviewed fixture/final composition: ' + name + '/' + path)
                used.append(exception)
            count += 1
    slice_report = current.json(GATES[-1])
    expected_slice_upstream = {
        'src/Ryujinx.Common/Memory/MemoryOwner.cs', 'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs',
        'src/Ryujinx.Graphics.Gpu/Image/Texture.cs', 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs',
        'src/Ryujinx.Memory/Range/MemoryRange.cs', 'src/Ryujinx.Memory/Range/MultiRange.cs',
    }
    require(set(slice_report['upstreamInputs']) == expected_slice_upstream,
            'Fragmented-upload/Slice upstream input inventory changed')
    for field in ('finalSliceCompiledWithProductionConsumers', 'baselineRetainsHistoricalSlice',
                  'productionConsumerBodiesUnchanged', 'conversionPayloadBoundaryObserved'):
        require(slice_report[field] is True, 'Fragmented-upload/Slice composition missing: ' + field)
    require(slice_report['historicalUnpooledVariantReplayed'] is False and
            slice_report['extraction']['baseline'] == slice_report['extraction']['candidate'],
            'Unexpected replay or consumer mutation in Slice composition')
    path = 'src/Ryujinx.Memory/Range/MultiRange.cs'
    require(slice_report['compiledMultiRangeSha256'] == {'baseline': upstream[path], 'candidate': final_sources[path]},
            'Wrong historical/final Slice actually compiled')
    cursor = current.json('texture-region-cursor-checks.json')
    require(cursor['finalCursorAndSliceCompiledTogether'] is True and
            cursor['compiledMultiRangeSha256'] == {'control': upstream[path], 'candidate': final_sources[path]},
            'Cursor gate did not compile the final Slice alongside the reviewed cursor')
    before, after = slice_report['reports']
    for field in ('passed', 'checks', 'fragmentedUploads', 'rents', 'returns', 'payloadDigest', 'payloadCalls', 'payloadBytes'):
        require(before[field] == after[field], 'Slice composition changed payload/lifetime: ' + field)
    require(before['payloadCalls'] > 0 and before['payloadBytes'] > 0 and after['allocatedBytes'] < before['allocatedBytes'],
            'Slice composition does not demonstrate observed payload equivalence and lower host allocation')
    require(len(used) == 5, 'Reviewed composition exception inventory changed')
    return {'receipts': index['receipts'], 'inputEntries': input_count,
            'upstreamInputEntries': upstream_count, 'postimages': count, 'compositionExceptions': used,
            'reviewedFixtureUpdates': {p: {'historical': pair[0], 'current': pair[1]}
                                       for p, pair in REVIEWED_FIXTURE_UPDATES.items()},
            'cursorAlsoCompilesFinalSlice': True}


def check_core(git, current, inputs, pin, exports, check_image, integration, gate_details):
    execution = {'source': SOURCE, 'run': RUN, 'attempt': ATTEMPT,
                 'url': f'https://github.com/{REPOSITORY}/actions/runs/{RUN}'}
    reports = {phase: current.json('core-validation/' + phase + '.json')
               for phase in ('preflight', 'gates', 'compiled', 'result')}
    for phase, report in reports.items():
        require(report['result'] == 'passed' and report['execution'] == execution, 'Foreign/failed phase: ' + phase)
    preflight = reports['preflight']
    smoke_inputs = git.hashes(SMOKE_INPUTS)
    require(preflight['system'] == 'Darwin' and preflight['architecture'] == 'arm64' and
            preflight['dotnet'] == '10.0.100' and 'osx-arm64' in preflight['dotnetInfo'] and
            preflight['upstreamRevision'] == pin['revision'] and preflight['preparationInputs'] == inputs and
            preflight['smokeInputs'] == smoke_inputs, 'Wrong Apple/preflight source/SDK evidence')
    require(current.json('embedded-inputs.json') == inputs, 'Built preparation inventory mismatch')
    images, binary_map, identity_map = {}, {}, {}
    for runtime in RUNTIMES:
        path = runtime + '/Ryujinx.Library.dylib'
        data = current.read(path)
        identity_path = runtime + '/identity.json'
        identity = current.json(identity_path)
        image = check_image(data, runtime)
        require(data[:4] == b'\xcf\xfa\xed\xfe', 'Unexpected multi-architecture candidate image: ' + runtime)
        require(identity['host'] == SOURCE and identity['source'] == pin and identity['runtimeIdentifier'] == runtime and
                identity['adaptations'] == inputs and identity['sha256'] == sha(data) and identity['size'] == len(data) and
                identity['libHac'] == current.json('libhac-identity.json') and identity['exports'] == exports and
                identity['embeddedLibraryAbi'] == 2 and identity['embeddedSessionImplemented'] is True and
                identity['embeddedSessionDeviceVerified'] is False and identity['status'] == 'compiled-not-gameplay-tested',
                'Candidate binary identity mismatch: ' + runtime)
        symbols = {line.split()[-1] for line in current.read(runtime + '/exports.txt').decode().splitlines() if line.split()}
        require(set('_' + n for n in exports) <= symbols, 'Saved nm output contradicts actual Mach-O exports')
        platform = 'IOS' if runtime == 'ios-arm64' else 'IOSSIMULATOR'
        require('platform ' + platform + '\n' in current.read(runtime + '/platform.txt').decode(), 'Platform text mismatch')
        images[runtime] = {k: image[k] for k in ('architecture', 'fileType', 'platform', 'minimumOS', 'id', 'dependencies')}
        images[runtime]['requiredExportCount'] = len(exports)
        images[runtime]['definedSymbolCount'] = len(image['definedSymbols'])
        images[runtime]['requiredExports'] = exports
        binary_map[runtime] = {'sha256': sha(data), 'bytes': len(data)}
        identity_map[runtime] = current.sha(identity_path)
    compiled = reports['compiled']
    require(compiled['identities'] == identity_map and compiled['binaries'] == binary_map and
            compiled['adaptationCount'] == 86 and compiled['reviewedChangedSources'] == 17 and
            compiled['verifiedGatePostimages'] == gate_details['postimages'] and
            compiled['compositionExceptions'] == integration['postimageCompositionExceptions'] and
            compiled['embeddedArchiveSha256'] == current.sha('embedded-adapted-source.zip') and
            compiled['physicalDeviceTested'] is False and compiled['gameplayTested'] is False,
            'Compiled proof does not bind actual binaries/source/gate composition')
    final = reports['result']
    require(all(final[k] == v for k, v in compiled.items()), 'Finalization changed compiled proof')
    require(final['inputs'] == git.hashes(FINAL_INPUTS) and
            final['historicalGatesReexecuted'] is False and final['nativeDependenciesRecompiled'] is False and
            final['status'] == 'compiled-and-simulator-validated-not-gameplay-tested' and
            final['gateReceiptSha256'] == current.sha('core-validation/gates.json'), 'Finalized recipe/source binding mismatch')
    return images, binary_map, final, smoke_inputs


def check_smoke(current, final, binary_map, smoke_inputs):
    smoke_path = 'runtime-smoke/actual-runtime.json'
    smoke = current.json(smoke_path)
    require(smoke['result'] == 'passed' and smoke['actualNativeAOT'] is True and
            smoke['coreSha256'] == binary_map['iossimulator-arm64']['sha256'] and smoke['inputs'] == smoke_inputs and
            smoke['homebrewSimulatorSessions'] == smoke['actualCoreDonatedBackingSessions'] == 2 and
            smoke['originalHomebrewGuestSvcConfirmed'] is True and
            smoke['performanceSnapshotStaleAndEndedRefused'] is True and
            smoke['gameplayTested'] is False and smoke['iphoneGuestExecutionTested'] is False and
            smoke['homebrewProducesVideo'] is False and smoke['personalKeysUsed'] is False and
            smoke['donorProcessUsedInSmoke'] is False, 'Current NativeAOT smoke or scope mismatch')
    sessions = smoke['homebrewGuestSvcSessions']
    require(len(sessions) == 2 and [s['session'] for s in sessions] == [1, 2] and
            len({s['generation'] for s in sessions}) == 2 and len({s['svcSequence'] for s in sessions}) == 2 and
            all(s['generation'] > 0 and s['svcSequence'] > s['afterSequence'] for s in sessions) and
            sessions[1]['afterSequence'] >= sessions[0]['svcSequence'], 'Smoke does not prove two fresh separate SVC sessions')
    require(final['runtimeSmokeSha256'] == current.sha(smoke_path) and final['guestSvcSessions'] == sessions and
            final['homebrewSimulatorSessions'] == final['releasedBackingSessions'] == 2,
            'Finalization does not bind two SVC/backing sessions')
    expected_reuse = ('baseline-engine82/authentication/result.json',
                      'libhac-authenticated-reuse.json', 'native-dependencies-reused.json')
    require(final['reusedEvidenceSha256'] == {p: current.sha(p) for p in expected_reuse},
            'Finalization does not bind all authenticated reuse proofs')
    return {'sha256': current.sha(smoke_path), 'guestSvcSessions': sessions,
            'releasedBackingSessions': 2, 'livePerformanceSnapshotSessions': smoke['livePerformanceSnapshotSessions'],
            'runtime': smoke['runtime'], 'physicalDeviceTested': False, 'gameplayTested': False}


def check_notices(current, adapted, pin):
    prefix = 'managed-notices/'
    manifest = current.json(prefix + 'resolved-managed-packages.json')
    require(manifest['packages'] and 'osx-arm64' in manifest['dotnetInfo'] and '10.0.100' in manifest['dotnetInfo'],
            'New build managed package/SDK notice evidence missing')
    checked = 0
    libhac_package = 'libhac-feed/' + pin['libHac']['package'] + '.' + pin['libHac']['version'] + '.nupkg'
    for key, package in manifest['packages'].items():
        require(key == package['id'] + '/' + package['version'] and package['notices'], 'Managed notice inventory mismatch')
        for path, digest in package['notices'].items():
            require(current.sha(prefix + path) == digest, 'Retained original package notice differs: ' + path)
            checked += 1
        if package['id'] == pin['libHac']['package']:
            package_sha512 = base64.b64encode(hashlib.sha512(current.read(libhac_package)).digest()).decode()
            require(package['version'] == pin['libHac']['version'] and package['resolvedSha512'] == package_sha512,
                    'Resolved LibHac package does not match authenticated nupkg')
    require(pin['libHac']['package'] + '/' + pin['libHac']['version'] in manifest['packages'],
            'Resolved LibHac package notice missing')
    require(current.sha(prefix + 'BuildConfiguration/Ryujinx.Library.csproj') ==
            adapted.sha('src/Ryujinx.Library/Ryujinx.Library.csproj'), 'Managed notice project differs from prepared source')
    require(current.json(prefix + 'BuildConfiguration/global.json')['sdk'] ==
            {'version': '10.0.100', 'rollForward': 'disable'}, 'Managed notice SDK selection differs')
    return {'packages': len(manifest['packages']), 'noticeFiles': checked,
            'manifestSha256': current.sha(prefix + 'resolved-managed-packages.json'),
            'licenseCompletenessAttested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=WORKSPACE / 'RewindBox')
    parser.add_argument('--source-file', action='append', default=[], metavar='GIT_PATH=LOCAL_FILE',
                        help='Supply a missing partial-clone blob; its Git object identity is still mandatory')
    parser.add_argument('--baseline-zip', type=Path, default=WORKSPACE / 'melonx-engine82-verified.zip')
    parser.add_argument('--prepare-only', action='store_true', help='Authenticate pinned local source and parser, then stop')
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--run-metadata', type=Path)
    parser.add_argument('--job-metadata', type=Path)
    parser.add_argument('--artifact-metadata', type=Path)
    parser.add_argument('--artifact-id', type=int)
    parser.add_argument('--output', type=Path, default=HERE / 'core84-independent-verification.json')
    args = parser.parse_args()
    require(__debug__, 'Do not run the existing check_image assertions with Python optimization enabled')
    supplied = {}
    for item in args.source_file:
        require('=' in item, 'Expected --source-file GIT_PATH=LOCAL_FILE')
        git_path, local_file = item.split('=', 1)
        relative(git_path)
        require(git_path not in supplied, 'Duplicate supplied source file: ' + git_path)
        supplied[git_path] = Path(local_file)
    git = GitSource(args.repo, supplied)
    pin, baseline, inputs, integration, expected_gates = source_contract(git)
    check_image, exports, provenance = machinery(git)
    require(args.baseline_zip.stat().st_size == baseline['archiveBytes'] and
            file_sha(args.baseline_zip) == baseline['archiveSha256'], 'Baseline ZIP82 authentication failed')
    if args.prepare_only:
        report = {'result': 'prepared-awaiting-core84-artifact', 'source': SOURCE, 'run': RUN, 'job': JOB,
                  'preparationInputs': 86, 'newSourcePostimages': 17, 'preparedArchiveFiles': 127,
                  'freshGatesRequired': 13, 'exportsRequiredPerImage': len(exports), 'machOParser': provenance,
                  'sourceContracts': git.hashes([PROOF + 'integration.json', PROOF + 'embedded-inputs.json', *FINAL_INPUTS]),
                  'baselineZipSha256': baseline['archiveSha256'], 'candidateArtifactVerified': False,
                  'networkRequests': 0, 'testsExecuted': 0, 'compilations': 0, 'ipaCreated': False}
    else:
        require(all((args.zip, args.run_metadata, args.job_metadata, args.artifact_metadata, args.artifact_id)),
                'Provide --zip, --run-metadata, --job-metadata, --artifact-metadata and --artifact-id')
        metadata = [document(p.read_bytes()) for p in (args.run_metadata, args.job_metadata, args.artifact_metadata)]
        artifact = check_metadata(git, args.zip, *metadata, args.artifact_id)
        current, previous = Archive(args.zip, 'Core84'), Archive(args.baseline_zip, 'authenticated engine82')
        history, old_validation, upstream, adapted, final_sources = check_baseline(
            current, previous, baseline, inputs, integration, pin)
        reuse = check_libhac_and_dependencies(current, previous, baseline, pin, history, old_validation)
        gates = check_gates(git, current, expected_gates, pin, upstream, final_sources, integration)
        images, binaries, final, smoke_inputs = check_core(git, current, inputs, pin, exports, check_image, integration, gates)
        require(all(binaries[r]['sha256'] != baseline['binarySha256'][r] for r in RUNTIMES),
                'Historical library copied as new Core84 output')
        smoke = check_smoke(current, final, binaries, smoke_inputs)
        notices = check_notices(current, adapted, pin)
        report = {'result': 'passed', 'scope': 'Offline independent verification of supplied Core84 artifact bytes and saved evidence',
                  'source': SOURCE, 'run': RUN, 'job': JOB, 'attempt': ATTEMPT, 'artifact': artifact,
                  'metadataSha256': {name: file_sha(path) for name, path in zip(('run', 'job', 'artifact'),
                    (args.run_metadata, args.job_metadata, args.artifact_metadata))},
                  'machOParser': provenance, 'images': images, 'binaries': binaries,
                  'preparationInputs': inputs, 'reviewedPostimages': integration['sourceDelta'],
                  'preparedSourceMembers': adapted.hashes, 'preparedUnchangedMembers': 110,
                  'freshGates': gates, 'runtimeSmoke': smoke, 'reusedEvidence': reuse, 'managedNotices': notices,
                  'coreValidationSha256': {phase: current.sha('core-validation/' + phase + '.json')
                    for phase in ('preflight', 'gates', 'compiled', 'result')},
                  'limits': [
                    'Metadata is supplied by the caller from GitHub; this offline verifier does not re-fetch it.',
                    'Successful source-bound CI gates are saved execution evidence, not independent replay or reproducible-build proof.',
                    'Five reviewed fixture/final-source differences remain explicit; unchanged historical results do not cover new bodies.',
                    'The ten external native frameworks are verified through retained engine82 proof and the current CI reauthentication receipt; their binaries are not in this Core artifact.',
                    'LibHac is the authenticated source reconstruction; original unavailable NuGet byte equivalence is not asserted.',
                    'Simulator homebrew proves two SVC/teardown/backing lifetimes; it produces no video and establishes no iPhone or Hogwarts FPS/RSS result.',
                    'Retained managed notices do not attest that all corresponding-source obligations are complete.',
                  ], 'networkRequests': 0, 'testsExecuted': 0, 'compilations': 0, 'ipaCreated': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report['verifierSha256'] = file_sha(Path(__file__))
    report['authenticatedGitInputs'] = {path: sha(data) for path, data in git.cache.items()}
    report['reviewedFixtureUpdates'] = {p: {'historical': pair[0], 'current': pair[1]}
                                       for p, pair in REVIEWED_FIXTURE_UPDATES.items()}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'result': report['result'], 'receipt': str(args.output), 'source': SOURCE,
                      'run': RUN, 'job': JOB, 'sha256': file_sha(args.output)}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Core84 verification FAILED: ' + str(error), file=sys.stderr)
        raise
