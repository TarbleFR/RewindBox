// SPDX-License-Identifier: MIT
#include "rpcs3/ios/IOSGPUMemoryProfile.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <memory>
#include <string_view>
#include <thread>

using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;
using f32 = float;
template<typename T> u32 size32(const T& v) { return static_cast<u32>(v.size()); }
#define ensure(x) do { if (!(x)) { std::cerr << __LINE__ << " assertion " << #x << '\n'; std::abort(); } } while(false)

struct VmaBudget {
    struct { u64 blockBytes = 0, allocationBytes = 0; } statistics;
    u64 usage = 0, budget = 0;
};
static std::array<VmaBudget, 4> fixture;
static unsigned budget_queries = 0, allocator_destroys = 0;
void vmaGetHeapBudgets(int, VmaBudget* out) { ++budget_queries; std::copy(fixture.begin(), fixture.end(), out); }
void vmaDestroyAllocator(int) { ++allocator_destroys; }

namespace vk {
struct mem_allocator_vma {
    int m_allocator = 1;
    std::array<VmaBudget, 4> stats{};
    std::array<u64, 4> m_pressure_heap_limits{};
    u32 m_rebar_heap_idx = UINT32_MAX;
    mem_allocator_vma() { rpcs3::ios::vma_profile.begin(this); }
    f32 get_memory_usage();
    void destroy();
};
#include "vma_usage.inc"
#include "vma_destroy.inc"

struct image_memory { u64 bytes; u64 size() const { return bytes; } };
struct image { std::unique_ptr<image_memory> memory; };
struct cached_image { std::unique_ptr<image> data; };
struct texture_base {
    unsigned end_calls = 0, clear_calls = 0;
    void on_frame_end() { ++end_calls; }
    void clear() { ++clear_calls; }
};
struct texture_cache : texture_base {
    using baseclass = texture_base;
    std::mutex m_cached_pool_lock;
    std::deque<cached_image> m_cached_images;
    u64 m_cached_memory_size = 0;
    bool m_cache_is_exiting = false;
    struct { u32 m_unreleased_texture_objects = 0; } m_storage;
    u32 m_max_zombie_objects = 32;
    static constexpr u32 max_cached_image_pool_size = 256;
    unsigned trims = 0, purges = 0, resets = 0;
    texture_cache() { rpcs3::ios::texture_profile.begin(this); }
    void trim_sections() { ++trims; }
    void purge_unreleased_sections() { ++purges; m_storage.m_unreleased_texture_objects = 0; }
    void reset_frame_statistics() { ++resets; }
    void add(u64 bytes) {
        m_cached_memory_size += bytes;
        m_cached_images.push_back({std::make_unique<image>(image{std::make_unique<image_memory>(image_memory{bytes})})});
    }
    void on_frame_end();
    void clear();
    void destroy();
};
#include "texture_frame.inc"
#include "texture_clear.inc"
#include "texture_destroy.inc"
}

// Pause a test payload's copy while the real production channel owns its
// mutex. Readers and publishers must return before this writer is released.
struct copy_gate {
    unsigned payload = 0;
    inline static std::atomic<bool> armed{false};
    inline static std::mutex mutex;
    inline static std::condition_variable cv;
    inline static bool held = false, release = false;
    copy_gate() = default;
    copy_gate(const copy_gate&) = default;
    copy_gate& operator=(const copy_gate& other) {
        payload = other.payload;
        if (armed.load()) {
            std::unique_lock lock(mutex);
            held = true; cv.notify_all();
            cv.wait(lock, [] { return release; });
        }
        return *this;
    }
};
struct gated_sample : rpcs3::ios::memory_sample_status { copy_gate gate; };

