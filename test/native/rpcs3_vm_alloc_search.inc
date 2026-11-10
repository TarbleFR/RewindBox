// Native adapters for the unchanged VM page mapping, lock and shared-memory
// interfaces. Both allocator versions below are extracted from production.
// No guest execution, host VM syscall timing or atomic concurrency is modeled.
#define RPCS3_IOS 1
#ifdef NDEBUG
#error "This differential test requires active assertions"
#endif
#include <algorithm>
#include <array>
#include <bit>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>
#include <sys/mman.h>

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;

#define ensure(condition) do { if (!(condition)) throw std::logic_error(#condition); } while (false)

struct Event
{
    char kind;
    std::array<u64, 6> args;
    bool operator==(const Event&) const = default;
};

static bool record_events = false;
static std::vector<Event> events;
static u64 page_reads = 0;
static u32 lock_depth = 0;
static u64 next_shm_id = 1000;

static void event(char kind, u64 a = 0, u64 b = 0, u64 c = 0,
                  u64 d = 0, u64 e = 0, u64 f = 0)
{
    if (record_events)
        events.push_back({kind, {a, b, c, d, e, f}});
}

namespace fmt
{
template<class... Args>
[[noreturn]] void throw_exception(const char*, Args...)
{
    throw std::invalid_argument("invalid alignment");
}
}

namespace utils
{
template<class T, class U>
constexpr T align(T value, U alignment)
{
    return (value + static_cast<T>(alignment) - 1) & (T{0} - static_cast<T>(alignment));
}

enum class shm_use { guest_data };
struct shm
{
    u64 id;
    explicit shm(u64 existing_id) : id(existing_id) {}
    shm(u32 size, int, shm_use) : id(next_shm_id++)
    {
        event('C', size, id, lock_depth);
    }
};
}

using AllocationMap = std::map<u32, std::pair<u32, std::shared_ptr<utils::shm>>>;
struct MapHolder
{
    mutable AllocationMap allocations;
    template<class T> T& get() const { return allocations; }
};
template<class> using auto_typemap = MapHolder;

constexpr u64 operator""_u64(const char* text, usz count)
{
    u64 result = 0;
    for (usz i = 0; i < count; ++i)
        result |= static_cast<u64>(static_cast<unsigned char>(text[i])) << (8 * i);
    return result;
}

namespace vm
{
enum : u8
{
    page_readable = 1 << 0, page_writable = 1 << 1, page_executable = 1 << 2,
    page_64k_size = 1 << 5, page_1m_size = 1 << 6, page_allocated = 1 << 7,
};
enum : u64
{
    stack_guarded = 0x10, preallocated = 0x20,
    page_size_4k = 0x100, page_size_64k = 0x200, page_size_1m = 0x400,
    page_size_mask = 0xf00, alloc_hidden = 0x1000,
    alloc_unwritable = 0x2000, alloc_executable = 0x4000,
    alloc_prot_mask = alloc_hidden | alloc_unwritable | alloc_executable,
};

struct Page
{
    u8 raw = 0;
    explicit operator bool() const
    {
        assert(lock_depth == 1);
        ++page_reads;
        return raw != 0;
    }
    u8 exchange(u8 value)
    {
        assert(lock_depth == 1);
        event('G', raw, value);
        return std::exchange(raw, value);
    }
};

static std::array<Page, 1 << 20> g_pages;
static u8* g_sudo_addr = nullptr;

struct writer_lock
{
    writer_lock() { assert(lock_depth == 0); ++lock_depth; event('L', 1); }
    ~writer_lock() { assert(lock_depth == 1); event('L', 0); --lock_depth; }
};

struct block_t_base
{
    const u32 addr;
    const u32 size;
    const u64 flags;
    std::shared_ptr<utils::shm> m_common;
    mutable MapHolder m;
    bool valid = true;
    block_t_base(u32 a, u32 s, u64 f) : addr(a), size(s), flags(f) {}
    bool is_valid() const { assert(lock_depth == 1); return valid; }
};

// Only the member-container interface is substituted. This lets the exact
// production mirror callback compile in both versioned block_t classes.
using block_t = block_t_base;
static block_t* active_block = nullptr;

template<class FindMirror>
void _page_map(u32 addr, u8 flags, u32 size, utils::shm* shm, u64 bflags,
               FindMirror find_mirror)
{
    assert(lock_depth == 1);
    const auto* mirror = shm ? find_mirror(active_block, shm) : nullptr;
    event('M', addr, size, flags, bflags, shm ? shm->id : 0,
          mirror ? static_cast<u64>(mirror->first) + 1 : 0);
    const u64 end = static_cast<u64>(addr) + size;
    assert(end <= (u64{1} << 32));
    for (u64 page = addr / 4096; page < end / 4096; ++page)
    {
        assert(g_pages[page].raw == 0);
        g_pages[page].raw = flags | page_allocated;
    }
}
}

