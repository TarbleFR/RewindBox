// ---------------------------------------------------------------- tests
// REWINDBOX_CORE610_LR: checks of the candidate full-MFC-queue wait, generated
// by test/rpcs3_spu_mfc_lr_test.py. Adapters: clock, guest memory/reservation
// table, kernel wait (condition variable or deterministic expiry), CPU-state
// dispatcher and g_escape (exception). Production bodies: do_mfc,
// check_mfc_interrupts, get_events, set_events, push_snr, cpu_work, decrementer
// arm/cancel/publish, reservation_check, cache-line waiter (de)registration, VM
// notifier begin/end/notify, thread_ctrl::wait_on_custom, the delivered
// full-queue prefix (baseline) and the candidate prefix extracted from the
// reviewed SPUThread.cpp.
#include <cstring>
#include <random>
#include <string>
#include <vector>
#include <cstdio>

using cand::spu_thread;
constexpr u32 WRCH_PC = 0x1240;

struct Check { std::string name; bool ok; };
std::vector<Check> g_checks;
static void check(const std::string& name, bool ok) { g_checks.push_back({name, ok}); }

static void reset_world()
{
	for (auto& r : vm::g_res_table) r.release(0);
	std::memset(vm::g_main, 0, sizeof(vm::g_main));
	std::memset(vm::g_rsx, 0, sizeof(vm::g_rsx));
	for (auto& w : vm::g_resrv_waiters_count) w.release({});
	for (auto& w : spu_thread::g_spu_waiters_by_value) w.release(0);
	g_stats.reset();
	on_bound_expiry = {}; on_wait_entry = {}; before_state_wait = {}; before_list_wait = {};
	concurrent_wait = false; list_entered = false; clock_now = 1;
}

static bool registrations_clear()
{
	for (auto& w : spu_thread::g_spu_waiters_by_value) if (w.load()) return false;
	return vm::total_waiters() == 0;
}

static void fixture(spu_thread& t, u32 mask, u32 raddr = 0x00010000)
{
	reset_world();
	rpcs3::ios::signal_trace::reset(100, true);
	spu_thread::ch_events_t events{}; events.mask = mask; t.ch_events.release(events);
	t.mfc_size = 16; for (u32 i = 0; i < 16; ++i) t.mfc_queue[i] = {MFC_PUT_CMD, u8(i), 16, 16 * i, 0x10000 + 16 * i, 0};
	t.mfc_queue[0].cmd = MFC_GETL_CMD; t.mfc_queue[0].tag |= 0x80; t.mfc_queue[1].cmd = MFC_BARRIER_CMD;
	t.ch_mfc_cmd = {MFC_SYNC_CMD, u8(31), 0, 0, 0x60300510, 0};
	t.ch_dec_value = 10; t.ch_dec_start_timestamp = 1; t.dec_intr_armed.release(1); t.dec_intr_deadline = 12;
	thread_ctrl::g_tls_this_thread = &t.host;
	if (raddr)
	{
		// A completed GETLLAR: line snapshot and generation.
		std::byte* line = vm::host(raddr);
		for (int i = 0; i < 128; i++) line[i] = std::byte(i ^ 0x5a);
		vm::reservation_acquire(raddr).release(0x1000);
		t.raddr = raddr; t.rtime = 0x1000; std::memcpy(t.rdata, line, 128);
	}
}

// Other-thread stores, as they exist in the Core (see analysis):
static void store_contents_no_notify(u32 a) { vm::host(a)[7] = std::byte(0xee); }          // PPU stw, RSX label, relaxed SPU PUT
static void bump_generation_no_notify(u32 a) { vm::reservation_acquire(a).fetch_add(128); }  // accurate SPU PUT, dcbz/STORE128 core
static void notifying_store(u32 a)                                                          // PUTLLC success / PPU stcx
{
	const u64 old = vm::reservation_acquire(a).load();
	vm::host(a)[9] = std::byte(0x11);
	vm::reservation_acquire(a).fetch_add(128);
	vm::reservation_notifier_notify(a, old);
}

