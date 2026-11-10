#!/usr/bin/env python3
"""Source-bound 589 host checks: Assassin's Creed joins the texture validation epoch and the scoped revalidation.

Build 585 iPhone logs, first run of Assassin's Creed (BLES00158, official
RPCS3 GameDB entry: Multithreaded RSX, asynchronous texture streaming): in
the game scenes (10-29 fps) the RSX thread limits the frame rate (0.4-0.8
core, FIFO busy 70-96 %) at 1,000-3,300 draws per frame with 14-45 ms of
texture preparation per frame (RSXFRAME551 texture_ms) and no epoch (OPT559
texture_epoch=0), every texture lookup hashing again. AGENTS adds a title to the texture validation per FIFO
batch (559) and the scoped revalidation (573) at 5 ms per frame; Black Ops II
and Bladestorm joined them in 575 (CELL589_TITLE_LEVERS, ios/IOSTitleLevers.h).

589 adds no mechanism. The two policy blocks are compiled verbatim with the
real title predicates and resolve_mode (plain and ASan/UBSan) and evaluated
for every title and mode; the 587 preimages come from the authenticated
reverse fixture, and with the 587 blocks and lines put back the policy,
setting and lever files are the 587 ones byte for byte. No iPhone FPS, frame
time or memory result is inferred.
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

BASE = 'a8a7ce1072c189806f4ddf70552280b3e95a1e17'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell589.diff'
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG_TYPES = 'rpcs3/Emu/system_config_types.h'
PRESSURE = 'rpcs3/ios/IOSMemoryPressurePolicy.h'
MODIFIED = {LEVERS, POLICY, SETTINGS}
NEW_FILES = []
INPUTS = ['test/rpcs3_cell589_test.py']
ASSASSINS_CREED = ['BLES00158', 'BLUS30089']
BLOCKS = [
    ('\t// CELL559_TEXTURE_EPOCH: Automatic is God of War III, where per-draw revalidation',
     'texture_validation::epoch_enabled.store(resolved.texture_validation_epoch, std::memory_order_relaxed);\n'),
    ('\t// CELL575_TITLE_LEVERS: with the texture epoch, Call of Duty: Black Ops II and Bladestorm;',
     'rpcs3::ios::texture_validation_scope::enabled.store(resolved.scoped_texture_revalidation, std::memory_order_relaxed);\n'),
]
OLD_BLOCKS = [
    BLOCKS[0],
    ('\t// CELL575_TITLE_LEVERS: with the texture epoch, Call of Duty: Black Ops II and Bladestorm.',
     'rpcs3::ios::texture_validation_scope::enabled.store(resolved.scoped_texture_revalidation, std::memory_order_relaxed);\n'),
]
AUTOMATIC = {
    'texture_validation_epoch': ("God of War III, Call of Duty: Black Ops II and Bladestorm",
                                 "God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed"),
    'scoped_texture_revalidation': ("God of War III, Call of Duty: Black Ops II and Bladestorm",
                                    "God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed"),
}
PREDICATE = ('\nconstexpr bool is_assassins_creed_title(std::string_view title_id) noexcept\n{\n'
             '\treturn title_id == "BLES00158" || title_id == "BLUS30089";\n}\n')


def full_base():
    return subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip()


def authenticated_baseline(source, work):
    """The 587 preimages: the reverse 589 fixture over the three files, authenticated by both manifests."""
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell589']
    assert record['baseline'] == full_base()
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', full_base() + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell589' not in old_manifest and 'cell587' in old_manifest
    assert record['codegen'] == old_manifest['cell587']['codegen']
    assert record['core_baseline'] == 'cell587' and record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == NEW_FILES and set(record['modified_paths']) == MODIFIED
    before = work / 'before587'
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


def between(text, start, end):
    assert text.count(start) == 1, start
    a = text.index(start)
    return text[a:text.index(end, a) + len(end)]


def placement_contract(source, before):
    """Only the two Automatic predicates, their comments, two setting texts and the lever record change."""
    policy, old_policy = (source / POLICY).read_text(), (before / POLICY).read_text()
    restored = policy
    for (a, b), (c, d) in zip(BLOCKS, OLD_BLOCKS):
        restored = restored.replace(between(policy, a, b), between(old_policy, c, d), 1)
    assert restored == old_policy, 'policy changed beyond the two 589 blocks'
    epoch_block = between(policy, *BLOCKS[0])
    assert 'rpcs3::ios::title_levers::is_assassins_creed_title(title_id);' in epoch_block
    assert 'CELL589_TITLE_LEVERS Assassin\'s Creed' in epoch_block
    scope_block = between(policy, *BLOCKS[1])
    assert 'CELL589_TITLE_LEVERS: Assassin\'s Creed.' in scope_block
    assert 'resolve_mode(g_cfg.ios_experimental.scoped_texture_revalidation, texture_epoch_title)' in scope_block
    settings, old_settings = (source / SETTINGS).read_text(), (before / SETTINGS).read_text()
    changed = [(a, b) for a, b in zip(old_settings.splitlines(), settings.splitlines()) if a != b]
    assert len(settings.splitlines()) == len(old_settings.splitlines()) and len(changed) == len(AUTOMATIC), changed
    for key, (old_titles, new_titles) in AUTOMATIC.items():
        line = next(l for l in settings.splitlines() if 'SETTING("experimental.%s"' % key in l)
        old_line = next(l for l in old_settings.splitlines() if 'SETTING("experimental.%s"' % key in l)
        assert 'Automatic enables it for %s;' % new_titles in line, key
        assert line.replace(new_titles, old_titles, 1) == old_line, key
    levers, old_levers = (source / LEVERS).read_text(), (before / LEVERS).read_text()
    assert levers.count(PREDICATE) == 1
    code = '\n'.join(l for l in levers.replace(PREDICATE, '', 1).splitlines() if not l.lstrip().startswith('//'))
    old_code = '\n'.join(l for l in old_levers.splitlines() if not l.lstrip().startswith('//'))
    assert code == old_code, 'title levers changed beyond the Assassin\'s Creed predicate'
    for text in ('CELL589_TITLE_LEVERS', '14-45 ms of texture', 'preparation per frame (RSXFRAME551 texture_ms)', '1,000-3,300 draws per frame',
                 'no epoch (OPT559', 'texture_epoch=0): every texture lookup hashing again', 'BLES00158, BLUS30089'):
        assert text in levers, text
    return {'policyOtherwiseIdentical': True, 'settingTextsChanged': sorted(AUTOMATIC),
            'leversOtherwiseIdentical': True, 'serials': ASSASSINS_CREED}


def policy_harness(source, blocks, assassins_creed):
    """The policy blocks compiled with the real predicates; Assassin's Creed expected on in Automatic or not."""
    types = (source / CONFIG_TYPES).read_text()
    ac = 'true' if assassins_creed else 'false'
    return (
        '#include <cstdio>\n#include <string>\n#include <string_view>\n'
        '#include "ios/IOSTextureValidationProfile.h"\n#include "ios/IOSTextureResidency.h"\n#include "ios/IOSTitleLevers.h"\n'
        + braced(types, 'enum class ios_experimental_mode') + ';\n'
        + braced((source / PRESSURE).read_text(), 'constexpr bool is_god_of_war_iii_title(std::string_view title_id) noexcept') + '\n'
        + 'namespace texture_validation = rpcs3::ios::texture_validation;\n'
        + braced((source / POLICY).read_text(), 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept') + '\n'
        + 'struct { struct { ios_experimental_mode fps_optimization_batch, texture_hash_hybrid, texture_validation_epoch,'
          ' deferred_fbo_writeback, early_submit, noop_putllc_keeps_reservations, texture_residency,'
          ' scoped_texture_revalidation; } ios_experimental; } g_cfg;\n'
        + 'struct { std::string id; const std::string& GetTitleID() const { return id; } } Emu;\n'
        + 'struct expect { const char* title; bool epoch; };\n'
        + 'int main() { int ok = 1, cases = 0;\n'
        + ' const expect titles[] = {{"BLES00158", ' + ac + '}, {"BLUS30089", ' + ac + '}, {"BCES00510", true}, {"BCUS98111", true},'
          ' {"BLES01717", true}, {"BLES00113", true}, {"BLUS30070", true}, {"BLES01658", false}, {"BLES00159", false},'
          ' {"BLUS30090", false}, {"BLUS31011", false}};\n'
        + ' for (const auto& t : titles) { Emu.id = t.title;\n'
        + '   for (auto mode : {ios_experimental_mode::automatic, ios_experimental_mode::enabled, ios_experimental_mode::disabled}) {\n'
        + '    g_cfg.ios_experimental.texture_validation_epoch = g_cfg.ios_experimental.scoped_texture_revalidation = mode;\n'
        + '    struct { bool texture_validation_epoch = false, scoped_texture_revalidation = false; } resolved;\n'
        + blocks + '\n'
        + '    const bool on = mode == ios_experimental_mode::enabled, autom = mode == ios_experimental_mode::automatic;\n'
        + '    const bool epoch = on || (autom && t.epoch);\n'
        + '    ok &= resolved.texture_validation_epoch == epoch && texture_validation::epoch_enabled.load() == epoch;\n'
        + '    ok &= resolved.scoped_texture_revalidation == epoch && rpcs3::ios::texture_validation_scope::enabled.load() == epoch;\n'
        + '    cases++; } }\n'
        + ' std::printf("{\\"passed\\": %s, \\"cases\\": %d}\\n", ok ? "true" : "false", cases); return ok ? 0 : 1; }\n')


def policy_modes(source, before, work):
    """The two policy blocks, verbatim, for every title and mode; with the 587 blocks only Assassin's Creed
    differs (off in Automatic). The prehash stays God of War III only."""
    policy, old_policy = (source / POLICY).read_text(), (before / POLICY).read_text()
    blocks = '\n'.join(between(policy, a, b) for a, b in BLOCKS)
    code = policy_harness(source, blocks, True)
    report, digest = build_and_run(work, 'policy589', code, source, 'address,undefined', extra=['-DRPCS3_IOS=1'])
    assert report['passed'] and report['cases'] == 11 * 3
    old_blocks = '\n'.join(between(old_policy, a, b) for a, b in OLD_BLOCKS)
    before_report, _ = build_and_run(work, 'policy587', policy_harness(source, old_blocks, False), source, 'address,undefined',
                                     extra=['-DRPCS3_IOS=1'])
    assert before_report['passed'] and before_report['cases'] == 11 * 3
    # Texture pre-validation (581/583) keeps God of War III as its only Automatic title.
    prehash = between(policy, '\tresolved.texture_prehash = resolved.texture_validation_epoch &&', ';\n')
    assert prehash.endswith('resolve_mode(g_cfg.ios_experimental.texture_prehash, is_god_of_war_iii_title(title_id));\n'), prehash
    return dict(report, harnessSHA256=digest, before587=before_report, newlyAutomatic=ASSASSINS_CREED, prehashUnchanged=True)


def codegen_identity(source):
    """No PPU or SPU codegen source changes: the 587 object caches stay valid."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell589']['codegen'] == manifest['cell587']['codegen']
    return {'identities': manifest['cell589']['codegen'], 'unchangedFrom587': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell589-') as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 589, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'offIOS': {'sharedFiles': [], 'iosOnlyFiles': sorted(MODIFIED)},
                  'placement': placement_contract(source, before), 'policy': policy_modes(source, before, work)}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='The 589 policy blocks compiled verbatim for every title and mode; the 559 and 573 mechanisms are unchanged. No iPhone FPS, frame time or memory result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end='')


if __name__ == '__main__':
    main()
