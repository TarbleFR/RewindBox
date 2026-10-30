
#include <cassert>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <source_location>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using u32=std::uint32_t;
using u64=std::uint64_t;
using s32=std::int32_t;
#define ensure(x) assert(x)
enum VkResult { VK_SUCCESS=0, VK_NOT_READY=1, VK_TIMEOUT=2, VK_EVENT_SET=3, VK_EVENT_RESET=4, VK_INCOMPLETE=5, VK_ERROR_DEVICE_LOST=6, VK_ERROR_EXTENSION_NOT_PRESENT=7, VK_ERROR_FEATURE_NOT_PRESENT=8, VK_ERROR_FORMAT_NOT_SUPPORTED=9, VK_ERROR_FRAGMENTATION_EXT=10, VK_ERROR_FRAGMENTED_POOL=11, VK_ERROR_INCOMPATIBLE_DISPLAY_KHR=12, VK_ERROR_INCOMPATIBLE_DRIVER=13, VK_ERROR_INITIALIZATION_FAILED=14, VK_ERROR_INVALID_EXTERNAL_HANDLE_KHR=15, VK_ERROR_INVALID_SHADER_NV=16, VK_ERROR_LAYER_NOT_PRESENT=17, VK_ERROR_MEMORY_MAP_FAILED=18, VK_ERROR_NATIVE_WINDOW_IN_USE_KHR=19, VK_ERROR_OUT_OF_DATE_KHR=20, VK_ERROR_OUT_OF_DEVICE_MEMORY=21, VK_ERROR_OUT_OF_HOST_MEMORY=22, VK_ERROR_OUT_OF_POOL_MEMORY_KHR=23, VK_ERROR_SURFACE_LOST_KHR=24, VK_ERROR_TOO_MANY_OBJECTS=25, VK_ERROR_VALIDATION_FAILED_EXT=26, VK_SUBOPTIMAL_KHR=27 };
struct renderer_error : std::exception {};
struct counters {
    u32 waits=0, fence_resets=0, completions=0, heaps=0, driver_resets=0;
    u32 trims=0, globals=0, frames=0, latency_records=0, fatal_errors=0, locks=0;
    u64 last_timeout=0;
} counts;
VkResult injected_wait=VK_SUCCESS, injected_status=VK_NOT_READY;
std::function<void()> upgrade_hook;
struct shared_mutex {};
struct reader_lock {
    explicit reader_lock(shared_mutex&) { ++counts.locks; }
    ~reader_lock() { --counts.locks; }
    void upgrade() { if (upgrade_hook) { auto f=std::exchange(upgrade_hook,{}); f(); } }
};
namespace fmt {
template<class... T> std::string format(const char*, T&&...) { return {}; }
template<class... T> [[noreturn]] void throw_exception(const char*, T&&...) {
    ++counts.fatal_errors; throw renderer_error{};
}
}
struct logger { template<class... T> void error(const char*, T&&...) {} } rsx_log;
namespace utils { inline u64 get_tsc() { return 42; } }
namespace rpcs3::ios::rsx_sync {
enum { cb_reuse, frame_cleanup };
struct SiteScope { explicit SiteScope(int) {} };
struct recorder { void record(u64) { ++counts.latency_records; } } frame_latency_ticks;
}
namespace vk {
void print_debug_markers() {}
std::string retrieve_device_fault_info() { return {}; }
void die_with_error(VkResult error_code, std::string message={}, std::source_location src_loc=std::source_location::current());
	void die_with_error(VkResult error_code, std::string message, std::source_location src_loc)
	{
		std::string error_message, extra_info;
		int severity = 0; // 0 - die, 1 - warn, 2 - nothing

		switch (error_code)
		{
		case VK_SUCCESS:
		case VK_EVENT_SET:
		case VK_EVENT_RESET:
		case VK_INCOMPLETE:
			return;
		case VK_SUBOPTIMAL_KHR:
			error_message = "Present surface is suboptimal (VK_SUBOPTIMAL_KHR)";
			severity = 1;
			break;
		case VK_NOT_READY:
			error_message = "Device or resource busy (VK_NOT_READY)";
			break;
		case VK_TIMEOUT:
			error_message = "Timeout event (VK_TIMEOUT)";
			break;
		case VK_ERROR_OUT_OF_HOST_MEMORY:
			error_message = "Out of host memory (system RAM) (VK_ERROR_OUT_OF_HOST_MEMORY)";
			break;
		case VK_ERROR_OUT_OF_DEVICE_MEMORY:
			error_message = "Out of video memory (VRAM) (VK_ERROR_OUT_OF_DEVICE_MEMORY)";
			break;
		case VK_ERROR_INITIALIZATION_FAILED:
			error_message = "Initialization failed (VK_ERROR_INITIALIZATION_FAILED)";
			break;
		case VK_ERROR_DEVICE_LOST:
			error_message = "Device lost (Driver crashed with unspecified error or stopped responding and recovered) (VK_ERROR_DEVICE_LOST)";
			extra_info = retrieve_device_fault_info();
			break;
		case VK_ERROR_MEMORY_MAP_FAILED:
			error_message = "Memory map failed (VK_ERROR_MEMORY_MAP_FAILED)";
			break;
		case VK_ERROR_LAYER_NOT_PRESENT:
			error_message = "Requested layer is not available (Try disabling debug output or install vulkan SDK) (VK_ERROR_LAYER_NOT_PRESENT)";
			break;
		case VK_ERROR_EXTENSION_NOT_PRESENT:
			error_message = "Requested extension not available (VK_ERROR_EXTENSION_NOT_PRESENT)";
			break;
		case VK_ERROR_FEATURE_NOT_PRESENT:
			error_message = "Requested feature not available (VK_ERROR_FEATURE_NOT_PRESENT)";
			break;
		case VK_ERROR_INCOMPATIBLE_DRIVER:
			error_message = "Incompatible driver (VK_ERROR_INCOMPATIBLE_DRIVER)";
			break;
		case VK_ERROR_TOO_MANY_OBJECTS:
			error_message = "Too many objects created (Out of handles) (VK_ERROR_TOO_MANY_OBJECTS)";
			break;
		case VK_ERROR_FORMAT_NOT_SUPPORTED:
			error_message = "Format not supported (VK_ERROR_FORMAT_NOT_SUPPORTED)";
			break;
		case VK_ERROR_FRAGMENTED_POOL:
			error_message = "Fragmented pool (VK_ERROR_FRAGMENTED_POOL)";
			break;
		case VK_ERROR_SURFACE_LOST_KHR:
			error_message = "Surface lost (VK_ERROR_SURFACE_LOST)";
			break;
		case VK_ERROR_NATIVE_WINDOW_IN_USE_KHR:
			error_message = "Native window in use (VK_ERROR_NATIVE_WINDOW_IN_USE_KHR)";
			break;
		case VK_ERROR_OUT_OF_DATE_KHR:
			error_message = "Present surface is out of date (VK_ERROR_OUT_OF_DATE_KHR)";
			severity = 1;
			break;
		case VK_ERROR_INCOMPATIBLE_DISPLAY_KHR:
			error_message = "Incompatible display (VK_ERROR_INCOMPATIBLE_DISPLAY_KHR)";
			break;
		case VK_ERROR_VALIDATION_FAILED_EXT:
			error_message = "Validation failed (VK_ERROR_INCOMPATIBLE_DISPLAY_KHR)";
			break;
		case VK_ERROR_INVALID_SHADER_NV:
			error_message = "Invalid shader code (VK_ERROR_INVALID_SHADER_NV)";
			break;
		case VK_ERROR_OUT_OF_POOL_MEMORY_KHR:
			error_message = "Out of pool memory (VK_ERROR_OUT_OF_POOL_MEMORY_KHR)";
			break;
		case VK_ERROR_INVALID_EXTERNAL_HANDLE_KHR:
			error_message = "Invalid external handle (VK_ERROR_INVALID_EXTERNAL_HANDLE_KHR)";
			break;
		case VK_ERROR_FRAGMENTATION_EXT:
			error_message = "Descriptor pool creation failed (VK_ERROR_FRAGMENTATION)";
			break;
		default:
			error_message = fmt::format("Unknown Code (%Xh, %d)%s", static_cast<s32>(error_code), static_cast<s32>(error_code), src_loc);
			break;
		}

		if (!extra_info.empty())
		{
			error_message = fmt::format("%s\n---------------- EXTRA INFORMATION --------------------\n%s", error_message, extra_info);
		}

		switch (severity)
		{
		default:
		case 0:
			print_debug_markers();

			if (!message.empty()) message += "\n\n";
			fmt::throw_exception("%sAssertion Failed! Vulkan API call failed with unrecoverable error: %s%s", message, error_message, src_loc);
		case 1:
			rsx_log.error("Vulkan API call has failed with an error but will continue: %s%s", error_message, src_loc);
			break;
		case 2:
			break;
		}
	}

struct fence {
    bool flushed=true;
    u32 handle=1;
    void reset() { ++counts.fence_resets; }
    void wait_flush() {}
};
struct command_pool { u32 get_owner() const { return 1; } } pool;
struct command_buffer {
    bool is_pending=true;
    vk::fence owned_fence;
    vk::fence* m_submit_fence=&owned_fence;
    command_pool* pool=&vk::pool;
    u32 commands=1;
    void reset();
};
VkResult wait_for_fence(fence*, u64 timeout) {
    ++counts.waits; counts.last_timeout=timeout; return injected_wait;
}
u64 get_event_id() { return 10; }
void on_event_completed(u64) { ++counts.completions; }
namespace data_heap_manager {
using managed_heap_snapshot_t=std::vector<u64>;
bool use_command_buffer_reclamation() { return true; }
managed_heap_snapshot_t get_heap_snapshot() { return {7}; }
u64 next_snapshot_id() { return 1; }
void restore_snapshot(managed_heap_snapshot_t&, u64) { ++counts.heaps; }
}
}
VkResult vkGetFenceStatus(u32,u32) { return injected_status; }
VkResult vkResetCommandBuffer(u32,u32) { ++counts.driver_resets; return VK_SUCCESS; }
#define CHECK_RESULT(expr) { VkResult _res = (expr); if (_res != VK_SUCCESS) vk::die_with_error(_res); }
#define FRAME_PRESENT_TIMEOUT 10000000ull
namespace vk {
	void command_buffer::reset()
	{
		// Do the driver reset
		CHECK_RESULT(vkResetCommandBuffer(commands, 0));
	}

