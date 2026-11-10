#include <array>
#include <bit>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>
using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using f32 = float;
void ensure(bool condition) { assert(condition); }
namespace rsx {
using flags32_t = u32;
enum class texture_dimension_extended : u32 { texture_dimension_2d = 1 };
enum class texture_upload_context { shader_read };
// @CONSTANTS@
// @PROGRAM_TYPES@
// @PROGRAM_METHODS@
u32 get_host_format_snorm_mask(u32 format) { assert(format == CELL_GCM_TEXTURE_A8R8G8B8); return 0xf; }
// @FORMAT_METHODS@
struct StateBits {
    u32 value = 0;
    bool test(u32 mask) const { return (value & mask) != 0; }
    void clear(u32 mask) { value &= ~mask; }
    StateBits& operator|=(u32 mask) { value |= mask; return *this; }
    u32 operator&(u32 mask) const { return value & mask; }
};
struct Texture {
    int unit = 0, kind = -1;
    bool on = true;
    bool enabled() const { return on; }
    texture_format_ex format_ex() const {
        texture_format_ex result(CELL_GCM_TEXTURE_A8R8G8B8);
        result.encoded_remap = RSX_TEXTURE_REMAP_IDENTITY;
        if (kind == 0) {
            result.features = RSX_FORMAT_FEATURE_GAMMA_CORRECTION;
            result.texel_remap_control = GAMMA_RGB_MASK;
        } else if (kind == 1) {
            result.features = RSX_FORMAT_FEATURE_SIGNED_COMPONENTS;
            result.texel_remap_control = SEXT_MASK;
        }
        return result;
    }
    u32 remap() const { return RSX_TEXTURE_REMAP_IDENTITY; }
    struct Remap { u32 shuffle_mask_bits(u32 value) const { return value; } };
    Remap decoded_remap() const { return {}; }
    int min_filter() const { return 1; }
    int mag_filter() const { return 1; }
};
struct Registers {
    std::array<Texture, 16> fragment_textures;
    std::pair<u32, u32> shader_program_address() const { return {0, 0}; }
} method_registers;
u32 get_address(u32 offset, u32) { return offset; }
int classify_format(u32) { return 1; }
}
using namespace rsx;
namespace program_hash_util {
struct fragment_program_utils {
    struct Metadata {
        u16 referenced_textures_mask = 0, bx2_texture_reads_mask = 0;
        u32 program_start_offset = 0, program_ucode_length = 16;
    };
    static Metadata analyse_fragment_program(void*);
};
static fragment_program_utils::Metadata next_metadata;
auto fragment_program_utils::analyse_fragment_program(void*) -> Metadata { return next_metadata; }
}
namespace vm { void* base(u32) { static std::array<u8, 64> bytes{}; return bytes.data(); } }
struct Config { struct Video { bool disable_hardware_texel_remapping = false; } video; } g_cfg;
using VkFormat = int;
using VkFilter = int;
constexpr VkFormat VK_FORMAT_UNDEFINED = 0, UNORM = 1, SRGB = 2, SNORM = 3;
constexpr VkFilter VK_FILTER_NEAREST = 0, VK_FILTER_LINEAR = 1;
constexpr int VK_SAMPLER_MIPMAP_MODE_NEAREST = 0;
constexpr u32 VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT = 1;
constexpr int RSX_FORMAT_CLASS_UNDEFINED = 0, RSX_FORMAT_CLASS_COLOR = 1;
namespace vk {
struct Image {
    int fmt;
    int format() const { return fmt; }
    Image* image() { return this; }
    Image* as(int);
};
static Image root_image{UNORM}, srgb_image{SRGB}, snorm_image{SNORM};
Image* Image::as(int value) {
    assert(this == &root_image);
    return value == SRGB ? &srgb_image : &snorm_image;
}
int get_compatible_snorm_format(int value) { assert(value == UNORM); return SNORM; }
int get_compatible_srgb_format(int value) { assert(value == UNORM); return SRGB; }
struct minification_filter { int filter = VK_FILTER_LINEAR, mipmap_mode = 1; };
minification_filter get_min_filter(int filter) { assert(filter == 1); return {}; }
int get_mag_filter(int filter) { return filter; }
int get_compatible_sampler_format(int, int) { return UNORM; }
struct Device {
    int get_formats_support() { return 0; }
    struct Properties { u32 optimalTilingFeatures = VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT; };
    Properties get_format_properties(int) { return {}; }
};
struct texture_cache {
    struct sampled_image_descriptor {
        int format_class = RSX_FORMAT_CLASS_UNDEFINED;
        texture_format_ex format_ex;
        Image* image_handle = nullptr;
        bool is_cyclic_reference = false;
        rsx::texture_upload_context upload_context = rsx::texture_upload_context::shader_read;
        struct { int gcm_format = CELL_GCM_TEXTURE_A8R8G8B8; } external_subresource_desc;
        bool validate() const { return image_handle != nullptr; }
    };
    std::array<u32, 16> uploads{};
    bool sampler_requires_validation(u32, const sampled_image_descriptor&) { return false; }
    int prepare_sampler_validation(u32) { return 0; }
    void finish_sampler_validation(u32, sampled_image_descriptor&, int, int) {}
    sampled_image_descriptor upload_texture(int, const Texture& texture, int) {
        ++uploads.at(texture.unit);
        sampled_image_descriptor result;
        result.image_handle = &root_image;
        result.format_class = RSX_FORMAT_CLASS_COLOR;
        return result;
    }
};
}
struct BufferInfo { u32 offset = 0; };
struct Ring {
    alignas(16) std::array<u8, 768> bytes{};
    u32 writes = 0;
    template<int Alignment, int Size> u32 static_alloc() { static_assert(Alignment == 256 && Size == 768); return 0; }
    void* map(u32 offset, u32 size) { assert(offset == 0 && size == bytes.size()); return bytes.data(); }
    void unmap() { ++writes; }
    template<int Size> BufferInfo window(u32 offset, u32 size, u32 capacity) {
        static_assert(Size == 768); assert(offset == 0 && size == Size && capacity >= size); return {};
    }
};
namespace rsx {
struct Program {
    u8* data = nullptr;
    u32 offset = 0, ucode_length = 0, total_length = 0, ctrl = 0;
    u32 texcoord_control_mask = 0, mrt_buffers_count = 1;
    bool two_sided_lighting = false;
    bool valid = false;
    fragment_program_texture_state texture_state;
    fragment_program_texture_config texture_params;
};
struct thread {
    explicit thread(bool use_new) : patched(use_new) {
        method_registers = {};
        for (u32 i = 0; i < 16; ++i) method_registers.fragment_textures[i].unit = i;
        g_cfg.video.disable_hardware_texel_remapping = false;
        observed_mag.fill(-1); observed_min.fill(-1);
    }
    bool patched;
    StateBits m_graphics_state;
    std::array<bool, 16> m_textures_dirty{};
    bool m_samplers_dirty = true;
    program_hash_util::fragment_program_utils::Metadata current_fp_metadata;
    Program current_fragment_program;
    fragment_program_texture_state current_fp_texture_state;
    std::array<std::unique_ptr<vk::texture_cache::sampled_image_descriptor>, 16> fs_sampler_state;
    vk::texture_cache m_texture_cache;
    int command_buffer = 0, m_rtts = 0;
    int* m_current_command_buffer = &command_buffer;
    vk::Device device;
    vk::Device* m_device = &device;
    std::array<int, 16> observed_mag, observed_min;
    Ring m_fragment_texture_params_ring_info;
    u32 m_texture_parameters_dynamic_offset = 0;
    BufferInfo m_fragment_texture_params_buffer_info;
    void prefetch_before();
    void prefetch_after();
    void load_textures() {
        bool check_for_cyclic_refs = false;
        auto check_surface_cache_sampler_valid = [](auto*, const auto&) { return true; };
// @TEXTURE_PREFIX@
            VkFilter mag_filter;
            vk::minification_filter min_filter;
            const u32 texture_format = sampler_state->format_ex.format();
// @FILTER_SELECTION@
            observed_mag[i] = mag_filter;
            observed_min[i] = min_filter.filter;
        }
        (void)check_for_cyclic_refs;
        m_samplers_dirty = false;
    }
    void build_parameters() {
// @PARAMETER_GUARD@
        for (u32 textures_ref = current_fp_metadata.referenced_textures_mask, i = 0; textures_ref; textures_ref >>= 1, ++i) {
            if (!(textures_ref & 1)) continue;
            const auto& tex = method_registers.fragment_textures[i];
            if (!tex.enabled() || fs_sampler_state[i]->format_class == RSX_FORMAT_CLASS_UNDEFINED) continue;
            auto& sampler_descriptors = fs_sampler_state;
// @PARAMETER_REMAP@
            u32 texture_control = 0;
// @FORMAT_PARAMETERS@
// @PARAMETER_CONTROL@
        }
    }
    void upload_parameters() {
        const bool update_fragment_texture_env = !!(m_graphics_state & rsx::pipeline_state::fragment_texture_state_dirty);
        const struct { u32 maxUniformBufferRange = 4096; } gpu_limits;
// @PARAMETER_UPLOAD@
    }
    void shader(u16 refs, u16 bx2, bool already_dirty = false) {
        program_hash_util::next_metadata = {refs, bx2, 0, 16};
        m_graphics_state |= fragment_program_ucode_dirty;
        if (already_dirty) m_graphics_state |= fragment_program_state_dirty;
        if (patched) prefetch_after(); else prefetch_before();
        load_textures(); build_parameters(); upload_parameters();
        m_graphics_state.value = 0;
    }
    void prime(u16 refs, u16 bx2) {
        for (u32 i = 0; i < 16; ++i) m_textures_dirty[i] = !!(refs & (1u << i));
        shader(refs, bx2, true);
        m_textures_dirty.fill(false);
    }
    bool correct(u32 unit, int kind, bool bx2, bool software = false) {
        const auto& descriptor = *fs_sampler_state.at(unit);
        const auto view = bx2 || software ? UNORM : kind == 0 ? SRGB : SNORM;
        const auto filter = kind == 1 && (bx2 || software) ? VK_FILTER_NEAREST : VK_FILTER_LINEAR;
        const u32 remap = (bx2 || software) ? u32(kind == 0 ? GAMMA_RGB_MASK : SEXT_MASK) : 0;
        const u32 features = kind == 0 ? RSX_FORMAT_FEATURE_GAMMA_CORRECTION : RSX_FORMAT_FEATURE_SIGNED_COMPONENTS;
        const u32 control = (features << FORMAT_FEATURES_OFFSET) | remap;
        const auto expected_remap = RSX_TEXTURE_REMAP_IDENTITY | (bx2 ? (0xfu << 16) : 0);
        fragment_program_texture_config::TIU_slot transferred;
        std::memcpy(&transferred, m_fragment_texture_params_ring_info.bytes.data() + unit * sizeof(transferred), sizeof(transferred));
        return descriptor.image_handle && descriptor.image_handle->format() == view &&
            observed_mag[unit] == filter && observed_min[unit] == filter &&
            current_fragment_program.texture_params[unit].control == control &&
            current_fragment_program.texture_params[unit].remap == expected_remap &&
            transferred.control == control && transferred.remap == expected_remap &&
            bool(current_fragment_program.ctrl & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT) == (bx2 || software);
    }
};
// @PREFETCH_BEFORE@
// @PREFETCH_AFTER@
}
using RSXFragmentProgram = rsx::Program;
namespace cache_probe {
struct fragment_program_utils {
    static std::optional<RSXFragmentProgram> normalize_fragment_program_key(const RSXFragmentProgram&, u16);
};
struct fragment_program_compare {
    static bool compare_properties(const RSXFragmentProgram&, const RSXFragmentProgram&);
};
// @CACHE_PROPERTIES@
#ifdef RPCS3_IOS
// @CACHE_NORMALIZATION@
#endif
bool redundant_conversion_key(const RSXFragmentProgram& program) {
    auto key = program;
#ifdef RPCS3_IOS
    // Force the production normalizer to do work: it removes unused color/texcoord
    // properties, but must retain the format-conversion control bit.
    auto input = program;
    input.ctrl |= RSX_SHADER_CONTROL_FLAT_SHADING;
    input.two_sided_lighting = true;
    input.texcoord_control_mask = ~0u;
    const auto normalized = fragment_program_utils::normalize_fragment_program_key(input, 0);
    assert(normalized);
    key = *normalized;
    assert(key.ctrl == program.ctrl);
#endif
    auto clean = key;
    clean.ctrl &= ~RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT;
    const bool distinct = !fragment_program_compare::compare_properties(key, clean);
    assert(distinct == bool(program.ctrl & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT));

    const auto& m_prog = program;
    struct Props { bool require_color_format_convert = false; } m_shader_props;
// @CONVERSION_PROPERTY@
    const auto& props = m_shader_props;
    std::vector<std::string> enabled_options;
// @CONVERSION_OPTION@
    assert(enabled_options == (distinct ? std::vector<std::string>{"_ENABLE_FORMAT_CONVERSION"} : std::vector<std::string>{}));
    return distinct;
}
}
static u32 transitions = 0, baseline_transition_defects = 0, candidate_transition_defects = 0, lifecycle_cases = 0;
static u32 conversion_removal_cases = 0, baseline_redundant_keys = 0, candidate_redundant_keys = 0;
static void test_transitions() {
    for (u32 unit : {0u, 15u}) for (int kind : {0, 1}) for (bool old_bx2 : {false, true})
    for (bool dirty : {false, true}) {
        const u16 bit = u16(1u << unit);
        for (bool patched : {false, true}) {
            rsx::thread t(patched); method_registers.fragment_textures[unit].kind = kind;
            t.prime(bit, old_bx2 ? bit : 0);
            assert(t.correct(unit, kind, old_bx2));
            t.shader(bit, old_bx2 ? 0 : bit, dirty);
            bool correct = t.correct(unit, kind, !old_bx2);
            if (patched) candidate_transition_defects += !correct; else baseline_transition_defects += !correct;
#ifdef RPCS3_IOS
            assert(correct == patched);
            assert(t.m_texture_cache.uploads[unit] == (patched ? 2u : 1u));
#else
            assert(!correct && t.m_texture_cache.uploads[unit] == 1);
#endif
        }
        ++transitions;
    }
}
static void test_lifecycle() {
#ifdef RPCS3_IOS
    for (u32 unit : {0u, 15u}) for (int kind : {0, 1}) {
        const u16 bit = u16(1u << unit), other = u16(1u << (unit ? 0 : 15));
        { // A changed, disabled unit is refreshed after it is enabled again.
            rsx::thread t(true); auto& texture = method_registers.fragment_textures[unit]; texture.kind = kind;
            t.prime(bit, bit); texture.on = false; t.m_textures_dirty[unit] = true;
            t.shader(bit, 0); assert(!t.fs_sampler_state[unit]->image_handle);
            texture.on = true; t.m_textures_dirty[unit] = true;
            t.shader(bit, 0); assert(t.correct(unit, kind, false)); ++lifecycle_cases;
        }
        { // A dormant BX2 unit keeps its dirty bit without an upload.
            rsx::thread t(true); method_registers.fragment_textures[unit].kind = kind;
            t.prime(bit | other, bit); const auto uploads = t.m_texture_cache.uploads;
            t.shader(other, 0); assert(t.m_textures_dirty[unit]);
            assert(t.m_texture_cache.uploads == uploads);
            t.shader(bit | other, 0); assert(t.correct(unit, kind, false)); ++lifecycle_cases;
        }
        { // The last BX2 removal clears the shared conversion flag.
            rsx::thread t(true); method_registers.fragment_textures[unit].kind = kind;
            t.prime(bit | other, bit);
            assert(t.current_fragment_program.ctrl & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT);
            t.shader(other, 0);
            assert(!(t.current_fragment_program.ctrl & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT)); ++lifecycle_cases;
        }
        { // Same use: no extra sampler upload or parameter transfer.
            rsx::thread t(true); method_registers.fragment_textures[unit].kind = kind;
            t.prime(bit, 0); const auto uploads = t.m_texture_cache.uploads;
            const auto writes = t.m_fragment_texture_params_ring_info.writes;
            t.shader(bit, 0); assert(t.correct(unit, kind, false));
            assert(t.m_texture_cache.uploads == uploads && t.m_fragment_texture_params_ring_info.writes == writes);
            ++lifecycle_cases;
        }
        { // No BX2 anywhere: reintroduction must restore software-conversion control.
            rsx::thread t(true); method_registers.fragment_textures[unit].kind = kind;
            g_cfg.video.disable_hardware_texel_remapping = true;
            t.prime(bit | other, 0); assert(t.correct(unit, kind, false, true));
            t.shader(other, 0, true);
            assert(!(t.current_fragment_program.ctrl & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT));
            const auto uploads = t.m_texture_cache.uploads;
            t.shader(bit | other, 0); assert(t.correct(unit, kind, false, true));
            assert(t.m_texture_cache.uploads == uploads); ++lifecycle_cases;
        }
    }
#endif
}
static void test_conversion_removal() {
    for (u32 unit : {0u, 15u}) for (int kind : {0, 1}) {
        const u16 bit = u16(1u << unit), other = u16(1u << (unit ? 0 : 15));
        for (bool patched : {false, true}) {
            rsx::thread t(patched); method_registers.fragment_textures[unit].kind = kind;
            g_cfg.video.disable_hardware_texel_remapping = true;
            t.prime(bit | other, 0);
            assert(t.correct(unit, kind, false, true));
            const auto uploads = t.m_texture_cache.uploads;
            t.shader(other, 0); // No BX2 and no pre-existing state dirty bit.
            const bool stale = cache_probe::redundant_conversion_key(t.current_fragment_program);
            if (patched) candidate_redundant_keys += stale; else baseline_redundant_keys += stale;
            assert(t.m_texture_cache.uploads == uploads);
#ifdef RPCS3_IOS
            assert(stale != patched);
#else
            assert(stale);
#endif
        }
        ++conversion_removal_cases;
#ifdef RPCS3_IOS
        ++lifecycle_cases;
#endif
    }
}
static u32 negative_controls(bool patched) {
    u32 failures = 0;
    for (const auto& [kind, old_bx2] : {std::pair{0, false}, std::pair{1, false}, std::pair{1, true}}) {
        rsx::thread t(patched); method_registers.fragment_textures[0].kind = kind;
        t.prime(1, old_bx2 ? 1 : 0); t.shader(1, old_bx2 ? 0 : 1);
        assert(!t.correct(0, kind, !old_bx2)); ++failures;
    }
    {
        rsx::thread t(patched); method_registers.fragment_textures[0].kind = 1;
        t.prime(3, 1); t.shader(2, 0); assert(!t.m_textures_dirty[0]);
        t.shader(3, 0); assert(!t.correct(0, 1, false)); ++failures;
    }
    {
        rsx::thread t(patched); method_registers.fragment_textures[0].kind = 0;
        t.prime(3, 1); t.shader(2, 0);
        assert(t.current_fragment_program.ctrl & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT); ++failures;
    }
    {
        rsx::thread t(patched); method_registers.fragment_textures[0].kind = 0;
        g_cfg.video.disable_hardware_texel_remapping = true;
        t.prime(3, 0); t.shader(2, 0, true); t.shader(3, 0);
        assert(!t.correct(0, 0, false, true));
        assert(!(t.current_fragment_program.ctrl & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT)); ++failures;
    }
    {
        rsx::thread t(patched); method_registers.fragment_textures[0].kind = 0;
        g_cfg.video.disable_hardware_texel_remapping = true;
        t.prime(3, 0); t.shader(2, 0);
        assert(cache_probe::redundant_conversion_key(t.current_fragment_program)); ++failures;
    }
    return failures;
}
int main() {
    static_assert(RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT == 0x04000000);
    static_assert(!(fs_export_config_mask & RSX_SHADER_CONTROL_TEXTURE_FORMAT_CONVERT));
    static_assert(sizeof(fragment_program_texture_config::TIU_slot) == 48);
    test_transitions(); test_lifecycle(); test_conversion_removal();
    const auto negatives = negative_controls(false); assert(negatives == 7);
#ifdef RPCS3_IOS
    assert(candidate_transition_defects == 0 && lifecycle_cases == 24 && candidate_redundant_keys == 0);
#else
    assert(negative_controls(true) == negatives);
    assert(candidate_transition_defects == baseline_transition_defects && lifecycle_cases == 0);
#endif
    assert(transitions == 16 && baseline_transition_defects == 16);
    assert(conversion_removal_cases == 4 && baseline_redundant_keys == 4);
    std::cout << "{\"transitions\":" << transitions
        << ",\"baselineTransitionDefects\":" << baseline_transition_defects
        << ",\"candidateTransitionDefects\":" << candidate_transition_defects
        << ",\"lifecycleCases\":" << lifecycle_cases
        << ",\"conversionRemovalCases\":" << conversion_removal_cases
        << ",\"baselineRedundantConversionKeys\":" << baseline_redundant_keys
        << ",\"candidateRedundantConversionKeys\":" << candidate_redundant_keys
        << ",\"baselineNegativeControls\":" << negatives << "}\n";
}
