#!/usr/bin/env python3
"""Source-bound 565 host checks: early submission kept on for DBZ, no-op PUTLLC
that keeps the other reservations, and the RSX idle park.

The RSX idle-park header is compiled as the Core includes it; the policy block,
the title predicates, resolve_mode, the no-op block of spu_thread::do_putllc and
the park block of FIFO_control::idle_wait are copied verbatim from the 565 Core
source (the park block's `return;` reads `return true;`, so the harness can see
that it parked). The 563 preimages come from the authenticated reverse fixture.
Adapters stand in for the configuration, the emulator, guest memory and the
reservation word. Results are host behaviour only: the reservation protocol,
the failures it removes in a three-poller model, and the idle thread's CPU time
on this host. No iPhone FPS, frame time, Metal rendering or thermal result is
inferred.
"""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from rpcs3_cell559_test import braced, build_and_run, compilers, normalized_sha, sha, squash, without_ios_blocks

NATIVE = ROOT / 'test/native'
BASE = 'e9ee22ed51525623c5776c01fd0c237bd65912f5'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell565.diff'
EARLY = 'rpcs3/ios/IOSEarlySubmit.h'
PARK = 'rpcs3/ios/IOSRsxIdlePark.h'
DEFERRED = 'rpcs3/ios/IOSDeferredCommit.h'
MEMORY = 'rpcs3/ios/IOSMemoryPressurePolicy.h'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
TYPES = 'rpcs3/Emu/system_config_types.h'
CONFIG = 'rpcs3/Emu/system_config.h'
SPU = 'rpcs3/Emu/Cell/SPUThread.cpp'
FIFO = 'rpcs3/Emu/RSX/RSXFIFO.cpp'
FIFO_H = 'rpcs3/Emu/RSX/RSXFIFO.h'
THREAD = 'rpcs3/Emu/RSX/RSXThread.cpp'
ZCULL = 'rpcs3/Emu/RSX/RSXZCULL.cpp'
RENDERER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
# Untouched by the Cores before 565: their preimage is the upstream file.
UPSTREAM_FILES = {ZCULL}
MODIFIED = {COMPAT, SPU, FIFO, FIFO_H, THREAD, ZCULL, RENDERER, CONFIG, EARLY, POLICY, POLICY_H, PERFORMANCE, SETTINGS}
INPUTS = ['test/rpcs3_cell565_test.py', 'test/native/rpcs3_spu_rsx565.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))
POLICY_START = '\t// CELL565_NOOP_PUTLLC: Automatic is'
POLICY_END = '\trpcs3::ios::rsx_idle_park::enabled.store(resolved.rsx_idle_park, std::memory_order_relaxed);\n'
NOOP_START = 'if (accurate && cmp_rdata(to_write, rdata))'
PARK_START = 'if (m_rsx_idle_park)'
PARK_RETURN = '\t\t\t\t\trpcs3::ios::rsx_idle_park::park();\n\t\t\t\t\treturn;\n'
WAKE = 'rpcs3::ios::rsx_idle_park::wake();'


def authenticated_baseline(source, work):
    manifest_path = ROOT / 'build-utils/rpcs3/canonical-source.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = manifest['cell565']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell565' not in old_manifest and 'cell563' in old_manifest
    assert record['codegen'] == old_manifest['cell563']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == [PARK]
    assert set(record['modified_paths']) == MODIFIED, set(record['modified_paths']) ^ MODIFIED
    assert set(record['before_sha256']) == MODIFIED
    assert set(record['after_sha256']) == MODIFIED | {PARK}
    before = work / 'before'
    for path in MODIFIED | {PARK}:
        current = source / path
        assert normalized_sha(current) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(current.read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    assert not (before / PARK).exists()
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest, path
        # A file the earlier Cores left as upstream wrote it enters the manifest now;
        # the Core driver compares its preimage with the upstream commit.
        assert path in UPSTREAM_FILES or digest == old_manifest['files_sha256'][path], path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | {PARK} | UPSTREAM_FILES
    assert not UPSTREAM_FILES & set(old_manifest['files_sha256'])
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {
        'baseline': BASE, 'fixtureSHA256': sha(FIXTURE.read_bytes()),
        'manifestSHA256': sha(manifest_path.read_bytes()), 'sourceSHA256': record['after_sha256'],
        'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(MODIFIED),
    }


def between(text, start, end):
    """The unique region from `start` through `end`."""
    assert text.count(start) == 1, start
    a = text.index(start)
    b = text.index(end, a) + len(end)
    return text[a:b]


def production_parts(source):
    policy = (source / POLICY).read_text()
    types = (source / TYPES).read_text()
    enums = (braced(types, 'enum class ios_experimental_mode') + ';\n' +
             braced(types, 'enum class ios_fifo_idle_mode') + ';')
    dbz = braced((source / DEFERRED).read_text(), 'constexpr bool is_dbz_budokai_hd_title(std::string_view title_id) noexcept')
    gow3 = braced((source / MEMORY).read_text(), 'constexpr bool is_god_of_war_iii_title(std::string_view title_id) noexcept')
    resolve = braced(policy, 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept')
    block = between(policy, POLICY_START, POLICY_END)
    noop = braced((source / SPU).read_text(), NOOP_START)
    assert 'CELL565_NOOP_PUTLLC' in noop and noop.count('res.compare_and_swap_test(rtime, rtime + 128)') == 1
    park = braced((source / FIFO).read_text(), PARK_START)
    assert park.count(PARK_RETURN) == 1
    park = park.replace(PARK_RETURN, PARK_RETURN.replace('return;', 'return true;'))
    end_idle = braced((source / FIFO_H).read_text(), 'void end_idle_period()')
    return dict(enums=enums, dbz=dbz, gow3=gow3, resolve=resolve, policy=block, noop=noop, park=park, endidle=end_idle)


def experiment(source, work, sanitizer):
    template = (NATIVE / 'rpcs3_spu_rsx565.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    parts = production_parts(source)
    for key, marker in (('enums', '//@ENUMS@'), ('dbz', '//@DBZ@'), ('gow3', '//@GOW3@'), ('resolve', '//@RESOLVE@'),
                        ('policy', '//@POLICY@'), ('noop', '//@NOOP@'), ('park', '//@PARK@'), ('endidle', '//@ENDIDLE@')):
        assert prelude.count(marker) == 1, marker
        prelude = prelude.replace(marker, parts[key])
    report, digest = build_and_run(work, 'spu_rsx565', prelude + main, source, sanitizer, extra=['-DRPCS3_IOS=1'])
    assert report['policyCases'] == 6 * 27 and report['noopProtocolCases'] == 10
    keep, advance = report['contention']['keep'], report['contention']['advance']
    assert keep['workerFailures'] == 0 and keep['finalTime'] == report['contention']['increments'] * 128
    park = report['park']
    assert park['resetRestartsGrace'] and park['wakeWithoutParkedIsNoop'] and park['woken'] == park['wakes'] == 200
    assert park['firstParkAfterUs'] >= park['graceUs'] and park['enabledParks'] > 0
    assert park['notifyWaitUs'] < 1_000_000
    return dict(report, harnessSHA256=digest)


def timing(source, work):
    """An optimized build without sanitizers: the contention and CPU figures of this host."""
    template = (NATIVE / 'rpcs3_spu_rsx565.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    parts = production_parts(source)
    for key, marker in (('enums', '//@ENUMS@'), ('dbz', '//@DBZ@'), ('gow3', '//@GOW3@'), ('resolve', '//@RESOLVE@'),
                        ('policy', '//@POLICY@'), ('noop', '//@NOOP@'), ('park', '//@PARK@'), ('endidle', '//@ENDIDLE@')):
        prelude = prelude.replace(marker, parts[key])
    report, digest = build_and_run(work, 'spu_rsx565_timing', prelude + main, source, '', extra=['-DRPCS3_IOS=1'],
                                   args=['timing'], optimize='-O2')
    park = report['park']
    # The parked idle thread uses a fraction of the core the yielding one keeps.
    assert park['enabledCpuUs'] * 2 < park['enabledWallUs'], park
    return dict(report, harnessSHA256=digest, scope='host timing; not an iPhone measurement')


def early_submit_contract(source, before):
    """The 563 alternation is gone: header and reporter are the 561 ones again,
    and Automatic keeps the lever on for DBZ for the whole session."""
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    for path in (EARLY, PERFORMANCE):
        assert normalized_sha(source / path) == manifest['cell561']['after_sha256'][path], path
    policy = (source / POLICY).read_text()
    for gone in ('early_submit_ab', 'alternate', 'window_boundary'):
        assert gone not in policy, gone
    assert ('resolved.early_submit = resolve_mode(g_cfg.ios_experimental.early_submit,\n'
            '\t\trpcs3::ios::deferred_commit::is_dbz_budokai_hd_title(Emu.GetTitleID()));') in policy
    entry = between((source / SETTINGS).read_text(), 'SETTING("experimental.early_submit"', '\n')
    assert 'Automatic enables it for Dragon Ball Z Budokai HD Collection only;' in entry and 'alternates' not in entry
    return {'automatic': 'BLES01658 on for the whole session', 'headerAndReporterEqual561': True, 'alternationRemoved': True}


def placement_contract(source, before):
    """Where the new code sits, what it leaves alone, and what a non-iOS build sees."""
    spu, old_spu = (source / SPU).read_text(), (before / SPU).read_text()
    noop = braced(spu, NOOP_START)
    old_noop = braced(old_spu, NOOP_START)
    ios = between(noop, '#ifdef RPCS3_IOS\n', '#endif\n')
    assert squash(noop.replace(ios, '', 1)) == squash(old_noop), 'the accurate no-op path changed beyond the 565 block'
    assert spu.replace(ios, '', 1) == old_spu
    fifo, old_fifo = (source / FIFO).read_text(), (before / FIFO).read_text()
    wait = braced(fifo, 'void FIFO_control::idle_wait()')
    assert wait.index(PARK_START) < wait.index('if (m_idle_spins < 8)')
    assert fifo.count('fifo_ctrl->end_idle_period(); // CELL565_RSX_IDLE_PARK') == 1
    resume = between(fifo, 'if (const auto state = performance_counters.state;', 'fifo_wake_delay();')
    assert 'end_idle_period()' in resume
    wakes = {path: (source / path).read_text().count(WAKE) for path in (RENDERER, THREAD, ZCULL)}
    assert wakes == {RENDERER: 2, THREAD: 1, ZCULL: 1}, wakes
    renderer = (source / RENDERER).read_text()
    assert renderer.index('m_flush_requests.post(false);') < renderer.index('// CELL565_RSX_IDLE_PARK: this thread waits')
    for path in (SPU, FIFO, FIFO_H, THREAD, ZCULL, RENDERER, CONFIG):
        assert without_ios_blocks((source / path).read_text()) == without_ios_blocks((before / path).read_text()), path
    header = (source / PARK).read_text()
    assert 'constexpr std::uint64_t grace_us = 1000;' in header and 'constexpr std::uint64_t slice_us = 50;' in header
    config = (source / CONFIG).read_text()
    assert 'noop_putllc_keeps_reservations{ this, "No-op PUTLLC Keeps Reservations", ios_experimental_mode::automatic };' in config
    assert 'rsx_idle_park{ this, "RSX Idle Park", ios_experimental_mode::automatic };' in config
    settings = (source / SETTINGS).read_text()
    for key in ('experimental.noop_putllc_keeps_reservations', 'experimental.rsx_idle_park'):
        assert settings.count(f'SETTING("{key}"') == 1, key
    policy = (source / POLICY).read_text()
    assert 'noop_putllc=%d rsx_idle_park=%d' in policy
    return {'noopBlockOnlyAddition': True, 'parkBeforeYieldLoop': True, 'idlePeriodEndsOnResume': True,
            'wakeSites': wakes, 'nonIOSUnchanged': True, 'graceUs': 1000, 'sliceUs': 50}


def codegen_identity(source):
    """The SPUThread.cpp edit is host code SPU objects call: the 546 alias moves to
    the new snapshot, and the PPU/SPU identities stay those of 563."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell565']
    assert cache_identities(source) == record['codegen'] == manifest['cell563']['codegen']
    actual = sha((source / SPU).read_bytes())
    assert record['codegen_alias']['actual_sha256'] == actual
    compat = (source / COMPAT).read_text()
    assert f'actual STREQUAL "{actual}"' in compat
    assert compat.count('elseif(source STREQUAL "Cell/SPUThread.cpp"') == 1
    return {'identities': record['codegen'], 'unchangedFrom563': True, 'spuThreadAlias': actual,
            'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 565, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'earlySubmit': early_submit_contract(source, before), 'placement': placement_contract(source, before)}
        result['experiment'] = {name: experiment(source, work, flag) for name, flag in SANITIZERS}
        result['hostTiming'] = timing(source, work)
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host behaviour of the 565 production bodies: policy resolution, the no-op PUTLLC protocol and '
                        'the contention it removes in a three-poller model, and the RSX idle park; no iPhone FPS, frame '
                        'time, Metal rendering, thermal or memory-pressure result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
