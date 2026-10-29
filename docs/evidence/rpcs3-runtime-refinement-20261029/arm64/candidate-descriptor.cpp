// Recording adapter for extracted command-buffer code; no GPU or Vulkan device.
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <span>
#include <string>
#include <vector>

#ifdef NDEBUG
#error Assertions must remain active
#endif

using u32 = std::uint32_t;
using u64 = std::uint64_t;
using VkDescriptorSet = u64;
using VkPipelineLayout = u64;
using VkPipeline = u64;
using VkBool32 = u32;
using VkStencilFaceFlags = u32;
enum VkPipelineBindPoint : u32
{
    VK_PIPELINE_BIND_POINT_GRAPHICS = 0,
    VK_PIPELINE_BIND_POINT_COMPUTE = 1,
    VK_PIPELINE_BIND_POINT_RAY_TRACING_KHR = 1000165000
};
#define VK_NULL_HANDLE 0
constexpr u32 VK_FALSE = 0;
constexpr u32 VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO = 41;
constexpr u32 VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO = 42;
constexpr u32 VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT = 1;
struct VkViewport { float x, y, width, height, minDepth, maxDepth; };
struct VkRect2D { struct { int x, y; } offset; struct { u32 width, height; } extent; };
struct VkCommandBufferInheritanceInfo { u32 sType; };
struct VkCommandBufferBeginInfo
{
    u32 sType, flags;
    const VkCommandBufferInheritanceInfo* pInheritanceInfo;
};
#define ensure(condition) assert(condition)
#define CHECK_RESULT(expression) assert((expression) == 0)
template <typename T> u32 size32(const T& value) { return static_cast<u32>(value.size()); }

struct bound_slot
{
    bool valid = false;
    VkDescriptorSet set = 0;
    VkPipelineLayout layout = 0;
    std::vector<u32> offsets;
};
struct binding_event
{
    VkPipelineBindPoint point;
    VkPipelineLayout layout;
    u32 first;
    std::vector<VkDescriptorSet> sets;
    std::vector<u32> offsets;
};
struct recording_driver
{
    std::array<std::array<bound_slot, 2>, 3> slots{};
    std::vector<binding_event> events;
    u64 calls = 0;
    u64 pipeline_calls = 0;
    u64 checksum = 0;
    u32 begins = 0, ends = 0, resets = 0, fence_waits = 0, fence_resets = 0;
    bool recording = false;
    bool capture = true;
};
using VkCommandBuffer = recording_driver*;

static void vkCmdBindPipeline(VkCommandBuffer cmd, VkPipelineBindPoint, VkPipeline)
{
    assert(cmd->recording);
    ++cmd->pipeline_calls;
}

static unsigned point_index(VkPipelineBindPoint point)
{
    if (point == VK_PIPELINE_BIND_POINT_GRAPHICS) return 0;
    if (point == VK_PIPELINE_BIND_POINT_COMPUTE) return 1;
    assert(point == VK_PIPELINE_BIND_POINT_RAY_TRACING_KHR);
    return 2;
}

// Fixture descriptor sets 900..999 have two dynamic descriptors. Other sets
// have none. Layouts with different IDs share descriptor-set definitions but
// have incompatible push-constant ranges: rebinding is required on a switch.
static u32 dynamic_count(VkDescriptorSet set)
{
    return set >= 900 && set < 1000 ? 2u : 0u;
}

// No Metal/Vulkan implementation is involved. For timing the recorder only
// increments counters; recording and the model are disabled outside controls.
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
static void vkCmdBindDescriptorSets(VkCommandBuffer cmd, VkPipelineBindPoint point,
    VkPipelineLayout layout, u32 first, u32 count, const VkDescriptorSet* sets,
    u32 offset_count, const u32* offsets)
{
    assert(cmd->recording && first == 0 && count > 0 && count <= 2);
    ++cmd->calls;
    cmd->checksum += sets[0] + layout + point + count + offset_count;
    if (!cmd->capture) return;

    u32 required_offsets = 0;
    for (u32 i = 0; i < count; ++i) required_offsets += dynamic_count(sets[i]);
    assert(required_offsets == offset_count);
    binding_event event{point, layout, first, {}, {}};
    event.sets.assign(sets, sets + count);
    if (offset_count) event.offsets.assign(offsets, offsets + offset_count);
    cmd->events.push_back(event);

    auto& bound = cmd->slots[point_index(point)];
    for (auto& slot : bound)
        if (slot.valid && slot.layout != layout) slot.valid = false;
    u32 cursor = 0;
    for (u32 i = 0; i < count; ++i)
    {
        auto& slot = bound[i];
        slot = {true, sets[i], layout, {}};
        const u32 number = dynamic_count(sets[i]);
        if (number) slot.offsets.assign(offsets + cursor, offsets + cursor + number);
        cursor += number;
    }
}

