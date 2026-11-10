#!/usr/bin/env python3
"""Source-bound 563 host checks for the in-session A/B of early submission.

The early-submit header is compiled as the Core includes it; the policy block,
the title predicate, resolve_mode, the window-boundary statement and the OPT561
export block are copied verbatim from the 563 Core source; the 561 control
comes from the authenticated reverse fixture. Adapters stand in for the
configuration, the emulator, the logger and the RSX thread's end-of-draw reads.
Results are host correctness only: which state each window runs with and what
it reports. No iPhone frame time, Metal rendering, thermal or memory-pressure
result is inferred.
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
from rpcs3_cell559_test import braced, build_and_run, compilers, normalized_sha, sha, squash

NATIVE = ROOT / 'test/native'
BASE = 'fc1c507f120f7cc20cdf8f3ea62290fda53f66e4'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell563.diff'
EARLY = 'rpcs3/ios/IOSEarlySubmit.h'
DEFERRED = 'rpcs3/ios/IOSDeferredCommit.h'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
TYPES = 'rpcs3/Emu/system_config_types.h'
CONFIG = 'rpcs3/Emu/system_config.h'
RENDERER = ['rpcs3/Emu/RSX/VK/VKGSRender.cpp', 'rpcs3/Emu/RSX/VK/VKGSRender.h',
            'rpcs3/Emu/RSX/VK/VKDraw.cpp', 'rpcs3/Emu/RSX/VK/VKPresent.cpp']
INPUTS = ['test/rpcs3_cell563_test.py', 'test/native/rpcs3_ab563.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))
POLICY_START = '\tconst bool early_submit_title = '
POLICY_END = '\trpcs3::ios::early_submit::alternate.store(early_submit_ab, std::memory_order_relaxed);\n'
BOUNDARY = '            early_submit_state = rpcs3::ios::early_submit::window_boundary();\n'
EXPORT_START = '        // CELL561_OPT_EXPORT:'


def authenticated_baseline(source, work):
    manifest_path = ROOT / 'build-utils/rpcs3/canonical-source.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = manifest['cell563']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell563' not in old_manifest and 'cell561' in old_manifest
    assert record['codegen'] == old_manifest['cell561']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == []
    paths = set(record['modified_paths'])
    assert paths == {EARLY, POLICY, PERFORMANCE, SETTINGS}, paths
    assert set(record['before_sha256']) == set(record['after_sha256']) == paths
    before = work / 'before'
    for path in paths:
        current = source / path
        assert normalized_sha(current) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(current.read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    # Every other Core source, the 561 renderer included, is byte-identical to the 561 Core.
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256'])
    for path, digest in old_manifest['files_sha256'].items():
        if path not in paths:
            assert manifest['files_sha256'][path] == digest, path
    for path in RENDERER:
        assert normalized_sha(source / path) == old_manifest['files_sha256'][path], path
    return before, {
        'baseline': BASE, 'fixtureSHA256': sha(FIXTURE.read_bytes()),
        'manifestSHA256': sha(manifest_path.read_bytes()), 'sourceSHA256': record['after_sha256'],
        'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(paths),
        'rendererUnchangedFrom561': True,
    }


def between(text, start, end):
    """The unique region from `start` through `end`."""
    assert text.count(start) == 1, start
    a = text.index(start)
    b = text.index(end, a) + len(end)
    return text[a:b]


def production_parts(source):
    policy = (source / POLICY).read_text()
    performance = (source / PERFORMANCE).read_text()
    enum = braced((source / TYPES).read_text(), 'enum class ios_experimental_mode') + ';'
    title = braced((source / DEFERRED).read_text(), 'constexpr bool is_dbz_budokai_hd_title(std::string_view title_id) noexcept')
    resolve = braced(policy, 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept')
    block = between(policy, POLICY_START, POLICY_END)
    assert performance.count(BOUNDARY) == 1
    export = braced(performance, EXPORT_START)
    assert 'COREPROF OPT561' in export
    return dict(enum=enum, title=title, resolve=resolve, policy=block, boundary=BOUNDARY, export=export)


def ab_experiment(source, work, sanitizer):
    """Automatic on DBZ alternates per window, on first; every window reports the
    state its draws ran with and its own counters; explicit modes keep one state."""
    template = (NATIVE / 'rpcs3_ab563.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    parts = production_parts(source)
    for key, marker in (('enum', '//@ENUM@'), ('title', '//@TITLE@'), ('resolve', '//@RESOLVE@'),
                        ('policy', '//@POLICY@'), ('boundary', '//@BOUNDARY@'), ('export', '//@EXPORT@')):
        assert prelude.count(marker) == 1, marker
        prelude = prelude.replace(marker, parts[key])
    report, digest = build_and_run(work, 'ab563', prelude + main, source, sanitizer, extra=['-DRPCS3_IOS=1'])
    assert report['sequence'] == '101010101010' and report['policyCases'] == 7
    assert report['onWindows'] == report['offWindows'] == 6
    assert report['everySubmissionReportedOnce'] and report['threadWindows'] == 400
    return dict(report, harnessSHA256=digest)


def boundary_contract(source, before):
    """The switch happens with the window snapshot, under the profile mutex, and the
    export prints that state; nothing else of the reporter changes."""
    performance = (source / PERFORMANCE).read_text()
    report = braced(performance, 'void report_profile_window()')
    lock = report.index('std::lock_guard lock(m_profile_mutex);')
    snapshot_end = report.index('m_profile_window_start = now;')
    assert lock < report.index(BOUNDARY) < snapshot_end
    assert report.index(BOUNDARY) < report.index('"COREPROF OPT561') < report.index('"COREPROF frames=')
    export = braced(performance, EXPORT_START)
    assert 'early_submit_state ? 1u : 0u' in export and 'early::enabled.load' not in export
    assert performance.count('window_boundary()') == 1
    old = (before / PERFORMANCE).read_text()
    stripped = performance.replace('        bool early_submit_state = false;\n', '', 1)
    stripped = stripped.replace('            // CELL563_EARLY_AB: the state of the ending window, switched at the same boundary.\n' + BOUNDARY, '', 1)
    stripped = stripped.replace(' ab=%u ', ' ', 1).replace('early_submit_state ? 1u : 0u', 'early::enabled.load(std::memory_order_relaxed) ? 1u : 0u', 1)
    stripped = stripped.replace('early::min_draws, early::max_per_frame, early::alternate.load(std::memory_order_relaxed) ? 1u : 0u);',
                                'early::min_draws, early::max_per_frame);', 1)
    assert squash(stripped) == squash(old), 'the reporter changed beyond the A/B boundary'
    header, old_header = (source / EARLY).read_text(), (before / EARLY).read_text()
    assert squash(braced(header, 'constexpr verdict decide(')) == squash(braced(old_header, 'constexpr verdict decide('))
    assert 'constexpr std::uint32_t min_draws = 32;' in header and 'constexpr std::uint32_t max_per_frame = 6;' in header
    return {'boundary': 'window snapshot under m_profile_mutex', 'exportsEndingWindowState': True,
            'fpsSummarySameWindow': True, 'decisionUnchangedFrom561': True}


def export_contract(source):
    """The setting key and values, the boot log and the OPT561 line."""
    config = (source / CONFIG).read_text()
    assert 'early_submit{ this, "Early Command Buffer Submission", ios_experimental_mode::automatic };' in config
    policy = (source / POLICY).read_text()
    assert 'early_submit=%d early_submit_ab=%d' in policy and 'resolved.early_submit, early_submit_ab);' in policy
    block = between(policy, POLICY_START, POLICY_END)
    assert ('const bool early_submit_ab = g_cfg.ios_experimental.early_submit == ios_experimental_mode::automatic '
            '&& early_submit_title;') in block
    settings = (source / SETTINGS).read_text()
    entry = between(settings, 'SETTING("experimental.early_submit"', '\n')
    assert '"Early command buffer submission"' in entry and 'alternates it every profiling window' in entry
    performance = (source / PERFORMANCE).read_text()
    line = performance[performance.index('"COREPROF OPT561'):]
    line = line[:line.index('window_boundary_approximate=1"') + 31]
    for field in ('early_submit=%u', 'early_submits=%llu', 'early_draws=%llu', 'gpu_busy_checks=%llu',
                  'frame_capped_checks=%llu', 'min_draws=%u', 'max_per_frame=%u', 'ab=%u'):
        assert field in line, field
    return {'line': 'COREPROF OPT561 ... ab=', 'bootLog': 'early_submit_ab=', 'automaticTitles': ['BLES01658'],
            'settingKeyUnchanged': 'experimental.early_submit'}


def codegen_identity(source):
    """No PPU/SPU codegen input changes: the identities stay those of 561, without an alias."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell563']
    assert cache_identities(source) == record['codegen'] == manifest['cell561']['codegen']
    assert not any(p.startswith('rpcs3/Emu/Cell/') or p.endswith('.cmake') for p in record['modified_paths'])
    return {'identities': record['codegen'], 'unchangedFrom561': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 563, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'boundary': boundary_contract(source, before), 'exportLine': export_contract(source)}
        result['abExperiment'] = {name: ab_experiment(source, work, flag) for name, flag in SANITIZERS}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host correctness of the 563 production bodies: the state each profiling window runs with '
                        'and reports; no iPhone FPS, frame time, Metal rendering, thermal or memory-pressure result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
