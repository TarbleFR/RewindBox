#!/usr/bin/env python3
"""Core 933: the local profile per game and its first learned decision, the SPU object prefetch.

REWINDBOX_LOCAL_PROFILE_933 and REWINDBOX_LEARNED_PREFETCH_933 (maintainer audit of 11 Nov 2026, priority 3: keep the
decisions validated for a game on this device for its later launches, and share a correction by mechanism instead of a
title list).

1. Source contract on a materialized Core: the two headers, the profile read by Emulator::Load right before the title
   policy, the learned prefetch after the unchanged title-list resolution (Automatic only), its boot line, and the report
   window that feeds the rule after JITPROF.
2. Host harness (test/rpcs3_local_profile933/harness.cpp) built with ASan/UBSan against the real headers: the file
   format, the rule, and seven boots of one title through the store over a temporary directory.
3. Controls: each mutation of the real headers or of the wiring must be caught.

Nothing here runs a game, Metal or an iPhone; no gain is measured.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/rpcs3_local_profile933/harness.cpp'
STUB = ROOT / 'test/rpcs3_local_profile933/stub'
PROFILE_H = 'rpcs3/ios/IOSLocalProfile933.h'
STORE_H = 'rpcs3/ios/IOSLocalProfileStore933.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SYSTEM = 'rpcs3/Emu/System.cpp'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'

TITLE_LIST_LINE = ('\tresolved.spu_object_prefetch = resolve_mode(g_cfg.ios_experimental.spu_object_prefetch,\n'
                   '\t\trpcs3::ios::title_levers::requires_spu_object_prefetch(title_id));\n')
LEARNED_BLOCK = (
    '\t{\n'
    '\t\tnamespace learned = rpcs3::ios::local_profile933;\n'
    '\t\tconst bool prefetch_learnable = g_cfg.ios_experimental.spu_object_prefetch.get() == ios_experimental_mode::automatic &&\n'
    '\t\t\t!rpcs3::ios::title_levers::requires_spu_object_prefetch(title_id);\n'
    '\t\tconst bool prefetch_learned = prefetch_learnable && learned::current::instance().prefetch().value == learned::state::on;\n'
    '\t\tresolved.spu_object_prefetch = resolved.spu_object_prefetch || prefetch_learned;\n'
    '\t\tlearned::current::instance().begin_boot(prefetch_learnable, prefetch_learned);\n'
    '\t}\n')
BOOT_LOAD = ('\t\t\trpcs3::ios::local_profile933::current::instance().load(m_title_id, m_app_version);\n'
             '\t\t\trpcs3::ios::resolve_experimental_policy();\n')


class Failure(AssertionError):
    pass


def require(value, message):
    if not value:
        raise Failure(message)


def position(text: str, needle: str, what: str) -> int:
    require(text.count(needle) == 1, f'{what}: expected once, found {text.count(needle)} times')
    return text.index(needle)


def read(source: Path, name: str) -> str:
    path = source / name
    require(path.is_file(), f'{name} missing')
    return path.read_text()


def source_contract(source: Path) -> dict:
    profile = read(source, PROFILE_H)
    store = read(source, STORE_H)
    require('REWINDBOX_LOCAL_PROFILE_933' in profile and 'REWINDBOX_LEARNED_PREFETCH_933' in profile, 'profile markers missing')
    require('fs::pending_file destination{path_for(value.serial)};' in store and 'destination.commit()' in store,
            'the profile is not written atomically')
    require('fs::get_config_dir(true) + "local_profiles/"' in store, 'profile directory changed')
    require(re.search(r'if \(!valid_serial\(serial\) \|\| !valid_version\(version\)\)\n\t\t\{\n\t\t\treturn m_status = load_status::not_a_title;', store),
            'a boot without a valid serial and version may read or write a file')

    policy = read(source, POLICY)
    require(policy.count(TITLE_LIST_LINE) == 1, 'the title-list resolution of the prefetch changed')
    at = position(policy, TITLE_LIST_LINE, 'title-list resolution') + len(TITLE_LIST_LINE)
    following = policy[at:at + 1200]
    block = following[following.index('\t{\n'):] if '\t{\n' in following else ''
    require(block.startswith(LEARNED_BLOCK), 'the learned prefetch block does not follow the title-list resolution as reviewed')
    require(policy.count('begin_boot(') == 1 and policy.count('resolved.spu_object_prefetch =') == 2,
            'the prefetch is resolved elsewhere too')
    require('#include "IOSLocalProfileStore933.h"' in policy, 'policy include missing')
    line = re.search(r'"Resolved title policy 933: (.*?)"\n\t\t\t"(.*?)",', policy)
    require(line, 'boot line 933 missing')
    fields = re.findall(r'(\w+)=%', line.group(1) + line.group(2))
    require(fields == ['local_profile', 'version', 'spu_object_prefetch', 'source', 'learned', 'validated', 'evidence_reads',
                       'evidence_ms', 'skipped_lines'], f'boot line 933 fields: {fields}')

    system = read(source, SYSTEM)
    require(system.count(BOOT_LOAD) == 1, 'the profile is not read right before the title policy')
    require(system.count('rpcs3::ios::resolve_experimental_policy();') == 1, 'the title policy is resolved more than once')
    require('#include "ios/IOSLocalProfileStore933.h"' in system, 'System.cpp include missing')
    ios_block = system[:position(system, BOOT_LOAD, 'profile read')]
    require(ios_block.rfind('#ifdef RPCS3_IOS') > ios_block.rfind('#endif'), 'the profile read is outside the iOS block')

    perf = read(source, PERFORMANCE)
    require('#include "IOSLocalProfileStore933.h"' in perf, 'report include missing')
    declared = position(perf, 'rpcs3::ios::local_profile933::window_input profile933_window{};', 'report window declaration')
    prefetch_block = position(perf, 'auto& prefetch = rpcs3::ios::spu_object_prefetch::instance();', 'prefetch block')
    jit_exchange = position(perf, 'const auto jit = jit_phase::g_counters.exchange();', 'JITPROF exchange')
    jit_notice = position(perf, 'ios_core_profiler.notice("%s", jit_line);', 'JITPROF line')
    observe = position(perf, 'learned::current::instance().observe(profile933_window);', 'rule call')
    require(declared < prefetch_block < jit_exchange < jit_notice < observe, 'report window wiring out of order')
    for statement in ('profile933_window.prefetch_active = state.active;', 'profile933_window.prefetch_hits = counters.hits;',
                      'profile933_window.prefetch_planned = state.planned;',
                      'profile933_window.cache_reads = jit.events[jit_phase::spu_cache_read];',
                      'profile933_window.cache_read_us = static_cast<u64>(milliseconds(jit.ticks[jit_phase::spu_cache_read]) * 1000.0);',
                      'profile933_window.frames = current_frames > frame_baseline ? current_frames - frame_baseline : 0;',
                      'profile933_window.gameplay_compiles = gameplay.count;',
                      'profile933_window.session = profile_session;'):
        require(perf.count(statement) == 1, 'report field missing: ' + statement)
    require(position(perf, 'profile933_window.gameplay_compiles = gameplay.count;', 'gameplay field') < observe, 'gameplay compiles filled after the rule')
    require(position(perf, 'profile933_window.session = profile_session;', 'session field') < observe, 'session filled after the rule')
    notice = re.search(r'"COREPROF LOCALPROFILE933 (.*?)"\n\t\t\t\t\t"(.*?)"\n\t\t\t\t\t"(.*?)",\n(.*?)\);', perf, re.S)
    require(notice, 'LOCALPROFILE933 line missing')
    specifiers = re.findall(r'%(?:\.\d+)?(?:llu|u|d|s|f)', ''.join(notice.groups()[:3]))
    arguments = [a for a in re.split(r',\s*(?![^()]*\))', notice.group(4).strip()) if a.strip()]
    require(len(specifiers) == len(arguments) == 12, f'LOCALPROFILE933: {len(specifiers)} specifiers, {len(arguments)} arguments')
    return {'profile_h': PROFILE_H, 'store_h': STORE_H, 'boot_line_fields': fields, 'report_specifiers': len(specifiers)}


# The increments whose feature tests revert them directly on the final tree (the 921 test does, without reverting the
# later ones first): they reverted on the Core 932 tree and must still revert on this one. The Core 933 lines stay out
# of their context (the end of resolve_experimental_policy belongs to the 921 hunk).
DIRECT_REVERTS = ('core905-from-904', 'core906-from-905', 'core921-from-920', 'core924-from-923', 'core929-from-928', 'core930-from-929')


def direct_reverts(source: Path) -> list:
    checked = []
    for name in DIRECT_REVERTS:
        patch = ROOT / f'build-utils/rpcs3/{name}.patch'
        require(patch.is_file(), f'{name}.patch missing')
        result = subprocess.run(['git', 'apply', '-R', '--check', '--whitespace=nowarn', str(patch)], cwd=source,
                                capture_output=True, text=True)
        require(result.returncode == 0, f'{name} no longer reverts on the tree under test: {result.stderr[-500:]}')
        checked.append(name)
    return checked


def run(command, **kwargs):
    result = subprocess.run([str(part) for part in command], capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout + result.stderr


def harness(source: Path, cxx: str, work: Path, label: str) -> dict:
    binary = work / f'harness-{label}'
    code, output = run([cxx, '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all', '-I', STUB, '-I', source / 'rpcs3', HARNESS, '-o', binary])
    if code:
        return {'built': False, 'passed': False, 'output': output[-2000:]}
    data = work / f'data-{label}'
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir()
    code, output = run([binary, data], timeout=300)
    lines = [line for line in output.splitlines() if line.startswith('{')]
    report = json.loads(lines[-1]) if lines else {}
    return {'built': True, 'passed': code == 0 and report.get('failures') == 0, 'checks': report.get('checks', 0),
            'failures': report.get('failures'), 'output': '' if code == 0 else output[-2000:]}


HEADER_MUTATIONS = [
    ('learning from the boot warm-up', PROFILE_H, ' ||\n\t\t\t\tin.gameplay_compiles * 2 < in.cache_reads)', ')'),
    ('a pause counts towards the withdrawal', PROFILE_H, 'm_windows += in.frames ? 1u : 0u;', 'm_windows++;'),
    ('learning while the prefetch runs', PROFILE_H, 'record.value != state::none || in.prefetch_active ||', 'record.value != state::none ||'),
    ('a withdrawn decision learned again', PROFILE_H, 'if (record.value != state::none ||', 'if (record.value == state::on ||'),
    ('another version accepted', PROFILE_H, '\t\t\tif (value != version)\n\t\t\t{\n\t\t\t\treturn load_status::other_version;\n\t\t\t}\n', ''),
    ('a cut file read', PROFILE_H,
     '\t\tif (end == std::string_view::npos)\n\t\t{\n\t\t\treturn load_status::malformed; // every line ends with a newline: a cut file is not read\n'
     '\t\t}\n\t\tstd::string_view line = text.substr(0, end);\n\t\ttext.remove_prefix(end + 1);\n',
     '\t\tstd::string_view line = text.substr(0, end);\n\t\ttext.remove_prefix(end == std::string_view::npos ? text.size() : end + 1);\n'),
    ('a bad serial reads a file', STORE_H, 'if (!valid_serial(serial) || !valid_version(version))', 'if (serial.empty())'),
    ('a failed write reported as saved', STORE_H, 'result.saved = save(m_profile);', 'save(m_profile); result.saved = true;'),
    # Review of 11 Nov (findings F1-F3).
    ('a window of the previous boot used', PROFILE_H, 'if (!m_session_seen || in.session != m_session)',
     'if (false && (!m_session_seen || in.session != m_session))'),
    ('every validation rewrites the file', PROFILE_H, 'if (record.validated >= validation_writes)', 'if (false)'),
    ('a title without a version gets a profile', PROFILE_H, '\treturn digit;\n', '\treturn digit || true;\n'),
]

SOURCE_MUTATIONS = [
    ('learned over a user setting', POLICY, '.get() == ios_experimental_mode::automatic &&\n\t\t\t!rpcs3::ios', '.get() != ios_experimental_mode::disabled &&\n\t\t\t!rpcs3::ios'),
    ('profile read after the policy', SYSTEM, BOOT_LOAD, '\t\t\trpcs3::ios::resolve_experimental_policy();\n'
     '\t\t\trpcs3::ios::local_profile933::current::instance().load(m_title_id, m_app_version);\n'),
    ('the rule never sees the object reads', PERFORMANCE,
     '\t\t\tprofile933_window.cache_reads = jit.events[jit_phase::spu_cache_read];\n', ''),
    ('the rule never sees the compiles of play', PERFORMANCE, '\t\t\tprofile933_window.gameplay_compiles = gameplay.count;\n', ''),
    ('the rule never sees the report session', PERFORMANCE, '\t\t\tprofile933_window.session = profile_session;\n', ''),
    ('the rule fed before the window is read', PERFORMANCE,
     '\t\t\tconst learned::observation seen = learned::current::instance().observe(profile933_window);\n',
     '\t\t\tconst learned::observation seen{};\n'),
]


def mutate(source: Path, work: Path, name: str, old: str, new: str, label: str) -> Path:
    tree = work / f'tree-{label}'
    shutil.rmtree(tree, ignore_errors=True)
    for part in ('rpcs3/ios', 'rpcs3/Emu'):
        (tree / part).parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / 'rpcs3/ios', tree / 'rpcs3/ios')
    (tree / 'rpcs3/Emu').mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / SYSTEM, tree / SYSTEM)
    text = (tree / name).read_text()
    require(text.count(old) == 1, f'mutation anchor not unique in {name}: {old[:60]!r}')
    (tree / name).write_text(text.replace(old, new))
    return tree


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='materialized candidate Core')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'schema': 1, 'source_contract': source_contract(args.source), 'direct_reverts': direct_reverts(args.source)}
    with tempfile.TemporaryDirectory(prefix='rpcs3-local-profile933-') as temp:
        work = Path(temp)
        result = harness(args.source, args.cxx, work, 'candidate')
        require(result['passed'], 'harness failed: ' + result['output'])
        report['harness'] = {'checks': result['checks'], 'sanitizers': 'address,undefined'}
        controls = []
        for index, (label, name, old, new) in enumerate(HEADER_MUTATIONS):
            tree = mutate(args.source, work, name, old, new, f'h{index}')
            outcome = harness(tree, args.cxx, work, f'h{index}')
            require(outcome['built'] and not outcome['passed'], f'control not caught by the harness: {label}')
            controls.append({'control': label, 'caught_by': 'harness'})
        for index, (label, name, old, new) in enumerate(SOURCE_MUTATIONS):
            tree = mutate(args.source, work, name, old, new, f's{index}')
            try:
                source_contract(tree)
            except Failure as caught:
                controls.append({'control': label, 'caught_by': 'source contract', 'message': str(caught)})
                continue
            raise Failure(f'control not caught by the source contract: {label}')
        report['controls'] = controls
    report['limits'] = ['No game, Metal, iPhone or frame measurement; the store runs over a stand-in of Utilities/File.h.',
                        'The thresholds come from device journals of Builds 614-694; their effect on an iPhone is not measured.']
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    print(f'PASS: Core 933 local profile ({result["checks"]} checks, {len(controls)} controls caught)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