static int vkBeginCommandBuffer(VkCommandBuffer cmd, const VkCommandBufferBeginInfo* info)
{
    assert(!cmd->recording && info->sType == VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO);
    assert(info->flags == VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT);
    assert(info->pInheritanceInfo->sType == VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO);
    cmd->slots = {};
    cmd->recording = true;
    ++cmd->begins;
    return 0;
}
static int vkEndCommandBuffer(VkCommandBuffer cmd)
{
    assert(cmd->recording);
    cmd->recording = false;
    ++cmd->ends;
    return 0;
}
static int vkResetCommandBuffer(VkCommandBuffer cmd, u32 flags)
{
    assert(!cmd->recording && flags == 0);
    cmd->slots = {};
    ++cmd->resets;
    return 0;
}
struct { void error(const char*) const { assert(false); } } rsx_log;
namespace rpcs3::ios::rsx_sync
{
    [[maybe_unused]] constexpr int cb_reuse = 1;
    struct SiteScope { explicit SiteScope(int) {} };
}

namespace vk
{
struct fence
{
    recording_driver* driver = nullptr;
    void reset() { ++driver->fence_resets; }
};
static void wait_for_fence(fence* value) { ++value->driver->fence_waits; }
struct command_pool { u32 get_queue_family() const { return 0; } };
struct queue_submit_t;

	struct dynamic_state_cache
	{
		enum slot : unsigned
		{
			line_width, blend_constants, depth_bias, depth_bounds,
			stencil_write_front, stencil_write_back,
			stencil_compare_front, stencil_compare_back,
			stencil_reference_front, stencil_reference_back,
#ifdef RPCS3_IOS
			viewport_bounds, viewport_depth, scissor_rect,
#endif
			count
		};

		std::array<std::array<std::uint32_t, 4>, count> values{};
		std::uint32_t valid = 0;

		void clear() { valid = 0; }
#ifdef RPCS3_IOS
		// A graphics bind invalidates only the states supplied statically by
		// that pipeline. Dynamic values survive other graphics pipeline binds.
		void retain(std::uint32_t dynamic_mask) { valid &= dynamic_mask; }
#endif
		bool update(slot index, std::array<std::uint32_t, 4> value)
		{
			const auto bit = 1u << index;
			if ((valid & bit) && values[index] == value)
			{
				return false;
			}
			values[index] = value;
			valid |= bit;
			return true;
		}
	};
	class command_buffer
	{
	protected:
		bool is_open = false;
		bool is_pending = false;
		fence* m_submit_fence = nullptr;

		command_pool* pool = nullptr;
		VkCommandBuffer commands = nullptr;

		// State cache
#ifdef RPCS3_IOS
		struct descriptor_binding_state
		{
			VkPipelineLayout layout = VK_NULL_HANDLE;
			std::array<VkDescriptorSet, 2> sets{};
			u32 count = 0;
		};
		mutable std::array<descriptor_binding_state, 2> m_descriptor_bindings{};
		bool update_descriptor_binding_cache(const std::span<VkDescriptorSet>& sets,
			VkPipelineBindPoint bind_point, VkPipelineLayout layout, bool has_dynamic_offsets) const;
#else
		mutable std::array<VkDescriptorSet, 2> m_bound_descriptor_sets {{ VK_NULL_HANDLE }};
#endif
		mutable std::array<VkPipeline, 2> m_bound_pipelines{{ VK_NULL_HANDLE }};
		mutable dynamic_state_cache m_dynamic_state;

		void clear_state_cache();

