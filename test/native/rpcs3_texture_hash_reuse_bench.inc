// Separate timing program: only the newly changed hash-reuse path runs.
// The real worker is parked by atomic::wait inside the host hash adapter.
namespace
{
using section = rsx::after::buffered_section;
constexpr u32 base = rsx::constants::local_mem_base;
constexpr u32 length = 64u << 10;
constexpr u32 arena_size = 64u << 20;
constexpr u32 gate = base + (60u << 20);

template <typename Predicate>
void wait_until(Predicate ready)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (!ready())
    {
        ensure(std::chrono::steady_clock::now() < deadline);
        std::this_thread::yield();
    }
}
}

int main(int argc, char** argv)
{
    ensure(argc == 3);
    const u32 size = static_cast<u32>(std::stoul(argv[1]));
    const u32 kind = static_cast<u32>(std::stoul(argv[2]));
    ensure(size && u64{size} * 8 < gate - base && kind < 3);
    constexpr u64 reservation = u64{base} + arena_size;
    auto* memory = mmap(nullptr, reservation, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    ensure(memory != MAP_FAILED);
    vm::g_sudo_addr = static_cast<u8*>(memory);
    ensure(mprotect(vm::g_sudo_addr + base, arena_size, PROT_READ | PROT_WRITE) == 0);
    std::memset(vm::g_sudo_addr + base, 0x53, size * 8);
    std::memset(vm::g_sudo_addr + gate, 0x59, length);
    tv::epoch_enabled = true;
    tv::validation_epoch = 10000;
    tp::enabled = true;

    // Prime a single worker prediction, then park it before any byte is hashed.
    tp::record(gate, length);
    tv::advance_epoch();
    tp::end_frame();
    tp::record(gate, length);
    hash_reuse_probe::paused_start = gate;
    tv::advance_epoch();
    tp::end_frame();
    wait_until([] { return hash_reuse_probe::entered.load(std::memory_order_acquire); });
    {
        std::lock_guard lock(tp::g_mutex);
        tp::g_current.reserve(tp::max_sequence);
    }
    std::vector<section> sections;
    for (unsigned i = 0; i < 8; ++i)
    {
        sections.emplace_back(base + (kind == 1 ? i * size : 0), size);
        sections.back().protect(utils::protection::ro);
    }
    auto epoch = [&]
    {
        tv::validation_epoch.fetch_add(1, std::memory_order_release);
        for (auto& s : sections)
        {
            if (kind == 2) s.reset_validation();
            ensure(s.sync());
        }
    };
    for (unsigned warmup = 0; warmup < 4; ++warmup) epoch();
    const auto worker_before = tp::worker_hashes.load();
    const unsigned iterations = std::max(8u, (128u << 20) / (8u * size));
    const auto begin = std::chrono::steady_clock::now();
    for (unsigned i = 0; i < iterations; ++i) epoch();
    const auto elapsed = std::chrono::steady_clock::now() - begin;
    const u64 worker_work = tp::worker_hashes - worker_before;
    ensure(worker_work == 0);
    const double ns = std::chrono::duration<double, std::nano>(elapsed).count() / (iterations * 8);
    hash_reuse_probe::resume.store(true, std::memory_order_release);
    hash_reuse_probe::resume.notify_one();
    tp::stop();
    std::cout << std::setprecision(12) << "{\"passed\":true,\"iterations\":" << iterations
              << ",\"workerHashesDuringTiming\":" << worker_work
              << ",\"nsPerValidation\":" << ns << "}\n";
    ensure(munmap(memory, reservation) == 0);
}
