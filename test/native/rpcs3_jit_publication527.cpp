// SPDX-License-Identifier: MIT
// Tests the production publication queue; no LLVM, game or device is simulated.
#include "Utilities/JITPublicationQueue.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

static std::uint64_t checks = 0;
static void require(bool ok) { ++checks; if (!ok) std::abort(); }
static std::uint64_t clock_ticks()
{
	return std::chrono::steady_clock::now().time_since_epoch().count();
}

template <bool Retain> void lifecycle()
{
	jit_publication::queue<Retain> queue;
	std::vector<std::uintptr_t> published;
	auto flush = [&](void* address, std::size_t size) {
		require(size == 64);
		published.push_back(reinterpret_cast<std::uintptr_t>(address));
	};
	queue.publish(flush, clock_ticks, true);
	require(published.empty());
	for (unsigned generation = 0; generation < 500; ++generation)
	{
		for (unsigned item = 0; item < 3; ++item)
			queue.add(reinterpret_cast<void*>(1 + generation * 3 + item), 64);
		require(queue.pending() == 3);
		queue.publish(flush, clock_ticks, true);
		require(queue.pending() == 0);
		const auto count = published.size();
		for (unsigned lookup = 0; lookup < 5; ++lookup)
			queue.publish(flush, clock_ticks, true);
		require(published.size() == count);
		if constexpr (Retain) require(queue.allocations().size() == (generation + 1) * 3);
		else require(queue.allocations().empty());
	}
	require(published.size() == 1500);
	for (unsigned index = 0; index < published.size(); ++index) require(published[index] == index + 1);
	if constexpr (!Retain) require(queue.metadata_bytes() <= 4 * sizeof(jit_publication::range));
	// A recoverable resolver failure occurs before finalization's flush. LLVM
	// keeps old relocations: all ranges must remain dirty until clean success.
	queue.add(reinterpret_cast<void*>(5001), 64);
	queue.publish(flush, clock_ticks, false);
	require(queue.pending() == 1);
	queue.add(reinterpret_cast<void*>(5002), 64);
	queue.publish(flush, clock_ticks, true);
	require(queue.pending() == 0);
	require(published[published.size() - 2] == 5001 && published.back() == 5002);
	// If publication aborts partway through, retry the whole dirty suffix.
	queue.add(reinterpret_cast<void*>(6001), 64);
	queue.add(reinterpret_cast<void*>(6002), 64);
	bool threw = false;
	try { queue.publish([](void*, std::size_t) { throw std::runtime_error("flush"); }, clock_ticks, true); }
	catch (const std::runtime_error&) { threw = true; }
	require(threw && queue.pending() == 2);
	queue.publish(flush, clock_ticks, true);
	require(queue.pending() == 0 && published.back() == 6002);
}

static void concurrency()
{
	// Production uses one MCJIT lock per queue. Exercise the same ownership
	// with concurrent producers/finalizers, plus independent manager queues.
	std::mutex engine_lock;
	jit_publication::queue<true> queue;
	std::uint64_t flushed = 0;
	auto flush = [&](void*, std::size_t) { ++flushed; };
	std::vector<std::thread> workers;
	for (unsigned worker = 0; worker < 6; ++worker)
		workers.emplace_back([&, worker] {
			jit_publication::queue<false> independent;
			for (unsigned index = 0; index < 1000; ++index)
			{
				independent.add(reinterpret_cast<void*>(1 + worker * 1000 + index), 16);
				independent.publish([](void*, std::size_t) {}, clock_ticks, true);
				std::lock_guard lock(engine_lock);
				queue.add(reinterpret_cast<void*>(1 + worker * 1000 + index), 16);
				if (index % 7 == 0) queue.publish(flush, clock_ticks, true);
			}
		});
	for (auto& worker : workers) worker.join();
	queue.publish(flush, clock_ticks, true);
	require(flushed == 6000 && queue.pending() == 0);
}

int main()
{
	const auto initial_metadata = jit_publication::metrics().retained_metadata_bytes.load();
	for (unsigned session = 0; session < 8; ++session) { lifecycle<true>(); lifecycle<false>(); }
	concurrency();
	const auto report = jit_publication::metrics().exchange();
	require(report.retained_metadata_bytes == initial_metadata);
	require(report.deferred_calls == 16);
	require(report.calls > report.dirty_ranges);
	std::printf("{\"passed\":true,\"checks\":%llu,\"publication_calls\":%llu,\"history_ranges\":%llu,\"flushed_ranges\":%llu,\"deferred_calls\":%llu,\"metadata_after\":%llu,\"physical_device\":false}\n",
		static_cast<unsigned long long>(checks), static_cast<unsigned long long>(report.calls),
		static_cast<unsigned long long>(report.history_ranges), static_cast<unsigned long long>(report.dirty_ranges),
		static_cast<unsigned long long>(report.deferred_calls), static_cast<unsigned long long>(report.retained_metadata_bytes));
}
