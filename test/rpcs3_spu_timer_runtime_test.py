#!/usr/bin/env python3
"""Execute both production SPU decrementer timers with deterministic host edges.

The complete timer declaration, arm and worker bodies are extracted. Guest
time, wait scheduling, IDM retention and atomic publication have explicit
adapters. Two vector adapters count allocations/erases and inject allocation
failure without replacing the compaction algorithm. Timing separately executes
the production locked sweep on ordinary std::vectors and a host mutex.
No device timing, complete CPU scheduler or concurrent atomic ordering is tested.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile

from rpcs3_texture_address_index_test import braced

ROOT = Path(__file__).resolve().parents[1]
CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
CPU = 'rpcs3/Emu/CPU/CPUThread.h'
HEADER = 'rpcs3/Emu/Cell/SPUThread.h'
CONFIG = 'rpcs3/Emu/system_config.h'
SOURCE = (CPP,)
SUPPORT = (CPU, HEADER, CONFIG)
ADAPTER = ROOT / 'test/native/rpcs3_spu_timer_runtime.inc'
TIMER = 'struct spu_dec_intr_timer\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def timer(tree):
    return braced((Path(tree) / CPP).read_text(), TIMER)


def scope_proof(source, baseline):
    """All code except the clock mask and timer worker remains byte-identical."""
    source, baseline = Path(source), Path(baseline)
    old, new = ((tree / CPP).read_text() for tree in (baseline, source))
    normalized = []
    body_hashes = {}
    for label, text, tree in (('baseline', old, baseline), ('candidate', new, source)):
        declaration = timer(tree)
        worker = braced(declaration, 'void operator()()')
        mask = braced(text, 'auto get_exec_mask = [&size = mfc_size]')
        body_hashes[label] = dict(mask=sha(mask.encode()), timerWorker=sha(worker.encode()))
        replaced_timer = declaration.replace(worker, '@TIMER_WORKER@', 1)
        normalized.append(text.replace(declaration, replaced_timer, 1).replace(mask, '@MFC_MASK@', 1))
    assert normalized[0] == normalized[1], 'Change outside two reviewed host bodies'
    for path in SUPPORT:
        assert (source / path).read_bytes() == (baseline / path).read_bytes(), path
    return dict(onlyRuntimeBodiesChanged=True,
                unchangedTextSHA256=sha(normalized[0].encode()),
                changedBodies=body_hashes, unchangedTimerEntryAndMembers=True,
                unchangedSPUThreadLayout=True, unchangedCPUFlagDefinitions=True)


def program(tree, namespace):
    declaration = timer(tree)
    for old, new in (
            ('std::vector<entry> armed;', 'ArmedVector<entry> armed;'),
            ('std::vector<entry> due_entries;', 'DueVector<entry> due_entries;')):
        assert declaration.count(old) == 1, old
        declaration = declaration.replace(old, new)
    return ('namespace ' + namespace + ' {\n' + declaration + ';\n' +
            'static_assert(std::is_trivially_copyable_v<spu_dec_intr_timer::entry>);\n'
            'static_assert(std::is_nothrow_move_assignable_v<spu_dec_intr_timer::entry>);\n}\n')


def harness(source, baseline):
    scope_proof(source, baseline)
    code = ADAPTER.read_text()
    constants = braced((Path(source) / CPU).read_text(), 'enum class cpu_flag : u32') + ';\n'
    for token, replacement in (
            ('@FLAGS@', constants), ('@BEFORE@', program(baseline, 'before')),
            ('@AFTER@', program(source, 'after'))):
        assert code.count(token) == 1, token
        code = code.replace(token, replacement)
    assert '@' not in code
    return code


def timing_program(source, baseline):
    entry = braced(timer(source), 'struct entry\n') + ';\n'
    old_entry = braced(timer(baseline), 'struct entry\n') + ';\n'
    assert old_entry == entry
    code = '''#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <limits>
#include <mutex>
#include <vector>
using u32=std::uint32_t; using u64=std::uint64_t;
constexpr u64 umax=std::numeric_limits<u64>::max();
struct { struct { u32 clocks_scale{100}; } core; } g_cfg;
using shared_mutex=std::mutex;
''' + entry
    for label, tree in (('baseline', baseline), ('candidate', source)):
        sweep = braced(timer(tree), '\n\t\t\t{\n\t\t\t\tstd::lock_guard lock(mutex);')
        code += ('[[gnu::noinline]] u64 ' + label + '(std::vector<entry>& armed, std::vector<entry>& due_entries, u64 now) {\n'
                 'shared_mutex mutex; u64 sleep_us=umax;\n' + sweep + '\nreturn sleep_us;\n}\n')
    return code + '''
using Sweep=u64(*)(std::vector<entry>&,std::vector<entry>&,u64);
u64 sink{};
double measure(Sweep f,const std::vector<entry>& input,u32 iterations) {
    std::vector<entry> armed; armed.reserve(input.size());
    const auto start=std::chrono::steady_clock::now();
    for(u32 i=0;i<iterations;++i) {
        armed=input; std::vector<entry> due;
        sink+=f(armed,due,1000)+armed.size()+due.size();
    }
    return std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/iterations;
}
int main() {
    std::cout<<"{\\"samples\\":7,\\"cases\\":["; bool first=true;
    for(u32 count:{6u,32u,128u,1024u}) for(u32 pattern=0;pattern<3;++pattern) {
        std::vector<entry> input;
        for(u32 i=0;i<count;++i) input.push_back({pattern==0 || (pattern==1 && i%2==0)?1000u:2000u,i,u64{i}+1});
        const u32 iterations=std::max(64u,100000u/(count+1));
        std::array<double,7> old{},fresh{};
        for(u32 i=0;i<7;++i) {
            if(i%2) { fresh[i]=measure(candidate,input,iterations); old[i]=measure(baseline,input,iterations); }
            else { old[i]=measure(baseline,input,iterations); fresh[i]=measure(candidate,input,iterations); }
        }
        if(!first) std::cout<<',';
        first=false;
        std::cout<<"{\\"entries\\":"<<count<<",\\"pattern\\":\\""<<(pattern==0?"all_due":pattern==1?"alternating":"none_due")
            <<"\\",\\"iterationsPerSample\\":"<<iterations<<",\\"baselineNs\\":[";
        for(u32 i=0;i<7;++i) { if(i) std::cout<<','; std::cout<<old[i]; }
        std::cout<<"],\\"candidateNs\\":[";
        for(u32 i=0;i<7;++i) { if(i) std::cout<<','; std::cout<<fresh[i]; }
        std::sort(old.begin(),old.end()); std::sort(fresh.begin(),fresh.end());
        std::cout<<"],\\"baselineMedianNs\\":"<<old[3]<<",\\"candidateMedianNs\\":"<<fresh[3]<<'}';
    }
    std::cout<<"],\\"sink\\":"<<sink<<"}\\n";
}
'''


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    return dict(
        sourceSHA256={p: sha((source / p).read_bytes()) for p in SOURCE + SUPPORT},
        baselineSHA256={p: sha((baseline / p).read_bytes()) for p in SOURCE + SUPPORT},
        harnessSHA256=sha(harness(source, baseline).encode()),
        timingHarnessSHA256=sha(timing_program(source, baseline).encode()),
        adapterSHA256={str(ADAPTER.relative_to(ROOT)): sha(ADAPTER.read_bytes())},
        sourceScope=scope_proof(source, baseline))


def verify_counts(result):
    assert result['passed'] is True and result['assertionsActive'] is True
    assert result['matrixCases'] == 7 * 6 * 5
    assert result['reentrantCases'] == 1 and result['shutdownCases'] == 1
    assert result['firstAllocationFailureCases'] == 2
    assert result['baselineShiftedSlots'] > 0 and result['candidateShiftedSlots'] == 0
    assert result['baselineNonemptyErases'] > result['candidateNonemptyErases'] > 0
    assert result['baselineDueAllocations'] > result['candidateDueAllocations'] > 0
    assert result['callbacksWhileLocked'] == 0
    assert result['obsoleteTokensRejected'] > 0 and result['notifications'] > 0
    assert result['pendingOrderComparisons'] > 0 and result['waitDeadlineComparisons'] > 0
    assert result['reentrantRetainedUntilCallbackReturned'] is True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=('address,undefined',))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    identities = expected(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-pthread',
             '-O1' if args.sanitizer else '-O3']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    timing = None
    with tempfile.TemporaryDirectory(prefix='rpcs3-spu-timer-') as temporary:
        cpp, exe = Path(temporary) / 'test.cpp', Path(temporary) / 'test'
        cpp.write_text(harness(args.source, args.baseline))
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], text=True, capture_output=True, timeout=120, env=env)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        result = json.loads(run.stdout)
        verify_counts(result)
        if not args.sanitizer:
            cpp.write_text(timing_program(args.source, args.baseline))
            subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
            timing = json.loads(subprocess.check_output([str(exe)], text=True, timeout=60))
    assert identities == expected(args.source, args.baseline)
    report = dict(passed=True, assertionsActive=True, results=result,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer, **identities,
                  host=dict(system=platform.system(), machine=platform.machine()),
                  hostSweepTiming=timing, leakSanitizer=False, physicalDeviceTested=False,
                  gameplayMeasured=False, concurrentMemoryOrderingTested=False, scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
