#!/usr/bin/env python3
"""Source-bound 555 host checks: pipeline, trim and readback observations.

The trim test compiles exact production methods with small range/storage/clock
adapters and the actual IOSTextureValidationProfile header. Its pre-555 control is recovered
from the authenticated reverse fixture. No iPhone performance is inferred.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b3955a21b8c23bca27251c49a5c73112cd790d95'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell555.diff'
TEXTURES = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
PROFILE = 'rpcs3/ios/IOSTextureValidationProfile.h'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalized_sha(path):
    return sha(path.read_bytes().replace(b'\r\n', b'\n'))


def method(text, signature):
    """Extract the complete method verbatim (these methods have no raw strings)."""
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError('unclosed method: ' + signature)


def without_ios_blocks(text):
    """Remove complete iOS-only observations; retain every validation statement."""
    out, depth = [], 0
    for line in text.splitlines(keepends=True):
        directive = re.match(r'\s*#\s*(ifdef|ifndef|if|endif|else|elif)\b(.*)', line)
        if directive and directive.group(1) == 'ifdef' and directive.group(2).strip() == 'RPCS3_IOS':
            depth += 1
        elif depth:
            if directive and directive.group(1) in ('if', 'ifdef', 'ifndef'):
                depth += 1
            elif directive and directive.group(1) == 'endif':
                depth -= 1
            elif directive and directive.group(1) in ('else', 'elif') and depth == 1:
                raise AssertionError('trim observation unexpectedly has a non-iOS branch')
        else:
            out.append(line)
    assert depth == 0
    return ''.join(out)


def authenticated_baseline(source, work):
    manifest_path = ROOT / 'build-utils/rpcs3/canonical-source.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = manifest['cell555']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert record['codegen'] == old_manifest['cell551']['codegen']
    paths = set(record['modified_paths']) | set(record['new_files'])
    assert set(record['before_sha256']) == set(record['modified_paths'])
    assert set(record['after_sha256']) == paths
    assert TEXTURES in paths and PROFILE in paths
    assert {'rpcs3/ios/IOSReadbackProfile.h', 'rpcs3/Emu/RSX/Common/texture_cache.h',
            'rpcs3/Emu/RSX/VK/VKPresent.cpp'} <= paths
    before = work / 'before'
    for path in paths:
        current = source / path
        assert normalized_sha(current) == record['after_sha256'][path], path
        assert manifest['files_sha256'][path] == record['after_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(current.read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest, path
        if path in old_manifest['files_sha256']:
            assert old_manifest['files_sha256'][path] == digest, path
        else:
            upstream = subprocess.check_output(
                ['git', 'show', old_manifest['upstream_commit'] + ':' + path], cwd=source)
            assert sha(upstream.replace(b'\r\n', b'\n')) == digest, path
    assert all(not (before / path).exists() for path in record['new_files'])
    return before, {
        'baseline': BASE, 'fixtureSHA256': sha(FIXTURE.read_bytes()),
        'manifestSHA256': sha(manifest_path.read_bytes()),
        'sourceSHA256': record['after_sha256'], 'codegenIdentitiesUnchanged': True,
    }


def trim_harness(source, before):
    current_header = (source / TEXTURES).read_text()
    old_header = (before / TEXTURES).read_text()
    old = method(old_header, 'void trim_sections()')
    current = method(current_header, 'void trim_sections()')
    assert without_ios_blocks(current) == old, 'trim validation policy changed'
    getter = method(current_header, 'const address_range32& get_confirmed_range() const')
    assert getter == method(old_header, 'const address_range32& get_confirmed_range() const')
    assert current.count('utils::get_tsc()') == 2
    performance = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    assert not re.search(r'\bhash_calls\b', (source / PROFILE).read_text()), 'no new per-hash counter'
    assert 'texture_hash_calls=' not in performance, 'no unmeasured per-hash counter'
    for field in ('texture_trim_calls', 'texture_trim_sections',
                  'texture_trim_bytes', 'texture_trim_ticks'):
        assert f'{field}=%llu' in performance, field
        counter = field.removeprefix('texture_')
        assert f'rpcs3::ios::texture_validation::{counter}.exchange(0)' in performance, field
    for marker in ('texture_hash_counter_hz=%llu', 'texture_hash_scope=hybrid_ge4096',
                   'texture_trim_scope=frame_end_all_sizes'):
        assert marker in performance, marker
    template = (ROOT / 'test/native/rpcs3_cell555.inc').read_text()
    for marker, value in (('@CONFIRMED_RANGE@', getter), ('@BEFORE_TRIM@', old), ('@AFTER_TRIM@', current)):
        assert template.count(marker) == 1
        template = template.replace(marker, value)
    return '#define RPCS3_IOS 1\n' + template, {
        'oldTrimSHA256': sha(old.encode()), 'currentTrimSHA256': sha(current.encode()),
        'confirmedRangeGetterSHA256': sha(getter.encode()),
        'productionProfileSHA256': normalized_sha(source / PROFILE),
        'validationPolicyByteIdenticalWithoutObservations': True,
    }


def run_trim(source, before, work):
    code, identity = trim_harness(source, before)
    cpp = work / 'trim.cpp'
    cpp.write_text(code)
    compiler = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]
    results = {}
    for mode, sanitizer in (('addressUndefined', 'address,undefined'), ('thread', 'thread')):
        binary = work / ('trim-' + mode)
        subprocess.run(compiler + ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            '-fno-exceptions', '-pthread', '-fno-omit-frame-pointer', '-fsanitize=' + sanitizer,
            '-I' + str(source), str(cpp), '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=60,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1',
                     TSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            print(run.stdout, run.stderr, file=sys.stderr)
            run.check_returncode()
        results[mode] = json.loads(run.stdout)
        assert results[mode]['passed'] is True
    return dict(identity, harnessSHA256=sha(code.encode()), scenarios=results)


def unchanged_hash_contract(source):
    """The unsuccessful ARM64 candidates must not enter the production Core."""
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    sources = {}
    for path in ('rpcs3/ios/IOSTextureHash.cpp', 'rpcs3/ios/IOSTextureHash.h', 'Utilities/xxhash3.h'):
        expected = old_manifest['files_sha256'].get(path)
        identity = 'canonical baseline ' + BASE
        if expected is None:
            upstream = subprocess.check_output(
                ['git', 'show', old_manifest['upstream_commit'] + ':' + path], cwd=source)
            expected = sha(upstream.replace(b'\r\n', b'\n'))
            identity = 'upstream ' + old_manifest['upstream_commit']
        observed = normalized_sha(source / path)
        assert observed == expected, ('texture hashing must remain unchanged', path, observed, expected)
        sources[path] = dict(sha256=observed, baselineIdentity=identity, unchanged=True)
    return sources


def child_test(script, source, report, extra=()):
    subprocess.run([sys.executable, str(ROOT / 'test' / script), str(source),
                    '--report', str(report), *extra], check=True, timeout=900)
    return json.loads(report.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell555-') as td:
        work = Path(td)
        before, contract = authenticated_baseline(source, work)
        unchanged_hash = unchanged_hash_contract(source)
        trim = run_trim(source, before, work)
        shaders = {}
        for mode, sanitizer in (('addressUndefined', 'address,undefined'), ('thread', 'thread')):
            shaders[mode] = child_test('rpcs3_shader555_test.py', source, work / ('shader-' + mode + '.json'),
                                      ['--sanitizers', sanitizer])
        readback = child_test('rpcs3_readback555_test.py', source, work / 'readback.json')
        assert readback['passed'] is True
    inputs = ['test/rpcs3_cell555_test.py', 'test/native/rpcs3_cell555.inc',
              'test/rpcs3_shader555_test.py', 'test/native/rpcs3_shader555.inc',
              'test/native/rpcs3_fingerprint553.inc',
              'test/rpcs3_readback555_test.py', 'test/native/rpcs3_readback555.inc']
    report = dict(passed=True, result='passed', build=555, hostSystem=platform.system(),
                  hostMachine=platform.machine(), sourceContract=contract, trim=trim,
                  pipelineDiagnostics=shaders, unchangedTextureHashSources=unchanged_hash,
                  readbackDiagnostics=readback,
                  inputs={path: sha((ROOT / path).read_bytes()) for path in inputs},
                  physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host observation correctness, concurrency and unchanged texture-hash sources; '
                        'no iPhone frame times, Metal rendering, thermal or memory-pressure validation.')
    output = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end='')


if __name__ == '__main__':
    main()
