
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <tuple>
#include <utility>
#include <vector>
using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define ensure(x) assert(x)
// Numeric production flag values are supplied from RSXDriverState.h.




namespace rsx
{
	enum pipeline_state : u32
	{
		fragment_program_ucode_dirty = (1 << 0),   // Fragment program ucode changed
		vertex_program_ucode_dirty   = (1 << 1),   // Vertex program ucode changed
		fragment_program_state_dirty = (1 << 2),   // Fragment program state changed
		vertex_program_state_dirty   = (1 << 3),   // Vertex program state changed
		fragment_state_dirty         = (1 << 4),   // Fragment state changed (alpha test, etc)
		vertex_state_dirty           = (1 << 5),   // Vertex state changed (scale_offset, clip planes, etc)
		transform_constants_dirty    = (1 << 6),   // Transform constants changed
		fragment_constants_dirty     = (1 << 7),   // Fragment constants changed
		framebuffer_reads_dirty      = (1 << 8),   // Framebuffer contents changed
		fragment_texture_state_dirty = (1 << 9),   // Fragment texture parameters changed
		vertex_texture_state_dirty   = (1 << 10),  // Fragment texture parameters changed
		scissor_config_state_dirty   = (1 << 11),  // Scissor region changed
		zclip_config_state_dirty     = (1 << 12),  // Viewport Z clip changed

		scissor_setup_invalid        = (1 << 13),  // Scissor configuration is broken
		scissor_setup_clipped        = (1 << 14),  // Scissor region is cropped by viewport constraint

		polygon_stipple_pattern_dirty = (1 << 15),  // Rasterizer stippling pattern changed
		line_stipple_pattern_dirty    = (1 << 16),  // Line stippling pattern changed

		push_buffer_arrays_dirty      = (1 << 17),   // Push buffers have data written to them (immediate mode vertex buffers)

		polygon_offset_state_dirty    = (1 << 18), // Polygon offset config was changed
		depth_bounds_state_dirty      = (1 << 19), // Depth bounds configuration changed

		pipeline_config_dirty         = (1 << 20), // Generic pipeline configuration changes. Shader peek hint.

		rtt_config_dirty              = (1 << 21), // Render target configuration changed
		rtt_config_contested          = (1 << 22), // Render target configuration is indeterminate
		rtt_config_valid              = (1 << 23), // Render target configuration is valid
		rtt_cache_state_dirty         = (1 << 24), // Texture cache state is indeterminate

		xform_instancing_state_dirty  = (1 << 25), // Transform instancing state has changed

		zeta_address_is_cyclic        = (1 << 26), // The currently bound Z buffer is active for R/W in a cyclic manner
		zeta_address_cyclic_barrier   = (1 << 27), // A memory barrier is required to "end" the Z buffer cyclic state

		blend_config_dirty            = (1 << 28), // Blending configuration has been updated. Only matters when programmable blending is in use.

		// TODO - Should signal that we simply need to do a FP compare before the next draw call and invalidate the ucode if the content has changed.
		// Marking as dirty to invalidate hot cache also works, it's not like there's tons of barriers per frame anyway.
		fragment_program_needs_rehash = fragment_program_ucode_dirty,

		fragment_program_dirty = fragment_program_ucode_dirty | fragment_program_state_dirty,
		vertex_program_dirty = vertex_program_ucode_dirty | vertex_program_state_dirty,
		invalidate_pipeline_bits = fragment_program_dirty | vertex_program_dirty | xform_instancing_state_dirty,
		invalidate_zclip_bits = vertex_state_dirty | zclip_config_state_dirty,
		memory_barrier_bits = framebuffer_reads_dirty,

		// Vulkan-specific signals
		invalidate_vk_dynamic_state = zclip_config_state_dirty | scissor_config_state_dirty | polygon_offset_state_dirty | depth_bounds_state_dirty,

		all_dirty = ~0u
	};
}

