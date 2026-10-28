#!/usr/bin/env python3
"""Source-bound 583 host checks: texture pre-validation pacing (CELL583_PREHASH_PACING).

Build 581 iPhone logs. God of War III (BCES00510): the worker served 56 % of
the RSX thread's validations of 64 KiB or more and 48 % of the bytes it hashed
were never used (82.7 GB hashed, 42.9 GB served over nine in-game windows);
the frame rate in comparable scenes rose from 18-20 fps (575) to 26-30 fps.
Black Ops II (BLES01717): its SPU threads use 3.4-4.1 cores while its RSX
thread uses 0.1-0.5; the worker served 20-28 % of its validations for up to
0.13 core and skipped 1,756-4,602 main-memory ranges per window. The 583
worker leaves out the ranges the RSX thread has already passed in this frame,
the RSX thread wakes it halfway through the ranges it prepared instead of the
4 ms timeout, and Automatic is God of War III only.

The 581 model (test/native/rpcs3_prehash583.inc, the 579 validation next to
the worker under test, real address reservation, vm range lock protocol, an
unmapper on main memory) runs twice: with the 581 worker and with the 583
worker. Both must accept no stale texture; the two 581 mutations must still
be caught with the 583 worker. Off iOS every touched file is the 581 one. No
iPhone FPS, frame time or memory result is inferred.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from rpcs3_cell559_test import braced, compilers, normalized_sha, sha, without_ios_blocks

BASE = '03956454afc710cb55901c74108b88fbb03dec5d'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell583.diff'
FIXTURE581 = ROOT / 'test/fixtures/rpcs3_cell581.diff'
HARNESS = ROOT / 'test/native/rpcs3_prehash583.inc'
CACHE = 'rpcs3/Emu/RSX/Common/texture_cache.cpp'
CACHE_H = 'rpcs3/Emu/RSX/Common/texture_cache.h'
UTILS = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
VK = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
PREHASH = 'rpcs3/ios/IOSTexturePrehash.h'
VALIDATION = 'rpcs3/ios/IOSTextureValidationProfile.h'
CONFIG = 'rpcs3/Emu/system_config.h'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
MODIFIED = {CACHE, PREHASH, POLICY, SETTINGS, PERFORMANCE}
NEW_FILES = []
# The 581 delta: its reverse gives the 579 preimages the model compares against.
MODIFIED581 = {CACHE, CACHE_H, UTILS, VK, VALIDATION, CONFIG, POLICY_H, POLICY, SETTINGS, PERFORMANCE}
NEW581 = [PREHASH]
INPUTS = ['test/rpcs3_cell583_test.py', 'test/native/rpcs3_prehash583.inc', 'test/fixtures/rpcs3_cell581.diff']
HEADS = {'FAST_HASH': 'u64 buffered_section::fast_hash_internal() const',
         'IS_LOCKED': 'bool buffered_section::is_locked(bool actual_page_flags) const',
         'PROTECT': 'void buffered_section::protect(utils::protection new_prot, bool force)',
         'SYNC': 'bool buffered_section::sync() const', 'DISCARD': 'void buffered_section::discard()'}
# Guest memory is shared without synchronization in the emulator (PPU, SPU and RSX
# threads read and write it with plain accesses): TSan checks the worker's own
# synchronization (results table, sequences, epochs, range lock) and leaves out the
# model guest's writes and the hash's reads of guest bytes.
TSAN_SUPPRESSIONS = 'race:fill\nrace:XXH3_\nrace:XXH_\nrace:XXH64\nrace:range_hash\n'


def full_base():
    return subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip()


def authenticated_baseline(source, work):
    """The 581 preimages (reverse 583 fixture) and the 579 ones (reverse 581 fixture), each authenticated."""
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell583']
    assert record['baseline'] == full_base()
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', full_base() + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell583' not in old_manifest and 'cell581' in old_manifest
    assert record['codegen'] == old_manifest['cell581']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == NEW_FILES and set(record['modified_paths']) == MODIFIED
    before581 = work / 'before581'
    for path in MODIFIED581 | set(NEW581):
        if path in MODIFIED:
            assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before581 / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before581, check=True)
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before581 / path) == digest == old_manifest['files_sha256'][path], path
    record581 = old_manifest['cell581']
    assert sha(FIXTURE581.read_bytes()) == record581['fixture_sha256']
    for path in MODIFIED581 | set(NEW581):
        assert normalized_sha(before581 / path) == record581['after_sha256'][path], path
    before579 = work / 'before579'
    for path in MODIFIED581 | set(NEW581):
        target = before579 / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((before581 / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE581)], cwd=before579, check=True)
    assert not (before579 / PREHASH).exists()
    for path, digest in record581['before_sha256'].items():
        assert normalized_sha(before579 / path) == digest, path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256'])
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before581, before579, {'baseline': full_base(), 'fixtureSHA256': record['fixture_sha256'],
                                  'sourceSHA256': record['after_sha256'], 'newFiles': NEW_FILES,
                                  'otherCoreSourcesUnchanged': len(set(old_manifest['files_sha256']) - MODIFIED)}


def codegen_identity(source):
    """No PPU or SPU codegen source changes: the 581 object caches stay valid."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell583']['codegen'] == manifest['cell581']['codegen']
    return {'identities': manifest['cell583']['codegen'], 'unchangedFrom581': True, 'coldCompileRequiredByThisChange': False}


