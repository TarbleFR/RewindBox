// GPL-2.0. Production snippets are extracted from the materialized Core.
#include "util/types.hpp"
#include "util/endian.hpp"
#include "Emu/Cell/SPUOpcodes.h"
#include "Emu/Cell/SPUAnalyser.h"
#include <algorithm>
#include <cassert>
#include <iostream>
#include <random>
#include <string>
#include <vector>

const spu_decoder<spu_itype> g_spu_itype{};
#include "Branch.inc"
constexpr u32 SPU_RdDec = 8;
struct cpu_translator
{
    template <class T> static constexpr int get_type() { return sizeof(std::remove_extent_t<T>); }
};
struct mask_info { u64 i1, i0; int (*type)(); u64 extract_from, insert_to; };
const mask_info masks[30] =
#include "Masks.inc"
;
struct { struct { bool spu_debug = false; } core; } g_cfg;
static u64 notices = 0, writes = 0;
static bool fail_write = false;
struct sink
{
    bool enabled;
    template <class... T> void operator()(T&&...) const { if (enabled) ++notices; }
};
struct { sink notice{true}, trace{false}; } spu_log;
namespace fs
{
    constexpr int write = 1, append = 2;
    template <class... T> bool write_file(T&&...) { ++writes; return !fail_write; }
}
struct context
{
    struct program { u32 entry_point = 0; std::vector<u32> data; } func;
    struct { bool logged = false; } item;
    struct { std::string get_cache_path() const { return {}; } } runtime;
    struct flag { bool value = false; bool exchange(int v) { return std::exchange(value, v != 0); } } logged;
    struct slot { flag logged; } state;
    slot* add_loc = &state;
    decltype(runtime)* m_spurt = &runtime;
    std::string m_hash = "test";
    u64 dumps = 0;
    void dump(const program&, std::string& text) { ++dumps; text = "full SPU disassembly"; }
    void run()
    {
#include "Diagnostics.inc"
    }
};

int main(int argc, char** argv)
{
    assert(argc == 2);
    const bool control = std::string_view(argv[1]) == "reference";
    std::mt19937 random(499);
    unsigned bad_masks = 0;
    for (const auto& m : masks)
    {
        bool bad = false;
        for (unsigned trial = 0; trial < 1024; ++trial)
        {
            std::array<u8, 16> a{}, b{}, expected{}, actual{};
            for (unsigned i = 0; i < 16; ++i) { a[i] = random(); b[i] = random(); }
            for (unsigned i = 0; i < 16; ++i)
            {
                const u8 selector = (i < 8 ? m.i0 : m.i1) >> (8 * (i % 8));
                // Scalar PS3 SHUFB byte selection, independent of vector inserts.
                expected[i] = selector < 16 ? a[15 - selector] : b[31 - selector];
            }
            actual = b;
            const unsigned width = m.type();
            std::copy_n(a.begin() + m.extract_from * width, width, actual.begin() + m.insert_to * width);
            bad |= actual != expected;
        }
        bad_masks += bad;
    }
    assert(bad_masks == (control ? 1u : 0u));
    unsigned branch_order_errors = 0;
    // Actual decoder, all four conditional relative branch opcodes, LS wraparound,
    // backwards branches, self loops and the coincident fallthrough case.
    for (u32 base : {0u, 0x100u, 0xc16cu, 0x3fffcu})
    for (u32 opcode : {0x20000000u, 0x21000000u, 0x22000000u, 0x23000000u})
    for (u32 displacement : {0u, 1u, 2u, 0x7fffu, 0x8000u, 0xffffu})
    {
        const auto targets = op_branch_targets(base, spu_opcode_t{opcode | (displacement << 7)});
        const u32 taken = (base + displacement * 4) & 0x3fffc;
        const u32 fallthrough = (base + 4) & 0x3fffc;
        const std::array<u32, 2> expected{taken, taken == fallthrough ? u32{umax} : fallthrough};
        branch_order_errors += targets != expected;
        if (taken != fallthrough) assert((targets == expected || targets == std::array<u32, 2>{fallthrough, taken}));
    }
    assert(branch_order_errors == (control ? 80u : 0u));
    context ctx;
    const u32 rddec = (0xdu << 21) | (SPU_RdDec << 7);
    ctx.func.data = {std::bit_cast<u32>(be_t<u32>{rddec})};
    for (unsigned i = 0; i < 4096; ++i) ctx.run();
    assert(ctx.dumps == (control ? 4096u : 0u));
    assert(notices == (control ? 4096u : 0u));
    assert(writes == 0);
    const u64 before = ctx.dumps;
    g_cfg.core.spu_debug = true;
    ctx.run();
    assert(ctx.dumps == before + 1 && writes == 1);
    ctx.state.logged.value = false;
    fail_write = true;
    ctx.run();
    assert(ctx.dumps == before + 2 && writes == 2);
    // Non-decrementer function still reports a failed explicit debug file write.
    ctx.func.data = {0};
    ctx.state.logged.value = false;
    const auto before_notices = notices;
    ctx.run();
    assert(ctx.dumps == before + 3 && notices == before_notices + 1);
    std::cout << (control ? "CONTROL" : "PASS") << ": 30 masks x 1024 inputs; bad_masks=" << bad_masks
              << "; branch_order_errors=" << branch_order_errors
              << "; ordinary_decrementer_dumps=" << before << "; debug/error dumps preserved\n";
}