	public:
		enum access_type_hint
		{
			flush_only, // Only to be submitted/opened/closed via command flush
			all         // Auxiliary, can be submitted/opened/closed at any time
		}
		access_hint = flush_only;

		enum command_buffer_data_flag : u32
		{
			cb_has_occlusion_task = 0x01,
			cb_has_blit_transfer  = 0x02,
			cb_has_dma_transfer   = 0x04,
			cb_has_open_query     = 0x08,
			cb_load_occluson_task = 0x10,
			cb_has_conditional_render = 0x20,
			cb_reload_dynamic_state   = 0x40
		};
		u32 flags = 0;

	public:
		command_buffer() = default;
		~command_buffer() = default;

		void create(command_pool& cmd_pool);
		void destroy();
		void reset();

		void begin();
		void end();
		void submit(queue_submit_t& submit_info, VkBool32 flush = VK_FALSE);

		// Abstractions with caching
#ifdef RPCS3_IOS
		void bind_pipeline(VkPipeline pipeline, VkPipelineBindPoint bind_point, u32 dynamic_state_mask = 0) const;
		void set_viewport(const VkViewport& viewport) const;
		void set_scissor(const VkRect2D& scissor) const;
#else
		void bind_pipeline(VkPipeline pipeline, VkPipelineBindPoint bind_point) const;
#endif
		void set_line_width(float width) const;
		void set_blend_constants(const float* colors) const;
		void set_depth_bias(float constant, float clamp, float slope) const;
		void set_depth_bounds(float minimum, float maximum) const;
		void set_stencil_write_mask(VkStencilFaceFlags faces, u32 value) const;
		void set_stencil_compare_mask(VkStencilFaceFlags faces, u32 value) const;
		void set_stencil_reference(VkStencilFaceFlags faces, u32 value) const;
		void bind_descriptor_sets(const std::span<VkDescriptorSet>& sets, VkPipelineBindPoint bind_point, VkPipelineLayout pipe_layout) const;
		void bind_descriptor_sets(const std::span<VkDescriptorSet>& sets, const std::span<u32>& dynamic_offsets, VkPipelineBindPoint bind_point, VkPipelineLayout pipe_layout) const;

		// Properties
		command_pool& get_command_pool() const { return *pool; }
		u32 get_queue_family() const { return pool->get_queue_family(); }
		bool is_recording() const { return is_open; }

		void clear_flags() { flags = 0; }
		void set_flag(command_buffer_data_flag flag) { flags |= flag; }

