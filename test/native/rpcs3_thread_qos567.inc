// SPDX-License-Identifier: GPL-2.0-only
// CELL567 host model. The thread QoS header is the production one, included as
// the Core compiles it; the policy block and resolve_mode are copied verbatim
// from the 567 Core source. A pooled worker is modelled with the same mapping
// thread_ctrl::set_native_priority uses. On Apple hosts the real
// pthread_set_qos_class_self_np / pthread_get_qos_class_np pair is exercised
// as well: a thread lowered to utility, then reset as a new job, reads back
// the user-interactive class at the default relative priority.
//@@PRELUDE
#include <cstdio>
#include <string>
#include <thread>

#if defined(__APPLE__)
#include <pthread.h>
#include <pthread/qos.h>
#endif

#include "ios/IOSThreadQoS.h"

//@ENUM@

//@RESOLVE@

struct fake_cfg
{
	struct
	{
		ios_experimental_mode rsx_thread_priority = ios_experimental_mode::automatic;
	} ios_experimental;
};
static fake_cfg g_cfg;

struct resolved_policy
{
	bool rsx_thread_priority = false;
};

// The 567 policy block, verbatim.
static resolved_policy resolve(ios_experimental_mode mode)
{
	g_cfg.ios_experimental.rsx_thread_priority = mode;
	resolved_policy resolved;
//@POLICY@
	return resolved;
}

// A pooled native worker: its level changes only through for_priority, as
// set_native_priority does, and each job starts with set_native_priority(0).
struct worker
{
	rpcs3::ios::thread_qos::level now{false, 0};

	void set_native_priority(int priority)
	{
		now = rpcs3::ios::thread_qos::for_priority(priority);
	}

	template <typename F>
	void run_job(F&& job)
	{
		set_native_priority(0);
		job(*this);
	}
};

#if defined(__APPLE__)
struct darwin_probe
{
	qos_class_t lowered = QOS_CLASS_UNSPECIFIED, reset = QOS_CLASS_UNSPECIFIED, raised = QOS_CLASS_UNSPECIFIED;
	int lowered_rel = 1, reset_rel = 1, raised_rel = 1;
};

static void apply(int priority)
{
	const auto level = rpcs3::ios::thread_qos::for_priority(priority);
	pthread_set_qos_class_self_np(level.utility ? QOS_CLASS_UTILITY : QOS_CLASS_USER_INTERACTIVE, level.relative_priority);
}

static void* darwin_job(void* opaque)
{
	auto* probe = static_cast<darwin_probe*>(opaque);
	apply(-1);
	pthread_get_qos_class_np(pthread_self(), &probe->lowered, &probe->lowered_rel);
	apply(0);
	pthread_get_qos_class_np(pthread_self(), &probe->reset, &probe->reset_rel);
	apply(1);
	pthread_get_qos_class_np(pthread_self(), &probe->raised, &probe->raised_rel);
	return nullptr;
}
#endif
//@@MAIN
static int failures = 0;

#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

int main()
{
	namespace q = rpcs3::ios::thread_qos;
	int modes = 0, darwin_modes = 0;

	for (const auto mode : {ios_experimental_mode::automatic, ios_experimental_mode::enabled, ios_experimental_mode::disabled})
	{
		const auto resolved = resolve(mode);
		const bool on = mode != ios_experimental_mode::disabled;
		const int expected = on ? q::lowered_relative_priority : 0;
		CHECK(resolved.rsx_thread_priority == on);
		CHECK(q::default_relative_priority.load() == expected);

		const auto raised = q::for_priority(1), normal = q::for_priority(0), low = q::for_priority(-1);
		CHECK(!raised.utility && raised.relative_priority == 0);
		CHECK(!normal.utility && normal.relative_priority == expected);
		CHECK(low.utility && low.relative_priority == 0);
		// RSX and audio (+1) above the threads that request nothing while on; equal while off.
		CHECK((raised.relative_priority > normal.relative_priority) == on);

		// A worker a shader-cache writer left at utility starts its next job at the default level.
		worker w;
		w.run_job([](worker& self) { self.set_native_priority(-1); });
		CHECK(w.now.utility);
		bool next_job_utility = true;
		int next_job_relative = 1;
		w.run_job([&](worker& self) { next_job_utility = self.now.utility; next_job_relative = self.now.relative_priority; });
		CHECK(!next_job_utility && next_job_relative == expected);
		modes++;

#if defined(__APPLE__)
		darwin_probe probe;
		pthread_t thread{};
		CHECK(pthread_create(&thread, nullptr, &darwin_job, &probe) == 0);
		CHECK(pthread_join(thread, nullptr) == 0);
		CHECK(probe.lowered == QOS_CLASS_UTILITY);
		CHECK(probe.reset == QOS_CLASS_USER_INTERACTIVE && probe.reset_rel == expected);
		CHECK(probe.raised == QOS_CLASS_USER_INTERACTIVE && probe.raised_rel == 0);
		darwin_modes++;
#endif
	}

	q::default_relative_priority.store(0);
	std::printf("{\"passed\": %s, \"modes\": %d, \"darwinKernelModes\": %d, \"loweredRelativePriority\": %d}\n",
		failures ? "false" : "true", modes, darwin_modes, q::lowered_relative_priority);
	return failures ? 1 : 0;
}