struct Outcome { bool blocked{}, escaped{}, returned{}, result{}; u32 queue{}, accepted{}, return_pc{}, raddr{}, events{}; bool waiting{}, count{}; };
template <class F> static Outcome enter(spu_thread& t, F&& call)
{
	Outcome out;
	try { out.result = call(); out.returned = true; }
	catch (const Escaped&) { out.escaped = true; }
	catch (const WouldBlock&) { out.blocked = true; }
	before_state_wait = {}; before_list_wait = {};
	out.queue = t.mfc_size; out.accepted = t.accepted; out.return_pc = t.srr0; out.raddr = t.raddr;
	const auto ev = t.ch_events.load(); out.events = ev.events; out.waiting = ev.waiting; out.count = ev.count;
	return out;
}
static Outcome run_cand(spu_thread& t) { return enter(t, [&] { return t.process_prefix(); }); }
static Outcome run_base(spu_thread& t) { return enter(t, [&] { return t.process_prefix_baseline(); }); }
static bool irq_at_wrch(const Outcome& o, const spu_thread& t)
{
	// Handler entry: BR at LS 0 (0x30000100) targets 0x8; SRR0 keeps the unaccepted WRCH.
	return o.escaped && o.return_pc == WRCH_PC && o.accepted == 0 && o.queue == 16 && t.pc == 0x8;
}
static u64 expected_bound_ns()
{
#ifdef __linux__
	return 50'000;
#else
	return 100'000;
#endif
}