// PRODUCTION_ALLOCATORS

using namespace vm;

struct Interval
{
    u32 addr;
    u32 size;
    u64 shm_id = 0;
};

struct Case
{
    std::string name;
    explicit Case(std::string value) : name(std::move(value)) {}
    u32 base = 0x20000000;
    u32 block_size = 0x200000;
    u64 block_flags = page_size_4k | preallocated;
    u32 request_size = 0x1000;
    u32 alignment = 0x1000;
    u64 request_flags = 0;
    bool common = true;
    bool import = false;
    bool valid = true;
    std::vector<Interval> allocated;
    std::vector<Interval> foreign;
};

struct Oracle
{
    u32 addr = 0;
    int error = 0;
};

static std::vector<u8> initial_pages(const Case& c)
{
    assert(c.base % 4096 == 0 && c.block_size % 4096 == 0);
    assert(static_cast<u64>(c.base) + c.block_size <= (u64{1} << 32));
    std::vector<u8> pages(c.block_size / 4096);
    auto occupy = [&](const Interval& interval)
    {
        assert(interval.addr % 4096 == 0 && interval.size % 4096 == 0);
        assert(interval.addr >= c.base);
        assert(static_cast<u64>(interval.addr) + interval.size <= static_cast<u64>(c.base) + c.block_size);
        for (u64 i = (interval.addr - c.base) / 4096;
             i < (static_cast<u64>(interval.addr) - c.base + interval.size) / 4096; ++i)
        {
            assert(!pages[i]);
            pages[i] = page_allocated | page_readable;
        }
    };
    for (const auto& interval : c.allocated) occupy(interval);
    for (const auto& interval : c.foreign) occupy(interval);
    return pages;
}

// Independent first-fit oracle: scan the page bitmap at every aligned address.
// It neither consults the interval map nor shares the optimized search logic.
static Oracle oracle(const Case& c, const std::vector<u8>& pages)
{
    const u64 flags = c.import ? c.request_flags :
        (c.block_flags & ~alloc_prot_mask) | (c.request_flags & alloc_prot_mask);
    const u32 minimum = flags & page_size_4k ? 4096 : 65536;
    const u32 size = static_cast<u32>((static_cast<u64>(c.request_size) + minimum - 1) / minimum * minimum)
        + (flags & stack_guarded ? 8192u : 0u);
    if (c.alignment < minimum || !std::has_single_bit(c.alignment)) return {0, 1};
    if (!c.request_size || !size || c.request_size > size || size > c.block_size) return {};
    if (c.common && c.import) return {0, 2};
    const u32 last = static_cast<u32>(static_cast<u64>(c.base) + c.block_size - size)
        / c.alignment * c.alignment;
    const u32 first = static_cast<u32>((static_cast<u64>(c.base) + c.alignment - 1)
        / c.alignment * c.alignment);
    if (c.base > last || first > last || !c.valid) return {};
    for (u64 addr = first; addr <= last; addr += c.alignment)
    {
        bool vacant = true;
        for (u64 offset = addr - c.base; offset < addr - c.base + size; offset += 4096)
        {
            if (pages.at(offset / 4096))
            {
                vacant = false;
                break;
            }
        }
        if (vacant) return {static_cast<u32>(addr + (flags & stack_guarded ? 4096 : 0)), 0};
    }
    return {};
}

template<class Block>
static void prepare(Block& block, const Case& c, const std::vector<u8>& pages)
{
    record_events = false;
    assert(lock_depth == 0);
    for (usz i = 0; i < pages.size(); ++i)
        g_pages[c.base / 4096 + i].raw = pages[i];
    if (c.common) block.m_common = std::make_shared<utils::shm>(1);
    block.valid = c.valid;
    for (const auto& interval : c.allocated)
        block.m.allocations.emplace(interval.addr, std::make_pair(interval.size,
            interval.shm_id ? std::make_shared<utils::shm>(interval.shm_id) : nullptr));
    active_block = &block;
    page_reads = 0;
    events.clear();
    next_shm_id = 1000;
}

struct Outcome
{
    u32 addr = 0;
    int error = 0;
    std::vector<Event> events;
    std::vector<u8> pages;
    std::vector<std::tuple<u32, u32, u64>> allocations;
    std::vector<u64> guards;
    long import_refs = 0;
    u64 reads = 0;
};

