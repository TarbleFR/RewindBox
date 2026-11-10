// SPDX-License-Identifier: GPL-2.0-only
// CELL569 host model. The thread QoS header is the production one, included as
// the Core compiles it, and the iOS branch of
// thread_ctrl::set_thread_affinity_mask is copied verbatim from the 569 Core
// source. On Apple hosts the real calls are exercised: a thread at a negative
// relative priority that applies THREAD_AFFINITY_POLICY (the 567 Core) is
// recorded, and the production sequence (relative priority -2, the iOS
// affinity branch, then +1) must keep its QoS and raise it.
//@@PRELUDE
#include <cstdio>
#include <cstdint>

#if defined(__APPLE__)
#include <mach/mach.h>
#include <mach/thread_policy.h>
#include <pthread.h>
#include <pthread/qos.h>
#endif

#include "ios/IOSThreadQoS.h"

using u64 = std::uint64_t;

// The iOS branch of thread_ctrl::set_thread_affinity_mask, verbatim.
static void ios_set_thread_affinity_mask([[maybe_unused]] u64 mask)
{
//@AFFINITY@
}

#if defined(__APPLE__)
static int apply(int priority)
{
	const auto level = rpcs3::ios::thread_qos::for_priority(priority);
	return pthread_set_qos_class_self_np(level.utility ? QOS_CLASS_UTILITY : QOS_CLASS_USER_INTERACTIVE, level.relative_priority);
}

// What the 567 Core did on Apple: THREAD_AFFINITY_POLICY through thread_policy_set().
static void raw_affinity(u64 mask)
{
	thread_affinity_policy_data_t policy = { static_cast<integer_t>(__builtin_ctzll(mask | (1ull << 63))) };
	thread_port_t mach_thread = pthread_mach_thread_np(pthread_self());
	thread_policy_set(mach_thread, THREAD_AFFINITY_POLICY, reinterpret_cast<thread_policy_t>(&policy), !mask ? 0 : 1);
}

struct darwin_probe
{
	bool production = false;
	int lowered_err = -1, raised_err = -1, raw_raise_err = -1, raw_relzero_err = -1;
	qos_class_t raised = QOS_CLASS_UNSPECIFIED;
	int raised_rel = 1;
};

static void* darwin_job(void* opaque)
{
	auto* probe = static_cast<darwin_probe*>(opaque);
	probe->lowered_err = apply(0);
	if (probe->production)
	{
		ios_set_thread_affinity_mask(0);
		ios_set_thread_affinity_mask(0x3f);
		probe->raised_err = apply(1);
		pthread_get_qos_class_np(pthread_self(), &probe->raised, &probe->raised_rel);
	}
	else
	{
		raw_affinity(0);
		probe->raw_raise_err = apply(1);
	}
	return nullptr;
}

static void* darwin_relzero_job(void* opaque)
{
	auto* probe = static_cast<darwin_probe*>(opaque);
	pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
	raw_affinity(0);
	probe->raw_relzero_err = pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
	return nullptr;
}

static darwin_probe run_probe(void* (*job)(void*), bool production)
{
	darwin_probe probe;
	probe.production = production;
	pthread_attr_t attrs;
	pthread_attr_init(&attrs);
	pthread_attr_set_qos_class_np(&attrs, QOS_CLASS_USER_INTERACTIVE, 0);
	pthread_t thread{};
	if (pthread_create(&thread, &attrs, job, &probe) == 0)
	{
		pthread_join(thread, nullptr);
	}
	pthread_attr_destroy(&attrs);
	return probe;
}
#endif
//@@MAIN
static int failures = 0;

#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

int main()
{
	namespace q = rpcs3::ios::thread_qos;
	int darwin = 0, raw_raise_err = -1, raw_relzero_err = -1;

	// The 567 mapping the 569 change keeps working: on, +1 is above 0.
	q::default_relative_priority.store(q::lowered_relative_priority);
	CHECK(q::for_priority(0).relative_priority == -2 && q::for_priority(1).relative_priority == 0);
	ios_set_thread_affinity_mask(0);
	ios_set_thread_affinity_mask(0x3f);

#if defined(__APPLE__)
	darwin = 1;
	// The production sequence keeps the QoS and raises the thread.
	const auto production = run_probe(&darwin_job, true);
	CHECK(production.lowered_err == 0);
	CHECK(production.raised_err == 0);
	CHECK(production.raised == QOS_CLASS_USER_INTERACTIVE && production.raised_rel == 0);
	// The 567 sequence and the relative-priority-0 sequence, recorded.
	raw_raise_err = run_probe(&darwin_job, false).raw_raise_err;
	raw_relzero_err = run_probe(&darwin_relzero_job, false).raw_relzero_err;
#endif

	q::default_relative_priority.store(0);
	std::printf("{\"passed\": %s, \"darwinKernel\": %d, \"rawAffinityThenRaiseErr\": %d, \"rawRelativeZeroErr\": %d}\n",
		failures ? "false" : "true", darwin, raw_raise_err, raw_relzero_err);
	return failures ? 1 : 0;
}
