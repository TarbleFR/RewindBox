#include "before.hpp"
#include "after.hpp"
#include <algorithm>
#include <barrier>
#include <cassert>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#ifdef NDEBUG
#error Assertions must be enabled
#endif

using u64 = std::uint64_t;
using u32 = std::uint32_t;

struct key { u32 start, length; };

template <bool Candidate> struct api;
#define API(CANDIDATE, NS) \
template <> struct api<CANDIDATE> { \
    static auto& table() { return NS::table; } \
    static std::size_t slot(key k) { return NS::slot_of(NS::make_key(k.start, k.length)); } \
    static void publish(key k, u64 e, u64 h) { NS::publish(k.start, k.length, e, h); } \
    static bool lookup(key k, u64 e, u64& h) { return NS::lookup(k.start, k.length, e, h); } \
};
API(false, before)
API(true, after)
#undef API

u64 oracle(key k, u64 epoch)
{
    // Independent payload oracle; no actual guest-memory hash is performed.
    u64 x = (u64{k.length} << 32) | k.start;
    x ^= epoch * 0xd6e8feb86659fd93ull;
    x ^= x >> 31;
    x *= 0xa0761d6478bd642full;
    return x ^ (x >> 29);
}

template <bool C> void reset()
{
    for (auto& s : api<C>::table())
    {
        s.seq.store(0);
        s.key.store(0);
        s.epoch.store(0);
        s.hash.store(0);
    }
}

key collision(key k)
{
    const auto slot = api<false>::slot(k);
    for (u32 x = 0x1000; x != 0; x += 0x1000)
    {
        key other{x, k.length};
        if (x != k.start && api<false>::slot(other) == slot)
        {
            assert(api<true>::slot(other) == slot);
            return other;
        }
    }
    assert(false);
    return {};
}

struct deterministic_result
{
    u64 same_key_stale_evictions = 0;
    u64 colliding_key_stale_evictions = 0;
    u64 same_epoch_replacements = 0;
    u64 newer_epoch_replacements = 0;
    u64 busy_returns = 0;
    u64 fallback_lookups = 0;
    u64 modeled_fallback_range_bytes = 0;
};

template <bool C> deterministic_result deterministic()
{
    reset<C>();
    deterministic_result result;
    for (u64 i = 0; i < 1024; ++i)
    {
        const key a{static_cast<u32>(0x100000 + i * 4096), static_cast<u32>((64u << 10) + (i % 8) * (64u << 10))};
        const key b = collision(a);
        const u64 fresh = 10 + i * 4;
        u64 out = 0;
        api<C>::publish(a, fresh, oracle(a, fresh));
        assert(api<C>::lookup(a, fresh, out) && out == oracle(a, fresh));
        api<C>::publish(a, fresh - 1, oracle(a, fresh - 1));
        const bool same_survived = api<C>::lookup(a, fresh, out);
        if (!same_survived) result.same_key_stale_evictions++;
        assert(same_survived == C);
        api<C>::publish(a, fresh, oracle(a, fresh));
        api<C>::publish(b, fresh - 1, oracle(b, fresh - 1));
        const bool collision_survived = api<C>::lookup(a, fresh, out);
        if (!collision_survived) result.colliding_key_stale_evictions++;
        assert(collision_survived == C);
        // Same-epoch key collisions keep the old last-writer-wins policy.
        api<C>::publish(a, fresh + 1, oracle(a, fresh + 1));
        api<C>::publish(b, fresh + 1, oracle(b, fresh + 1));
        assert(!api<C>::lookup(a, fresh + 1, out));
        assert(api<C>::lookup(b, fresh + 1, out) && out == oracle(b, fresh + 1));
        result.same_epoch_replacements++;
        // A newer epoch may replace any older key.
        api<C>::publish(a, fresh + 2, oracle(a, fresh + 2));
        assert(api<C>::lookup(a, fresh + 2, out) && out == oracle(a, fresh + 2));
        assert(!api<C>::lookup(b, fresh + 1, out));
        result.newer_epoch_replacements++;
    }
    reset<C>();
    const key a{0x1234000, 65536};
    const key b = collision(a);
    api<C>::publish(a, 17, oracle(a, 17));
    auto& s = api<C>::table()[api<C>::slot(a)];
    const auto even = s.seq.load();
    s.seq.store(even + 1);
    for (u64 e : {16ull, 17ull, 18ull})
    {
        api<C>::publish(b, e, oracle(b, e));
        assert(s.seq.load() == even + 1);
        assert(s.epoch.load() == 17);
        assert(s.key.load() == ((u64{a.length} << 32) | a.start));
        assert(s.hash.load() == oracle(a, 17));
        result.busy_returns++;
    }
    s.seq.store(even + 2);
    // Replay a delayed worker's obsolete result arriving after a synchronous
    // next-epoch validation, followed by another current-epoch consumer.
    reset<C>();
    for (u64 round = 1; round <= 4096; ++round)
    {
        const u64 current = round + 100;
        api<C>::publish(a, current, oracle(a, current));
        api<C>::publish((round & 1) ? a : b, current - 1,
                        oracle((round & 1) ? a : b, current - 1));
        u64 out = 0;
        if (!api<C>::lookup(a, current, out))
        {
            result.fallback_lookups++;
            result.modeled_fallback_range_bytes += a.length;
            api<C>::publish(a, current, oracle(a, current));
        }
        else assert(out == oracle(a, current));
    }
    assert(result.fallback_lookups == (C ? 0 : 4096));
    return result;
}

