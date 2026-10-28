#!/usr/bin/env python3
"""Source-bound 579 host checks: SPURS reservation_op fatal error, writer deferral that sleeps, PPU spin timing, RSX idle park for every title.

Build 575 logs. God of War III (BCES00510): the first boot of the process ended
in 2 of 2 cases on "vm::writer_lock is being used without cpu_flag::wait set
by the caller!" in cellSpursRemoveWorkload: vm::reservation_op, called by the
SPURS HLE functions on a PPU thread, takes the full writer lock while that
thread holds its passive lock without cpu_flag::wait. 579 sets the flag around
the lock and leaves through test_stopped(), as ppu_store_reservation does
(CELL579_RESERVATION_OP_WAIT). Call of Duty: Black Ops II (BLES01717): the 571
fairness gate made heavy PUTLLC spin up to 500 us while a PPU waiter starved;
its waiters averaged 25-31 timed waits per episode and in PUTLLC storms about
5 s per 5 s window went before the writers published their bits. A deferring
writer now spins at most 50 us and sleeps for the rest; the last starving
waiter wakes one writer and each woken writer the next (CELL579_GATE_SLEEP).
Every title on the A18 Pro's 1 GHz counter: busy_wait(n) is (n / 100) ticks,
so the PPU wait loops (passive_lock, seven lv2 primitives) spun about 1 us
instead of 6.7-8.3 us before sleeping (Dragon Ball Z: 825 passive-lock
episodes of 38 us per window); spin_ns gives them the 3 GHz durations upstream
wrote, rounded up so 24 MHz counters keep their tick counts (CELL579_SPIN_NS).
RSX idle park becomes Automatic for every title (CELL579_IDLE_PARK_ALL).

The production code is extracted from the materialized Core and compiled in
host models (the 575 text reproduces the fatal error; the 575 and 579 gate
headers run in the same threaded model). Off iOS every touched file is the 575
one. No iPhone FPS, frame time or memory result is inferred.
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
from rpcs3_cell559_test import braced, build_and_run, compilers, normalized_sha, sha, without_ios_blocks

BASE = 'ddf734206dfc5aee950c1538f13d13b5532bbb93'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell579.diff'
VM = 'rpcs3/Emu/Memory/vm.cpp'
VM_LOCKING = 'rpcs3/Emu/Memory/vm_locking.h'
VM_RESERVATION = 'rpcs3/Emu/Memory/vm_reservation.h'
GATE = 'rpcs3/ios/IOSPassiveLockGate.h'
ASM = 'rpcs3/util/asm.hpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
LV2_SPINS = {'sys_semaphore.cpp': 1, 'sys_lwmutex.cpp': 1, 'sys_event.cpp': 1, 'sys_cond.cpp': 1, 'sys_lwcond.cpp': 1,
             'sys_event_flag.cpp': 1, 'sys_mutex.cpp': 2}
MODIFIED = {VM, VM_LOCKING, VM_RESERVATION, GATE, ASM, POLICY, SETTINGS} | {'rpcs3/Emu/Cell/lv2/' + n for n in LV2_SPINS}
INPUTS = ['test/rpcs3_cell579_test.py']


def full_base():
    return subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip()


def authenticated_baseline(source, work):
    """The 575 preimages, from the materialized Core and the authenticated reverse fixture."""
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell579']
    assert record['baseline'] == full_base()
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', full_base() + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell579' not in old_manifest and 'cell575' in old_manifest
    assert record['codegen'] == old_manifest['cell575']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == [] and set(record['modified_paths']) == MODIFIED
    before = work / 'before'
    for path in MODIFIED:
        assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    upstream_files = sorted(MODIFIED - set(old_manifest['files_sha256']))
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest, path
        if path in old_manifest['files_sha256']:
            assert old_manifest['files_sha256'][path] == digest, path
        else:
            # First change to an upstream file: its preimage is the XITRIX source.
            upstream = subprocess.check_output(['git', 'show', old_manifest['upstream_commit'] + ':' + path], cwd=source)
            assert sha(upstream.replace(b'\r\n', b'\n')) == digest, path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | MODIFIED
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': full_base(), 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'], 'upstreamPreimages': upstream_files,
                    'otherCoreSourcesUnchanged': len(set(old_manifest['files_sha256']) - MODIFIED)}


def codegen_identity(source):
    """No PPU or SPU codegen source changes: the 575 object caches stay valid."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell579']['codegen'] == manifest['cell575']['codegen']
    return {'identities': manifest['cell579']['codegen'], 'unchangedFrom575': True, 'coldCompileRequiredByThisChange': False}


