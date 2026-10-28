// CELL587 on the real libdispatch (macOS): the registry of rpcs3/ios/IOSMoltenVKExecQueue.h,
// compiled unchanged, records a queue created the way MoltenVK 1.4.2 creates its
// encoding queue (MVKQueue::initExecQueue: serial, user-interactive for the high
// global priority), through a hook equal to rbx_mvk_exec_q_create. Jobs queued on
// it stand for MoltenVK's submissions and presents.
#include "ios/IOSMoltenVKExecQueue.h"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <thread>

namespace exec = rpcs3::ios::moltenvk_exec;
using exec::gcd::registry;

static int g_failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); g_failures++; } } while (0)

// RPCS3IOSPlatform.mm's rbx_mvk_exec_q_create, minus the C linkage.
static dispatch_queue_t hook(const char* label, dispatch_queue_attr_t attr)
{
	dispatch_queue_t queue = dispatch_queue_create(label, attr);
	registry::instance().record(queue, label);
	return queue;
}

struct job
{
	std::atomic<bool> done{false};
	int sleep_ms = 0;
};

static void run_job(void* context)
{
	auto* item = static_cast<job*>(context);
	std::this_thread::sleep_for(std::chrono::milliseconds(item->sleep_ms));
	item->done.store(true, std::memory_order_release);
}

static double ms_since(std::chrono::steady_clock::time_point begin)
{
	return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
}

int main()
{
	auto& queues = registry::instance();
	queues.begin_device();
	CHECK(queues.queue_count() == 0 && queues.mark_present() == 0);

	const dispatch_queue_attr_t attr = dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INTERACTIVE, 0);
	dispatch_queue_t other = hook("com.example.not-moltenvk", attr);
	CHECK(queues.queue_count() == 0);
	dispatch_queue_t mvk = hook("MoltenVKQueue-0-0-1.0-Dispatch", attr);
	CHECK(queues.queue_count() == 1 && exec::exec_queues.load() == 1);

	// A render being encoded, the present behind it, then later submissions.
	job render, present, later;
	render.sleep_ms = 60;
	present.sleep_ms = 5;
	later.sleep_ms = 300;
	dispatch_async_f(mvk, &render, run_job);
	dispatch_async_f(mvk, &present, run_job);
	const std::uint64_t ticket = queues.mark_present();
	CHECK(ticket != 0);
	dispatch_async_f(mvk, &later, run_job);

	auto begin = std::chrono::steady_clock::now();
	queues.wait_for_present(ticket);
	const double waited = ms_since(begin);
	CHECK(render.done.load(std::memory_order_acquire) && present.done.load(std::memory_order_acquire));
	CHECK(!later.done.load(std::memory_order_acquire)); // the barrier stops at the present
	CHECK(waited >= 40 && waited < 280);
	CHECK(exec::acquire_waits.load() == 1 && exec::acquire_timeouts.load() == 0);
	CHECK(exec::presents_marked.load() == 1);

	// Already run: no wait, no count.
	queues.wait_for_present(ticket);
	CHECK(exec::acquire_waits.load() == 1);

	// drain() waits for everything queued so far.
	begin = std::chrono::steady_clock::now();
	queues.drain();
	CHECK(later.done.load(std::memory_order_acquire));
	CHECK(exec::drains.load() == 1);
	const double drained = ms_since(begin);

	// Back-to-back presents (the shader cache dialog): each acquisition waits only for
	// the previous present.
	std::uint64_t last = 0;
	job frames[50];
	for (auto& frame : frames)
	{
		queues.wait_for_present(last);
		frame.sleep_ms = 1;
		dispatch_async_f(mvk, &frame, run_job);
		last = queues.mark_present();
	}
	queues.wait_for_present(last);
	bool all = true;
	for (auto& frame : frames)
	{
		all = frame.done.load(std::memory_order_acquire) && all;
	}
	CHECK(all);
	CHECK(exec::acquire_timeouts.load() == 0);

	// MoltenVK destroys its queue (dispatch_release); the registry's reference keeps
	// the object valid until the next device replaces it.
	dispatch_release(mvk);
	queues.drain();
	queues.begin_device();
	CHECK(queues.queue_count() == 0 && exec::exec_queues.load() == 0 && queues.mark_present() == 0);
	queues.drain();
	dispatch_release(other);

	std::printf("{\"gcd\":{\"presentWaitMs\":%.3f,\"drainMs\":%.3f,\"markerLagMaxMs\":%.3f,\"failures\":%d}}\n",
		waited, drained, exec::marker_lag_max_us.load() / 1000.0, g_failures);
	return g_failures ? 1 : 0;
}
