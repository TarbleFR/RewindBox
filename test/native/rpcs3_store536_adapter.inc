// Execute the complete production STORE128 body with controlled CPU/RSX/VM
// boundaries. This is an ordering test, not a GPU or guest emulation test.
using u8 = std::uint8_t; using u32 = std::uint32_t; using u64 = std::uint64_t;
using u128 = unsigned __int128; using spu_rdata_t = u8[128];
constexpr u64 operator""_u64(const char*, std::size_t) { return 0; }
template<u64> struct perf_meter { u64 get() const { return 0; } };
namespace cpu_flag { constexpr unsigned pause = 1, wait = 2; }
inline unsigned fault_calls, fault_owned, copy_calls, writer_calls, suspend_calls;
inline bool rsx_owned, fault_pause, resume_after_acquire, throw_fault;
inline u128 reservation;
struct spu_thread { void* range_lock = nullptr; };
struct cpu_thread {
    unsigned state = 0;
    void check_state() {} bool test_stopped() { return false; }
    template<class T> T* try_get() { return nullptr; }
    template<int, class F> static void suspend_all(cpu_thread*, std::initializer_list<int>, F f) { ++suspend_calls; f(); }
};
inline cpu_thread current;
inline cpu_thread* get_current_cpu_thread() { return &current; }
struct Config { struct { bool spu_accurate_reservations = true, perf_report = false; } core; };
inline Config g_cfg;
template<class> struct atomic_t {
    template<class F> auto fetch_op(F fn) {
        const u128 old = reservation; const bool ok = fn(reservation);
        if (resume_after_acquire) current.state = 0;
        return std::pair{old,ok};
    }
    u128 operator^(u128 rhs) const { return reservation ^ rhs; }
};
namespace vm {
constexpr u64 rsrv_unique_lock = 64, rsrv_putunc_flag = 32;
inline u64 g_shmem[1] = {0};
alignas(16) inline u8 line[128];
inline atomic_t<u128> atom;
inline auto* g_reservations = reinterpret_cast<u8*>(&atom);
struct Reservation {
    operator u64() const { return static_cast<u64>(reservation); }
    void operator+=(u64 amount) { reservation += amount; }
};
inline Reservation reservation_proxy;
inline Reservation& reservation_acquire(u32) { return reservation_proxy; }
inline void try_reservation_update(u32) { reservation += 128; }
template<class T> T* get_super_ptr(u32) { return reinterpret_cast<T*>(line); }
inline void* base(u32) { return line; }
enum class writer_lock_source { spu_store128 };
struct writer_lock_tag { explicit writer_lock_tag(writer_lock_source) {} };
struct writer_lock { writer_lock(u32, void*) { assert((reservation & 127) == 96); ++writer_calls; } };
}
namespace rsx { struct reservation_lock { reservation_lock(u32, unsigned) { assert(!rsx_owned); rsx_owned = true; } ~reservation_lock() { rsx_owned = false; } }; }
namespace utils {
template<class T> T* bless(void* p) { return static_cast<T*>(p); }
inline u64 get_tsc() { return 42; } inline double get_tsc_freq() { return 1e9; }
inline void trigger_write_page_fault(void*) {
    assert(rsx_owned); ++fault_calls; fault_owned += (reservation & 127) != 0;
    if (fault_pause) current.state |= cpu_flag::pause;
    if (throw_fault) throw 536;
}
}
inline void busy_wait(unsigned) {}
inline bool cmp_rdata(const spu_rdata_t& a,const spu_rdata_t& b) { return std::memcmp(a,b,128)==0; }
inline bool rdata_fence() { return true; }
inline void mov_rdata(spu_rdata_t& a,const spu_rdata_t& b) { ++copy_calls; std::memcpy(a,b,128); }
struct Logger { template<class... T> void warning(const char*,T...) {} }; inline Logger perf_log;
void do_cell_atomic_128_store(u32 addr,const void* data);
inline void reset() {
    fault_calls=fault_owned=copy_calls=writer_calls=suspend_calls=0;
    rsx_owned=fault_pause=resume_after_acquire=throw_fault=false;
    reservation=0;current.state=0;g_cfg={};std::memset(vm::line,0,128);
}
inline void test(bool fixed) {
    alignas(16) spu_rdata_t data{}; data[30]=9;
    reset();do_cell_atomic_128_store(0,data);
    assert(fault_calls==1 && fault_owned==(fixed?0u:1u) && copy_calls==1 && writer_calls==1);
    assert(reservation==128 && std::memcmp(data,vm::line,128)==0 && !rsx_owned);
    reset();do_cell_atomic_128_store(0,vm::line);
    assert(fault_calls==0 && copy_calls==0 && reservation==128);
    reset();g_cfg.core.spu_accurate_reservations=false;do_cell_atomic_128_store(0,data);
    assert(fault_calls==0 && writer_calls==0 && copy_calls==1 && reservation==128);
    reset();current.state=cpu_flag::pause;do_cell_atomic_128_store(0,data);
    assert(fault_calls==0 && writer_calls==0 && suspend_calls==1 && reservation==128);
    reset();current.state=cpu_flag::pause;resume_after_acquire=true;do_cell_atomic_128_store(0,data);
    // The uncommon paused -> running transition retains the old fault path.
    assert(fault_calls==1 && fault_owned==1 && writer_calls==1 && reservation==128);
    reset();fault_pause=true;do_cell_atomic_128_store(0,data);
    assert(fault_owned==(fixed?0u:1u) && copy_calls==1 && reservation==128);
    assert(suspend_calls==(fixed?1u:0u));
    reset();throw_fault=true;
    try { do_cell_atomic_128_store(0,data); assert(false); } catch(int value) { assert(value==536); }
    assert(reservation==(fixed?0u:96u) && !rsx_owned && copy_calls==0);
    // No-op comparisons still inspect all 128 bytes, including unprobed lanes.
    for(unsigned byte=0;byte<128;++byte) {
        reset();std::memset(data,0,128);data[byte]=1;do_cell_atomic_128_store(0,data);
        assert(copy_calls==1 && reservation==128 && std::memcmp(data,vm::line,128)==0);
    }
}
