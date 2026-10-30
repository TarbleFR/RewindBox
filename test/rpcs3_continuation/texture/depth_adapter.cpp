#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
using u8 = uint8_t; using u16 = uint16_t; using u32 = uint32_t; using s32 = int32_t; using f32 = float;
constexpr u32 CELL_GCM_TEXTURE_LN=0x20, CELL_GCM_TEXTURE_UN=0x40;
namespace rsx {
enum class texture_dimension_extended { texture_dimension_1d, texture_dimension_2d, texture_dimension_cubemap, texture_dimension_3d };
enum class texture_wrap_mode { clamp_to_edge, repeat };
u32 get_address(u32 x, u32) { return x; }
}
using Dim = rsx::texture_dimension_extended;
struct image_section_attributes_t { u32 address, gcm_format, pitch; u16 width, height, depth, mipmaps, slice_h; u8 bpp; bool swizzled, edge_clamped; };
struct texture_cache_search_options { bool is_compressed_format{}; };
struct size3f { float width, height, depth; };
struct result { image_section_attributes_t attr; size3f scale; bool valid; u32 tex_size, required_height; u8 subsurfaces; Dim dimension; };
struct tex_t {
    Dim dim; u16 w, h, d, mips; u32 row_pitch; bool un, linear, compressed;
    u32 offset() const { return 0x10000; } u32 location() const { return 0; }
    u32 format() const { return (compressed ? 2u : 1u) | (un ? CELL_GCM_TEXTURE_UN : 0u) | (linear ? CELL_GCM_TEXTURE_LN : 0u); }
    u16 width() const { return w; } u16 height() const { return h; } u16 depth() const { return d; }
    u16 get_exact_mipmap_count() const { return mips; }
    Dim get_extended_texture_dimension() const { return dim; }
    u32 pitch() const { return row_pitch; } bool border_type() const { return true; }
    rsx::texture_wrap_mode wrap_s() const { return rsx::texture_wrap_mode::repeat; }
    rsx::texture_wrap_mode wrap_t() const { return rsx::texture_wrap_mode::repeat; }
};
u8 get_format_block_size_in_bytes(u32) { return 4; }
u32 get_format_packed_pitch(u32, u16 width, bool, bool) { return width * 4u; }
u32 get_texture_size(const tex_t& t, unsigned = 0) { return (t.row_pitch ? t.row_pitch : t.w * 4u) * t.h * (t.dim == Dim::texture_dimension_cubemap ? 6 : t.d); }
namespace helpers { bool is_compressed_gcm_format(u32 x) { return x == 2; } }
namespace fmt { template<class... T> void throw_exception(const char*, T...) { throw std::runtime_error("dimension"); } }
struct { template<class... T> void warning(const char*, T...) {} } rsx_log;
static result upload_prefix(const tex_t& tex) {
    // INSERT_PRODUCTION_PREFIX
    return { attributes, scale, true, tex_size, required_surface_height, subsurface_count, extended_dimension };
}
int main() {
    unsigned cases = 0, bad_depth = 0, baseline_expected_bad = 0;
    const u16 widths[] = {1,2,8,32,128,512};
    const u16 heights[] = {1,4,16,64,256};
    const u16 depths[] = {1,2,3,8,32,128};
    for (unsigned dim = 0; dim < 4; ++dim)
    for (bool un : {false,true}) for (bool linear : {false,true})
    for (bool compressed : {false,true})
    for (auto w : widths) for (auto h : heights) for (auto d : depths)
    for (u16 mips : {1,2,4}) for (unsigned pitch_mode=0; pitch_mode<4; ++pitch_mode) {
        tex_t t{static_cast<Dim>(dim),w,h,d,mips, pitch_mode==0 ? 0u : pitch_mode==1 ? w*4u : pitch_mode==2 ? w*8u : std::max(4u,w*2u),un,linear,compressed};
        result actual = upload_prefix(t);
        if (!actual.valid) throw std::runtime_error("valid input rejected");
        float expected_depth = dim < 2 || (linear && !t.row_pitch) ? 0.f : un ? 1.f / (dim==2 ? 6.f : float(d)) : 1.f;
        if (!std::isfinite(actual.scale.depth) || actual.scale.depth != expected_depth) ++bad_depth;
        if (dim >= 2 && un && !(linear && !t.row_pitch)) ++baseline_expected_bad;
        // Prefix change must not disturb X/Y scale or guest layout; compare an independent arithmetic oracle.
        float expected_x = un ? 1.f/w : 1.f;
        float expected_y = dim==0 ? 0.f : un ? 1.f/h : 1.f;
        if (linear && !t.row_pitch) { expected_x=1.f;expected_y=0.f; }
        else if (linear && w*4u>t.row_pitch && !compressed) expected_x *= float(w*4u)/t.row_pitch;
        if (actual.scale.width != expected_x || actual.scale.height != expected_y) throw std::runtime_error("xy changed");
        if (actual.attr.depth != (dim==2 ? 6 : dim==3 ? d : 1)) throw std::runtime_error("depth layout");
        ++cases;
    }
#ifdef EXPECT_BASELINE
    if (!bad_depth || bad_depth != baseline_expected_bad) throw std::runtime_error("negative control mismatch");
#else
    if (bad_depth) throw std::runtime_error("invalid normalization");
#endif
    std::cout << "{\"case\":\"unnormalized_depth\",\"cases\":" << cases
              << ",\"bad_depth_scales\":" << bad_depth << "}\n";
}
