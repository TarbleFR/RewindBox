#!/usr/bin/env python3
"""Source-bound 575 host checks: the Automatic mode of four existing levers covers Black Ops II and Bladestorm.

Build 567 logs. Call of Duty: Black Ops II (BLES01717; SPU and RSX bound,
accurate reservations on): 3.5-10 million failed SPU PUTLLC per 5 s window and
9-16 ms of texture preparation per frame at about 5,270 draws, every lookup
hashing again. Bladestorm (BLES00113, BLUS30070; 30 fps, main PPU thread 18.8 ms per frame):
an RSX thread at 0.66 core for a FIFO busy 31 % of the time and 7.4 ms of
texture preparation per frame. 575 adds no mechanism: no-op PUTLLC keeps
reservations (565) covers Black Ops II, texture validation per FIFO batch
(559) and scoped revalidation (573) cover both, RSX idle park (565) covers
Bladestorm (CELL575_TITLE_LEVERS, ios/IOSTitleLevers.h). The four policy
blocks are compiled verbatim with the real title predicates and resolve_mode
for every title and mode; the 573 preimages come from the authenticated
reverse fixture. No iPhone FPS, frame time or memory result is inferred.
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
from rpcs3_cell559_test import braced, build_and_run, compilers, normalized_sha, sha

BASE = 'd1f61ee0fe6de8d3d692b2e8bcd295057957ece6'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell575.diff'
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG_TYPES = 'rpcs3/Emu/system_config_types.h'
PRESSURE = 'rpcs3/ios/IOSMemoryPressurePolicy.h'
DEFERRED = 'rpcs3/ios/IOSDeferredCommit.h'
MODIFIED = {POLICY, SETTINGS}
INPUTS = ['test/rpcs3_cell575_test.py']
BLOCKS = [
    ('\t// CELL559_TEXTURE_EPOCH: Automatic is God of War III, where per-draw revalidation',
     'texture_validation::epoch_enabled.store(resolved.texture_validation_epoch, std::memory_order_relaxed);\n'),
    ('\t// CELL575_TITLE_LEVERS adds Call of Duty: Black Ops II: 3.5-10 million failed PUTLLC',
     'rpcs3::ios::title_levers::is_black_ops_ii_title(title_id));\n'),
    ('\t// CELL575_TITLE_LEVERS adds Bladestorm: RSX thread 0.66 core',
     'rpcs3::ios::rsx_idle_park::enabled.store(resolved.rsx_idle_park, std::memory_order_relaxed);\n'),
    ('\t// CELL575_TITLE_LEVERS: with the texture epoch, Call of Duty: Black Ops II and Bladestorm.',
     'rpcs3::ios::texture_validation_scope::enabled.store(resolved.scoped_texture_revalidation, std::memory_order_relaxed);\n'),
]
AUTOMATIC = {
    'texture_validation_epoch': 'God of War III, Call of Duty: Black Ops II and Bladestorm',
    'noop_putllc_keeps_reservations': 'Dragon Ball Z Budokai HD Collection and Call of Duty: Black Ops II',
    'rsx_idle_park': 'Dragon Ball Z Budokai HD Collection, God of War III and Bladestorm',
    'scoped_texture_revalidation': 'God of War III, Call of Duty: Black Ops II and Bladestorm',
}


def full_base():
    return subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip()


def authenticated_baseline(source, work):
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell575']
    assert record['baseline'] == full_base()
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', full_base() + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell575' not in old_manifest and 'cell573' in old_manifest
    assert record['codegen'] == old_manifest['cell573']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == [LEVERS] and set(record['modified_paths']) == MODIFIED
    before = work / 'before'
    for path in MODIFIED | {LEVERS}:
        assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    assert not (before / LEVERS).exists()
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | {LEVERS}
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': full_base(), 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'],
                    'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(MODIFIED)}


def between(text, start, end):
    assert text.count(start) == 1, start
    a = text.index(start)
    return text[a:text.index(end, a) + len(end)]


OLD_BLOCKS = [
    ('\t// CELL559_TEXTURE_EPOCH: Automatic is God of War III only',
     'texture_validation::epoch_enabled.store(resolved.texture_validation_epoch, std::memory_order_relaxed);\n'),
    ('\tresolved.noop_putllc_keeps_reservations = resolve_mode(', 'is_dbz_budokai_hd_title(Emu.GetTitleID()));\n'),
    ('\tresolved.rsx_idle_park = g_cfg.ios_experimental.fifo_idle_mode',
     'rpcs3::ios::rsx_idle_park::enabled.store(resolved.rsx_idle_park, std::memory_order_relaxed);\n'),
    ('\tresolved.scoped_texture_revalidation = resolve_mode(',
     'rpcs3::ios::texture_validation_scope::enabled.store(resolved.scoped_texture_revalidation, std::memory_order_relaxed);\n'),
]


def placement_contract(source, before):
    """Only the Automatic predicates of the four levers and their setting texts change: with the
    573 blocks put back and the include removed, the policy file is the 573 one byte for byte."""
    policy, old_policy = (source / POLICY).read_text(), (before / POLICY).read_text()
    restored = policy.replace('#include "IOSTitleLevers.h"\n', '', 1)
    assert policy.count('#include "IOSTitleLevers.h"\n') == 1
    for (a, b), (c, d) in zip(BLOCKS, OLD_BLOCKS):
        restored = restored.replace(between(policy, a, b), between(old_policy, c, d), 1)
    assert restored == old_policy, 'policy changed beyond the four 575 blocks'
    settings, old_settings = (source / SETTINGS).read_text(), (before / SETTINGS).read_text()
    changed = [(a, b) for a, b in zip(old_settings.splitlines(), settings.splitlines()) if a != b]
    assert len(settings.splitlines()) == len(old_settings.splitlines()) and len(changed) == len(AUTOMATIC), changed
    for key, titles in AUTOMATIC.items():
        line = next(l for l in settings.splitlines() if 'SETTING("experimental.%s"' % key in l)
        assert 'Automatic enables it for %s;' % titles in line, key
    for old, new in changed:
        assert old.split('Automatic enables it for')[0] == new.split('Automatic enables it for')[0]
    levers = (source / LEVERS).read_text()
    assert 'return title_id == "BLES01717";' in levers
    assert 'return title_id == "BLES00113" || title_id == "BLUS30070";' in levers
    return {'policyOtherwiseIdentical': True, 'settingTextsChanged': sorted(AUTOMATIC), 'serials': {
        'blackOpsII': ['BLES01717'], 'bladestorm': ['BLES00113', 'BLUS30070']}}


def policy_modes(source, work):
    """The four policy blocks, verbatim, for every title, mode and FIFO idle mode."""
    policy = (source / POLICY).read_text()
    blocks = '\n'.join(between(policy, a, b) for a, b in BLOCKS)
    types = (source / CONFIG_TYPES).read_text()
    code = (
        '#include <cstdio>\n#include <string>\n#include <string_view>\n'
        '#include "ios/IOSTextureValidationProfile.h"\n#include "ios/IOSTextureResidency.h"\n'
        '#include "ios/IOSRsxIdlePark.h"\n#include "ios/IOSTitleLevers.h"\n'
        + braced(types, 'enum class ios_experimental_mode') + ';\n'
        + braced(types, 'enum class ios_fifo_idle_mode') + ';\n'
        + braced((source / PRESSURE).read_text(), 'constexpr bool is_god_of_war_iii_title(std::string_view title_id) noexcept') + '\n'
        + 'namespace rpcs3::ios::deferred_commit {\n'
        + braced((source / DEFERRED).read_text(), 'constexpr bool is_dbz_budokai_hd_title(std::string_view title_id) noexcept') + '\n}\n'
        + 'namespace texture_validation = rpcs3::ios::texture_validation;\n'
        + braced(policy, 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept') + '\n'
        + 'struct { struct { ios_experimental_mode texture_validation_epoch, noop_putllc_keeps_reservations, rsx_idle_park,'
          ' scoped_texture_revalidation; ios_fifo_idle_mode fifo_idle_mode; } ios_experimental; } g_cfg;\n'
        + 'struct { std::string id; const std::string& GetTitleID() const { return id; } } Emu;\n'
        + 'struct expect { const char* title; bool epoch, noop, park; };\n'
        + 'int main() { int ok = 1, cases = 0;\n'
        + ' const expect titles[] = {{"BCES00510", true, false, true}, {"BLES01717", true, true, false},'
          ' {"BLES00113", true, false, true}, {"BLUS30070", true, false, true}, {"BLES01658", false, true, true},'
          ' {"BLES01863", false, false, false}, {"BLUS31011", false, false, false}};\n'
        + ' for (const auto& t : titles) { Emu.id = t.title;\n'
        + '  for (auto fifo : {ios_fifo_idle_mode::yield, ios_fifo_idle_mode::wait_for_event}) {\n'
        + '   for (auto mode : {ios_experimental_mode::automatic, ios_experimental_mode::enabled, ios_experimental_mode::disabled}) {\n'
        + '    g_cfg.ios_experimental.texture_validation_epoch = g_cfg.ios_experimental.noop_putllc_keeps_reservations ='
          ' g_cfg.ios_experimental.rsx_idle_park = g_cfg.ios_experimental.scoped_texture_revalidation = mode;\n'
        + '    g_cfg.ios_experimental.fifo_idle_mode = fifo;\n'
        + '    struct { bool texture_validation_epoch = false, noop_putllc_keeps_reservations = false, rsx_idle_park = false,'
          ' scoped_texture_revalidation = false; } resolved;\n'
        + blocks + '\n'
        + '    const bool on = mode == ios_experimental_mode::enabled, autom = mode == ios_experimental_mode::automatic;\n'
        + '    const bool epoch = on || (autom && t.epoch), noop = on || (autom && t.noop);\n'
        + '    const bool park = fifo == ios_fifo_idle_mode::yield && (on || (autom && t.park));\n'
        + '    ok &= resolved.texture_validation_epoch == epoch && texture_validation::epoch_enabled.load() == epoch;\n'
        + '    ok &= resolved.scoped_texture_revalidation == epoch && rpcs3::ios::texture_validation_scope::enabled.load() == epoch;\n'
        + '    ok &= resolved.noop_putllc_keeps_reservations == noop;\n'
        + '    ok &= resolved.rsx_idle_park == park && rpcs3::ios::rsx_idle_park::enabled.load() == park;\n'
        + '    cases++; } } }\n'
        + ' std::printf("{\\"passed\\": %s, \\"cases\\": %d}\\n", ok ? "true" : "false", cases); return ok ? 0 : 1; }\n')
    report, digest = build_and_run(work, 'policy575', code, source, 'address,undefined', extra=['-DRPCS3_IOS=1'])
    assert report['cases'] == 7 * 2 * 3
    return dict(report, harnessSHA256=digest)


def codegen_identity(source):
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell575']['codegen'] == manifest['cell573']['codegen']
    return {'identities': manifest['cell575']['codegen'], 'unchangedFrom573': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 575, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'placement': placement_contract(source, before), 'policy': policy_modes(source, work)}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='The 575 policy blocks compiled verbatim for every title and mode; no iPhone FPS, frame time or memory result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
