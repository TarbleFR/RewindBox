// CELL587 host tests: the encoding-queue label, the present tracker and the boot
// canary of the RPCS3 Core 587 (rpcs3/ios/IOSMoltenVKExec.h,
// IOSMoltenVKAsyncCanary.h), and a model of the hazard the barrier removes.
//
// The model replays MoltenVK 1.4.2's own swapchain rules on a serial queue
// thread: vkAcquireNextImageKHR picks the image with the smallest
// (unavailable, acquisition ID) pair and releases its drawable at once
// (MVKSwapchain::acquireNextImage, MVKPresentableSwapchainImage::
// acquireAndSignalWhenAvailable, MVKImage.mm:1565); an image becomes available
// again when its present runs on the queue with no acquisition waiting for it
// (getPresentationSignaler, MVKImage.mm:1686); renders and presents fetch the
// drawable when the queue runs them. RPCS3's pacing is kept: a frame context is
// reused only after the render of the frame that used it three flips earlier
// has run (frame_context_cleanup). A release while the queue still holds a
// render or present of that image is the hazard. The queue thread stalls
// between a render and its present on chosen flips, as a preempted GCD thread
// does. It is a model of MoltenVK's logic, not MoltenVK.
#include "ios/IOSMoltenVKAsyncCanary.h"
#include "ios/IOSMoltenVKExec.h"

#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace exec = rpcs3::ios::moltenvk_exec;
namespace canary = rpcs3::ios::mvk_async_canary;

static int g_failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); g_failures++; } } while (0)

static void labels()
{
	static_assert(exec::is_exec_queue_label("MoltenVKQueue-0-0-1.0-Dispatch"));
	static_assert(exec::is_exec_queue_label("MoltenVKQueue-2-1-0.5-Dispatch"));
	static_assert(!exec::is_exec_queue_label("MoltenVKQueue--Dispatch"));
	static_assert(!exec::is_exec_queue_label("MoltenVKQueue-0-0-1.0"));
	static_assert(!exec::is_exec_queue_label("com.apple.main-thread"));
	static_assert(!exec::is_exec_queue_label(""));
	CHECK(exec::is_exec_queue_label(std::string("MoltenVKQueue-0-0-") + "0.0-Dispatch"));
}

static void tracker()
{
	using result = exec::present_tracker::wait_result;
	exec::present_tracker presents;
	CHECK(presents.wait(0) == result::ready);
	const auto t1 = presents.issue(100), t2 = presents.issue(200), t3 = presents.issue(300);
	CHECK(t1 == 1 && t2 == 2 && t3 == 3);
	CHECK(!presents.completed(t1));
	CHECK(presents.wait(t1, std::chrono::milliseconds(20)) == result::timed_out);
	CHECK(presents.complete(t1, 1100) == 1000);
	CHECK(presents.completed(t1) && !presents.completed(t2));
	// A later ticket completes the earlier ones; a stale completion changes nothing.
	CHECK(presents.complete(t3, 1300) == 1000);
	CHECK(presents.completed(t2) && presents.wait(t2) == result::ready);
	CHECK(presents.complete(t2, 5000) == 0);

	// Completion from another thread wakes the waiter.
	const auto t4 = presents.issue(0);
	std::thread worker([&] {
		std::this_thread::sleep_for(std::chrono::milliseconds(30));
		presents.complete(t4, 30000);
	});
	CHECK(presents.wait(t4, std::chrono::milliseconds(2000)) == result::waited);
	worker.join();

	// Many tickets completed in order by one thread while another waits for each.
	std::vector<std::uint64_t> tickets;
	for (int i = 0; i < 2000; i++)
	{
		tickets.push_back(presents.issue(static_cast<std::uint64_t>(i)));
	}
	std::thread completer([&] {
		for (const auto ticket : tickets)
		{
			presents.complete(ticket, ticket);
		}
	});
	bool all = true;
	for (const auto ticket : tickets)
	{
		all = presents.wait(ticket, std::chrono::milliseconds(2000)) != result::timed_out && all;
	}
	completer.join();
	CHECK(all);

	std::atomic<std::uint64_t> maximum{5};
	exec::record_max(maximum, 3);
	exec::record_max(maximum, 9);
	CHECK(maximum.load() == 9);
}

