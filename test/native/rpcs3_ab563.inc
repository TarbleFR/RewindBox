// SPDX-License-Identifier: GPL-2.0-only
// CELL563_EARLY_AB host model. The early-submit header is the production one,
// included as the Core compiles it; the policy block, the title predicate,
// resolve_mode, the window-boundary statement and the OPT561 export block are
// copied verbatim from the 563 Core source. Adapters stand in for g_cfg, Emu,
// the profiler logger and the RSX thread's end-of-draw reads. No Vulkan, Metal
// or GPU is involved: the model checks which state each window runs with and
// what the window reports, not frame times.
//@@PRELUDE
#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include "ios/IOSEarlySubmit.h"

using u32 = std::uint32_t;
using u64 = std::uint64_t;

//@ENUM@

namespace rpcs3::ios::deferred_commit
{
//@TITLE@
}

//@RESOLVE@

struct fake_cfg
{
	struct
	{
		ios_experimental_mode early_submit = ios_experimental_mode::automatic;
	} ios_experimental;
};
static fake_cfg g_cfg;

struct fake_emu
{
	std::string title;
	const std::string& GetTitleID() const { return title; }
};
static fake_emu Emu;

struct resolved_policy
{
	bool early_submit = false;
};

// The 563 policy block, verbatim, inside the resolution it belongs to.
static bool resolve(ios_experimental_mode mode, const char* title, bool& ab)
{
	g_cfg.ios_experimental.early_submit = mode;
	Emu.title = title;
	resolved_policy resolved;
//@POLICY@
	ab = early_submit_ab;
	return resolved.early_submit;
}

struct fake_logger
{
	std::string last;
	void notice(const char* format, ...)
	{
		char text[1024];
		va_list args;
		va_start(args, format);
		std::vsnprintf(text, sizeof(text), format, args);
		va_end(args);
		last = text;
	}
};
static fake_logger ios_core_profiler;

static u64 field(const std::string& line, const char* key)
{
	const std::string needle = std::string(" ") + key + "=";
	const auto at = line.find(needle);
	if (at == std::string::npos)
	{
		return ~u64{0};
	}
	return std::strtoull(line.c_str() + at + needle.size(), nullptr, 10);
}

struct window_report
{
	u64 state, ab, submits, draws;
};

// One profiling window boundary: the snapshot statement taken under the profile
// mutex, then the export block formatted after it, as report_profile_window does.
static window_report report_window(u64 profile_session, u64 profile_window)
{
	bool early_submit_state = false;
//@BOUNDARY@
//@EXPORT@
	const auto& line = ios_core_profiler.last;
	return {field(line, "early_submit"), field(line, "ab"), field(line, "early_submits"), field(line, "early_draws")};
}

// The RSX thread at the end of one draw: it reads the lever, and an early
// submission (here: every draw while the lever is on) bumps the counters.
static bool end_of_draw()
{
	namespace early = rpcs3::ios::early_submit;
	const bool on = early::enabled.load(std::memory_order_relaxed);
	if (on)
	{
		early::submits.fetch_add(1, std::memory_order_relaxed);
		early::submitted_draws.fetch_add(early::min_draws, std::memory_order_relaxed);
	}
	return on;
}

