// CELL547 scenarios. wait_after/wait_before hold vk::wait_for_fence copied
// verbatim from the 547 tree and the 546 baseline by test/rpcs3_cell547_test.py.

#include <algorithm>
#include <string>

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

static u64 now_ns()
{
	return static_cast<u64>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
}

static u64 thread_cpu_us()
{
	timespec t{};
	clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
	return static_cast<u64>(t.tv_sec) * 1'000'000 + static_cast<u64>(t.tv_nsec) / 1000;
}

struct measured
{
	double cpu_us_mean = 0, wall_us_mean = 0, latency_us_p50 = 0, latency_us_p95 = 0;
	int successes = 0;
	u64 status_calls = 0, wait_calls = 0;
};

template <typename Wait>
static measured measure(Wait&& wait, u64 gpu_us, int reps)
{
	measured m;
	std::vector<double> latency;
	for (int i = 0; i < reps; i++)
	{
		sim_fence sf;
		fence f{&sf};
		std::atomic<u64> signalled_at{0};
		const u64 start = now_ns();
		std::thread gpu([&]
		{
			std::this_thread::sleep_until(std::chrono::steady_clock::time_point(std::chrono::nanoseconds(start + gpu_us * 1000)));
			signalled_at = now_ns();
			sf.signal();
		});
		const u64 cpu0 = thread_cpu_us();
		const VkResult r = wait(&f, 0);
		const u64 end = now_ns();
		const u64 cpu1 = thread_cpu_us();
		gpu.join();
		m.successes += r == VK_SUCCESS;
		m.cpu_us_mean += static_cast<double>(cpu1 - cpu0) / reps;
		m.wall_us_mean += static_cast<double>(end - start) / 1000.0 / reps;
		latency.push_back(end >= signalled_at ? static_cast<double>(end - signalled_at) / 1000.0 : 0.0);
		m.status_calls += sf.status_calls;
		m.wait_calls += sf.wait_calls;
	}
	std::sort(latency.begin(), latency.end());
	m.latency_us_p50 = latency[latency.size() / 2];
	m.latency_us_p95 = latency[std::min(latency.size() - 1, latency.size() * 95 / 100)];
	return m;
}

// K compute threads (the Metal compiler or a busy SPU) plus one waiter thread on
// K cores: how long the compute work takes while the waiter spins or blocks.
template <typename Wait>
static double contended_work_ms(Wait&& wait, unsigned workers, u64 gpu_ms)
{
	std::atomic<bool> go{false};
	std::vector<std::thread> pool;
	std::vector<double> took(workers);
	sim_fence sf;
	fence f{&sf};
	std::thread waiter([&] { while (!go) {} wait(&f, 0); });
	for (unsigned w = 0; w < workers; w++)
	{
		pool.emplace_back([&, w]
		{
			while (!go) {}
			const u64 t0 = now_ns();
			volatile u64 x = w + 1;
			for (u64 i = 0; i < 60'000'000; i++) x = x * 6364136223846793005ull + 1442695040888963407ull;
			took[w] = static_cast<double>(now_ns() - t0) / 1e6;
		});
	}
	go = true;
	for (auto& t : pool) t.join();
	std::this_thread::sleep_for(std::chrono::milliseconds(gpu_ms));
	sf.signal();
	waiter.join();
	return *std::max_element(took.begin(), took.end());
}

