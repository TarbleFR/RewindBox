#include <cassert>
#include <cstdint>
#include <iostream>
#include <thread>
#include <vector>
#include "ios/IOSReadbackProfile.h"
using namespace rpcs3::ios::readback;
static unsigned index(Origin value) { return static_cast<unsigned>(value); }
int main()
{
    static_assert(sizeof(counters) == 200, "five fixed 40-byte counters; no per-transfer storage");
    for (const auto& sample : take()) assert(sample.duration_ticks.count == 0);
    // Empty batches cannot add clock work or counters.
    { BatchScope empty(0, 0); }
    assert(utils::clock_reads == 0);
    utils::ticks = 10;
    { BatchScope unknown(2, 8192); utils::ticks = 40; }
    assert(utils::clock_reads == 2);
    auto values = take();
    assert(values[0].duration_ticks.count == 1 && values[0].duration_ticks.total == 30);
    assert(values[0].sections == 2 && values[0].confirmed_bytes == 8192);
    // Nested contexts restore their predecessor. A batch retains its origin
    // even if a nested action changes the current reason before destruction.
    {
        OriginScope texture(Origin::texture_cpu);
        utils::ticks = 100;
        { BatchScope batch(3, 1ull << 33); OriginScope nested(Origin::blit_source_cpu); utils::ticks = 170; }
        assert(current_origin == Origin::texture_cpu);
        { OriginScope inner(Origin::presentation_cpu); assert(current_origin == Origin::presentation_cpu); }
        assert(current_origin == Origin::texture_cpu);
    }
    assert(current_origin == Origin::unknown);
    values = take();
    assert(values[index(Origin::texture_cpu)].duration_ticks.total == 70);
    assert(values[index(Origin::texture_cpu)].confirmed_bytes == (1ull << 33));
    assert(values[index(Origin::blit_source_cpu)].duration_ticks.count == 0);
    assert(values[index(Origin::presentation_cpu)].duration_ticks.count == 0);
    // A regressing test clock cannot underflow into an apparent long pause.
    utils::ticks = 100;
    { OriginScope invalid(static_cast<Origin>(999)); BatchScope batch(1, 64); utils::ticks = 1; }
    values = take(); assert(values[0].duration_ticks.total == 0 && values[0].duration_ticks.count == 1);
    // TLS reasons are independent; draining while producers run conserves
    // counts/bytes/sums across windows without requiring a coherent tuple.
    constexpr unsigned workers = 8, iterations = 500;
    std::atomic<unsigned> done{0};
    std::vector<std::thread> threads;
    for (unsigned worker = 0; worker < workers; ++worker)
        threads.emplace_back([&, worker] {
            assert(current_origin == Origin::unknown);
            const auto origin = worker % 2 ? Origin::blit_source_cpu : Origin::blit_destination_dma;
            {
                OriginScope reason(origin);
                for (unsigned i = 0; i < iterations; ++i) {
                    BatchScope batch(2, 1ull << 32);
                    utils::ticks += 5;
                }
            }
            assert(current_origin == Origin::unknown);
            assert(utils::clock_reads == 2 * iterations);
            done.fetch_add(1, std::memory_order_release);
        });
    std::uint64_t count = 0, sections = 0, bytes = 0, ticks = 0;
    auto drain = [&] {
        for (const auto& value : take()) {
            count += value.duration_ticks.count; ticks += value.duration_ticks.total;
            sections += value.sections; bytes += value.confirmed_bytes;
        }
    };
    while (done.load(std::memory_order_acquire) != workers) { drain(); std::this_thread::yield(); }
    for (auto& thread : threads) thread.join();
    drain();
    assert(count == workers * iterations && sections == 2 * count && bytes == (count << 32));
    assert(ticks == 5 * count && current_origin == Origin::unknown);
    for (const auto& value : take()) assert(value.duration_ticks.count == 0 && value.sections == 0 && value.confirmed_bytes == 0);
    std::cout << "{\"passed\":true,\"counterBytes\":" << sizeof(counters)
              << ",\"origins\":5,\"clockReadsPerNonemptyBatch\":2,\"emptyBatchClockReads\":0,\"concurrentBatches\":" << count
              << ",\"conservedRequestedBytes\":" << bytes << "}\n";
}
