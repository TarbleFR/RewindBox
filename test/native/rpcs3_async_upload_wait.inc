#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
#include <algorithm>
using u32 = std::uint32_t;
using VkQueue = std::uint64_t;
using VkSemaphore = std::uint64_t;
using VkCommandBuffer = std::uint64_t;
using VkPipelineStageFlags = u32;
using VkBool32 = u32;
constexpr auto VK_NULL_HANDLE = 0;
constexpr VkBool32 VK_TRUE = 1, VK_FALSE = 0;
constexpr VkPipelineStageFlags VK_PIPELINE_STAGE_VERTEX_SHADER_BIT = 0x8;
constexpr VkPipelineStageFlags VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT = 0x80;
constexpr VkPipelineStageFlags VK_PIPELINE_STAGE_TRANSFER_BIT = 0x1000;
constexpr VkPipelineStageFlags EXTERNAL_STAGE = 0x4;
constexpr auto GENERAL_WAIT_TIMEOUT = 100;
template<class T> auto& at32(T& container, u32 index) { return container.at(index); }
void ensure(bool ok) { assert(ok); }
namespace vk {
struct render_device { VkQueue get_graphics_queue() const { return 9; } };
struct fence { explicit fence(render_device&) {} };
struct semaphore { operator VkSemaphore() const { return 42; } };
// @QUEUE_SUBMIT@
struct Event { char kind; queue_submit_t packet; VkBool32 force; };
static std::vector<Event> events;
static u32 scope_count = 0;
struct ResourceManager { void push_down_current_scope() { ++scope_count; } } resource_manager;
ResourceManager* get_resource_manager() { return &resource_manager; }
struct AsyncTaskScheduler {
    bool recording = false, host = false;
    semaphore sema;
    bool is_recording() const { return recording; }
    bool is_host_mode() const { return host; }
    semaphore* get_sema() { return &sema; }
    void flush(queue_submit_t& packet, VkBool32 force) {
        events.push_back({'A', packet, force}); recording = false;
    }
};
struct command_buffer {
    enum access_type_hint { flush_only, all };
    enum { cb_has_open_query = 0x08, cb_load_occluson_task = 0x10 };
    u32 flags = 0;
    access_type_hint access_hint = flush_only;
    bool recording = true;
    void end() { assert(recording); recording = false; events.push_back({'E', {}, 0}); }
    void submit(queue_submit_t& packet, VkBool32 force) {
        events.push_back({'P', packet, force}); flags = 0;
        if (access_hint == all) recording = true;
    }
    void reset() { assert(!recording); events.push_back({'R', {}, 0}); }
    void begin() { assert(!recording); recording = true; events.push_back({'B', {}, 0}); }
    bool is_recording() const { return recording; }
};
void do_query_cleanup(command_buffer& cmd) {
    assert(cmd.flags & command_buffer::cb_has_open_query);
    cmd.flags &= ~command_buffer::cb_has_open_query;
    events.push_back({'Q', {}, 0});
}
void wait_for_fence(fence*, int timeout) { assert(timeout == GENERAL_WAIT_TIMEOUT); events.push_back({'F', {}, 0}); }
struct texture_cache {
    render_device* m_device;
    VkQueue m_submit_queue = 9;
    void cleanup_after_dma_transfers(command_buffer&);
};
}
struct Registry {
    vk::AsyncTaskScheduler* current = nullptr;
    template<class T> T* try_get() { return current; }
} registry;
Registry* g_fxo = &registry;
namespace rpcs3::ios::rsx_sync {
enum { texture };
struct SiteScope { SiteScope(int, bool) {} };
}
struct VKGSRender {
    vk::render_device* m_device;
    vk::command_buffer* m_current_command_buffer;
    void submit_primary(vk::fence* pFence, VkSemaphore wait_semaphore,
        VkPipelineStageFlags pipeline_stage_flags, VkSemaphore signal_semaphore, VkBool32 force_flush) {
// @PRIMARY_SUBMIT@
    }
};
namespace vk {
// @DMA_CLEANUP@
}
static constexpr bool candidate = @CANDIDATE@;
static constexpr VkPipelineStageFlags all_consumers = VK_PIPELINE_STAGE_TRANSFER_BIT |
    VK_PIPELINE_STAGE_VERTEX_SHADER_BIT | VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;
