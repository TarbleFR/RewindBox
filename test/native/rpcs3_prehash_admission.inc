// Added to the 581 production-code VM model. Every worker/validation function
// above comes from the supplied source tree, not an implementation in this test.
namespace
{
constexpr u32 rewritten_size = 1280u * 720u * 4u;
constexpr u32 sentinel_size = 64u << 10;
constexpr u32 rewritten_start = rsx::constants::local_mem_base;
constexpr u32 sentinel_start = rsx::constants::local_mem_base + (8u << 20);
constexpr u32 sentinel2_start = rsx::constants::local_mem_base + (10u << 20);

void wait_hash(u32 start, u32 size, u64 epoch)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    u64 value = 0;
    while (!tp::lookup(start, size, epoch, value))
    {
        CELL581_REQUIRE(std::chrono::steady_clock::now() < deadline);
        std::this_thread::sleep_for(std::chrono::microseconds(50));
    }
    CELL581_REQUIRE(value == tp::range_hash(vm::g_sudo_addr + start, size));
}

void record_eligibility(u32 start, u32 size, bool eligible)
{
#if ADMISSION_CANDIDATE
    tp::record(start, size, eligible);
#else
    static_cast<void>(eligible);
    tp::record(start, size);
#endif
}

void begin_prediction_session()
{
    tp::stop();
    tp::enabled = true;
    // Start the real worker, then establish the first frame epoch just as the
    // texture cache does. The previous dummy has a later ordinal and cannot
    // run before the test's first frame end. Keep both real sequence slots.
    tp::record(sentinel_start, sentinel_size);
    tv::advance_epoch();
    tp::end_frame();
}

void next_prediction_frame()
{
    tv::advance_epoch();
    tp::end_frame();
}

void reject_stale_results()
{
    tp::stop();
    tp::enabled = true;
    section a(rewritten_start, sentinel_size);
    fill(rewritten_start, sentinel_size, 71);
    a.protect(utils::protection::ro);
    tp::publish(rewritten_start, sentinel_size, tv::current_epoch(), a.mem_hash);
    fill(rewritten_start, sentinel_size, 72);
    tv::advance_epoch();
    // A published hash from the preceding epoch is not a valid confirmation.
    CELL581_REQUIRE(!a.sync());
    tp::stop();

    tp::enabled = true;
    a.discard();
    a.protect(utils::protection::ro);
    tp::publish(rewritten_start, sentinel_size, tv::current_epoch(), a.mem_hash);
    fill(rewritten_start, sentinel_size, 73);
    a.reset_validation();
    // An RSX write invalidates even a result carrying the current epoch.
    CELL581_REQUIRE(!a.sync());
    tp::stop();
}

void mixed_requests()
{
    fill(rewritten_start, rewritten_size, 91);
    fill(sentinel_start, sentinel_size, 92);
    fill(sentinel2_start, sentinel_size, 93);

    // Ineligible and eligible requests for exactly the same bytes coexist.
    // Admission belongs to a sequence slot, never to a global address blacklist.
    for (bool first : {false, true})
    {
        begin_prediction_session();
        record_eligibility(rewritten_start, rewritten_size, first);
        record_eligibility(rewritten_start, rewritten_size, !first);
        record_eligibility(sentinel_start, sentinel_size, true);
        const u64 before = tp::worker_bytes;
        next_prediction_frame();
        wait_hash(sentinel_start, sentinel_size, tv::current_epoch());
        u64 out = 0;
        CELL581_REQUIRE(tp::lookup(rewritten_start, rewritten_size, tv::current_epoch(), out));
        CELL581_REQUIRE(out == tp::range_hash(vm::g_sudo_addr + rewritten_start, rewritten_size));
        tp::stop();
        CELL581_REQUIRE(tp::worker_bytes - before == rewritten_size + sentinel_size);
    }

    // Same address, different lengths: rejecting one request does not exclude
    // the other. Their content keys and original epoch checks are unchanged.
    begin_prediction_session();
    record_eligibility(rewritten_start, sentinel_size, false);
    record_eligibility(rewritten_start, rewritten_size, true);
    record_eligibility(sentinel_start, sentinel_size, true);
    next_prediction_frame();
    wait_hash(sentinel_start, sentinel_size, tv::current_epoch());
    u64 out = 0;
    CELL581_REQUIRE(tp::lookup(rewritten_start, rewritten_size, tv::current_epoch(), out));
    tp::stop();

    // A bypassed slot at ordinal zero must remain in the sequence. At ordinal
    // one the same range becomes eligible; filtering the slot out would shift
    // the progress indices and skip or mis-schedule the second epoch's work.
    begin_prediction_session();
    record_eligibility(rewritten_start, rewritten_size, false);
    record_eligibility(sentinel_start, sentinel_size, true);
    tv::advance_epoch();
    record_eligibility(rewritten_start, rewritten_size, true);
    record_eligibility(sentinel2_start, sentinel_size, true);
    next_prediction_frame();
    wait_hash(sentinel_start, sentinel_size, tv::current_epoch());
#if ADMISSION_CANDIDATE
    CELL581_REQUIRE(!tp::lookup(rewritten_start, rewritten_size, tv::current_epoch(), out));
#endif
    record_eligibility(rewritten_start, rewritten_size, false);
    record_eligibility(sentinel_start, sentinel_size, true);
    tv::advance_epoch();
    wait_hash(sentinel2_start, sentinel_size, tv::current_epoch());
    CELL581_REQUIRE(tp::lookup(rewritten_start, rewritten_size, tv::current_epoch(), out));
    tp::stop();
}

