// SPDX-License-Identifier: MIT
// Production HLE lock methods and RPCS3 atomic.cpp; no emulator/game doubles.
#include "util/atomic.hpp"
#include "Utilities/StrFmt.h"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <latch>
#include <thread>
#include <vector>

#include "hle-lock.inc"

thread_local std::latch* before_park = nullptr;

static bool parked(u64 progress)
{
    if (progress == 0 && before_park)
    {
        before_park->count_down();
        before_park = nullptr;
    }
    return true;
}

static bool contention(bool finalize, unsigned count)
{
    hle_locks_t lock;
    std::latch start{1}, entered{static_cast<std::ptrdiff_t>(count)};
    std::latch finished{static_cast<std::ptrdiff_t>(count)};
    std::atomic<unsigned> acquired{0};
    std::vector<std::thread> workers;
    for (unsigned index = 0; index < count; ++index)
    {
        workers.emplace_back([&]
        {
            start.wait();
            before_park = &entered;
            atomic_wait_engine::set_one_time_use_wait_callback(parked);
            if (lock.try_lock())
            {
                acquired.fetch_add(1);
                lock.unlock();
            }
            finished.count_down();
        });
    }
    unsigned predicates = 0;
    const bool result = lock.try_finalize([&]
    {
        if (++predicates == 1) return true;
        start.count_down();
        entered.wait(); // Every real wait passed its value check and registered.
        ensure(lock.lock_val == hle_locks_t::waiting_for_evaluation);
        ensure(acquired.load() == 0);
        return finalize;
    });
    ensure(predicates == 2 && result == finalize);
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    while (!finished.try_wait() && std::chrono::steady_clock::now() < deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    const bool resumed_without_rescue = finished.try_wait();
    if (!resumed_without_rescue)
        lock.lock_val.notify_all(); // Test rescue only, after recording failure.
    for (auto& worker : workers) worker.join();
    ensure(acquired.load() == (finalize ? 0 : count));
    ensure(lock.lock_val == (finalize ? static_cast<s64>(hle_locks_t::finalized) : s64{0}));
    if (!finalize)
    {
        ensure(lock.try_finalize([] { return true; }));
        ensure(!lock.try_lock());
    }
    return resumed_without_rescue;
}

int main(int argc, char**)
{
    // The old method leaves all eight native waits asleep until the test rescue.
    if (!contention(false, 8))
    {
        std::cerr << "FAIL aborted HLE finalization left 8 registered native waits asleep; fixture notify_all rescued them\n";
        return 7;
    }
    if (argc > 1) return 0;
    unsigned cases = 1;
    for (unsigned count : {1u, 8u})
        for (unsigned iteration = 0; iteration < 8; ++iteration)
        {
            ensure(contention(false, count));
            ++cases;
        }
    ensure(contention(true, 8));
    ++cases;
    {
        hle_locks_t lock;
        unsigned calls = 0;
        ensure(!lock.try_finalize([&] { ++calls; return false; }));
        ensure(calls == 1 && lock.lock_val == 0 && lock.try_lock());
        lock.unlock();
        ++cases;
    }
    {
        hle_locks_t lock;
        ensure(lock.try_lock());
        unsigned calls = 0;
        ensure(!lock.try_finalize([&] { ++calls; return true; }));
        ensure(calls == 1 && lock.lock_val == 1);
        lock.unlock();
        ensure(lock.try_lock());
        lock.unlock();
        ++cases;
    }
    std::cout << "PASS " << cases << " HLE cases: parked waiters resume after abort, retry succeeds, finalized rejects, active locks and initial rejection preserved; actual RPCS3 wait engine\n";
}
