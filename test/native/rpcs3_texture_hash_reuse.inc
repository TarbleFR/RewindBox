// Host observations around the unmodified production range_hash. These do not
// exist in the core. The worker pause makes the duplicate-work case deterministic.
#include <array>
#include <iomanip>
#include <iostream>
#include <string>

namespace hash_reuse_probe
{
inline std::atomic<u64> hashes{0}, bytes{0};
inline bool observe = true; // changed only with the worker stopped
inline std::atomic<bool> advance_after_hash{false};
inline std::atomic<u32> paused_start{0};
inline std::atomic<bool> entered{false}, resume{false};
}

namespace rpcs3::ios::texture_prehash
{
u64 observed_range_hash(const void* src, u32 length) noexcept
{
    const auto paused = hash_reuse_probe::paused_start.load(std::memory_order_relaxed);
    if (paused && src == vm::g_sudo_addr + paused)
    {
        hash_reuse_probe::entered.store(true, std::memory_order_release);
        while (!hash_reuse_probe::resume.load(std::memory_order_acquire)) std::this_thread::yield();
    }
    if (hash_reuse_probe::observe)
    {
        hash_reuse_probe::hashes.fetch_add(1, std::memory_order_relaxed);
        hash_reuse_probe::bytes.fetch_add(length, std::memory_order_relaxed);
    }
    const auto result = range_hash(src, length);
    if (hash_reuse_probe::advance_after_hash.exchange(false, std::memory_order_relaxed))
        texture_validation::advance_epoch();
    return result;
}
}

// @CASES@
namespace
{
using section = rsx::after::buffered_section;
constexpr u32 base = rsx::constants::local_mem_base;
constexpr u32 length = 64u << 10;
constexpr u32 arena_size = 64u << 20;

void fill(u32 start, u32 size, u32 seed)
{
    for (u32 offset = 0; offset < size; ++offset)
        vm::g_sudo_addr[start + offset] = static_cast<u8>((offset * 17u + seed) ^ (offset >> 8));
}

void clear_slots()
{
    for (auto& slot : tp::table)
    {
        slot.seq = 0;
        slot.key = 0;
        slot.epoch = 0;
        slot.hash = 0;
    }
}

void fresh(bool enable = true, bool epochs = true)
{
    tp::stop();
    clear_slots();
    tv::epoch_enabled = epochs;
    tv::validation_epoch.fetch_add(10000, std::memory_order_relaxed);
    tp::enabled = enable;
}

template <typename Predicate>
void wait_until(Predicate condition)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (!condition())
    {
        ensure(std::chrono::steady_clock::now() < deadline);
        std::this_thread::yield();
    }
}

struct results
{
    u64 repeated_hashes = 0, repeated_bytes = 0, distinct_hashes = 0;
    u64 overlap_write_hashes = 0, overlap_changed = 0;
    u64 worker_hashes = 0, worker_bytes = 0, synchronous_hashes = 0;
    u64 stress_hits = 0;
};

void repeated_and_distinct(results& out)
{
    fresh();
    std::vector<section> aliases;
    for (unsigned i = 0; i < 8; ++i)
    {
        aliases.emplace_back(base, length);
        aliases.back().protect(utils::protection::ro);
    }
    const u64 h0 = hash_reuse_probe::hashes, b0 = hash_reuse_probe::bytes;
    for (unsigned epoch = 0; epoch < 12; ++epoch)
    {
        tv::advance_epoch();
        for (auto& s : aliases) ensure(s.sync());
    }
    tp::stop();
    out.repeated_hashes = hash_reuse_probe::hashes - h0;
    out.repeated_bytes = hash_reuse_probe::bytes - b0;
    ensure(out.repeated_hashes == (HASH_REUSE_CANDIDATE ? 12 : 96));
    ensure(out.repeated_bytes == out.repeated_hashes * length);

    fresh();
    aliases.clear();
    for (unsigned i = 0; i < 32; ++i)
    {
        aliases.emplace_back(base + i * length, length);
        aliases.back().protect(utils::protection::ro);
    }
    const u64 h1 = hash_reuse_probe::hashes;
    tv::advance_epoch();
    for (auto& s : aliases) ensure(s.sync());
    tp::stop();
    out.distinct_hashes = hash_reuse_probe::hashes - h1;
    ensure(out.distinct_hashes == 32);
}