struct flag_set {
    u32 value=0;
    u32 load() const { return value; }
    u32 operator&(u32 mask) const { return value & mask; }
    void clear(u32 mask) { value &= ~mask; }
    void operator|=(u32 mask) { value |= mask; }
};
enum class shader_mode { recompiler, async_recompiler, async_with_interpreter, interpreter_only };
constexpr u32 RSX_SHADER_CONTROL_PROGRAMMABLE_BLENDING = 0x100;
struct shader_input { u32 id=1, ctrl=0; bool valid=true; };
struct shader_metadata { u32 id=1; };
struct shader_object { u32 id=1; };
struct binding_table {};
binding_table table;
struct hint { bool has_vertex_program() const { return true; } bool has_fragment_program() const { return true; } };
struct device { bool get_depth_bounds_support() const { return true; } };
device gpu;
struct config_t { struct { bool debug_overlay=false; } video; struct { bool show_shader_compilation_hint=false; } misc; } g_cfg;
namespace rsx { class thread { public: void begin() {} }; enum class framebuffer_creation_context { context_draw }; }
namespace rsx::overlays { inline void show_shader_compile_notification() {} }
namespace rpcs3::ios { inline void record_rsx_shader_cache_lookup(bool) {} }
namespace vk {
struct vertex_input_assembly_state { u32 primitive=3; bool restart_index_enabled=false; } desired_ia;
struct pipeline_props {
    struct state_t {
        struct ia_t { u32 topology=3; bool primitiveRestartEnable=false; bool operator==(const ia_t&) const=default; } ia;
        u32 other=0;
        void set_primitive_type(u32 x) { ia.topology=x; }
        void enable_primitive_restart(bool x) { ia.primitiveRestartEnable=x; }
        bool operator==(const state_t&) const=default;
    } state;
    u64 renderpass_key=0;
    bool operator==(const pipeline_props&) const=default;
} desired_props;
u32 decodes=0, enters=0;
vertex_input_assembly_state decode_vertex_input_assembly_state() { return desired_ia; }
pipeline_props decode_rsx_state(void*, vertex_input_assembly_state ia, int, int, u8, u8, bool, bool) {
    ++decodes; auto result=desired_props; result.state.ia={ia.primitive,ia.restart_index_enabled}; return result;
}
bool renderpass_has_input_attachments(u64 key) { return (key & 1) != 0; }
void enter_uninterruptible() { ++enters; }
void leave_uninterruptible() { assert(enters); --enters; }
namespace glsl { struct program { u32 vp=0, fp=0; pipeline_props props; bool interpreter=false; }; }
using key_t=std::tuple<u32,u32,u32,bool,u32,u64,bool>;
std::map<key_t,glsl::program> programs;
glsl::program* resolve(u32 vp,u32 fp,pipeline_props p,bool interpreter) {
    key_t key{vp,fp,p.state.ia.topology,p.state.ia.primitiveRestartEnable,p.state.other,p.renderpass_key,interpreter};
    return &programs.try_emplace(key,glsl::program{vp,fp,p,interpreter}).first->second;
}
}
struct cache_t {
    u32 queries=0; bool ready=true; shader_object vp,fp;
    auto get_graphics_pipeline(hint*,const shader_input& v,const shader_input& f,const vk::pipeline_props& props,bool async,bool) {
        ++queries; vp.id=v.id; fp.id=f.id;
        vk::glsl::program* p=(!ready && async)?nullptr:vk::resolve(v.id,f.id,props,false);
        return std::tuple{p,static_cast<const shader_object*>(&vp),static_cast<const shader_object*>(&fp)};
    }
    bool check_cache_missed() const { return false; }
};
struct interpreter_t {
    bool is_interpreter(vk::glsl::program* p) const { return p && p->interpreter; }
    vk::glsl::program* get(const vk::pipeline_props& p,shader_metadata f,shader_metadata v,u32,u32) {
        return vk::resolve(v.id,f.id,p,true);
    }
};
class VKGSRender : public rsx::thread {
public:
    shader_mode m_shader_mode=shader_mode::recompiler;
    flag_set m_graphics_state;
    shader_input current_fragment_program,current_vertex_program;
    shader_metadata current_fp_metadata,current_vp_metadata;
    shader_input pending_fp,pending_vp;
    int fs_sampler_state=0,vs_sampler_state=0;
    vk::pipeline_props m_pipeline_properties;
    vk::glsl::program* m_program=nullptr;
    vk::glsl::program* m_prev_program=nullptr;
    const shader_object* m_vertex_prog=nullptr;
    const shader_object* m_fragment_prog=nullptr;
    interpreter_t m_shader_interpreter;
    u64 m_current_renderpass_key=0;
    void* m_ctx=nullptr;
    struct { std::pair<int,int> m_bound_depth_stencil; } m_rtts;
    int backend_config=0;
    std::vector<int> m_draw_buffers{1};
    device* m_device=&gpu;
    cache_t cache;
    cache_t* m_prog_buffer=&cache;
    hint m_program_cache_hint;
    struct { u32 program_cache_lookups_total=0,program_cache_lookups_ellided=0; } m_frame_stats;
    void* m_overlay_manager=nullptr;
    u32 m_interpreter_state=0;
    const binding_table* m_vs_binding_table=nullptr;
    const binding_table* m_fs_binding_table=nullptr;
    u32 fp_resolves=0,vp_resolves=0;
    bool skip_current_frame=false,swapchain_unavailable=false;
    struct { bool disable_rendering() const { return false; } } cond_render_ctrl;
    void init_buffers(rsx::framebuffer_creation_context) {}
    void begin();
    struct sampled_image { u32 format_class; bool format_ex=false; };
    void late_texture_format_change(bool is_sampler_dirty,u32 previous_format_class,sampled_image* sampler_state) {
        // Execute the exact load_texture_env conditional with its continue target.
        do {
		if (!is_sampler_dirty)
		{
			if (sampler_state->format_class != previous_format_class)
			{
				// Host details changed but RSX is not aware
				m_graphics_state |= rsx::fragment_program_state_dirty;
			}

			if (sampler_state->format_ex)
			{
				// Nothing to change, use cached sampler
				continue;
			}
		}

        } while (false);
    }
    void get_current_fragment_program(int) {
        ++fp_resolves;
        if (m_graphics_state & rsx::fragment_program_dirty) {
            current_fragment_program=pending_fp; current_fp_metadata.id=pending_fp.id;
            m_graphics_state.clear(rsx::fragment_program_dirty);
        }
    }
    void get_current_vertex_program(int) {
        ++vp_resolves;
        if (m_graphics_state & (rsx::vertex_program_dirty|rsx::xform_instancing_state_dirty)) {
            current_vertex_program=pending_vp; current_vp_metadata.id=pending_vp.id;
        }
    }
    void invalidate_render_pass() {
        m_current_renderpass_key=!!(current_fragment_program.ctrl & RSX_SHADER_CONTROL_PROGRAMMABLE_BLENDING);
        m_graphics_state |= rsx::pipeline_config_dirty;
    }
    auto get_binding_table() const { return std::pair{&table,&table}; }
    bool load_program();
};
void VKGSRender::begin()
{
	// Save shader state now before prefetch and loading happens
	m_interpreter_state = (m_graphics_state.load() & rsx::pipeline_state::invalidate_pipeline_bits);

	rsx::thread::begin();

	if (skip_current_frame ||
		swapchain_unavailable ||
		cond_render_ctrl.disable_rendering())
	{
		return;
	}

	init_buffers(rsx::framebuffer_creation_context::context_draw);

	if (m_graphics_state & rsx::pipeline_state::invalidate_pipeline_bits)
	{
		// Shaders need to be reloaded.
		m_prev_program = m_program;
		m_program = nullptr;
	}
}
bool VKGSRender::load_program()
{
	const auto shadermode = m_shader_mode;

	// TODO: EXT_dynamic_state should get rid of this sillyness soon (kd)
	const auto vertex_state = vk::decode_vertex_input_assembly_state();

	// Preserve shader invalidation before the resolved-program helpers consume
	// it. Equal fixed-function properties do not imply the same shader program.
	const bool program_state_dirty = !!(m_graphics_state & rsx::pipeline_state::invalidate_pipeline_bits);
	if (program_state_dirty)
	{
		get_current_fragment_program(fs_sampler_state);
		ensure(current_fragment_program.valid);

		get_current_vertex_program(vs_sampler_state);

		m_graphics_state.clear(rsx::pipeline_state::invalidate_pipeline_bits);
	}
	else if (!(m_graphics_state & rsx::pipeline_state::pipeline_config_dirty) &&
		m_program &&
		m_pipeline_properties.state.ia.topology == vertex_state.primitive &&
		m_pipeline_properties.state.ia.primitiveRestartEnable == vertex_state.restart_index_enabled)
	{
		if (!m_shader_interpreter.is_interpreter(m_program)) [[ likely ]]
		{
			return true;
		}

		if (shadermode == shader_mode::interpreter_only)
		{
			m_program = m_shader_interpreter.get(
				m_pipeline_properties,
				current_fp_metadata,
				current_vp_metadata,
				current_vertex_program.ctrl,
				current_fragment_program.ctrl);

			std::tie(m_vs_binding_table, m_fs_binding_table) = get_binding_table();
			return true;
		}
	}

	if (!!(current_fragment_program.ctrl & RSX_SHADER_CONTROL_PROGRAMMABLE_BLENDING) !=
		vk::renderpass_has_input_attachments(m_current_renderpass_key))
	{
		invalidate_render_pass();
	}

	auto &vertex_program = current_vertex_program;
	auto &fragment_program = current_fragment_program;

	if (m_graphics_state & rsx::pipeline_state::pipeline_config_dirty)
	{
		vk::pipeline_props properties = vk::decode_rsx_state(
			m_ctx,
			vertex_state,
			m_rtts.m_bound_depth_stencil.second,
			backend_config,
			static_cast<u8>(m_draw_buffers.size()),
			u8((m_current_renderpass_key >> 16) & 0xF),
			m_device->get_depth_bounds_support(),
			!!(current_fragment_program.ctrl & RSX_SHADER_CONTROL_PROGRAMMABLE_BLENDING)
		);

		properties.renderpass_key = m_current_renderpass_key;
		// CELL539_PIPELINE_DIRTY: this register state has been decoded even
		// when it resolves to the currently bound pipeline. A later register
		// change will mark it dirty again through the existing invalidation.
		m_graphics_state.clear(rsx::pipeline_state::pipeline_config_dirty);
		if (m_program &&
			!m_shader_interpreter.is_interpreter(m_program) &&
			!program_state_dirty &&
			m_pipeline_properties == properties)
		{
			// Nothing changed
			return true;
		}

		// Fallthrough
		m_pipeline_properties = properties;
	}
	else
	{
		// Update primitive type and restart index. Note that this is not needed with EXT_dynamic_state
		m_pipeline_properties.state.set_primitive_type(vertex_state.primitive);
		m_pipeline_properties.state.enable_primitive_restart(vertex_state.restart_index_enabled);
		m_pipeline_properties.renderpass_key = m_current_renderpass_key;
	}

	m_vertex_prog = nullptr;
	m_fragment_prog = nullptr;

	if (shadermode != shader_mode::interpreter_only) [[likely]]
	{
		vk::enter_uninterruptible();

		if (g_cfg.video.debug_overlay)
		{
			m_frame_stats.program_cache_lookups_total += 2;
			if (m_program_cache_hint.has_fragment_program())
			{
				m_frame_stats.program_cache_lookups_ellided++;
			}
			if (m_program_cache_hint.has_vertex_program())
			{
				m_frame_stats.program_cache_lookups_ellided++;
			}
		}

		// Load current program from cache
		std::tie(m_program, m_vertex_prog, m_fragment_prog) = m_prog_buffer->get_graphics_pipeline(
			&m_program_cache_hint,
			vertex_program,
			fragment_program,
			m_pipeline_properties,
			shadermode != shader_mode::recompiler, true);

		vk::leave_uninterruptible();

		const bool cache_missed = m_prog_buffer->check_cache_missed();
#ifdef RPCS3_IOS
		rpcs3::ios::record_rsx_shader_cache_lookup(!cache_missed);
#endif
		if (cache_missed)
		{
			// Notify the user with HUD notification
			if (g_cfg.misc.show_shader_compilation_hint)
			{
				if (m_overlay_manager)
				{
					rsx::overlays::show_shader_compile_notification();
				}
			}
		}
	}
	else
	{
		m_program = nullptr;
	}

	if (shadermode == shader_mode::async_with_interpreter || shadermode == shader_mode::interpreter_only)
	{
		const bool is_interpreter = !m_program;
		const bool was_interpreter = m_shader_interpreter.is_interpreter(m_prev_program);

		// First load the next program if not available
		if (!m_program)
		{
			m_program = m_shader_interpreter.get(
				m_pipeline_properties,
				current_fp_metadata,
				current_vp_metadata,
				current_vertex_program.ctrl,
				current_fragment_program.ctrl);

			// Program has changed, reupload
			m_interpreter_state = rsx::invalidate_pipeline_bits;
		}

		// If swapping between interpreter and recompiler, we need to adjust some flags to reupload data as needed.
		if (is_interpreter != was_interpreter)
		{
			// Always reupload transform constants when going between interpreter and recompiler
			m_graphics_state |= rsx::transform_constants_dirty;

			// Always reload fragment constansts when moving from interpreter back to recompiler.
			if (was_interpreter)
			{
				m_graphics_state |= rsx::fragment_constants_dirty;
			}
		}
	}

	if (m_program)
	{
		std::tie(m_vs_binding_table, m_fs_binding_table) = get_binding_table();
	}
	else
	{
		m_vs_binding_table = nullptr;
		m_fs_binding_table = nullptr;
	}

	return m_program != nullptr;
}

