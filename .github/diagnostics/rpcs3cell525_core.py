"""Authenticate 524 evidence and exercise only the native paths changed for 525."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import rpcs3cell524_core as previous

ROOT = Path(__file__).resolve().parents[2]
BASE = 'a7a109b955d2e60de005fd663eb4391f6c93e88d'
PRIOR_RUN = 40110663507
PRIOR_ARTIFACT = 12566613108
PRIOR_SHA = '917a901c81bb07d627e6309f7eff25ca68463ad60626b56721ff750e1a0ef3f7'
FIXTURE = 'test/fixtures/rpcs3_cell525.diff'
FIXTURE_SHA = '63306a30adfd3b375e866fd94f91645519d09bb1c85fcf652a95f02681604ec8'
CHANGED = previous.CHANGED | {'build-utils/rpcs3_core_syntax_gate.py'}
TESTS = (
    ('test/rpcs3_fs_restore525_test.py', 'fs-restore'),
    ('test/rpcs3_ppu_window525_test.py', 'ppu-cache'),
    ('test/rpcs3_gpu_memory525_test.py', 'gpu-memory'),
)
EXTRA_INPUTS = previous.EXTRA_INPUTS + (
    '.github/diagnostics/rpcs3cell525_core.py', '.github/workflows/rpcs3-cell525-core.yml', FIXTURE,
    'test/rpcs3_fs_restore525_test.py', 'test/native/rpcs3_fs_restore525.cpp',
    'test/rpcs3_ppu_window525_test.py', 'test/native/rpcs3_ppu_window525.cpp',
    'test/rpcs3_gpu_memory525_test.py', 'test/native/rpcs3_gpu_memory525.cpp',
    'test/fixtures/rpcs3_ppu_window525.diff',
)
pin_module = previous.pin_module
sha = previous.sha
command = previous.command
old = lambda path: command('git', 'show', BASE + ':' + path)


def inputs():
    return {**pin_module().core_input_hashes(),
            **{path: sha((ROOT / path).read_bytes()) for path in EXTRA_INPUTS}}


def codegen(source, manifest):
    """Match CMake's exact source list, retaining its conservative invalidation."""
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    result = {}
    for kind in ('PPU', 'SPU'):
        pattern = r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)'
        paths = re.search(pattern, cmake, re.S).group(1).split()
        parts = []
        for path in paths:
            digest = (manifest['llvm_aarch64_ghc_patch']['postimage_sha256']
                if path.endswith('/AArch64FrameLowering.cpp')
                else sha((source / 'rpcs3/Emu' / path).read_bytes()))
            parts.append(path + ':' + digest + ';')
        result[kind] = sha(''.join(parts).encode())[:16]
    return result


def source_contract(source=None):
    pin_module().validate_source_contract(source_root=source)
    before = json.loads(old('build-utils/rpcs3/canonical-source.json'))
    after = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = after['cell525']
    changed = {p for p, h in before['files_sha256'].items() if after['files_sha256'].get(p) != h}
    added = set(after['files_sha256']) - set(before['files_sha256'])
    assert changed | added == {'rpcs3/Emu/Cell/lv2/sys_fs.cpp', 'rpcs3/Emu/RSX/VK/vkutils/memory.cpp', 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp', 'rpcs3/Emu/IdManager.h', 'rpcs3/Emu/savestate_utils.cpp', 'rpcs3/Emu/Cell/PPUThread.cpp', 'rpcs3/ios/IOSGPUMemoryProfile.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp'}
    assert changed == set(record['modified_paths'])
    assert added == set(record['new_delta_paths'])
    expected = dict(before)
    expected.update(files_sha256=after['files_sha256'], patch_sha256=after['patch_sha256'], cell525=record)
    assert expected == after
    assert sha((ROOT / FIXTURE).read_bytes()) == FIXTURE_SHA == record['fixture_sha256']
    for path in dict.fromkeys(pin_module().CORE_INPUTS + previous.EXTRA_INPUTS):
        if path not in CHANGED:
            assert (ROOT / path).read_bytes() == old(path), path
    assert not command('git', 'diff', BASE, '--', 'lib', 'native', 'packages', 'assets', 'ios',
                       'pubspec.yaml', 'pubspec.lock').strip(), 'App/host inputs changed'
    if source:
        assert codegen(source, after) == record['codegen']
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for path in changed | added:
                target = work / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source / path).read_bytes())
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / FIXTURE)], cwd=work, check=True)
            assert all(not (work / path).exists() for path in record['new_files'])
            for path, digest in record['before_sha256'].items():
                assert sha((work / path).read_bytes()) == digest, path
    return inputs()


def prepare(source, out):
    current = source_contract(source)
    prior = previous.previous.authenticated(PRIOR_RUN, BASE, PRIOR_ARTIFACT, PRIOR_SHA, 'prior524')
    identity = json.loads((prior / 'identity.json').read_bytes())
    assert identity['host_commit'] == BASE and identity['abi_version'] == 30
    for path, digest in identity['cell524_input_sha256'].items():
        assert sha(old(path)) == digest, path
        if path not in CHANGED:
            assert current[path] == digest, path
    receipt = json.loads((prior / 'cell524-reuse.json').read_bytes())
    assert sha((prior / 'cell524-proof.txt').read_bytes()) == receipt['log_sha256']
    diagnostics = ROOT / 'build/rpcs3-core-diagnostics'
    log = diagnostics / 'cell525-proof.txt'
    outputs = []
    for script, name in TESTS:
        options = ['--require-llvm', '--sanitize'] if name == 'ppu-cache' else []
        result = subprocess.run(['python3', script, str(source), *options, '--report',
            str(diagnostics / (name + '-result.json'))], cwd=ROOT,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
        outputs.append(result.stdout)
        log.write_bytes(b'\n'.join(outputs))
        print(result.stdout.decode(), end='', flush=True)
        result.check_returncode()
    benchmark = subprocess.run(['python3', 'test/rpcs3_ppu_window525_test.py', str(source),
        '--require-llvm', '--benchmark', '--report', str(diagnostics / 'ppu-window-benchmark.json')],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
    outputs.append(benchmark.stdout)
    log.write_bytes(b'\n'.join(outputs))
    print(benchmark.stdout.decode(), end='', flush=True)
    benchmark.check_returncode()
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
    assert sha((ROOT / 'build/rpcs3-core-diagnostics/cell525-proof.txt').read_bytes()) == record['log_sha256']
    print('PASS targeted native restore, object cache and GPU diagnostics; exact unchanged 524 evidence authenticated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--verify-reuse', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/rpcs3-core-diagnostics/cell525-reuse.json')
    args = parser.parse_args()
    if args.verify_reuse:
        verify(args.verify_reuse)
    elif args.source:
        prepare(args.source.resolve(), args.output.resolve())
    else:
        source_contract()
        print('PASS scoped CELL525 source contract; app and emulation fidelity preserved')