template<class Block>
static Outcome execute(const Case& c, const std::vector<u8>& pages)
{
    Block block(c.base, c.block_size, c.block_flags);
    prepare(block, c, pages);
    std::shared_ptr<utils::shm> imported = c.import ? std::make_shared<utils::shm>(777) : nullptr;
    Outcome result;
    record_events = true;
    try
    {
        result.addr = block.alloc(c.request_size, c.import ? &imported : nullptr,
                                  c.alignment, c.request_flags);
    }
    catch (const std::invalid_argument&) { result.error = 1; }
    catch (const std::logic_error&) { result.error = 2; }
    record_events = false;
    assert(lock_depth == 0);
    result.events = events;
    result.reads = page_reads;
    result.import_refs = imported.use_count();
    for (usz i = 0; i < pages.size(); ++i)
        result.pages.push_back(g_pages[c.base / 4096 + i].raw);
    for (const auto& [addr, allocation] : block.m.allocations)
        result.allocations.emplace_back(addr, allocation.first,
                                         allocation.second ? allocation.second->id : 0);
    if (result.addr && c.block_flags & stack_guarded)
    {
        const auto& allocation = block.m.allocations.at(result.addr - 4096);
        for (usz i = 0; i < 512; ++i)
        {
            u64 first, last;
            std::memcpy(&first, g_sudo_addr + result.addr - 4096 + i * 8, 8);
            std::memcpy(&last, g_sudo_addr + result.addr - 4096 + allocation.first - 4096 + i * 8, 8);
            assert(first == "STACKGRD"_u64 && last == "UNDERFLO"_u64);
            result.guards.push_back(first);
            result.guards.push_back(last);
        }
    }
    active_block = nullptr;
    return result;
}

static u64 case_count = 0;
static u64 reads_before = 0;
static u64 reads_after = 0;

static std::pair<u64, u64> check(const Case& c, bool print = false)
{
    const auto pages = initial_pages(c);
    const Oracle expected = oracle(c, pages);
    const Outcome old = execute<before::block_t>(c, pages);
    const Outcome now = execute<after::block_t>(c, pages);
    if (old.addr != expected.addr || old.error != expected.error ||
        now.addr != old.addr || now.error != old.error || now.events != old.events ||
        now.pages != old.pages || now.allocations != old.allocations ||
        now.guards != old.guards || now.import_refs != old.import_refs || now.reads > old.reads)
    {
        std::cerr << "FAIL: " << c.name << " result " << old.addr << '/' << now.addr
                  << '/' << expected.addr << " error " << old.error << '/' << now.error
                  << '/' << expected.error << " reads " << old.reads << '/' << now.reads << '\n';
        std::abort();
    }
    ++case_count;
    reads_before += old.reads;
    reads_after += now.reads;
    if (print)
        std::cout << c.name << ": page reads " << old.reads << " -> " << now.reads
                  << ", first-fit address " << now.addr << '\n';
    return {old.reads, now.reads};
}

static Case occupied_prefix()
{
    Case c{"128MiB-prefix"};
    c.block_size = 256u << 20;
    c.request_size = 65536;
    c.allocated.push_back({c.base, 128u << 20});
    return c;
}

