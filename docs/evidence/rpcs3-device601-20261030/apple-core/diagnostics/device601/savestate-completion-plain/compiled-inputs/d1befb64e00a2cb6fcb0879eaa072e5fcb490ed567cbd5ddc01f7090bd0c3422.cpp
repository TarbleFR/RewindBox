// SPDX-License-Identifier: MIT
#include "ios/NeoStationSavestateStatus.h"
#define neostation baseline_neostation
#include "baseline.h"
#undef neostation
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <memory>
#include <random>
#include <thread>
#include <vector>
#ifdef NDEBUG
#error Assertions must remain enabled
#endif
namespace current = neostation::savestate;
namespace previous = baseline_neostation::savestate;
using state = current::operation::registration_state;
static_assert(sizeof(current::snapshot) == sizeof(previous::snapshot));
static_assert(alignof(current::snapshot) == alignof(previous::snapshot));
static_assert(offsetof(current::snapshot, message) == offsetof(previous::snapshot, message));

std::uint64_t checks = 0;
void equal(const current::operation& now, const previous::operation& old)
{
    const auto a = now.read();
    const auto b = old.read();
    assert(static_cast<std::uint32_t>(a.state) == static_cast<std::uint32_t>(b.state));
    assert(a.active == b.active && a.committed == b.committed && a.slot == b.slot && a.message == b.message);
    ++checks;
}

void old_status_api()
{
    current::operation now;
    previous::operation old;
    std::mt19937 random(601);
    for (unsigned iteration = 0; iteration < 50000; ++iteration)
    {
        const auto choice = random() % 5;
        const bool success = random() & 1;
        switch (choice)
        {
        case 0:
        {
            const auto slot = random() % 13;
            assert(now.begin(slot) == old.begin(slot));
            break;
        }
        case 1:
        {
            const auto phase = random() % 6;
            now.advance(static_cast<current::phase>(phase));
            old.advance(static_cast<previous::phase>(phase));
            break;
        }
        case 2:
            now.error("original diagnostic");
            old.error("original diagnostic");
            break;
        case 3:
            now.record_write(success);
            old.record_write(success);
            break;
        case 4:
            now.finish(success, "fallback diagnostic");
            old.finish(success, "fallback diagnostic");
            break;
        }
        equal(now, old);
    }
}

void bounded_owner()
{
    current::operation operation;
    unsigned calls = 0;
    assert(operation.after_finish(7, [](bool) noexcept {}).state == state::inactive);
    assert(!operation.after_finish(7, [](bool) noexcept {}).finished);
    assert(operation.begin(4, 7));
    assert(!operation.begin(5, 8));
    assert(operation.after_finish(8, [&](bool) noexcept { calls += 100; }).state == state::busy);
    assert(operation.after_finish(7, {}).state == state::busy);
    assert(operation.after_finish(7, [&](bool success) noexcept { assert(!success); ++calls; }).state == state::registered);
    assert(operation.after_finish(7, [&](bool) noexcept { calls += 100; }).state == state::busy);
    operation.error("preserved failure");
    operation.finish(false, "must not replace the original error");
    assert(calls == 1 && operation.read().message == "preserved failure");
    operation.finish(true);
    assert(calls == 1);
    const auto same_owner = operation.after_finish(7, [&](bool) noexcept { calls += 100; });
    assert(same_owner.state == state::inactive && same_owner.finished == false && calls == 1);
    const auto other_owner = operation.after_finish(8, [&](bool) noexcept { calls += 100; });
    assert(other_owner.state == state::inactive && !other_owner.finished);
    assert(operation.begin(3, 8));
    assert(operation.after_finish(8, [&](bool success) noexcept { assert(success); ++calls; }).state == state::registered);
    operation.record_write(true);
    operation.finish(true);
    assert(calls == 2 && operation.read().committed);
    assert(operation.after_finish(8, [](bool) noexcept {}).finished == true);
    assert(!operation.after_finish(7, [](bool) noexcept {}).finished);
    checks += 20;
}

void callback_outside_lock()
{
    current::operation operation;
    unsigned calls = 0;
    assert(operation.begin(1, 10));
    assert(operation.after_finish(10, [&](bool success) noexcept
    {
        assert(!success && !operation.read().active);
        ++calls;
        // finish must already have vacated its one callback slot. Re-enter
        // all status methods and even begin/finish a second operation.
        assert(operation.begin(2, 11));
        assert(operation.after_finish(11, [&](bool next_success) noexcept
        {
            assert(next_success && !operation.read().active);
            ++calls;
        }).state == state::registered);
        operation.finish(true);
    }).state == state::registered);
    operation.finish(false, "first failure");
    assert(calls == 2 && operation.read().state == current::phase::succeeded);
    checks += 5;
}

void finish_registration_races()
{
    for (unsigned iteration = 0; iteration < 1200; ++iteration)
    {
        current::operation operation;
        assert(operation.begin(1, iteration + 1));
        std::atomic<unsigned> ready{0}, calls{0};
        std::atomic<bool> go{false};
        const bool success = iteration & 1;
        current::operation::finish_registration registered{state::busy, std::nullopt};
        std::thread registering([&]
        {
            ++ready;
            while (!go.load(std::memory_order_acquire)) std::this_thread::yield();
            registered = operation.after_finish(iteration + 1, [&](bool outcome) noexcept
            {
                assert(outcome == success && !operation.read().active);
                ++calls;
            });
        });
        std::thread finishing([&]
        {
            ++ready;
            while (!go.load(std::memory_order_acquire)) std::this_thread::yield();
            operation.finish(success);
        });
        while (ready.load(std::memory_order_acquire) != 2) std::this_thread::yield();
        go.store(true, std::memory_order_release);
        registering.join();
        finishing.join();
        if (registered.state == state::registered)
        {
            assert(calls == 1 && !registered.finished);
        }
        else
        {
            assert(registered.state == state::inactive && calls == 0);
            assert(registered.finished.has_value() && *registered.finished == success);
        }
        operation.finish(!success);
        assert(calls <= 1 && !operation.read().active);
        const auto retained = operation.after_finish(iteration + 1, [](bool) noexcept {});
        assert(retained.finished.has_value() && *retained.finished == success);
        ++checks;
    }
}

void callback_owner_lifetime()
{
    current::operation operation;
    auto owner = std::make_shared<unsigned>(23);
    std::weak_ptr<unsigned> weak = owner;
    assert(operation.begin(1, 1));
    assert(operation.after_finish(1, [owner](bool) noexcept { assert(*owner == 23); }).state == state::registered);
    owner.reset();
    assert(!weak.expired());
    operation.finish(false);
    assert(weak.expired());
    checks += 3;
}

int main()
{
    old_status_api();
    bounded_owner();
    callback_outside_lock();
    finish_registration_races();
    callback_owner_lifetime();
    std::cout << "{\"checks\":" << checks
              << ",\"original_status_behavior_equal\":true,\"snapshot_layout_preserved\":true,"
                 "\"single_slot_owner_guard\":true,\"callback_outside_mutex\":true,"
                 "\"registration_finish_races\":1200,\"callback_lifetime_released\":true}\n";
}
