#include "ios/IOSFrameTrace.h"
#include <cassert>
#include <cmath>
#include <iostream>
#include <thread>
#include <vector>

using namespace rpcs3::ios::frame_trace;

Frame row(std::uint64_t frame, std::uint64_t ticks, bool sampled = false)
{
    Frame result;
    result.frame = frame;
    result.end_ticks = ticks;
    result.frequency = 1'000'000;
    result.stages_sampled = sampled;
    result.draws = frame * 3;
    result.vertex_us = frame * 5;
    return result;
}

int main()
{
    // The observed GOW3 shape: thirteen short completed intervals must not
    // become a claim of 60 FPS over a five-second blocked report window.
    const auto blocked = progress(13, 5078.760, 13, 215742, 1'000'000, 5'863'018, 1'000'000);
    assert(blocked.wall_guest_fps > 2.55 && blocked.wall_guest_fps < 2.57);
    assert(blocked.completed_interval_fps > 60.25 && blocked.completed_interval_fps < 60.26);
    assert(blocked.last_guest_flip_age_ms == 4863.018);
    const auto none = progress(0, 5000, 0, 0, 0, 100, 0);
    assert(none.wall_guest_fps == 0 && none.completed_interval_fps == 0 && none.last_guest_flip_age_ms == -1);
    const auto no_new_flip = progress(0, 5000, 0, 0, 1000, 6'001'000, 1'000'000);
    assert(no_new_flip.wall_guest_fps == 0 && no_new_flip.last_guest_flip_age_ms == 6000);
    const auto empty_window = progress(30, 0, 30, 1'000'000, 1000, 999, 1'000'000);
    assert(empty_window.wall_guest_fps == 0 && empty_window.completed_interval_fps == 30 && empty_window.last_guest_flip_age_ms == -1);
    assert(microseconds(UINT64_MAX, 1) == UINT64_MAX);
    assert(microseconds(24'000'000, 24'000'000) == 1'000'000);
    assert(microseconds(16'000'000'000ull, 32'000'000'000ull) == 500'000);

    Profile trace;
    trace.reset(5);
    trace.record(row(1, 1000, true));
    auto first = trace.take();
    assert(first.captured && first.frames == 1 && first.size == 1);
    assert(!first.events[0].interval_available && first.events[0].session == 5);
    trace.record(row(2, 35'999));
    trace.record(row(3, 70'999));
    auto threshold = trace.take();
    assert(threshold.frames == 2 && threshold.slow == 1 && threshold.size == 1);
    assert(threshold.events[0].interval_us == 35000);
    // Two groups retain sampled context without losing the longest intervals.
    trace.reset(6);
    std::uint64_t now = 1000;
    for (unsigned i = 0; i < 100; ++i)
    {
        now += (i + 1) * 1000;
        trace.record(row(i + 1, now, i % 8 == 0));
    }
    const auto bounded = trace.take();
    assert(bounded.captured && bounded.frames == 100 && bounded.sampled == 13);
    assert(bounded.slow == 66 && bounded.size <= 8 && bounded.unretained > 0);
    unsigned sampled = 0;
    bool longest = false;
    for (std::size_t i = 0; i < bounded.size; ++i)
    {
        const auto& event = bounded.events[i];
        assert(event.session == 6 && event.draws == event.frame * 3 && event.vertex_us == event.frame * 5);
        if (i) assert(bounded.events[i - 1].end_ticks < event.end_ticks);
        sampled += event.stages_sampled;
        longest |= event.interval_us == 100'000;
    }
    assert(sampled == 4 && longest);
    assert(trace.take().size == 0);
    trace.reset(7);
    trace.record(row(1001, now + 1'000'000, true));
    const auto reset = trace.take();
    assert(reset.size == 1 && !reset.events[0].interval_available && reset.events[0].session == 7);
    trace.reset(0);
    trace.record(row(1, 1000, true));
    assert(trace.take().frames == 0);

    // Calling-thread waits cannot be attributed to RSX from unrelated workers.
    active_session = 9;
    waits().fence_ticks += 71;
    waits().pipeline_us += 23;
    std::thread foreign([] { waits().fence_ticks += 999; assert(take_thread_waits().fence_ticks == 999); });
    foreign.join();
    const auto local = take_thread_waits();
    assert(local.fence_ticks == 71 && local.pipeline_us == 23);
    assert(take_thread_waits().fence_ticks == 0);
    waits().submit_ticks += 123;
    active_session = 10;
    assert(take_thread_waits().submit_ticks == 0);

    // One RSX producer and the report consumer concurrently operate real code.
    trace.reset(11);
    std::atomic<bool> done{false};
    std::uint64_t seen = 0, contention = 0, accepted_events = 0;
    std::thread producer([&] {
        for (std::uint64_t i = 1; i <= 100'000; ++i)
            trace.record(row(i, i * 50'000, i % 8 == 0));
        done.store(true, std::memory_order_release);
    });
    auto consume = [&] {
        const auto snapshot = trace.take();
        if (!snapshot.captured) return;
        seen += snapshot.frames;
        contention += snapshot.contended;
        assert(snapshot.size <= 8 && snapshot.session == 11);
        for (std::size_t i = 0; i < snapshot.size; ++i)
        {
            const auto& event = snapshot.events[i];
            assert(event.draws == event.frame * 3 && event.vertex_us == event.frame * 5);
            assert(!event.interval_available || event.interval_us == 50'000);
            ++accepted_events;
        }
    };
    while (!done.load(std::memory_order_acquire)) consume();
    producer.join();
    consume();
    assert(seen + contention == 100'000 && accepted_events > 0);
    std::cout << "{\"passed\":true,\"fpsRegressionCase\":{\"completedIntervalFps\":"
        << blocked.completed_interval_fps << ",\"wallGuestFps\":" << blocked.wall_guest_fps
        << "},\"boundedCapacity\":8,\"threadTrials\":100000,\"recorded\":" << seen
        << ",\"contended\":" << contention << ",\"acceptedEvents\":" << accepted_events
        << ",\"profileBytes\":" << sizeof(Profile)
        << ",\"sessionReset\":true,\"threadWaitIsolation\":true,\"deviceTested\":false}\n";
}