RESERVATION_HARNESS = r"""
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <type_traits>

using u8 = std::uint8_t; using u32 = std::uint32_t; using u64 = std::uint64_t;
#define SAFE_BUFFERS(...) __VA_ARGS__
constexpr u64 umax = ~u64{0};

enum class thread_class : u32 { general, ppu, spu };
enum class cpu_flag : u32 { wait = 1, memory = 2 };
struct cpu_state
{
	u32 bits = 0;
	bool operator&(cpu_flag f) const { return bits & static_cast<u32>(f); }
	cpu_state& operator+=(cpu_flag f) { bits |= static_cast<u32>(f); return *this; }
	cpu_state& operator-=(cpu_flag f) { bits &= ~static_cast<u32>(f); return *this; }
	explicit operator bool() const { return bits != 0; }
};

struct cpu_thread;
static thread_local cpu_thread* g_current = nullptr;
static int g_check_state_calls = 0;

namespace vm { static thread_local void* g_tls_locked = nullptr; }

struct cpu_thread
{
	thread_class cls = thread_class::ppu;
	cpu_state state;
	thread_class get_class() const { return cls; }
	// cpu_thread::check_state(): leaves the wait state; with cpu_flag::memory it
	// takes the passive lock again (vm::passive_lock).
	bool check_state() noexcept
	{
		g_check_state_calls++;
		if (state & cpu_flag::memory) { static int slot; vm::g_tls_locked = &slot; }
		state -= cpu_flag::memory;
		state -= cpu_flag::wait;
		return false;
	}
	[[nodiscard]] bool test_stopped() { return state ? check_state() : false; }
	static cpu_thread* get_current() noexcept { return g_current; }
};

static int g_fatal = 0, g_locks = 0, g_wait_while_locked = 0, g_notifies = 0;
namespace fmt { template <typename... Args> void throw_exception(const char*, Args&&...) { g_fatal++; } }

namespace vm
{
	template <typename T, typename AT> struct _ptr_base { AT m_addr; AT addr() const { return m_addr; } };
	alignas(128) static u8 g_memory[4096];
	template <typename T> T* get_super_ptr(u32 addr) { return reinterpret_cast<T*>(g_memory + addr); }
	static std::atomic<u64> g_res[32];
	inline std::atomic<u64>& reservation_acquire(u32 addr) { return g_res[addr / 128]; }
	// Production: one fetch_op that succeeds unless the line is unique-locked; while it
	// is (g_contended), the loop runs check_state() for a thread with pending flags.
	static bool g_contended = false;
	inline void reservation_shared_lock_internal(std::atomic<u64>& res)
	{
		if (auto cpu = cpu_thread::get_current(); g_contended && cpu && cpu->state) cpu->check_state();
		res += 1;
	}
	inline void reservation_notifier_notify(u32, u64) { g_notifies++; }
	enum class writer_lock_source : u8 { other, reservation_op };
	struct writer_lock_tag { explicit writer_lock_tag(writer_lock_source) {} };
	struct writer_lock
	{
		explicit writer_lock(u32)
		{
@CHECK@
			g_locks++;
			if (cpu_thread* cpu = cpu_thread::get_current(); cpu && cpu->state & cpu_flag::wait) g_wait_while_locked++;
		}
	};

@PRODUCTION@
}

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); failures++; } } while (0)

struct line128 { alignas(128) u64 words[16]; };

int main()
{
	const vm::_ptr_base<line128, u32> line{256};
	auto& res = vm::reservation_acquire(256);
	auto* data = vm::get_super_ptr<line128>(256);
	int scenarios = 0;
	struct { thread_class cls; bool locked, waiting, memory, none; } cases[] = {
		{thread_class::ppu, true, false, false, false},     // GoW3 cellSpursRemoveWorkload: passive lock held, no wait
		{thread_class::ppu, true, false, true, false},      // cpu_flag::memory pending as well
		{thread_class::ppu, true, true, false, false},      // the caller already waits
		{thread_class::ppu, false, false, false, false},    // no passive lock: the writer lock never objected
		{thread_class::spu, true, false, false, false},     // SPU caller (cellSpursSpu.cpp)
		{thread_class::general, false, false, false, true}, // not a CPU thread
	};
	for (const bool contended : {false, true})
	for (const auto& c : cases)
	{
		for (int kind = 0; kind < 3; kind++)
		{
			cpu_thread thread; thread.cls = c.cls;
			if (c.waiting) thread.state += cpu_flag::wait;
			if (c.memory) thread.state += cpu_flag::memory;
			static int slot;
			vm::g_tls_locked = c.locked ? &slot : nullptr;
			vm::g_contended = contended;
			g_current = c.none ? nullptr : &thread;
			// What the shared lock leaves: a contended wait runs check_state(), which clears both flags.
			const bool shared_check = contended && !c.none && (c.waiting || c.memory);
			const bool waiting_after_shared = c.waiting && !shared_check;
			const int fatal = g_fatal, locks = g_locks, waits = g_wait_while_locked, checks = g_check_state_calls;
			const u64 before = res.load();
			const u64 word = data->words[3];
			bool returned = false;
			if (kind == 0)
				vm::reservation_op<true>(thread, line, [](line128& l) { l.words[3]++; });
			else
				returned = vm::reservation_op<true>(thread, line, [kind](line128& l) { if (kind == 1) { l.words[3]++; return true; } return false; });
			const bool success = kind != 2;
			CHECK(g_locks == locks + 1);
			CHECK(data->words[3] == word + (success ? 1 : 0));
			CHECK(res.load() == before + (success ? 128 : 0));
			if (kind) CHECK(returned == success);
#ifndef MODEL_575
			CHECK(g_fatal == fatal);
			// The writer lock always sees cpu_flag::wait on a PPU that holds its passive lock.
			if (c.cls == thread_class::ppu && c.locked) CHECK(g_wait_while_locked == waits + 1);
			// The flag is added only where the writer lock objected, and leaves through test_stopped():
			// the thread ends as the shared lock left it.
			const bool added = c.cls == thread_class::ppu && c.locked && !waiting_after_shared;
			CHECK((thread.state & cpu_flag::wait) == waiting_after_shared);
			CHECK(g_check_state_calls == checks + (shared_check ? 1 : 0) + (added ? 1 : 0));
			if (!added) CHECK(g_wait_while_locked == waits + (waiting_after_shared ? 1 : 0));
#else
			static_cast<void>(fatal); static_cast<void>(waits); static_cast<void>(checks); static_cast<void>(waiting_after_shared);
#endif
			scenarios++;
		}
	}
	std::printf("{\"passed\": %s, \"scenarios\": %d, \"fatal\": %d, \"locks\": %d, \"notifies\": %d}\n",
		failures ? "false" : "true", scenarios, g_fatal, g_locks, g_notifies);
	return failures ? 1 : 0;
}
"""

