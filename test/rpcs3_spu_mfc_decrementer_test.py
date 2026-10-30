#!/usr/bin/env python3
"""Exercise expired decrementers while an unaccepted MFC WRCH waits on a full queue.

Extract real MFC drain, cpu_work, event collection, decrementer reading/arming,
IRQ entry, timer publication, notification latch, wait construction and IRET.
The clock, timer queue, VM, CPU-state dispatcher and native wait backend remain
explicit adapters. No game, LLVM translation or iOS kernel executes here.
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

from rpcs3_device597.cpu.run_late_snr import braced, prefix

ROOT = Path(__file__).resolve().parents[1]
CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
HEADER = 'rpcs3/Emu/Cell/SPUThread.h'
ADAPTER = ROOT / 'test/rpcs3_device597/cpu/late_snr.cpp.in'
MAIN = ROOT / 'test/native/rpcs3_spu_mfc_decrementer.inc'
sha = lambda data: hashlib.sha256(data).hexdigest()
METHODS = ['bool spu_thread::do_mfc(', 'u32 spu_thread::get_mfc_completed() const',
           'bool spu_thread::check_mfc_interrupts(', 'void spu_thread::push_snr(',
           'void spu_thread::set_events(', 'void spu_thread::cpu_work()',
           'spu_thread::ch_events_t spu_thread::get_events(',
           'std::pair<u32, u32> spu_thread::read_dec() const',
           'void spu_thread::cancel_dec_interrupt()', 'void spu_thread::arm_dec_interrupt()']


def generate(source, baseline, mutation=None):
    current = (source / CPP).read_text()
    original = (baseline / CPP).read_text()
    # The candidate changes two host bodies only. No translator or class layout
    # is rewritten by this proof. Codegen/cache identity is a separate gate.
    restored = current
    for signature in ['bool spu_thread::process_mfc_cmd()', 'struct spu_dec_intr_timer\n']:
        restored = restored.replace(braced(current, signature), braced(original, signature), 1)
    assert restored == original, 'Unreviewed SPUThread change beyond the two owner helpers'
    for method in METHODS:
        assert braced(current, method) == braced(original, method), method
    files = [HEADER, 'Utilities/Thread.h', 'Utilities/Thread.cpp',
             'rpcs3/Emu/CPU/CPUThread.h', 'rpcs3/Emu/CPU/CPUThread.cpp',
             'rpcs3/Emu/Cell/MFC.h', 'rpcs3/Emu/Cell/SPUInterpreter.cpp',
             'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp']
    for name in files:
        assert (source / name).read_bytes() == (baseline / name).read_bytes(), name
    head = (source / HEADER).read_text()
    thread = (source / 'Utilities/Thread.h').read_text()
    thread_cpp = (source / 'Utilities/Thread.cpp').read_text()
    cpu_cpp = (source / 'rpcs3/Emu/CPU/CPUThread.cpp').read_text()
    mfc = (source / 'rpcs3/Emu/Cell/MFC.h').read_text()
    interpreter = (source / 'rpcs3/Emu/Cell/SPUInterpreter.cpp').read_text()
    llvm = (source / 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp').read_text()
    code = ADAPTER.read_text().split('template<class T>void fixture', 1)[0]
    # Reproduce named_thread's actual two-parent lookup. The old fixture put a
    # notify() member on spu_thread itself, hiding the production ambiguity.
    cpu_adapter = braced(code, 'struct cpu_thread {') + ';'
    code = code.replace(cpu_adapter, 'struct cpu_thread;')
    cpu_adapter = cpu_adapter.replace('static cpu_thread* get_current(){return nullptr;}', '''
    static cpu_thread* get_current(){return nullptr;}
    thread_class get_class()const{return thread_class::spu;}
    void notify();''')
    code = code.replace('struct atomic_wait_timeout{', '''
enum class thread_class{ppu,spu,rsx};
template<class>struct result_storage{};
''' + thread[thread.index('template <class Context>\nclass named_thread final'):thread.index('{', thread.index('template <class Context>\nclass named_thread final'))] + '''{
    friend struct thread_ctrl;
public:
    thread_base& host_thread(){return *this;}
};
struct atomic_wait_timeout{''')
    code = code.replace('    @WAIT_CUSTOM@', '    ' + braced(thread, 'template <typename T>\n\tstatic void notify(') + '\n    @WAIT_CUSTOM@')
    code = code.replace('enum class cpu_flag:u32 {wait=1,stop=2,again=4};', '''
enum class cpu_flag:u32 {wait=1,stop=2,again=4,pending=8,pending_recheck=16,dbg_pause=32};
template<class T>using bs_t=u32;
u32 operator&(u32 v,cpu_flag b){return v&u32(b);}
u32 operator+(cpu_flag a,cpu_flag b){return u32(a)|u32(b);}
u32 operator-(u32 v,cpu_flag b){return v&~u32(b);}
u32& operator-=(u32&v,cpu_flag b){v&=~u32(b);return v;}
''')
    code = code.replace('struct CpuState:atomic_t<u32>{', '''struct CpuState:atomic_t<u32>{
    void operator+=(u32 bits){*this|=bits;}
''')
    code = code.replace('T exchange(T next)', 'atomic_t& operator=(T next){release(next);return *this;}\n    T fetch_add(T n){std::lock_guard guard(mutex);T old=value;value+=n;return old;}\n    T exchange(T next)')
    code = code.replace('u64 get_system_time(){return 1;}', '''
u64 clock_now=1;u64 get_system_time(){return clock_now;}u64 get_timebased_time(){return clock_now;}
void busy_wait(u64){}
namespace fmt{template<class...T>[[noreturn]]void throw_exception(T...){throw std::runtime_error("unexpected");}}
''')
    code = code.replace('struct {struct {u32 mfc_transfers_shuffling{};bool mfc_shuffling_in_steps{};}core;}g_cfg;', '''
struct {struct {u32 mfc_transfers_shuffling{},mfc_transfers_timeout{},clocks_scale{100};bool mfc_shuffling_in_steps{};}core;}g_cfg;
constexpr u32 SPU_EVENT_LR=0x400,SPU_EVENT_TM=0x20,SPU_EVENT_SN=2;
constexpr u32 SPU_EVENT_IMPLEMENTED=SPU_EVENT_LR|SPU_EVENT_TM|SPU_EVENT_SN|0x300;
constexpr u32 SPU_EVENT_INTR_BUSY_CHECK=SPU_EVENT_IMPLEMENTED&~SPU_EVENT_SN;
struct Logger{template<class...T>void error(T...){};}spu_log;
struct spu_dec_intr_timer;template<class T>class named_thread;
struct TimerQueue{u64 calls{},due{},token{};void arm(u64 d,u32,u64 t){++calls;due=d;token=t;}};
struct FixedObjects{template<class T>TimerQueue& get(){static TimerQueue queue;return queue;}}fixed_objects;
auto* g_fxo=&fixed_objects;
''')
    start = code.index('// @CLASS_BEGIN@\n')
    end = code.index('// @CLASS_END@\n') + len('// @CLASS_END@\n')
    cls = code[start:end].replace("// @CLASS_BEGIN@\n", "").replace("// @CLASS_END@\n", "")
    cls = cls.replace('    thread_base host;\n', '')
    cls = cls.replace('    void notify(){++notified;state.notify_one();host.notify();}\n', '')
    cls = cls.replace('bool test_stopped(){return is_stopped(state.load());}', '''
    // CPUThread::check_state boundary: pending invokes real cpu_work, then wait
    // is cleared before returning to the real full-queue loop. Suspend/debug
    // scheduling and the kernel wait implementation are outside this fixture.
    bool test_stopped(){
        if(state.load()&u32(cpu_flag::pending))cpu_work();
        state.atomic_op([](u32& s){s-=cpu_flag::wait;});
        return is_stopped(state.load());
    }''')
    cls = cls.replace('void cancel_dec_interrupt(){++interrupt_cancels;}', 'void cancel_dec_interrupt();')
    cls = cls.replace('u8* ls{};', '''u8* ls{};
    bool in_cpu_work{},allow_interrupts_in_cpu_work{},interrupt_requires_escape{},has_active_local_bps{};
    u32 cpu_work_iteration_count{},current_bp_pc{},raddr{},rdata{};
    std::array<u8,0x10000> local_breakpoints{};
    u32 ch_dec_value{};u64 ch_dec_start_timestamp{};bool is_dec_frozen{};
    u64 dec_intr_deadline{umax};atomic_t<u64> dec_intr_armed{};
    bool reservation_check(u32&,u32&){return false;}
    std::pair<u32,u32> read_dec()const;
    ch_events_t get_events(u64 mask_hint=0,bool waiting=false,bool reading=false);
    void arm_dec_interrupt();void cpu_work();
''')
    # get_events is tested only on TM here; no reservation memory is supplied.
    # Model umax's implicit narrowing explicitly in this adapter's PC sentinel.
    cls = cls.replace('u32 cpu_work_iteration_count{},current_bp_pc{},raddr{},rdata{};',
                      'u32 cpu_work_iteration_count{};u64 current_bp_pc{};u32 raddr{},rdata{};')
    code = code[:start] + code[end:]
    versions = ''
    body_hashes = {}
    for name, text in [('before', original), ('after', current)]:
        process_text = text
        timer_text = text
        if name == 'after' and mutation == 'omit-owner-collect':
            process_text = original
        if name == 'after' and mutation == 'omit-sticky-notify':
            timer_text = original
        if name == 'after' and mutation == 'ambiguous-notify':
            timer_text = timer_text.replace('spu->cpu_thread::notify();', 'spu->notify();')
        versions += 'namespace ' + name + ' {\n' + cpu_adapter + '\nstruct ppu_thread:cpu_thread{};\n' + cls + '\n'
        versions += braced(cpu_cpp, 'void cpu_thread::notify()') + '\n'
        versions += braced(text, 'static void ios_publish_mfc_snapshot(') + '\n'
        versions += '\n'.join(braced(text, method) for method in METHODS)
        dispatch = braced(text, 'bool spu_thread::process_mfc_cmd()')
        barrier = dispatch[dispatch.index('\tcase MFC_BARRIER_CMD:\n'):dispatch.index('\n\tdefault:', dispatch.index('\tcase MFC_BARRIER_CMD:\n'))]
        versions += '\nbool spu_thread::process_prefix(){' + prefix(process_text) + '\n++accepted;switch(ch_mfc_cmd.cmd){\n' + barrier + '\n default: assert(false);return false;} }\n'
        timer_publish = braced(braced(timer_text, 'struct spu_dec_intr_timer\n'), 'if (spu->dec_intr_armed.compare_and_swap_test(e.token, 0))')
        versions += '\nvoid publish_timer(named_thread<spu_thread>& target,u64 token){auto* spu=&target;struct{u64 token;}e{token};\n' + timer_publish + '\n}\n'
        versions += '''
struct spu_opcode_t{};
namespace spu_interpreter{
void set_interrupt_status(spu_thread& spu,spu_opcode_t){assert(!spu.interrupts_enabled);}
}
'''
        versions += braced(interpreter, 'bool IRET(spu_thread& spu, spu_opcode_t op)') + '\n'
        versions += braced(llvm, 'static void exec_list_unstall(') + '\n}\n'
        body_hashes[name] = dict(processPrefix=sha(prefix(process_text).encode()), timerPublication=sha(timer_publish.encode()),
                                methods={method: sha(braced(text, method).encode()) for method in METHODS})
    replacements = {
        '@MFC@': '\n'.join(braced(mfc, sig) + ';' for sig in ['enum MFC : u8', 'enum mfc_tag_update : u32', 'struct alignas(16) spu_mfc_cmd']),
        '@CHANNEL@': braced(head, 'struct spu_channel_op_state\n') + ';\n' + braced(head, 'struct alignas(16) spu_channel\n') + ';',
        '@NOTIFY@': braced(thread_cpp, 'void thread_base::notify()'),
        '@WAIT_CUSTOM@': braced(thread, 'template <uint Max, typename Func>'),
        '@WAIT_ON@': braced(thread, 'template <typename T, typename U>\n\tstatic inline void wait_on('),
        '@VERSIONS@': versions,
    }
    for token, body in replacements.items():
        assert code.count(token) == 1, token
        code = code.replace(token, body)
    assert '@' not in code
    code = '#include "ios/IOSSignalTrace.h"\n' + code + MAIN.read_text()
    return code, body_hashes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    p.add_argument('--sanitizer', choices=['address,undefined'])
    p.add_argument('--mutation', choices=['omit-owner-collect', 'omit-sticky-notify', 'ambiguous-notify'])
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    source, baseline = a.source.resolve(), a.baseline.resolve()
    program, hashes = generate(source, baseline, a.mutation)
    compiler = shlex.split(a.compiler)
    flags = ['-std=c++20', '-O1' if a.sanitizer else '-O3', '-g', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-pthread',
             '-DRPCS3_IOS', '-I' + str(source / 'rpcs3')]
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    if a.sanitizer:
        flags += ['-fsanitize=' + a.sanitizer, '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
        if platform.system() == 'Linux':
            flags += ['-fno-pie', '-no-pie']
    with tempfile.TemporaryDirectory(prefix='rpcs3-mfc-decrementer-') as temporary:
        cpp, executable = Path(temporary) / 'probe.cpp', Path(temporary) / 'probe'
        cpp.write_text(program)
        built = subprocess.run([*compiler, *flags, str(cpp), '-o', str(executable)],
                               capture_output=a.mutation == 'ambiguous-notify', text=True)
        if a.mutation == 'ambiguous-notify':
            report = dict(passed=built.returncode != 0 and 'ambiguous' in built.stderr,
                          mutation=a.mutation, mutationRejected=built.returncode != 0 and 'ambiguous' in built.stderr,
                          compilationReturncode=built.returncode, compilerDiagnostics=built.stderr,
                          generatedSHA256=sha(program.encode()), runnerSHA256=sha(Path(__file__).read_bytes()),
                          physicalDeviceTested=False, gameplayMeasured=False, native_program_executed=False)
            a.report.parent.mkdir(parents=True, exist_ok=True)
            a.report.write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report, indent=2))
            raise SystemExit(0 if report['passed'] else 1)
        built.check_returncode()
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=45,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
    report = dict(passed=run.returncode == 0, mutation=a.mutation, returncode=run.returncode, stderr=run.stderr,
                  sourceSHA256={name: sha((source / name).read_bytes()) for name in [CPP, HEADER, 'Utilities/Thread.h', 'Utilities/Thread.cpp', 'rpcs3/Emu/CPU/CPUThread.h', 'rpcs3/Emu/CPU/CPUThread.cpp', 'rpcs3/Emu/Cell/MFC.h', 'rpcs3/Emu/Cell/SPUInterpreter.cpp', 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp', 'rpcs3/ios/IOSSignalTrace.h']},
                  extractionHelperSHA256=sha((ROOT / 'test/rpcs3_device597/cpu/run_late_snr.py').read_bytes()),
                  baselineSHA256=sha((baseline / CPP).read_bytes()), bodySHA256=hashes,
                  runnerSHA256=sha(Path(__file__).read_bytes()), adapterSHA256=sha(ADAPTER.read_bytes()),
                  scenariosSHA256=sha(MAIN.read_bytes()), generatedSHA256=sha(program.encode()),
                  compiler=subprocess.check_output([*compiler, '--version'], text=True).splitlines()[0], flags=flags,
                  host=platform.machine(), sanitizer=a.sanitizer, physicalDeviceTested=False, gameplayMeasured=False,
                  cpuStateDispatcherAdapted=True, kernelWaitBackendExecuted=False, realDMATransfersTested=False,
                  clockAndTimerQueueAdapted=True, guestTimeoutAdded=False)
    assert (program, hashes) == generate(source, baseline, a.mutation), 'Sources changed during the test'
    if run.returncode == 0:
        report['results'] = json.loads(run.stdout)
    elif a.mutation:
        report['mutationRejected'] = 'expected_interrupt' in run.stderr
        report['passed'] = report['mutationRejected']
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