	struct command_buffer_chunk : public vk::command_buffer
	{
		u64 eid_tag = 0;
		u64 reset_id = 0;
		shared_mutex guard_mutex;
		data_heap_manager::managed_heap_snapshot_t heap_snapshot;
		u64 heap_snapshot_id = 0;

		command_buffer_chunk() = default;

		inline void tag()
		{
			eid_tag = vk::get_event_id();

			if (data_heap_manager::use_command_buffer_reclamation())
			{
				heap_snapshot = data_heap_manager::get_heap_snapshot();
				heap_snapshot_id = data_heap_manager::next_snapshot_id();
			}
			else
			{
				heap_snapshot.clear();
				heap_snapshot_id = 0;
			}
		}

		void reclaim_heap_snapshot()
		{
			if (!heap_snapshot_id)
			{
				return;
			}

			data_heap_manager::restore_snapshot(heap_snapshot, heap_snapshot_id);
			heap_snapshot.clear();
			heap_snapshot_id = 0;
		}

		void reset()
		{
			if (is_pending && !poke())
			{
#ifdef RPCS3_IOS
				const rpcs3::ios::rsx_sync::SiteScope ios_sync_site(rpcs3::ios::rsx_sync::cb_reuse);
#endif
				wait(FRAME_PRESENT_TIMEOUT);
			}

			++reset_id;
			vk::command_buffer::reset();
		}

