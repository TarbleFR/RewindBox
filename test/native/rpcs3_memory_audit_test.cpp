// SPDX-License-Identifier: GPL-2.0-or-later
#include "Utilities/JITObjectBuffer.h"
#include "Utilities/JITArenaAllocator.h"
#include "NeoSwapCompilerBudget.h"
#include "NeoSwapBudget.h"
#include "rpcs3/Emu/RSX/VK/vkutils/VRAMBudgetPolicy.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <random>
#include <thread>
#include <vector>

static std::vector<unsigned char> gzip(const std::vector<unsigned char>& data) {
    z_stream z{}; assert(deflateInit2(&z, 6, Z_DEFLATED, 31, 8, Z_DEFAULT_STRATEGY) == Z_OK);
    std::vector<unsigned char> out(deflateBound(&z, data.size()));
    z.next_in = const_cast<unsigned char*>(data.data()); z.avail_in = data.size(); z.next_out = out.data(); z.avail_out = out.size();
    assert(deflate(&z, Z_FINISH) == Z_STREAM_END); out.resize(z.total_out); deflateEnd(&z); return out;
}
static bool decode(const std::vector<unsigned char>& file, std::vector<unsigned char>& out, bool short_reads = false) {
    auto read = [&](std::uint64_t offset, void* target, std::size_t count) -> std::size_t {
        if (offset > file.size()) return 0;
        const auto n = std::min({count, file.size() - static_cast<std::size_t>(offset), short_reads && count != 4 ? std::size_t(73) : count});
        std::memcpy(target, file.data() + offset, n); return n;
    };
    const auto n = jit_object_buffer::gzip_size(file.size(), read);
    if (!n) return false;
    out.resize(n);
    return jit_object_buffer::inflate(file.size(), read, out.data(), out.size());
}
int main() {
    std::mt19937 random(508);
    for (std::size_t size : {1u, 65535u, 65536u, 65537u, 5u * 1024 * 1024}) {
        std::vector<unsigned char> input(size), output;
        for (auto& byte : input) byte = random();
        const auto file = gzip(input);
        assert(decode(file, output) && output == input);
        assert(decode(file, output, true) && output == input);
        auto corrupt = file; corrupt[corrupt.size() - 8] ^= 1; assert(!decode(corrupt, output));
        corrupt = file; corrupt.resize(corrupt.size() - 1); assert(!decode(corrupt, output));
        corrupt = file; corrupt.push_back(0); assert(!decode(corrupt, output));
        corrupt = file; corrupt.back() = 127; assert(!decode(corrupt, output));
    }
    // Small compressed input with a dishonest ISIZE cannot expand past the owner.
    auto bomb = gzip(std::vector<unsigned char>(1024 * 1024, 0));
    bomb[bomb.size() - 4] = 16; bomb[bomb.size() - 3] = bomb[bomb.size() - 2] = bomb.back() = 0;
    std::vector<unsigned char> out; assert(!decode(bomb, out));

    using rpcs3::ios::jit::arena_allocator;
    using rpcs3::ios::jit::arena_range;
    arena_allocator arena(4 * 16384); arena_range a, b;
    assert(arena.allocate_lowest(8192, 1, a));
    assert(arena.allocate_lowest(8192, 1, b));
    assert(arena.release(a.offset, a.size));
    assert(arena.released_data_pages(a.offset, a.size, 16384).size == 0); // live neighbour
    assert(arena.release(b.offset, b.size));
    auto pages = arena.released_data_pages(b.offset, b.size, 16384);
    assert(pages.offset == 0 && pages.size == 16384);
    assert(arena.released_data_pages(1, 10, 3).size == 0);
    // Random allocator fragmentation: no advice interval overlaps any live byte.
    std::vector<arena_range> live;
    for (unsigned i = 0; i < 3000; ++i) {
        arena_range item;
        if (arena.allocate_highest(1 + random() % 3000, 16, item)) live.push_back(item);
        if (!live.empty() && random() % 2) {
            const auto index = random() % live.size(); const auto freed = live[index];
            live.erase(live.begin() + index); assert(arena.release(freed.offset, freed.size));
            const auto p = arena.released_data_pages(freed.offset, freed.size, 4096);
            for (auto retained : live) assert(!p.size || p.offset + p.size <= retained.offset || retained.offset + retained.size <= p.offset);
        }
    }
    constexpr auto MiB = 1024ull * 1024;
    neostation::compiler::budget admission;
    admission.update(true, false, 256 * MiB);
    auto first = admission.acquire(512 * MiB, 2048 * MiB); assert(first);
    auto second = admission.acquire(512 * MiB, 2048 * MiB); assert(second);
    assert(!admission.acquire(1024 * MiB, 2048 * MiB));
    assert(admission.reserved() == 1024 * MiB);
    admission.update(true, true, 256 * MiB);
    assert(!admission.acquire(1, 4096 * MiB));
    admission.release(first); admission.release(first); admission.release(second); // duplicate/stale release
    auto oversized = admission.acquire(4096 * MiB, 32 * MiB); assert(oversized); // exclusive progress
    assert(!admission.acquire(1, 8192 * MiB)); admission.release(oversized);
    admission.update(false, false, 0); assert(!admission.acquire(1, 8192 * MiB));
    admission.update(true, false, 0);
    std::vector<std::thread> workers;
    for (int i = 0; i < 12; ++i) workers.emplace_back([&] {
        for (int j = 0; j < 100; ++j) {
            std::uint64_t ticket;
            while (!(ticket = admission.acquire(128 * MiB, 8192 * MiB))) std::this_thread::yield();
            admission.release(ticket);
        }
    });
    for (auto& worker : workers) worker.join();
    assert(admission.reserved() == 0);
    using namespace neostation::budget;
    Inputs in{}; in.session_active = true; in.system_valid = true; in.system_usable_bytes = 4 * GiB; in.physical_bytes = 8 * GiB;
    const auto ordinary = decide(in, {}); in.compiler_working_set_estimate_bytes = GiB;
    const auto compiling = decide(in, {});
    assert(compiling.growth_room_bytes + GiB == ordinary.growth_room_bytes);
    assert(vk::get_preferred_vram_block_size(0) == 0);
    assert(vk::get_preferred_vram_block_size(4 * GiB) == 32 * MiB);
    assert(vk::get_preferred_vram_block_size(8 * GiB) == 0);
    std::cout << "PASS direct gzip ownership/corruption bounds, shared compiler admission, fragmentation-safe data pages and VMA heap boundaries\n";
}
