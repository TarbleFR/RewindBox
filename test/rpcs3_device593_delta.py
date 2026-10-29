"""Authenticate only the RPCS3 changes after delivered private IPA 593.

No historical native suite is executed. Reconstruction reverses this exact
reviewed fixture in a caller-owned directory and never edits a source index.
The three newly covered NV47 files already exist at the pinned upstream commit.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KEY = 'runtime_device593_followup_20261029'
BASELINE = '571dbc0849caa55c76be797b649c8abf79de5053'
BASELINE_PATCH = 'b07952f3b96deb3c446e9b739f29d8f9af9e749695465bd0bfde848ce0cde6f3'
FIXTURE = 'test/fixtures/rpcs3_device593_20261029.diff'
NEW_DELTA_PATHS = {
    'rpcs3/Emu/RSX/NV47/HW/nv0039.cpp',
    'rpcs3/Emu/RSX/NV47/HW/nv3089.cpp',
    'rpcs3/Emu/RSX/NV47/HW/nv308a.cpp',
}
PATHS = NEW_DELTA_PATHS | {
    'Utilities/JITLLVM.cpp',
    'rpcs3/Emu/CPU/JITCacheCompatibility.cmake',
    'rpcs3/Emu/RSX/Common/texture_cache.h',
    'rpcs3/Emu/RSX/VK/VKDraw.cpp',
    'rpcs3/Emu/RSX/VK/VKGSRender.cpp',
    'rpcs3/Emu/RSX/VK/vkutils/device.cpp',
    'rpcs3/ios/IOSMoltenVKExec.h',
    'rpcs3/ios/IOSMoltenVKExecQueue.h',
    'rpcs3/ios/IOSTextureValidationProfile.h',
    'rpcs3/ios/RPCS3IOSPlatform.mm',
}


def normalized_bytes_sha(data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def normalized_sha(path):
    return normalized_bytes_sha(path.read_bytes())


def committed_bytes(relative):
    return subprocess.check_output(['git', 'show', BASELINE + ':' + relative], cwd=ROOT)


def authenticate(source, manifest=None):
    """Require the delivered parent, the exact delta and every current postimage."""
    source = Path(source)
    if manifest is None:
        manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest[KEY]
    parent = json.loads(committed_bytes('build-utils/rpcs3/canonical-source.json'))
    assert record['baseline_commit'] == BASELINE
    assert record['core_baseline_patch_sha256'] == parent['patch_sha256'] == BASELINE_PATCH
    assert manifest['upstream_commit'] == parent['upstream_commit']
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip() == manifest['upstream_commit']
    assert record['codegen'] == parent['runtime_log_followup_20261029']['codegen']
    assert len(record['modified_paths']) == len(PATHS) and set(record['modified_paths']) == PATHS
    assert set(record['before_sha256']) == set(record['after_sha256']) == PATHS
    assert record.get('new_files', []) == []
    assert len(record['new_delta_paths']) == len(NEW_DELTA_PATHS)
    assert set(record['new_delta_paths']) == NEW_DELTA_PATHS == PATHS - set(parent['files_sha256'])
    assert set(record['upstream_preimage_blobs']) == NEW_DELTA_PATHS
    for relative in PATHS:
        before = parent['files_sha256'].get(relative)
        if relative in NEW_DELTA_PATHS:
            object_name = manifest['upstream_commit'] + ':' + relative
            blob = subprocess.check_output(['git', '-C', str(source), 'rev-parse', object_name]).decode().strip()
            assert blob == record['upstream_preimage_blobs'][relative], relative
            raw = subprocess.check_output(['git', '-C', str(source), 'show', object_name])
            before = normalized_bytes_sha(raw)
        assert record['before_sha256'][relative] == before, relative
        assert before != record['after_sha256'][relative], relative
    expected_files = dict(parent['files_sha256'], **record['after_sha256'])
    assert manifest['files_sha256'] == expected_files
    expected_manifest = dict(parent, files_sha256=expected_files, patch_sha256=manifest['patch_sha256'])
    expected_manifest[KEY] = record
    assert manifest == expected_manifest, 'Unrelated canonical metadata changed'
    patch = ROOT / 'build-utils/rpcs3/embedded-core.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == manifest['patch_sha256']
    assert record['fixture'] == FIXTURE
    fixture = ROOT / FIXTURE
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == record['fixture_sha256']
    stats = subprocess.check_output(['git', 'apply', '--numstat', '-z', str(fixture)], cwd=ROOT)
    fixture_paths = [row.split(b'\t', 2)[2].decode() for row in stats.split(b'\0') if row]
    assert len(fixture_paths) == len(PATHS) and set(fixture_paths) == PATHS
    for relative, digest in expected_files.items():
        assert normalized_sha(source / relative) == digest, relative
    return manifest, record, parent


def reconstruct(source, destination, authenticated, extra_paths=()):
    """Reverse the complete fixture and authenticate all thirteen preimages."""
    source, destination = Path(source), Path(destination)
    manifest, record, parent = authenticated
    selected = PATHS | set(extra_paths)
    for relative in sorted(selected):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(destination.parent.resolve()))
    subprocess.run(['git', 'apply', '--reverse', '--whitespace=nowarn', str(ROOT / FIXTURE)],
                   cwd=destination, env=env, check=True)
    for relative in selected:
        expected = record['before_sha256'].get(relative, parent['files_sha256'].get(relative))
        if expected is None:
            expected = normalized_sha(source / relative)
        assert normalized_sha(destination / relative) == expected, relative
    return destination