void becomes_eligible_again()
{
    section a(rewritten_start, rewritten_size), sentinel(sentinel_start, sentinel_size);
    fill(rewritten_start, rewritten_size, 101);
    a.protect(utils::protection::ro);
    sentinel.protect(utils::protection::ro);
    begin_prediction_session();
    a.reset_validation();
    CELL581_REQUIRE(a.sync());
    CELL581_REQUIRE(sentinel.sync());

    next_prediction_frame();
    wait_hash(sentinel_start, sentinel_size, tv::current_epoch());
    u64 out = 0;
#if ADMISSION_CANDIDATE
    CELL581_REQUIRE(!tp::lookup(rewritten_start, rewritten_size, tv::current_epoch(), out));
#endif
    // No write now: this caller hashes as before, and records an eligible slot.
    CELL581_REQUIRE(a.sync());
    CELL581_REQUIRE(sentinel.sync());
    next_prediction_frame();
    wait_hash(sentinel_start, sentinel_size, tv::current_epoch());
    CELL581_REQUIRE(tp::lookup(rewritten_start, rewritten_size, tv::current_epoch(), out));
    const u64 hits = tp::hits;
    CELL581_REQUIRE(a.sync());
    CELL581_REQUIRE(tp::hits == hits + 1);
    tp::stop();
}

void admission_main()
{
    constexpr u64 reservation = u64{rsx::constants::local_mem_base} + (16u << 20);
    void* base = mmap(nullptr, reservation, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    CELL581_REQUIRE(base != MAP_FAILED);
    vm::g_sudo_addr = static_cast<u8*>(base);
    CELL581_REQUIRE(mprotect(vm::g_sudo_addr + rsx::constants::local_mem_base, 16u << 20, PROT_READ | PROT_WRITE) == 0);
    tv::epoch_enabled = true;
    reject_stale_results();
    // Distinct direct-map slots make the byte-count expectation unambiguous.
    CELL581_REQUIRE(tp::slot_of(tp::make_key(rewritten_start, rewritten_size)) != tp::slot_of(tp::make_key(sentinel_start, sentinel_size)));

    section a(rewritten_start, rewritten_size), sentinel(sentinel_start, sentinel_size);
    fill(rewritten_start, rewritten_size, 11);
    fill(sentinel_start, sentinel_size, 12);
    a.protect(utils::protection::ro);
    sentinel.protect(utils::protection::ro);
    begin_prediction_session();
    a.reset_validation();
    CELL581_REQUIRE(a.sync());
    CELL581_REQUIRE(sentinel.sync());

    constexpr u64 frames = 12;
    const u64 before = tp::worker_bytes;
    const u64 hashes_before = tp::worker_hashes;
    u64 changed = 0;
    for (u64 frame = 0; frame < frames; frame++)
    {
        next_prediction_frame();
        // Last in the batch: its publication proves earlier work completed.
        wait_hash(sentinel_start, sentinel_size, tv::current_epoch());
        fill(rewritten_start, rewritten_size, static_cast<u32>(1000 + frame));
        a.reset_validation();
        CELL581_REQUIRE(!a.sync());
        ++changed;
        a.discard();
        a.protect(utils::protection::ro);
        CELL581_REQUIRE(sentinel.sync());
    }
    tp::stop(); // Join before reading the final completed-work counts.
    const u64 worker_bytes_used = tp::worker_bytes - before;
    const u64 worker_hashes_used = tp::worker_hashes - hashes_before;
    const u64 expected_bytes = frames * (sentinel_size + (ADMISSION_CANDIDATE ? 0 : rewritten_size));
    CELL581_REQUIRE(worker_bytes_used == expected_bytes);
    CELL581_REQUIRE(worker_hashes_used == frames * (ADMISSION_CANDIDATE ? 1 : 2));

    mixed_requests();
    becomes_eligible_again();
    CELL581_REQUIRE(!tp::enabled.load() && vm::g_range_lock_bits[0].load() == 0);
    std::printf("{\"passed\":true,\"candidate\":%s,\"frames\":%llu,\"rewrittenBytesPerFrame\":%u,"
                "\"workerBytes\":%llu,\"workerHashes\":%llu,\"changedTexturesRejected\":%llu,"
                "\"mixedEligibility\":true,\"epochOrdinals\":true,\"nextFrameReadmission\":true,"
                "\"staleEpochRejected\":true,\"scopedWriteRejected\":true}\n",
                ADMISSION_CANDIDATE ? "true" : "false", static_cast<unsigned long long>(frames), rewritten_size,
                static_cast<unsigned long long>(worker_bytes_used), static_cast<unsigned long long>(worker_hashes_used),
                static_cast<unsigned long long>(changed));
    munmap(base, reservation);

    // The unchanged 581 model below starts its observations at zero.
    tp::hits = tp::misses = tp::hit_bytes = 0;
    tp::worker_hashes = tp::worker_bytes = tp::worker_ticks = tp::worker_skips = 0;
    tp::worker_passed = tp::worker_refills = 0;
}
}

int main(int argc, char** argv)
{
    admission_main();
    return existing_model_main(argc, argv);
}
