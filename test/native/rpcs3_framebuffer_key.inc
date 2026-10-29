#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <concepts>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <new>
#include <ranges>
#include <set>
#include <shared_mutex>
#include <tuple>
#include <unordered_map>
#include <vector>

using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
template <typename T> using atomic_t = std::atomic<T>;
using usz = std::size_t;
using uint = unsigned;
using VkDevice = u64;
using VkImage = u64;
using VkImageView = u64;
using VkFramebuffer = u64;
using VkRenderPass = u64;
using VkBool32 = u32;
using VkFormat = u32;
using VkImageAspectFlags = u32;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT = 1;
constexpr u32 VK_IMAGE_VIEW_TYPE_2D = 1;
constexpr u32 VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO = 37;
struct VkComponentMapping {};
struct VkImageSubresourceRange { u32 aspectMask, baseMipLevel, levelCount, baseArrayLayer, layerCount; };
struct VkFramebufferCreateInfo
{
    u32 sType{}, width{}, height{}, attachmentCount{};
    const VkImageView* pAttachments{};
    VkRenderPass renderPass{};
    u32 layers{};
};

#define ensure(x) assert(x)
#define CHECK_RESULT(x) assert((x) == 0)
#define FN(expr) [&](const auto& x) { return (expr); }

static u64 created_fbos{}, destroyed_fbos{}, next_fbo{1}, next_view{1};
static int vkCreateFramebuffer(VkDevice, const VkFramebufferCreateInfo* info, void*, VkFramebuffer* result)
{
    assert(info->layers == 1 && info->attachmentCount > 0);
    assert(info->pAttachments);
    *result = next_fbo++;
    ++created_fbos;
    return 0;
}
static void vkDestroyFramebuffer(VkDevice, VkFramebuffer value, void*)
{
    assert(value > 0);
    ++destroyed_fbos;
}

using shared_mutex = std::shared_mutex;
struct reader_lock
{
    shared_mutex& mutex;
    std::shared_lock<shared_mutex> reader;
    std::unique_lock<shared_mutex> writer;
    explicit reader_lock(shared_mutex& m) : mutex(m), reader(m) {}
    void upgrade()
    {
        reader.unlock();
        writer = std::unique_lock<shared_mutex>(mutex);
    }
};

namespace rsx
{
    // Production refcount/idle-age methods, with host standard atomic storage.
@REFCOUNT@
}

namespace vk
{
    static const VkComponentMapping default_component_map{};
    struct image
    {
        VkImage value;
        struct { VkFormat format; } info;
        VkImageAspectFlags aspect() const { return VK_IMAGE_ASPECT_COLOR_BIT; }
        VkFormat format() const { return info.format; }
        u8 samples() const { return 1; }
    };
    struct image_view
    {
        VkImageView value;
        struct { VkImage image; VkFormat format; } info;
        vk::image* object{};
        image_view(VkDevice, vk::image* img, VkFormat format, u32,
                   VkComponentMapping, VkImageSubresourceRange)
            : value(next_view++), info{img->value, format}, object(img) {}
        image_view(VkDevice, VkImage img, u32, VkFormat format,
                   VkComponentMapping, VkImageSubresourceRange)
            : value(next_view++), info{img, format} {}
        vk::image* image() const { return object; }
    };
@FRAMEBUFFER@
@HOLDER@
}

namespace before
{
@BEFORE@
}
namespace after
{
@AFTER@
}

template <typename Key>
[[gnu::noinline]] static u64 construct_key(u16 width, u16 height, VkBool32 input, u8 fill)
{
    alignas(Key) std::array<u8, sizeof(Key)> storage;
    storage.fill(fill);
    Key* key = new (storage.data()) Key(width, height, input);
    u64 representation;
    // Read the complete initialized storage representation, including the
    // old constructor's untouched bytes. Do not rely on arbitrary stack data.
    std::memcpy(&representation, key, sizeof(representation));
    key->~Key();
    return representation;
}