void overlap_and_reset(results& out)
{
    fresh();
    section a(base, 2 * length), b(base, 2 * length);
    section c(base + length / 2, length), untouched(base + 3 * length, length);
    for (auto* s : {&a, &b, &c, &untouched}) s->protect(utils::protection::ro);
    tv::advance_epoch();
    for (auto* s : {&a, &b, &c, &untouched}) ensure(s->sync());
    const auto old_hash = a.mem_hash;
    fill(base + length, 4096, 201);
    // The production scoped writer applies reset_validation to every overlap.
    // Here the mapping/overlap notification is an explicit host stimulus.
    for (auto* s : {&a, &b, &c}) s->reset_validation();
    tp::publish(base, 2 * length, tv::current_epoch(), old_hash);
    for (auto* pointer : {&a, &b, &c})
    {
        auto& s = *pointer;
        const auto h0 = hash_reuse_probe::hashes.load();
        ensure(!s.sync());
        out.overlap_write_hashes += hash_reuse_probe::hashes - h0;
        ++out.overlap_changed;
        // A mismatch is discarded before that section can be sampled again,
        // exactly as sync_protection requires. Its reupload gets a fresh hash.
        s.discard();
        s.protect(utils::protection::ro);
        ensure(s.sync());
        // A worker which started before the write publishes late in this same
        // epoch. Other overlapping sections must still reject that old hash.
        tp::publish(base, 2 * length, tv::current_epoch(), old_hash);
    }
    const u64 before_untouched = hash_reuse_probe::hashes;
    ensure(untouched.sync());
    ensure(hash_reuse_probe::hashes == before_untouched);
    ensure(out.overlap_write_hashes == 3 && out.overlap_changed == 3);

    // Reuse a slot for a different range. The actual reset discards its old
    // validation/bypass state, and protect hashes its new contents itself.
    a.discard();
    a.reset_validation();
    a.reset(rsx::address_range32::start_length(base + (4u << 20), length));
    ensure(!a.validated_epoch && !a.prehash_bypass);
    a.protect(utils::protection::ro);
    tv::advance_epoch();
    ensure(a.sync());
    ensure(a.mem_hash == tp::range_hash(vm::g_sudo_addr + a.cpu_range.start, length));
    tp::stop();

    // Two different full section ranges can confirm exactly the same subrange.
    fresh();
    section x(base, 4 * length), y(base + length / 2, 3 * length);
    x.confirmed_range = y.confirmed_range = rsx::address_range32::start_length(base + length, length);
    x.protect(utils::protection::ro);
    y.protect(utils::protection::ro);
    const u64 h0 = hash_reuse_probe::hashes;
    tv::advance_epoch();
    ensure(x.sync() && y.sync());
    ensure(hash_reuse_probe::hashes - h0 == (HASH_REUSE_CANDIDATE ? 1 : 2));
    tp::stop();
}

void epoch_and_controls()
{
    fresh();
    section s(base, length);
    s.protect(utils::protection::ro);
    tv::advance_epoch();
    const auto old_epoch = tv::current_epoch();
    hash_reuse_probe::advance_after_hash = true;
    ensure(s.sync());
    ensure(s.validated_epoch == old_epoch && tv::current_epoch() != old_epoch);
    u64 out = 0;
    ensure(!tp::lookup(base, length, old_epoch, out));
    ensure(!tp::lookup(base, length, tv::current_epoch(), out));
    const u64 h0 = hash_reuse_probe::hashes;
    ensure(s.sync());
    ensure(hash_reuse_probe::hashes == h0 + 1);
    const auto new_epoch = tv::current_epoch();
    tp::publish(base, length, new_epoch, s.mem_hash);
    // Delayed old-epoch publishers may evict new results; they cannot certify
    // the newer epoch. A miss safely invokes the normal hash again.
    tp::publish(base, length, old_epoch, s.mem_hash ^ 1);
    ensure(!tp::lookup(base, length, new_epoch, out));
    s.validated_epoch = 0;
    ensure(s.sync());
    tp::stop();

    // The three existing controls stay independent: worker disabled, epoch
    // disabled and range below the prehash threshold all hash on demand.
    for (unsigned control = 0; control < 3; ++control)
    {
        fresh(control != 0, control != 1);
        const u32 size = control == 2 ? length / 2 : length;
        section a(base, size);
        a.protect(utils::protection::ro);
        const auto before = hash_reuse_probe::hashes.load();
        for (unsigned i = 0; i < 7; ++i)
        {
            a.validated_epoch = 0;
            ensure(a.sync());
        }
        ensure(hash_reuse_probe::hashes == before + 7);
        ensure(!tp::lookup(base, size, tv::current_epoch(), out));
        tp::stop();
    }
}

std::array<u32, 64> collision_addresses()
{
    std::array<u32, 64> addresses{};
    const auto slot = tp::slot_of(tp::make_key(0xffff0000u, length));
    addresses[0] = 0xffff0000u;
    unsigned n = 1;
    for (u32 address = 1; n < addresses.size(); ++address)
        if (tp::slot_of(tp::make_key(address, length)) == slot) addresses[n++] = address;
    return addresses;
}

u64 stamp(u32 address, u64 epoch)
{
    return (tp::make_key(address, length) * 0xd6e8feb86659fd93ull) ^ (epoch * 0x9e3779b97f4a7c15ull);
}

