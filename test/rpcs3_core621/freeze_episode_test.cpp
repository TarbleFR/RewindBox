// Host test of REWINDBOX_FREEZE_EPISODE_621 (rpcs3/ios/RPCS3IOSFreezeEpisode.h)
// and of the waits summary helper of the freeze dump. The sampler is replayed
// every 500 ms with the scenarios of the maintainer's request: a normal pause,
// a freeze followed by repeated pauses, a quiet freeze, a guest-fault freeze
// and stop, an iOS suspension, loading, recovery and a later freeze.
#include "ios/RPCS3IOSFreezeEpisode.h"
#include "ios/RPCS3IOSProfilerHelpers.h"

#include <cstdio>
#include <string>
#include <vector>

namespace fe = rpcs3::ios::freeze_episode;

static int g_failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); ++g_failures; } } while (0)

namespace
{
struct replay
{
	fe::tracker tracker;
	std::uint64_t now = 1'000'000;
	std::uint64_t flips = 0;
	std::vector<fe::report> events;
	unsigned dumps = 0;
	unsigned refuse = 0; // the next dump attempts that give up (busy idm lock)
	unsigned attempts = 0;

	// `seconds` of samples every 500 ms; fps 0 means no guest flip.
	void run(double seconds, fe::emu state, double fps, double cores = 1.0)
	{
		const int samples = static_cast<int>(seconds * 2 + 0.5);
		double carry = 0.0;
		for (int i = 0; i < samples; ++i)
		{
			now += 500'000;
			carry += fps * 0.5;
			while (carry >= 1.0)
			{
				flips++;
				carry -= 1.0;
			}
			push({now, state, flips, cores});
		}
	}

	void push(const fe::tick& sample)
	{
		const auto result = tracker.observe(sample);
		if (result.what != fe::event::none) events.push_back(result);
		if (result.dump)
		{
			attempts++;
			if (refuse) refuse--;
			else
			{
				dumps++;
				tracker.dump_taken(sample.now_us);
			}
		}
	}

	// A gap without samples (the app suspended by iOS), then one sample.
	void suspend(double seconds, fe::emu state = fe::emu::running)
	{
		now += static_cast<std::uint64_t>(seconds * 1e6);
		push({now, state, flips, 0.0});
	}

	unsigned count(fe::event what) const
	{
		unsigned result = 0;
		for (const auto& e : events) result += e.what == what;
		return result;
	}

