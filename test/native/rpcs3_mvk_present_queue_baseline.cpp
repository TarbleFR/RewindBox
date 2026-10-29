// SPDX-License-Identifier: GPL-2.0-only
// Reproduce the delivered Core's two-queue fallback with its unchanged header.
#include "ios/IOSMoltenVKExecQueue.h"
#include <cassert>
#include <cstdio>

#ifdef NDEBUG
#error "The baseline reproduction requires active assertions"
#endif

int main()
{
	using rpcs3::ios::moltenvk_exec::gcd::registry;
	auto& queues = registry::instance();
	queues.begin_device();
	auto present = dispatch_queue_create("MoltenVKQueue-0-0-0.0-Dispatch", DISPATCH_QUEUE_SERIAL);
	auto transfer = dispatch_queue_create("MoltenVKQueue-0-1-0.0-Dispatch", DISPATCH_QUEUE_SERIAL);
	queues.record(present, "MoltenVKQueue-0-0-0.0-Dispatch");
	queues.record(transfer, "MoltenVKQueue-0-1-0.0-Dispatch");
	assert(queues.queue_count() == 2);
	assert(queues.mark_present() == 0);
	queues.begin_device();
	dispatch_release(present);
	dispatch_release(transfer);
#ifndef RPCS3_MVK_USE_REAL_GCD
	assert(present->references.load() == 0 && transfer->references.load() == 0);
	rpcs3_mvk_test_dispatch::queues.clear();
#endif
	std::puts("{\"passed\":true,\"assertionsActive\":true,\"deliveredTwoQueueFallbackReproduced\":true,\"queueCount\":2,\"presentTicket\":0}");
}
