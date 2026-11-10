// Production header + exact 553 FingerprintTable control. No Vulkan, shader
// compilation or iPhone timing is simulated by these diagnostic tests.
using namespace rpcs3::ios::shader_timing;

static PipelineContext context_for(std::uint64_t id)
{
    return {id, 0x241822c, 0x100000 + id, 0x200000 + id, 5};
}

int main()
{
    before::FingerprintTable old;
    FingerprintTable current;
    assert(FingerprintTable::capacity == 64);
    static_assert(sizeof(FingerprintTable) <= sizeof(before::FingerprintTable) + 64);

    // The exact repeated key from the 553 GoW3 log represents missing context,
    // not two equal game pipelines. Keep its operations visible separately.
    assert(FingerprintTable::fingerprint(PipelineContext{}) == 0xa13f0aae7a3f4fc0ull);
    for (int i = 0; i < 3; ++i)
    {
        old.record(before::FingerprintTable::fingerprint({}), 100 + i);
        current.record(PipelineContext{}, 100 + i);
    }
    assert(old.snapshot().repeated_builds == 2);
    auto sample = current.snapshot();
    assert(sample.unattributed == 3 && sample.tracked == 0 && sample.repeated_builds == 0);
    old.reset(); current.reset();

    // Warm-up exhausts the old table permanently. New admissions remain
    // observable after a long preload, with eviction explicitly reported.
    for (std::uint64_t i = 1; i <= 900; ++i)
    {
        const auto context = context_for(i);
        old.record(before::FingerprintTable::fingerprint(context), i);
        current.record(context, i);
    }
    const auto game_context = context_for(1001);
    for (int i = 0; i < 2; ++i)
    {
        old.record(before::FingerprintTable::fingerprint(game_context), 1000 + i);
        current.record(game_context, 1000 + i);
    }
    assert(old.snapshot().dropped == 838 && old.snapshot().repeated_builds == 0);
    sample = current.snapshot();
    assert(sample.distinct == 64 && sample.tracked == 902 && sample.evicted == 837);
    assert(sample.dropped == 0 && sample.repeated_builds == 1);
    assert(sample.repeated[0].fingerprint == FingerprintTable::fingerprint(game_context));
    assert(sample.repeated[0].builds == 2 && sample.repeated[0].total_us == 2001);
    assert(sample.costliest[0].max_us == 1001);

    // FIFO replacement is exactly bounded; observing an old evicted identity
    // again must not pretend that all lifetime duplicates are still knowable.
    for (std::uint64_t i = 2000; i < 2064; ++i) current.record(context_for(i), i);
    sample = current.snapshot();
    assert(sample.repeated_builds == 1 && sample.repeated[0].fingerprint == 0);
    current.record(game_context, 1234);
    assert(current.snapshot().repeated_builds == 1);
    current.record(game_context, 1235);
    assert(current.snapshot().repeated_builds == 2);

    // A zero properties hash is legal; validity is determined by the shader
    // modules, not by an arbitrary nonzero hash assumption.
    current.record(PipelineContext{0, 0, 41, 42, 0}, 1);
    current.record(PipelineContext{0, 0, 41, 42, 0}, 2);
    assert(current.snapshot().repeated_builds == 3);
    current.record(PipelineContext{1, 2, 0, 42, 5}, 3);
    current.record(PipelineContext{1, 2, 41, 0, 5}, 3);
    assert(current.snapshot().unattributed == 2);

    current.reset();
    sample = current.snapshot();
    assert(sample.captured && !sample.distinct && !sample.repeated_builds && !sample.dropped &&
        !sample.tracked && !sample.evicted && !sample.unattributed);

    // Try-lock producers plus a concurrent reporter: every operation is either
    // tracked, explicitly dropped for contention, or unattributed. No loss is
    // hidden by saturation, and reporting cannot block compilation workers.
    constexpr unsigned threads = 8, per_thread = 2000;
    std::atomic<bool> done{false};
    std::thread reporter([&] { while (!done.load()) (void)current.snapshot(); });
    std::vector<std::thread> workers;
    for (unsigned t = 0; t < threads; ++t)
        workers.emplace_back([&, t] {
            for (unsigned i = 0; i < per_thread; ++i)
            {
                current.record(context_for(1 + (i + t) % 40), i);
                current.record(PipelineContext{}, i);
            }
        });
    for (auto& worker : workers) worker.join();
    done.store(true); reporter.join();
    sample = current.snapshot();
    assert(sample.tracked + sample.dropped == threads * per_thread);
    assert(sample.unattributed == threads * per_thread && sample.evicted == 0);
    assert(sample.distinct + sample.repeated_builds == sample.tracked);

    // Attribution does not disable timing for raw/UI operations.
    (void)take();
    for (int i = 0; i < 3; ++i)
    {
        Scope timer(Stage::graphics);
        current.record(PipelineContext{}, 1);
    }
    assert(take()[static_cast<std::size_t>(Stage::graphics)].count == 3);
    std::cout << "{\"baselineFalseRepeats\":2,\"fixedFalseRepeats\":0,"
        "\"baselineWarmupDropped\":838,\"fixedWarmupDropped\":0,"
        "\"fixedWarmupEvicted\":837,\"postWarmupRepeatDetected\":1,"
        "\"concurrentAttributedRequests\":16000,\"concurrentUnknownRequests\":16000,"
        "\"capacity\":64,\"extraBytes\":" << sizeof(FingerprintTable)-sizeof(before::FingerprintTable)
        << ",\"renderingTested\":false,\"deviceTimingMeasured\":false}\n";
}