static void directed_tests()
{
    Case c{"first-probe-empty"};
    assert((check(c, true) == std::pair<u64, u64>{1, 1}));
    c.request_size = 65536;
    assert((check(c, true) == std::pair<u64, u64>{16, 16}));
    c = occupied_prefix();
    assert((check(c, true) == std::pair<u64, u64>{32784, 17}));

    c = Case{"foreign-pages-only"};
    c.request_size = 8192;
    c.foreign = {{c.base + 4096, 4096}, {c.base + 16384, 65536}};
    assert((check(c, true) == std::pair<u64, u64>{5, 5}));
    c.name = "mixed-map-and-foreign";
    c.allocated = {{c.base + 8192, 8192}};
    check(c, true);

    c = Case{"dense-mixed-map-keeps-original-scan"};
    c.block_size = 8u << 20;
    c.request_size = 65536;
    c.alignment = 65536;
    c.allocated = {{c.base, 1048576}};
    for (u32 i = 0; i < 128; ++i)
        c.allocated.push_back({c.base + 1048576 + i * 4096, 4096});
    const auto dense_reads = check(c, true);
    assert(dense_reads.first == dense_reads.second);

    c = Case{"dense-map-2GiB-alignment"};
    c.base = 0;
    c.block_size = 0xfffff000;
    c.alignment = 0x80000000;
    c.allocated = {{0, 4096}};
    check(c, true);

    c = Case{"guards"};
    c.block_flags |= stack_guarded;
    c.request_size = 8000;
    c.allocated = {{c.base, 32768}, {c.base + 65536, 16384}};
    check(c, true);
    c.block_size = 49152;
    c.allocated.resize(1);
    check(c);

    c = Case{"last-page-at-4GiB"};
    c.base = 0xffff0000;
    c.block_size = 65536;
    c.allocated = {{c.base, 61440}};
    check(c, true);
    c.name = "skip-past-4GiB";
    c.allocated[0].size = 65536;
    check(c, true);
    c.name = "aligned-overflow-at-4GiB";
    c.alignment = 0x80000000u;
    check(c);
    c = Case{"aligned-end-exceeds-max"};
    c.base += 4096;
    c.block_size = 65536;
    c.alignment = 65536;
    c.allocated = {{c.base, 65536}};
    check(c);

    c = Case{"map-interval-before-first-aligned-candidate"};
    c.base += 4096;
    c.alignment = 65536;
    c.allocated = {{c.base, 131072}, {c.base + 196608, 4096}};
    check(c);
    c.name = "first-fit-exact-gap";
    c.request_size = 65536;
    c.alignment = 4096;
    c.allocated = {{c.base, 4096}, {c.base + 69632, 8192}};
    check(c);
    c.name = "first-fit-gap-one-page-short";
    c.allocated[1].addr -= 4096;
    check(c);
    c.name = "whole-block-full";
    c.allocated = {{c.base, c.block_size}};
    check(c);

    for (u32 alignment : {65536u, 1048576u})
    {
        c = Case{"large-jump-over-small-map-entries"};
        c.block_size = 8u << 20;
        c.alignment = alignment;
        c.request_size = alignment;
        const u32 prefix = 2 * alignment + 4096;
        c.allocated = {{c.base, prefix}};
        for (u32 i = 0; i < 256; ++i)
            c.allocated.push_back({c.base + prefix + i * 4096, 4096});
        check(c);
    }

    for (u64 page_flags : {static_cast<u64>(page_size_64k), static_cast<u64>(page_size_1m)})
    {
        for (u64 protection = 0; protection < 8; ++protection)
        {
            c = Case{"page-flags-and-protection"};
            c.block_flags = page_flags;
            c.request_flags = protection << 12;
            c.alignment = 65536;
            c.common = false;
            c.allocated = {{c.base, 131072, 2}};
            check(c);
            c.name = "import-shm";
            c.import = true;
            c.request_flags |= page_flags;
            check(c);
        }
    }
    c = Case{"common-and-import-rejected"};
    c.import = true;
    c.request_flags = page_size_4k;
    check(c);
    c = Case{"expired-block-preserves-shm-before-lock"};
    c.block_flags = page_size_64k;
    c.alignment = 65536;
    c.common = false;
    c.valid = false;
    check(c);
    auto outcome = execute<after::block_t>(c, initial_pages(c));
    assert(outcome.events.size() == 3 && outcome.events[0].kind == 'C' &&
           outcome.events[1].kind == 'L' && outcome.events[2].kind == 'L');

    for (u32 request : {0u, 1u, 0xfffffff0u, 0xffffffffu, 0x300000u})
    {
        c = Case{"invalid-size-or-rounded-size"};
        c.request_size = request;
        check(c);
        c.block_flags |= stack_guarded;
        check(c);
    }
    for (u32 alignment : {0u, 1u, 4095u, 12288u, 65535u})
    {
        c = Case{"invalid-alignment-before-size"};
        c.alignment = alignment;
        c.request_size = 0;
        check(c);
    }
}

static void randomized_tests()
{
    std::mt19937_64 random(0x766d616c6c6f63);
    for (u32 trial = 0; trial < 20000; ++trial)
    {
        Case c{"random-" + std::to_string(trial)};
        const u32 pages = 32 + random() % 481;
        c.block_size = pages * 4096;
        c.base = trial % 4 ? 0x20000000u + static_cast<u32>(random() % 32) * 4096
                           : static_cast<u32>((u64{1} << 32) - c.block_size);
        c.request_size = 1 + random() % (96 * 4096);
        c.alignment = 4096u << (random() % 7);
        c.request_flags = (random() % 8) << 12;
        if (trial % 7 == 0) c.block_flags |= stack_guarded;
        if (trial % 11 == 0)
        {
            c.block_flags = trial % 2 ? page_size_64k : page_size_1m;
            c.common = false;
            c.alignment = 65536u << (random() % 4);
            c.import = trial % 3 == 0;
            if (c.import) c.request_flags |= c.block_flags;
        }
        c.valid = trial % 97 != 0;
        for (u32 page = 0; page < pages;)
        {
            const u32 span = std::min<u32>(1 + random() % 24, pages - page);
            switch (random() % 4)
            {
            case 0: c.foreign.push_back({c.base + page * 4096, span * 4096}); break;
            case 1:
            case 2: c.allocated.push_back({c.base + page * 4096, span * 4096, c.common ? 0u : 2u}); break;
            default: break;
            }
            page += span;
        }
        check(c);
    }
}