struct stress_result
{
    u64 writer_calls;
    u64 reader_hits;
    u64 reader_misses;
    u64 sampled_epoch_regressions;
    u64 payload_errors;
};

template <bool C> stress_result concurrent(unsigned rounds)
{
    reset<C>();
    const key a{0x1234000, 65536};
    const key b = collision(a);
    constexpr unsigned writer_count = 3;
    std::barrier start(5);
    std::atomic<u64> published_epoch{1};
    std::atomic<unsigned> finished{0};
    std::atomic<u64> hits{0}, misses{0}, errors{0}, regressions{0};
    std::vector<std::thread> threads;
    for (unsigned id = 0; id < writer_count; ++id)
    {
        threads.emplace_back([&, id] {
            start.arrive_and_wait();
            for (unsigned i = 1; i <= rounds; ++i)
            {
                u64 epoch = 0;
                if (id == 0)
                {
                    epoch = u64{i} * 4 + 4;
                    published_epoch.store(epoch, std::memory_order_release);
                }
                else
                {
                    epoch = published_epoch.load(std::memory_order_acquire);
                    if (id == 1 && epoch > 1) --epoch;
                }
                const key k = ((i + id) & 1) ? a : b;
                api<C>::publish(k, epoch, oracle(k, epoch));
                if ((i & 255u) == 0) std::this_thread::yield();
            }
            finished.fetch_add(1, std::memory_order_release);
        });
    }
    threads.emplace_back([&] {
        start.arrive_and_wait();
        u64 last_epoch = 0, local_hits = 0, local_misses = 0, local_errors = 0, drops = 0;
        unsigned iteration = 0;
        do
        {
            auto& slot = api<C>::table()[api<C>::slot(a)];
            const u64 observed = slot.epoch.load(std::memory_order_acquire);
            if (observed < last_epoch) ++drops;
            last_epoch = observed;
            const auto epoch = published_epoch.load(std::memory_order_acquire);
            u64 out = 0;
            for (const key k : {a, b})
            {
                if (api<C>::lookup(k, epoch, out))
                {
                    ++local_hits;
                    if (out != oracle(k, epoch)) ++local_errors;
                }
                else ++local_misses;
            }
            ++iteration;
        }
        while (finished.load(std::memory_order_acquire) != writer_count || iteration < rounds);
        hits.store(local_hits); misses.store(local_misses); errors.store(local_errors); regressions.store(drops);
    });
    start.arrive_and_wait();
    for (auto& thread : threads) thread.join();
    assert(errors.load() == 0);
    if constexpr (C) assert(regressions.load() == 0);
    assert(hits.load() + misses.load() >= u64{rounds} * 2);
    // Final quiescent observation proves both APIs can still publish after load.
    const u64 epoch = u64{rounds} * 4 + 100;
    api<C>::publish(a, epoch, oracle(a, epoch));
    u64 out = 0;
    assert(api<C>::lookup(a, epoch, out) && out == oracle(a, epoch));
    return {u64{rounds} * writer_count, hits.load(), misses.load(), regressions.load(), errors.load()};
}