		bool poke()
		{
			reader_lock lock(guard_mutex);

			if (!is_pending)
			{
				return true;
			}

			if (!m_submit_fence->flushed)
			{
				return false;
			}

			if (vkGetFenceStatus(pool->get_owner(), m_submit_fence->handle) == VK_SUCCESS)
			{
				lock.upgrade();

				if (is_pending)
				{
					m_submit_fence->reset();
					vk::on_event_completed(eid_tag);
					reclaim_heap_snapshot();

					is_pending = false;
					eid_tag = 0;
				}
			}

			return !is_pending;
		}

		VkResult wait(u64 timeout = 0ull)
		{
			reader_lock lock(guard_mutex);

			if (!is_pending)
			{
				return VK_SUCCESS;
			}

			const auto ret = vk::wait_for_fence(m_submit_fence, timeout);
			if (ret != VK_SUCCESS)
			{
				// A timed-out fence has not completed. Report the existing Vulkan
				// error before callers can recycle this command buffer or its heaps.
				vk::die_with_error(ret);
				return ret;
			}

			lock.upgrade();

			if (is_pending)
			{
				m_submit_fence->reset();
				vk::on_event_completed(eid_tag);

				if (ret == VK_SUCCESS)
				{
					reclaim_heap_snapshot();
				}

				is_pending = false;
				eid_tag = 0;
			}

			return ret;
		}