		operator VkCommandBuffer() const
		{
			return commands;
		}
	};
void command_buffer::reset()
	{
		// Do the driver reset
		CHECK_RESULT(vkResetCommandBuffer(commands, 0));
	}

void command_buffer::clear_state_cache()
	{
		m_dynamic_state.clear();
		m_bound_pipelines[0] = VK_NULL_HANDLE;
		m_bound_pipelines[1] = VK_NULL_HANDLE;
#ifdef RPCS3_IOS
		for (auto& binding : m_descriptor_bindings)
		{
			binding.count = 0;
		}
#else
		m_bound_descriptor_sets[0] = VK_NULL_HANDLE;
#endif
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

#ifdef RPCS3_IOS
	void command_buffer::bind_pipeline(VkPipeline pipeline, VkPipelineBindPoint bind_point, u32 dynamic_state_mask) const
#else
	void command_buffer::bind_pipeline(VkPipeline pipeline, VkPipelineBindPoint bind_point) const
#endif
	{
		ensure(is_open && bind_point <= VK_PIPELINE_BIND_POINT_COMPUTE);
		auto& cached = m_bound_pipelines[static_cast<int>(bind_point)];
		if (cached == pipeline)
		{
			return;
		}

		cached = pipeline;
		if (bind_point == VK_PIPELINE_BIND_POINT_GRAPHICS)
		{
#ifdef RPCS3_IOS
			// Preserve exactly the states declared dynamic at creation. Unknown
			// callers use mask zero and retain the original full invalidation.
			m_dynamic_state.retain(dynamic_state_mask);
#else
			// Static state in a different pipeline can invalidate dynamic state.
			m_dynamic_state.clear();
#endif
		}
		vkCmdBindPipeline(commands, bind_point, pipeline);
	}

#ifdef RPCS3_IOS
bool command_buffer::update_descriptor_binding_cache(const std::span<VkDescriptorSet>& sets,
		VkPipelineBindPoint bind_point, VkPipelineLayout layout, bool has_dynamic_offsets) const
	{
		ensure(is_open && sets.size() <= 2);
		if (sets.empty())
		{
			return false;
		}
		if (bind_point != VK_PIPELINE_BIND_POINT_GRAPHICS && bind_point != VK_PIPELINE_BIND_POINT_COMPUTE)
		{
			// Preserve pass-through behavior for any future pipeline type.
			return true;
		}

		// Vulkan keeps descriptor bindings independently for each pipeline type.
		// Require the exact layout; compatibility between different layouts is
		// intentionally not inferred from descriptor handles alone.
		auto& cached = m_descriptor_bindings[static_cast<u32>(bind_point)];
		if (has_dynamic_offsets)
		{
			// Dynamic offsets are consumed at bind time. Keep their existing path
			// and invalidate only this pipeline type's non-dynamic cache.
			cached.count = 0;
			return true;
		}
		// At most two handles: fixed-width accesses avoid variable-size libc
		// comparisons/copies on both the hit and changing-handle paths.
		const auto first = sets[0];
		if (cached.count == sets.size() && cached.layout == layout &&
			cached.sets[0] == first && (sets.size() == 1 || cached.sets[1] == sets[1]))
		{
			return false;
		}
		cached.layout = layout;
		cached.count = ::size32(sets);
		cached.sets[0] = first;
		if (sets.size() == 2)
		{
			cached.sets[1] = sets[1];
		}
		return true;
	}
#endif

void command_buffer::bind_descriptor_sets(
		const std::span<VkDescriptorSet>& sets,
		const std::span<u32>& dynamic_offsets,
		VkPipelineBindPoint bind_point,
		VkPipelineLayout pipe_layout) const
	{
		const u32 num_sets = ::size32(sets);
		ensure(num_sets <= 2);

#ifdef RPCS3_IOS
		if (!update_descriptor_binding_cache(sets, bind_point, pipe_layout, !dynamic_offsets.empty()))
		{
			return;
		}
#else
		if (dynamic_offsets.empty() &&
			!memcmp(sets.data(), m_bound_descriptor_sets.data(), sets.size_bytes()))
		{
			return;
		}

		std::memcpy(m_bound_descriptor_sets.data(), sets.data(), sets.size_bytes());
#endif
		vkCmdBindDescriptorSets(commands, bind_point, pipe_layout, 0, num_sets, sets.data(), ::size32(dynamic_offsets), dynamic_offsets.data());
	}

void command_buffer::bind_descriptor_sets(
		const std::span<VkDescriptorSet>& sets,
		VkPipelineBindPoint bind_point,
		VkPipelineLayout pipe_layout) const
	{
		const u32 num_sets = ::size32(sets);
		ensure(is_open && num_sets <= 2);

#ifdef RPCS3_IOS
		if (!update_descriptor_binding_cache(sets, bind_point, pipe_layout, false))
		{
			return;
		}
#else
		if (!memcmp(sets.data(), m_bound_descriptor_sets.data(), sets.size_bytes()))
		{
			return;
		}

		std::memcpy(m_bound_descriptor_sets.data(), sets.data(), sets.size_bytes());
#endif
		vkCmdBindDescriptorSets(commands, bind_point, pipe_layout, 0, num_sets, sets.data(), 0, nullptr);
	}

namespace glsl
{
// Descriptor allocation/template writes are explicit adapters. The actual
// descriptor_table_t::commit and program::bind below decide whether to allocate
// and which descriptor handles reach the production command-buffer wrapper.
struct descriptor_set_boundary
{
    VkDescriptorSet handle = 0;
    explicit operator bool() const { return handle != 0; }
    VkDescriptorSet value() const { return handle; }
    void on_bind() const {}
};
struct descriptor_table_t
{
    bool m_device = false;
    descriptor_set_boundary m_descriptor_set;
    bool m_any_descriptors_dirty = false;
    std::array<bool, 2> m_descriptors_dirty{};
    std::vector<int> m_descriptor_template;
    VkDescriptorSet next_handle = 0;
    u32 allocations = 0, creates = 0, updates = 0;
    descriptor_set_boundary allocate_descriptor_set() { ++allocations; return {next_handle++}; }
    void create_descriptor_template() { ++creates; m_descriptor_template.push_back(1); }
    void update_descriptor_template() { ++updates; }
    VkDescriptorSet commit();
};
constexpr unsigned binding_set_index_max_enum = 2;
struct program
{
    std::array<descriptor_table_t, binding_set_index_max_enum> m_sets;
    VkPipeline m_pipeline = 0;
    u32 m_dynamic_state_mask = 0;
    VkPipelineLayout m_pipeline_layout = 0;
    program& bind(const vk::command_buffer& cmd, VkPipelineBindPoint bind_point);
};
program& program::bind(const vk::command_buffer& cmd, VkPipelineBindPoint bind_point)
		{
			VkDescriptorSet bind_sets[binding_set_index_max_enum];
			unsigned count = 0;

			for (auto& set : m_sets)
			{
				if (!set.m_device)
				{
					continue;
				}

				bind_sets[count++] = set.commit();   // Commit variable changes and return handle to the new set
			}

#ifdef RPCS3_IOS
			cmd.bind_pipeline(m_pipeline, bind_point, m_dynamic_state_mask);
#else
			cmd.bind_pipeline(m_pipeline, bind_point);
#endif
			cmd.bind_descriptor_sets({ bind_sets, count }, bind_point, m_pipeline_layout);
			return *this;
		}
VkDescriptorSet descriptor_table_t::commit()
		{
			if (!m_descriptor_set)
			{
				m_any_descriptors_dirty = true;
				std::fill(m_descriptors_dirty.begin(), m_descriptors_dirty.end(), false);
			}

			// Check if we need to actually open a new set
			if (!m_any_descriptors_dirty)
			{
				return m_descriptor_set.value();
			}

			m_descriptor_set = allocate_descriptor_set();

			if (!m_descriptor_template.empty()) [[ likely ]]
			{
				// Run pointer updates. Optimized for cached back-to-back updates which are quite frequent.
				update_descriptor_template();
			}
			else
			{
				// Creating the template also seeds initial values
				create_descriptor_template();
			}

			m_descriptor_set.on_bind();
			m_any_descriptors_dirty = false;

			return m_descriptor_set.value();
		}
}

struct fixture : command_buffer
{
    recording_driver driver;
    fence completion{&driver};
    u64 attempts = 0;
    u64 mismatches = 0;
    u64 dynamic_calls = 0;

    fixture() { commands = &driver; begin(); }

    void seed_other_caches()
    {
        m_dynamic_state.valid = 0xffff;
        m_bound_pipelines = {123, 456};
    }
    void assert_other_caches_clear() const
    {
        assert(m_dynamic_state.valid == 0);
        assert(m_bound_pipelines[0] == 0 && m_bound_pipelines[1] == 0);
    }
    void assert_other_caches_retained() const
    {
        assert(m_dynamic_state.valid == 0xffff);
        assert(m_bound_pipelines[0] == 123 && m_bound_pipelines[1] == 456);
    }
    void pending()
    {
        assert(!is_open);
        is_pending = true;
        m_submit_fence = &completion;
    }
    void bind(std::vector<VkDescriptorSet> sets, VkPipelineBindPoint point, VkPipelineLayout layout,
        std::vector<u32> offsets = {}, bool offset_overload = false)
    {
        ++attempts;
        const u64 before = driver.calls;
        // program::bind supplies its stack array even when count is zero.
        // Keep that non-null backing for the baseline's zero-length memcmp.
        std::array<VkDescriptorSet, 2> empty_backing{};
        auto set_span = sets.empty() ? std::span<VkDescriptorSet>(empty_backing.data(), 0) : std::span<VkDescriptorSet>(sets);
        if (offset_overload)
        {
            auto offset_span = std::span<u32>(offsets);
            bind_descriptor_sets(set_span, offset_span, point, layout);
        }
        else
        {
            assert(offsets.empty());
            bind_descriptor_sets(set_span, point, layout);
        }
        if (!offsets.empty())
        {
            ++dynamic_calls;
            assert(driver.calls == before + 1);
            const auto& event = driver.events.back();
            assert(event.first == 0 && event.point == point && event.layout == layout);
            assert(event.sets == sets && event.offsets == offsets);
        }
        if (sets.empty())
        {
            assert(driver.calls == before);
            return;
        }
        check_bound(sets, point, layout, offsets);
    }
    void check_bound(const std::vector<VkDescriptorSet>& sets, VkPipelineBindPoint point,
        VkPipelineLayout layout, const std::vector<u32>& offsets = {})
    {
        // Compare every requested set with an uncached binding's required state.
        // Higher unrequested sets remain live: a 2 -> 1 prefix is not itself
        // classified as a semantic defect.
        const auto& bound = driver.slots[point_index(point)];
        bool mismatch = false;
        u32 cursor = 0;
        for (u32 i = 0; i < sets.size(); ++i)
        {
            const u32 number = dynamic_count(sets[i]);
            std::vector<u32> wanted;
            if (number) wanted.assign(offsets.begin() + cursor, offsets.begin() + cursor + number);
            cursor += number;
            const auto& slot = bound[i];
            mismatch |= !slot.valid || slot.set != sets[i] || slot.layout != layout || slot.offsets != wanted;
        }
        assert(cursor == offsets.size());
        mismatches += mismatch;
    }
};
}

struct case_result
{
    std::string name;
    u64 attempts, calls, mismatches, dynamic_calls;
    u64 allocations = 0, creates = 0, updates = 0, pipeline_calls = 0;
};
static std::vector<case_result> cases;
static void save(const char* name, const vk::fixture& f)
{
    cases.push_back({name, f.attempts, f.driver.calls, f.mismatches, f.dynamic_calls});
}

static void controls()
{
    constexpr auto graphics = VK_PIPELINE_BIND_POINT_GRAPHICS;
    constexpr auto compute = VK_PIPELINE_BIND_POINT_COMPUTE;
    {
        vk::fixture f;
        for (int i = 0; i < 64; ++i) f.bind({101, 102}, graphics, 11);
        save("graphics_repeat_plain", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 64; ++i) f.bind({101, 102}, graphics, 11, {}, true);
        save("graphics_repeat_empty_offset_overload", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 64; ++i)
        {
            f.bind({101, 102}, graphics, 11);
            f.bind({201}, compute, 21);
        }
        save("alternating_bind_points", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 4; ++i)
        {
            f.bind({101}, graphics, 11);
            f.bind({101}, compute, 11);
        }
        save("equal_handles_different_bind_point", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 4; ++i)
        {
            f.bind({101}, graphics, 11);
            f.bind({101}, graphics, 12);
        }
        save("incompatible_layout_same_handles", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 8; ++i)
        {
            f.bind({101, 102}, graphics, 11);
            f.bind({301}, graphics, 31);
            f.bind({201}, compute, 21);
            f.bind({101, 102}, graphics, 11);
        }
        save("overlay_return", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 8; ++i)
        {
            f.bind({101, 102}, graphics, 11);
            f.bind({101}, graphics, 11);
            f.bind({101, 102}, graphics, 11);
        }
        save("prefix_count_changes", f);
    }
    {
        vk::fixture f;
        for (u32 i = 0; i < 64; ++i) f.bind({101 + i, 201 + i}, graphics, 11);
        save("changed_descriptor_handles", f);
    }
    {
        vk::fixture f;
        for (u32 i = 0; i < 32; ++i) f.bind({101, 900}, graphics, 11, {16 * (i / 2), 32}, true);
        save("dynamic_offsets_passthrough", f);
    }
    {
        vk::fixture f;
        f.bind({101}, graphics, 11);
        for (int i = 0; i < 16; ++i)
        {
            f.bind({201, 901}, compute, 21, {16, 32}, true);
            f.bind({101}, graphics, 11);
        }
        save("dynamic_compute_preserves_graphics", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 8; ++i)
        {
            f.bind({101, 900}, graphics, 11, {16, 32}, true);
            f.bind({101}, graphics, 11);
            f.bind({101, 102}, graphics, 11);
        }
        save("dynamic_prefix_to_plain", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 8; ++i) f.bind({101}, VK_PIPELINE_BIND_POINT_RAY_TRACING_KHR, 11);
        save("unknown_bind_point_passthrough", f);
    }
    {
        vk::fixture f;
        for (int i = 0; i < 8; ++i)
        {
            f.bind({}, graphics, 11);
            f.bind({}, compute, 21, {}, true);
        }
        save("empty_spans", f);
    }
    {
        vk::fixture f;
        f.bind({101}, graphics, 11);
        f.bind({201}, compute, 21);
        f.seed_other_caches();
        f.end();
        f.reset();
        f.begin();
        f.assert_other_caches_clear();
        f.bind({101}, graphics, 11);
        f.bind({201}, compute, 21);
        assert(f.driver.begins == 2 && f.driver.ends == 1 && f.driver.resets == 1);
        save("real_begin_resets", f);
    }
    {
        vk::fixture f;
        f.bind({101}, graphics, 11);
        f.seed_other_caches();
        f.begin();
        f.assert_other_caches_retained();
        f.bind({101}, graphics, 11);
        assert(f.driver.begins == 1 && f.driver.ends == 0 && f.driver.resets == 0);
        save("already_open_begin_preserves", f);
    }
    {
        vk::fixture f;
        f.bind({101}, graphics, 11);
        f.seed_other_caches();
        f.end();
        f.pending();
        f.begin();
        f.assert_other_caches_clear();
        f.bind({101}, graphics, 11);
        assert(f.driver.begins == 2 && f.driver.ends == 1 && f.driver.resets == 1);
        assert(f.driver.fence_waits == 1 && f.driver.fence_resets == 1);
        save("pending_reuse", f);
    }
    {
        vk::fixture first, second;
        first.bind({101}, graphics, 11);
        second.bind({101}, graphics, 11);
        first.bind({101}, graphics, 11);
        second.bind({101}, graphics, 11);
        cases.push_back({"independent_command_buffers", first.attempts + second.attempts,
            first.driver.calls + second.driver.calls, first.mismatches + second.mismatches, 0});
    }
    {
        vk::fixture f;
        u32 state = 0x23c0de;
        for (u32 i = 0; i < 4096; ++i)
        {
            state = state * 1664525u + 1013904223u;
            const auto point = (state & 0x100) ? graphics : compute;
            const VkPipelineLayout layout = 11 + ((state >> 10) & 1);
            const u32 choice = (state >> 17) % 5;
            if (i && i % 127 == 0)
            {
                f.seed_other_caches();
                f.end();
                f.reset();
                f.begin();
                f.assert_other_caches_clear();
            }
            if (choice == 0) f.bind({101}, point, layout);
            if (choice == 1) f.bind({101, 102}, point, layout);
            if (choice == 2) f.bind({201}, point, layout, {}, true);
            if (choice == 3) f.bind({101, 900}, point, layout, {16 * ((state >> 3) & 7), 32}, true);
            if (choice == 4) f.bind({101}, point, layout, {}, true);
        }
        assert(f.driver.begins == 33 && f.driver.resets == 32);
        save("deterministic_mixed_sequence", f);
    }
    for (bool dirty_and_overlay : {false, true})
    {
        vk::fixture f;
        vk::glsl::program game, conversion, overlay;
        game.m_pipeline = 101;
        game.m_pipeline_layout = 11;
        game.m_sets[0].m_device = game.m_sets[1].m_device = true;
        game.m_sets[0].next_handle = 101;
        game.m_sets[1].next_handle = 201;
        conversion.m_pipeline = 102;
        conversion.m_pipeline_layout = 21;
        conversion.m_sets[0].m_device = true;
        conversion.m_sets[0].next_handle = 301;
        overlay.m_pipeline = 103;
        overlay.m_pipeline_layout = 31;
        overlay.m_sets[0].m_device = true;
        overlay.m_sets[0].next_handle = 401;
        auto bind = [&](vk::glsl::program& p, VkPipelineBindPoint point)
        {
            p.bind(f, point);
            ++f.attempts;
            std::vector<VkDescriptorSet> expected_sets;
            for (const auto& set : p.m_sets)
                if (set.m_device) expected_sets.push_back(set.m_descriptor_set.value());
            f.check_bound(expected_sets, point, p.m_pipeline_layout);
        };
        for (int i = 0; i < 16; ++i)
        {
            bind(game, graphics);
            bind(conversion, compute);
        }
        if (dirty_and_overlay)
        {
            game.m_sets[0].m_any_descriptors_dirty = true;
            bind(game, graphics);
            bind(conversion, compute);
            bind(overlay, graphics);
            bind(game, graphics);
        }
        save(dirty_and_overlay ? "production_program_dirty_and_overlay" : "production_program_reuse", f);
        auto& result = cases.back();
        for (const auto* p : {&game, &conversion, &overlay})
            for (const auto& set : p->m_sets)
            {
                result.allocations += set.allocations;
                result.creates += set.creates;
                result.updates += set.updates;
            }
        result.pipeline_calls = f.driver.pipeline_calls;
    }
}

struct timing_result
{
    std::string name;
    std::vector<u64> nanoseconds;
    u64 operations = 0, calls = 0, checksum = 0;
};
static timing_result measure(unsigned mode)
{
    timing_result result;
    result.name = mode == 0 ? "graphics_hits" : mode == 1 ? "changing_sets" : "alternating_bind_points";
    constexpr u32 iterations = 2000000;
    result.operations = iterations;
    for (int sample = -1; sample < 7; ++sample)
    {
        vk::fixture f;
        f.driver.capture = false;
        std::array<VkDescriptorSet, 2> sets{101, 102};
        const auto start = std::chrono::steady_clock::now();
        const u32 count = sample < 0 ? 10000 : iterations;
        for (u32 i = 0; i < count; ++i)
        {
            const auto point = mode == 2 && (i & 1) ? VK_PIPELINE_BIND_POINT_COMPUTE : VK_PIPELINE_BIND_POINT_GRAPHICS;
            sets[0] = mode == 1 ? 101 + i : point == VK_PIPELINE_BIND_POINT_COMPUTE ? 201 : 101;
            sets[1] = sets[0] + 1;
            const VkPipelineLayout layout = point == VK_PIPELINE_BIND_POINT_COMPUTE ? 21 : 11;
            f.bind_descriptor_sets(std::span<VkDescriptorSet>(sets), point, layout);
        }
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - start).count();
        if (sample >= 0)
        {
            result.nanoseconds.push_back(static_cast<u64>(elapsed));
            if (sample) assert(result.calls == f.driver.calls && result.checksum == f.driver.checksum);
            result.calls = f.driver.calls;
            result.checksum = f.driver.checksum;
        }
    }
    return result;
}