template <bool C> double timed_publish(unsigned iterations, unsigned pattern)
{
    reset<C>();
    const auto begin = std::chrono::steady_clock::now();
    for (unsigned i = 0; i < iterations; ++i)
    {
        const key k{static_cast<u32>(0x100000 + (pattern == 0 ? 0 : i % 4096) * 4096), 65536};
        const u64 epoch = pattern == 2 ? i + 1ull : 1;
        api<C>::publish(k, epoch, oracle(k, epoch));
    }
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::nano>(end - begin).count() / iterations;
}

void print_deterministic(const deterministic_result& d)
{
    std::cout << "{\"sameKeyStaleEvictions\":" << d.same_key_stale_evictions
              << ",\"collidingKeyStaleEvictions\":" << d.colliding_key_stale_evictions
              << ",\"sameEpochReplacements\":" << d.same_epoch_replacements
              << ",\"newerEpochReplacements\":" << d.newer_epoch_replacements
              << ",\"busyReturns\":" << d.busy_returns
              << ",\"replayFallbackLookups\":" << d.fallback_lookups
              << ",\"modeledReplayFallbackRangeBytes\":" << d.modeled_fallback_range_bytes << "}";
}

void print_stress(const stress_result& s)
{
    std::cout << "{\"writerCalls\":" << s.writer_calls << ",\"readerHits\":" << s.reader_hits
              << ",\"readerMisses\":" << s.reader_misses << ",\"sampledEpochRegressions\":" << s.sampled_epoch_regressions
              << ",\"payloadErrors\":" << s.payload_errors << "}";
}

int main(int argc, char** argv)
{
    const bool benchmark = argc < 2 || std::string(argv[1]) == "bench";
    const auto b = deterministic<false>();
    const auto a = deterministic<true>();
    const auto bs = concurrent<false>(100000);
    const auto as = concurrent<true>(100000);
    std::cout << "{\"passed\":true,\"baseline\":"; print_deterministic(b);
    std::cout << ",\"candidate\":"; print_deterministic(a);
    std::cout << ",\"baselineConcurrent\":"; print_stress(bs);
    std::cout << ",\"candidateConcurrent\":"; print_stress(as);
    std::cout << ",\"timingsNsPerPublish\":[";
    if (benchmark)
    {
        constexpr unsigned iterations = 300000;
        for (unsigned pattern = 0; pattern < 3; ++pattern)
        {
            if (pattern) std::cout << ',';
            std::cout << "{\"pattern\":" << pattern << ",\"iterationsPerSample\":" << iterations << ",\"samples\":[";
            for (unsigned sample = 0; sample < 7; ++sample)
            {
                double before_ns, after_ns;
                if ((sample & 1) == 0)
                {
                    before_ns = timed_publish<false>(iterations, pattern);
                    after_ns = timed_publish<true>(iterations, pattern);
                }
                else
                {
                    after_ns = timed_publish<true>(iterations, pattern);
                    before_ns = timed_publish<false>(iterations, pattern);
                }
                if (sample) std::cout << ',';
                std::cout << "{\"baseline\":" << before_ns << ",\"candidate\":" << after_ns
                          << ",\"first\":\"" << ((sample & 1) ? "candidate" : "baseline") << "\"}";
            }
            std::cout << "]}";
        }
    }
    std::cout << "]}" << std::endl;
}