static bool primary_scope_missing = false, readback_scope_missing = false;
static u32 primary_cases = 0, readback_cases = 0;
static void start_case(vk::AsyncTaskScheduler& scheduler, int mode) {
    vk::events.clear(); vk::scope_count = 0;
    scheduler.recording = mode >= 2;
    scheduler.host = mode != 3;
    registry.current = mode ? &scheduler : nullptr;
}
static std::vector<vk::Event> select(char kind) {
    std::vector<vk::Event> result;
    for (auto& event : vk::events) if (event.kind == kind) result.push_back(event);
    return result;
}
static void check_wait(const vk::queue_submit_t& packet, u32 slot, bool& missing) {
    assert(packet.wait_semaphores.at(slot) == 42);
    const auto stages = packet.wait_stages.at(slot);
#ifdef RPCS3_IOS
    assert(stages == (candidate ? all_consumers : VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT));
    missing |= (stages & all_consumers) != all_consumers;
#else
    assert(stages == VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
#endif
    (void)missing;
}
static void check_order(bool producer) {
    if (producer) {
        const auto async = std::find_if(vk::events.begin(), vk::events.end(), [](auto& e) { return e.kind == 'A'; });
        const auto primary = std::find_if(vk::events.begin(), vk::events.end(), [](auto& e) { return e.kind == 'P'; });
        assert(async < primary);
    }
}
static void test_primary() {
    for (int mode = 0; mode < 4; ++mode) for (int external = 0; external < 2; ++external)
    for (VkBool32 force : {VK_FALSE, VK_TRUE}) {
        vk::AsyncTaskScheduler scheduler; start_case(scheduler, mode);
        vk::render_device device; vk::command_buffer cmd;
        VKGSRender renderer{&device, &cmd};
        vk::fence fence(device);
        renderer.submit_primary(&fence, external ? 101 : 0, EXTERNAL_STAGE, external ? 102 : 0, force);
        const auto primaries = select('P'), producers = select('A');
        assert(primaries.size() == 1 && producers.size() == (mode >= 2 ? 1u : 0u));
        const auto& packet = primaries[0].packet;
        assert(packet.queue == 9 && packet.pfence == &fence && primaries[0].force == force);
        assert(packet.wait_semaphores_count == u32(external + (mode == 2)));
        assert(packet.signal_semaphores_count == u32(external));
        if (external) {
            assert(packet.wait_semaphores[0] == 101 && packet.wait_stages[0] == EXTERNAL_STAGE);
            assert(packet.signal_semaphores[0] == 102);
        }
        if (mode == 2) {
            check_wait(packet, external, primary_scope_missing);
            assert(producers[0].packet.signal_semaphores_count == 1);
            assert(producers[0].packet.signal_semaphores[0] == 42);
        }
        if (mode == 3) assert(producers[0].packet.signal_semaphores_count == 0);
        if (mode >= 2) assert(producers[0].force == force);
        assert(vk::scope_count == u32(mode == 2));
        check_order(mode >= 2); ++primary_cases;
    }
}
static void test_readback() {
    for (int auxiliary = 0; auxiliary < 2; ++auxiliary) for (int mode = 0; mode < 4; ++mode)
    for (int query = 0; query < (auxiliary ? 1 : 2); ++query) {
        vk::AsyncTaskScheduler scheduler; start_case(scheduler, mode);
        vk::render_device device; vk::texture_cache cache{&device}; vk::command_buffer cmd;
        cmd.access_hint = auxiliary ? vk::command_buffer::all : vk::command_buffer::flush_only;
        if (query) cmd.flags = vk::command_buffer::cb_has_open_query;
        cache.cleanup_after_dma_transfers(cmd);
        const auto primaries = select('P'), producers = select('A');
        const bool producer = !auxiliary && mode >= 2;
        const bool host = !auxiliary && mode == 2;
        assert(primaries.size() == 1 && producers.size() == u32(producer));
        const auto& packet = primaries[0].packet;
        assert(packet.queue == 9 && primaries[0].force == VK_TRUE);
        assert((packet.pfence != nullptr) == !auxiliary);
        assert(packet.wait_semaphores_count == u32(host) && packet.signal_semaphores_count == 0);
        if (host) {
            check_wait(packet, 0, readback_scope_missing);
            assert(producers[0].packet.signal_semaphores_count == 1);
            assert(producers[0].packet.signal_semaphores[0] == 42);
        }
        if (producer) assert(producers[0].force == VK_TRUE);
        if (producer && !host) assert(producers[0].packet.signal_semaphores_count == 0);
        assert(select('F').size() == u32(!auxiliary));
        assert(select('R').size() == u32(!auxiliary));
        assert(select('B').size() == u32(!auxiliary));
        assert(select('Q').size() == u32(query));
        assert(cmd.is_recording());
        assert(cmd.flags == (query ? vk::command_buffer::cb_load_occluson_task : 0));
        assert(vk::scope_count == 0);
        check_order(producer); ++readback_cases;
    }
}
int main() {
    (void)candidate; (void)all_consumers;
    test_primary(); test_readback();
    assert(primary_cases == 16 && readback_cases == 12);
    std::cout << "{\"primaryCases\":" << primary_cases << ",\"readbackCases\":" << readback_cases
        << ",\"unprotectedConsumerSites\":" << (u32(primary_scope_missing) + u32(readback_scope_missing)) << "}\n";
#ifdef RPCS3_IOS
    if (primary_scope_missing || readback_scope_missing) {
        assert(!candidate && primary_scope_missing && readback_scope_missing);
        std::cerr << "primary TRANSFER/vertex consumers unprotected\nreadback TRANSFER/vertex consumers unprotected\n";
        return 86;
    }
#endif
}
