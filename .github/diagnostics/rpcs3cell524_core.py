"""Authenticate unchanged 523 inputs and test only cancelled HLE admission."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import rpcs3cell523_core as previous

ROOT = Path(__file__).resolve().parents[2]
BASE = 'e8437623a1ba37874adfacd8521c596e94d055c3'
PRIOR_RUN = 40103133192
PRIOR_ARTIFACT = 12563609498
PRIOR_SHA = '4a6efff5e6e39ffcd20a9897742763cefa8de5ba266c0be16274244d6655c1d3'
FIXTURE = 'test/fixtures/rpcs3_hle_abort524.diff'
FIXTURE_SHA = '38d121c544dc22dd783852341944841855a9b2768c0bc5be73b31c158b01a403'
NATIVE = 'rpcs3/Emu/savestate_utils.cpp'
CHANGED = {'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
           'build-utils/build_rpcs3_embedded_core.sh', 'test/neo_swap_core_pin_test.py'}
EXTRA_INPUTS = previous.EXTRA_INPUTS + (
    '.github/diagnostics/rpcs3cell524_core.py', '.github/workflows/rpcs3-cell524-core.yml',
    'test/rpcs3_savestate_wake524_test.py', 'test/native/rpcs3_savestate_wake524.cpp', FIXTURE)
pin_module = previous.pin_module
sha = previous.sha
command = previous.command


def old(path):
    return command('git', 'show', BASE + ':' + path)


def inputs():
    return {**pin_module().core_input_hashes(),
            **{p: sha((ROOT / p).read_bytes()) for p in EXTRA_INPUTS}}


def source_contract(source=None):
    pin_module().validate_source_contract(source_root=source)
    before = json.loads(old('build-utils/rpcs3/canonical-source.json'))
    after = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert set(before['files_sha256']) == set(after['files_sha256'])
    assert {p for p, h in before['files_sha256'].items() if after['files_sha256'][p] != h} == {NATIVE}
    expected = dict(before)
    expected.update(files_sha256=after['files_sha256'], patch_sha256=after['patch_sha256'], cell524=after['cell524'])
    assert expected == after
    assert sha((ROOT / FIXTURE).read_bytes()) == FIXTURE_SHA
    for path in dict.fromkeys(pin_module().CORE_INPUTS + previous.EXTRA_INPUTS):
        if path not in CHANGED:
            assert (ROOT / path).read_bytes() == old(path), path
    if source:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / NATIVE
            path.parent.mkdir(parents=True)
            path.write_bytes((source / NATIVE).read_bytes())
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / FIXTURE)], cwd=d, check=True)
            assert sha(path.read_bytes()) == before['files_sha256'][NATIVE]
    return inputs()


def prepare(source, out):
    current = source_contract(source)
    prior = previous.authenticated(PRIOR_RUN, BASE, PRIOR_ARTIFACT, PRIOR_SHA, 'prior523')
    identity = json.loads((prior / 'identity.json').read_bytes())
    assert identity['host_commit'] == BASE and identity['abi_version'] == 30
    for path, digest in identity['cell523_input_sha256'].items():
        assert sha(old(path)) == digest, path
        if path not in CHANGED:
            assert current[path] == digest, path
    receipt = json.loads((prior / 'cell523-reuse.json').read_bytes())
    assert sha((prior / 'cell523-proof.txt').read_bytes()) == receipt['log_sha256']
    diagnostics = ROOT / 'build/rpcs3-core-diagnostics'
    log = diagnostics / 'cell524-proof.txt'
    result = subprocess.run(['python3', 'test/rpcs3_savestate_wake524_test.py', str(source),
                             '--report', str(diagnostics / 'wake-result.json')], cwd=ROOT,
                            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    log.write_bytes(result.stdout)
    print(result.stdout.decode(), end='', flush=True)
    result.check_returncode()
    record = dict(schema=1, source=command('git', 'rev-parse', 'HEAD').decode().strip(),
        input_sha256=current, prior_source=BASE, prior_run=PRIOR_RUN, prior_artifact=PRIOR_ARTIFACT,
        prior_archive_sha256=PRIOR_SHA, fixture_sha256=FIXTURE_SHA,
        log_sha256=sha(log.read_bytes()), physical_device_tested=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')


def verify(path):
    record = json.loads(path.read_bytes())
    assert record['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert record['input_sha256'] == source_contract()
    assert record['prior_archive_sha256'] == PRIOR_SHA and record['fixture_sha256'] == FIXTURE_SHA
    assert sha((ROOT / 'build/rpcs3-core-diagnostics/cell524-proof.txt').read_bytes()) == record['log_sha256']
    print('PASS actual HLE abort wake; unchanged 523 proofs authenticated; no device performance claim')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path)
    p.add_argument('--verify-reuse', type=Path)
    p.add_argument('--output', type=Path, default=ROOT / 'build/rpcs3-core-diagnostics/cell524-reuse.json')
    args = p.parse_args()
    if args.verify_reuse:
        verify(args.verify_reuse)
    elif args.source:
        prepare(args.source.resolve(), args.output.resolve())
    else:
        source_contract()
        print('PASS iOS-only HLE abort notification; all other native and app inputs preserved')