void slots_and_concurrency(results& out)
{
    fresh(false);
    const auto addresses = collision_addresses();
    for (unsigned i = 0; i < addresses.size(); ++i)
    {
        tp::publish(addresses[i], length, 55, stamp(addresses[i], 55));
        u64 value = 0;
        ensure(tp::lookup(addresses[i], length, 55, value));
        ensure(value == stamp(addresses[i], 55));
        if (i) ensure(!tp::lookup(addresses[i - 1], length, 55, value));
        ensure(!tp::lookup(addresses[i], length + 1, 55, value));
        ensure(!tp::lookup(addresses[i], length, 56, value));
    }
#if HASH_REUSE_CANDIDATE
    auto& slot = tp::table[tp::slot_of(tp::make_key(addresses[0], length))];
    slot.seq = 99;
    slot.key = 123;
    slot.epoch = 456;
    slot.hash = 789;
    const auto seq = slot.seq.load();
    tp::publish(addresses[0], length, 60, stamp(addresses[0], 60));
    ensure(slot.seq.load() == seq);
    ensure(slot.key == 123 && slot.epoch == 456 && slot.hash == 789);
#endif
    clear_slots();
    std::atomic<bool> begin{false};
    std::atomic<unsigned> ready{0};
    std::atomic<u64> hits{0};
    const unsigned writers = HASH_REUSE_CANDIDATE ? 2 : 1;
    std::vector<std::thread> threads;
    for (unsigned writer = 0; writer < writers; ++writer)
    {
        threads.emplace_back([&, writer]
        {
            ++ready;
            while (!begin.load(std::memory_order_acquire)) std::this_thread::yield();
            for (unsigned i = 0; i < 250000; ++i)
            {
                const auto address = addresses[(i * 13u + writer * 7u) % addresses.size()];
                const u64 epoch = 1 + i % 31;
                tp::publish(address, length, epoch, stamp(address, epoch));
            }
        });
    }
    for (unsigned reader = 0; reader < 2; ++reader)
    {
        threads.emplace_back([&, reader]
        {
            ++ready;
            while (!begin.load(std::memory_order_acquire)) std::this_thread::yield();
            for (unsigned i = 0; i < 250000; ++i)
            {
                const auto address = addresses[(i * 13u + reader * 7u) % addresses.size()];
                const u64 epoch = 1 + i % 31;
                u64 value = 0;
                if (tp::lookup(address, length, epoch, value))
                {
                    ensure(value == stamp(address, epoch));
                    hits.fetch_add(1, std::memory_order_relaxed);
                }
            }
        });
    }
    wait_until([&] { return ready.load() == writers + 2; });
    begin.store(true, std::memory_order_release);
    for (auto& thread : threads) thread.join();
    out.stress_hits = hits;
    for (const auto& slot : tp::table) ensure(!(slot.seq.load() & 1));
}

void actual_worker_reuse(results& out)
{
    fresh();
    constexpr u32 gate = base + (12u << 20), target = base + (16u << 20), sentinel = base + (20u << 20);
    ensure(tp::slot_of(tp::make_key(gate, length)) != tp::slot_of(tp::make_key(target, length)));
    ensure(tp::slot_of(tp::make_key(sentinel, length)) != tp::slot_of(tp::make_key(target, length)));
    section s(target, length);
    s.protect(utils::protection::ro);
    // Establish a frame origin. The dummy's very large original ordinal cannot
    // enter the worker's first prediction batch.
    tp::record(sentinel, length);
    tv::advance_epoch();
    tp::end_frame();
    tp::record(gate, length);
    tp::record(target, length);
    tp::record(sentinel, length);
    hash_reuse_probe::entered = false;
    hash_reuse_probe::resume = false;
    hash_reuse_probe::paused_start = gate;
    const auto hashes0 = tp::worker_hashes.load(), bytes0 = tp::worker_bytes.load();
    tv::advance_epoch();
    tp::end_frame();
    wait_until([] { return hash_reuse_probe::entered.load(std::memory_order_acquire); });
    const auto before = hash_reuse_probe::hashes.load();
    ensure(s.sync()); // the real RSX fallback publishes before the worker reaches target
    out.synchronous_hashes = hash_reuse_probe::hashes - before;
    ensure(out.synchronous_hashes == 1);
    hash_reuse_probe::resume.store(true, std::memory_order_release);
    wait_until([&]
    {
        u64 hash = 0;
        return tp::lookup(sentinel, length, tv::current_epoch(), hash);
    });
    tp::stop();
    hash_reuse_probe::paused_start = 0;
    out.worker_hashes = tp::worker_hashes - hashes0;
    out.worker_bytes = tp::worker_bytes - bytes0;
    ensure(out.worker_hashes == (HASH_REUSE_CANDIDATE ? 2 : 3));
    ensure(out.worker_bytes == out.worker_hashes * length);
    ensure(vm::g_range_lock_bits[0].load() == 0);
}