RESERVATION_OP_START = '\ttemplate <bool Ack = false, typename CPU, typename T, typename AT = u32, typename F>\n\tinline SAFE_BUFFERS(auto) reservation_op(CPU& /*cpu*/, _ptr_base<T, AT> ptr, F op)\n'
WRITER_CHECK_START = '\t\tif (cpu_thread* cpu = cpu_thread::get_current(); cpu && cpu->get_class() == thread_class::ppu)\n'


def reservation_harness(vm_text, reservation_text, with_fix):
    """The production writer_lock check and reservation_op in the model; with_fix adds the 579 helpers."""
    check = braced(vm_text, WRITER_CHECK_START)
    assert 'fmt::throw_exception("vm::writer_lock is being used without cpu_flag::wait set by the caller!' in check
    functions = [braced(reservation_text, RESERVATION_OP_START)]
    if with_fix:
        functions = [braced(vm_text, '\tcpu_thread* writer_lock_wait_begin() noexcept\n'),
                     braced(vm_text, '\tvoid writer_lock_wait_end(cpu_thread* cpu) noexcept\n')] + functions
    return RESERVATION_HARNESS.replace('@CHECK@', check).replace('@PRODUCTION@', '\n'.join(functions))


def reservation_op_wait(work, source, before):
    """CELL579_RESERVATION_OP_WAIT: the 575 reservation_op trips the writer_lock check
    in the model (the God of War III cellSpursRemoveWorkload fatal error); the 579 one
    never does, applies the op and leaves the thread's wait state as it found it."""
    vm_text, reservation = (source / VM).read_text(), (source / VM_RESERVATION).read_text()
    locking = (source / VM_LOCKING).read_text()
    assert 'cpu_thread* writer_lock_wait_begin() noexcept;' in locking and 'void writer_lock_wait_end(cpu_thread* cpu) noexcept;' in locking
    op = braced(reservation, RESERVATION_OP_START)
    # Both branches: begin after the shared lock and before the writer lock; end after its scope, before the notify.
    assert op.count('cpu_thread* const waiting = vm::writer_lock_wait_begin();') == 2
    assert op.count('vm::writer_lock_wait_end(waiting);') == 2
    shared = op.index('reservation_shared_lock_internal(res);')
    for a in range(2):
        begin = [i for i in range(len(op)) if op.startswith('vm::writer_lock_wait_begin()', i)][a]
        lock = op.index('vm::writer_lock lock(addr);', begin)
        end = op.index('vm::writer_lock_wait_end(waiting);', lock)
        assert shared < begin < lock < end < op.index('reservation_notifier_notify', end)
    # Off iOS reservation_op is the upstream one.
    assert without_ios_blocks(op) == without_ios_blocks(braced((before / VM_RESERVATION).read_text(), RESERVATION_OP_START))
    old = reservation_harness((before / VM).read_text(), (before / VM_RESERVATION).read_text(), False)
    new = reservation_harness(vm_text, reservation, True)
    # The 575 text reproduces the fatal error wherever the writer lock objects: a PPU
    # holding its passive lock without cpu_flag::wait (cases 1-2 always, case 3 when a
    # contended shared lock cleared its flag), 3 ops each; the ops still apply.
    reproduced, _ = build_and_run(work, 'reservation575', old, before, 'address,undefined', extra=['-DRPCS3_IOS=1', '-DMODEL_575'])
    assert reproduced['fatal'] == 15 and reproduced['scenarios'] == 36, reproduced
    results = {}
    for sanitizer in ('address,undefined', 'thread'):
        report, harness = build_and_run(work, 'reservation579', new, source, sanitizer, extra=['-DRPCS3_IOS=1'])
        results[sanitizer] = report
    assert results['address,undefined']['fatal'] == 0 and results['address,undefined']['scenarios'] == 36
    return dict(results['address,undefined'], tsan=results['thread']['passed'], fatalWith575=reproduced['fatal'], harnessSHA256=harness)


