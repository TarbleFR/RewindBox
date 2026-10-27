#!/usr/bin/env python3
"""Source-bound 571 host checks: passive-lock fairness (vm::passive_lock, vm::writer_lock).

Build 567, Dragon Ball Z combat: 520-720 passive-lock episodes per 5 s window,
90-200 ms and up to 10 ms each (build 564: 3-10 ms in total), while ~120,000
heavy PUTLLC took their writer lock in 103 ms instead of 12.8 ms. A CPU thread
re-entering guest memory waits until no exclusive writer bit is set; SPUs
taking writer locks back to back keep the word set and the waiter, woken only
when it clears, finds a new writer each time. The 571 gate: a waiter past two
timed waits marks itself starving and new writers defer (at most 500 us)
before publishing their bit. ios/IOSPassiveLockGate.h is compiled as the Core
has it; the policy block and resolve_mode are copied verbatim; the 569
preimages come from the authenticated reverse fixture. Host behaviour only:
no iPhone FPS, frame time or scheduling result is inferred.
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

NATIVE = ROOT / 'test/native'
BASE = '92ea4ef0b19ec841a25667f5915d336b606ff0f9'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell571.diff'
VM = 'rpcs3/Emu/Memory/vm.cpp'
GATE = 'rpcs3/ios/IOSPassiveLockGate.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG = 'rpcs3/Emu/system_config.h'
TYPES = 'rpcs3/Emu/system_config_types.h'
MODIFIED = {VM, CONFIG, POLICY, POLICY_H, SETTINGS}
INPUTS = ['test/rpcs3_cell571_test.py', 'test/native/rpcs3_passive_gate571.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))
POLICY_START = '\t// CELL571_PASSIVE_LOCK_FAIRNESS: Automatic is every title.'
POLICY_END = 'rpcs3::ios::passive_gate::enabled.store(resolved.passive_lock_fairness, std::memory_order_relaxed);\n'
PASSIVE = 'void passive_lock(cpu_thread& cpu)'
WRITER = 'writer_lock::writer_lock(u32 const addr, atomic_t<u64, 128>* range_lock, u32 const size, u64 const flags) noexcept'
MARK = '\t\t\t// CELL571_PASSIVE_LOCK_FAIRNESS: a long wait asks new writers to let this one through.\n\t\t\trpcs3::ios::passive_gate::waiter_mark fairness;\n'
ON_WAIT = '\t\t\t\t\tfairness.on_timed_wait(episode.waits);\n'
DEFER = ('#ifdef RPCS3_IOS\n\t\t// CELL571_PASSIVE_LOCK_FAIRNESS: let a starving passive locker through before\n'
         '\t\t// publishing this lock (bounded; ios/IOSPassiveLockGate.h).\n\t\tif (range_lock)\n\t\t{\n'
         '\t\t\trpcs3::ios::passive_gate::defer_writer();\n\t\t}\n#endif\n\n')
INCLUDE = '#include "ios/IOSPassiveLockGate.h"\n'


def authenticated_baseline(source, work):
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell571']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell571' not in old_manifest and 'cell569' in old_manifest
    assert record['codegen'] == old_manifest['cell569']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == [GATE] and set(record['modified_paths']) == MODIFIED
    before = work / 'before'
    for path in MODIFIED | {GATE}:
        assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    assert not (before / GATE).exists()
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | {GATE}
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': BASE, 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'],
                    'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(MODIFIED)}


def between(text, start, end):
    assert text.count(start) == 1, start
    a = text.index(start)
    return text[a:text.index(end, a) + len(end)]


def experiment(source, work, sanitizer, optimize='-O1', timing=False):
    template = (NATIVE / 'rpcs3_passive_gate571.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    extra = ['-DRPCS3_IOS=1'] + (['-DCELL571_TIMING_CHECKS=1'] if timing else [])
    report, digest = build_and_run(work, 'passive_gate571', prelude + main, source, sanitizer, extra=extra, optimize=optimize)
    assert report['on']['starved'] == 0, report
    return dict(report, harnessSHA256=digest)


def placement_contract(source, before):
    """The waiter marks itself inside the iOS episode of passive_lock and after each timed
    wait; only range-lock writers defer, before the acquisition loop; every other line of
    vm.cpp is the 569 one; the policy, setting and log field are wired."""
    vm, old_vm = (source / VM).read_text(), (before / VM).read_text()
    passive = braced(vm, PASSIVE)
    assert passive.count(MARK) == 1 and passive.index('} episode;') < passive.index(MARK)
    assert passive.count(ON_WAIT) == 1 and passive.index('++episode.waits;') < passive.index(ON_WAIT)
    assert passive.index(ON_WAIT) < passive.index('#endif', passive.index(ON_WAIT))
    writer = braced(vm, WRITER)
    assert writer.count(DEFER) == 1 and writer.index(DEFER) < writer.index('for (u64 i = 0;; i++)')
    assert writer.index('source = static_cast<u8>(g_tls_writer_lock_source);') < writer.index(DEFER)
    stripped = vm.replace(MARK, '', 1).replace(ON_WAIT, '', 1).replace(DEFER, '', 1).replace(INCLUDE, '', 1)
    assert stripped == old_vm, 'vm.cpp changed beyond the 571 blocks'
    config = (source / CONFIG).read_text()
    assert 'passive_lock_fairness{ this, "Passive Lock Fairness", ios_experimental_mode::automatic };' in config
    assert (source / SETTINGS).read_text().count('SETTING("experimental.passive_lock_fairness"') == 1
    policy = (source / POLICY).read_text()
    assert 'rsx_thread_priority=%d passive_fairness=%d' in policy and '#include "IOSPassiveLockGate.h"' in policy
    assert 'bool passive_lock_fairness = false;' in (source / POLICY_H).read_text()
    return {'waiterMarkedInIosEpisode': True, 'onlyRangeLockWritersDefer': True, 'vmCppOtherwiseIdentical': True,
            'settingAndLogWired': True}


def policy_modes(source, work):
    """The policy block, verbatim: Automatic and Enabled turn the gate on, Disabled off."""
    policy = (source / POLICY).read_text()
    block = between(policy, POLICY_START, POLICY_END)
    code = (
        '#include <cstdio>\n#include "ios/IOSPassiveLockGate.h"\n'
        + braced((source / TYPES).read_text(), 'enum class ios_experimental_mode') + ';\n'
        + braced(policy, 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept') + '\n'
        + 'struct { struct { ios_experimental_mode passive_lock_fairness; } ios_experimental; } g_cfg;\n'
        + 'int main() { int ok = 1;\n'
        + ' for (auto mode : {ios_experimental_mode::automatic, ios_experimental_mode::enabled, ios_experimental_mode::disabled}) {\n'
        + '  g_cfg.ios_experimental.passive_lock_fairness = mode; struct { bool passive_lock_fairness = false; } resolved;\n'
        + block + '\n'
        + '  const bool on = mode != ios_experimental_mode::disabled;\n'
        + '  ok &= resolved.passive_lock_fairness == on && rpcs3::ios::passive_gate::enabled.load() == on; }\n'
        + ' std::printf("{\\"passed\\": %s, \\"modes\\": 3}\\n", ok ? "true" : "false"); return ok ? 0 : 1; }\n')
    report, digest = build_and_run(work, 'policy571', code, source, 'address,undefined', extra=['-DRPCS3_IOS=1'])
    return dict(report, harnessSHA256=digest)


def codegen_identity(source):
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell571']['codegen'] == manifest['cell569']['codegen']
    return {'identities': manifest['cell571']['codegen'], 'unchangedFrom569': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 571, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'placement': placement_contract(source, before), 'policy': policy_modes(source, work)}
        result['experiment'] = {name: experiment(source, work, flag) for name, flag in SANITIZERS}
        result['hostTiming'] = experiment(source, work, '', optimize='-O2', timing=True)
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host model of the 571 gate with the production header and the vm.cpp lock timings; '
                        'no iPhone FPS, frame time or scheduling result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
