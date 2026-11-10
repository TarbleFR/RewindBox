#!/usr/bin/env python3
"""Source-bound 585 host checks: early command buffer submission for God of War III (CELL585_EARLY_SUBMIT_GOW3).

Build 583 iPhone logs. God of War III (BCES00510) reads one 1280x720x4 render
target back every frame (one READBACK555 fault_read per frame, 3.69 MB each)
and waits for the GPU: 2.1-6.7 ms per frame and 0.80-1.06 s per 5 s window in
the ~700-draw scenes, with Multithreaded RSX on. That is Dragon Ball Z's
pattern before 561, where early submission cut the read-back wait by 1.7 ms
per frame (build 563 A/B, 12 of 12 pairs). The 561 mechanism is unchanged;
its Automatic mode now also covers the six God of War III serials.

The production resolve_mode, is_dbz_budokai_hd_title, is_god_of_war_iii_title
and the early-submission policy expression are compiled together and
evaluated for every mode and for the God of War III, Dragon Ball Z, Black Ops
II, Bladestorm and other serials; the 583 expression beside it gives the
before. The 561 decision (ios/IOSEarlySubmit.h) and the RSX call site are
the 583 ones. No iPhone FPS, frame time or memory result is inferred.
"""
import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from rpcs3_cell559_test import braced, compilers, normalized_sha, sha

BASE = '8ebca28794af4ea0056c90e6d5ee13140dc94ad6'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell585.diff'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
MEMORY = 'rpcs3/ios/IOSMemoryPressurePolicy.h'
DEFERRED = 'rpcs3/ios/IOSDeferredCommit.h'
EARLY = 'rpcs3/ios/IOSEarlySubmit.h'
VK = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
DRAW = 'rpcs3/Emu/RSX/VK/VKDraw.cpp'
TYPES = 'rpcs3/Emu/system_config_types.h'
MODIFIED = {POLICY, SETTINGS, LEVERS}
NEW_FILES = []
INPUTS = ['test/rpcs3_cell585_test.py']
GOW3 = ['BCES00510', 'BCES00799', 'BCUS98111', 'BCJS37001', 'BCAS25003', 'BCKS15003']
OTHERS = ['BLES01717', 'BLES00113', 'BLUS30070', 'BLES00215', 'NPUB00000']
SETTING_TEXT = ('Automatic enables it for Dragon Ball Z Budokai HD Collection and God of War III; '
                'Disabled sends at the end of the frame as before.')
EXPRESSION = re.compile(r'resolved\.early_submit = resolve_mode\(g_cfg\.ios_experimental\.early_submit,\n\t\t(.+?)\);\n')


def full_base():
    return subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip()


def authenticated_baseline(source, work):
    """The 583 preimages: the reverse 585 fixture over the three files, authenticated by both manifests."""
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell585']
    assert record['baseline'] == full_base()
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', full_base() + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell585' not in old_manifest and 'cell583' in old_manifest
    assert record['codegen'] == old_manifest['cell583']['codegen']
    assert record['core_baseline'] == 'cell583' and record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == NEW_FILES and set(record['modified_paths']) == MODIFIED
    before = work / 'before583'
    for path in MODIFIED:
        assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256'])
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': full_base(), 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'], 'newFiles': NEW_FILES,
                    'otherCoreSourcesUnchanged': len(set(old_manifest['files_sha256']) - MODIFIED)}


