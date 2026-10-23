"""Reuse immutable 508 proofs only for the reviewed two-file GoW3 Core delta."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'cfe92344e1b3dd26d2cb17bb8b8ad68260c5cc7f'
BASE_RUN = 39877981229
BASE_JOB = 120168213588
PROOF_ARTIFACT = 12469262558
PROOF_SHA = 'ec7a723c2de08987101e9013e39e8dd422b77c5789a46f0f72ed2972334d0f4a'
OLD_PATCH = '179156b3c987132d5a98c967b4c277d9934da7ce3a49e69d95127c996c56604a'
NEW_PATCH = 'f31bf5f7d66c44dd3a02683a12a3b3ad6ac450d83bd66603e8c2010f7579198d'
CHANGED_CORE = {
    'rpcs3/Emu/System.cpp': '56e94c20aa57497a5ec06ec5c015711244f0b0a12c12f49ae695957d227e48b5',
    'rpcs3/Emu/RSX/VK/vkutils/VRAMBudgetPolicy.h': 'df913dcb4e2d386bfcfffc36543e748acea7bb7e31373e817187f79a716e0045',
}
SELF = '.github/diagnostics/rpcs3gow3_core.py'
NEW_TEST = 'test/rpcs3_gow3_boot_regression_test.py'

def command(*args):
    return subprocess.check_output(args, cwd=ROOT)

def old(path):
    return command('git', 'show', BASE + ':' + path)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def pin_module():
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test as core
    return core

def wrap_native_tests(text):
    begin = text.index('HOST_CXX="$(xcrun --sdk macosx --find clang++)"')
    end = text.index('\nlog "Configure RPCS3Core for iPhoneOS arm64', begin)
    block = text[begin:end]
    return (text[:begin] + 'if [[ -n "${RPCS3_REUSED_NATIVE_PROOF:-}" ]]; then\n'
        '  python3 "$PWD/.github/diagnostics/rpcs3gow3_core.py" --verify-reuse "$RPCS3_REUSED_NATIVE_PROOF"\n'
        'else\n' + block + '\nfi\n' + text[end:])

def verify_source():
    core = pin_module()
    core.validate_source_contract()
    manifest_path = 'build-utils/rpcs3/canonical-source.json'
    before = json.loads(old(manifest_path))
    after = json.loads((ROOT / manifest_path).read_bytes())
    assert before['patch_sha256'] == OLD_PATCH and after['patch_sha256'] == NEW_PATCH
    assert after['device_runtime_tested'] is False
    assert {k for k in before['files_sha256'] if before['files_sha256'][k] != after['files_sha256'].get(k)} == set(CHANGED_CORE)
    assert before['files_sha256'].keys() == after['files_sha256'].keys()
    for path, digest in CHANGED_CORE.items():
        assert after['files_sha256'][path] == digest
    def blocks(data):
        matches = list(re.finditer(rb'^diff --git a/(.*?) b/\1\n', data, re.M))
        return {m[1].decode(): data[m.start():matches[i+1].start() if i+1 < len(matches) else len(data)] for i, m in enumerate(matches)}
    a = blocks(old('build-utils/rpcs3/embedded-core.patch'))
    b = blocks((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes())
    assert a.keys() == b.keys()
    assert {k for k in a if a[k] != b[k]} == set(CHANGED_CORE)
    changed_inputs = {SELF, NEW_TEST, manifest_path, 'build-utils/rpcs3/embedded-core.patch',
        'build-utils/build_rpcs3_embedded_core.sh', '.github/workflows/rpcs3-memory-audit.yml',
        'test/rpcs3_memory_audit_test.py', 'test/native/rpcs3_memory_audit_test.cpp', 'test/neo_swap_core_pin_test.py'}
    for path in core.CORE_INPUTS:
        if path not in changed_inputs:
            assert (ROOT / path).read_bytes() == old(path), 'Changed prior proof input: ' + path
    path = 'test/native/rpcs3_memory_audit_test.cpp'
    expected = old(path).decode().replace('assert(vk::get_preferred_vram_block_size(8 * GiB) == 0);',
        'assert(vk::get_preferred_vram_block_size(8 * GiB) == 64 * MiB);\n    assert(vk::get_preferred_vram_block_size(8 * GiB + 1) == 0);')
    assert (ROOT / path).read_text() == expected
    path = 'test/rpcs3_memory_audit_test.py'
    expected = old(path).decode().replace('import argparse,json,os,shlex,shutil,subprocess,tempfile',
        'import argparse,json,os,shlex,shutil,subprocess,sys,tempfile')
    expected = expected.replace('def run(cmd):subprocess.run(list(map(str,cmd)),check=True,timeout=180)\n',
        'def run(cmd):subprocess.run(list(map(str,cmd)),check=True,timeout=180)\nrun([sys.executable,ROOT/\'test/rpcs3_gow3_boot_regression_test.py\',core])\n')
    assert (ROOT / path).read_text() == expected
    path = 'test/neo_swap_core_pin_test.py'
    expected = old(path).decode().replace(OLD_PATCH, NEW_PATCH).replace('CORE_INPUTS = (\n',
        "CORE_INPUTS = (\n    '.github/diagnostics/rpcs3gow3_core.py',\n    'test/rpcs3_gow3_boot_regression_test.py',\n")
    assert (ROOT / path).read_text() == expected
    path = 'build-utils/build_rpcs3_embedded_core.sh'
    assert (ROOT / path).read_text() == wrap_native_tests(old(path).decode())
    return core.core_input_hashes()

def api(path):
    return json.loads(command('gh', 'api', 'repos/TarbleFR/RewindBox/' + path))

def prepare(source, output):
    inputs = verify_source()
    run = api('actions/runs/' + str(BASE_RUN))
    assert run['head_sha'] == BASE and run['status'] == 'completed' and run['conclusion'] == 'success'
    jobs = api('actions/runs/' + str(BASE_RUN) + '/jobs?per_page=100')['jobs']
    assert any(j['id'] == BASE_JOB and j['conclusion'] == 'success' for j in jobs)
    version = command(str(Path(command('brew', '--prefix', 'llvm@22').decode().strip()) / 'bin/llvm-config'), '--version').decode().strip()
    assert version == '22.1.8', version
    archive = Path(os.environ['RUNNER_TEMP']) / 'gow3-prior-proofs.zip'
    with archive.open('wb') as stream:
        subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{PROOF_ARTIFACT}/zip'], stdout=stream, check=True)
    assert sha(archive.read_bytes()) == PROOF_SHA
    diagnostics = ROOT / 'build/rpcs3-core-diagnostics'
    diagnostics.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            relative = PurePosixPath(item.filename)
            assert not relative.is_absolute() and '..' not in relative.parts
            if not item.is_dir():
                dest = diagnostics / 'prior508' / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(bundle.read(item))
    for name in ['memory-audit-proof.txt', 'spu-object-cache-proof.txt', 'llvm-pipeline-proof.txt',
                 'build499-proof.txt', 'build487-core-proof.txt', 'build487-host-proof.txt']:
        assert 'PASS' in (diagnostics / 'prior508' / name).read_text(), name
    for path, digest in CHANGED_CORE.items():
        assert sha((source / path).read_bytes()) == digest, path
    # Execute the changed behavior on the actual newly materialized sources.
    test = subprocess.run([sys.executable, str(ROOT / NEW_TEST), str(source)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    log = diagnostics / 'gow3-boot-proof.txt'
    log.write_text(test.stdout)
    print(test.stdout, end='')
    test.check_returncode()
    record = {'schema': 1, 'source': command('git', 'rev-parse', 'HEAD').decode().strip(),
        'core_input_sha256': inputs, 'prior_source': BASE, 'prior_run': BASE_RUN,
        'prior_job': BASE_JOB, 'prior_artifact': PROOF_ARTIFACT, 'prior_archive_sha256': PROOF_SHA,
        'llvm': version, 'changed_core': CHANGED_CORE, 'new_targeted_test': NEW_TEST,
        'new_targeted_log': str(log.relative_to(ROOT)), 'new_targeted_log_sha256': sha(log.read_bytes()),
        'scope': 'Unchanged native tests reused; new ISO/CPU/VMA host checks passed; current Core must still compile and pass binary gates',
        'physical_device_tested': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS authenticated unchanged 508 native proofs and newly executed GoW3 boot/CPU/VMA regressions')

def verify_receipt(path):
    record = json.loads(path.read_text())
    assert record['schema'] == 1 and record['source'] == command('git', 'rev-parse', 'HEAD').decode().strip()
    assert record['core_input_sha256'] == verify_source()
    assert record['prior_source'] == BASE and record['prior_run'] == BASE_RUN
    assert record['prior_archive_sha256'] == PROOF_SHA and record['llvm'] == '22.1.8'
    assert record['changed_core'] == CHANGED_CORE
    log = ROOT / record['new_targeted_log']
    assert record['new_targeted_log_sha256'] == sha(log.read_bytes())
    assert 'PASS God of War III boot regressions' in log.read_text()
    print('PASS source-bound reuse receipt; unchanged native campaigns retained')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/rpcs3-core-diagnostics/gow3-reuse.json')
    parser.add_argument('--verify-reuse', type=Path)
    args = parser.parse_args()
    if args.verify_reuse:
        verify_receipt(args.verify_reuse)
    elif args.source:
        prepare(args.source.resolve(), args.output.resolve())
    else:
        verify_source()
        print('PASS reviewed GoW3 delta and unchanged prior proof inputs')