static u64 key_cases{}, old_varying_cases{}, normalized_bit_cases{};
static std::set<u64> old_key_buckets, new_key_buckets;
static void key_representations()
{
    static_assert(sizeof(before::framebuffer_storage_key) == sizeof(u64));
    static_assert(sizeof(after::framebuffer_storage_key) == sizeof(u64));
    std::map<std::tuple<u16, u16, bool>, u64> identities;
    std::set<u64> distinct;
    const std::array<u16, 9> sizes{0, 1, 2, 255, 256, 720, 1080, 32768, 65535};
    const std::array<u32, 5> inputs{0, 1, 2, 3, 0xffffffffu};
    for (u16 w : sizes) for (u16 h : sizes) for (u32 input : inputs)
    {
        std::set<u64> old_representations;
        u64 first = 0;
        for (u32 fill = 0; fill < 256; ++fill)
        {
            const auto previous = construct_key<before::framebuffer_storage_key>(w, h, input, static_cast<u8>(fill));
            const auto current = construct_key<after::framebuffer_storage_key>(w, h, input, static_cast<u8>(fill));
            if (!fill) first = current;
            assert(current == first);
            // Production field widths define the old lower 33 bits. Validate
            // them directly, including VkBool32 values that truncate to 1 bit.
            assert((previous & 0x1ffffffffull) == current);
            assert((current >> 33) == 0);
            old_representations.insert(previous);
            ++key_cases;
        }
        old_varying_cases += old_representations.size() > 1;
        const auto tuple = std::tuple{w, h, static_cast<bool>(input & 1)};
        auto [it, inserted] = identities.emplace(tuple, first);
        if (inserted) assert(distinct.insert(first).second);
        else assert(it->second == first);
        ++normalized_bit_cases;
    }

    // Controlled object representations are fed into the same map key type
    // as production. This quantifies key fragmentation, not game FBO misses.
    for (u32 fill = 0; fill < 256; ++fill)
    {
        const auto previous = construct_key<before::framebuffer_storage_key>(1280, 720, 0, static_cast<u8>(fill));
        const auto current = construct_key<after::framebuffer_storage_key>(1280, 720, 0, static_cast<u8>(fill));
        before::g_framebuffers_cache.try_emplace(previous);
        after::g_framebuffers_cache.try_emplace(current);
        old_key_buckets.insert(previous);
        new_key_buckets.insert(current);
    }
    assert(after::g_framebuffers_cache.size() == 1);
    assert(before::g_framebuffers_cache.size() == old_key_buckets.size());
    before::clear_framebuffer_cache();
    after::clear_framebuffer_cache();
}

