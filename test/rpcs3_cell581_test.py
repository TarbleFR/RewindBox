#!/usr/bin/env python3
"""Source-bound 581 host checks: texture pre-validation by a worker thread (God of War III).

Build 575 logs. God of War III (BCES00510): on iOS the texture cache confirms
CPU textures by content hash, and under Texture Validation Per FIFO Batch
(CELL559_TEXTURE_EPOCH) a texture is hashed again on its first use after each
synchronization point. The RSX thread, whose FIFO is 72-95 % busy, spends
461-815 ms of every 5 s window there (2.8-10.4 ms per frame, 7-10 GB);
Dragon Ball Z and Black Ops II hash nothing. A frame validates nearly the same
ranges in nearly the same order as the frame before it. When an epoch starts,
a worker thread hashes the ranges the previous frame validated next, with the
texture cache's own hash, and publishes each result tagged with the epoch it
read before the bytes; the RSX thread uses a result only in that epoch, never
for a section an RSX write revalidated inside it, and hashes everything else
as before (CELL581_TEXTURE_PREHASH). RSX local memory is read directly, main
memory only under a vm range lock that unmaps wait for.

The production code is copied from the materialized Core into a host model:
the 579 validation next to the 581 one, a real address space reservation, the
vm range lock slots, exclusive bits and page flags, and an unmapper running
the vm unmap protocol on main memory while the worker reads it. Two mutations
(no epoch check in the lookup, no bypass after an RSX write) must make the
model accept a stale texture. Off iOS every touched file is the 579 one. No
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

BASE = '1f82f9d988cbecb9bf07bdcb3ed3983404668270'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell581.diff'
HARNESS = ROOT / 'test/native/rpcs3_prehash581.inc'
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
MODIFIED = {CACHE, CACHE_H, UTILS, VK, VALIDATION, CONFIG, POLICY_H, POLICY, SETTINGS, PERFORMANCE}
NEW_FILES = [PREHASH]
INPUTS = ['test/rpcs3_cell581_test.py', 'test/native/rpcs3_prehash581.inc']
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
    """The 579 preimages, from the materialized Core and the authenticated reverse fixture."""
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell581']
    assert record['baseline'] == full_base()
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', full_base() + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell581' not in old_manifest and 'cell579' in old_manifest
    assert record['codegen'] == old_manifest['cell579']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == NEW_FILES and set(record['modified_paths']) == MODIFIED
    before = work / 'before'
    for path in MODIFIED | set(NEW_FILES):
        assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    assert not (before / PREHASH).exists()
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | set(NEW_FILES)
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': full_base(), 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'], 'newFiles': NEW_FILES,
                    'otherCoreSourcesUnchanged': len(set(old_manifest['files_sha256']) - MODIFIED)}


def codegen_identity(source):
    """No PPU or SPU codegen source changes: the 579 object caches stay valid."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell581']['codegen'] == manifest['cell579']['codegen']
    return {'identities': manifest['cell581']['codegen'], 'unchangedFrom579': True, 'coldCompileRequiredByThisChange': False}


def off_ios_unchanged(source, before):
    """Off iOS every shared file is the 579 one (rpcs3/ios is compiled for iOS only)."""
    shared = sorted(p for p in MODIFIED if not p.startswith('rpcs3/ios/'))
    for path in shared:
        assert without_ios_blocks((source / path).read_text()) == without_ios_blocks((before / path).read_text()), path
    users = [p for p in shared if 'IOSTexturePrehash.h' in (source / p).read_text()]
    for path in users:
        assert 'IOSTexturePrehash.h' not in without_ios_blocks((source / path).read_text()), path
    return {'sharedFiles': shared, 'iosOnlyFiles': sorted(set(MODIFIED) - set(shared)) + NEW_FILES,
            'headerIncludedOnlyUnderRPCS3IOS': sorted(users)}


def reset_line(text):
    return re.search(r'void reset_validation\(\) const \{[^}]*\}', text).group(0)


def harness(source, before, mutation=None):
    """The model with the production blocks substituted (optionally one deliberate mutation)."""
    now, old = (source / CACHE).read_text(), (before / CACHE).read_text()
    code = HARNESS.read_text()
    for name, head in HEADS.items():
        code = code.replace('@BEFORE_' + name + '@', braced(old, head))
        after = braced(now, head)
        if mutation == 'no_bypass' and name == 'SYNC':
            assert after.count('!prehash_bypass && ') == 1
            after = after.replace('!prehash_bypass && ', '')
        code = code.replace('@AFTER_' + name + '@', after)
    code = code.replace('@BEFORE_RESET_VALIDATION@', reset_line((before / UTILS).read_text()))
    code = code.replace('@AFTER_RESET_VALIDATION@', reset_line((source / UTILS).read_text()))
    secret = braced(now, 'namespace\n{\n\tstruct ios_xxh3_seeded_secret')
    assert secret == braced(old, 'namespace\n{\n\tstruct ios_xxh3_seeded_secret'), 'seeded secret changed'
    code = code.replace('@SECRET_AND_PREHASH@', secret + '\n\n' + braced(now, 'namespace rpcs3::ios::texture_prehash\n{'))
    header = (source / PREHASH).read_text()
    if mutation == 'no_epoch_check':
        assert header.count(' || stored_epoch != epoch') == 1
        header = header.replace(' || stored_epoch != epoch', ' || (static_cast<void>(stored_epoch), static_cast<void>(epoch), false)')
    code = code.replace('@PREHASH_HEADER_INCLUDE@', header.replace('#pragma once', ''))
    assert not re.findall(r'@[A-Z_]+@', code), re.findall(r'@[A-Z_]+@', code)
    return '#define RPCS3_IOS 1\n' + code