		void flush()
		{
			reader_lock lock(guard_mutex);

			if (!is_pending)
			{
				return;
			}

			m_submit_fence->wait_flush();
		}
	};

struct command_chain {
    command_buffer_chunk m_cb_list[4];
		void wait_all()
		{
			for (auto& cb : m_cb_list)
			{
				cb.wait();
			}
		}

};
struct frame_context_t {
    command_buffer_chunk* swap_command_buffer=nullptr;
    u64 ios_submit_tsc=1,last_frame_sync_time=1,heap_snapshot_id=1;
    data_heap_manager::managed_heap_snapshot_t heap_snapshot{9};
};
struct ui_overlay_renderer { void remove_temp_resources(u32) {} } ui;
template<class T> T* get_overlay_pass() { return &ui; }
struct resources { void trim() { ++counts.trims; } } resource_manager;
resources* get_resource_manager() { return &resource_manager; }
void reset_global_resources() { ++counts.globals; }
void advance_completed_frame_counter() { ++counts.frames; }
}
struct view { u32 uid=0; };
struct overlays {
    bool has_dirty() const { return false; }
    void lock_shared() {} void unlock_shared() {}
    std::vector<view*> get_dirty() { return {}; }
    void dispose(const std::vector<u32>&) {}
};
class VKGSRender {
public:
    bool swapchain_unavailable=false;
    overlays* m_overlay_manager=nullptr;
    u64 m_last_heap_sync_time=0;
    std::deque<vk::frame_context_t*> m_queued_frames;
    void frame_context_cleanup(vk::frame_context_t*);
};
void VKGSRender::frame_context_cleanup(vk::frame_context_t *ctx)
{
	ensure(ctx->swap_command_buffer);

	// Perform hard swap here
#ifdef RPCS3_IOS
	const rpcs3::ios::rsx_sync::SiteScope ios_sync_site(rpcs3::ios::rsx_sync::frame_cleanup);
#endif
	if (ctx->swap_command_buffer->wait(FRAME_PRESENT_TIMEOUT) != VK_SUCCESS)
	{
		// Lost surface/device, release swapchain
		swapchain_unavailable = true;
	}
#ifdef RPCS3_IOS
	if (ctx->ios_submit_tsc)
	{
		rpcs3::ios::rsx_sync::frame_latency_ticks.record(utils::get_tsc() - ctx->ios_submit_tsc);
		ctx->ios_submit_tsc = 0;
	}
#endif

	// Resource cleanup.
	{
		if (m_overlay_manager && m_overlay_manager->has_dirty())
		{
			auto ui_renderer = vk::get_overlay_pass<vk::ui_overlay_renderer>();
			m_overlay_manager->lock_shared();

			std::vector<u32> uids_to_dispose;
			uids_to_dispose.reserve(m_overlay_manager->get_dirty().size());

			for (const auto& view : m_overlay_manager->get_dirty())
			{
				ui_renderer->remove_temp_resources(view->uid);
				uids_to_dispose.push_back(view->uid);
			}

			m_overlay_manager->unlock_shared();
			m_overlay_manager->dispose(uids_to_dispose);
		}

		vk::get_resource_manager()->trim();

		vk::reset_global_resources();

		if (ctx->last_frame_sync_time > m_last_heap_sync_time)
		{
			m_last_heap_sync_time = ctx->last_frame_sync_time;

			// Heap cleanup; deallocates memory consumed by the frame if it is still held
			vk::data_heap_manager::restore_snapshot(ctx->heap_snapshot, ctx->heap_snapshot_id);
		}
	}

	ctx->swap_command_buffer = nullptr;

	// Remove from queued list
	while (!m_queued_frames.empty())
	{
		auto frame = m_queued_frames.front();
		m_queued_frames.pop_front();

		if (frame == ctx)
		{
			break;
		}
	}

	vk::advance_completed_frame_counter();
}


