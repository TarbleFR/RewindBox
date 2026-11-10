#include "ios/IOSShaderTiming.h"
#include <cassert>
#include <thread>
#include <vector>
#include <iostream>
using namespace rpcs3::ios::shader_timing;
int main()
{
    static_assert(sizeof(SlowOperations) < 2048);
    SlowOperations profile;
    profile.record(Stage::source, 10, 9);
    profile.record(Stage::source, 10, 50009);
    assert(profile.take().size == 0);
    for (int i = 0; i < 40; ++i) profile.record(Stage::graphics, 100 + i, 50100 + i);
    auto full = profile.take();
    assert(full.captured && full.size == 32 && full.dropped == 8);
    for (std::size_t i = 0; i < full.size; ++i)
    {
        assert(full.events[i].stage == Stage::graphics);
        assert(full.events[i].begin_us == 100 + i && full.events[i].end_us == 50100 + i);
    }
    auto empty = profile.take(); assert(empty.captured && !empty.size && !empty.dropped);
    std::atomic<int> done{0};
    std::vector<std::thread> workers;
    for (int i = 0; i < 4; ++i) workers.emplace_back([&] {
        for (int j = 0; j < 10000; ++j) profile.record(Stage::module, j + 1, j + 50001);
        done.fetch_add(1);
    });
    std::uint64_t accepted = 0, dropped = 0;
    const auto consume = [&] {
        const auto s = profile.take();
        assert(s.size <= 32);
        accepted += s.size; dropped += s.dropped;
        for (std::size_t i = 0; i < s.size; ++i)
            assert(s.events[i].end_us - s.events[i].begin_us == 50000);
    };
    while (done.load() != 4) { consume(); std::this_thread::yield(); }
    for (auto& worker : workers) worker.join();
    consume(); assert(accepted + dropped == 40000);
    (void)take(); (void)slow_operations.take();
    { Scope sample(Stage::compute); std::this_thread::sleep_for(std::chrono::milliseconds(55)); }
    const auto event = slow_operations.take(); const auto cost = take();
    assert(event.captured && event.size == 1 && !event.dropped);
    assert(event.events[0].stage == Stage::compute && event.events[0].begin_us > 0);
    assert(event.events[0].end_us - event.events[0].begin_us >= 50000);
    assert(cost[3].count == 1 && cost[3].maximum >= 50000);
    std::cout << "PASS bounded slow-operation records: threshold, overflow, concurrent accounting, real Scope; bytes=" << sizeof(SlowOperations) << '\n';
}
