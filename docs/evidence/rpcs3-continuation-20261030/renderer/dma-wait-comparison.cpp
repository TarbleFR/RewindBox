
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <source_location>
#include <span>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
using u8=std::uint8_t; using u16=std::uint16_t; using u32=std::uint32_t;
using u64=std::uint64_t; using s32=std::int32_t;
using VkDevice=u32; using VkFence=u32; using VkCommandBuffer=u32;
using VkQueue=u32; using VkBool32=u32;
constexpr auto VK_NULL_HANDLE=0u; constexpr auto VK_TRUE=1u, VK_FALSE=0u;
constexpr u32 VK_STRUCTURE_TYPE_FENCE_CREATE_INFO=1, VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO=2;
constexpr u32 VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO=3, VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO=4;
constexpr u32 VK_COMMAND_BUFFER_LEVEL_PRIMARY=1, VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT=1;
constexpr u32 VK_PIPELINE_STAGE_TRANSFER_BIT=1, VK_PIPELINE_STAGE_VERTEX_SHADER_BIT=2, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT=4;
constexpr u32 CELL_GCM_TEXTURE_A8R8G8B8=1,CELL_GCM_TEXTURE_DEPTH24_D8=2,CELL_GCM_TEXTURE_R5G6B5=3,CELL_GCM_TEXTURE_DEPTH16=4;
#define FRAME_PRESENT_TIMEOUT 10000000ull
#define GENERAL_WAIT_TIMEOUT 2000000ull
#define AUDIT(x) assert(x)
#define ensure(x) assert(x)
#define CHECK_RESULT(expr) { VkResult _res = (expr); if (_res != VK_SUCCESS) vk::die_with_error(_res); }
enum VkResult { VK_SUCCESS=0, VK_NOT_READY=1, VK_TIMEOUT=2, VK_EVENT_SET=3, VK_EVENT_RESET=4, VK_INCOMPLETE=5, VK_ERROR_DEVICE_LOST=6, VK_ERROR_EXTENSION_NOT_PRESENT=7, VK_ERROR_FEATURE_NOT_PRESENT=8, VK_ERROR_FORMAT_NOT_SUPPORTED=9, VK_ERROR_FRAGMENTATION_EXT=10, VK_ERROR_FRAGMENTED_POOL=11, VK_ERROR_INCOMPATIBLE_DISPLAY_KHR=12, VK_ERROR_INCOMPATIBLE_DRIVER=13, VK_ERROR_INITIALIZATION_FAILED=14, VK_ERROR_INVALID_EXTERNAL_HANDLE_KHR=15, VK_ERROR_INVALID_SHADER_NV=16, VK_ERROR_LAYER_NOT_PRESENT=17, VK_ERROR_MEMORY_MAP_FAILED=18, VK_ERROR_NATIVE_WINDOW_IN_USE_KHR=19, VK_ERROR_OUT_OF_DATE_KHR=20, VK_ERROR_OUT_OF_DEVICE_MEMORY=21, VK_ERROR_OUT_OF_HOST_MEMORY=22, VK_ERROR_OUT_OF_POOL_MEMORY_KHR=23, VK_ERROR_SURFACE_LOST_KHR=24, VK_ERROR_TOO_MANY_OBJECTS=25, VK_ERROR_VALIDATION_FAILED_EXT=26, VK_SUBOPTIMAL_KHR=27 };
struct VkFenceCreateInfo { u32 sType=0; };
struct VkCommandBufferAllocateInfo { u32 sType=0,commandBufferCount=0,commandPool=0,level=0; };
struct VkCommandBufferInheritanceInfo { u32 sType=0; };
struct VkCommandBufferBeginInfo { u32 sType=0,flags=0; VkCommandBufferInheritanceInfo* pInheritanceInfo=nullptr; };
struct test_result { u32 fence_failures=0,event_failures=0,success_checks=0,mismatches=0; u32 unsafe_resets=0,unsafe_fence_destructions=0,unsafe_readbacks=0; u32 success_local_fence_creates=0,success_local_fence_destroys=0; };