static void canary_states()
{
	using canary::state;
	using canary::verdict;
	std::vector<canary::record> records;

	// First boot: armed; the record file would now say armed.
	CHECK(canary::on_boot(records, "BCES00510", true) == verdict::run);
	CHECK(records.size() == 1 && records[0].value == state::armed);
	CHECK(canary::serialize(records) == "BCES00510 armed\n");
	// Confirmed after the presents (or a clean shutdown): ok, once.
	CHECK(canary::on_confirm(records, "BCES00510"));
	CHECK(!canary::on_confirm(records, "BCES00510"));
	CHECK(records[0].value == state::ok);
	// Next boot runs again.
	CHECK(canary::on_boot(records, "BCES00510", true) == verdict::run);
	// That boot crashed: the next one finds the title armed.
	auto after_crash = canary::parse(canary::serialize(records));
	CHECK(canary::on_boot(after_crash, "BCES00510", true) == verdict::previous_boot_failed);
	CHECK(after_crash[0].value == state::failed);
	// Failed stays failed, requested or not, and is never confirmed.
	CHECK(canary::on_boot(after_crash, "BCES00510", true) == verdict::failed_before);
	CHECK(canary::on_boot(after_crash, "BCES00510", false) == verdict::off);
	CHECK(!canary::on_confirm(after_crash, "BCES00510"));
	CHECK(canary::serialize(after_crash) == "BCES00510 failed\n");

	// An armed title whose next boot does not request them is failed too.
	std::vector<canary::record> other{{"BCUS98111", state::armed}};
	CHECK(canary::on_boot(other, "BCUS98111", false) == verdict::previous_boot_failed);
	CHECK(other[0].value == state::failed);

	// Not requested: nothing written; an invalid title never runs.
	std::vector<canary::record> empty;
	CHECK(canary::on_boot(empty, "BLES01658", false) == verdict::off && empty.empty());
	CHECK(canary::on_boot(empty, "", true) == verdict::invalid_title && empty.empty());
	CHECK(canary::on_boot(empty, "bces00510", true) == verdict::invalid_title && empty.empty());

	// Parsing: unknown states, bad titles and malformed lines are ignored; the last line of a title wins.
	const auto parsed = canary::parse("BCES00510 ok\ngarbage\nBLES01658 maybe\nbces00510 armed\nBCES00510 armed\n\nBCES0051 ok\nBCAS25003 failed");
	CHECK(parsed.size() == 2);
	CHECK(parsed[0].title == "BCES00510" && parsed[0].value == state::armed);
	CHECK(parsed[1].title == "BCAS25003" && parsed[1].value == state::failed);
	CHECK(canary::parse(canary::serialize(parsed)).size() == 2);
	CHECK(canary::verdict_name(verdict::previous_boot_failed) == "previous_boot_failed");
	CHECK(canary::file_name == "rewindbox-mvk-async-587.txt" && canary::confirm_presents == 900);
}

// ---- Model of MoltenVK's swapchain on its encoding queue -----------------------------
struct swapchain_model
{
	struct image
	{
		bool available = true;
		std::uint64_t acquisition = 0;
		std::uint32_t waiting = 0;        // acquisitions queued while unavailable
		std::uint32_t queued_users = 0;   // renders and presents queued, not yet run
	};

	std::mutex lock;
	std::array<image, 3> images{};
	std::uint64_t next_acquisition = 0;
	std::uint64_t hazards = 0;

	swapchain_model()
	{
		for (auto& img : images)
		{
			img.acquisition = ++next_acquisition;
		}
	}

	// MVKSwapchain::acquireNextImage + acquireAndSignalWhenAvailable.
	std::uint32_t acquire()
	{
		std::lock_guard guard(lock);
		std::uint32_t best = 0;
		for (std::uint32_t i = 1; i < images.size(); i++)
		{
			const auto& a = images[i];
			const auto& b = images[best];
			if (a.available != b.available ? a.available : a.acquisition < b.acquisition)
			{
				best = i;
			}
		}

		auto& img = images[best];
		// releaseMetalDrawable(): the queue still has work that fetches this drawable.
		if (img.queued_users)
		{
			hazards++;
		}

		img.acquisition = ++next_acquisition;
		if (img.available)
		{
			img.available = false;
		}
		else
		{
			img.waiting++;
		}

		return best;
	}

	void queued(std::uint32_t index)
	{
		std::lock_guard guard(lock);
		images[index].queued_users++;
	}

	void ran_render(std::uint32_t index)
	{
		std::lock_guard guard(lock);
		images[index].queued_users--;
	}

