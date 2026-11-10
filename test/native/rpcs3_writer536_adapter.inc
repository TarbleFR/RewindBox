// Namespace-local adapter for the *extracted production destructor*.
using u64 = std::uint64_t;
namespace utils { inline u64 get_tsc() { return 42; } }
struct Word {
    std::atomic<u64> value{0};
    std::atomic<unsigned> notifications{0};
    u64 operator&=(u64 mask) { return value.fetch_and(mask) & mask; }
    void release(u64 v) { value.store(v, std::memory_order_release); }
    void notify_all() { ++notifications; value.notify_all(); }
};
namespace vm {
inline Word g_range_lock_bits[2], g_range_lock_set[64];
struct writer_lock {
    Word* range_lock = nullptr;
    unsigned source = 1;
    u64 acquire_ticks = 17, acquired_tsc = 32;
    ~writer_lock() noexcept;
};
}
inline std::atomic<bool> entered{false}, resume_profile{false};
inline u64 observed_bits, observed_slot, observed_hold;
inline unsigned observed_notifications;
namespace rpcs3::ios {
inline void record_writer_lock(unsigned source, u64 acquisition, u64 hold) {
    assert(source == 1 && acquisition == 17);
    observed_bits = vm::g_range_lock_bits[1].value.load();
    observed_slot = vm::g_range_lock_set[3].value.load();
    observed_hold = hold;
    observed_notifications = vm::g_range_lock_bits[1].notifications.load();
    entered.store(true, std::memory_order_release);
    entered.notify_all();
    resume_profile.wait(false);
}
}
inline void test(bool fixed) {
    for (unsigned mode = 0; mode < 3; ++mode) {
        const u64 initial = mode == 0 ? ~u64{0} : mode == 1 ? 8 : 24;
        vm::g_range_lock_bits[1].release(initial);
        vm::g_range_lock_bits[1].notifications = 0;
        vm::g_range_lock_set[3].release(128);
        entered = false; resume_profile = false;
        std::thread writer([&] { vm::writer_lock lock; if (mode) lock.range_lock = &vm::g_range_lock_set[3]; });
        entered.wait(false);
        // A deliberately delayed profiler cannot retain the writer exclusion.
        assert(observed_bits == (fixed ? (mode == 2 ? 16 : 0) : initial));
        assert(observed_slot == (fixed && mode ? 0 : 128));
        assert(observed_notifications == (fixed && mode != 2 ? 1u : 0u));
        assert(observed_hold == 10);
        resume_profile = true; resume_profile.notify_all(); writer.join();
        assert(vm::g_range_lock_bits[1].value == (mode == 2 ? 16 : 0));
        assert(vm::g_range_lock_bits[1].notifications == (mode == 2 ? 0u : 1u));
    }
}
