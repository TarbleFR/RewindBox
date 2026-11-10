"""Authenticate and reverse only the runtime follow-up based on Core592.

This helper never edits the caller's source tree. The reconstructed files are
owned by a caller-provided temporary directory; no repository index is used.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KEY = 'runtime_log_followup_20261029'
BASELINE = '075d84a49e3540cdae5352908fd81bc411b78942'
BASELINE_PATCH = '873a3ec24376cd3e6c4eb34143ea12de977550b7763c8648f0d648fecb5dbe5d'
FIXTURE = 'test/fixtures/rpcs3_runtime_log_followup_20261029.diff'
PATHS = {
    'rpcs3/Emu/Memory/vm.cpp',
    'rpcs3/Emu/RSX/Common/texture_cache.cpp',
    'rpcs3/Emu/RSX/Program/ProgramStateCache.h',
    'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp',
    'rpcs3/Emu/RSX/VK/VKProgramPipeline.h',
    'rpcs3/Emu/RSX/VK/vkutils/commands.cpp',
    'rpcs3/Emu/RSX/VK/vkutils/commands.h',
    'rpcs3/Emu/RSX/VK/vkutils/dynamic_state_cache.hpp',
    'rpcs3/ios/IOSTexturePrehash.h',
}


def normalized_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def committed_bytes(relative):
    return subprocess.check_output(['git', 'show', BASELINE + ':' + relative], cwd=ROOT)


def authenticate(source, manifest=None):
    """Require the exact pinned parent and all current canonical postimages."""
    if manifest is None:
        manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest[KEY]
    assert record['baseline_commit'] == BASELINE
    assert record['core_baseline_patch_sha256'] == BASELINE_PATCH
    parent = json.loads(committed_bytes('build-utils/rpcs3/canonical-source.json'))
    assert parent['patch_sha256'] == BASELINE_PATCH
    assert manifest['upstream_commit'] == parent['upstream_commit']
    for name in ['runtime_20261029', 'runtime_followup_20261029']:
        assert manifest[name] == parent[name], name
    assert record['codegen'] == parent['runtime_20261029']['codegen']
    assert len(record['modified_paths']) == len(PATHS)
    assert set(record['modified_paths']) == PATHS
    assert set(record['before_sha256']) == set(record['after_sha256']) == PATHS
    assert record.get('new_files', []) == []
    assert record['before_sha256'] == {p: parent['files_sha256'][p] for p in PATHS}
    assert all(record['before_sha256'][p] != record['after_sha256'][p] for p in PATHS)
    expected = dict(parent['files_sha256'])
    expected.update(record['after_sha256'])
    assert manifest['files_sha256'] == expected
    patch = ROOT / 'build-utils/rpcs3/embedded-core.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == manifest['patch_sha256']
    assert record['fixture'] == FIXTURE
    fixture = ROOT / FIXTURE
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == record['fixture_sha256']
    stats = subprocess.check_output(['git', 'apply', '--numstat', '-z', str(fixture)], cwd=ROOT)
    fixture_paths = [row.split(b'\t', 2)[2].decode() for row in stats.split(b'\0') if row]
    assert len(fixture_paths) == len(PATHS) and set(fixture_paths) == PATHS
    for relative, expected_hash in expected.items():
        assert normalized_sha(source / relative) == expected_hash, relative
    return manifest, record, parent


def reconstruct(source, destination, authenticated, extra_paths=()):
    """Reverse the complete authenticated fixture, then verify every preimage."""
    manifest, record, parent = authenticated
    selected = PATHS | set(extra_paths)
    for relative in sorted(selected):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    # A caller can place its temporary directory inside another repository.
    # Stop discovery at its parent so git apply cannot operate on that index/tree.
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(destination.parent.resolve()))
    subprocess.run(['git', 'apply', '--reverse', '--whitespace=nowarn', str(ROOT / FIXTURE)],
                   cwd=destination, env=env, check=True)
    for relative in selected:
        expected = parent['files_sha256'].get(relative, normalized_sha(source / relative))
        assert normalized_sha(destination / relative) == expected, relative
    return destination
