#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <random>
#include <string_view>
#include <vector>

using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
constexpr int smax = std::numeric_limits<int>::max();
struct areai
{
    int x1, y1, x2, y2;
    int width() const { return x2 - x1; }
    int height() const { return y2 - y1; }
};
struct section_t { u16 dst_x, dst_y, dst_z, dst_w, dst_h; unsigned char level; };
struct desc_t { u16 width, height, depth; std::vector<section_t> sections_to_copy; };
struct candidate_t
{
    desc_t external_subresource_desc;
    // INSERT_CANDIDATE
};
struct baseline_t
{
    desc_t external_subresource_desc;
    // INSERT_BASELINE
};

static std::uint64_t checks = 0, cases = 0, baseline_mismatches = 0, safe_cases = 0;
static void require(bool value, std::string_view why)
{
    ++checks;
    if (!value) { std::cerr << why << '\n'; std::exit(1); }
}

// Independent wide-integer oracle for the existing sum-and-bounds heuristic.
// Deliberately retains overlap counting: this check is not a union-area test.
static bool reference(const desc_t& desc, int threshold)
{
    using wide = unsigned __int128;
    wide required = wide(desc.width) * desc.height * desc.depth * threshold / 100;
    wide sum = 0;
    u64 min_x = std::numeric_limits<u64>::max(), min_y = min_x, max_x = 0, max_y = 0;
    bool any = false;
    for (const auto& item : desc.sections_to_copy)
    {
        if (item.level != 0) continue;
        any = true;
        sum += wide(item.dst_w) * item.dst_h;
        u64 x = item.dst_x, y = u64(item.dst_z) * desc.height + item.dst_y;
        min_x = std::min(min_x, x); min_y = std::min(min_y, y);
        max_x = std::max(max_x, x + item.dst_w); max_y = std::max(max_y, y + item.dst_h);
    }
    if (sum < required) return false;
    if (!any) return required == 0;
    return wide(max_x - min_x) * (max_y - min_y) >= required;
}

static void verify(const desc_t& desc, int threshold)
{
    ++cases;
    const bool expected = reference(desc, threshold);
    require(candidate_t{desc}.atlas_covers_target_area(threshold) == expected, "candidate coverage differs from wide oracle");
#ifndef VERIFY_CANDIDATE_ONLY
    const bool old = baseline_t{desc}.atlas_covers_target_area(threshold);
    baseline_mismatches += old != expected;
    // These generated inputs have at most 512 copies with each rectangle in
    // bounds. When the whole percentage fits, all intermediate sums and bbox
    // products fit too, including repeated sections in the generated cases.
    u64 total = u64(desc.width) * desc.height * desc.depth;
    u64 sum = 0;
    for (const auto& section : desc.sections_to_copy)
        if (section.level == 0) sum += u64(section.dst_w) * section.dst_h;
    if (total * threshold <= u64(smax) && sum <= u64(smax) && total <= u64(smax))
    {
        require(old == expected, "ordinary coverage behavior changed");
        ++safe_cases;
    }
#endif
}

int main(int argc, char** argv)
{
    const desc_t overflow_probe{256, 256, 512, {{0, 0, 0, 256, 256, 0}}};
    if (argc == 2 && std::string_view(argv[1]) == "--baseline-overflow-probe")
    {
        const bool old = baseline_t{overflow_probe}.atlas_covers_target_area(90);
        std::cout << "baseline_accepts_single_of_512_slices=" << old << '\n';
        return 0;
    }
    require(!reference(overflow_probe, 90), "probe oracle must reject incomplete volume");
    verify(overflow_probe, 90);
#ifndef VERIFY_CANDIDATE_ONLY
    require(baseline_t{overflow_probe}.atlas_covers_target_area(90), "expected baseline overflow was not observed by this compiler");
#endif
    for (u16 width : {u16(1), u16(64), u16(256), u16(1024), u16(4096), u16(65535)})
    for (u16 height : {u16(1), u16(64), u16(256), u16(1024), u16(4096), u16(65535)})
    for (u16 depth : {u16(1), u16(6), u16(16), u16(64), u16(128), u16(256), u16(512)})
    {
        desc_t d{width, height, depth, {}};
        for (unsigned count : {0u, unsigned(depth / 2), unsigned(depth - 1), unsigned(depth)})
        {
            d.sections_to_copy.clear();
            for (unsigned z = 0; z < count; ++z)
                d.sections_to_copy.push_back({0, 0, u16(z), width, height, 0});
            for (int threshold : {1, 50, 90, 99, 100}) verify(d, threshold);
        }
    }
    std::mt19937 rng(0x7c2a51);
    constexpr u16 sizes[] = {1, 8, 64, 127, 256, 512, 1024, 2048, 4096};
    constexpr u16 depths[] = {1, 6, 16, 64, 128, 256, 512};
    for (unsigned iteration = 0; iteration < 24000; ++iteration)
    {
        const u16 width = sizes[rng() % std::size(sizes)], height = sizes[rng() % std::size(sizes)], depth = depths[rng() % std::size(depths)];
        // Keep this generated group within a 256 MiB byte-per-texel volume.
        if (u64(width) * height * depth > 256ull * 1024 * 1024) continue;
        desc_t d{width, height, depth, {}};
        const auto count = 1 + rng() % 24;
        for (unsigned i = 0; i < count; ++i)
        {
            const u16 x = rng() % width, y = rng() % height, z = rng() % depth;
            const u16 w = 1 + rng() % (width - x), h = 1 + rng() % (height - y);
            d.sections_to_copy.push_back({x, y, z, w, h, static_cast<unsigned char>(rng() % 5 == 0 ? 1 : 0)});
        }
        for (int threshold : {1, 50, 90, 99, 100}) verify(d, threshold);
    }
    std::cout << "{\"case\":\"atlas_area\",\"cases\":" << cases
        << ",\"checks\":" << checks << ",\"baseline_mismatches\":" << baseline_mismatches
        << ",\"unchanged_safe_cases\":" << safe_cases << "}\n";
}
