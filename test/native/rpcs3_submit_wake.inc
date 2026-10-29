#include <algorithm>
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <string_view>
#include <thread>
#include <type_traits>
#include <vector>

#ifdef NDEBUG
#error The completion checks require active assertions.
#endif
using u64 = std::uint64_t;
using u32 = std::uint32_t;
using namespace std::string_view_literals;

// Explicit host boundaries. The CAS loop itself is verbatim production.
thread_local std::function<void(const void*)> cas_hook;
thread_local std::function<void(const void*)> before_wait_hook;
thread_local std::function<void(const void*)> wait_registered_hook;
template<class T> struct atomic_storage {
    static T load(const std::atomic<T>& data) { return data.load(); }
    static bool compare_exchange(std::atomic<T>& data, T& old, T value) {
        if (cas_hook) cas_hook(&data);
        return data.compare_exchange_strong(old, value);
    }
};
template<class T> struct atomic_t {
    using type = T;
    std::atomic<T> m_data;
    std::atomic<u64> notifications{0};
    std::mutex wait_mutex;
    std::condition_variable_any event;
    atomic_t(T value) : m_data(value) {}
    T load() const { return m_data.load(); }
    T observe() const { return m_data.load(std::memory_order_relaxed); }
    void store(T value) { m_data.store(value); }
    T operator++(int) { return m_data.fetch_add(1); }
    void notify_one() { ++notifications; std::lock_guard lock(wait_mutex); event.notify_one(); }
    void notify_all() { ++notifications; std::lock_guard lock(wait_mutex); event.notify_all(); }
    void wait(T token) {
        struct registration_lock {
            atomic_t& owner;
            std::unique_lock<std::mutex> held;
            explicit registration_lock(atomic_t& a) : owner(a), held(a.wait_mutex) {}
            void lock() { held.lock(); }
            void unlock() {
                held.unlock();
                // condition_variable_any owns its internal wait mutex at this
                // point. A concurrent notify cannot pass wait registration.
                if (wait_registered_hook) wait_registered_hook(&owner);
            }
        } lock(*this);
        event.wait(lock, [&] { return m_data.load() != token; });
    }
    @ATOMIC_OP@
};

enum class thread_state { running, aborting };
struct ThreadState { std::atomic<bool> abort{false}; };
thread_local ThreadState* state_context = nullptr;
namespace thread_ctrl {
thread_state state() {
    return state_context && state_context->abort.load() ? thread_state::aborting : thread_state::running;
}
template<class T> void wait_on(atomic_t<T>& value, T token) {
    if (before_wait_hook) before_wait_hook(&value);
    value.wait(token);
}
}
struct ResourceManager {
    std::vector<u64> completed;
    void eid_completed(u64 eid) {
        assert(completed.empty() || completed.back() < eid);
        completed.push_back(eid);
    }
};
thread_local ResourceManager* resource_context = nullptr;
namespace vk { ResourceManager* get_resource_manager() { assert(resource_context); return resource_context; } }

@BEFORE@
@AFTER@

struct Gate {
    std::mutex mutex;
    std::condition_variable condition;
    bool arrived = false, released = false;
    void arrive() { std::lock_guard lock(mutex); arrived = true; condition.notify_all(); }
    void wait_arrived() { std::unique_lock lock(mutex); condition.wait(lock, [&] { return arrived; }); }
    void block() { arrive(); std::unique_lock lock(mutex); condition.wait(lock, [&] { return released; }); }
    void release() { std::lock_guard lock(mutex); released = true; condition.notify_all(); }
};
template<class Manager> std::thread launch(Manager& manager, ThreadState& state, ResourceManager& resources,
                                         std::function<void()> configure = {}) {
    return std::thread([&, configure] {
        state_context = &state; resource_context = &resources;
        if (configure) configure();
        manager();
    });
}
template<class Manager> void stop(Manager& manager, ThreadState& state, std::thread& worker) {
    state.abort.store(true); manager.m_wake_event++; manager.m_wake_event.notify_all(); worker.join();
}

