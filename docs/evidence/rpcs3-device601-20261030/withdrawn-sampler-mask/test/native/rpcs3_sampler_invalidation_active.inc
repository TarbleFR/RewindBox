#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <random>
#include <shared_mutex>
#include <string>
#include <thread>
#include <vector>
#ifdef NDEBUG
#error Assertions must remain enabled
#endif
// @PRODUCTION@
using u64 = std::uint64_t;
using u32 = std::uint32_t;
inline u64 checks = 0;

template <std::size_t Count>
void equivalent(const before::sampler_bindings<Count>& old, const after::sampler_bindings<Count>& now)
{
    u64 expected_mask = 0;
    for (std::size_t i = 0; i < Count; ++i)
    {
        const auto a = old.m_bindings[i].range.load();
        const auto b = now.m_bindings[i].range.load();
        assert(a == b);
        assert(old.m_bindings[i].revision.load() == now.m_bindings[i].revision.load());
        if (a) expected_mask |= u64{1} << i;
        ++checks;
    }
    // An unbound slot may remain indexed until the next exclusive scan.
    assert((now.m_active.load() & expected_mask) == expected_mask);
}

template <std::size_t Count>
void operations(u64 seed)
{
    before::sampler_bindings<Count> old;
    after::sampler_bindings<Count> now;
    std::array<before::sampler_stamp, Count> old_stamps{};
    std::array<after::sampler_stamp, Count> new_stamps{};
    std::mt19937_64 random(seed);
    for (u32 operation = 0; operation < 12000; ++operation)
    {
        const std::size_t slot = random() % Count;
        const auto choice = random() % 7;
        const u32 start = static_cast<u32>(random());
        // Include unknown/unbounded layouts, zero lengths and 32-bit wraps.
        const u64 lengths[] = {0, 1, 4096, 65536, 0xffffffffull, 0x100000000ull};
        const auto length = lengths[random() % std::size(lengths)];
        switch (choice)
        {
        case 0:
            old_stamps[slot] = old.prepare(slot);
            new_stamps[slot] = now.prepare(slot);
            break;
        case 1:
            old.set_range(slot, start, length);
            now.set_range(slot, start, length);
            break;
        case 2:
            old.forget(slot);
            now.forget(slot);
            break;
        case 3:
            old.invalidate(start, length);
            now.invalidate(start, length);
            break;
        case 4:
            old.invalidate(0, 0x100000000ull);
            now.invalidate(0, 0x100000000ull);
            break;
        case 5:
            before::sampler_revision.fetch_add(1);
            after::sampler_revision.fetch_add(1);
            break;
        case 6:
            // Repeated publication into an already-active slot.
            old.set_range(slot, 4096, 4096);
            now.set_range(slot, 4096, 4096);
            break;
        }
        equivalent(old, now);
        for (std::size_t i = 0; i < Count; ++i)
        {
            assert(old.matches(i, old_stamps[i]) == now.matches(i, new_stamps[i]));
            ++checks;
        }
    }
}

void interleaving()
{
    before::sampler_bindings<20> old;
    after::sampler_bindings<20> now;
    std::shared_mutex cache;
    std::atomic<bool> ready{false};
    std::thread invalidator([&]
    {
        while (!ready.load(std::memory_order_acquire)) std::this_thread::yield();
        for (u32 iteration = 0; iteration < 8000; ++iteration)
        {
            std::unique_lock lock(cache);
            const u32 start = (iteration % 20) * 4096;
            old.invalidate(start, 4096);
            now.invalidate(start, 4096);
        }
    });
    ready.store(true, std::memory_order_release);
    // prepare and finish are separately reader locked, as in the cache. A
    // writer between them must see the unknown/in-flight range, even when the
    // binding was previously inactive. Reuse and unbinding run concurrently.
    for (u32 iteration = 0; iteration < 8000; ++iteration)
    {
        const auto index = iteration % 20;
        {
            std::shared_lock lock(cache);
            const auto a = old.prepare(index);
            const auto b = now.prepare(index);
            assert(a.memory == b.memory && a.range == b.range);
        }
        std::this_thread::yield();
        {
            std::shared_lock lock(cache);
            old.set_range(index, index * 4096, 4096);
            now.set_range(index, index * 4096, 4096);
            if (iteration & 1)
            {
                old.forget(index);
                now.forget(index);
            }
        }
    }
    invalidator.join();
    equivalent(old, now);
}

void shared_publishers()
{
    // Independent slots may be published by simultaneous reader-lock holders.
    // Their bitmap updates must preserve every slot, including bit 63.
    before::sampler_bindings<64> old;
    after::sampler_bindings<64> now;
    std::shared_mutex cache;
    std::array<std::thread, 8> publishers;
    for (unsigned thread = 0; thread < publishers.size(); ++thread)
        publishers[thread] = std::thread([&, thread]
        {
            for (unsigned iteration = 0; iteration < 3000; ++iteration)
            {
                std::shared_lock lock(cache);
                const auto index = thread * 8 + iteration % 8;
                old.prepare(index);
                now.prepare(index);
                old.set_range(index, static_cast<u32>(index * 4096), 4096);
                now.set_range(index, static_cast<u32>(index * 4096), 4096);
                if (iteration & 1)
                {
                    old.forget(index);
                    now.forget(index);
                }
            }
        });
    for (auto& publisher : publishers) publisher.join();
    std::unique_lock lock(cache);
    old.invalidate(0, 0x100000000ull);
    now.invalidate(0, 0x100000000ull);
    equivalent(old, now);
}

