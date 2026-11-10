#!/usr/bin/env python3
"""REWINDBOX_CORE610_LR: an armed reservation loss interrupts a WRCH blocked on a full MFC queue.

The open LR follow-up of device601 (docs/evidence/rpcs3-device601-20261030/cpu/
lr-followup) showed that the delivered full-queue wait of process_mfc_cmd never
collects SPU_EVENT_LR. The candidate collects it on the owner, registers the
wait like SPU_RdEventStat (cache-line waiter, then reservation notifier), revalidates
the reservation generation and contents, and waits with RdEventStat's existing
host bound only while LR is armed (interrupts on, LR unmasked, reservation held,
materialized entry). Every other full-queue wait keeps its unbounded wait.

The program is generated from the frozen device601 LR probe (authenticated by
SHA-256), production bodies copied verbatim from the candidate tree, the
delivered prefix embedded in that probe (baseline) and the candidate prefix
extracted from the reviewed SPUThread.cpp. Adapters: clock, two guest windows and
a reservation table with production line aliasing, the kernel wait backend, the
CPU-state dispatcher, g_escape and the reservation wait-flag view. Six mutations
of the candidate text must each fail at least one check. No game, LLVM object,
Apple wait backend or iPhone executes here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from rpcs3_device597.cpu.run_late_snr import braced, prefix  # noqa: E402

PROBE = ROOT / 'docs/evidence/rpcs3-device601-20261030/cpu/lr-followup/lr-probe.cpp'
PROBE_SHA = 'd9715a6a07106e643d42ff2d8a21eca52e991610ab419eeea3edee341661d02a'
TESTS = ROOT / 'test/native/rpcs3_spu_mfc_lr/tests.inc'
CPP = 'rpcs3/Emu/Cell/SPUThread.cpp'
BASELINE_SHA = '84cd797c8ebd47211f97ca1bb78af6c5dd71410530aa563b08bed39545852309'
CANDIDATE_SHA = '97da453d7717a1a63cd44f58d6ae1b6c0053f1f7e3a1c1626e90c83c1cfd518d'
CORE627_SHA = 'd03e51eef50cb89fdb0c5d32484e40e400f7f6baf6d8e2155c7be1b472a309a5'
CORE911_SHA = 'c59a24dd44e7fee377a56f32d1e3114658649f33c04d54fe09f737ac3cb94da4'
CORE912_SHA = 'c7f903e345e1577dbb141a2584b1dc71bd179817bf491e785c9114d7b4dd6195'
CORE914_SHA = 'a1b9099f2424779aa60b9401f265e556a5073115d568f7781852128ac6d44187'
CORE916_SHA = '19b239a1c264c5e4c65c3dfe47148474e73fcbd68f2efa5f69e7ed33afc79245'
WAIT_FLAG = '*utils::bless<atomic_t<u32>>(&wait_var->raw().wait_flag)'
TAIL_MARK = '\n++accepted;switch(ch_mfc_cmd.cmd){'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError(f'expected one occurrence ({text.count(old)}): {old[:80]!r}')
    return text.replace(old, new, 1)


def between(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a:text.index(end, a) + len(end)]


NOTIFIER_START = '\t\t\tif (auto [wait_var, flag_val] = vm::reservation_notifier_begin_wait(raddr, rtime); wait_var)\n'
NOTIFIER_END = '\t\t\t\tvm::reservation_notifier_end_wait(*wait_var);\n\t\t\t}\n'
MUTATIONS = {
    'no_materialization_guard': [('const bool lr_armed = wait_for_events && raddr && !unsavable && (ch_events.load().mask & SPU_EVENT_LR);',
                                  'const bool lr_armed = wait_for_events && raddr && (ch_events.load().mask & SPU_EVENT_LR);')],
    'no_owner_collection': [('\t\tif (lr_armed)\n\t\t{\n\t\t\tget_events(SPU_EVENT_LR);\n\t\t}\n', '')],
    'no_revalidation': [('\t\t\t\tif (!reservation_check(raddr, rdata))\n', '')],
    'no_bound': [('#ifdef __linux__\n\t\t\t\t\t50\n#else\n\t\t\t\t\t100\n#endif\n', '\t\t\t\t\tumax\n')],
    'unconditional_bound': [('\t\telse\n\t\t{\n\t\t\tthread_ctrl::wait_on(state, old);\n\t\t}\n',
                             '\t\telse\n\t\t{\n\t\t\tthread_ctrl::wait_on(state, old, 100);\n\t\t}\n')],
    'no_notifier': [(None, '\t\t\tthread_ctrl::wait_on(state, old, 100);\n')],
}


def without_core627(raw: bytes) -> bytes:
    """Core 627 changes SPUThread.cpp outside process_mfc_cmd (do_putllc, one include, one thread_local).
    The reviewed increment is taken out first, so the contract below stays the exact one it was."""
    if sha(raw) != CORE627_SHA:
        return raw
    increment = json.loads((ROOT / 'build-utils/rpcs3/core627-delta.json').read_text())['increment_from_core624']
    with tempfile.TemporaryDirectory(prefix='lr-core627-') as temporary:
        folder = Path(temporary)
        target = folder / CPP
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        subprocess.run(['git', 'init', '-q'], cwd=folder, check=True)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', '--include=' + CPP, str(ROOT / increment['patch'])], cwd=folder, check=True)
        return target.read_bytes()


def without_core911(raw: bytes) -> bytes:
    """Core 911 changes SPUThread.cpp again inside do_putllc only (REWINDBOX_SPU_NOOP_SPIN_ACCURATE_911). The reviewed
    increment is taken out first and must give back the exact Core 627 file."""
    if sha(raw) != CORE911_SHA:
        return raw
    increment = json.loads((ROOT / 'build-utils/rpcs3/core911-delta.json').read_text())['increment_from_core910']
    with tempfile.TemporaryDirectory(prefix='lr-core911-') as temporary:
        folder = Path(temporary)
        target = folder / CPP
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        subprocess.run(['git', 'init', '-q'], cwd=folder, check=True)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', '--include=' + CPP, str(ROOT / increment['patch'])], cwd=folder, check=True)
        result = target.read_bytes()
    if sha(result) != CORE627_SHA:
        raise AssertionError('SPUThread.cpp without the Core 911 increment is not the Core 627 file')
    return result


def without_core912(raw: bytes) -> bytes:
    """Core 912 changes SPUThread.cpp inside do_putllc and adds one include (REWINDBOX_CAPTURE_912). The reviewed
    increment is taken out first and must give back the exact Core 911 file."""
    if sha(raw) != CORE912_SHA:
        return raw
    increment = json.loads((ROOT / 'build-utils/rpcs3/core912-delta.json').read_text())['increment_from_core911']
    with tempfile.TemporaryDirectory(prefix='lr-core912-') as temporary:
        folder = Path(temporary)
        target = folder / CPP
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        subprocess.run(['git', 'init', '-q'], cwd=folder, check=True)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', '--include=' + CPP, str(ROOT / increment['patch'])], cwd=folder, check=True)
        result = target.read_bytes()
    if sha(result) != CORE911_SHA:
        raise AssertionError('SPUThread.cpp without the Core 912 increment is not the Core 911 file')
    return result


def without_core914(raw: bytes) -> bytes:
    """Core 914 changes SPUThread.cpp inside do_putllc (REWINDBOX_CAPTURE_914). The reviewed
    increment is taken out first and must give back the exact Core 912 file."""
    if sha(raw) != CORE914_SHA:
        return raw
    increment = json.loads((ROOT / 'build-utils/rpcs3/core914-delta.json').read_text())['increment_from_core912']
    with tempfile.TemporaryDirectory(prefix='lr-core914-') as temporary:
        folder = Path(temporary)
        target = folder / CPP
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        subprocess.run(['git', 'init', '-q'], cwd=folder, check=True)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', '--include=' + CPP, str(ROOT / increment['patch'])], cwd=folder, check=True)
        result = target.read_bytes()
    if sha(result) != CORE912_SHA:
        raise AssertionError('SPUThread.cpp without the Core 914 increment is not the Core 912 file')
    return result


def without_core916(raw: bytes) -> bytes:
    """Core 916 changes SPUThread.cpp inside do_putllc and adds one include (REWINDBOX_SPURS_RELAXED_STORE_916). The
    reviewed increment is taken out first and must give back the exact Core 914 file."""
    if sha(raw) != CORE916_SHA:
        return raw
    increment = json.loads((ROOT / 'build-utils/rpcs3/core916-delta.json').read_text())['increment_from_core914']
    with tempfile.TemporaryDirectory(prefix='lr-core916-') as temporary:
        folder = Path(temporary)
        target = folder / CPP
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        subprocess.run(['git', 'init', '-q'], cwd=folder, check=True)
        subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', '--include=' + CPP, str(ROOT / increment['patch'])], cwd=folder, check=True)
        result = target.read_bytes()
    if sha(result) != CORE914_SHA:
        raise AssertionError('SPUThread.cpp without the Core 916 increment is not the Core 914 file')
    return result


def contract(source: Path, baseline: Path) -> dict:
    old_raw, new_raw = (baseline / CPP).read_bytes(), without_core627(without_core911(without_core912(without_core914(without_core916((source / CPP).read_bytes())))))
    if sha(old_raw) != BASELINE_SHA or sha(new_raw) != CANDIDATE_SHA:
        raise AssertionError('SPUThread.cpp is not the delivered/reviewed pair covered by the exact cache alias')
    old, new = old_raw.decode(), new_raw.decode()
    # Only process_mfc_cmd changes, and inside it only the full-queue prefix.
    method_old, method_new = braced(old, 'bool spu_thread::process_mfc_cmd()'), braced(new, 'bool spu_thread::process_mfc_cmd()')
    if new.replace(method_new, method_old, 1) != old:
        raise AssertionError('SPUThread.cpp changes outside process_mfc_cmd')
    if method_new.replace(prefix(new), prefix(old), 1) != method_old:
        raise AssertionError('process_mfc_cmd changes outside its full-queue prefix')
    probe = PROBE.read_text()
    if sha(PROBE.read_bytes()) != PROBE_SHA:
        raise AssertionError('frozen device601 LR probe changed')
    after = probe[probe.index('namespace after {'):]
    if prefix(old) not in after:
        raise AssertionError('the probe baseline is not the delivered full-queue prefix')
    added = prefix(new)
    for needle in ('get_events(SPU_EVENT_LR);', 'register_cache_line_waiter(raddr)', 'deregister_cache_line_waiter(cache_line_waiter_index);',
                   'vm::reservation_notifier_begin_wait(raddr, rtime)', 'vm::reservation_notifier_end_wait(*wait_var);',
                   'if (!reservation_check(raddr, rdata))', WAIT_FLAG, '#ifdef __linux__\n\t\t\t\t\t50\n#else\n\t\t\t\t\t100\n#endif',
                   'thread_ctrl::wait_on(state, old);'):
        if added.count(needle) != 1:
            raise AssertionError('candidate prefix element missing or duplicated: ' + needle)
    # The bound is SPU_RdEventStat's literal pair (50 us on Linux, 100 us elsewhere).
    rdeventstat = braced(new, 'u32 spu_thread::get_ch_value(u32 ch)') if 'u32 spu_thread::get_ch_value(u32 ch)' in new else new
    if 'atomic_wait_timeout{50\'000}' not in rdeventstat or 'atomic_wait_timeout{100\'000}' not in rdeventstat:
        raise AssertionError('RdEventStat bounds changed; the candidate bound no longer matches them')
    if unarmed_projection(added) != prefix(old):
        raise AssertionError('removing the LR-armed statements does not give back the delivered prefix')
    return {'baseline_sha256': BASELINE_SHA, 'candidate_sha256': CANDIDATE_SHA, 'probe_sha256': PROBE_SHA,
            'only_full_queue_prefix_changed': True, 'baseline_prefix_sha256': sha(prefix(old).encode()),
            'candidate_prefix_sha256': sha(added.encode()),
            # With lr_armed false (LR masked, interrupts off, no reservation or an unsavable
            # entry) the candidate executes exactly the delivered statements; the delivered
            # decrementer/SNR harness results therefore still describe those paths.
            'unarmed_projection_equals_delivered_prefix': True}


def unarmed_projection(candidate: str) -> str:
    """Delete exactly the statements reachable only when lr_armed is true."""
    a = candidate.index('\t\t// [LR] A held reservation')
    b = candidate.index('\t\tif (check_mfc_interrupts(pc))')
    text = candidate[:a] + candidate[b:]
    wait_else = '\t\telse\n\t\t{\n\t\t\tthread_ctrl::wait_on(state, old);\n\t\t}\n\n'
    a = text.index('\t\t[[maybe_unused]] bool lr_bound_only = false;\n')
    b = text.index(wait_else)
    text = text[:a] + '\t\tthread_ctrl::wait_on(state, old);\n' + text[b + len(wait_else):]
    return once(text, '\t\t// [LR] A bare bound expiry is not progress: keep the producer row in\n'
                      '\t\t// mfc_blocked so blocked_since_us and the stall reporter stay meaningful.\n'
                      '\t\tif (trace_full_queue && !lr_bound_only)', '\t\tif (trace_full_queue)')


def generate(source: Path, mutation: str | None) -> str:
    spu = (source / CPP).read_text()
    vmr = (source / 'rpcs3/Emu/Memory/vm_reservation.h').read_text()
    vmc = (source / 'rpcs3/Emu/Memory/vm.cpp').read_text()
    probe = PROBE.read_text()
    prelude = probe[:probe.index('namespace before {')]
    after_ns = probe[probe.index('namespace after {'):probe.index('// Controlled timer callbacks')]
    end_mark = 'default: assert(false);return false;} }'
    tail = after_ns[after_ns.index(TAIL_MARK):]
    tail = tail[:tail.index(end_mark) + len(end_mark)]

    # Adapters (explicit): value access for the waiter view and the kernel wait backend.
    prelude = once(prelude, 'template<class T> struct atomic_t {',
                   'template<class T, std::size_t Align = 0> struct atomic_t {\n    T& raw(){return value;}\n    void store(T next){release(next);}')
    old_wait = prelude[prelude.index('    void wait(atomic_wait_timeout timeout){'):prelude.index('};\n}\nstruct thread_ctrl')]
    new_wait = r'''    void wait(atomic_wait_timeout timeout){
        // Adapter: the kernel wait backend. Infinite waits keep the probe semantics
        // (WouldBlock when nothing changed); a bounded wait models one expiry of the
        // host bound. Neither path sets a guest event or touches guest state.
        const bool bounded = timeout.value != umax;
        if (bounded) { ++g_stats.bounded_waits; g_stats.last_bound_ns = timeout.value; } else ++g_stats.infinite_waits;
        if (on_wait_entry) on_wait_entry(bounded);
        if(before_list_wait){auto f=std::move(before_list_wait);before_list_wait={};f();}
        auto ready=[&]{for(auto& f:changed)if(f&&f())return true;return false;};
        if(!concurrent_wait){
            if(ready()){ ++g_stats.ready_wakes; return; }
            if(!bounded) throw WouldBlock{};
            ++g_stats.bound_expiries;
            if(on_bound_expiry) on_bound_expiry();
            return;
        }
        std::unique_lock guard(wait_mutex);list_entered.store(true,std::memory_order_release);wait_cv.notify_all();
        if(!bounded){
            // This deadline is solely a test watchdog, not candidate code.
            if(!wait_cv.wait_for(guard,std::chrono::seconds(2),ready)) { ++g_stats.watchdog; throw WouldBlock{}; }
            ++g_stats.ready_wakes; return;
        }
        if(wait_cv.wait_for(guard,std::chrono::nanoseconds(timeout.value),ready)) ++g_stats.ready_wakes; else ++g_stats.bound_expiries;
    }
'''
    prelude = prelude.replace(old_wait, new_wait, 1)
    prelude = once(prelude, 'std::atomic<bool> list_entered{};', '''std::atomic<bool> list_entered{};
struct Stats{std::atomic<u64> bounded_waits{},infinite_waits{},bound_expiries{},ready_wakes{},watchdog{},last_bound_ns{};
    void reset(){bounded_waits=0;infinite_waits=0;bound_expiries=0;ready_wakes=0;watchdog=0;last_bound_ns=0;}} g_stats;
std::function<void()> on_bound_expiry;
std::function<void(bool)> on_wait_entry;''')
    rdata_fence = spu[spu.index('// Bracket reservation snapshots'):spu.index('#if defined(ARCH_X64)\nstatic FORCE_INLINE void mov_rdata_avx')]
    waiter = vmr[vmr.index('\tstruct alignas(8) reservation_waiter_t'):vmr.index('\tatomic_t<u32>* reservation_notifier_notify(u32 raddr, u64 rtime, bool postpone = false);')]
    notify = braced(vmc, 'atomic_t<u32>* reservation_notifier_notify(u32 raddr, u64 rtime, bool postpone)')
    prelude += r'''
#include <cstring>
#define FORCE_INLINE inline
inline void atomic_fence_acquire(){std::atomic_thread_fence(std::memory_order_acquire);}
using spu_rdata_t = std::byte[128];
// Adapter: cmp_rdata/compute_rdata_hash32 are vectorized per architecture in
// production; only equality and a stable 32-bit line hash matter here.
inline bool cmp_rdata(const spu_rdata_t& a, const spu_rdata_t& b){return std::memcmp(a,b,128)==0;}
inline u32 compute_rdata_hash32(const spu_rdata_t& s){u32 h=0;for(int i=0;i<128;i+=4){u32 w;std::memcpy(&w,s+i,4);h=h*31+w;}return h;}
''' + rdata_fence + r'''
namespace vm {
	enum : u64 { rsrv_lock_mask = 127, rsrv_unique_lock = 64, rsrv_putunc_flag = 32 };
	enum range_lock_flags : u64 { range_writable = 4ull << 61, range_readable = 2ull << 61, range_full_mask = 7ull << 61,
		range_locked = 4ull << 61, range_allocation = 0, range_pos = 61 };
	enum page_info_t : u8 { page_readable = 1, page_writable = 2, page_64k_size = 1 << 5, page_1m_size = 1 << 6 };
	// Adapter guest memory: two 64 KiB windows (main memory and an RSX-context-like window).
	alignas(128) inline std::byte g_main[0x10000]; alignas(128) inline std::byte g_rsx[0x10000];
	inline std::byte* host(u32 addr){ if((addr>>16)==0x0001) return g_main+(addr&0xffff); if((addr>>16)==0x6030) return g_rsx+(addr&0xffff); return nullptr; }
	inline bool check_addr(u64 addr, u8 = page_readable, u32 = 1){ return host(static_cast<u32>(addr)) != nullptr; }
	template<class T> T* get_super_ptr(u32 addr){ return reinterpret_cast<T*>(host(addr)); }
	template<class T> T& _ref(u32 addr){ return *reinterpret_cast<T*>(host(addr)); }
	// Adapter reservation table, same line aliasing as g_reservations + (addr & 0xff80) / 2.
	inline atomic_t<u64> g_res_table[512];
	inline atomic_t<u64>& reservation_acquire(u32 addr){ return g_res_table[(addr & 0xff80) >> 7]; }
	inline atomic_t<u64, 128> g_range_lock_set[64]{};
	inline u64 g_shmem[0x10000]{};
''' + waiter + '''
	atomic_t<u32>* reservation_notifier_notify(u32 raddr, u64 rtime, bool postpone = false);
	std::array<atomic_t<reservation_waiter_t, 128>, 1024> g_resrv_waiters_count;
''' + notify + '''
	inline u32 total_waiters(){u32 n=0;for(auto& w:g_resrv_waiters_count)n+=w.load().waiters_count;return n;}
}
struct waiter_flag_view { atomic_t<vm::reservation_waiter_t,128>* owner; u32 load() const { return owner->load().wait_flag; } };
// Adapter for the production expression *utils::bless<atomic_t<u32>>(&wait_var->raw().wait_flag).
#define RBX_RESERVATION_WAIT_FLAG(wait_var) (*rbx_flag_view(wait_var))
inline waiter_flag_view* rbx_flag_view(atomic_t<vm::reservation_waiter_t,128>* w){ static thread_local waiter_flag_view v; v.owner=w; return &v; }
'''
    ns = after_ns.replace('namespace after {', 'namespace cand {', 1)
    ns = once(ns, 'u32 raddr{},rdata{};', 'u32 raddr{}; u64 rtime{}; alignas(64) std::byte rdata[128]{}; atomic_t<u64,128> own_range_lock; atomic_t<u64,128>* range_lock{&own_range_lock}; bool unsavable{};\n    static atomic_t<u64,128> g_spu_waiters_by_value[6];')
    ns = once(ns, '    bool reservation_lost{};bool reservation_check(u32&,u32&){return reservation_lost;}',
              '    bool reservation_check(u32 addr, const decltype(rdata)& data, u32 current_eal = 0) const;\n    usz register_cache_line_waiter(u32 addr);\n    void deregister_cache_line_waiter(usz index);')
    ns = once(ns, '    bool process_prefix();\n};', '    bool process_prefix();\n    bool process_prefix_baseline();\n};\natomic_t<u64,128> spu_thread::g_spu_waiters_by_value[6];')
    ns = once(ns, 'bool spu_thread::process_prefix(){', 'bool spu_thread::process_prefix_baseline(){')
    ns = once(ns, '    bool test_stopped(){\n', '    u64 loop_iterations{};\n    bool test_stopped(){\n        if(++loop_iterations > 4096) state += cpu_flag::stop; // test-only runaway guard\n')
    candidate = prefix(spu)
    candidate = once(candidate, WAIT_FLAG, 'RBX_RESERVATION_WAIT_FLAG(wait_var)')
    if mutation:
        for old, new in MUTATIONS[mutation]:
            if old is None:
                old = between(candidate, NOTIFIER_START, NOTIFIER_END)
            candidate = once(candidate, old, new)
    bodies = [braced(spu, 'bool spu_thread::reservation_check(u32 addr, const decltype(rdata)& data, u32 current_eal) const'),
              braced(spu, 'usz spu_thread::register_cache_line_waiter(u32 addr)'),
              braced(spu, 'void spu_thread::deregister_cache_line_waiter(usz index)'),
              'bool spu_thread::process_prefix(){' + candidate + tail]
    ns = ns.rstrip()
    if not ns.endswith('}'):
        raise AssertionError('unexpected probe namespace layout')
    return prelude + ns[:-1] + '\n' + '\n'.join(bodies) + '\n}\n' + TESTS.read_text()


def build_and_run(program: str, work: Path, name: str, cxx: str, sanitize: bool, deterministic_only: bool,
                  source: Path) -> dict:
    cpp = work / f'{name}.cpp'
    cpp.write_text(program)
    binary = work / name
    # The recorded probe command (lr-probe.json) with the tested tree's include path.
    flags = ['-std=c++20', '-O1', '-g', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-pthread', '-DRPCS3_IOS',
             f'-I{source / "rpcs3"}']
    if 'clang' in subprocess.check_output([cxx, '--version'], text=True):
        # The program inlines production headers (vm_reservation.h) into this main
        # file; clang, unlike in a real header, then reports their unused static
        # inline helpers. GCC never does. Every other warning stays an error.
        flags += ['-Wno-unused-function']
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    build = subprocess.run([cxx, *flags, str(cpp), '-o', str(binary)], capture_output=True, text=True)
    if build.returncode:
        raise AssertionError(f'{name} failed to compile: {build.stderr[-4000:]}')
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1')
    result = subprocess.run([str(binary)] + (['--deterministic-only'] if deterministic_only else []),
                            capture_output=True, text=True, timeout=600, env=env)
    checks = json.loads(result.stdout.strip().splitlines()[-1])
    return {'returncode': result.returncode, 'checks': checks, 'program_sha256': sha(program.encode()),
            'failed': sorted(k for k, v in checks.items() if not v), 'stderr_tail': result.stderr[-300:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='materialized candidate Core')
    parser.add_argument('--baseline', type=Path, required=True, help='materialized delivered Core (canonical 70d694bb)')
    parser.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--report', type=Path)
    parser.add_argument('--skip-sanitizers', action='store_true')
    args = parser.parse_args()
    report = {'schema': 1, 'contract': contract(args.source, args.baseline), 'host': platform.platform(),
              'compiler': subprocess.check_output([args.cxx, '--version'], text=True).splitlines()[0],
              'tests_inc_sha256': sha(TESTS.read_bytes())}
    with tempfile.TemporaryDirectory(prefix='rpcs3-lr-') as temp:
        work = Path(temp)
        candidate = build_and_run(generate(args.source, None), work, 'candidate', args.cxx, False, False, args.source)
        if candidate['returncode'] or candidate['failed'] or len(candidate['checks']) != 60:
            raise AssertionError(f'candidate checks failed: {candidate["failed"]} ({len(candidate["checks"])} checks)')
        report['candidate'] = {k: v for k, v in candidate.items() if k != 'checks'} | {'checks': len(candidate['checks'])}
        if not args.skip_sanitizers:
            asan = build_and_run(generate(args.source, None), work, 'candidate-asan', args.cxx, True, False, args.source)
            if asan['returncode'] or asan['failed']:
                raise AssertionError(f'ASan/UBSan candidate failed: {asan["failed"]} {asan["stderr_tail"]}')
            report['candidate_asan_ubsan'] = {'checks': len(asan['checks']), 'failed': asan['failed'],
                                              'leak_detection': 'disabled (not claimed)'}
        report['mutations'] = {}
        for name in MUTATIONS:
            mutant = build_and_run(generate(args.source, name), work, f'mut-{name}', args.cxx, False, True, args.source)
            if not mutant['failed']:
                raise AssertionError(f'mutation {name} was not rejected')
            report['mutations'][name] = {'rejected': True, 'failed_checks': mutant['failed']}
    report.update(result='passed', physicalDeviceTested=False, guestTimeoutAdded=False, labelForced=False,
                  limits=['Adapters stand in for the Apple wait backend, range-lock contention and LLVM entry paths.',
                          'Proves the host protocol of the candidate wait, not a God of War III fix.'])
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
