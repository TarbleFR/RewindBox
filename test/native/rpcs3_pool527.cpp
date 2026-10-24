#include "rpcs3/ios/IOSRecyclableImagePool.h"
#include "rpcs3/ios/IOSGPUMemoryProfile.h"
#include <chrono>
#include <algorithm>
#include <string_view>
#include <array>
#include <atomic>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <stdexcept>
#include <thread>
#include <unordered_map>
#include <vector>

using u8 = uint8_t;
using u16 = uint16_t;
using u32 = uint32_t;
using u64 = uint64_t;
using usz = size_t;
using VkFormat = u32;
using VkImageType = u32;
using VkImageCreateFlags = u32;
using VkImageUsageFlags = u32;
using VkSharingMode = u32;
struct shared_mutex : std::shared_mutex
{
    inline static thread_local unsigned held = 0;
    void lock() { std::shared_mutex::lock(); ++held; }
    void unlock() { --held; std::shared_mutex::unlock(); }
    bool try_lock() { if (!std::shared_mutex::try_lock()) return false; ++held; return true; }
};

static std::atomic<unsigned> checks{0};
template <typename T> static void ensure(const T& value)
{
    ++checks;
    if (!value)
    {
#ifdef POOL_NO_EXCEPTIONS
        std::abort();
#else
        throw std::runtime_error("Image-pool ownership/accounting assertion failed");
#endif
    }
}
template <typename T> u32 size32(const T& values) { return static_cast<u32>(values.size()); }
struct reader_lock
{
    shared_mutex& mutex;
    bool exclusive = false;
    explicit reader_lock(shared_mutex& m) : mutex(m) { mutex.lock_shared(); }
    void upgrade() { mutex.unlock_shared(); mutex.lock(); exclusive = true; }
    ~reader_lock() { if (exclusive) mutex.unlock(); else mutex.unlock_shared(); }
};
namespace rsx { enum class problem_severity { low, moderate, severe, fatal }; }
struct { void warning(const char*) {} } rsx_log;
namespace vk
{
struct memory_block { u64 bytes = 4096; u64 size() const { return bytes; } };
struct viewable_image
{
    // Match the reported arm64 image usage offset, verified from product DWARF.
    std::array<u8, 0xb8> padding{};
    struct { u32 usage = 3, imageType = 0, flags = 0, sharingMode = 0; } info;
    u32 current_layout{}, current_queue_family{}, identity{};
    bool must_destroy_unlocked = false;
    inline static std::atomic<u64> destroyed = 0;
    ~viewable_image()
    {
        if (must_destroy_unlocked) ensure(shared_mutex::held == 0);
        ++destroyed;
    }
    std::unique_ptr<memory_block> memory = std::make_unique<memory_block>();
    u32 format() const { return 1; }
    u16 width() const { return 2; }
    u16 height() const { return 2; }
    u16 depth() const { return 1; }
    u16 mipmaps() const { return 1; }
};
static_assert(offsetof(viewable_image, info) == 0xb8);
constexpr u32 VK_IMAGE_LAYOUT_UNDEFINED = 0;
constexpr u32 VK_QUEUE_FAMILY_IGNORED = ~0u;
struct resource_manager
{
    std::vector<std::unique_ptr<viewable_image>> pending;
    std::function<void()> during_disposal;
    void dispose(std::unique_ptr<viewable_image>& image)
    {
        pending.push_back(std::move(image));
        if (during_disposal)
        {
            auto callback = std::move(during_disposal);
            during_disposal = nullptr;
            callback();
        }
    }
} gc;
resource_manager* get_resource_manager() { return &gc; }
struct basecache
{
    bool handle_memory_pressure(rsx::problem_severity) { return false; }
    void clear() {}
    void on_frame_end() {}
    u32 get_unreleased_textures_count() const { return 0; }
};
struct texture_cache : basecache
{
    using baseclass = basecache;
    struct cached_image_reference_t
    {
        std::unique_ptr<viewable_image> data;
        texture_cache* parent;
        cached_image_reference_t(texture_cache*, std::unique_ptr<viewable_image>&);
        ~cached_image_reference_t();
    };
    struct cached_image_t
    {
        u64 key{};
        std::unique_ptr<viewable_image> data;
        cached_image_t() = default;
        cached_image_t(u64 k, std::unique_ptr<viewable_image>& image) : key(k), data(std::move(image)) {}
    };
    std::deque<cached_image_t> m_cached_images;
    std::atomic<u64> m_cached_memory_size{0};
    mutable shared_mutex m_cached_pool_lock;
    bool m_cache_is_exiting = false;
    std::mutex m_cache_mutex;
    std::unordered_map<u32, std::pair<u32, unsigned*>> m_temporary_subresource_cache;
    struct { u32 m_unreleased_texture_objects = 0; } m_storage;
    u32 m_max_zombie_objects = 10, max_cached_image_pool_size = 256, released_views = 0;
    void release_temporary_subresource(unsigned* view) { delete view; ++released_views; }
    void trim_sections() {}
    void purge_unreleased_sections() {}
    void reset_frame_statistics() {}
    void clear();
    void on_frame_end();
    bool handle_memory_pressure(rsx::problem_severity);
    u32 get_unreleased_textures_count() const;
    std::unique_ptr<viewable_image> find_cached_image(VkFormat, u16, u16, u16, u16, VkImageType, VkImageCreateFlags, VkImageUsageFlags, VkSharingMode);
    void driver_return(u32 id, u64 bytes = 4096, bool unlocked = false)
    {
        auto image = std::make_unique<viewable_image>();
        image->identity = id;
        image->memory->bytes = bytes;
        image->must_destroy_unlocked = unlocked;
        cached_image_reference_t completion(this, image);
    }
    std::unique_ptr<viewable_image> lookup(u32 usage = 1)
    {
        return find_cached_image(1, 2, 2, 1, 1, 0, 0, usage, 0);
    }
};
}
#include "VKImagePool.inc"


