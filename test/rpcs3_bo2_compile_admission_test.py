#!/usr/bin/env python3
"""Reproduce the real compiler-admission missed notification without timing gates.

Extract the unchanged delivered constructor and both destructors. Real mutexes,
condition_variable_any and the production host budget execute; hooks impose the
release between failed acquisition and wait registration. Memory/profiling and
the host's asynchronous dispatch-source signal are explicit boundaries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
HEADER = 'rpcs3/ios/IOSCompileAdmission.h'
HOST = 'packages/neo_swap/ios/Classes/NeoSwapCompiler.mm'
HOST_HEADERS = ('packages/neo_swap/ios/Classes/NeoSwapCompilerAPI.h',
                'packages/neo_swap/ios/Classes/NeoSwapCompilerBudget.h')
ADAPTER = ROOT / 'test/native/rpcs3_bo2_compile_admission.inc'
CONSTRUCTOR = 'compile_admission::compile_admission('
DESTRUCTOR = 'compile_admission::~compile_admission()'
WAKE = 'void wake_compile_waiters() noexcept'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def braced(text, marker):
    start = text.index(marker)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def production(source, name):
    text = (source / SOURCE).read_text()
    cls = braced((source / HEADER).read_text(), 'class compile_admission') + ';'
    prefix = '''
std::atomic<const NeoSwapCompilerAPI*> compiler_api{nullptr};
boundary::mutex compiler_wait_mutex;
boundary::condition_variable compiler_wait_cv;
bool fallback_compiler_active = false;
std::atomic<u64> observed_compile_cost[32]{};
u64 available_process_memory_headroom() { return 8ull << 30; }
void sample_compiler_memory() {}
'''
    access = '''
struct access {
    using admission = compile_admission;
    static void set_api(const NeoSwapCompilerAPI* api) { compiler_api.store(api); }
    static auto& wait_mutex() { return compiler_wait_mutex; }
    static void wake() { wake_compile_waiters(); }
};
'''
    return ('namespace ' + name + ' {\n' + prefix + cls + '\n' +
            '\n'.join(braced(text, marker) for marker in (CONSTRUCTOR, DESTRUCTOR, WAKE)) + access + '}\n')


def harness(source, baseline, host):
    before = (baseline / SOURCE).read_text()
    after = (source / SOURCE).read_text()
    assert after.replace(braced(after, DESTRUCTOR), braced(before, DESTRUCTOR), 1) == before
    assert braced(before, DESTRUCTOR) != braced(after, DESTRUCTOR)
    assert (source / HEADER).read_bytes() == (baseline / HEADER).read_bytes()
    raw = host.read_bytes()
    blob = hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
    expected = subprocess.check_output(['git', 'rev-parse', 'HEAD:' + HOST], cwd=ROOT, text=True).strip()
    assert blob == expected, 'Host wrapper must match the committed production blob'
    callbacks = braced(raw.decode(), 'namespace {')
    code = ADAPTER.read_text()
    for marker, fragment in (('@HOST_CALLBACKS@', callbacks),
                             ('@BASELINE_PRODUCTION@', production(baseline, 'baseline')),
                             ('@CANDIDATE_PRODUCTION@', production(source, 'candidate'))):
        assert code.count(marker) == 1
        code = code.replace(marker, fragment)
    return code, blob


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--host-wrapper', type=Path, default=ROOT / HOST,
                        help='Optional authenticated sparse-checkout copy of the unchanged host wrapper.')
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--mode', choices=('plain', 'asan-ubsan', 'tsan'), default='plain')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    code, host_blob = harness(source, baseline, args.host_wrapper)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-O2', '-g', '-pthread', '-UNDEBUG']
    if args.mode != 'plain':
        flags += ['-fsanitize=' + ('address,undefined' if args.mode == 'asan-ubsan' else 'thread'),
                  '-fno-omit-frame-pointer']
        if sys.platform.startswith('linux'):
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1', TSAN_OPTIONS='halt_on_error=1')
    with tempfile.TemporaryDirectory(prefix='rpcs3-bo2-admission-') as temporary:
        work = Path(temporary)
        cpp, binary = work / 'admission.cpp', work / 'admission'
        cpp.write_text(code)
        subprocess.run(compiler + flags + ['-I', str(ROOT), str(cpp), '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60, env=env)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        result = json.loads(run.stdout)
    assert result['passed'] and result['assertionsActive']
    result.update(
        compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
        compilerFlags=flags, mode=args.mode, sourceSHA256=sha((source / SOURCE).read_bytes()),
        baselineSHA256=sha((baseline / SOURCE).read_bytes()), headerSHA256=sha((source / HEADER).read_bytes()),
        harnessSHA256=sha(code.encode()), adapterSHA256=sha(ADAPTER.read_bytes()),
        hostInputSHA256={HOST: sha(args.host_wrapper.read_bytes()),
                        **{path: sha((ROOT / path).read_bytes()) for path in HOST_HEADERS}},
        hostWrapperGitBlob=host_blob, onlyReleaseCriticalSectionChanged=True,
        baselineSourceMutationApplied=False, leakSanitizer=False,
        physicalDeviceTested=False, gameplayMeasured=False,
        scope='Exact admission constructor/destructor and host budget; controlled real mutex/CV interleaving. Memory sampling, diagnostics and asynchronous host signal are boundaries.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