template<class Manager> u64 completion_sequence() {
    Manager manager;
    for (u64 value : {0ull, 0ull, 1ull, 1ull, 0ull, 3ull, 2ull, 3ull, 9ull, 4ull})
        manager.notify_completed(value);
    manager.notify_completed(std::numeric_limits<u64>::max());
    manager.notify_completed(std::numeric_limits<u64>::max());
    manager.notify_completed(1);
    assert(manager.m_eid_ctr.load() == std::numeric_limits<u64>::max());
    assert(manager.m_wake_event.load() == manager.m_wake_event.notifications.load());
    return manager.m_wake_event.notifications.load();
}
template<class Manager> u64 late_old_completions() {
    Manager manager;
    for (u64 frame = 1; frame <= 128; ++frame) {
        manager.notify_completed(frame * 8);
        for (u64 old = frame * 8 - 7; old < frame * 8; ++old) manager.notify_completed(old);
    }
    assert(manager.m_eid_ctr.load() == 1024);
    return manager.m_wake_event.notifications.load();
}
template<class Manager> u64 cas_retry() {
    Manager manager;
    Gate paused;
    std::thread older([&] {
        bool once = false;
        cas_hook = [&](const void* address) {
            if (address == &manager.m_eid_ctr.m_data && !once) { once = true; paused.block(); }
        };
        manager.notify_completed(1);
    });
    paused.wait_arrived();
    manager.notify_completed(2);
    paused.release(); older.join();
    assert(manager.m_eid_ctr.load() == 2);
    return manager.m_wake_event.notifications.load();
}
template<class Manager> void wake_boundary(bool after_registration) {
    Manager manager; ThreadState state; ResourceManager resources; Gate reached;
    auto worker = launch(manager, state, resources, [&] {
        bool* once = new bool(false);
        // Own this local gate flag for the worker's full lifetime through the
        // hook closure; no source allocation/lifetime behavior is modeled here.
        auto fired = std::shared_ptr<bool>(once);
        auto hook = [&, fired](const void* address) {
            if (address == &manager.m_wake_event && !*fired) {
                *fired = true;
                if (after_registration) reached.arrive(); else reached.block();
            }
        };
        if (after_registration) wait_registered_hook = hook; else before_wait_hook = hook;
    });
    reached.wait_arrived();
    manager.notify_completed(7);
    if (!after_registration) reached.release();
    manager.drain();
    assert(manager.m_last_completed_eid.load() == 7);
    stop(manager, state, worker);
    assert(resources.completed.size() == 1 && resources.completed.back() == 7);
}
template<class Manager> void explicit_drain_wake() {
    Manager manager; ThreadState state; ResourceManager resources; Gate at_wait, drain_wait;
    auto worker = launch(manager, state, resources, [&] {
        auto once = std::make_shared<bool>(false);
        before_wait_hook = [&, once](const void* address) {
            if (address == &manager.m_wake_event && !*once) { *once = true; at_wait.block(); }
        };
    });
    at_wait.wait_arrived();
    // Publish an already requested target at the boundary without its wake,
    // so this scenario specifically requires the unchanged explicit drain wake.
    manager.m_eid_ctr.store(11);
    std::thread drainer([&] {
        before_wait_hook = [&](const void* address) { if (address == &manager.m_completed_signal) drain_wait.arrive(); };
        manager.drain();
    });
    drain_wait.wait_arrived();
    assert(manager.m_wake_event.notifications.load() >= 1);
    at_wait.release(); drainer.join();
    assert(manager.m_last_completed_eid.load() == 11);
    stop(manager, state, worker);
}
template<class Manager> void concurrent_progress() {
    Manager manager; ThreadState state; ResourceManager resources;
    auto worker = launch(manager, state, resources);
    std::vector<std::thread> producers;
    for (u64 lane = 0; lane < 4; ++lane) producers.emplace_back([&, lane] {
        for (u64 i = 1; i <= 2048; ++i) {
            const u64 eid = 4 * i + lane;
            manager.notify_completed(eid);
            manager.notify_completed(eid - 1);
            if (i % 127 == 0) {
                manager.drain();
                assert(manager.m_last_completed_eid.load() >= eid);
            }
        }
    });
    for (auto& producer : producers) producer.join();
    manager.drain();
    assert(manager.m_eid_ctr.load() == 8195 && manager.m_last_completed_eid.load() == 8195);
    stop(manager, state, worker);
    assert(!resources.completed.empty() && resources.completed.back() == 8195);
    // A stopped emulation must still exit drain even with unfinished work.
    manager.m_eid_ctr.store(9000); state_context = &state; manager.drain(); state_context = nullptr;
}
int main() {
    const auto before_sequence = completion_sequence<before::driver_manager_t>();
    const auto after_sequence = completion_sequence<after::driver_manager_t>();
    assert(before_sequence == 13 && after_sequence == 4);
    const auto before_late = late_old_completions<before::driver_manager_t>();
    const auto after_late = late_old_completions<after::driver_manager_t>();
    assert(before_late == 1024 && after_late == 128);
    assert(cas_retry<before::driver_manager_t>() == 2);
    assert(cas_retry<after::driver_manager_t>() == 1);
    wake_boundary<before::driver_manager_t>(false); wake_boundary<after::driver_manager_t>(false);
    wake_boundary<before::driver_manager_t>(true); wake_boundary<after::driver_manager_t>(true);
    explicit_drain_wake<before::driver_manager_t>(); explicit_drain_wake<after::driver_manager_t>();
    concurrent_progress<before::driver_manager_t>(); concurrent_progress<after::driver_manager_t>();
    std::cout << "{\"passed\":true,\"assertionsActive\":true,\"sequenceCalls\":13,"
      "\"sequenceBaselineWakes\":13,\"sequenceCandidateWakes\":4,"
      "\"lateCompletionCalls\":1024,\"lateBaselineWakes\":1024,\"lateCandidateWakes\":128,"
      "\"casRetryCases\":2,\"wakeBoundaryCases\":4,\"explicitDrainCases\":2,"
      "\"concurrentProducerCallsPerVersion\":16384,\"abortDrainCases\":2}\n";
}