static constexpr u64 MiB = 1024 * 1024;
static void invariant(vk::texture_cache& cache)
{
    std::lock_guard lock(cache.m_cached_pool_lock);
    u64 total = 0;
    for (const auto& image : cache.m_cached_images)
    {
        ensure(image.data);
        total += image.data->memory->size();
    }
    ensure(total == cache.m_cached_memory_size);
    ensure(total <= 256 * MiB);
    ensure(cache.m_cached_images.size() <= 256);
}

static void verify()
{
    {
        vk::texture_cache cache;
        cache.driver_return(1, 300 * MiB, true);
        invariant(cache); //526 fails: a single oversize retired image is admitted.
        ensure(cache.m_cached_images.empty());
        cache.driver_return(2, 256 * MiB, true);
        invariant(cache);
        ensure(cache.m_cached_images.size() == 1);
        cache.driver_return(3, MiB, true);
        invariant(cache);
        ensure(cache.m_cached_images.size() == 1);
        auto image = cache.lookup();
        ensure(image && image->identity == 3 && image->current_layout == vk::VK_IMAGE_LAYOUT_UNDEFINED);
        ensure(image->current_queue_family == vk::VK_QUEUE_FAMILY_IGNORED);
        invariant(cache);
    }
    {
        vk::texture_cache cache;
        for (u32 i = 0; i < 8; ++i)
        {
            cache.driver_return(i, 64 * MiB, true);
            invariant(cache);
        }
        ensure(cache.m_cached_memory_size == 256 * MiB);
        // Newest four survive; the oldest four have been retired outside the lock.
        for (u32 i = 8; i-- > 4;)
            ensure(cache.lookup()->identity == i);
        invariant(cache);
        ensure(!cache.lookup());
        for (u32 i = 0; i < 300; ++i) cache.driver_return(i, 0, true);
        invariant(cache);
        ensure(cache.m_cached_images.size() == 256);
        ensure(!cache.lookup(4));
        ensure(cache.lookup()->identity == 299);
        invariant(cache);
        // Remaining normal zero-byte entries are cleared by the legacy shutdown
        // method, whose lock scope is outside this eviction-only change.
        for (auto& entry : cache.m_cached_images) entry.data->must_destroy_unlocked = false;
        cache.clear();
        cache.driver_return(900, MiB, true); //return after shutdown cannot repopulate.
        invariant(cache);
    }
    {
        vk::texture_cache cache;
        // Exercise frame fallback on an intentionally over-budget queue. A
        // newest260MiB item survives526 count-halving and violates the byte cap.
        for (u32 id : {10u, 11u})
        {
            auto image = std::make_unique<vk::viewable_image>();
            image->identity = id;
            image->memory->bytes = id == 11 ? 260 * MiB : MiB;
            image->must_destroy_unlocked = true;
            cache.m_cached_memory_size += image->memory->bytes;
            cache.m_cached_images.emplace_front(0, image);
        }
        cache.on_frame_end();
        invariant(cache);
        ensure(cache.m_cached_images.empty());
        auto sample = rpcs3::ios::texture_profile.capture();
        // Profile was not begun by this lightweight adapter; the production
        // begin/destroy owner lifecycle is retained from525 independently.
        ensure(sample.captured);
    }
    {
        vk::texture_cache cache;
        for (u32 i = 0; i < 9; ++i) cache.driver_return(i, 32 * MiB, true);
        vk::gc.during_disposal = [&]
        {
            std::thread driver([&] { cache.driver_return(900, MiB, true); });
            driver.join();
        };
        ensure(cache.handle_memory_pressure(rsx::problem_severity::severe));
        invariant(cache);
        ensure(cache.lookup()->identity == 900);
        vk::gc.pending.clear();
    }
    {
        vk::texture_cache stress;
        std::atomic<bool> begin{false};
        std::thread driver([&]
        {
            while (!begin.load()) std::this_thread::yield();
            for (u32 i = 0; i < 30000; ++i) stress.driver_return(i, (i % 17 + 1) * MiB, true);
        });
        begin = true;
        for (u32 i = 0; i < 3000; ++i)
        {
            (void)stress.lookup();
            stress.on_frame_end();
            invariant(stress);
        }
        driver.join();
        invariant(stress);
        while (auto image = stress.lookup()) {}
        invariant(stress);
    }
}

static void benchmark()
{
    vk::texture_cache cache;
    u64 peak = 0, peak_items = 0;
    const auto start = std::chrono::steady_clock::now();
    for (u32 i = 0; i < 4096; ++i)
    {
        cache.driver_return(i, (i % 17 + 1) * MiB);
        peak = std::max(peak, cache.m_cached_memory_size.load());
        peak_items = std::max(peak_items, static_cast<u64>(cache.m_cached_images.size()));
        if (i % 64 == 63) cache.on_frame_end();
    }
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
    std::cout << "{\"logical_pool_peak_bytes\":" << peak << ",\"logical_pool_peak_items\":" << peak_items
        << ",\"end_bytes\":" << cache.m_cached_memory_size << ",\"returns\":4096,\"host_ns\":" << ns << "}\n";
}

int main(int argc, char** argv)
{
    if (argc > 1 && std::string_view(argv[1]) == "--benchmark") benchmark();
    else { verify(); std::cout << "{\"passed\":true,\"checks\":" << checks << "}\n"; }
}