template <typename Bindings>
double time_invalidations(unsigned active, bool overlap)
{
    Bindings bindings;
    for (unsigned i = 0; i < active; ++i) bindings.set_range(i, i * 4096, 4096);
    constexpr unsigned count = 150000;
    const auto begin = std::chrono::steady_clock::now();
    for (unsigned i = 0; i < count; ++i)
        bindings.invalidate(overlap ? 0 : 0x80000000u, overlap ? 20 * 4096 : 4096);
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::nano>(end - begin).count() / count;
}

template <typename Bindings>
double time_publication(bool unbind)
{
    Bindings bindings;
    constexpr unsigned count = 150000;
    const auto begin = std::chrono::steady_clock::now();
    for (unsigned i = 0; i < count; ++i)
    {
        const auto index = i % 20;
        bindings.prepare(index);
        bindings.set_range(index, index * 4096, 4096);
        if (unbind) bindings.forget(index);
    }
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::nano>(end - begin).count() / count;
}

template <typename Bindings>
double time_mix(unsigned active, unsigned invalidations, bool unbind)
{
    Bindings bindings;
    for (unsigned i = 0; i < active; ++i) bindings.set_range(i, i * 4096, 4096);
    constexpr unsigned count = 30000;
    const auto begin = std::chrono::steady_clock::now();
    for (unsigned i = 0; i < count; ++i)
    {
        const auto index = i % active;
        if (unbind) bindings.forget(index);
        bindings.prepare(index);
        bindings.set_range(index, index * 4096, 4096);
        for (unsigned write = 0; write < invalidations; ++write)
            bindings.invalidate((write & 1) ? 0 : 0x80000000u, (write & 1) ? 20 * 4096 : 4096);
    }
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::nano>(end - begin).count() / count;
}

double median(std::vector<double> values)
{
    std::sort(values.begin(), values.end());
    return values[values.size() / 2];
}

int main(int argc, char** argv)
{
    operations<1>(1);
    operations<20>(2);
    operations<64>(3);
    interleaving();
    shared_publishers();
    std::cout << "{\"checks\":" << checks << ",\"publication_writer_interleaving\":true,\"benchmarks\":[";
    bool first = true;
    if (argc > 1 && std::string(argv[1]) == "--benchmark")
    {
        for (unsigned active : {0u, 1u, 4u, 8u, 20u}) for (bool overlap : {false, true})
        {
            std::vector<double> previous, candidate;
            for (unsigned round = 0; round < 11; ++round)
            {
                if (round & 1)
                {
                    candidate.push_back(time_invalidations<after::sampler_bindings<20>>(active, overlap));
                    previous.push_back(time_invalidations<before::sampler_bindings<20>>(active, overlap));
                }
                else
                {
                    previous.push_back(time_invalidations<before::sampler_bindings<20>>(active, overlap));
                    candidate.push_back(time_invalidations<after::sampler_bindings<20>>(active, overlap));
                }
            }
            if (!first) std::cout << ',';
            first = false;
            std::cout << "{\"active\":" << active << ",\"overlap\":" << overlap
                      << ",\"before_ns\":" << median(previous) << ",\"after_ns\":" << median(candidate) << '}';
        }
        for (bool unbind : {false, true})
        {
            std::vector<double> previous, candidate;
            for (unsigned round = 0; round < 11; ++round)
            {
                previous.push_back(time_publication<before::sampler_bindings<20>>(unbind));
                candidate.push_back(time_publication<after::sampler_bindings<20>>(unbind));
            }
            std::cout << ",{\"publication_unbind\":" << unbind << ",\"before_ns\":" << median(previous)
                      << ",\"after_ns\":" << median(candidate) << '}';
        }
        for (unsigned active : {1u, 4u, 8u, 20u}) for (unsigned invalidations : {1u, 8u, 32u}) for (bool unbind : {false, true})
        {
            std::vector<double> previous, candidate;
            for (unsigned round = 0; round < 7; ++round)
            {
                if (round & 1)
                {
                    candidate.push_back(time_mix<after::sampler_bindings<20>>(active, invalidations, unbind));
                    previous.push_back(time_mix<before::sampler_bindings<20>>(active, invalidations, unbind));
                }
                else
                {
                    previous.push_back(time_mix<before::sampler_bindings<20>>(active, invalidations, unbind));
                    candidate.push_back(time_mix<after::sampler_bindings<20>>(active, invalidations, unbind));
                }
            }
            std::cout << ",{\"mix_active\":" << active << ",\"invalidations_per_publication\":" << invalidations
                      << ",\"unbind\":" << unbind << ",\"before_ns\":" << median(previous)
                      << ",\"after_ns\":" << median(candidate) << '}';
        }
    }
    std::cout << "]}\n";
}