int main(int argc, char** argv)
{
    controls();
    u64 mismatch_count = 0;
    std::cout << "{\"commandBufferBytes\":" << sizeof(vk::command_buffer) << ",\"cases\":[";
    for (std::size_t i = 0; i < cases.size(); ++i)
    {
        const auto& item = cases[i];
        if (i) std::cout << ',';
        std::cout << "{\"name\":\"" << item.name << "\",\"attempts\":" << item.attempts
            << ",\"calls\":" << item.calls << ",\"mismatches\":" << item.mismatches
            << ",\"dynamicCalls\":" << item.dynamic_calls
            << ",\"allocations\":" << item.allocations << ",\"templateCreates\":" << item.creates
            << ",\"templateUpdates\":" << item.updates << ",\"pipelineCalls\":" << item.pipeline_calls << '}';
        mismatch_count += item.mismatches;
    }
    std::cout << "],\"mismatches\":" << mismatch_count << ",\"benchmark\":[";
    if (argc == 2 && std::string(argv[1]) == "--benchmark")
    {
        for (unsigned mode = 0; mode < 3; ++mode)
        {
            const auto result = measure(mode);
            if (mode) std::cout << ',';
            std::cout << "{\"name\":\"" << result.name << "\",\"operations\":" << result.operations
                << ",\"calls\":" << result.calls << ",\"checksum\":" << result.checksum << ",\"nanoseconds\":[";
            for (std::size_t i = 0; i < result.nanoseconds.size(); ++i)
            {
                if (i) std::cout << ',';
                std::cout << result.nanoseconds[i];
            }
            std::cout << "]}";
        }
    }
    std::cout << "]}\n";
    return mismatch_count ? 86 : 0;
}