static bool expect(bool condition, const char* what)
{
	if (!condition)
	{
		std::fprintf(stderr, "FAILED: %s\n", what);
	}
	return condition;
}
//@@MAIN
int main()
{
	namespace early = rpcs3::ios::early_submit;
	bool ok = true;

	// Policy: alternation only for Automatic on the DBZ title; explicit modes keep one state.
	struct policy_case
	{
		ios_experimental_mode mode;
		const char* title;
		bool on, ab;
	};
	const policy_case cases[] = {
		{ios_experimental_mode::automatic, "BLES01658", true, true},
		{ios_experimental_mode::automatic, "BLES01717", false, false},
		{ios_experimental_mode::automatic, "BCES00510", false, false},
		{ios_experimental_mode::enabled, "BLES01658", true, false},
		{ios_experimental_mode::enabled, "BLES01717", true, false},
		{ios_experimental_mode::disabled, "BLES01658", false, false},
		{ios_experimental_mode::disabled, "BLES01717", false, false},
	};
	u32 policy_cases = 0;
	for (const auto& c : cases)
	{
		bool ab = !c.ab;
		const bool on = resolve(c.mode, c.title, ab);
		ok &= expect(on == c.on && ab == c.ab, "policy table");
		ok &= expect(early::enabled.load() == c.on && early::alternate.load() == c.ab, "policy stores");
		policy_cases++;
	}

	// Alternation in one session: every window reports the state its draws saw,
	// the first window runs with the lever on, and the states alternate.
	{ bool alternating = false; resolve(ios_experimental_mode::automatic, "BLES01658", alternating); }
	early::submits = 0;
	early::submitted_draws = 0;
	std::string sequence;
	u32 windows = 0, on_windows = 0, off_windows = 0;
	bool expected = true;
	for (u64 window = 1; window <= 12; window++)
	{
		u32 seen_on = 0, seen_off = 0;
		for (u32 draw = 0; draw < 200 + 7 * window; draw++)
		{
			(end_of_draw() ? seen_on : seen_off)++;
		}
		const auto report = report_window(2, window);
		ok &= expect(report.ab == 1, "ab flag on alternating windows");
		ok &= expect(report.state == (expected ? 1u : 0u), "window state sequence");
		ok &= expect(expected ? (seen_off == 0 && seen_on > 0) : (seen_on == 0 && seen_off > 0), "draws see the window state");
		ok &= expect(report.state == 1 ? report.submits == seen_on : report.submits == 0, "counters belong to their window");
		ok &= expect(report.draws == report.submits * early::min_draws, "draw counter");
		sequence += report.state ? '1' : '0';
		(report.state ? on_windows : off_windows)++;
		expected = !expected;
		windows++;
	}
	ok &= expect(sequence == "101010101010", "alternation pattern");

	// Explicit modes and other titles: one state for the whole session, ab=0.
	for (const auto mode : {ios_experimental_mode::enabled, ios_experimental_mode::disabled})
	{
		bool ab = true;
		const bool on = resolve(mode, "BLES01658", ab);
		for (u64 window = 1; window <= 6; window++)
		{
			for (u32 draw = 0; draw < 50; draw++)
			{
				ok &= expect(end_of_draw() == on, "explicit mode keeps its state between boundaries");
			}
			const auto report = report_window(2, window);
			ok &= expect(report.state == (on ? 1u : 0u) && report.ab == 0, "explicit mode keeps one state");
		}
	}
	{
		bool ab = true;
		resolve(ios_experimental_mode::automatic, "BLES01717", ab);
		for (u64 window = 1; window <= 4; window++)
		{
			const auto report = report_window(1, window);
			ok &= expect(report.state == 0 && report.ab == 0 && report.submits == 0, "other titles stay off");
		}
	}

	// Concurrency: the RSX thread reads the lever and counts while the profiler
	// thread crosses window boundaries. Every early submission is reported once.
	{ bool alternating = false; resolve(ios_experimental_mode::automatic, "BLES01658", alternating); }
	early::submits = 0;
	early::submitted_draws = 0;
	std::atomic<bool> stop{false};
	std::atomic<u64> made{0};
	std::thread rsx([&] {
		while (!stop.load(std::memory_order_acquire))
		{
			if (end_of_draw())
			{
				made.fetch_add(1, std::memory_order_relaxed);
			}
		}
	});
	u64 reported = 0;
	u32 thread_windows = 0, alternations = 0;
	u64 previous = 2;
	for (u64 window = 1; window <= 400; window++)
	{
		std::this_thread::yield();
		const auto report = report_window(3, window);
		reported += report.submits;
		alternations += previous != 2 && report.state != previous;
		previous = report.state;
		thread_windows++;
	}
	stop.store(true, std::memory_order_release);
	rsx.join();
	reported += early::submits.exchange(0);
	early::submitted_draws.exchange(0);
	ok &= expect(reported == made.load(), "every early submission is reported once");
	ok &= expect(alternations == thread_windows - 1, "the state alternates at every boundary under concurrency");

	// The 561 decision itself is the production one, unchanged.
	u32 decisions = 0;
	for (u32 draws = 0; draws < early::min_draws * 2; draws++)
		for (u32 this_frame = 0; this_frame <= early::max_per_frame + 1; this_frame++)
			for (const bool idle : {false, true})
			{
				const auto v = early::decide(true, draws, this_frame, idle);
				const auto want = draws < early::min_draws ? early::verdict::keep :
					this_frame >= early::max_per_frame ? early::verdict::capped :
					idle ? early::verdict::submit : early::verdict::gpu_busy;
				ok &= expect(v == want, "decide verdict");
				ok &= expect(early::decide(false, draws, this_frame, idle) == early::verdict::keep, "decide off");
				decisions++;
			}

	if (!ok)
	{
		return 1;
	}
	std::printf("{\"passed\":true,\"policyCases\":%u,\"windows\":%u,\"onWindows\":%u,\"offWindows\":%u,\"sequence\":\"%s\","
		"\"explicitModesStable\":true,\"otherTitlesOff\":true,\"threadWindows\":%u,"
		"\"everySubmissionReportedOnce\":true,\"decisions\":%u}\n",
		policy_cases, windows, on_windows, off_windows, sequence.c_str(), thread_windows, decisions);
	return 0;
}