def off_ios_unchanged(source, before):
    """Off iOS every shared file is the 581 one (rpcs3/ios is compiled for iOS only)."""
    shared = sorted(p for p in MODIFIED if not p.startswith('rpcs3/ios/'))
    for path in shared:
        assert without_ios_blocks((source / path).read_text()) == without_ios_blocks((before / path).read_text()), path
    return {'sharedFiles': shared, 'iosOnlyFiles': sorted(set(MODIFIED) - set(shared))}


def reset_line(text):
    return re.search(r'void reset_validation\(\) const \{[^}]*\}', text).group(0)


def harness(worker, before579, mutation=None):
    """The model with the 579 validation and the worker tree's 581/583 blocks (optionally one deliberate mutation)."""
    now, old = (worker / CACHE).read_text(), (before579 / CACHE).read_text()
    code = HARNESS.read_text()
    for name, head in HEADS.items():
        code = code.replace('@BEFORE_' + name + '@', braced(old, head))
        after = braced(now, head)
        if mutation == 'no_bypass' and name == 'SYNC':
            assert after.count('!prehash_bypass && ') == 1
            after = after.replace('!prehash_bypass && ', '')
        code = code.replace('@AFTER_' + name + '@', after)
    code = code.replace('@BEFORE_RESET_VALIDATION@', reset_line((before579 / UTILS).read_text()))
    code = code.replace('@AFTER_RESET_VALIDATION@', reset_line((worker / UTILS).read_text()))
    secret = braced(now, 'namespace\n{\n\tstruct ios_xxh3_seeded_secret')
    assert secret == braced(old, 'namespace\n{\n\tstruct ios_xxh3_seeded_secret'), 'seeded secret changed'
    code = code.replace('@SECRET_AND_PREHASH@', secret + '\n\n' + braced(now, 'namespace rpcs3::ios::texture_prehash\n{'))
    header = (worker / PREHASH).read_text()
    if mutation == 'no_epoch_check':
        assert header.count(' || stored_epoch != epoch') == 1
        header = header.replace(' || stored_epoch != epoch', ' || (static_cast<void>(stored_epoch), static_cast<void>(epoch), false)')
    code = code.replace('@PREHASH_HEADER_INCLUDE@', header.replace('#pragma once', ''))
    assert not re.findall(r'@[A-Z_]+@', code), re.findall(r'@[A-Z_]+@', code)
    counters = '#define CELL583_COUNTERS 1\n' if 'worker_passed' in header else ''
    return '#define RPCS3_IOS 1\n' + counters + code


def run_model(work, source, code, sanitizer, min_hit_rate, label='583', expect_failure=False):
    name = 'prehash583-' + label + ('-' + sanitizer.replace(',', '-') if sanitizer else '') + ('-mutant' if expect_failure else '')
    cpp = work / (name + '.cpp')
    cpp.write_text(code)
    binary = work / name
    flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-pthread',
             '-fno-omit-frame-pointer', '-I' + str(source / 'rpcs3'), '-I' + str(source)]
    if sanitizer:
        flags.append('-fsanitize=' + sanitizer)
    subprocess.run(compilers() + flags + [str(cpp), '-o', str(binary)], check=True)
    suppressions = work / 'tsan583.supp'
    suppressions.write_text(TSAN_SUPPRESSIONS)
    run = subprocess.run([str(binary), str(min_hit_rate)], text=True, capture_output=True, timeout=900,
        env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
                 TSAN_OPTIONS='halt_on_error=1:suppressions=' + str(suppressions)))
    if expect_failure:
        assert run.returncode != 0 and 'stale_accepted == 0' in run.stderr, (run.returncode, run.stderr[-2000:])
        return {'rejected': True}
    if run.returncode:
        print(run.stdout, run.stderr, file=sys.stderr)
        run.check_returncode()
    report = json.loads(run.stdout)
    assert report['passed'] is True and report['disabledIdenticalTo579'] is True
    for case in ('steady', 'tightLoop', 'scopedRsxWrites'):
        assert report[case]['staleAccepted'] == 0, case
    assert report['steady']['hitRate'] >= min_hit_rate
    assert report['unmapRace']['workerSkips'] > 0 and report['unmapRace']['workerHashes'] > 0
    return dict(report, harnessSHA256=sha(code.encode()))


