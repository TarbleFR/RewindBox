#!/usr/bin/env python3
"""Source-bound 569 host checks: iOS threads keep their QoS (no affinity policy).

Build 567 logged `pthread_set_qos_class_self_np() failed: 1` (EPERM) 1486 times:
thread_ctrl::set_thread_affinity_mask applied THREAD_AFFINITY_POLICY, which iOS
does not support, and XNU's thread_policy_set() restores the QoS it removed
with the stored relative priority unnegated, so a thread at relative priority -2
stays opted out of QoS. The 569 iOS branch applies nothing. The 567 preimage
comes from the authenticated reverse fixture; the iOS branch is compiled as the
Core has it; on Apple hosts the real QoS calls are exercised. No iPhone FPS or
scheduling result is inferred.
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
BASE = '4801af965dd8855e0320591147610d2c28cc3b12'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell569.diff'
THREAD = 'Utilities/Thread.cpp'
MODIFIED = {THREAD}
INPUTS = ['test/rpcs3_cell569_test.py', 'test/native/rpcs3_qos_keep569.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))
AFFINITY = 'void thread_ctrl::set_thread_affinity_mask(u64 mask)'
IOS_START = '#elif defined(RPCS3_IOS)\n\t// CELL569_QOS_KEEP:'
IOS_END = '#elif __APPLE__\n'


def authenticated_baseline(source, work):
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell569']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell569' not in old_manifest and 'cell567' in old_manifest
    assert record['codegen'] == old_manifest['cell567']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == [] and set(record['modified_paths']) == MODIFIED
    before = work / 'before'
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
    return before, {'baseline': BASE, 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'],
                    'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(MODIFIED)}


def ios_branch(text):
    body = braced(text, AFFINITY)
    a = body.index(IOS_START)
    return body[a + len('#elif defined(RPCS3_IOS)\n'):body.index(IOS_END, a)]


def experiment(source, work, sanitizer):
    template = (NATIVE / 'rpcs3_qos_keep569.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    assert prelude.count('//@AFFINITY@') == 1
    prelude = prelude.replace('//@AFFINITY@', ios_branch((source / THREAD).read_text()))
    report, digest = build_and_run(work, 'qos_keep569', prelude + main, source, sanitizer, extra=['-DRPCS3_IOS=1'])
    if platform.system() == 'Darwin':
        assert report['darwinKernel'] == 1, report
    return dict(report, harnessSHA256=digest)


def placement_contract(source, before):
    """The iOS branch applies no thread policy; every other line of Thread.cpp is the 567 one;
    the callers (pooled job end, CPU and RSX threads, offloader) are unchanged."""
    thread, old_thread = (source / THREAD).read_text(), (before / THREAD).read_text()
    branch = ios_branch(thread)
    code = [line for line in branch.splitlines() if line.strip() and not line.strip().startswith('//')]
    assert code == [], code
    body = braced(thread, AFFINITY)
    assert body.index(IOS_START) < body.index(IOS_END) < body.index('thread_policy_set(mach_thread, THREAD_AFFINITY_POLICY')
    assert thread.replace('#elif defined(RPCS3_IOS)\n' + branch, '', 1) == old_thread, 'Thread.cpp changed beyond the 569 branch'
    assert 'thread_policy_set(' not in braced(thread, 'void thread_ctrl::set_native_priority(int priority)')
    callers = {'Utilities/Thread.cpp': 'thread_ctrl::set_thread_affinity_mask(0);',
               'rpcs3/Emu/CPU/CPUThread.cpp': 'thread_ctrl::set_thread_affinity_mask(thread_ctrl::get_affinity_mask(get_class()));',
               'rpcs3/Emu/RSX/RSXThread.cpp': 'thread_ctrl::set_thread_affinity_mask(thread_ctrl::get_affinity_mask(thread_class::rsx));',
               'rpcs3/Emu/RSX/RSXOffload.cpp': 'thread_ctrl::set_thread_affinity_mask(thread_ctrl::get_affinity_mask(thread_class::rsx));'}
    for path, text in callers.items():
        assert (source / path).read_text().count(text) == 1, path
    return {'iosBranchAppliesNoPolicy': True, 'threadCppOtherwiseIdentical': True, 'callersUnchanged': len(callers)}


def codegen_identity(source):
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell569']['codegen'] == manifest['cell567']['codegen']
    return {'identities': manifest['cell569']['codegen'], 'unchangedFrom567': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 569, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'placement': placement_contract(source, before)}
        result['experiment'] = {name: experiment(source, work, flag) for name, flag in SANITIZERS}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host behaviour of the 569 iOS affinity branch and the 567 QoS calls (real calls on Apple '
                        'hosts); no iPhone FPS or scheduling result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