int main(int argc, char** argv)
{
	const std::string mode = argc > 1 ? argv[1] : "timing";
	const bool timing = mode == "timing";
	const auto after = [](fence* f, u64 t) { return wait_after::wait_for_fence(f, t); };
	const auto before = [](fence* f, u64 t) { return wait_before::wait_for_fence(f, t); };

	std::string json = "{\"mode\": \"" + mode + "\", \"waits\": [";
	const u64 gpu_times[] = {20, 300, 2000, 8000};
	bool first = true;
	for (const u64 gpu_us : gpu_times)
	{
		const int reps = timing ? 40 : 8;
		const u64 spins_before = rpcs3::ios::fence_wait::spin_completed.load();
		const auto blocked_before = rpcs3::ios::fence_wait::blocked_us.take();
		static_cast<void>(blocked_before);
		const measured a = measure(after, gpu_us, reps);
		const u64 spin_hits = rpcs3::ios::fence_wait::spin_completed.load() - spins_before;
		const auto blocked = rpcs3::ios::fence_wait::blocked_us.take();
		const measured b = measure(before, gpu_us, reps);
		CHECK(a.successes == reps && b.successes == reps);
		CHECK(spin_hits + blocked.count == static_cast<u64>(reps));
		if (gpu_us >= 2000)
		{
			// The 546 body spins for the whole GPU time; 547 spins 100 us then sleeps.
			CHECK(blocked.count == static_cast<u64>(reps) && a.wait_calls >= static_cast<u64>(reps));
			if (timing) CHECK(a.cpu_us_mean < b.cpu_us_mean / 4);
			CHECK(b.wait_calls == 0);
		}
		char line[640];
		std::snprintf(line, sizeof line,
			"%s{\"gpu_us\": %llu, \"reps\": %d, \"after\": {\"cpu_us\": %.1f, \"wall_us\": %.1f, \"wake_p50_us\": %.1f, \"wake_p95_us\": %.1f, \"spin_completed\": %llu, \"blocked\": %llu, \"status_calls\": %llu},"
			" \"before\": {\"cpu_us\": %.1f, \"wall_us\": %.1f, \"wake_p50_us\": %.1f, \"wake_p95_us\": %.1f, \"status_calls\": %llu}}",
			first ? "" : ", ", static_cast<unsigned long long>(gpu_us), reps, a.cpu_us_mean, a.wall_us_mean, a.latency_us_p50, a.latency_us_p95,
			static_cast<unsigned long long>(spin_hits), static_cast<unsigned long long>(blocked.count), static_cast<unsigned long long>(a.status_calls),
			b.cpu_us_mean, b.wall_us_mean, b.latency_us_p50, b.latency_us_p95, static_cast<unsigned long long>(b.status_calls));
		json += line;
		first = false;
	}
	json += "]";

	// A fence slower than one blocking slice (100 ms) keeps waiting, as before.
	{
		const measured slow = measure(after, 250'000, 1);
		CHECK(slow.successes == 1 && slow.wait_calls >= 3);
		json += ", \"slowerThanSlice\": {\"wall_us\": " + std::to_string(slow.wall_us_mean) + ", \"waitCalls\": " + std::to_string(slow.wait_calls) + "}";
	}

	// Device loss is reported once, by both bodies, with the same result.
	for (int body = 0; body < 2; body++)
	{
		sim_fence sf;
		sf.error = VK_ERROR_DEVICE_LOST;
		fence f{&sf};
		const int dies = g_die_calls.load();
		const VkResult r = body ? before(&f, 0) : after(&f, 0);
		CHECK(r == VK_ERROR_DEVICE_LOST && g_die_calls.load() == dies + 1);
	}
	// Timed waits (texture cache) take the unchanged vkWaitForFences path.
	{
		sim_fence sf;
		fence f{&sf};
		sf.signal();
		CHECK(after(&f, 1000) == VK_SUCCESS && sf.wait_calls == 1);
	}

	if (timing)
	{
		const unsigned workers = std::max(1u, std::thread::hardware_concurrency());
		const double spun = contended_work_ms(before, workers, 50);
		const double blocked = contended_work_ms(after, workers, 50);
		const double spun2 = contended_work_ms(before, workers, 50);
		const double blocked2 = contended_work_ms(after, workers, 50);
		json += ", \"contention\": {\"workers\": " + std::to_string(workers) + ", \"workMsWhileSpinning\": [" + std::to_string(spun) + ", " + std::to_string(spun2) +
			"], \"workMsWhileBlocked\": [" + std::to_string(blocked) + ", " + std::to_string(blocked2) + "]}";
		CHECK(std::min(blocked, blocked2) < std::min(spun, spun2));
	}

	// Compile pressure: only builds a draw waits for; nesting and concurrency.
	using namespace rpcs3::ios::compile_pressure;
	static_cast<void>(blocking_build_us.take());
	{
		BlockingBuildScope preload(false);
		CHECK(!active());
	}
	{
		BlockingBuildScope outer(true);
		CHECK(active());
		{
			BlockingBuildScope inner(true);
			CHECK(blocking_builds.load() == 2);
		}
		CHECK(active());
	}
	CHECK(!active() && blocking_build_us.take().count == 2);
	{
		std::vector<std::thread> threads;
		for (int t = 0; t < 8; t++)
			threads.emplace_back([] { for (int i = 0; i < 20000; i++) { BlockingBuildScope s(i % 3 != 0); } });
		for (auto& t : threads) t.join();
		const auto sample = blocking_build_us.take();
		CHECK(!active() && sample.count == 8u * (20000u - 6667u));
		json += ", \"pressure\": {\"scopes\": " + std::to_string(sample.count) + ", \"activeAfter\": " + (active() ? "true" : "false") + "}";
	}

	json += ", \"failures\": " + std::to_string(failures) + "}";
	std::printf("%s\n", json.c_str());
	return failures ? 1 : 0;
}
