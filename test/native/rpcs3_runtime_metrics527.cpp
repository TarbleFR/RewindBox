#include "rpcs3/ios/IOSRuntimeMetrics.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>
#include <atomic>
using namespace rpcs3::ios::diagnostics;
using u64 = std::uint64_t;
using u32 = std::uint32_t;
namespace utils { static u64 tsc = 0; u64 get_tsc() { return tsc; } u64 get_tsc_freq() { return 1'000'000; } }
struct ProductionHooks
{
    GuestFrameWindow m_guest_frame_window;
    std::array<EventCost, 7> m_event_costs{};
    std::atomic<u64> m_guest_frames{0}, m_pipeline_completed{0}, m_pipeline_queue_ticks{0}, m_pipeline_compile_ticks{0};
    std::atomic<u64> m_gpu_fence_waits{0}, m_gpu_fence_wait_ticks{0}, m_gpu_fence_timeouts{0};
    std::atomic<u64> m_rsx_semaphore_waits{0}, m_rsx_semaphore_wait_us{0}, m_rsx_semaphore_timeouts{0};
    std::atomic<u32> m_native_ui_visible{0};
    std::atomic_bool m_has_flip_info{false};
#include "production_methods.inc"
};

int main()
{
    ProductionHooks hooks;
    utils::tsc = 1000; hooks.record_flip(true, false);
    utils::tsc = 2000; hooks.record_flip(false, true);
    utils::tsc = 18000; hooks.record_flip(true, false);
    assert(hooks.m_guest_frame_window.take().median_us == 17000);
    assert(hooks.m_guest_frames == 2 && hooks.m_has_flip_info && !hooks.m_native_ui_visible);
    hooks.record_pipeline_job_completed(100, 200);
    hooks.record_gpu_fence_wait(300, true);
    hooks.record_rsx_semaphore_wait(400, true);
    assert(hooks.m_event_costs[0].take().total == 100 && hooks.m_event_costs[1].take().maximum == 200);
    assert(hooks.m_event_costs[2].take().total == 300 && hooks.m_gpu_fence_timeouts == 1);
    assert(hooks.m_event_costs[4].take().maximum == 400 && hooks.m_rsx_semaphore_timeouts == 1);
    GuestFrameWindow frames;
    frames.record(true, 1'000'000, 1'000'000);
    frames.record(false, 1'001'000, 1'000'000);
    frames.record(true, 1'016'000, 1'000'000);
    auto a = frames.take();
    assert(a.intervals == 1 && a.median_us == 16'000 && a.maximum_us == 16'000);
    assert(a.unavailable == 0 && frames.take().intervals == 0);
    // Guest/UI distinction: the UI timestamp above must not become the baseline.
    for (unsigned i = 1; i <= 100; ++i) frames.record(true, 1'016'000ull + i * i * 1'000ull, 1'000'000);
    a = frames.take();
    assert(a.intervals == 100 && a.median_us == 99'000 && a.p95_us == 189'000 && a.p99_us == 197'000 && a.maximum_us == 199'000);
    assert(a.over_50ms == 75 && a.over_100ms == 50);
    std::uint64_t histogram_count = 0;
    for (const auto count : a.histogram) histogram_count += count;
    assert(histogram_count == a.intervals);
    assert(GuestFrameWindow::histogram_upper_us(0) == 999 && GuestFrameWindow::histogram_upper_us(127) == 127999);
    assert(GuestFrameWindow::histogram_upper_us(128) == 135999 && GuestFrameWindow::histogram_upper_us(255) == UINT32_MAX);
    frames.reset();
    assert(frames.take().intervals == 0);
    frames.record(true, 5, 1'000'000);
    frames.record(true, 10, 0); // invalid frequency cannot advance baseline
    frames.record(true, 15, 1'000'000);
    assert(frames.take().median_us == 10);
    frames.record(true, 12, 1'000'000); // non-monotonic clock cannot create interval
    assert(frames.take().intervals == 0);
    frames.reset();
    frames.record(true, 1, 1'000'000);
    frames.record(true, UINT64_MAX, 1'000'000);
    assert(frames.take().maximum_us == UINT32_MAX);
    frames.reset();
    frames.record(true, 1, 1'000'000);
    for (unsigned i = 1; i <= 4000; ++i) frames.record(true, i * 100ull + 1, 1'000'000);
    a = frames.take();
    assert(a.intervals == GuestFrameWindow::capacity && a.unavailable == 4000 - GuestFrameWindow::capacity && a.median_us == 100);
    // Concurrent reader never observes a torn sequence/timestamp pair. If the
    // writer overwrites a slot, the unavailable count accounts for it.
    frames.reset();
    frames.record(true, 1, 1'000'000);
    std::atomic<bool> done{false};
    std::thread producer([&] {
        for (unsigned i = 1; i <= 250'000; ++i) frames.record(true, 1 + i * 100ull, 1'000'000);
        done.store(true, std::memory_order_release);
    });
    std::uint64_t consumed = 0;
    while (!done.load(std::memory_order_acquire))
    {
        const auto sample = frames.take();
        consumed += sample.intervals + sample.unavailable;
        if (sample.intervals) assert(sample.median_us == 100 && sample.maximum_us == 100);
    }
    producer.join();
    a = frames.take(); consumed += a.intervals + a.unavailable;
    assert(consumed == 250'000);
    EventCost cost;
    cost.record(0); cost.record(123); cost.record(456);
    auto c = cost.take(); assert(c.count == 3 && c.total == 579 && c.maximum == 456);
    c = cost.take(); assert(!c.count && !c.total && !c.maximum);
    std::vector<std::thread> threads;
    std::atomic<unsigned> active{8};
    for (unsigned i = 0; i < 8; ++i) threads.emplace_back([&] {
        for (unsigned j = 0; j < 100'000; ++j) cost.record(7);
        active.fetch_sub(1, std::memory_order_release);
    });
    std::uint64_t count = 0, total = 0, maximum = 0;
    do { c = cost.take(); count += c.count; total += c.total; maximum = std::max(maximum, c.maximum); }
    while (active.load(std::memory_order_acquire));
    for (auto& thread : threads) thread.join();
    c = cost.take(); count += c.count; total += c.total; maximum = std::max(maximum, c.maximum);
    assert(count == 800'000 && total == 5'600'000 && maximum == 7);
    ProcessMemoryWindow memory;
    memory.record({}); assert(!memory.samples && !memory.latest.valid);
    memory.record({true, 100, 200, 20, 1'000});
    memory.record({true, 90, 250, 10, 800});
    assert(memory.samples == 2 && memory.peak.footprint == 100 && memory.peak.resident == 250 && memory.peak.compressed == 20 && memory.peak.virtual_bytes == 1000);
    assert(memory.latest.footprint == 90 && memory.latest.virtual_bytes == 800);
    memory.reset(); assert(!memory.samples && !memory.peak.valid && !memory.latest.valid);
    std::printf("PASS guest-only frames, bounded ring, percentiles, reset, clock limits, concurrent overwrite and event drains, distinct memory peaks\n");
}