def run_model(work, source, code, sanitizer, min_hit_rate, expect_failure=False):
    name = 'prehash581' + ('-' + sanitizer.replace(',', '-') if sanitizer else '') + ('-mutant' if expect_failure else '')
    cpp = work / (name + '.cpp')
    cpp.write_text(code)
    binary = work / name
    flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-pthread',
             '-fno-omit-frame-pointer', '-I' + str(source / 'rpcs3'), '-I' + str(source)]
    if sanitizer:
        flags.append('-fsanitize=' + sanitizer)
    subprocess.run(compilers() + flags + [str(cpp), '-o', str(binary)], check=True)
    suppressions = work / 'tsan581.supp'
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


def prehash(work, source, before):
    """The worker's results serve the RSX validations; nothing stale is accepted; mutations are caught."""
    code = harness(source, before)
    results = {
        'plain': run_model(work, source, code, '', 0.5),
        'asanUbsan': run_model(work, source, code, 'address,undefined', 0.25),
        'tsan': run_model(work, source, code, 'thread', 0.0),
    }
    results['mutations'] = {m: run_model(work, source, harness(source, before, m), '', 0.0, expect_failure=True)
                            for m in ('no_epoch_check', 'no_bypass')}
    return results


def policy_contract(source, before):
    """Texture Pre-Validation follows the epochs; the hooks sit where the 559/573 epochs advance."""
    config = (source / CONFIG).read_text()
    assert 'cfg::_enum<ios_experimental_mode> texture_prehash{ this, "Texture Pre-Validation", ios_experimental_mode::automatic };' in config
    policy = (source / POLICY).read_text()
    assert ('resolved.texture_prehash = resolved.texture_validation_epoch && resolve_mode(g_cfg.ios_experimental.texture_prehash, texture_epoch_title);'
            in policy)
    assert 'rpcs3::ios::texture_prehash::enabled.store(resolved.texture_prehash, std::memory_order_relaxed);' in policy
    assert 'scoped_revalidation=%d writer_yield=%d texture_prehash=%d"' in policy
    assert policy.index('resolved.texture_validation_epoch = resolve_mode(') < policy.index('resolved.texture_prehash = ')
    assert 'bool texture_prehash = false;' in (source / POLICY_H).read_text()
    settings = [l for l in (source / SETTINGS).read_text().splitlines(keepends=True) if 'SETTING("experimental.texture_prehash"' in l]
    assert len(settings) == 1 and 'Automatic follows Texture Validation Per FIFO Batch; Disabled hashes on the RSX thread as before.' in settings[0]
    assert (source / SETTINGS).read_text().replace(settings[0], '') == (before / SETTINGS).read_text()
    performance = (source / PERFORMANCE).read_text()
    assert 'COREPROF OPT581 session=%llu window=%llu texture_prehash=%u hits=%llu misses=%llu hit_bytes=%llu ' in performance
    texture = (source / CACHE_H).read_text()
    frame_end = braced(texture, 'virtual void on_frame_end()')
    assert frame_end.index('texture_validation::advance_epoch();') < frame_end.index('texture_prehash::end_frame();')
    vk = braced((source / VK).read_text(), 'void VKGSRender::on_exit()')
    assert vk.index('rpcs3::ios::texture_prehash::stop();') < vk.index('GSRender::on_exit();')
    validation = (source / VALIDATION).read_text()
    advance = braced(validation, 'inline void advance_epoch() noexcept')
    assert advance.index('validation_epoch.fetch_add') < advance.index('listener();')
    utils = (source / UTILS).read_text()
    assert 'void reset_validation() const { validated_epoch = 0; prehash_bypass = true; }' in utils
    cache = (source / CACHE).read_text()
    sync = braced(cache, 'bool buffered_section::sync() const')
    assert sync.index('validated_epoch == epoch') < sync.index('texture_prehash::lookup(')
    assert sync.count('fast_hash_internal()') == 2  # the iOS miss path and the non-iOS path
    worker = braced(cache, 'void worker_main()')
    assert worker.index('const u64 epoch = validation::current_epoch();') < worker.index('hash_guest_range(range_lock')
    assert worker.index('if (validation::current_epoch() != epoch)') < worker.index('hash_guest_range(range_lock')
    guarded = braced(cache, 'bool hash_guest_range(atomic_t<u64, 128>* range_lock, u32 start, u32 length, u64& out) noexcept')
    assert guarded.index('range_lock->store(') < guarded.index('vm::g_range_lock_bits[1].load()') < guarded.index('out = range_hash(vm::g_sudo_addr + start, length);\n\t\t\trange_lock->release(0);')
    return {'automatic': 'Texture Validation Per FIFO Batch titles (God of War III, Call of Duty: Black Ops II, Bladestorm)',
            'disabled': 'hashes on the RSX thread as in 579', 'profileLine': 'COREPROF OPT581'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell581-') as temporary:
        work = Path(temporary)
        before, contract = authenticated_baseline(source, work)
        result = {
            'passed': False, 'build': 581, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
            'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
            'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
            'offIOS': off_ios_unchanged(source, before),
        }
        result['texturePrehash'] = prehash(work, source, before)
        result['policy'] = policy_contract(source, before)
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
        result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                      scope='The 581 production code compiled in a host model; no iPhone FPS, frame time or memory result.')
    text = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