void start(VkResult result=VK_SUCCESS) {
    assert(counts.locks==0); counts={}; injected_wait=result;
    injected_status=VK_NOT_READY; upgrade_hook={};
}
void initialize(vk::command_buffer_chunk& cb) {
    cb.eid_tag=77; cb.heap_snapshot.clear(); cb.heap_snapshot.push_back(5); cb.heap_snapshot_id=99;
}
template<class F> bool throws(F&& f) {
    try { f(); return false; } catch (const renderer_error&) { return true; }
}
bool unchanged(const vk::command_buffer_chunk& cb) {
    return cb.is_pending && cb.eid_tag==77 && cb.heap_snapshot_id==99 && cb.heap_snapshot==std::vector<u64>{5};
}
bool no_retirement() {
    return counts.fence_resets==0 && counts.completions==0 && counts.heaps==0 && counts.driver_resets==0;
}
int main() {
    u32 failure_cases=0, failure_mismatches=0, success_cases=0, success_mismatches=0;
    u32 false_completions=0, false_fence_resets=0, false_heap_restores=0, unsafe_driver_resets=0, unsafe_frame_cleanup=0;
    auto failed_case=[&](bool ok) {
        ++failure_cases; failure_mismatches+=!ok;
        assert(counts.locks==0);
    };
    auto passed_case=[&](bool ok) {
        ++success_cases; success_mismatches+=!ok;
        assert(counts.locks==0);
    };
    auto count_unsafe=[&] {
        false_completions+=counts.completions;
        false_fence_resets+=counts.fence_resets;
        false_heap_restores+=counts.heaps;
        unsafe_driver_resets+=counts.driver_resets;
        unsafe_frame_cleanup+=counts.frames;
    };
    const VkResult errors[]={VK_TIMEOUT,VK_ERROR_DEVICE_LOST,VK_ERROR_OUT_OF_HOST_MEMORY,VK_ERROR_OUT_OF_DEVICE_MEMORY};
    for (const auto result:errors) {
        // Direct wait: no retirement on failure and a repeated call must not
        // turn the unfinished work into an immediate success.
        start(result); vk::command_buffer_chunk direct; initialize(direct);
        bool caught=throws([&] { direct.wait(FRAME_PRESENT_TIMEOUT); });
        failed_case(caught && unchanged(direct) && no_retirement() && counts.last_timeout==FRAME_PRESENT_TIMEOUT);
        count_unsafe();
        const u32 waits_before=counts.waits;
        caught=throws([&] { direct.wait(FRAME_PRESENT_TIMEOUT); });
        failed_case(caught && unchanged(direct) && no_retirement() && counts.waits==waits_before+1);

        // The actual command-buffer reuse caller must not increment reset_id
        // or call vkResetCommandBuffer after a failed timed wait.
        for (bool flushed:{false,true}) {
            start(result); vk::command_buffer_chunk cb; initialize(cb);
            cb.owned_fence.flushed=flushed;
            caught=throws([&] { cb.reset(); });
            failed_case(caught && unchanged(cb) && cb.reset_id==0 && no_retirement() && counts.last_timeout==FRAME_PRESENT_TIMEOUT);
            count_unsafe();
        }

        // The actual frame cleanup caller must preserve queued work, frame
        // ownership and both heap snapshots; no resource cleanup may run.
        start(result); vk::command_buffer_chunk cb; initialize(cb);
        vk::frame_context_t ctx; ctx.swap_command_buffer=&cb;
        VKGSRender renderer; renderer.m_queued_frames.push_back(&ctx);
        caught=throws([&] { renderer.frame_context_cleanup(&ctx); });
        failed_case(caught && unchanged(cb) && no_retirement() && ctx.swap_command_buffer==&cb
            && renderer.m_queued_frames.size()==1 && renderer.m_last_heap_sync_time==0
            && counts.frames==0 && counts.trims==0 && counts.globals==0 && counts.latency_records==0);
        count_unsafe();

        // wait_all propagates the exception at any slot. Already completed
        // predecessors are allowed to retire; failing/subsequent work is not.
        for (u32 failed_slot=0;failed_slot<4;++failed_slot) {
            start(result); vk::command_chain chain;
            for (auto& item:chain.m_cb_list) initialize(item);
            for (u32 i=0;i<failed_slot;++i) chain.m_cb_list[i].is_pending=false;
            caught=throws([&] { chain.wait_all(); });
            bool safe=caught && no_retirement() && counts.waits==1 && counts.last_timeout==0;
            for (u32 i=failed_slot;i<4;++i) safe &= unchanged(chain.m_cb_list[i]);
            failed_case(safe); count_unsafe();
        }
    }

    // Success and already-finished paths retain their old behavior.
    for (u64 timeout:{0ull,FRAME_PRESENT_TIMEOUT}) {
        start(); vk::command_buffer_chunk cb; initialize(cb);
        const bool success=cb.wait(timeout)==VK_SUCCESS;
        passed_case(success && !cb.is_pending && cb.eid_tag==0 && cb.heap_snapshot_id==0 && cb.heap_snapshot.empty()
            && counts.waits==1 && counts.last_timeout==timeout && counts.fence_resets==1 && counts.completions==1 && counts.heaps==1);
        const auto before=counts;
        passed_case(cb.wait(timeout)==VK_SUCCESS && counts.waits==before.waits && counts.completions==before.completions && counts.fence_resets==before.fence_resets && counts.heaps==before.heaps);
    }
    start(); vk::command_buffer_chunk no_snapshot; initialize(no_snapshot); no_snapshot.heap_snapshot_id=0;
    passed_case(no_snapshot.wait()==VK_SUCCESS && counts.heaps==0 && counts.completions==1);

    for (u32 path=0;path<3;++path) {
        start(); vk::command_buffer_chunk cb; initialize(cb);
        if (path==1) injected_status=VK_SUCCESS;
        if (path==2) cb.is_pending=false;
        cb.reset();
        passed_case(cb.reset_id==1 && counts.driver_resets==1 && counts.waits==(path==0)
            && counts.completions==(path!=2) && counts.fence_resets==(path!=2) && counts.heaps==(path!=2));
    }
    for (bool pending:{false,true}) {
        start(); vk::command_buffer_chunk cb; initialize(cb); cb.is_pending=pending;
        vk::frame_context_t ctx; ctx.swap_command_buffer=&cb;
        VKGSRender renderer; renderer.m_queued_frames.push_back(&ctx);
        renderer.frame_context_cleanup(&ctx);
        passed_case(ctx.swap_command_buffer==nullptr && renderer.m_queued_frames.empty()
            && counts.waits==pending && counts.heaps==1u+pending && counts.frames==1
            && counts.trims==1 && counts.globals==1 && counts.latency_records==1);
    }
    start(); vk::command_chain chain;
    for (auto& cb:chain.m_cb_list) initialize(cb);
    chain.wait_all();
    passed_case(counts.waits==4 && counts.completions==4 && counts.fence_resets==4 && counts.heaps==4);

    // Another waiter may retire the command before the lock is upgraded.
    // Deterministic interleaving checks the post-upgrade is_pending guard.
    start(); vk::command_buffer_chunk raced; initialize(raced);
    upgrade_hook=[&] { raced.is_pending=false; raced.eid_tag=0; raced.heap_snapshot_id=0; raced.heap_snapshot.clear(); };
    passed_case(raced.wait()==VK_SUCCESS && counts.waits==1 && no_retirement());

    std::cout << "{\"failure_cases\":" << failure_cases << ",\"failure_mismatches\":" << failure_mismatches
        << ",\"success_cases\":" << success_cases << ",\"success_mismatches\":" << success_mismatches
        << ",\"false_completions\":" << false_completions << ",\"false_fence_resets\":" << false_fence_resets
        << ",\"false_heap_restores\":" << false_heap_restores << ",\"unsafe_driver_resets\":" << unsafe_driver_resets
        << ",\"unsafe_frame_cleanup\":" << unsafe_frame_cleanup << "}\n";
}
