"""Authenticate the global runtime follow-up to the verified device594 fixes.

The fixture contains only the new native edits. Reverse it before the earlier
device594 fixture. Store.cpp belongs to the host repository and is bound by its
own exact before/after hashes. Reconstruction runs neither tests nor CMake.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KEY = 'runtime_global_20261029'
BASELINE = '3e4fcfa121e01fd08934486b833dde6a69a2d318'
BASELINE_PATCH = 'f357467b66f1c1dcec0aac94e9e6da73443e2c160a446993feb5274286bafd2e'
FIXTURE = 'test/fixtures/rpcs3_global_20261029.diff'
PATHS = {
    'rpcs3/Emu/Cell/SPUThread.cpp',
    'rpcs3/Emu/CPU/JITCacheCompatibility.cmake',
    'rpcs3/Emu/RSX/VK/vkutils/commands.cpp',
    'rpcs3/Emu/RSX/VK/vkutils/commands.h',
    'rpcs3/Emu/RSX/Common/texture_cache.cpp',
    'rpcs3/ios/IOSTexturePrehash.h',
}
HOST_PATHS = {'native/neoswap-storage/Store.cpp'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def normalized_bytes_sha(raw):
    return sha(raw.replace(b'\r\n', b'\n'))


def normalized_sha(path):
    return normalized_bytes_sha(path.read_bytes())


def committed_bytes(path):
    return subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT)


def authenticate(source, manifest=None):
    source = Path(source)
    if manifest is None:
        manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest[KEY]
    parent = json.loads(committed_bytes('build-utils/rpcs3/canonical-source.json'))
    assert record['baseline_commit'] == BASELINE
    assert record['baseline_patch_sha256'] == parent['patch_sha256'] == BASELINE_PATCH
    assert manifest['upstream_commit'] == parent['upstream_commit']
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip() == manifest['upstream_commit']
    assert record['codegen'] == parent['runtime_device594_followup_20261029']['codegen']
    assert len(record['modified_paths']) == len(PATHS) and set(record['modified_paths']) == PATHS
    assert set(record['before_sha256']) == set(record['after_sha256']) == PATHS
    assert record['new_files'] == [] and record['new_delta_paths'] == []
    for path in PATHS:
        assert record['before_sha256'][path] == parent['files_sha256'][path], path
        assert record['before_sha256'][path] != record['after_sha256'][path], path
    assert set(record['host_before_sha256']) == set(record['host_after_sha256']) == HOST_PATHS
    for path in HOST_PATHS:
        assert record['host_before_sha256'][path] == sha(committed_bytes(path)), path
        assert record['host_after_sha256'][path] == sha((ROOT / path).read_bytes()), path
        assert record['host_before_sha256'][path] != record['host_after_sha256'][path], path
    expected_files = dict(parent['files_sha256'], **record['after_sha256'])
    assert len(expected_files) == 313 and manifest['files_sha256'] == expected_files
    expected = dict(parent, files_sha256=expected_files, patch_sha256=manifest['patch_sha256'])
    expected[KEY] = record
    assert manifest == expected, 'Unrelated canonical metadata changed'
    assert sha((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes()) == manifest['patch_sha256']
    assert record['fixture'] == FIXTURE
    fixture = ROOT / FIXTURE
    assert sha(fixture.read_bytes()) == record['fixture_sha256']
    stats = subprocess.check_output(['git', 'apply', '--numstat', '-z', str(fixture)], cwd=ROOT)
    paths = [row.split(b'\t', 2)[2].decode() for row in stats.split(b'\0') if row]
    assert len(paths) == len(PATHS) and set(paths) == PATHS
    for path, digest in expected_files.items():
        assert normalized_sha(source / path) == digest, path
    return manifest, record, parent


def reconstruct(source, destination, authenticated, extra_paths=()):
    source, destination = Path(source), Path(destination)
    _, record, parent = authenticated
    selected = PATHS | set(extra_paths)
    for path in sorted(selected):
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, target)
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(destination.parent.resolve()))
    subprocess.run(['git', 'apply', '--reverse', '--whitespace=nowarn', str(ROOT / FIXTURE)],
                   cwd=destination, env=env, check=True)
    for path in selected:
        expected = record['before_sha256'].get(path, parent['files_sha256'].get(path))
        if expected is not None:
            assert normalized_sha(destination / path) == expected, path
        else:
            assert (destination / path).read_bytes() == (source / path).read_bytes(), path
    return destination