static void deterministic(const char* tag, u32 raddr)
{
	const std::string p = std::string(tag) + ".";
	// T1/T2: reservation already lost when the WRCH reaches the full queue.
	for (int kind = 0; kind < 2; ++kind)
	{
		const std::string k = kind ? "contents" : "generation";
		{
			spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
			kind ? store_contents_no_notify(raddr) : bump_generation_no_notify(raddr);
			auto o = run_base(t);
			check(p + "baseline_lost_" + k + "_blocks_without_irq", o.blocked && !o.escaped && !o.count && g_stats.infinite_waits == 1);
		}
		{
			spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
			kind ? store_contents_no_notify(raddr) : bump_generation_no_notify(raddr);
			auto o = run_cand(t);
			check(p + "candidate_lost_" + k + "_irq_at_wrch_pc", irq_at_wrch(o, t) && o.raddr == 0 && (o.events & SPU_EVENT_LR) && !t.interrupts_enabled);
			check(p + "candidate_lost_" + k + "_no_wait_no_registration", g_stats.bounded_waits == 0 && g_stats.infinite_waits == 0 && registrations_clear() && !o.waiting);
		}
	}
	// T4: intact reservation, nothing happens: bounded re-checks only, then a stop.
	{
		spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
		auto o0 = run_base(t);
		check(p + "baseline_intact_infinite_wait", o0.blocked && g_stats.infinite_waits == 1 && g_stats.bounded_waits == 0);
	}
	{
		spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
		bool registered_during_wait = true;
		on_wait_entry = [&](bool) { registered_during_wait &= (vm::total_waiters() == 1); };
		on_bound_expiry = [&] { if (g_stats.bound_expiries == 3) { t.state += cpu_flag::stop; } };
		auto o = run_cand(t);
		check(p + "candidate_intact_three_bounded_rechecks_then_stop", o.returned && !o.result && !o.escaped && o.accepted == 0 && g_stats.bounded_waits == 3 && g_stats.infinite_waits == 0);
		check(p + "candidate_intact_bound_equals_rdeventstat", g_stats.last_bound_ns == expected_bound_ns());
		check(p + "candidate_intact_registered_while_waiting_released_after", registered_during_wait && registrations_clear() && !o.waiting && o.raddr == raddr && !o.count);
	}
	// T5: direct stores that never notify, after the wait started.
	for (int kind = 0; kind < 2; ++kind)
	{
		const std::string k = kind ? "contents" : "generation";
		{
			spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
			before_list_wait = [&] { kind ? store_contents_no_notify(raddr) : bump_generation_no_notify(raddr); };
			auto o = run_base(t);
			check(p + "baseline_direct_" + k + "_store_during_wait_blocks", o.blocked && !o.escaped);
		}
		{
			spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
			on_bound_expiry = [&] { if (g_stats.bound_expiries == 1) { kind ? store_contents_no_notify(raddr) : bump_generation_no_notify(raddr); } else t.state += cpu_flag::stop; };
			auto o = run_cand(t);
			check(p + "candidate_direct_" + k + "_store_irq_after_one_bound", irq_at_wrch(o, t) && g_stats.bound_expiries == 1 && g_stats.bounded_waits == 1 && registrations_clear());
		}
	}
	// T6: notifying store (PUTLLC success / stcx) wakes the registered wait without the bound.
	{
		spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
		before_list_wait = [&] { notifying_store(raddr); };
		auto o = run_base(t);
		check(p + "baseline_notifying_store_blocks", o.blocked && !o.escaped);
	}
	{
		spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
		before_list_wait = [&] { notifying_store(raddr); };
		on_bound_expiry = [&] { if (g_stats.bound_expiries > 1) t.state += cpu_flag::stop; };
		auto o = run_cand(t);
		check(p + "candidate_notifying_store_wakes_without_bound", irq_at_wrch(o, t) && g_stats.bound_expiries == 0 && g_stats.ready_wakes >= 1 && registrations_clear());
	}
	// T7: loss between owner collection and registration (state.add_fetch(wait) hook).
	for (int kind = 0; kind < 2; ++kind)
	{
		const std::string k = kind ? "contents" : "generation";
		spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
		before_state_wait = [&] { kind ? store_contents_no_notify(raddr) : bump_generation_no_notify(raddr); };
		on_bound_expiry = [&] { if (g_stats.bound_expiries > 1) t.state += cpu_flag::stop; };
		auto o = run_cand(t);
		check(p + "candidate_window_" + k + "_revalidated_without_waiting", irq_at_wrch(o, t) && g_stats.bounded_waits == 0 && registrations_clear());
	}
	// T8: SNR during an LR-armed wait keeps its prompt notification.
	{
		spu_thread t; fixture(t, SPU_EVENT_LR | SPU_EVENT_S1, raddr);
		before_list_wait = [&] { t.push_snr(0, 0x1234); };
		on_bound_expiry = [&] { t.state += cpu_flag::stop; };
		auto o = run_cand(t);
		check(p + "candidate_snr_wakes_lr_wait_without_bound", irq_at_wrch(o, t) && g_stats.bound_expiries == 0 && (o.events & SPU_EVENT_S1) && o.raddr == raddr && registrations_clear());
	}
	// T9: decrementer deadline during an LR-armed wait keeps its prompt notification.
	{
		spu_thread t; fixture(t, SPU_EVENT_LR | SPU_EVENT_TM, raddr);
		before_list_wait = [&] { clock_now = 12; cand::publish_timer(t, 1); };
		on_bound_expiry = [&] { t.state += cpu_flag::stop; };
		auto o = run_cand(t);
		check(p + "candidate_decrementer_wakes_lr_wait_without_bound", irq_at_wrch(o, t) && g_stats.bound_expiries == 0 && (o.events & SPU_EVENT_TM) && o.raddr == raddr && registrations_clear());
	}
	// T10: stop during an LR-armed wait.
	{
		spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
		before_list_wait = [&] { t.state += cpu_flag::stop; t.notify(); };
		auto o = run_cand(t);
		check(p + "candidate_stop_releases_registrations", o.returned && !o.result && !o.escaped && o.accepted == 0 && g_stats.bound_expiries == 0 && registrations_clear() && !o.waiting && o.raddr == raddr);
	}
	// T11: not armed -> unchanged infinite wait, no registration, no collection.
	struct Neg { const char* name; u32 mask; bool irq; u32 raddr; bool unsavable; };
	const Neg negs[] = {
		{"lr_masked_off", SPU_EVENT_TM, true, raddr, false},
		{"interrupts_disabled", SPU_EVENT_LR, false, raddr, false},
		{"no_reservation", SPU_EVENT_LR, true, 0, false},
		{"non_materialized_entry", SPU_EVENT_LR, true, raddr, true},
	};
	for (const auto& n : negs)
	{
		spu_thread t; fixture(t, n.mask, raddr);
		t.interrupts_enabled = n.irq; t.unsavable = n.unsavable; t.raddr = n.raddr;
		bump_generation_no_notify(raddr);
		bool clean_at_wait = true;
		on_wait_entry = [&](bool) { clean_at_wait &= registrations_clear(); };
		auto o = run_cand(t);
		check(p + "candidate_negative_" + n.name + "_infinite_wait_only", o.blocked && !o.escaped && g_stats.infinite_waits == 1 && g_stats.bounded_waits == 0 && clean_at_wait && o.raddr == n.raddr && !(o.events & SPU_EVENT_LR));
	}
	// T12: IRQ, handler ACK, IRET: the same WRCH is accepted exactly once.
	{
		spu_thread t; fixture(t, SPU_EVENT_LR, raddr);
		bump_generation_no_notify(raddr);
		auto o = run_cand(t);
		if (!o.escaped)
		{
			check(p + "candidate_iret_reexecutes_wrch_once", false);
			check(p + "candidate_after_ack_accepted_exactly_once", false);
			return;
		}
		cand::spu_opcode_t op{};
		cand::IRET(t, op);
		t.complete_lists = true;
		auto handler = enter(t, [&] { cand::exec_list_unstall(&t, 0); return true; });
		auto again = run_cand(t);
		check(p + "candidate_iret_reexecutes_wrch_once", irq_at_wrch(o, t) || (o.escaped && o.return_pc == WRCH_PC));
		check(p + "candidate_after_ack_accepted_exactly_once", handler.returned && again.returned && again.result && t.accepted == 1 && t.pc == WRCH_PC);
	}
}

