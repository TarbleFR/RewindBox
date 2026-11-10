"""Authenticate the BO2 source delta after the verified device593 follow-up.

The three reviewed files are independent of the thirteen previous corrections.
No historical native suite, build, download or cache invalidation runs here.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KEY = 'runtime_bo2_followup_20261029'
BASELINE = '7d1ca65c8cb12d5d27934cd40cd0cf361518d9ad'
BASELINE_PATCH = '1ee71b4e78b145fa9d8a902d26c201516debef01c036df5f3e61a2a9d8ffa774'
FIXTURE = 'test/fixtures/rpcs3_bo2_20261029.diff'
PATHS = {
    'rpcs3/ios/RPCS3IOSPerformance.cpp',
    'rpcs3/Emu/RSX/Program/ProgramStateCache.cpp',
    'rpcs3/Emu/RSX/Program/ProgramStateCache.h',
}


def normalized_bytes_sha(data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def normalized_sha(path):
    return normalized_bytes_sha(path.read_bytes())


def committed_bytes(relative):
    return subprocess.check_output(['git', 'show', BASELINE + ':' + relative], cwd=ROOT)


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
    assert len(record['modified_paths']) == len(PATHS) and set(record['modified_paths']) == PATHS
    assert set(record['before_sha256']) == set(record['after_sha256']) == PATHS
    assert record['new_files'] == [] and record['new_delta_paths'] == []
    assert PATHS.isdisjoint(parent['runtime_device593_followup_20261029']['modified_paths'])
    assert record['codegen'] == parent['runtime_device593_followup_20261029']['codegen']
    for path in PATHS:
        assert record['before_sha256'][path] == parent['files_sha256'][path], path
        assert record['before_sha256'][path] != record['after_sha256'][path], path
    expected_files = dict(parent['files_sha256'], **record['after_sha256'])
    assert manifest['files_sha256'] == expected_files
    expected = dict(parent, files_sha256=expected_files, patch_sha256=manifest['patch_sha256'])
    expected[KEY] = record
    assert manifest == expected, 'Unrelated canonical metadata changed'
    assert hashlib.sha256((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest() == manifest['patch_sha256']
    assert record['fixture'] == FIXTURE
    fixture = ROOT / FIXTURE
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == record['fixture_sha256']
    stats = subprocess.check_output(['git', 'apply', '--numstat', '-z', str(fixture)], cwd=ROOT)
    paths = [row.split(b'\t', 2)[2].decode() for row in stats.split(b'\0') if row]
    assert len(paths) == len(PATHS) and set(paths) == PATHS
    for path, digest in expected_files.items():
        assert normalized_sha(source / path) == digest, path
    return manifest, record, parent


def reconstruct(source, destination, authenticated, extra_paths=()):
    """Reverse exactly this delta; untouched files retain the current bytes."""
    source, destination = Path(source), Path(destination)
    _, record, parent = authenticated
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