GATE_HARNESS = r"""
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <thread>
#include <vector>
#include <pthread.h>

#include "ios/IOSPassiveLockGate.h"

using clock_type = std::chrono::steady_clock;
namespace gate = rpcs3::ios::passive_gate;

static double thread_cpu_us()
{
	timespec ts{};
	clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
	return ts.tv_sec * 1e6 + ts.tv_nsec / 1e3;
}

static void spin_for(std::chrono::nanoseconds d)
{
	const auto stop = clock_type::now() + d;
	while (clock_type::now() < stop) {}
}

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

// One deferral against a mark held `hold`: wall and CPU time of the writer.
struct deferral { double wall_us, cpu_us; bool deferred; };
static deferral defer_against(std::chrono::microseconds hold)
{
	std::atomic<bool> marked{false}, started{false};
	std::thread waiter([&]
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(gate::starving_after);
		marked = true;
		// The hold counts from the writer's start.
		while (!started.load()) {}
		spin_for(hold);
	});
	while (!marked.load()) {}
	started = true;
	const auto t0 = clock_type::now();
	const double c0 = thread_cpu_us();
	const bool deferred = gate::defer_writer();
	const double cpu = thread_cpu_us() - c0;
	const double wall = std::chrono::duration<double, std::micro>(clock_type::now() - t0).count();
	waiter.join();
	return {wall, cpu, deferred};
}

int main()
{
	gate::enabled.store(true);
	// 571 semantics: the mark is counted once and released on exit.
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(1);
		CHECK(!mark.marked() && gate::starving.load() == 0);
		mark.on_timed_wait(gate::starving_after);
		CHECK(mark.marked() && gate::starving.load() == 1);
	}
	CHECK(gate::starving.load() == 0 && !gate::defer_writer());

	// A mark that outlives the bound: the writer still proceeds after writer_deferral.
	double bound_cpu = 0, bound_wall = 0;
	{
		gate::waiter_mark mark;
		mark.on_timed_wait(gate::starving_after);
		const auto t0 = clock_type::now();
		const double c0 = thread_cpu_us();
		CHECK(gate::defer_writer());
		bound_cpu = thread_cpu_us() - c0;
		bound_wall = std::chrono::duration<double, std::micro>(clock_type::now() - t0).count();
		CHECK(bound_wall >= 500.0 && bound_wall < 50000.0);
	}

	// A waiter that leaves after 200 us: the writer returns with it, whatever it was doing.
	// A trial counts when the writer found the mark (a preempted writer may start after it left).
	double early_wall = 1e9, early_cpu = 0;
	int deferred_trials = 0;
	for (int i = 0; i < 20; i++)
	{
		const auto d = defer_against(std::chrono::microseconds(200));
		if (!d.deferred) continue;
		deferred_trials++;
		early_wall = std::min(early_wall, d.wall_us);
		early_cpu = std::max(early_cpu, d.cpu_us);
	}
	CHECK(deferred_trials >= 10);
	CHECK(early_wall >= 150.0 && early_wall < 500.0);

	// Oversubscription: more deferring writers than cores and one waiter that starves on and off.
	const unsigned cores = std::max(2u, std::thread::hardware_concurrency());
	const int writers = static_cast<int>(cores) + 2;
	std::atomic<bool> stop{false};
	std::atomic<std::uint64_t> ops{0};
	std::vector<double> cpu(writers, 0.0);
	std::vector<std::thread> pool;
	for (int w = 0; w < writers; w++)
	{
		pool.emplace_back([&, w]
		{
			const double c0 = thread_cpu_us();
			while (!stop.load(std::memory_order_relaxed))
			{
				if (!gate::defer_writer()) std::this_thread::yield();
				ops.fetch_add(1, std::memory_order_relaxed);
			}
			cpu[w] = thread_cpu_us() - c0;
		});
	}
	const auto run_begin = clock_type::now();
	double episodes_ms = 0;
	for (int e = 0; e < 200; e++)
	{
		const auto b = clock_type::now();
		{
			gate::waiter_mark mark;
			mark.on_timed_wait(gate::starving_after);
			spin_for(std::chrono::microseconds(300));
		}
		episodes_ms += std::chrono::duration<double, std::milli>(clock_type::now() - b).count();
		std::this_thread::sleep_for(std::chrono::microseconds(200));
	}
	const double wall_ms = std::chrono::duration<double, std::milli>(clock_type::now() - run_begin).count();
	stop = true;
	for (auto& t : pool) t.join();
	double writer_cpu_ms = 0;
	for (double c : cpu) writer_cpu_ms += c / 1000.0;
	CHECK(gate::starving.load() == 0);
	CHECK(ops.load() > 0);

	std::printf("{\"passed\": %s, \"boundWallUs\": %.1f, \"boundCpuUs\": %.1f, \"earlyReturnWallUs\": %.1f, \"earlyReturnMaxCpuUs\": %.1f, "
		"\"deferredTrials\": %d, \"writers\": %d, \"cores\": %u, \"oversubscribedWallMs\": %.1f, \"writerCpuMs\": %.1f, \"writerCpuShare\": %.3f, \"episodesMs\": %.1f}\n",
		failures ? "false" : "true", bound_wall, bound_cpu, early_wall, early_cpu, deferred_trials, writers, cores, wall_ms, writer_cpu_ms,
		writer_cpu_ms / (wall_ms * writers), episodes_ms);
	return failures ? 1 : 0;
}
"""


