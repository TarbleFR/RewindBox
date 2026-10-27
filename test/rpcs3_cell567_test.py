#!/usr/bin/env python3
"""Source-bound 567 host checks for the RSX thread priority on iOS.

The thread QoS header is compiled as the Core includes it; the policy block and
resolve_mode are copied verbatim from the 567 Core source; the 565 preimages
come from the authenticated reverse fixture. A pooled native worker is modelled
with the production mapping; on Apple hosts the real QoS calls are exercised
(lowered to utility, reset as a new job, raised). Results are host behaviour
only: no iPhone FPS, frame time, scheduling placement or thermal result is
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
from rpcs3_cell559_test import braced, build_and_run, compilers, normalized_sha, sha

NATIVE = ROOT / 'test/native'
BASE = 'f903a76e81317fe6801bc99f876d7548f23ec4b6'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell567.diff'
QOS = 'rpcs3/ios/IOSThreadQoS.h'
THREAD = 'Utilities/Thread.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG = 'rpcs3/Emu/system_config.h'
TYPES = 'rpcs3/Emu/system_config_types.h'
MODIFIED = {THREAD, CONFIG, POLICY, POLICY_H, SETTINGS}
INPUTS = ['test/rpcs3_cell567_test.py', 'test/native/rpcs3_thread_qos567.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))
POLICY_START = '\t// CELL567_THREAD_QOS: Automatic is every title.'
POLICY_END = 'resolved.rsx_thread_priority ? rpcs3::ios::thread_qos::lowered_relative_priority : 0, std::memory_order_relaxed);\n'


def authenticated_baseline(source, work):
    manifest_path = ROOT / 'build-utils/rpcs3/canonical-source.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = manifest['cell567']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell567' not in old_manifest and 'cell565' in old_manifest
    assert record['codegen'] == old_manifest['cell565']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == [QOS]
    assert set(record['modified_paths']) == MODIFIED, set(record['modified_paths']) ^ MODIFIED
    assert set(record['before_sha256']) == MODIFIED and set(record['after_sha256']) == MODIFIED | {QOS}
    before = work / 'before'
    for path in MODIFIED | {QOS}:
        current = source / path
        assert normalized_sha(current) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(current.read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    assert not (before / QOS).exists()
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | {QOS}
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': BASE, 'fixtureSHA256': sha(FIXTURE.read_bytes()),
                    'manifestSHA256': sha(manifest_path.read_bytes()), 'sourceSHA256': record['after_sha256'],
                    'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(MODIFIED)}


def between(text, start, end):
    assert text.count(start) == 1, start
    a = text.index(start)
    return text[a:text.index(end, a) + len(end)]


def experiment(source, work, sanitizer):
    policy = (source / POLICY).read_text()
    parts = {
        '//@ENUM@': braced((source / TYPES).read_text(), 'enum class ios_experimental_mode') + ';',
        '//@RESOLVE@': braced(policy, 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept'),
        '//@POLICY@': between(policy, POLICY_START, POLICY_END),
    }
    template = (NATIVE / 'rpcs3_thread_qos567.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    for marker, text in parts.items():
        assert prelude.count(marker) == 1, marker
        prelude = prelude.replace(marker, text)
    report, digest = build_and_run(work, 'thread_qos567', prelude + main, source, sanitizer, extra=['-DRPCS3_IOS=1'])
    assert report['modes'] == 3 and report['loweredRelativePriority'] == -2
    if platform.system() == 'Darwin':
        assert report['darwinKernelModes'] == 3, report
    return dict(report, harnessSHA256=digest)


def placement_contract(source, before):
    """The reset precedes every pooled job; the mapping is the only priority path;
    the callers' requests (RSX and audio +1, compilers and the shader-cache writer -1) are unchanged."""
    thread, old_thread = (source / THREAD).read_text(), (before / THREAD).read_text()
    run = braced(thread, 'void* ios_thread_worker::run(void* opaque) noexcept')
    assert run.index('thread_ctrl::set_native_priority(0);') < run.index('thread->entry_point(thread);')
    branch = between(thread, '#elif defined(RPCS3_IOS)\n\t// iOS schedules work through QoS classes.', '#else\n')
    assert 'rpcs3::ios::thread_qos::for_priority(priority)' in branch
    assert 'pthread_set_qos_class_self_np(qos, level.relative_priority)' in branch
    assert thread.count('#include "ios/IOSThreadQoS.h"') == 1
    # Everything else of Thread.cpp is the 565 file.
    stripped = thread.replace(braced(thread, 'void* ios_thread_worker::run(void* opaque) noexcept'),
                              braced(old_thread, 'void* ios_thread_worker::run(void* opaque) noexcept'))
    stripped = stripped.replace(branch, between(old_thread, '#elif defined(RPCS3_IOS)\n\t// iOS schedules work through QoS classes.', '#else\n'))
    stripped = stripped.replace('#include "ios/IOSThreadQoS.h"\n\n', '', 1)
    assert stripped == old_thread, 'Thread.cpp changed beyond the 567 blocks'
    for path, text in (('rpcs3/Emu/RSX/RSXThread.cpp', 'thread_ctrl::scoped_priority high_prio(+1);'),
                       ('rpcs3/Emu/Cell/Modules/cellAudio.cpp', 'thread_ctrl::scoped_priority high_prio(+1);'),
                       ('rpcs3/Emu/Cell/lv2/sys_rsxaudio.cpp', 'thread_ctrl::scoped_priority high_prio(+1);'),
                       ('rpcs3/Emu/RSX/rsx_cache.h', '[]() { thread_ctrl::set_native_priority(-1); }')):
        assert (source / path).read_text().count(text) == 1, path
    config = (source / CONFIG).read_text()
    assert 'rsx_thread_priority{ this, "RSX Thread Priority", ios_experimental_mode::automatic };' in config
    assert (source / SETTINGS).read_text().count('SETTING("experimental.rsx_thread_priority"') == 1
    assert 'rsx_thread_priority=%d' in (source / POLICY).read_text()
    return {'resetBeforeEveryJob': True, 'singleMappingPath': True, 'callersUnchanged': True,
            'threadCppOtherwiseIdentical': True}


def codegen_identity(source):
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell567']
    assert cache_identities(source) == record['codegen'] == manifest['cell565']['codegen']
    return {'identities': record['codegen'], 'unchangedFrom565': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 567, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'placement': placement_contract(source, before)}
        result['experiment'] = {name: experiment(source, work, flag) for name, flag in SANITIZERS}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host behaviour of the 567 production bodies: policy resolution, the priority mapping, the '
                        'reset of a reused worker (real QoS calls on Apple hosts); no iPhone FPS or scheduling result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