template<class Block>
static double timed(const Case& c, u32 repetitions)
{
    const auto pages = initial_pages(c);
    const u32 expected = oracle(c, pages).addr;
    assert(expected && !(c.block_flags & stack_guarded));
    Block block(c.base, c.block_size, c.block_flags);
    prepare(block, c, pages);
    std::array<double, 5> samples;
    for (auto& sample : samples)
    {
        const auto begin = std::chrono::steady_clock::now();
        for (u32 i = 0; i < repetitions; ++i)
        {
            const auto result = block.alloc(c.request_size, nullptr, c.alignment, c.request_flags);
            assert(result == expected);
            auto it = block.m.allocations.find(result);
            assert(it != block.m.allocations.end());
            for (u64 page = result / 4096;
                 page < (static_cast<u64>(result) + it->second.first) / 4096; ++page)
                g_pages[page].raw = 0;
            block.m.allocations.erase(it);
        }
        sample = std::chrono::duration<double, std::nano>(std::chrono::steady_clock::now() - begin).count() / repetitions;
    }
    std::sort(samples.begin(), samples.end());
    return samples[2];
}

static void benchmarks()
{
    Case empty{"first-probe-empty"};
    Case prefix = occupied_prefix();
    Case future{"first-probe-before-2048-map-entries"};
    future.block_size = 32u << 20;
    for (u32 i = 1; i <= 2048; ++i)
        future.allocated.push_back({future.base + i * 8192, 4096});
    Case fragmented{"2048-occupied-islands"};
    fragmented.block_size = 256u << 20;
    fragmented.request_size = 65536;
    for (u32 i = 0; i < 2048; ++i)
        fragmented.allocated.push_back({fragmented.base + i * 131072, 114688});
    fragmented.block_size += 65536;
    for (const Case* c : {&empty, &future, &prefix, &fragmented})
    {
        const u32 repetitions = c == &empty || c == &future ? 20000 : 200;
        const double old = timed<before::block_t>(*c, repetitions);
        const double now = timed<after::block_t>(*c, repetitions);
        std::cout << "Synthetic host median ns/alloc+reset, " << c->name << ": "
                  << old << " -> " << now << " (" << repetitions << " iterations/sample)\n";
    }
}

static void dense_benchmarks()
{
    for (u32 span : {4096u, 8192u, 16384u, 65536u})
    {
        for (u32 alignment : {4096u, 65536u, 1048576u})
        {
            Case c{"dense-interval-" + std::to_string(span) + "-align-" + std::to_string(alignment)};
            c.block_size = 256u << 20;
            c.request_size = alignment;
            c.alignment = alignment;
            for (u32 i = 0; i < 2048; ++i)
                c.allocated.push_back({c.base + i * span, span});
            check(c);
            const double old = timed<before::block_t>(c, 400);
            const double now = timed<after::block_t>(c, 400);
            std::cout << "Dense host median ns/alloc+reset, " << c.name << ": "
                      << old << " -> " << now << '\n';
        }
    }
}

int main(int argc, char** argv)
{
    // Sparse virtual space only; guard tests commit the two pages they fill.
    constexpr usz space = usz{1} << 32;
    void* memory = mmap(nullptr, space, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(memory != MAP_FAILED);
    g_sudo_addr = static_cast<u8*>(memory);
    if (argc > 1 && std::string(argv[1]) == "dense")
    {
        dense_benchmarks();
    }
    else
    {
        directed_tests();
        randomized_tests();
        std::cout << "PASS " << case_count << " exact-first-fit cases; identical mapping/constructor/lock events, "
                     "protection bytes, shared-memory ownership and guards. Page reads: "
                  << reads_before << " -> " << reads_after << '\n';
        if (argc > 1)
        {
            benchmarks();
            dense_benchmarks();
        }
    }
    assert(munmap(memory, space) == 0);
}