void nonblocking_test() {
    rpcs3::ios::owned_memory_profile<gated_sample> channel;
    int owner = 0;
    channel.begin(&owner);
    copy_gate::armed = true;
    std::thread writer([&] { ensure(channel.publish(&owner, {})); });
    { std::unique_lock lock(copy_gate::mutex); copy_gate::cv.wait(lock, [] { return copy_gate::held; }); }
    ensure(!channel.capture().captured);
    ensure(!channel.publish(&owner, {}));
    { std::lock_guard lock(copy_gate::mutex); copy_gate::release = true; copy_gate::cv.notify_all(); }
    writer.join(); copy_gate::armed = false;
    ensure(channel.capture().sampled);
    channel.end(&owner);
}

void lifecycle_test() {
    ensure(!rpcs3::ios::vma_profile.capture().owner_live);
    fixture = {};
    fixture[0] = {{0x1'0000'0000ull, 0x8000'0000ull}, 500, 1000};
    fixture[1] = {{1000, 200}, 800, 1000};
    vk::mem_allocator_vma old;
    auto initial = rpcs3::ios::vma_profile.capture();
    ensure(initial.captured && initial.owner_live && !initial.sampled && !initial.block_bytes);
    old.m_rebar_heap_idx = 1;
    old.m_pressure_heap_limits[0] = 800;
    ensure(old.get_memory_usage() == 62.5f); // Existing ReBAR/pressure policy preserved.
    auto sampled = rpcs3::ios::vma_profile.capture();
    ensure(sampled.captured && sampled.sampled && sampled.block_bytes == 0x1'0000'0000ull + 1000);
    ensure(sampled.allocated == 0x8000'0000ull + 200 && sampled.unused == sampled.block_bytes - sampled.allocated);
    ensure(budget_queries == 1);
    rpcs3::ios::vma_profile.capture(); ensure(budget_queries == 1); // Reporter never enters VMA.
    old.destroy();
    auto stopped = rpcs3::ios::vma_profile.capture();
    ensure(stopped.captured && !stopped.owner_live && !stopped.sampled && !stopped.block_bytes && !stopped.allocated && !stopped.unused);
    ensure(stopped.generation == sampled.generation && allocator_destroys == 1);

    vk::mem_allocator_vma next;
    auto fresh = rpcs3::ios::vma_profile.capture();
    ensure(fresh.generation > stopped.generation && !fresh.sampled && !fresh.block_bytes);
    next.get_memory_usage();
    // A late diagnostic publication/teardown from the old allocator cannot
    // overwrite a current allocator. This does not call Vulkan on a dead object.
    ensure(!rpcs3::ios::vma_profile.publish(&old, {}));
    rpcs3::ios::vma_profile.end(&old);
    auto surviving = rpcs3::ios::vma_profile.capture();
    ensure(surviving.owner_live && surviving.sampled && surviving.generation == fresh.generation && surviving.block_bytes == sampled.block_bytes);
    fixture[0] = {{100, 300}, 0, 1000}; fixture[1] = {};
    next.get_memory_usage(); ensure(rpcs3::ios::vma_profile.capture().unused == 0); // Saturation, no unsigned underflow.
    next.destroy();
}

void texture_test() {
    vk::texture_cache cache;
    ensure(!rpcs3::ios::texture_profile.capture().sampled);
    cache.add(0x1'0000'0000ull); cache.add(100); cache.add(200); cache.add(300);
    cache.m_storage.m_unreleased_texture_objects = cache.m_max_zombie_objects;
    cache.on_frame_end(); // Existing >256MiB trim, then snapshot of remaining pool.
    auto pool = rpcs3::ios::texture_profile.capture();
    ensure(pool.captured && pool.owner_live && pool.sampled && pool.recyclable_images == 2 && pool.recyclable_bytes == 0x1'0000'0000ull + 100);
    ensure(cache.trims == 1 && cache.purges == 1 && cache.resets == 1 && cache.end_calls == 1);
    cache.clear();
    auto cleared = rpcs3::ios::texture_profile.capture();
    ensure(cleared.captured && cleared.owner_live && cleared.sampled && !cleared.recyclable_images && !cleared.recyclable_bytes);
    ensure(cleared.generation == pool.generation);
    ensure(cache.m_cache_is_exiting && cache.m_cached_images.empty() && !cache.m_cached_memory_size && cache.clear_calls == 1);
    cache.destroy();
    auto destroyed = rpcs3::ios::texture_profile.capture();
    ensure(destroyed.captured && !destroyed.owner_live && !destroyed.sampled && !destroyed.recyclable_images && !destroyed.recyclable_bytes);
    ensure(destroyed.generation == cleared.generation && cache.clear_calls == 2);
    vk::texture_cache next;
    next.add(123); next.on_frame_end();
    rpcs3::ios::texture_profile.end(&cache);
    auto live = rpcs3::ios::texture_profile.capture();
    ensure(live.generation > cleared.generation && live.sampled && live.recyclable_images == 1 && live.recyclable_bytes == 123);
    next.destroy();
}

void concurrent_test() {
    rpcs3::ios::owned_memory_profile<rpcs3::ios::vma_memory_sample> channel;
    int owner = 0;
    std::atomic<bool> done{false};
    std::atomic<u64> published{0};
    std::thread writer([&] {
        for (u64 n = 1; n <= 30000; ++n) {
            channel.begin(&owner);
            rpcs3::ios::vma_memory_sample sample;
            sample.block_bytes = n * 100;
            sample.allocated = n * 60;
            sample.unused = n * 40;
            if (channel.publish(&owner, sample)) ++published;
            channel.end(&owner);
        }
        done = true;
    });
    u64 captures = 0, skipped = 0;
    while (!done) {
        auto s = channel.capture();
        if (!s.captured) { ++skipped; continue; }
        ++captures;
        if (s.sampled) ensure(s.owner_live && s.block_bytes == s.allocated + s.unused && s.block_bytes / 100 == s.generation);
        else ensure(!s.block_bytes && !s.allocated && !s.unused);
    }
    writer.join();
    auto final = channel.capture();
    ensure(final.captured && !final.owner_live && !final.sampled && !final.block_bytes && final.generation == 30000);
    ensure(published > 0);
    std::cout << "PASS coherent 30000 lifecycle epochs, captures=" << captures << ", nonblocking skips=" << skipped << '\n';
}

int main(int argc, char** argv) {
    if (argc > 1 && std::string_view(argv[1]) == "--benchmark") {
        rpcs3::ios::owned_memory_profile<rpcs3::ios::texture_memory_sample> channel;
        int owner = 0; channel.begin(&owner);
        rpcs3::ios::texture_memory_sample sample; sample.recyclable_images = 7; sample.recyclable_bytes = 1234567;
        constexpr unsigned n = 1000000;
        auto begin = std::chrono::steady_clock::now();
        for (unsigned i = 0; i < n; ++i) ensure(channel.publish(&owner, sample));
        auto middle = std::chrono::steady_clock::now();
        u64 sum = 0;
        for (unsigned i = 0; i < n; ++i) sum += channel.capture().recyclable_images;
        auto end = std::chrono::steady_clock::now();
        ensure(sum == n * 7ull);
        std::cout << "{\"iterations\":" << n << ",\"publish_host_ns_each\":" << std::chrono::duration<double, std::nano>(middle-begin).count()/n
                  << ",\"capture_host_ns_each\":" << std::chrono::duration<double, std::nano>(end-middle).count()/n
                  << ",\"texture_channel_bytes\":" << sizeof(channel) << ",\"dynamic_allocations_per_sample\":0,\"try_lock_attempts_per_sample\":1}\n";
        return 0;
    }
    nonblocking_test(); lifecycle_test(); texture_test(); concurrent_test();
    std::cout << "PASS allocator stop/reset, >32-bit values, delayed-owner exclusion, no VMA call from reporter, preserved pressure/ReBAR policy, existing texture trim/lifecycle, held-writer refusal\n";
}