int main() {
    u64 cases=0,mismatches=0,old_native_kept=0,warm_lookups=0,clean_case_lookups=0;
    for (u32 shader_mask=0;shader_mask<8;shader_mask++)
    for (u32 pipe_dirty=0;pipe_dirty<2;pipe_dirty++)
    for (u32 fixed_change=0;fixed_change<2;fixed_change++)
    for (u32 ia_change=0;ia_change<2;ia_change++)
    for (u32 restart_change=0;restart_change<2;restart_change++)
    for (u32 mode=0;mode<4;mode++)
    for (u32 old_kind=0;old_kind<3;old_kind++)
    for (u32 ready=0;ready<2;ready++)
    for (u32 debug=0;debug<2;debug++) {
        // Changes to fixed properties are legal only when their dirty bit is set.
        if (fixed_change && !pipe_dirty) continue;
        VKGSRender r;
        r.cache.ready=ready;
        r.m_shader_mode=static_cast<shader_mode>(mode);
        g_cfg.video.debug_overlay=debug;
        const u32 flags=((shader_mask&1)?rsx::fragment_program_state_dirty:0u)
            |((shader_mask&2)?rsx::vertex_program_state_dirty:0u)
            |((shader_mask&4)?rsx::xform_instancing_state_dirty:0u)
            |(pipe_dirty?rsx::pipeline_config_dirty:0u);
        r.m_graphics_state.value=flags;
        r.pending_fp.id=(shader_mask&1)?2:1;
        r.pending_vp.id=(shader_mask&6)?3:1;
        vk::desired_ia={3+ia_change,bool(restart_change)};
        vk::desired_props={}; vk::desired_props.state.other=fixed_change;
        if (old_kind) {
            r.m_program=vk::resolve(1,1,r.m_pipeline_properties,old_kind==2);
            r.m_prev_program=r.m_program;
        }
        const bool got=r.load_program();
        assert(vk::enters==0);
        assert((r.m_graphics_state.value & (rsx::invalidate_pipeline_bits|rsx::pipeline_config_dirty))==0);
        vk::pipeline_props expected_props=vk::desired_props;
        expected_props.state.ia={vk::desired_ia.primitive,vk::desired_ia.restart_index_enabled};
        // A clean cached native program remains valid even if an async compiler is unavailable.
        const bool clean_native=old_kind==1 && !shader_mask && !fixed_change && !ia_change && !restart_change;
        bool expected_native=(mode!=3 && (ready || mode==0)) || clean_native;
        bool expected_interpreter=!expected_native && (mode==2 || mode==3);
        if (old_kind==2 && !shader_mask && !pipe_dirty && !ia_change && !restart_change && mode==3)
            expected_interpreter=true;
        const bool expected_present=expected_native || expected_interpreter;
        bool match=got==expected_present;
        if (got && expected_present) {
            match &= r.m_program->vp==r.pending_vp.id && r.m_program->fp==r.pending_fp.id;
            match &= r.m_program->props==expected_props;
            match &= r.m_program->interpreter==expected_interpreter;
        }
        if (!match) {
            ++mismatches;
            if (r.m_program && r.m_program->vp==1 && r.m_program->fp==1 && shader_mask) ++old_native_kept;
            if (mismatches<3) std::cerr << "mismatch flags=" << flags << " mode=" << mode << " old=" << old_kind << " ready=" << ready << '\n';
        }
        if (clean_native) clean_case_lookups+=r.cache.queries;
        // A resolved, compiled pipeline and cleared flags need no additional lookup on a warm call.
        if (match && r.m_program && !r.m_program->interpreter && mode!=3) {
            const u32 before=r.cache.queries;
            assert(r.load_program());
            warm_lookups+=r.cache.queries-before;
        }
        ++cases;
    }
    // Exhaustive FP/VP identity sequence with alternating redundant fixed-state writes.
    VKGSRender seq; vk::desired_props={}; vk::desired_ia={}; g_cfg.video.debug_overlay=false;
    seq.m_graphics_state.value=rsx::pipeline_config_dirty;
    assert(seq.load_program());
    u64 sequence_mismatches=0;
    for (u32 i=0;i<20000;i++) {
        seq.pending_fp.id=2+(i%29); seq.pending_vp.id=50+(i%17);
        seq.m_graphics_state.value=rsx::fragment_program_state_dirty|rsx::vertex_program_state_dirty
            |((i%3)?rsx::pipeline_config_dirty:0u);
        assert(seq.load_program());
        if (seq.m_program->vp!=seq.pending_vp.id || seq.m_program->fp!=seq.pending_fp.id) ++sequence_mismatches;
    }
    // Real begin() is not sufficient: upload_texture may reveal a new host
    // format class later in end(), after begin's program-pointer invalidation.
    VKGSRender late; vk::desired_props={}; vk::desired_ia={};
    late.m_program=vk::resolve(1,1,late.m_pipeline_properties,false);
    auto old_program=late.m_program;
    late.m_graphics_state.value=rsx::pipeline_config_dirty;
    late.begin();
    assert(late.m_program==old_program);
    VKGSRender::sampled_image sampler{2,true};
    late.late_texture_format_change(false,1,&sampler);
    assert(late.m_graphics_state.value & rsx::fragment_program_state_dirty);
    late.pending_fp.id=2;
    assert(late.load_program());
    const bool late_texture_mismatch=late.m_program->fp!=2;
    std::cout << "{\"cases\":"<<cases<<",\"mismatches\":"<<mismatches
        <<",\"stale_native_cases\":"<<old_native_kept<<",\"sequence_draws\":20000,\"sequence_mismatches\":"<<sequence_mismatches
        <<",\"warm_extra_lookups\":"<<warm_lookups<<",\"clean_native_lookups\":"<<clean_case_lookups
        <<",\"late_texture_mismatch\":"<<late_texture_mismatch<<"}\n";
}