def gate_sleep(work, source, before):
    """CELL579_GATE_SLEEP: the production gate header (575 and 579) in a threaded model.
    A deferring writer spins at most writer_spin and sleeps for the rest: its CPU time for
    a full 500 us deferral falls to about the spin, it returns as soon as the last starving
    waiter leaves, and the 571 mark semantics and the 500 us bound are unchanged."""
    header = (source / GATE).read_text()
    assert 'constexpr std::chrono::microseconds writer_spin{50};' in header
    assert 'constexpr std::chrono::microseconds writer_deferral{500};' in header
    assert 'constexpr std::uint64_t starving_after = 2;' in header
    assert header.count('CELL579_GATE_SLEEP') >= 3
    # vm.cpp calls the gate exactly as in 575.
    vm, old_vm = (source / VM).read_text(), (before / VM).read_text()
    for call in ('rpcs3::ios::passive_gate::defer_writer();', 'rpcs3::ios::passive_gate::waiter_mark fairness;', 'fairness.on_timed_wait(episode.waits);'):
        assert vm.count(call) == old_vm.count(call) == 1, call
    results = {}
    for label, tree in (('575', before), ('579', source)):
        report, digest = build_and_run(work, 'gate' + label, GATE_HARNESS, tree, 'address,undefined', extra=['-DRPCS3_IOS=1'], optimize='-O2')
        results[label] = report
    tsan, _ = build_and_run(work, 'gate579', GATE_HARNESS, source, 'thread', extra=['-DRPCS3_IOS=1'], optimize='-O2')
    old, new = results['575'], results['579']
    # A full deferral: 575 spins it, 579 spins at most writer_spin (plus wake-up slack).
    assert old['boundCpuUs'] >= 300.0, old
    assert new['boundCpuUs'] <= 250.0 and new['boundCpuUs'] < old['boundCpuUs'] / 2, new
    # Oversubscribed (reported; shared runners move it): the deferring writers do not take more CPU.
    assert new['writerCpuShare'] <= old['writerCpuShare'] + 0.05, (old, new)
    return {'gate575': old, 'gate579': new, 'tsan': tsan['passed'], 'harnessSHA256': digest}


