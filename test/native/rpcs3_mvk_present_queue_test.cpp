// SPDX-License-Identifier: GPL-2.0-only
// Production registry with real GCD on macOS, or serial test queues on Linux.
// This checks queue selection and ordering, not iOS/Metal performance.
#include "ios/IOSMoltenVKExecQueue.h"

#include <cassert>
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>
#include <vector>

#ifdef NDEBUG
#error "The present-queue regression checks require active assertions"
#endif

namespace exec = rpcs3::ios::moltenvk_exec;
using exec::gcd::registry;

static unsigned cases = 0;
static void check(bool value)
{
	++cases;
	assert(value);
}

static dispatch_queue_t record(const char* label)
{
	auto queue = dispatch_queue_create(label, DISPATCH_QUEUE_SERIAL);
	registry::instance().record(queue, label);
	return queue;
}

struct gate
{
	std::mutex mutex;
	std::condition_variable cv;
	bool started = false, released = false, finished = false;

	void wait_started()
	{
		std::unique_lock lock(mutex);
		check(cv.wait_for(lock, std::chrono::seconds(5), [&] { return started; }));
	}
	void open()
	{
		{
			std::lock_guard lock(mutex);
			released = true;
		}
		cv.notify_all();
	}
	bool done()
	{
		std::lock_guard lock(mutex);
		return finished;
	}
	static void run(void* pointer)
	{
		auto& self = *static_cast<gate*>(pointer);
		std::unique_lock lock(self.mutex);
		self.started = true;
		self.cv.notify_all();
		self.cv.wait(lock, [&] { return self.released; });
		self.finished = true;
		self.cv.notify_all();
	}
};

static void parsing()
{
	for (const auto family : {0u, 1u, 17u, UINT32_MAX})
	{
		for (const auto index : {0u, 1u, 23u, UINT32_MAX})
		{
			for (const auto priority : {"0.0", "0.1", "0.9", "1.0"})
			{
				const std::string label = "MoltenVKQueue-" + std::to_string(family) + "-" + std::to_string(index) + "-" + priority + "-Dispatch";
				const auto identity = exec::parse_exec_queue_label(label);
				check(identity.valid && identity.family == family && identity.index == index);
			}
		}
	}
	for (const char* label : {
		"", "other", "MoltenVKQueue--Dispatch", "MoltenVKQueue-0-0-Dispatch",
		"MoltenVKQueue--1-0-0.0-Dispatch", "MoltenVKQueue-0--1-0.0-Dispatch",
		"MoltenVKQueue-+1-0-0.0-Dispatch", "MoltenVKQueue-1-+0-0.0-Dispatch",
		"MoltenVKQueue-00-0-0.0-Dispatch", "MoltenVKQueue-0-01-0.0-Dispatch",
		"MoltenVKQueue-4294967296-0-0.0-Dispatch", "MoltenVKQueue-0-4294967296-0.0-Dispatch",
		"MoltenVKQueue-99999999999999999999-0-0.0-Dispatch",
		"MoltenVKQueue-0x1-0-0.0-Dispatch", "MoltenVKQueue-0-0x1-0.0-Dispatch",
		"MoltenVKQueue- 1-0-0.0-Dispatch", "MoltenVKQueue-0-1 -0.0-Dispatch",
		"MoltenVKQueue-0-0-1.1-Dispatch", "MoltenVKQueue-0-0-2.0-Dispatch",
		"MoltenVKQueue-0-0-0-Dispatch", "MoltenVKQueue-0-0-0.00-Dispatch",
		"MoltenVKQueue-0-0--0.0-Dispatch", "MoltenVKQueue-0-0-nan-Dispatch",
		"MoltenVKQueue-0-0-0,0-Dispatch", "MoltenVKQueue-0-0-0.0-Dispatch-tail",
		"MoltenVKQueue-0-0-0.0-Dispatch\n"})
	{
		check(!exec::parse_exec_queue_label(label).valid);
	}
}

static void selection_and_order(unsigned family, unsigned present_index, bool reversed)
{
	auto& registry = registry::instance();
	registry.begin_device(family, present_index);
	const auto q0_label = "MoltenVKQueue-" + std::to_string(family) + "-0-0.0-Dispatch";
	const auto q1_label = "MoltenVKQueue-" + std::to_string(family) + "-1-0.0-Dispatch";
	dispatch_queue_t q0, q1;
	if (reversed) { q1 = record(q1_label.c_str()); q0 = record(q0_label.c_str()); }
	else { q0 = record(q0_label.c_str()); q1 = record(q1_label.c_str()); }
	check(registry.queue_count() == 2 && registry.has_present_queue());

	auto selected = present_index ? q1 : q0;
	auto unrelated = present_index ? q0 : q1;
	gate before, after, transfer;
	dispatch_async_f(selected, &before, gate::run);
	dispatch_async_f(unrelated, &transfer, gate::run);
	before.wait_started();
	transfer.wait_started();
	const auto ticket = registry.mark_present();
	check(ticket != 0);
	dispatch_async_f(selected, &after, gate::run);
	const auto previous_timeouts = exec::acquire_timeouts.load();
	before.open();
	registry.wait_for_present(ticket);
	after.wait_started();
	check(before.done());
	check(!after.done() && !transfer.done());
	check(exec::acquire_timeouts.load() == previous_timeouts);
#ifndef RPCS3_MVK_USE_REAL_GCD
	check(q0->sync_calls.load() == 0 && q1->sync_calls.load() == 0);
#endif

	// The explicit drain still covers both queues, beyond the present marker.
	after.open();
	transfer.open();
	registry.drain();
	check(after.done() && transfer.done());
#ifndef RPCS3_MVK_USE_REAL_GCD
	check(q0->sync_calls.load() == 1 && q1->sync_calls.load() == 1);
#endif
	registry.begin_device();
	dispatch_release(q0);
	dispatch_release(q1);
}

