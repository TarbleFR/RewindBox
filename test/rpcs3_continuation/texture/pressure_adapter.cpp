#include <atomic>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <unordered_map>
#include <vector>
using u32 = uint32_t;
using u64 = uint64_t;
static unsigned checks = 0;
template<class T> void ensure(const T& x) { ++checks; if (!x) throw std::runtime_error("pressure assertion"); }
namespace rsx { enum class problem_severity { low, moderate, severe, fatal }; }
struct { void warning(const char*) {} } rsx_log;
struct tracking_mutex {
    std::mutex inner;
    std::atomic<bool> held{false};
    void lock() { inner.lock(); held = true; }
    bool try_lock() { if (!inner.try_lock()) return false; held = true; return true; }
    void unlock() { held = false; inner.unlock(); }
};
namespace vk {
static std::atomic<u64> live_bytes{0};
static std::function<void()> during_retire;
static tracking_mutex* pool_mutex = nullptr;
static tracking_mutex* cache_mutex = nullptr;
static void interleave()
{
    if (!during_retire) return;
    auto callback = std::move(during_retire);
    during_retire = nullptr;
    callback();
}
struct image {
    u64 bytes;
    explicit image(u64 n) : bytes(n) { live_bytes += n; }
    ~image() {
        if (pool_mutex) {
            ensure(!pool_mutex->held);
        }
        if (cache_mutex) ensure(!cache_mutex->held);
        live_bytes -= bytes;
        interleave();
    }
};
struct view { std::unique_ptr<image> storage; };
struct resource_manager {
    std::vector<std::unique_ptr<image>> pending;
    void dispose(std::unique_ptr<image>& x) { pending.push_back(std::move(x)); interleave(); }
} gc;
resource_manager* get_resource_manager() { return &gc; }
struct basecache {
    bool base_released = false;
    bool handle_memory_pressure(rsx::problem_severity) { return base_released; }
};
struct texture_cache : basecache {
    using baseclass = basecache;
    struct cached_image_t { std::unique_ptr<image> data; };
    std::deque<cached_image_t> m_cached_images;
    std::atomic<u64> m_cached_memory_size{0};
    tracking_mutex m_cache_mutex, m_cached_pool_lock;
    std::unordered_map<u32, std::pair<u32, view*>> m_temporary_subresource_cache;
    bool handle_memory_pressure(rsx::problem_severity);
    void release_temporary_subresource(view* p) { gc.dispose(p->storage); delete p; }
    void seed(u64 bytes) {
        std::lock_guard lock(m_cached_pool_lock);
        m_cached_images.push_back({std::make_unique<image>(bytes)});
        m_cached_memory_size += bytes;
    }
};
// INSERT_PRODUCTION_PRESSURE
}
int main() {
    using namespace vk;
    using rsx::problem_severity;
    constexpr u64 mib = 1024 * 1024;
    u64 retained_after_pressure = 0;
    for (auto severity : {problem_severity::moderate, problem_severity::severe, problem_severity::fatal}) {
        texture_cache cache;
        for (int i = 0; i < 64; ++i) cache.seed(4 * mib);
        cache.m_temporary_subresource_cache.emplace(1, std::make_pair(0, new view{std::make_unique<image>(2 * mib)}));
        pool_mutex = &cache.m_cached_pool_lock;
        cache_mutex = &cache.m_cache_mutex;
        ensure(live_bytes == 258 * mib);
        ensure(cache.handle_memory_pressure(severity));
        ensure(cache.m_cached_images.empty());
        ensure(cache.m_cached_memory_size == 0);
        ensure(cache.m_temporary_subresource_cache.empty());
        // An active temporary image must remain queued until GPU completion.
#ifdef EXPECT_BASELINE
        ensure(live_bytes == 258 * mib);
        ensure(gc.pending.size() == 65);
#else
        ensure(live_bytes == 2 * mib);
        ensure(gc.pending.size() == 1);
#endif
        retained_after_pressure = live_bytes;
        gc.pending.clear();
        ensure(live_bytes == 0);
        pool_mutex = nullptr;
        cache_mutex = nullptr;
    }
    for (auto severity : {problem_severity::low, problem_severity::moderate}) {
        texture_cache cache;
        cache.seed(63 * mib);
        ensure(!cache.handle_memory_pressure(severity));
        ensure(live_bytes == 63 * mib);
        ensure(cache.m_cached_memory_size == 63 * mib);
    }
    ensure(live_bytes == 0);
    {
        texture_cache cache;
        cache.base_released = true;
        ensure(cache.handle_memory_pressure(problem_severity::fatal));
        ensure(gc.pending.empty());
    }
    {
        texture_cache cache;
        cache.seed(64 * mib);
        std::unique_lock guard(cache.m_cache_mutex);
        bool result = true;
        std::thread requester([&] { result = cache.handle_memory_pressure(problem_severity::severe); });
        requester.join();
        ensure(!result);
        ensure(cache.m_cached_memory_size == 64 * mib);
    }
    for (unsigned i = 0; i < 1000; ++i) {
        texture_cache cache;
        cache.seed(64 * mib);
        pool_mutex = &cache.m_cached_pool_lock;
        cache_mutex = &cache.m_cache_mutex;
        during_retire = [&] {
            std::thread driver([&] { cache.seed(4096); });
            driver.join();
        };
        ensure(cache.handle_memory_pressure(problem_severity::severe));
        ensure(cache.m_cached_images.size() == 1);
        ensure(cache.m_cached_memory_size == 4096);
        gc.pending.clear();
        ensure(live_bytes == 4096);
        pool_mutex = nullptr;
        cache_mutex = nullptr;
    }
    ensure(live_bytes == 0);
    std::cout << "{\"case\":\"retired_image_pressure\",\"checks\":" << checks
              << ",\"completed_pool_bytes\":" << 256 * mib
              << ",\"active_temporary_bytes\":" << 2 * mib
              << ",\"retained_after_pressure\":" << retained_after_pressure
              << ",\"late_driver_returns\":1000}\n";
}