SPIN_HARNESS = r"""
#include <chrono>
#include <cstdint>
#include <cstdio>
using u64 = std::uint64_t;
@TICKS@
// busy_wait(n) on ARM64 with arm_timer_scale 1 (util/asm.hpp): (n / 100) ticks.
constexpr u64 busy_wait_ticks(u64 cycles) { return cycles / 100; }
// 24 MHz iPhones keep the tick counts busy_wait gives them today.
static_assert(spin_ns_ticks(67, 24'000'000) == busy_wait_ticks(200));
static_assert(spin_ns_ticks(100, 24'000'000) == busy_wait_ticks(300));
static_assert(spin_ns_ticks(167, 24'000'000) == busy_wait_ticks(500));
// The 1 GHz counter (A18 Pro) gets the 3 GHz durations upstream wrote: 67, 100 and 167 ns.
static_assert(spin_ns_ticks(67, 1'000'000'000) == 67 && busy_wait_ticks(200) == 2);
static_assert(spin_ns_ticks(100, 1'000'000'000) == 100 && busy_wait_ticks(300) == 3);
static_assert(spin_ns_ticks(167, 1'000'000'000) == 167 && busy_wait_ticks(500) == 5);
// Other counters: never zero, never below the requested time.
static_assert(spin_ns_ticks(1, 24'000'000) == 1 && spin_ns_ticks(0, 1'000'000'000) == 1);
static_assert(spin_ns_ticks(167, 19'200'000) == 4 && spin_ns_ticks(10'000, 1'000'000'000) == 10'000);
int main()
{
	bool ok = true;
	for (u64 f : {19'200'000ull, 24'000'000ull, 1'000'000'000ull})
		for (u64 ns = 1; ns <= 20'000; ns++)
			ok &= spin_ns_ticks(ns, f) * 1'000'000'000 >= ns * f && (spin_ns_ticks(ns, f) - 1) * 1'000'000'000 < ns * f + 1'000'000'000;
	std::printf("{\"passed\": %s, \"lv2Spin1GHzUs\": %.2f, \"lv2Spin24MHzUs\": %.2f, \"passiveSpin1GHzUs\": %.2f, \"passiveSpin24MHzUs\": %.2f}\n",
		ok ? "true" : "false", 50 * spin_ns_ticks(167, 1'000'000'000) / 1000.0, 50 * spin_ns_ticks(167, 24'000'000) / 24.0,
		100 * spin_ns_ticks(67, 1'000'000'000) / 1000.0, 100 * spin_ns_ticks(67, 24'000'000) / 24.0);
	return ok ? 0 : 1;
}
"""


