// SPDX-License-Identifier: GPL-2.0-only
// Test scaffolding, never shipped: the few libdispatch calls that rpcs3/ios/IOSMoltenVKExecQueue.h makes, on a
// std::thread, so that the registry itself runs unchanged on a host without libdispatch (Linux). A queue is serial:
// one worker runs the jobs in the order they were queued, as a DISPATCH_QUEUE_SERIAL queue does. On macOS the tests
// include the real <dispatch/dispatch.h> instead (this directory is not on their include path).
#pragma once

#include <atomic>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <utility>

struct dispatch_queue_s
{
	using function = void (*)(void*);

	explicit dispatch_queue_s(const char* label) : m_label(label ? label : ""), m_worker([this] { run(); })
	{
	}

	~dispatch_queue_s()
	{
		{
			std::lock_guard lock(m_mutex);
			m_stop = true;
		}
		m_cv.notify_all();
		m_worker.join();
	}

	void async(void* context, function work)
	{
		{
			std::lock_guard lock(m_mutex);
			m_jobs.emplace_back(context, work);
		}
		m_cv.notify_all();
	}

	void sync(void* context, function work)
	{
		struct waiter
		{
			std::mutex mutex;
			std::condition_variable cv;
			bool done = false;
			void* context = nullptr;
			function work = nullptr;
		} state;
		state.context = context;
		state.work = work;
		async(&state, [](void* raw)
		{
			auto* item = static_cast<waiter*>(raw);
			item->work(item->context);
			// Notified under the lock: the waiter owns this state and destroys it as soon as it can lock again.
			std::lock_guard lock(item->mutex);
			item->done = true;
			item->cv.notify_all();
		});
		std::unique_lock lock(state.mutex);
		state.cv.wait(lock, [&state] { return state.done; });
	}

	std::atomic<int> references{1};

private:
	void run()
	{
		std::unique_lock lock(m_mutex);
		for (;;)
		{
			m_cv.wait(lock, [this] { return m_stop || !m_jobs.empty(); });
			if (m_jobs.empty())
			{
				return; // stopped and drained
			}

			const auto job = m_jobs.front();
			m_jobs.pop_front();
			lock.unlock();
			job.second(job.first);
			lock.lock();
		}
	}

	std::string m_label;
	std::mutex m_mutex;
	std::condition_variable m_cv;
	std::deque<std::pair<void*, function>> m_jobs;
	bool m_stop = false;
	std::thread m_worker;
};

using dispatch_queue_t = dispatch_queue_s*;
using dispatch_queue_attr_t = const void*;
inline constexpr dispatch_queue_attr_t DISPATCH_QUEUE_SERIAL = nullptr;

inline dispatch_queue_t dispatch_queue_create(const char* label, dispatch_queue_attr_t)
{
	return new dispatch_queue_s(label);
}

inline void dispatch_retain(dispatch_queue_t queue)
{
	queue->references.fetch_add(1, std::memory_order_relaxed);
}

inline void dispatch_release(dispatch_queue_t queue)
{
	if (queue->references.fetch_sub(1, std::memory_order_acq_rel) == 1)
	{
		delete queue;
	}
}

inline void dispatch_async_f(dispatch_queue_t queue, void* context, void (*work)(void*))
{
	queue->async(context, work);
}

inline void dispatch_sync_f(dispatch_queue_t queue, void* context, void (*work)(void*))
{
	queue->sync(context, work);
}
