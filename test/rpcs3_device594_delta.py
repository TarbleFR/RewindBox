"""Authenticate the five native changes after the delivered iPhone build594.

Reverse this fixture before earlier fixtures. Reconstruction never executes a
compiler, historical native suite, CMake, Core build or release operation.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KEY = 'runtime_device594_followup_20261029'
BASELINE = 'c609b0d05a583d2d39f636f328830a6256439807'
BASELINE_PATCH = 'd7e8921e513dcb7caaf90ef6f903b1f9a28eb749b41fa668762304d90f876b2d'
FIXTURE = 'test/fixtures/rpcs3_device594_20261029.diff'
PATHS = {
    'rpcs3/Emu/RSX/RSXFIFO.cpp',
    'rpcs3/Emu/RSX/RSXThread.cpp',
    'rpcs3/Emu/RSX/Common/texture_cache_utils.h',
    'rpcs3/Emu/RSX/VK/VKGSRender.cpp',
    'rpcs3/Emu/RSX/VK/VKTextureCache.cpp',
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
    assert record['codegen'] == parent['runtime_bo2_exact_20261029']['codegen']
    assert len(record['modified_paths']) == len(PATHS) and set(record['modified_paths']) == PATHS
    assert set(record['before_sha256']) == set(record['after_sha256']) == PATHS
    assert record['new_files'] == [] and record['new_delta_paths'] == []
    for path in PATHS:
        assert record['before_sha256'][path] == parent['files_sha256'][path], path
        assert record['before_sha256'][path] != record['after_sha256'][path], path
    expected_files = dict(parent['files_sha256'], **record['after_sha256'])
    assert len(expected_files) == 313 and manifest['files_sha256'] == expected_files
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
        if expected is not None:
            assert normalized_sha(destination / relative) == expected, relative
        else:
            assert (destination / relative).read_bytes() == (source / relative).read_bytes(), relative
    return destination