def prehash(work, source, before581, before579):
    """Both workers serve the RSX validations without accepting a stale texture; the 583 one is
    run under the sanitizers and with the mutations, the 581 one beside it for comparison."""
    code583, code581 = harness(source, before579), harness(before581, before579)
    results = {
        'worker581': run_model(work, source, code581, '', 0.0, '581'),
        'plain': run_model(work, source, code583, '', 0.5),
        'asanUbsan': run_model(work, source, code583, 'address,undefined', 0.25),
        'tsan': run_model(work, source, code583, 'thread', 0.0),
    }
    assert results['plain']['steady']['workerRefills'] > 0 and results['worker581']['steady']['workerRefills'] == 0
    results['mutations'] = {m: run_model(work, source, harness(source, before579, m), '', 0.0, '583', expect_failure=True)
                            for m in ('no_epoch_check', 'no_bypass')}
    return results


def policy_contract(source, before):
    """Automatic is God of War III; the pacing hooks sit on the worker's hash path and the RSX record path."""
    policy = (source / POLICY).read_text()
    assert ('resolved.texture_prehash = resolved.texture_validation_epoch &&\n\t\tresolve_mode(g_cfg.ios_experimental.texture_prehash, is_god_of_war_iii_title(title_id));'
            in policy)
    assert 'rpcs3::ios::texture_prehash::enabled.store(resolved.texture_prehash, std::memory_order_relaxed);' in policy
    settings = [l for l in (source / SETTINGS).read_text().splitlines(keepends=True) if 'SETTING("experimental.texture_prehash"' in l]
    assert len(settings) == 1 and 'Needs Texture Validation Per FIFO Batch. Automatic enables it for God of War III; Disabled hashes on the RSX thread as before.' in settings[0]
    old_settings = [l for l in (before / SETTINGS).read_text().splitlines(keepends=True) if 'SETTING("experimental.texture_prehash"' in l]
    assert (source / SETTINGS).read_text().replace(settings[0], old_settings[0]) == (before / SETTINGS).read_text()
    performance = (source / PERFORMANCE).read_text()
    assert 'COREPROF OPT583 session=%llu window=%llu worker_passed=%llu worker_refills=%llu ' in performance
    assert performance.index('COREPROF OPT581 ') < performance.index('COREPROF OPT583 ')
    assert 'inline std::atomic<std::uint64_t> worker_passed{0}, worker_refills{0};' in (source / PREHASH).read_text()
    cache = (source / CACHE).read_text()
    worker = braced(cache, 'void worker_main()')
    assert worker.index('g_refill_at = position + (batch.size() + 1) / 2;') < worker.index('lock.unlock();')
    assert worker.index('if (index < g_position.load(std::memory_order_relaxed))') < worker.index('hash_guest_range(range_lock')
    assert worker.index('if (validation::current_epoch() != epoch)') < worker.index('if (index < g_position.load(')
    record = braced(cache, 'void record(u32 start, u32 length) noexcept')
    assert record.index('g_position.store(g_current.size(), std::memory_order_relaxed);') < record.index('if (g_current.size() >= g_refill_at)')
    for name in ('void end_frame() noexcept', 'void stop() noexcept'):
        body = braced(cache, name)
        assert 'g_position.store(0, std::memory_order_relaxed);' in body and 'g_refill_at = umax;' in body, name
    return {'automatic': 'God of War III', 'enabled': 'any title with Texture Validation Per FIFO Batch',
            'disabled': 'hashes on the RSX thread as in 579', 'profileLines': ['COREPROF OPT581', 'COREPROF OPT583']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell583-') as temporary:
        work = Path(temporary)
        before581, before579, contract = authenticated_baseline(source, work)
        result = {
            'passed': False, 'build': 583, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
            'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
            'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
            'offIOS': off_ios_unchanged(source, before581),
        }
        result['prehashPacing'] = prehash(work, source, before581, before579)
        result['policy'] = policy_contract(source, before581)
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
        result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                      scope='The 583 production code (and the 581 worker beside it) compiled in a host model; no iPhone FPS, frame time or memory result.')
    text = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