void benchmark()
{
    // The observer is disabled. The real worker still exists, but its previous
    // frame is empty; no speculation or guest writes races these timing series.
    tp::stop();
    hash_reuse_probe::observe = false;
    std::cout << ",\"benchmarks\":[";
    bool first = true;
    for (u32 size : {32768u, 65536u, 262144u, 1048576u, 3686400u})
    {
        for (unsigned kind = 0; kind < 3; ++kind)
        {
            fresh();
            std::vector<section> sections;
            for (unsigned i = 0; i < 8; ++i)
            {
                sections.emplace_back(base + (kind == 1 ? i * size : 0), size);
                sections.back().protect(utils::protection::ro);
            }
            const unsigned iterations = std::max(4u, std::min(128u, (16u << 20) / (8 * size)));
            std::array<double, 7> samples{};
            for (auto& sample : samples)
            {
                const auto start = std::chrono::steady_clock::now();
                for (unsigned round = 0; round < iterations; ++round)
                {
                    // Same epoch transition observed by sync; notification is
                    // omitted only to avoid timing scheduler wake-up jitter.
                    tv::validation_epoch.fetch_add(1, std::memory_order_release);
                    for (auto& s : sections)
                    {
                        if (kind == 2) s.reset_validation();
                        ensure(s.sync());
                    }
                }
                const auto elapsed = std::chrono::steady_clock::now() - start;
                sample = std::chrono::duration<double, std::nano>(elapsed).count() / (8 * iterations);
            }
            tp::stop();
            auto ordered = samples;
            std::sort(ordered.begin(), ordered.end());
            if (!first) std::cout << ',';
            first = false;
            std::cout << "{\"bytes\":" << size << ",\"sections\":8,\"pattern\":\""
                      << (kind == 0 ? "identical" : kind == 1 ? "distinct" : "scoped_bypass")
                      << "\",\"iterationsPerSeries\":" << iterations << ",\"medianNsPerValidation\":" << ordered[3]
                      << ",\"seriesNsPerValidation\":[";
            for (unsigned i = 0; i < samples.size(); ++i) std::cout << (i ? "," : "") << samples[i];
            std::cout << "]}";
        }
    }
    std::cout << ']';
    hash_reuse_probe::observe = true;
}
}

int main(int argc, char** argv)
{
    constexpr u64 reservation = u64{base} + arena_size;
    auto* memory = mmap(nullptr, reservation, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    ensure(memory != MAP_FAILED);
    vm::g_sudo_addr = static_cast<u8*>(memory);
    ensure(mprotect(vm::g_sudo_addr + base, arena_size, PROT_READ | PROT_WRITE) == 0);
    fill(base, arena_size, 31);
    results r;
    repeated_and_distinct(r);
    overlap_and_reset(r);
    epoch_and_controls();
    slots_and_concurrency(r);
    actual_worker_reuse(r);
    std::cout << std::setprecision(10)
              << "{\"passed\":true,\"candidate\":" << (HASH_REUSE_CANDIDATE ? "true" : "false")
              << ",\"repeatedQueries\":96,\"repeatedHashes\":" << r.repeated_hashes
              << ",\"repeatedBytes\":" << r.repeated_bytes
              << ",\"distinctQueries\":32,\"distinctHashes\":" << r.distinct_hashes
              << ",\"overlapWriteHashes\":" << r.overlap_write_hashes
              << ",\"overlapChangedRejected\":" << r.overlap_changed
              << ",\"confirmedRangeReuse\":true,\"cacheReset\":true,\"oldWorkerAfterScopedWrite\":true"
              << ",\"epochDuringHash\":true,\"oldPublisherAfterNewEpoch\":true,\"disabledControls\":true"
              << ",\"collisionChecks\":64,\"heldSlotNoWait\":" << (HASH_REUSE_CANDIDATE ? "true" : "false")
              << ",\"stressWrites\":" << (HASH_REUSE_CANDIDATE ? 500000 : 250000)
              << ",\"stressReads\":500000,\"stressAcceptedMatches\":" << r.stress_hits
              << ",\"multiWriterTested\":" << (HASH_REUSE_CANDIDATE ? "true" : "false")
              << ",\"workerPredictionHashes\":" << r.worker_hashes
              << ",\"workerPredictionBytes\":" << r.worker_bytes
              << ",\"workerSynchronousHashes\":" << r.synchronous_hashes
              << ",\"guestMemoryMappingModeled\":true,\"gpuExecuted\":false";
    if (argc == 2 && std::string(argv[1]) == "--benchmark") benchmark();
    else ensure(argc == 1);
    std::cout << "}\n";
    tp::stop();
    ensure(munmap(memory, reservation) == 0);
}
