#include <algorithm>
#include <array>
#include <bit>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <initializer_list>
#include <iostream>
#include <limits>
#include <span>
#include <tuple>
#include <utility>

#ifdef NDEBUG
#error FIFO checks require assertions.
#endif
using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;
constexpr u32 umax = std::numeric_limits<u32>::max();
using spu_rdata_t = std::byte[128];
void mov_rdata(spu_rdata_t& dst, const spu_rdata_t& src) { std::memcpy(dst, src, sizeof(src)); }
bool cmp_rdata(const spu_rdata_t& lhs, const spu_rdata_t& rhs) { return std::memcmp(lhs, rhs, sizeof(lhs)) == 0; }
#define ensure(expr) assert(expr)

@CONSTANTS@

// Host boundaries: deterministic big-endian guest RAM, I/O map, reservation
// values and callbacks. The FIFO cache and packet machinery below is production.
template<class T> struct be_t {
    std::array<u8, sizeof(T)> bytes;
    operator T() const { T value{}; for (u8 byte : bytes) value = (value << 8) | byte; return value; }
};
template<class T> T read_from_ptr_unsafe(const std::byte* data, usz offset) {
    T value; std::memcpy(&value, data + offset, sizeof(T)); return value;
}
namespace vm {
alignas(128) std::array<std::byte, 0x200000> ram{};
std::array<u64, ram.size() / 128> reservations{};
template<class T> T* _ptr(u32 address) { assert(address + sizeof(T) <= ram.size()); return reinterpret_cast<T*>(ram.data() + address); }
u64& reservation_acquire(u32 address) { return reservations.at(address / 128); }
u32 read32(u32 address) { assert(address + 4 <= ram.size()); return read_from_ptr_unsafe<be_t<u32>>(ram.data(), address); }
void write32(u32 address, u32 value) {
    assert(address + 4 <= ram.size());
    for (u32 i = 0; i != 4; ++i) ram[address + i] = static_cast<std::byte>((value >> (24 - i * 8)) & 0xff);
}
}
struct Word {
    u32 value{};
    u64 publications{};
    operator u32() const { return value; }
    void release(u32 next) { value = next; ++publications; }
    u32 and_fetch(u32 mask) { return value &= mask; }
};
struct RsxDmaControl { Word get, put; };
namespace rsx {
struct rsx_iomap_table {
    u32 bad_begin{umax}, bad_end{umax};
    u32 get_addr(u32 address) const {
        if (address >= vm::ram.size() || (address >= bad_begin && address < bad_end)) return umax;
        return address;
    }
};
template<bool, u32> struct reservation_lock { reservation_lock(u32, u32, bool) {} };
struct thread {
    RsxDmaControl owned_ctrl;
    RsxDmaControl* ctrl = &owned_ctrl;
    rsx_iomap_table iomap_table;
    struct { u64 idle_time{}; } performance_counters;
    bool stopped{};
    u32 waits{}, recoveries{};
    std::function<void()> on_wait, on_recover;
    bool is_stopped() const { return stopped; }
    void cpu_wait(std::initializer_list<int>) { ++waits; if (on_wait) on_wait(); }
    void recover_fifo() { ++recoveries; if (on_recover) on_recover(); }
};
}
struct ModeOption {
    rsx_fifo_mode value{rsx_fifo_mode::fast};
    operator bool() const { return value != rsx_fifo_mode::fast; }
    bool operator==(rsx_fifo_mode other) const { return value == other; }
    bool operator>=(rsx_fifo_mode other) const { return value >= other; }
};
struct { struct { ModeOption rsx_fifo_accuracy; } core; } g_cfg;
namespace rpcs3::ios {
struct Policy { u32 fifo_cache_bytes{1024}; bool deferred_get_publishing{}, fifo_idle_wfe{}, fifo_idle_bounded_sleep{}, rsx_idle_park{}; } policy;
const Policy& get_experimental_policy() { return policy; }
namespace texture_validation { u64 epochs{}; void advance_epoch() { ++epochs; } }
}
struct { bool stopped{}; bool IsStopped() const { return stopped; } } Emu;
u64 clock_tick{};
u64 get_system_time() { return clock_tick += 60; }
void busy_wait(u32) {}

@BEFORE@
@AFTER@