static u64 queries{}, cache_hits{}, invalidations{}, ownership_cases{};
static void production_cache()
{
    using namespace after;
    vk::image a{100, {17}}, b{101, {17}}, c{100, {23}};
    auto list_get = [&](u16 w, u16 h, VkBool32 input, const std::vector<vk::image*>& images)
    {
        const u64 start = created_fbos;
        auto* value = after::get_framebuffer(1, w, h, input, 8, images);
        cache_hits += created_fbos == start;
        ++queries;
        return value;
    };
    auto raw_get = [&](u16 w, u16 h, VkBool32 input, VkImage handle, VkFormat format = 17)
    {
        const u64 start = created_fbos;
        auto* value = after::get_framebuffer(1, w, h, input, 8, format, handle);
        cache_hits += created_fbos == start;
        ++queries;
        return value;
    };
    auto live = [] { return created_fbos - destroyed_fbos; };
    auto* first = list_get(1280, 720, 0, {&a});
    for (u32 i = 0; i < 1000; ++i) assert(list_get(1280, 720, 0, {&a}) == first);
    auto* width = list_get(1281, 720, 0, {&a});
    auto* height = list_get(1280, 721, 0, {&a});
    auto* input = list_get(1280, 720, 1, {&a});
    assert(width != first && height != first && input != first);
    assert(list_get(1280, 720, 2, {&a}) == first);
    assert(list_get(1280, 720, 3, {&a}) == input);
    auto* format = list_get(1280, 720, 0, {&c});
    auto* other = list_get(1280, 720, 0, {&b});
    auto* ab = list_get(1280, 720, 0, {&a, &b});
    auto* ba = list_get(1280, 720, 0, {&b, &a});
    assert(format != first && other != first && ab != first && ba != ab);
    assert(list_get(1280, 720, 0, {&c}) == format);
    assert(list_get(1280, 720, 0, {&a, &b}) == ab);
    assert(list_get(1280, 720, 0, {&b, &a}) == ba);
    // The raw-image overload intentionally keeps its original first-image
    // predicate (it does not add the vector overload's format/count checks).
    assert(raw_get(1280, 720, 0, a.value, 99) == first);
    const auto count = live();
    after::remove_framebuffers_with_image(static_cast<const vk::image*>(nullptr));
    after::remove_framebuffers_with_image(VkImage{});
    assert(live() == count);
    after::remove_framebuffers_with_image(&a);
    ++invalidations;
    assert(live() == 1 && list_get(1280, 720, 0, {&b}) == other);
    const u64 creations = created_fbos;
    first = list_get(1280, 720, 0, {&a});
    assert(created_fbos == creations + 1);
    assert(list_get(1280, 720, 0, {&a}) == first);
    after::remove_framebuffers_with_image(b.value);
    ++invalidations;
    assert(live() == 1);
    auto* raw = raw_get(640, 480, 0, 102);
    assert(raw_get(640, 480, 0, 102) == raw);
    assert(raw_get(641, 480, 0, 102) != raw);
    assert(raw_get(640, 481, 0, 102) != raw);
    assert(raw_get(640, 480, 1, 102) != raw);
    after::remove_framebuffers_with_image(VkImage{102});
    ++invalidations;
    assert(live() == 1);
    first->add_ref();
    remove_unused_framebuffers();
    remove_unused_framebuffers();
    assert(live() == 1 && list_get(1280, 720, 0, {&a}) == first);
    ++ownership_cases;
    first->release();
    remove_unused_framebuffers();
    assert(live() == 1);
    remove_unused_framebuffers();
    assert(live() == 1);
    remove_unused_framebuffers();
    assert(live() == 0);
    ++ownership_cases;
    const auto before_create = created_fbos;
    raw = raw_get(640, 480, 0, 102);
    assert(created_fbos == before_create + 1);
    assert(raw_get(640, 480, 0, 102) == raw);
    clear_framebuffer_cache();
    assert(live() == 0 && g_framebuffers_cache.empty());
    raw_get(640, 480, 0, 102);
    clear_framebuffer_cache();
    assert(live() == 0);
}

int main()
{
    key_representations();
    production_cache();
    assert(created_fbos == destroyed_fbos);
    std::cout << "{\"keyConstructionsPerVersion\":" << key_cases + 256
              << ",\"fieldCases\":" << normalized_bit_cases
              << ",\"preimageCasesVaryingWithPriorBytes\":" << old_varying_cases
              << ",\"controlledPreimageKeyBuckets\":" << old_key_buckets.size()
              << ",\"controlledFixedKeyBuckets\":" << new_key_buckets.size()
              << ",\"productionCacheQueries\":" << queries
              << ",\"productionCacheHits\":" << cache_hits
              << ",\"productionFBOCreations\":" << created_fbos
              << ",\"productionFBODestructions\":" << destroyed_fbos
              << ",\"imageInvalidations\":" << invalidations
              << ",\"ownershipCases\":" << ownership_cases
              << ",\"allDefinedKeyBitsPreserved\":true"
              << ",\"bothLookupOverloadsExecuted\":true"
              << ",\"attachmentPredicateOrderPreserved\":true"
              << ",\"physicalDeviceCacheMissesMeasured\":false}\n";
}