static void concurrent(u32 raddr, int iterations)
{
	// Real threads; real bounded waits; watchdog 2 s only for infinite waits.
	const char* names[] = {"notifying", "contents_no_notify", "generation_no_notify", "snr", "decrementer", "stop"};
	std::mt19937 rng(12345);
	for (int kind = 0; kind < 6; ++kind)
	{
		int ok = 0;
		for (int i = 0; i < iterations; ++i)
		{
			spu_thread t;
			const u32 mask = SPU_EVENT_LR | (kind == 3 ? SPU_EVENT_S1 : 0) | (kind == 4 ? SPU_EVENT_TM : 0);
			fixture(t, mask, raddr);
			concurrent_wait = true;
			const int delay = int(rng() % 300);
			std::thread writer([&] {
				std::this_thread::sleep_for(std::chrono::microseconds(delay));
				switch (kind)
				{
				case 0: notifying_store(raddr); break;
				case 1: store_contents_no_notify(raddr); break;
				case 2: bump_generation_no_notify(raddr); break;
				case 3: t.push_snr(0, 0x77); break;
				case 4: clock_now = 12; cand::publish_timer(t, 1); break;
				case 5: t.state += cpu_flag::stop; t.notify(); break;
				}
			});
			auto o = run_cand(t);
			writer.join();
			const bool good = kind == 5 ? (o.returned && !o.result && !o.escaped && o.accepted == 0)
			                            : (o.escaped && o.return_pc == WRCH_PC && o.accepted == 0 && o.queue == 16);
			ok += good && registrations_clear() && g_stats.watchdog == 0;
		}
		check(std::string("concurrent.") + names[kind] + "_" + std::to_string(iterations), ok == iterations);
	}
	concurrent_wait = false;
}

int main(int argc, char** argv)
{
	static_cast<void>(&cand::exec_list_unstall);
	const bool deterministic_only = argc > 1 && std::string(argv[1]) == "--deterministic-only";
	deterministic("main", 0x00010000);
	deterministic("rsx_window", 0x60300500);
	if (!deterministic_only) concurrent(0x00010000, 64);
	int failed = 0;
	std::printf("{");
	for (usz i = 0; i < g_checks.size(); ++i)
	{
		std::printf("%s\"%s\":%s", i ? "," : "", g_checks[i].name.c_str(), g_checks[i].ok ? "true" : "false");
		failed += !g_checks[i].ok;
	}
	std::printf("}\n");
	std::fprintf(stderr, "checks=%zu failed=%d\n", g_checks.size(), failed);
	return failed ? 1 : 0;
}
