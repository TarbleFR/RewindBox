"""Reverse only the reviewed refinement before using any historical fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '140f35c1fe9eff6b951ae7af7fd3807b590ef2f7'
KEY = 'runtime_refinement_20261029'
FIXTURE = 'test/fixtures/rpcs3_runtime_refinement_20261029.diff'
PATHS = {'rpcs3/Emu/Cell/SPUThread.cpp', 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake',
         'rpcs3/Emu/RSX/VK/vkutils/commands.cpp', 'rpcs3/ios/IOSTexturePrehash.h'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def original(path):
    return subprocess.check_output(['git','show',BASELINE+':'+path],cwd=ROOT)


def reconstruct(source, destination, extras=()):
    source, destination = Path(source), Path(destination)
    manifest = json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_bytes())
    parent = json.loads(original('build-utils/rpcs3/canonical-source.json'))
    record = manifest[KEY]
    assert record['baseline_commit'] == BASELINE
    assert record['modified_paths'] == sorted(PATHS) and record['new_files'] == []
    assert record['before_sha256'] == {p:parent['files_sha256'][p] for p in sorted(PATHS)}
    expected = dict(parent['files_sha256'],**record['after_sha256'])
    assert set(record['after_sha256']) == PATHS and manifest['files_sha256'] == expected
    unchanged = dict(manifest)
    unchanged.pop(KEY)
    unchanged['files_sha256'] = parent['files_sha256']
    unchanged['patch_sha256'] = parent['patch_sha256']
    assert unchanged == parent, 'Unrelated canonical metadata changed'
    assert sha((ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()) == manifest['patch_sha256']
    assert record['fixture'] == FIXTURE and sha((ROOT/FIXTURE).read_bytes()) == record['fixture_sha256']
    for path in sorted(set(expected)|set(extras)):
        raw = (source/path).read_bytes()
        if path in expected:
            assert sha(raw.replace(b'\r\n',b'\n')) == expected[path],path
        target = destination/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    subprocess.run(['git','apply','--reverse','--whitespace=nowarn',str(ROOT/FIXTURE)],cwd=destination,check=True)
    for path,digest in parent['files_sha256'].items():
        assert sha((destination/path).read_bytes().replace(b'\r\n',b'\n')) == digest,path
    return manifest,record,parent