	const fe::report* last(fe::event what) const
	{
		for (auto it = events.rbegin(); it != events.rend(); ++it)
			if (it->what == what) return &*it;
		return nullptr;
	}
};

void normal_pause()
{
	// Gameplay, a 60 s pause (debugger or capture: the RewindBox menu does not
	// pause), gameplay again: no episode at all.
	replay r;
	r.run(10, fe::emu::running, 30);
	r.run(60, fe::emu::paused, 0, 0.0);
	r.run(10, fe::emu::running, 30);
	CHECK(r.events.empty());
	CHECK(r.dumps == 0);
}

void freeze_then_repeated_pauses()
{
	replay r;
	r.run(10, fe::emu::running, 30);
	// The game stops presenting with an SPU group spinning.
	r.run(4, fe::emu::running, 0, 1.2);
	CHECK(r.count(fe::event::begin) == 1);
	const auto* begin = r.last(fe::event::begin);
	CHECK(begin && std::string(begin->reason) == "no_frames_busy" && begin->dump);
	CHECK(begin && begin->no_frames_s >= 3.0 && begin->no_frames_s < 3.6);
	// The tester alternates pause and resume five times; nothing is presented.
	for (int i = 0; i < 5; ++i)
	{
		r.run(8, fe::emu::paused, 0, 0.0);
		r.run(3, fe::emu::running, 0, 1.2);
	}
	CHECK(r.count(fe::event::begin) == 1); // still the same episode
	CHECK(r.dumps == 1);                   // its evidence was taken once, before the pauses
	CHECK(!r.events.empty() && r.events.front().episode == 1);
	const auto* update = r.last(fe::event::update);
	CHECK(update && update->episode == 1 && update->pauses >= 1);
	CHECK(update && update->episode_s < 20.0); // pauses never count as frozen time
	CHECK(r.tracker.open());
	// Stopped by the tester.
	r.run(1, fe::emu::stopped, 0, 0.0);
	const auto* end = r.last(fe::event::end);
	CHECK(end && std::string(end->outcome) == "stopped" && end->episode == 1 && end->pauses == 5);
	CHECK(end && end->paused_s >= 39.0 && end->episode_s < 20.0);
	CHECK(!r.tracker.open());
}

void resume_then_later_freeze()
{
	replay r;
	r.run(5, fe::emu::running, 30);
	r.run(4, fe::emu::running, 0, 0.9); // episode 1
	r.run(5, fe::emu::paused, 0, 0.0);
	r.run(3, fe::emu::running, 30);     // frames come back: recovered
	const auto* end = r.last(fe::event::end);
	CHECK(end && std::string(end->outcome) == "recovered" && end->episode == 1);
	CHECK(end && end->flips_during >= 10);
	r.run(30, fe::emu::running, 30);
	r.run(4, fe::emu::running, 0, 0.9); // episode 2, after the resume
	CHECK(r.count(fe::event::begin) == 2);
	CHECK(r.last(fe::event::begin)->episode == 2);
	CHECK(r.dumps == 2);
	// A third stall 3 s after recovering is a new episode, but its dump waits for the 10 s floor.
	r.run(2, fe::emu::running, 30);
	r.run(4, fe::emu::running, 0, 0.9);
	CHECK(r.count(fe::event::begin) == 3);
	CHECK(r.last(fe::event::begin)->dump_suppressed);
	CHECK(r.dumps == 2);
	// The suppressed dump of episode 3 is taken once the 10 s floor has passed.
	r.run(8, fe::emu::running, 0, 0.9);
	CHECK(r.dumps == 3);
}

void boot_before_first_frame()
{
	// First boot: 40 s of running time compiling before the first guest flip, busy
	// or quiet: loading, not a freeze. The first flip arms the triggers.
	replay r;
	r.run(20, fe::emu::running, 0, 2.5);
	r.run(20, fe::emu::running, 0, 0.1);
	CHECK(r.events.empty());
	r.run(1, fe::emu::running, 30);
	r.run(4, fe::emu::running, 0, 1.0);
	CHECK(r.count(fe::event::begin) == 1);
}

void dump_retried_until_taken()
{
	// The dump gives up twice (idm lock busy): it is retried on the next samples,
	// taken once, and never again for the same episode.
	replay r;
	r.run(5, fe::emu::running, 30);
	r.refuse = 2;
	r.run(10, fe::emu::running, 0, 1.0);
	CHECK(r.count(fe::event::begin) == 1);
	CHECK(r.attempts == 3 && r.dumps == 1);
	r.run(30, fe::emu::running, 0, 1.0);
	CHECK(r.dumps == 1);
	// Paused: the dump of a new episode waits (the dump refuses a paused emulator here).
}

void quiet_freeze()
{
	replay r;
	r.run(5, fe::emu::running, 30, 0.8);
	// Every thread waits (a deadlock): 0.05 core. The Build 487 trigger never fired.
	r.run(5, fe::emu::running, 0, 0.05);
	CHECK(r.count(fe::event::begin) == 0);
	r.run(2, fe::emu::running, 0, 0.05);
	CHECK(r.count(fe::event::begin) == 1);
	const auto* begin = r.last(fe::event::begin);
	CHECK(begin && std::string(begin->reason) == "no_frames_idle" && begin->dump);
	CHECK(begin && begin->no_frames_s >= 6.0);
	// Updates every 10 s for the first minute, then every 60 s.
	r.run(120, fe::emu::running, 0, 0.05);
	unsigned updates = r.count(fe::event::update);
	CHECK(updates >= 6 && updates <= 8);
}

void guest_fault_freeze_and_stop()
{
	replay r;
	r.run(5, fe::emu::running, 30);
	r.run(1, fe::emu::frozen, 0, 0.0); // access violation: Emu.Pause(true)
	CHECK(r.count(fe::event::begin) == 1);
	const auto* begin = r.last(fe::event::begin);
	CHECK(begin && std::string(begin->reason) == "emulator_frozen" && begin->dump);
	r.run(25, fe::emu::frozen, 0, 0.0);
	const auto* update = r.last(fe::event::update);
	CHECK(update && update->episode_s >= 10.0); // wall time for a frozen emulator
	const auto stopped = r.tracker.stop(r.now + 500'000);
	CHECK(stopped.what == fe::event::end && std::string(stopped.outcome) == "stopped");
	CHECK(r.dumps == 1);
}

void ios_suspension_and_loading()
{
	replay r;
	r.run(5, fe::emu::running, 30);
	// Background: iOS suspends the process for 5 minutes; no sample, no frame.
	r.suspend(300);
	r.run(2, fe::emu::running, 30);
	CHECK(r.events.empty());
	// Boot-time loading without frames for 40 s.
	r.run(40, fe::emu::loading, 0, 2.0);
	CHECK(r.events.empty());
	// A suspension inside an open episode is reported apart.
	r.run(4, fe::emu::running, 0, 1.0);
	CHECK(r.count(fe::event::begin) == 1);
	r.suspend(120);
	r.run(10, fe::emu::running, 0, 1.0);
	const auto* update = r.last(fe::event::update);
	CHECK(update && update->suspended_s >= 120.0 && update->suspensions == 1);
	CHECK(update && update->episode_s < 20.0);
}

void sparse_flips_stay_open()
{
	// A loading screen that flips once every 4 s with busy compile threads: one
	// episode, never "recovered" by isolated flips.
	replay r;
	r.run(5, fe::emu::running, 30);
	r.run(40, fe::emu::running, 0.25, 2.0);
	CHECK(r.count(fe::event::begin) == 1);
	CHECK(r.count(fe::event::end) == 0);
	CHECK(r.tracker.open());
	const auto* update = r.last(fe::event::update);
	CHECK(update && update->flips_during >= 5);
}

void name_counts()
{
	using rpcs3::ios::profiler::format_name_counts;
	CHECK(format_name_counts({"sys_cond_wait", "guest_code", "sys_cond_wait", "sys_lwmutex_lock", "sys_cond_wait"}) ==
		"sys_cond_wait:3,guest_code:1,sys_lwmutex_lock:1");
	CHECK(format_name_counts({}) == "none");
	CHECK(format_name_counts({"a", "b", "c", "d", "e"}, 2) == "a:1,b:1");
}
}

int main()
{
	normal_pause();
	freeze_then_repeated_pauses();
	resume_then_later_freeze();
	quiet_freeze();
	guest_fault_freeze_and_stop();
	ios_suspension_and_loading();
	sparse_flips_stay_open();
	boot_before_first_frame();
	dump_retried_until_taken();
	name_counts();
	if (g_failures)
	{
		std::fprintf(stderr, "%d failure(s)\n", g_failures);
		return 1;
	}
	std::printf("freeze episode: all checks passed\n");
	return 0;
}