namespace baseline {

struct renderer_error : std::exception {};
struct statistics {
    u32 creates=0,destroys=0,pending_fence_destroys=0,resets=0,pending_resets=0,begins=0,ends=0,submits=0;
    u32 timed_waits=0,ready_rechecks=0,unbounded_pending_waits=0,event_waits=0;
    u32 fence_resets=0,state_clears=0,readbacks=0,guest_reads=0,swizzles=0;
    u32 async_flushes=0,wait_semaphores=0,query_closes=0,fatal_errors=0,locks=0;
    u32 event_destroys=0,unprotects=0,callbacks=0;
    u64 last_fence_timeout=0,last_event_timeout=0;
} stats;
VkResult fence_result=VK_SUCCESS,event_result=VK_SUCCESS;
std::unordered_map<u32,bool> pending_fences;
std::unordered_map<u32,u32> command_fences;
u32 next_handle=1;
struct atomic_flag { bool value=false; void release(bool x) { value=x; } operator bool() const { return value; } };
struct shared_mutex { void lock() { ++stats.locks; } void unlock() { --stats.locks; } };
struct reader_lock { shared_mutex& lock; explicit reader_lock(shared_mutex& x):lock(x){lock.lock();} ~reader_lock(){lock.unlock();} void upgrade() {} };
namespace fmt {
template<class... T> std::string format(const char*,T&&...) { return {}; }
template<class... T> [[noreturn]] void throw_exception(const char*,T&&...) { ++stats.fatal_errors; throw renderer_error{}; }
}
struct logger { template<class... T> void error(const char*,T&&...) {} template<class... T> void trace(const char*,T&&...) {} } rsx_log;
namespace utils { template<class A,class B> auto align(A x,B n) { return ((x+n-1)/n)*n; } }
namespace rpcs3::ios::rsx_sync { enum { texture,cb_reuse }; struct SiteScope { explicit SiteScope(int,bool=false) {} }; }
struct range { u32 start=64,bytes=256; u32 length() const { return bytes; } };
namespace rsx {
enum class texture_upload_context { framebuffer_storage,shader_read };
template<class T> using simple_array=std::vector<T>;
struct tile { u32 size=512,pitch=16; } tiled;
struct tile_region { rsx::tile* tile=nullptr; u32 base_address=64; explicit operator bool() const{return tile!=nullptr;} };
bool tiled_enabled=false;
struct renderer { tile_region get_tiled_memory_region(range) { return {tiled_enabled?&tiled:nullptr,64}; } } renderer_instance;
renderer* get_current_renderer() { return &renderer_instance; }
template<class T> void convert_linear_swizzle_bounded(std::span<const u8>,std::span<u8>,u32,u32,u32) { ++stats.swizzles; }
}
namespace vk {
void print_debug_markers() {}
std::string retrieve_device_fault_info() { return {}; }
void die_with_error(VkResult,std::string={},std::source_location=std::source_location::current());
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

}
VkResult vkCreateFence(VkDevice,const VkFenceCreateInfo*,void*,VkFence* handle) { *handle=next_handle++; pending_fences[*handle]=false; ++stats.creates; return VK_SUCCESS; }
void vkDestroyFence(VkDevice,VkFence handle,void*) { ++stats.destroys; stats.pending_fence_destroys+=pending_fences.at(handle); pending_fences.erase(handle); }
VkResult vkResetFences(VkDevice,u32,const VkFence* handle) { assert(!pending_fences.at(*handle)); ++stats.fence_resets; return VK_SUCCESS; }
VkResult vkAllocateCommandBuffers(VkDevice,const VkCommandBufferAllocateInfo*,VkCommandBuffer* cb) { *cb=next_handle++; return VK_SUCCESS; }
void vkFreeCommandBuffers(VkDevice,u32,u32,const VkCommandBuffer* cb) { command_fences.erase(*cb); }
VkResult vkResetCommandBuffer(VkCommandBuffer cmd,u32) {
    ++stats.resets;
    if(auto it=command_fences.find(cmd);it!=command_fences.end()) {
        auto f=pending_fences.find(it->second);
        stats.pending_resets+=(f!=pending_fences.end() && f->second);
    }
    return VK_SUCCESS;
}
VkResult vkBeginCommandBuffer(VkCommandBuffer,const VkCommandBufferBeginInfo*) { ++stats.begins; return VK_SUCCESS; }
VkResult vkEndCommandBuffer(VkCommandBuffer) { ++stats.ends; return VK_SUCCESS; }
VkResult vkGetFenceStatus(VkDevice,VkFence handle) { return pending_fences.at(handle)?VK_NOT_READY:VK_SUCCESS; }
namespace vk {
struct fence {
    atomic_flag flushed; VkFence handle=0; VkDevice owner=0;
    explicit fence(VkDevice); ~fence();
    void reset() { vkResetFences(owner,1,&handle); flushed.release(false); }
    void wait_flush() { assert(flushed); }
    void signal_flushed() { flushed.release(true); }
};
	fence::fence(VkDevice dev)
	{
		owner                  = dev;
		VkFenceCreateInfo info = {};
		info.sType             = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
		CHECK_RESULT(vkCreateFence(dev, &info, nullptr, &handle));
	}
	fence::~fence()
	{
		if (handle)
		{
			vkDestroyFence(owner, handle, nullptr);
			handle = VK_NULL_HANDLE;
		}
	}
VkResult wait_for_fence(fence* f,u64 timeout=0) {
    f->wait_flush();
    if (!timeout) {
        if (!pending_fences.at(f->handle)) { ++stats.ready_rechecks; return VK_SUCCESS; }
        ++stats.unbounded_pending_waits;
    } else { ++stats.timed_waits; stats.last_fence_timeout=timeout; }
    if (fence_result==VK_SUCCESS || fence_result==VK_ERROR_DEVICE_LOST) pending_fences[f->handle]=false;
    if (!timeout && fence_result!=VK_SUCCESS) die_with_error(fence_result);
    return fence_result;
}
struct event { ~event() { ++stats.event_destroys; } };
VkResult wait_for_event(event*,u64 timeout) {
    ++stats.event_waits; stats.last_event_timeout=timeout;
    // Mirrors sync.cpp: event timeout is returned; other driver errors enter
    // the existing error handler before returning to imp_flush.
    if (event_result!=VK_SUCCESS && event_result!=VK_TIMEOUT) die_with_error(event_result);
    return event_result;
}
struct semaphore {};
struct command_pool { VkDevice get_owner() const {return 1;} operator u32() const{return 1;} } pool;
struct queue_submit_t {
    VkQueue queue=1; fence* pfence=nullptr; VkCommandBuffer commands=0;
    void wait_on(semaphore&,u32 mask) { assert(mask==7); ++stats.wait_semaphores; }
    void queue_signal(semaphore&) {}
};
void queue_submit(const queue_submit_t& info,VkBool32 flush) {
    assert(flush==VK_TRUE && info.pfence); ++stats.submits;
    pending_fences[info.pfence->handle]=true; command_fences[info.commands]=info.pfence->handle;
    info.pfence->signal_flushed();
}
class command_buffer {
protected:
    bool is_open=false,is_pending=false;
    fence* m_submit_fence=nullptr;
    command_pool* pool=nullptr;
    VkCommandBuffer commands=0;
    void clear_state_cache(){++stats.state_clears;}
public:
    enum access_type_hint {flush_only,all} access_hint=flush_only;
    enum command_buffer_data_flag {cb_has_open_query=0x08,cb_load_occluson_task=0x10};
    u32 flags=0;
    void create(command_pool&); void destroy(); void reset(); void begin(); void end(); void submit(queue_submit_t&,VkBool32=VK_FALSE);
    void clear_flags(){flags=0;} bool is_recording()const{return is_open;}
    bool pending()const{return is_pending;} fence* owned_fence()const{return m_submit_fence;}
};
	void command_buffer::create(command_pool& cmd_pool)
	{
		VkCommandBufferAllocateInfo infos = {};
		infos.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
		infos.commandBufferCount = 1;
		infos.commandPool = +cmd_pool;
		infos.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
		CHECK_RESULT(vkAllocateCommandBuffers(cmd_pool.get_owner(), &infos, &commands));

		m_submit_fence = new fence(cmd_pool.get_owner());
		pool = &cmd_pool;
	}
	void command_buffer::destroy()
	{
		vkFreeCommandBuffers(pool->get_owner(), (*pool), 1, &commands);

		if (m_submit_fence)
		{
			//vkDestroyFence(pool->get_owner(), m_submit_fence, nullptr);
			delete m_submit_fence;
			m_submit_fence = nullptr;
		}
	}
	void command_buffer::reset()
	{
		// Do the driver reset
		CHECK_RESULT(vkResetCommandBuffer(commands, 0));
	}
	void command_buffer::begin()
	{
		if (m_submit_fence && is_pending)
		{
#ifdef RPCS3_IOS
			const rpcs3::ios::rsx_sync::SiteScope ios_sync_site(rpcs3::ios::rsx_sync::cb_reuse);
#endif
			wait_for_fence(m_submit_fence);
			is_pending = false;

			//CHECK_RESULT(vkResetFences(pool->get_owner(), 1, &m_submit_fence));
			m_submit_fence->reset();
			reset();
		}

		if (is_open)
			return;

		VkCommandBufferInheritanceInfo inheritance_info = {};
		inheritance_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO;

		VkCommandBufferBeginInfo begin_infos = {};
		begin_infos.pInheritanceInfo = &inheritance_info;
		begin_infos.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
		begin_infos.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
		CHECK_RESULT(vkBeginCommandBuffer(commands, &begin_infos));
		is_open = true;

		clear_state_cache();
	}
	void command_buffer::end()
	{
		if (!is_open)
		{
			rsx_log.error("commandbuffer->end was called but commandbuffer is not in a recording state");
			return;
		}

		CHECK_RESULT(vkEndCommandBuffer(commands));
		is_open = false;
	}
	void command_buffer::submit(queue_submit_t& submit_info, VkBool32 flush)
	{
		if (is_open)
		{
			rsx_log.error("commandbuffer->submit was called whilst the command buffer is in a recording state");
			return;
		}

		// Check for hanging queries to avoid driver hang
		ensure((flags & cb_has_open_query) == 0); // "close and submit of commandbuffer with a hanging query!"

		if (!submit_info.pfence)
		{
			submit_info.pfence = m_submit_fence;
			is_pending = bool(submit_info.pfence);
		}

		submit_info.commands = this->commands;
		queue_submit(submit_info, flush);
		clear_flags();
	}
namespace data_heap_manager {
using managed_heap_snapshot_t=std::vector<u64>;
bool use_command_buffer_reclamation(){return true;}
managed_heap_snapshot_t get_heap_snapshot(){return {1};}
u64 next_snapshot_id(){return 1;}
void restore_snapshot(managed_heap_snapshot_t&,u64){assert(false && "DMA path must not retire chunk snapshots");}
}
u64 get_event_id(){assert(false && "DMA path must not assign EIDs");return 0;}
void on_event_completed(u64){assert(false && "DMA path must not publish EIDs");}
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

void do_query_cleanup(command_buffer& cmd){++stats.query_closes;cmd.flags&=~command_buffer::cb_has_open_query;}
struct AsyncTaskScheduler {
    u32 mode=0; semaphore sema;
    bool is_recording()const{return mode>=2;} bool is_host_mode()const{return mode==2;}
    semaphore* get_sema(){return &sema;}
    void flush(queue_submit_t&,VkBool32 flush){assert(flush==VK_TRUE);++stats.async_flushes;}
} scheduler;
void flush_dma(u32,u32){++stats.readbacks;}
struct section_base { virtual void imp_flush()=0; virtual ~section_base()=default; };
class cached_texture_section : public section_base {
public:
    bool synchronized=true,swizzled=false;
    rsx::texture_upload_context context=rsx::texture_upload_context::shader_read;
    std::unique_ptr<vk::event> dma_fence=std::make_unique<vk::event>();
    u32 height=4,width=4,rsx_pitch=16,gcm_format=CELL_GCM_TEXTURE_A8R8G8B8;
    std::array<u8,512> guest{};
    range get_section_range()const{return {64,256};}
    range get_confirmed_range()const{return {72,120};}
    bool is_swizzled()const{return swizzled;}
    void* get_ptr(u32){++stats.guest_reads;return guest.data();}
		void imp_flush() override
		{
			AUDIT(synchronized);

			// Synchronize, reset dma_fence after waiting
			vk::wait_for_event(dma_fence.get(), GENERAL_WAIT_TIMEOUT);

			// Calculate smallest range to flush - for framebuffers, the raster region is enough
			const auto range = (context == rsx::texture_upload_context::framebuffer_storage) ? get_section_range() : get_confirmed_range();
			auto flush_length = range.length();

			const auto tiled_region = rsx::get_current_renderer()->get_tiled_memory_region(range);
			if (tiled_region)
			{
				const auto available_tile_size = tiled_region.tile->size - (range.start - tiled_region.base_address);
				const auto max_content_size = tiled_region.tile->pitch * utils::align(height, 64);
				flush_length = std::min(max_content_size, available_tile_size);
			}

			vk::flush_dma(range.start, flush_length);

#if DEBUG_DMA_TILING
			// Are we a tiled region?
			if (const auto tiled_region = rsx::get_current_renderer()->get_tiled_memory_region(range))
			{
				auto real_data = vm::get_super_ptr<u8>(range.start);
				auto out_data = rsx::simple_array<u8>(tiled_region.tile->size);
				rsx::tile_texel_data<u32>(
					out_data.data(),
					real_data,
					tiled_region.base_address,
					range.start - tiled_region.base_address,
					tiled_region.tile->size,
					tiled_region.tile->bank,
					tiled_region.tile->pitch,
					width,
					height
				);
				std::memcpy(real_data, out_data.data(), flush_length);
			}
#endif

			if (is_swizzled())
			{
				// This format is completely worthless to CPU processing algorithms where cache lines on die are linear.
				// If this is happening, usually it means it was not a planned readback (e.g shared pages situation)
				rsx_log.trace("[Performance warning] CPU readback of swizzled data");

				// Morton offsets may exceed the linear region, especially for non-POT
				// dimensions. Bound both the snapshot and every write to the owned range.
				auto* data = static_cast<u8*>(get_ptr(range.start));
				const auto linear_size = std::min<u64>(range.length(), u64{rsx_pitch} * height);
				rsx::simple_array<u8> tmp_data(linear_size);
				std::memcpy(tmp_data.data(), data, tmp_data.size());
				const std::span<const u8> source{tmp_data.data(), tmp_data.size()};
				const std::span<u8> destination{data, tmp_data.size()};

				switch (gcm_format)
				{
				case CELL_GCM_TEXTURE_A8R8G8B8:
				case CELL_GCM_TEXTURE_DEPTH24_D8:
					rsx::convert_linear_swizzle_bounded<u32>(source, destination, width, height, rsx_pitch);
					break;
				case CELL_GCM_TEXTURE_R5G6B5:
				case CELL_GCM_TEXTURE_DEPTH16:
					rsx::convert_linear_swizzle_bounded<u16>(source, destination, width, height, rsx_pitch);
					break;
				default:
					rsx_log.error("Unexpected swizzled texture format 0x%x", gcm_format);
				}
			}
		}
};
struct cache_tag { u64 load()const{return 0;} };
struct cause_t { bool deferred_flush()const{return true;} cause_t undefer()const{return {};} };
struct thrashed_set { cause_t cause; bool flushed=false; u64 cache_tag=0; range fault_range; };
class texture_cache {
public:
    VkDevice device=1; VkDevice* m_device=&device; VkQueue m_submit_queue=1;
    shared_mutex m_cache_mutex; vk::cache_tag m_cache_update_tag;
    cached_texture_section* section=nullptr;
    using commandbuffer_type=command_buffer;
    void cleanup_after_dma_transfers(command_buffer&);
    template<class... A> void flush_set(command_buffer&,thrashed_set&,std::function<void()> cb,A&&...) {if(cb)cb(); section->imp_flush();}
    void unprotect_set(thrashed_set&){++stats.unprotects;}
    template<class... A> void invalidate_range_impl_base(command_buffer&,range,cause_t,std::function<void()>,A&&...){assert(false);}
		template<typename... Args>
		bool flush_all(commandbuffer_type& cmd, thrashed_set& data, std::function<void()> on_data_transfer_completed = {}, Args&&... extras)
		{
			std::lock_guard lock(m_cache_mutex);

			AUDIT(data.cause.deferred_flush());
			AUDIT(!data.flushed);

			if (m_cache_update_tag.load() == data.cache_tag)
			{
				//1. Write memory to cpu side
				flush_set(cmd, data, on_data_transfer_completed, std::forward<Args>(extras)...);

				//2. Release all obsolete sections
				unprotect_set(data);
			}
			else
			{
				// The cache contents have changed between the two readings. This means the data held is useless
				invalidate_range_impl_base(cmd, data.fault_range, data.cause.undefer(), on_data_transfer_completed, std::forward<Args>(extras)...);
			}

			return true;
		}
};
}
struct fxo { template<class T> T* try_get(){return vk::scheduler.mode?&vk::scheduler:nullptr;} } fx;
fxo* g_fxo=&fx;
namespace vk {
	void texture_cache::cleanup_after_dma_transfers(vk::command_buffer& cmd)
	{
		bool occlusion_query_active = !!(cmd.flags & vk::command_buffer::cb_has_open_query);
		if (occlusion_query_active)
		{
			// We really stepped in it
			vk::do_query_cleanup(cmd);
		}

		// End recording
		cmd.end();

		if (cmd.access_hint != vk::command_buffer::access_type_hint::all)
		{
			// Flush any pending async jobs in case of blockers
			// TODO: Context-level manager should handle this logic
			auto async_scheduler = g_fxo->try_get<AsyncTaskScheduler>();
			vk::semaphore* async_sema = nullptr;

			if (async_scheduler && async_scheduler->is_recording())
			{
				if (async_scheduler->is_host_mode())
				{
					async_sema = async_scheduler->get_sema();
				}
				else
				{
					vk::queue_submit_t submit_info{};
					async_scheduler->flush(submit_info, VK_TRUE);
				}
			}

			// Primary access command queue, must restart it after
			vk::fence submit_fence(*m_device);
			vk::queue_submit_t submit_info{ m_submit_queue, &submit_fence };

			if (async_sema)
			{
				vk::queue_submit_t submit_info2{};
				submit_info2.queue_signal(*async_sema);
				async_scheduler->flush(submit_info2, VK_TRUE);

#ifdef RPCS3_IOS
				// Readback transfers and image transitions consume the uploaded data.
				submit_info.wait_on(*async_sema, VK_PIPELINE_STAGE_TRANSFER_BIT |
					VK_PIPELINE_STAGE_VERTEX_SHADER_BIT | VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
#else
				submit_info.wait_on(*async_sema, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
#endif
			}

			cmd.submit(submit_info, VK_TRUE);
#ifdef RPCS3_IOS
			const rpcs3::ios::rsx_sync::SiteScope ios_sync_site(rpcs3::ios::rsx_sync::texture, true);
#endif
			vk::wait_for_fence(&submit_fence, GENERAL_WAIT_TIMEOUT);

			cmd.reset();
			cmd.begin();
		}
		else
		{
			// Auxilliary command queue with auto-restart capability
			vk::queue_submit_t submit_info{ m_submit_queue, nullptr };
			cmd.submit(submit_info, VK_TRUE);
		}

		ensure(cmd.flags == 0);

		if (occlusion_query_active)
		{
			ensure(cmd.is_recording());
			cmd.flags |= vk::command_buffer::cb_load_occluson_task;
		}
	}
}

template<class F> bool caught_error(F&& f){try{f();return false;}catch(const renderer_error&){return true;}}
void reset_statistics(){assert(stats.locks==0);stats={};}
void finish_gpu(){for(auto& [h,p]:pending_fences)p=false;}
test_result run(bool corrected){
    test_result result;
    const VkResult errors[]={VK_TIMEOUT,VK_ERROR_DEVICE_LOST,VK_ERROR_OUT_OF_HOST_MEMORY,VK_ERROR_OUT_OF_DEVICE_MEMORY};
    auto check=[&](bool expected){result.mismatches+=!expected;};
    for(u32 mode=0;mode<4;++mode)for(bool query:{false,true})for(VkResult status:errors){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.eid_tag=77;cmd.heap_snapshot_id=99;
        if(query)cmd.flags|=vk::command_buffer::cb_has_open_query;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=status;
        const auto owned=cmd.owned_fence()->handle;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.fence_failures;
        result.unsafe_resets+=stats.pending_resets;
        result.unsafe_fence_destructions+=stats.pending_fence_destroys;
        if(corrected){
            check(caught && stats.timed_waits==1 && stats.last_fence_timeout==GENERAL_WAIT_TIMEOUT);
            check(stats.resets==0 && stats.begins==0 && stats.creates==0 && stats.destroys==0 && stats.unbounded_pending_waits==0);
            check(cmd.pending() && !cmd.is_recording() && cmd.owned_fence()->handle==owned && cmd.flags==0);
        }else{
            check(!caught && stats.resets==1 && stats.begins==1 && stats.creates==1 && stats.destroys==1);
            check(!cmd.pending() && cmd.is_recording());
        }
        check(cmd.eid_tag==77 && cmd.heap_snapshot_id==99 && stats.query_closes==query);
        check(stats.async_flushes==(mode>=2) && stats.wait_semaphores==(mode==2));
        finish_gpu();cmd.destroy();
    }
    for(u32 mode=0;mode<4;++mode)for(bool query:{false,true}){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.eid_tag=77;cmd.heap_snapshot_id=99;
        if(query)cmd.flags|=vk::command_buffer::cb_has_open_query;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=VK_SUCCESS;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.success_checks;
        check(!caught && stats.timed_waits==1 && stats.last_fence_timeout==GENERAL_WAIT_TIMEOUT && stats.resets==1 && stats.begins==1);
        check(!cmd.pending() && cmd.is_recording() && cmd.eid_tag==77 && cmd.heap_snapshot_id==99);
        check(cmd.flags==(query?u32(vk::command_buffer::cb_load_occluson_task):0u) && stats.query_closes==query);
        check(stats.unbounded_pending_waits==0 && stats.pending_resets==0 && stats.pending_fence_destroys==0);
        check(stats.async_flushes==(mode>=2) && stats.wait_semaphores==(mode==2));
        check(stats.creates==!corrected && stats.destroys==!corrected && stats.ready_rechecks==corrected && stats.fence_resets==corrected);
        result.success_local_fence_creates+=stats.creates;result.success_local_fence_destroys+=stats.destroys;
        finish_gpu();cmd.destroy();
    }
    // Auxiliary buffers keep the original asynchronous submission path.
    for(u32 mode=0;mode<4;++mode){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.access_hint=vk::command_buffer::all;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=VK_TIMEOUT;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.success_checks;
        check(!caught && stats.submits==1 && stats.timed_waits==0 && stats.resets==0 && stats.begins==0 && cmd.pending());
        check(stats.creates==0 && stats.destroys==0 && stats.async_flushes==0);
        finish_gpu();cmd.destroy();
    }
    for(bool tiled:{false,true})for(bool swizzled:{false,true})for(bool framebuffer:{false,true}){
        for(VkResult status:errors){
            vk::cached_texture_section section;section.swizzled=swizzled;
            section.context=framebuffer?rsx::texture_upload_context::framebuffer_storage:rsx::texture_upload_context::shader_read;
            rsx::tiled_enabled=tiled;vk::texture_cache cache;cache.section=&section;
            vk::command_buffer unused;vk::thrashed_set data;reset_statistics();event_result=status;
            const auto* original_event=section.dma_fence.get();
            const bool caught=caught_error([&]{cache.flush_all(unused,data,[]{++stats.callbacks;});});
            ++result.event_failures;
            const bool should_stop=corrected || status!=VK_TIMEOUT;
            check(caught==should_stop && stats.event_waits==1 && stats.last_event_timeout==GENERAL_WAIT_TIMEOUT);
            check(stats.readbacks==!should_stop && stats.guest_reads==(!should_stop&&swizzled) && stats.swizzles==(!should_stop&&swizzled));
            check(stats.event_destroys==0 && section.dma_fence.get()==original_event && stats.unprotects==!should_stop);
            check(stats.locks==0 && stats.callbacks==1);
            result.unsafe_readbacks+=stats.readbacks;
        }
        vk::cached_texture_section section;section.swizzled=swizzled;
        section.context=framebuffer?rsx::texture_upload_context::framebuffer_storage:rsx::texture_upload_context::shader_read;
        rsx::tiled_enabled=tiled;vk::texture_cache cache;cache.section=&section;
        vk::command_buffer unused;vk::thrashed_set data;reset_statistics();event_result=VK_SUCCESS;
        const bool caught=caught_error([&]{cache.flush_all(unused,data,[]{++stats.callbacks;});});
        ++result.success_checks;
        check(!caught && stats.event_waits==1 && stats.last_event_timeout==GENERAL_WAIT_TIMEOUT && stats.readbacks==1);
        check(stats.guest_reads==swizzled && stats.swizzles==swizzled && stats.unprotects==1 && stats.event_destroys==0 && stats.locks==0);
    }
    return result;
}

}

namespace candidate {

struct renderer_error : std::exception {};
struct statistics {
    u32 creates=0,destroys=0,pending_fence_destroys=0,resets=0,pending_resets=0,begins=0,ends=0,submits=0;
    u32 timed_waits=0,ready_rechecks=0,unbounded_pending_waits=0,event_waits=0;
    u32 fence_resets=0,state_clears=0,readbacks=0,guest_reads=0,swizzles=0;
    u32 async_flushes=0,wait_semaphores=0,query_closes=0,fatal_errors=0,locks=0;
    u32 event_destroys=0,unprotects=0,callbacks=0;
    u64 last_fence_timeout=0,last_event_timeout=0;
} stats;
VkResult fence_result=VK_SUCCESS,event_result=VK_SUCCESS;
std::unordered_map<u32,bool> pending_fences;
std::unordered_map<u32,u32> command_fences;
u32 next_handle=1;
struct atomic_flag { bool value=false; void release(bool x) { value=x; } operator bool() const { return value; } };
struct shared_mutex { void lock() { ++stats.locks; } void unlock() { --stats.locks; } };
struct reader_lock { shared_mutex& lock; explicit reader_lock(shared_mutex& x):lock(x){lock.lock();} ~reader_lock(){lock.unlock();} void upgrade() {} };
namespace fmt {
template<class... T> std::string format(const char*,T&&...) { return {}; }
template<class... T> [[noreturn]] void throw_exception(const char*,T&&...) { ++stats.fatal_errors; throw renderer_error{}; }
}
struct logger { template<class... T> void error(const char*,T&&...) {} template<class... T> void trace(const char*,T&&...) {} } rsx_log;
namespace utils { template<class A,class B> auto align(A x,B n) { return ((x+n-1)/n)*n; } }
namespace rpcs3::ios::rsx_sync { enum { texture,cb_reuse }; struct SiteScope { explicit SiteScope(int,bool=false) {} }; }
struct range { u32 start=64,bytes=256; u32 length() const { return bytes; } };
namespace rsx {
enum class texture_upload_context { framebuffer_storage,shader_read };
template<class T> using simple_array=std::vector<T>;
struct tile { u32 size=512,pitch=16; } tiled;
struct tile_region { rsx::tile* tile=nullptr; u32 base_address=64; explicit operator bool() const{return tile!=nullptr;} };
bool tiled_enabled=false;
struct renderer { tile_region get_tiled_memory_region(range) { return {tiled_enabled?&tiled:nullptr,64}; } } renderer_instance;
renderer* get_current_renderer() { return &renderer_instance; }
template<class T> void convert_linear_swizzle_bounded(std::span<const u8>,std::span<u8>,u32,u32,u32) { ++stats.swizzles; }
}
namespace vk {
void print_debug_markers() {}
std::string retrieve_device_fault_info() { return {}; }
void die_with_error(VkResult,std::string={},std::source_location=std::source_location::current());
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

}
VkResult vkCreateFence(VkDevice,const VkFenceCreateInfo*,void*,VkFence* handle) { *handle=next_handle++; pending_fences[*handle]=false; ++stats.creates; return VK_SUCCESS; }
void vkDestroyFence(VkDevice,VkFence handle,void*) { ++stats.destroys; stats.pending_fence_destroys+=pending_fences.at(handle); pending_fences.erase(handle); }
VkResult vkResetFences(VkDevice,u32,const VkFence* handle) { assert(!pending_fences.at(*handle)); ++stats.fence_resets; return VK_SUCCESS; }
VkResult vkAllocateCommandBuffers(VkDevice,const VkCommandBufferAllocateInfo*,VkCommandBuffer* cb) { *cb=next_handle++; return VK_SUCCESS; }
void vkFreeCommandBuffers(VkDevice,u32,u32,const VkCommandBuffer* cb) { command_fences.erase(*cb); }
VkResult vkResetCommandBuffer(VkCommandBuffer cmd,u32) {
    ++stats.resets;
    if(auto it=command_fences.find(cmd);it!=command_fences.end()) {
        auto f=pending_fences.find(it->second);
        stats.pending_resets+=(f!=pending_fences.end() && f->second);
    }
    return VK_SUCCESS;
}
VkResult vkBeginCommandBuffer(VkCommandBuffer,const VkCommandBufferBeginInfo*) { ++stats.begins; return VK_SUCCESS; }
VkResult vkEndCommandBuffer(VkCommandBuffer) { ++stats.ends; return VK_SUCCESS; }
VkResult vkGetFenceStatus(VkDevice,VkFence handle) { return pending_fences.at(handle)?VK_NOT_READY:VK_SUCCESS; }
namespace vk {
struct fence {
    atomic_flag flushed; VkFence handle=0; VkDevice owner=0;
    explicit fence(VkDevice); ~fence();
    void reset() { vkResetFences(owner,1,&handle); flushed.release(false); }
    void wait_flush() { assert(flushed); }
    void signal_flushed() { flushed.release(true); }
};
	fence::fence(VkDevice dev)
	{
		owner                  = dev;
		VkFenceCreateInfo info = {};
		info.sType             = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
		CHECK_RESULT(vkCreateFence(dev, &info, nullptr, &handle));
	}
	fence::~fence()
	{
		if (handle)
		{
			vkDestroyFence(owner, handle, nullptr);
			handle = VK_NULL_HANDLE;
		}
	}
VkResult wait_for_fence(fence* f,u64 timeout=0) {
    f->wait_flush();
    if (!timeout) {
        if (!pending_fences.at(f->handle)) { ++stats.ready_rechecks; return VK_SUCCESS; }
        ++stats.unbounded_pending_waits;
    } else { ++stats.timed_waits; stats.last_fence_timeout=timeout; }
    if (fence_result==VK_SUCCESS || fence_result==VK_ERROR_DEVICE_LOST) pending_fences[f->handle]=false;
    if (!timeout && fence_result!=VK_SUCCESS) die_with_error(fence_result);
    return fence_result;
}
struct event { ~event() { ++stats.event_destroys; } };
VkResult wait_for_event(event*,u64 timeout) {
    ++stats.event_waits; stats.last_event_timeout=timeout;
    // Mirrors sync.cpp: event timeout is returned; other driver errors enter
    // the existing error handler before returning to imp_flush.
    if (event_result!=VK_SUCCESS && event_result!=VK_TIMEOUT) die_with_error(event_result);
    return event_result;
}
struct semaphore {};
struct command_pool { VkDevice get_owner() const {return 1;} operator u32() const{return 1;} } pool;
struct queue_submit_t {
    VkQueue queue=1; fence* pfence=nullptr; VkCommandBuffer commands=0;
    void wait_on(semaphore&,u32 mask) { assert(mask==7); ++stats.wait_semaphores; }
    void queue_signal(semaphore&) {}
};
void queue_submit(const queue_submit_t& info,VkBool32 flush) {
    assert(flush==VK_TRUE && info.pfence); ++stats.submits;
    pending_fences[info.pfence->handle]=true; command_fences[info.commands]=info.pfence->handle;
    info.pfence->signal_flushed();
}
class command_buffer {
protected:
    bool is_open=false,is_pending=false;
    fence* m_submit_fence=nullptr;
    command_pool* pool=nullptr;
    VkCommandBuffer commands=0;
    void clear_state_cache(){++stats.state_clears;}
public:
    enum access_type_hint {flush_only,all} access_hint=flush_only;
    enum command_buffer_data_flag {cb_has_open_query=0x08,cb_load_occluson_task=0x10};
    u32 flags=0;
    void create(command_pool&); void destroy(); void reset(); void begin(); void end(); void submit(queue_submit_t&,VkBool32=VK_FALSE);
    void clear_flags(){flags=0;} bool is_recording()const{return is_open;}
    bool pending()const{return is_pending;} fence* owned_fence()const{return m_submit_fence;}
};
	void command_buffer::create(command_pool& cmd_pool)
	{
		VkCommandBufferAllocateInfo infos = {};
		infos.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
		infos.commandBufferCount = 1;
		infos.commandPool = +cmd_pool;
		infos.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
		CHECK_RESULT(vkAllocateCommandBuffers(cmd_pool.get_owner(), &infos, &commands));

		m_submit_fence = new fence(cmd_pool.get_owner());
		pool = &cmd_pool;
	}
	void command_buffer::destroy()
	{
		vkFreeCommandBuffers(pool->get_owner(), (*pool), 1, &commands);

		if (m_submit_fence)
		{
			//vkDestroyFence(pool->get_owner(), m_submit_fence, nullptr);
			delete m_submit_fence;
			m_submit_fence = nullptr;
		}
	}
	void command_buffer::reset()
	{
		// Do the driver reset
		CHECK_RESULT(vkResetCommandBuffer(commands, 0));
	}
	void command_buffer::begin()
	{
		if (m_submit_fence && is_pending)
		{
#ifdef RPCS3_IOS
			const rpcs3::ios::rsx_sync::SiteScope ios_sync_site(rpcs3::ios::rsx_sync::cb_reuse);
#endif
			wait_for_fence(m_submit_fence);
			is_pending = false;

			//CHECK_RESULT(vkResetFences(pool->get_owner(), 1, &m_submit_fence));
			m_submit_fence->reset();
			reset();
		}

		if (is_open)
			return;

		VkCommandBufferInheritanceInfo inheritance_info = {};
		inheritance_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO;

		VkCommandBufferBeginInfo begin_infos = {};
		begin_infos.pInheritanceInfo = &inheritance_info;
		begin_infos.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
		begin_infos.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
		CHECK_RESULT(vkBeginCommandBuffer(commands, &begin_infos));
		is_open = true;

		clear_state_cache();
	}
	void command_buffer::end()
	{
		if (!is_open)
		{
			rsx_log.error("commandbuffer->end was called but commandbuffer is not in a recording state");
			return;
		}

		CHECK_RESULT(vkEndCommandBuffer(commands));
		is_open = false;
	}
	void command_buffer::submit(queue_submit_t& submit_info, VkBool32 flush)
	{
		if (is_open)
		{
			rsx_log.error("commandbuffer->submit was called whilst the command buffer is in a recording state");
			return;
		}

		// Check for hanging queries to avoid driver hang
		ensure((flags & cb_has_open_query) == 0); // "close and submit of commandbuffer with a hanging query!"

		if (!submit_info.pfence)
		{
			submit_info.pfence = m_submit_fence;
			is_pending = bool(submit_info.pfence);
		}

		submit_info.commands = this->commands;
		queue_submit(submit_info, flush);
		clear_flags();
	}
namespace data_heap_manager {
using managed_heap_snapshot_t=std::vector<u64>;
bool use_command_buffer_reclamation(){return true;}
managed_heap_snapshot_t get_heap_snapshot(){return {1};}
u64 next_snapshot_id(){return 1;}
void restore_snapshot(managed_heap_snapshot_t&,u64){assert(false && "DMA path must not retire chunk snapshots");}
}
u64 get_event_id(){assert(false && "DMA path must not assign EIDs");return 0;}
void on_event_completed(u64){assert(false && "DMA path must not publish EIDs");}
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

void do_query_cleanup(command_buffer& cmd){++stats.query_closes;cmd.flags&=~command_buffer::cb_has_open_query;}
struct AsyncTaskScheduler {
    u32 mode=0; semaphore sema;
    bool is_recording()const{return mode>=2;} bool is_host_mode()const{return mode==2;}
    semaphore* get_sema(){return &sema;}
    void flush(queue_submit_t&,VkBool32 flush){assert(flush==VK_TRUE);++stats.async_flushes;}
} scheduler;
void flush_dma(u32,u32){++stats.readbacks;}
struct section_base { virtual void imp_flush()=0; virtual ~section_base()=default; };
class cached_texture_section : public section_base {
public:
    bool synchronized=true,swizzled=false;
    rsx::texture_upload_context context=rsx::texture_upload_context::shader_read;
    std::unique_ptr<vk::event> dma_fence=std::make_unique<vk::event>();
    u32 height=4,width=4,rsx_pitch=16,gcm_format=CELL_GCM_TEXTURE_A8R8G8B8;
    std::array<u8,512> guest{};
    range get_section_range()const{return {64,256};}
    range get_confirmed_range()const{return {72,120};}
    bool is_swizzled()const{return swizzled;}
    void* get_ptr(u32){++stats.guest_reads;return guest.data();}
		void imp_flush() override
		{
			AUDIT(synchronized);

			// Synchronize, reset dma_fence after waiting
			CHECK_RESULT(vk::wait_for_event(dma_fence.get(), GENERAL_WAIT_TIMEOUT));

			// Calculate smallest range to flush - for framebuffers, the raster region is enough
			const auto range = (context == rsx::texture_upload_context::framebuffer_storage) ? get_section_range() : get_confirmed_range();
			auto flush_length = range.length();

			const auto tiled_region = rsx::get_current_renderer()->get_tiled_memory_region(range);
			if (tiled_region)
			{
				const auto available_tile_size = tiled_region.tile->size - (range.start - tiled_region.base_address);
				const auto max_content_size = tiled_region.tile->pitch * utils::align(height, 64);
				flush_length = std::min(max_content_size, available_tile_size);
			}

			vk::flush_dma(range.start, flush_length);

#if DEBUG_DMA_TILING
			// Are we a tiled region?
			if (const auto tiled_region = rsx::get_current_renderer()->get_tiled_memory_region(range))
			{
				auto real_data = vm::get_super_ptr<u8>(range.start);
				auto out_data = rsx::simple_array<u8>(tiled_region.tile->size);
				rsx::tile_texel_data<u32>(
					out_data.data(),
					real_data,
					tiled_region.base_address,
					range.start - tiled_region.base_address,
					tiled_region.tile->size,
					tiled_region.tile->bank,
					tiled_region.tile->pitch,
					width,
					height
				);
				std::memcpy(real_data, out_data.data(), flush_length);
			}
#endif

			if (is_swizzled())
			{
				// This format is completely worthless to CPU processing algorithms where cache lines on die are linear.
				// If this is happening, usually it means it was not a planned readback (e.g shared pages situation)
				rsx_log.trace("[Performance warning] CPU readback of swizzled data");

				// Morton offsets may exceed the linear region, especially for non-POT
				// dimensions. Bound both the snapshot and every write to the owned range.
				auto* data = static_cast<u8*>(get_ptr(range.start));
				const auto linear_size = std::min<u64>(range.length(), u64{rsx_pitch} * height);
				rsx::simple_array<u8> tmp_data(linear_size);
				std::memcpy(tmp_data.data(), data, tmp_data.size());
				const std::span<const u8> source{tmp_data.data(), tmp_data.size()};
				const std::span<u8> destination{data, tmp_data.size()};

				switch (gcm_format)
				{
				case CELL_GCM_TEXTURE_A8R8G8B8:
				case CELL_GCM_TEXTURE_DEPTH24_D8:
					rsx::convert_linear_swizzle_bounded<u32>(source, destination, width, height, rsx_pitch);
					break;
				case CELL_GCM_TEXTURE_R5G6B5:
				case CELL_GCM_TEXTURE_DEPTH16:
					rsx::convert_linear_swizzle_bounded<u16>(source, destination, width, height, rsx_pitch);
					break;
				default:
					rsx_log.error("Unexpected swizzled texture format 0x%x", gcm_format);
				}
			}
		}
};
struct cache_tag { u64 load()const{return 0;} };
struct cause_t { bool deferred_flush()const{return true;} cause_t undefer()const{return {};} };
struct thrashed_set { cause_t cause; bool flushed=false; u64 cache_tag=0; range fault_range; };
class texture_cache {
public:
    VkDevice device=1; VkDevice* m_device=&device; VkQueue m_submit_queue=1;
    shared_mutex m_cache_mutex; vk::cache_tag m_cache_update_tag;
    cached_texture_section* section=nullptr;
    using commandbuffer_type=command_buffer;
    void cleanup_after_dma_transfers(command_buffer&);
    template<class... A> void flush_set(command_buffer&,thrashed_set&,std::function<void()> cb,A&&...) {if(cb)cb(); section->imp_flush();}
    void unprotect_set(thrashed_set&){++stats.unprotects;}
    template<class... A> void invalidate_range_impl_base(command_buffer&,range,cause_t,std::function<void()>,A&&...){assert(false);}
		template<typename... Args>
		bool flush_all(commandbuffer_type& cmd, thrashed_set& data, std::function<void()> on_data_transfer_completed = {}, Args&&... extras)
		{
			std::lock_guard lock(m_cache_mutex);

			AUDIT(data.cause.deferred_flush());
			AUDIT(!data.flushed);

			if (m_cache_update_tag.load() == data.cache_tag)
			{
				//1. Write memory to cpu side
				flush_set(cmd, data, on_data_transfer_completed, std::forward<Args>(extras)...);

				//2. Release all obsolete sections
				unprotect_set(data);
			}
			else
			{
				// The cache contents have changed between the two readings. This means the data held is useless
				invalidate_range_impl_base(cmd, data.fault_range, data.cause.undefer(), on_data_transfer_completed, std::forward<Args>(extras)...);
			}

			return true;
		}
};
}
struct fxo { template<class T> T* try_get(){return vk::scheduler.mode?&vk::scheduler:nullptr;} } fx;
fxo* g_fxo=&fx;
namespace vk {
	void texture_cache::cleanup_after_dma_transfers(vk::command_buffer& cmd)
	{
		bool occlusion_query_active = !!(cmd.flags & vk::command_buffer::cb_has_open_query);
		if (occlusion_query_active)
		{
			// We really stepped in it
			vk::do_query_cleanup(cmd);
		}

		// End recording
		cmd.end();

		if (cmd.access_hint != vk::command_buffer::access_type_hint::all)
		{
			// Flush any pending async jobs in case of blockers
			// TODO: Context-level manager should handle this logic
			auto async_scheduler = g_fxo->try_get<AsyncTaskScheduler>();
			vk::semaphore* async_sema = nullptr;

			if (async_scheduler && async_scheduler->is_recording())
			{
				if (async_scheduler->is_host_mode())
				{
					async_sema = async_scheduler->get_sema();
				}
				else
				{
					vk::queue_submit_t submit_info{};
					async_scheduler->flush(submit_info, VK_TRUE);
				}
			}

			// Use the command buffer-owned fence so a failed wait cannot destroy
			// a fence still referenced by the queue. submit() also marks it pending.
			vk::queue_submit_t submit_info{ m_submit_queue, nullptr };

			if (async_sema)
			{
				vk::queue_submit_t submit_info2{};
				submit_info2.queue_signal(*async_sema);
				async_scheduler->flush(submit_info2, VK_TRUE);

#ifdef RPCS3_IOS
				// Readback transfers and image transitions consume the uploaded data.
				submit_info.wait_on(*async_sema, VK_PIPELINE_STAGE_TRANSFER_BIT |
					VK_PIPELINE_STAGE_VERTEX_SHADER_BIT | VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
#else
				submit_info.wait_on(*async_sema, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
#endif
			}

			cmd.submit(submit_info, VK_TRUE);
#ifdef RPCS3_IOS
			const rpcs3::ios::rsx_sync::SiteScope ios_sync_site(rpcs3::ios::rsx_sync::texture, true);
#endif
			// A timeout leaves this command buffer pending; it must not be reset.
			CHECK_RESULT(vk::wait_for_fence(submit_info.pfence, GENERAL_WAIT_TIMEOUT));

			// begin() recycles the now-completed owned fence and resets the buffer.
			cmd.begin();
		}
		else
		{
			// Auxilliary command queue with auto-restart capability
			vk::queue_submit_t submit_info{ m_submit_queue, nullptr };
			cmd.submit(submit_info, VK_TRUE);
		}

		ensure(cmd.flags == 0);

		if (occlusion_query_active)
		{
			ensure(cmd.is_recording());
			cmd.flags |= vk::command_buffer::cb_load_occluson_task;
		}
	}
}

template<class F> bool caught_error(F&& f){try{f();return false;}catch(const renderer_error&){return true;}}
void reset_statistics(){assert(stats.locks==0);stats={};}
void finish_gpu(){for(auto& [h,p]:pending_fences)p=false;}
test_result run(bool corrected){
    test_result result;
    const VkResult errors[]={VK_TIMEOUT,VK_ERROR_DEVICE_LOST,VK_ERROR_OUT_OF_HOST_MEMORY,VK_ERROR_OUT_OF_DEVICE_MEMORY};
    auto check=[&](bool expected){result.mismatches+=!expected;};
    for(u32 mode=0;mode<4;++mode)for(bool query:{false,true})for(VkResult status:errors){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.eid_tag=77;cmd.heap_snapshot_id=99;
        if(query)cmd.flags|=vk::command_buffer::cb_has_open_query;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=status;
        const auto owned=cmd.owned_fence()->handle;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.fence_failures;
        result.unsafe_resets+=stats.pending_resets;
        result.unsafe_fence_destructions+=stats.pending_fence_destroys;
        if(corrected){
            check(caught && stats.timed_waits==1 && stats.last_fence_timeout==GENERAL_WAIT_TIMEOUT);
            check(stats.resets==0 && stats.begins==0 && stats.creates==0 && stats.destroys==0 && stats.unbounded_pending_waits==0);
            check(cmd.pending() && !cmd.is_recording() && cmd.owned_fence()->handle==owned && cmd.flags==0);
        }else{
            check(!caught && stats.resets==1 && stats.begins==1 && stats.creates==1 && stats.destroys==1);
            check(!cmd.pending() && cmd.is_recording());
        }
        check(cmd.eid_tag==77 && cmd.heap_snapshot_id==99 && stats.query_closes==query);
        check(stats.async_flushes==(mode>=2) && stats.wait_semaphores==(mode==2));
        finish_gpu();cmd.destroy();
    }
    for(u32 mode=0;mode<4;++mode)for(bool query:{false,true}){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.eid_tag=77;cmd.heap_snapshot_id=99;
        if(query)cmd.flags|=vk::command_buffer::cb_has_open_query;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=VK_SUCCESS;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.success_checks;
        check(!caught && stats.timed_waits==1 && stats.last_fence_timeout==GENERAL_WAIT_TIMEOUT && stats.resets==1 && stats.begins==1);
        check(!cmd.pending() && cmd.is_recording() && cmd.eid_tag==77 && cmd.heap_snapshot_id==99);
        check(cmd.flags==(query?u32(vk::command_buffer::cb_load_occluson_task):0u) && stats.query_closes==query);
        check(stats.unbounded_pending_waits==0 && stats.pending_resets==0 && stats.pending_fence_destroys==0);
        check(stats.async_flushes==(mode>=2) && stats.wait_semaphores==(mode==2));
        check(stats.creates==!corrected && stats.destroys==!corrected && stats.ready_rechecks==corrected && stats.fence_resets==corrected);
        result.success_local_fence_creates+=stats.creates;result.success_local_fence_destroys+=stats.destroys;
        finish_gpu();cmd.destroy();
    }
    // Auxiliary buffers keep the original asynchronous submission path.
    for(u32 mode=0;mode<4;++mode){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.access_hint=vk::command_buffer::all;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=VK_TIMEOUT;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.success_checks;
        check(!caught && stats.submits==1 && stats.timed_waits==0 && stats.resets==0 && stats.begins==0 && cmd.pending());
        check(stats.creates==0 && stats.destroys==0 && stats.async_flushes==0);
        finish_gpu();cmd.destroy();
    }
    for(bool tiled:{false,true})for(bool swizzled:{false,true})for(bool framebuffer:{false,true}){
        for(VkResult status:errors){
            vk::cached_texture_section section;section.swizzled=swizzled;
            section.context=framebuffer?rsx::texture_upload_context::framebuffer_storage:rsx::texture_upload_context::shader_read;
            rsx::tiled_enabled=tiled;vk::texture_cache cache;cache.section=&section;
            vk::command_buffer unused;vk::thrashed_set data;reset_statistics();event_result=status;
            const auto* original_event=section.dma_fence.get();
            const bool caught=caught_error([&]{cache.flush_all(unused,data,[]{++stats.callbacks;});});
            ++result.event_failures;
            const bool should_stop=corrected || status!=VK_TIMEOUT;
            check(caught==should_stop && stats.event_waits==1 && stats.last_event_timeout==GENERAL_WAIT_TIMEOUT);
            check(stats.readbacks==!should_stop && stats.guest_reads==(!should_stop&&swizzled) && stats.swizzles==(!should_stop&&swizzled));
            check(stats.event_destroys==0 && section.dma_fence.get()==original_event && stats.unprotects==!should_stop);
            check(stats.locks==0 && stats.callbacks==1);
            result.unsafe_readbacks+=stats.readbacks;
        }
        vk::cached_texture_section section;section.swizzled=swizzled;
        section.context=framebuffer?rsx::texture_upload_context::framebuffer_storage:rsx::texture_upload_context::shader_read;
        rsx::tiled_enabled=tiled;vk::texture_cache cache;cache.section=&section;
        vk::command_buffer unused;vk::thrashed_set data;reset_statistics();event_result=VK_SUCCESS;
        const bool caught=caught_error([&]{cache.flush_all(unused,data,[]{++stats.callbacks;});});
        ++result.success_checks;
        check(!caught && stats.event_waits==1 && stats.last_event_timeout==GENERAL_WAIT_TIMEOUT && stats.readbacks==1);
        check(stats.guest_reads==swizzled && stats.swizzles==swizzled && stats.unprotects==1 && stats.event_destroys==0 && stats.locks==0);
    }
    return result;
}

}

void print(const test_result& r){
    std::cout<<"{\"fence_failure_cases\":"<<r.fence_failures<<",\"event_failure_cases\":"<<r.event_failures
    <<",\"success_cases\":"<<r.success_checks<<",\"mismatches\":"<<r.mismatches
    <<",\"unsafe_resets\":"<<r.unsafe_resets<<",\"unsafe_fence_destructions\":"<<r.unsafe_fence_destructions
    <<",\"unsafe_readbacks\":"<<r.unsafe_readbacks<<",\"success_local_fence_creates\":"<<r.success_local_fence_creates
    <<",\"success_local_fence_destroys\":"<<r.success_local_fence_destroys<<"}";
}
int main(){std::cout<<"{\"baseline\":";print(baseline::run(false));std::cout<<",\"candidate\":";print(candidate::run(true));std::cout<<"}\n";}