static void rejected_sets()
{
	auto& registry = registry::instance();
	registry.begin_device();
	check(!registry.has_present_queue() && registry.mark_present() == 0);
	auto other = record("other-queue");
	check(registry.queue_count() == 0 && !registry.has_present_queue());
	dispatch_release(other);

	// A single captured queue with the wrong identity is not a present queue.
	registry.begin_device(7, 1);
	auto wrong = record("MoltenVKQueue-7-0-0.0-Dispatch");
	check(registry.queue_count() == 1 && !registry.has_present_queue() && registry.mark_present() == 0);
	registry.begin_device();
	dispatch_release(wrong);

	for (const char* second : {"MoltenVKQueue-0-0-1.0-Dispatch", "MoltenVKQueue-0x0-1-0.0-Dispatch",
		"MoltenVKQueue-0-0-0.0-Dispatch-tail", "MoltenVKQueue--Dispatch"})
	{
		registry.begin_device();
		auto first = record("MoltenVKQueue-0-0-0.0-Dispatch");
		auto duplicate_or_invalid = record(second);
		check(registry.queue_count() == 2 && !registry.has_present_queue() && registry.mark_present() == 0);
		registry.begin_device();
		dispatch_release(first);
		dispatch_release(duplicate_or_invalid);
	}

	// Capturing five queues must not silently retain a valid-looking four-entry set.
	registry.begin_device();
	std::vector<dispatch_queue_t> queues;
	for (unsigned index = 0; index < 6; ++index)
	{
		const auto label = "MoltenVKQueue-0-" + std::to_string(index) + "-0.0-Dispatch";
		queues.push_back(record(label.c_str()));
		check(registry.queue_count() == index + 1);
		check(registry.has_present_queue() == (index < 4));
		if (index >= 4) check(registry.mark_present() == 0);
	}
	registry.begin_device();
	for (auto queue : queues) dispatch_release(queue);
}

static void device_replacement()
{
	auto& registry = registry::instance();
	registry.begin_device();
	auto old_queue = record("MoltenVKQueue-0-0-0.0-Dispatch");
	gate old_render;
	dispatch_async_f(old_queue, &old_render, gate::run);
	old_render.wait_started();
	const auto old_ticket = registry.mark_present();

	registry.begin_device(3, 1);
	check(!registry.has_present_queue());
	auto new_queue = record("MoltenVKQueue-3-1-0.0-Dispatch");
	gate new_render;
	dispatch_async_f(new_queue, &new_render, gate::run);
	new_render.wait_started();
	const auto new_ticket = registry.mark_present();
	check(new_ticket > old_ticket);
	old_render.open();
	registry.wait_for_present(old_ticket);
	check(old_render.done() && !new_render.done());

	// An old queue's callback must not complete a new device's ticket. Use the
	// actual bounded wait to prove this, without scheduling-dependent sleeps.
	const auto timeouts = exec::acquire_timeouts.load();
	registry.wait_for_present(new_ticket);
	check(exec::acquire_timeouts.load() == timeouts + 1 && !new_render.done());
	new_render.open();
	registry.wait_for_present(new_ticket);
	check(new_render.done() && exec::acquire_timeouts.load() == timeouts + 1);
	registry.drain();
	registry.begin_device();
	dispatch_release(old_queue);
	dispatch_release(new_queue);
}

int main()
{
	parsing();
	for (unsigned family : {0u, 7u})
		for (unsigned index : {0u, 1u})
			for (bool reversed : {false, true})
				selection_and_order(family, index, reversed);
	rejected_sets();
	device_replacement();
#ifdef RPCS3_MVK_USE_REAL_GCD
	constexpr const char* backend = "libdispatch";
#else
	for (const auto& queue : rpcs3_mvk_test_dispatch::queues)
		check(queue->references.load() == 0);
	rpcs3_mvk_test_dispatch::queues.clear();
	constexpr const char* backend = "serial-queue-test-adapter";
#endif
	std::printf("{\"passed\":true,\"assertionsActive\":true,\"checks\":%u,\"backend\":\"%s\",\"intentionalTimeouts\":1,\"metalOrDeviceTested\":false}\n", cases, backend);
}