	// presentCAMetalDrawable -> getPresentationSignaler.
	void ran_present(std::uint32_t index)
	{
		std::lock_guard guard(lock);
		auto& img = images[index];
		img.queued_users--;
		if (img.waiting)
		{
			img.waiting--;
		}
		else
		{
			img.available = true;
		}
	}
};

// A serial queue: jobs run in submission order on one thread.
class serial_queue
{
	std::mutex m_mutex;
	std::condition_variable m_cv;
	std::deque<std::function<void()>> m_jobs;
	bool m_stop = false;
	std::thread m_thread;

public:
	serial_queue() : m_thread([this] { run(); }) {}

	~serial_queue()
	{
		{
			std::lock_guard lock(m_mutex);
			m_stop = true;
		}
		m_cv.notify_all();
		m_thread.join();
	}

	void async(std::function<void()> job)
	{
		{
			std::lock_guard lock(m_mutex);
			m_jobs.push_back(std::move(job));
		}
		m_cv.notify_all();
	}

private:
	void run()
	{
		for (;;)
		{
			std::function<void()> job;
			{
				std::unique_lock lock(m_mutex);
				m_cv.wait(lock, [&] { return m_stop || !m_jobs.empty(); });
				if (m_jobs.empty())
				{
					return;
				}
				job = std::move(m_jobs.front());
				m_jobs.pop_front();
			}
			job();
		}
	}
};

struct model_result
{
	std::uint64_t hazards = 0;
	std::uint64_t waits = 0;
	double wait_ms = 0;
};

// flips back to back, as the shader cache dialog does; the queue thread stalls for
// stall_us between the render and the present of every stall_every-th flip.
static model_result run_model(bool barrier, int flips, int stall_every, int stall_us)
{
	swapchain_model chain;
	exec::present_tracker presents;
	std::vector<std::atomic<bool>> rendered(static_cast<std::size_t>(flips));
	std::uint64_t last_ticket = 0;
	model_result result;
	{
		serial_queue queue;
		for (int flip = 0; flip < flips; flip++)
		{
			// frame_context_cleanup: three frame contexts.
			if (flip >= 3)
			{
				while (!rendered[static_cast<std::size_t>(flip - 3)].load(std::memory_order_acquire))
				{
					std::this_thread::yield();
				}
			}

			if (barrier && last_ticket)
			{
				const auto begin = std::chrono::steady_clock::now();
				if (presents.wait(last_ticket) == exec::present_tracker::wait_result::waited)
				{
					result.waits++;
					result.wait_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
				}
			}

			const std::uint32_t image = chain.acquire();
			chain.queued(image);
			const bool stall = stall_every && flip % stall_every == stall_every - 1;
			queue.async([&, image, flip, stall] {
				std::this_thread::sleep_for(std::chrono::microseconds(200));
				chain.ran_render(image);
				rendered[static_cast<std::size_t>(flip)].store(true, std::memory_order_release);
				if (stall)
				{
					std::this_thread::sleep_for(std::chrono::microseconds(stall_us));
				}
			});
			chain.queued(image);
			queue.async([&, image] { chain.ran_present(image); });
			if (barrier)
			{
				const std::uint64_t ticket = presents.issue(0);
				queue.async([&presents, ticket] { presents.complete(ticket, 0); });
				last_ticket = ticket;
			}
		}
	}

	result.hazards = chain.hazards;
	return result;
}

static void model()
{
	// The queue thread is preempted after the render of every 8th flip: the next
	// acquisitions overtake that present unless they wait for it.
	const auto without = run_model(false, 400, 8, 3000);
	const auto with = run_model(true, 400, 8, 3000);
	std::printf("{\"model\":{\"flips\":400,\"stallEvery\":8,\"stallUs\":3000,"
		"\"hazardsWithoutBarrier\":%llu,\"hazardsWithBarrier\":%llu,\"barrierWaits\":%llu,\"barrierWaitMs\":%.3f}}\n",
		static_cast<unsigned long long>(without.hazards), static_cast<unsigned long long>(with.hazards),
		static_cast<unsigned long long>(with.waits), with.wait_ms);
	CHECK(without.hazards > 0);
	CHECK(with.hazards == 0);

	// Without stalls a fast queue thread rarely lets an acquisition overtake; the
	// barrier still never allows it.
	CHECK(run_model(true, 300, 0, 0).hazards == 0);
}

int main()
{
	labels();
	tracker();
	canary_states();
	model();
	std::printf("{\"failures\":%d}\n", g_failures);
	return g_failures ? 1 : 0;
}