using namespace rsx;
using namespace rsx::FIFO;
constexpr u32 sentinel = 0x1234abcd;
constexpr u32 value_sentinel = 0x76543210;
constexpr u32 method = 0x300;
constexpr std::array<rsx_fifo_mode, 4> modes{rsx_fifo_mode::fast, rsx_fifo_mode::atomic, rsx_fifo_mode::atomic_ordered, rsx_fifo_mode::as_ps3};
constexpr std::array<u32, 3> starts{0x4000, 0x407c, 0xffffc};
u32 argument(u32 index) { return 0x91000000u ^ (index * 0x10203u); }
u32 command(u32 count, bool non_increment) { return method | (count << 18) | (non_increment ? static_cast<u32>(RSX_METHOD_NON_INCREMENT_CMD) : 0u); }
void configure(rsx_fifo_mode mode, u32 cache_bytes, bool deferred) {
    g_cfg.core.rsx_fifo_accuracy.value = mode;
    rpcs3::ios::policy = {cache_bytes, deferred, false};
    vm::reservations.fill(0);
    Emu.stopped = false;
}
void packet(u32 start, u32 count, bool non_increment) {
    vm::write32(start, command(count, non_increment));
    for (u32 i = 0; i < count; ++i) vm::write32(start + 4 + 4 * i, argument(i));
    vm::write32(start + 4 + 4 * count, RSX_METHOD_NOP_CMD);
}
template<class F> auto state(const F& fifo) {
    return std::tuple{fifo.m_internal_get, fifo.m_remaining_commands,
                      fifo.m_command_reg, fifo.m_command_inc, fifo.m_args_ptr, fifo.m_cmd};
}
struct Results {
    u64 pending_cases{}, pending_waits{}, old_pending_unchanged{}, new_pending_unchanged{}, resumed_pending{};
    u64 partial_packets{}, old_first_missed{}, new_first_missed{}, resumed_partial_words{}, header_waits{}, get_reentries{};
    u64 exceptional{}, fast_blocking{}, restored_pending{};
} counts;

void pending_packets() {
    constexpr std::array<u32, 10> lengths{2, 3, 4, 7, 8, 31, 32, 33, 127, 255};
    for (auto mode : modes) for (u32 bytes : {1024u, 4096u})
    for (bool deferred : {false, true}) for (bool non_increment : {false, true})
    for (u32 start : starts) for (u32 length : lengths) {
        configure(mode, bytes, deferred);
        packet(start, length, non_increment);
        rsx::thread bt, at;
        bt.ctrl->put.value = at.ctrl->put.value = start + 8;
        before::FIFO_control b(&bt); after::FIFO_control a(&at);
        b.set_get(start); a.set_get(start);
        register_pair bd{sentinel, value_sentinel}, ad = bd;
        b.read(bd); a.read(ad);
        assert(bd.reg == method && bd.value == argument(0));
        assert(ad.reg == bd.reg && ad.value == bd.value);
        for (u32 index = 1; index < length; ++index) {
            const auto bs = state(b), as = state(a);
            for (u32 retry = 0; retry < 4; ++retry) {
                bd = ad = {sentinel, value_sentinel};
                b.read(bd); a.read(ad);
                assert(state(b) == bs && state(a) == as);
                counts.old_pending_unchanged += bd.reg == sentinel;
                counts.new_pending_unchanged += ad.reg == sentinel;
                assert(bd.reg == sentinel && ad.reg == FIFO_EMPTY);
                assert(bd.value == value_sentinel && ad.value == value_sentinel);
                b.sync_get(); a.sync_get();
                assert(bt.ctrl->get.value == at.ctrl->get.value);
                assert(bt.ctrl->get.value <= start + 4 * index);
                ++counts.pending_waits;
            }
            b.sync_get_force(); a.sync_get_force();
            assert(bt.ctrl->get.value == start + 4 * index && at.ctrl->get.value == bt.ctrl->get.value);
            bt.ctrl->put.value = at.ctrl->put.value = start + 4 * (index + 2);
            b.read(bd); a.read(ad);
            const u32 reg = method + (non_increment ? 0 : 4 * index);
            assert(bd.reg == reg && ad.reg == reg);
            assert(bd.value == argument(index) && ad.value == bd.value);
            assert(b.get_remaining_args_count() == length - index - 1);
            assert(a.get_remaining_args_count() == b.get_remaining_args_count());
            ++counts.resumed_pending;
        }
        assert(!b.read_unsafe(bd) && !a.read_unsafe(ad));
        assert(b.get_pos() == start + 4 * (length + 1) && a.get_pos() == b.get_pos());
        ++counts.pending_cases;
    }
}

@PACKET_TESTS@