def codegen_identity(source):
    """No PPU or SPU codegen source changes: the 583 object caches stay valid."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell585']['codegen'] == manifest['cell583']['codegen']
    return {'identities': manifest['cell585']['codegen'], 'unchangedFrom583': True, 'coldCompileRequiredByThisChange': False}


def without_comments(text):
    return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('//'))


def source_contract(source, before):
    """Only the Automatic expression, its comment, the setting text and the levers record change."""
    policy, old_policy = (source / POLICY).read_text(), (before / POLICY).read_text()
    new_expr, old_expr = EXPRESSION.search(policy).group(1), EXPRESSION.search(old_policy).group(1)
    assert old_expr == 'rpcs3::ios::deferred_commit::is_dbz_budokai_hd_title(Emu.GetTitleID())', old_expr
    assert new_expr == 'rpcs3::ios::deferred_commit::is_dbz_budokai_hd_title(title_id) || is_god_of_war_iii_title(title_id)', new_expr
    assert policy.index('const std::string_view title_id = Emu.GetTitleID();') < policy.index('resolved.early_submit = resolve_mode(')
    assert 'rpcs3::ios::early_submit::enabled.store(resolved.early_submit, std::memory_order_relaxed);' in policy
    assert without_comments(policy).replace(new_expr, old_expr) == without_comments(old_policy)
    assert 'CELL585_EARLY_SUBMIT_GOW3 adds God of War III' in policy
    entry = [l for l in (source / SETTINGS).read_text().splitlines(keepends=True) if 'SETTING("experimental.early_submit"' in l]
    old_entry = [l for l in (before / SETTINGS).read_text().splitlines(keepends=True) if 'SETTING("experimental.early_submit"' in l]
    assert len(entry) == len(old_entry) == 1 and SETTING_TEXT in entry[0]
    assert 'Automatic enables it for Dragon Ball Z Budokai HD Collection only;' in old_entry[0]
    assert (source / SETTINGS).read_text().replace(entry[0], old_entry[0]) == (before / SETTINGS).read_text()
    levers, old_levers = (source / LEVERS).read_text(), (before / LEVERS).read_text()
    assert without_comments(levers) == without_comments(old_levers)
    for text in ('CELL585_EARLY_SUBMIT_GOW3', 'is_god_of_war_iii_title', '1280x720x4', '2.1-6.7 ms per frame', 'Multithreaded RSX on'):
        assert text in levers, text
    # The 561 mechanism and its RSX call site are the 583 ones.
    vk = (source / VK).read_text()
    body = braced(vk, 'void VKGSRender::ios_early_submit()')
    assert 'early::decide(true, m_ios_draws_since_submit, m_ios_early_submits_this_frame, gpu_idle)' in body
    assert '(m_queue_status & flush_queue_state::deadlock)' in body and 'vk::is_uninterruptible()' in body
    assert 'ios_early_submit();' in (source / DRAW).read_text()
    return {'automaticBefore': old_expr, 'automaticAfter': new_expr, 'setting': SETTING_TEXT,
            'mechanismUnchanged': ['ios/IOSEarlySubmit.h', 'VKGSRender::ios_early_submit', 'VKDraw.cpp call site']}


def serials(function_text):
    return re.findall(r'"([A-Z]{4}\d{5})"', function_text)


def gating(source, before, work):
    """The production gating code, compiled: which serials early submission covers in each mode."""
    enum = braced((source / TYPES).read_text(), 'enum class ios_experimental_mode')
    resolve = braced((source / POLICY).read_text(), 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept')
    dbz = braced((source / DEFERRED).read_text(), 'constexpr bool is_dbz_budokai_hd_title(std::string_view title_id) noexcept')
    gow3 = braced((source / MEMORY).read_text(), 'constexpr bool is_god_of_war_iii_title(std::string_view title_id) noexcept')
    decide = braced((source / EARLY).read_text(), 'constexpr verdict decide(bool on, std::uint32_t draws, std::uint32_t this_frame, bool gpu_idle) noexcept')
    verdicts = braced((source / EARLY).read_text(), 'enum class verdict : std::uint8_t')
    assert sorted(serials(gow3)) == sorted(GOW3), serials(gow3)
    dbz_serials = serials(dbz)
    assert dbz_serials and not set(dbz_serials) & set(GOW3 + OTHERS)
    new_expr = EXPRESSION.search((source / POLICY).read_text()).group(1)
    old_expr = EXPRESSION.search((before / POLICY).read_text()).group(1).replace('Emu.GetTitleID()', 'title_id')
    titles = GOW3 + dbz_serials + OTHERS
    code = '\n'.join([
        '#include <cstdint>', '#include <cstdio>', '#include <string_view>',
        enum + ';',
        'namespace rpcs3::ios {',
        resolve,
        'namespace deferred_commit {', dbz, '}',
        gow3,
        'namespace early_submit {', 'constexpr std::uint32_t min_draws = 32;', 'constexpr std::uint32_t max_per_frame = 6;',
        verdicts + ';', decide, '}',
        'bool automatic_after(std::string_view title_id) { return ' + new_expr + '; }',
        'bool automatic_before(std::string_view title_id) { return ' + old_expr + '; }',
        '}',
        'int main() {',
        '  using namespace rpcs3::ios;',
        '  const ios_experimental_mode modes[] = {ios_experimental_mode::automatic, ios_experimental_mode::enabled, ios_experimental_mode::disabled};',
        '  const char* titles[] = {' + ', '.join('"%s"' % t for t in titles) + '};',
        '  std::printf("{\\"cases\\":[");',
        '  bool first = true;',
        '  for (const char* t : titles) for (int m = 0; m < 3; m++) {',
        '    std::printf("%s{\\"title\\":\\"%s\\",\\"mode\\":%d,\\"after\\":%d,\\"before\\":%d}", first ? "" : ",", t, m,',
        '      resolve_mode(modes[m], automatic_after(t)) ? 1 : 0, resolve_mode(modes[m], automatic_before(t)) ? 1 : 0);',
        '    first = false; }',
        '  using early_submit::verdict;',
        '  const bool decide_ok = early_submit::decide(true, 32, 0, true) == verdict::submit &&',
        '    early_submit::decide(true, 31, 0, true) == verdict::keep && early_submit::decide(true, 64, 6, true) == verdict::capped &&',
        '    early_submit::decide(true, 64, 0, false) == verdict::gpu_busy && early_submit::decide(false, 64, 0, true) == verdict::keep;',
        '  std::printf("],\\"decideUnchanged\\":%d}\\n", decide_ok ? 1 : 0);',
        '  return decide_ok ? 0 : 1;',
        '}'])
    cpp = work / 'gating585.cpp'
    cpp.write_text(code)
    reports = {}
    for label, extra in (('plain', []), ('asanUbsan', ['-fsanitize=address,undefined'])):
        binary = work / ('gating585-' + label)
        subprocess.run(compilers() + ['-std=gnu++20', '-O1', '-Wall', '-Wextra', '-Werror', *extra, str(cpp), '-o', str(binary)], check=True)
        reports[label] = json.loads(subprocess.check_output([str(binary)], text=True))
    assert reports['plain'] == reports['asanUbsan']
    report = reports['plain']
    assert report['decideUnchanged'] == 1
    names = ['automatic', 'enabled', 'disabled']
    table = {}
    for case in report['cases']:
        title, mode = case['title'], names[case['mode']]
        if mode == 'enabled':
            assert case['after'] == case['before'] == 1, case
        elif mode == 'disabled':
            assert case['after'] == case['before'] == 0, case
        elif title in GOW3:
            assert case['after'] == 1 and case['before'] == 0, case
        elif title in dbz_serials:
            assert case['after'] == case['before'] == 1, case
        else:
            assert case['after'] == case['before'] == 0, case
        table.setdefault(title, {})[mode] = case['after']
    return {'cases': len(report['cases']), 'automaticOn': sorted(t for t, v in table.items() if v['automatic']),
            'automaticNewlyOn': GOW3, 'dbzSerials': dbz_serials, 'otherSerialsOff': OTHERS,
            'enabledAll': True, 'disabledNone': True, 'decideUnchanged': True, 'sanitizers': ['address', 'undefined']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell585-') as temporary:
        work = Path(temporary)
        before, contract = authenticated_baseline(source, work)
        result = {
            'passed': False, 'build': 585, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
            'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
            'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
            'offIOS': {'sharedFiles': [], 'iosOnlyFiles': sorted(MODIFIED)},
            'policy': source_contract(source, before),
            'gating': gating(source, before, work),
        }
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
        result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                      scope='The 585 gating code compiled and evaluated on the host; the 561 mechanism is unchanged. No iPhone FPS, frame time or memory result.')
    text = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