def spin_timing(work, source, before):
    """CELL579_SPIN_NS: the tick conversion compiled from util/asm.hpp; every call site is
    an iOS branch whose #else is the 575 busy_wait, so other platforms compile the 575 text."""
    asm = (source / ASM).read_text()
    ticks = braced(asm, '\tconstexpr u64 spin_ns_ticks(u64 ns, u64 frequency)\n')
    spin = braced(asm, '\tinline void spin_ns(u64 ns)\n')
    assert 'spin_ns_ticks(ns, frequency)' in spin and 'mrs %0, cntfrq_el0' in spin
    assert without_ios_blocks(asm) == without_ios_blocks((before / ASM).read_text())
    sites = 0
    for name, count in LV2_SPINS.items():
        path = 'rpcs3/Emu/Cell/lv2/' + name
        now, old = (source / path).read_text(), (before / path).read_text()
        assert now.count('CELL579_SPIN_NS') == count, name
        # Off iOS the file is the 575 one, byte for byte.
        assert without_ios_blocks(now) == without_ios_blocks(old), name
        assert now.count('utils::spin_ns(167);') + now.count('utils::spin_ns(100);') == count, name
        sites += count
    vm = (source / VM).read_text()
    passive = braced(vm, '\tvoid passive_lock(cpu_thread& cpu)\n')
    assert passive.count('utils::spin_ns(67);') == 1 and passive.count('busy_wait(200);') == 1
    assert without_ios_blocks(vm) == without_ios_blocks((before / VM).read_text())
    report, digest = build_and_run(work, 'spin579', SPIN_HARNESS.replace('@TICKS@', ticks.replace('\tconstexpr', 'constexpr')), source, 'address,undefined')
    return dict(report, sites=sites + 1, harnessSHA256=digest)


def policy_contract(source, before):
    """RSX idle park resolves Automatic to every title; off iOS the policy and settings files are unchanged."""
    policy = (source / POLICY).read_text()
    assert 'resolve_mode(g_cfg.ios_experimental.rsx_idle_park, true);' in policy and 'CELL579_IDLE_PARK_ALL' in policy
    settings = (source / SETTINGS).read_text()
    assert 'Applies with RSX FIFO Idle Wait set to Yield. Automatic enables it for every title; Disabled spins as before.' in settings
    old_settings = (before / SETTINGS).read_text()
    assert settings.replace('Automatic enables it for every title; Disabled spins as before.',
                            'Automatic enables it for Dragon Ball Z Budokai HD Collection, God of War III and Bladestorm; Disabled spins as before.') == old_settings
    return {'rsxIdleParkAutomatic': 'every title (FIFO idle wait Yield)'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell579-') as temporary:
        work = Path(temporary)
        before, contract = authenticated_baseline(source, work)
        result = {
            'passed': False, 'build': 579, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
            'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
            'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
        }
        result['reservationOpWait'] = reservation_op_wait(work, source, before)
        result['gateSleep'] = gate_sleep(work, source, before)
        result['spinTiming'] = spin_timing(work, source, before)
        result['policy'] = policy_contract(source, before)
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
        result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                      scope='The 579 production code compiled in host models; no iPhone FPS, frame time or memory result.')
    text = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
