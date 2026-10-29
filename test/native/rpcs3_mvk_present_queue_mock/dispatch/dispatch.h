// SPDX-License-Identifier: GPL-2.0-only
#pragma once

// Test adapter for systems without libdispatch. Each queue has its own serial
// worker. This does not emulate Metal, Vulkan or the iOS scheduler.
#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <future>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

#ifndef __has_feature
#define __has_feature(x) 0
#endif

namespace rpcs3_mvk_test_dispatch
{
struct queue
{
	struct item { void* context; void (*function)(void*); };
	std::atomic<int> references{1};
	std::atomic<unsigned> sync_calls{0};
	std::mutex mutex;
	std::condition_variable cv;
	std::deque<item> pending;
	bool stop = false;
	std::thread worker;

	queue() : worker([this]
	{
		std::unique_lock lock(mutex);
		for (;;)
		{
			cv.wait(lock, [&] { return stop || !pending.empty(); });
			if (pending.empty()) return;
			const item work = pending.front();
			pending.pop_front();
			lock.unlock();
			work.function(work.context);
			lock.lock();
		}
	}) {}

	~queue()
	{
		{
			std::lock_guard lock(mutex);
			stop = true;
		}
		cv.notify_one();
		worker.join();
	}

	void push(void* context, void (*function)(void*))
	{
		{
			std::lock_guard lock(mutex);
			pending.push_back({context, function});
		}
		cv.notify_one();
	}
};

// The fixture owns allocation until cleanup; reference counts independently
// check every production hold/release, including device replacement.
inline std::vector<std::unique_ptr<queue>> queues;
}

using dispatch_queue_t = rpcs3_mvk_test_dispatch::queue*;
using dispatch_queue_attr_t = int;
inline constexpr dispatch_queue_attr_t DISPATCH_QUEUE_SERIAL = 0;

inline dispatch_queue_t dispatch_queue_create(const char*, dispatch_queue_attr_t)
{
	auto q = std::make_unique<rpcs3_mvk_test_dispatch::queue>();
	const auto pointer = q.get();
	rpcs3_mvk_test_dispatch::queues.push_back(std::move(q));
	return pointer;
}

inline void dispatch_retain(dispatch_queue_t queue)
{
	if (queue->references.fetch_add(1) <= 0) std::abort();
}

inline void dispatch_release(dispatch_queue_t queue)
{
	if (queue->references.fetch_sub(1) <= 0) std::abort();
}

inline void dispatch_async_f(dispatch_queue_t queue, void* context, void (*function)(void*))
{
	queue->push(context, function);
}

inline void dispatch_sync_f(dispatch_queue_t queue, void* context, void (*function)(void*))
{
	struct sync_item
	{
		void* context;
		void (*function)(void*);
		std::promise<void> complete;
	};
	auto* work = new sync_item{context, function, {}};
	auto complete = work->complete.get_future();
	queue->sync_calls.fetch_add(1);
	queue->push(work, [](void* context)
	{
		std::unique_ptr<sync_item> item{static_cast<sync_item*>(context)};
		item->function(item->context);
		item->complete.set_value();
	});
	complete.get();
}
