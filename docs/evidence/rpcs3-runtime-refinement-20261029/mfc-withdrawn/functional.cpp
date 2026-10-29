#include <algorithm>
#include <array>
#include <bit>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <tuple>
#include <utility>
#include <vector>

#ifdef NDEBUG
#error MFC tests require assertions
#endif
using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
#define ENABLE_BITWISE_SERIALIZATION
enum MFC : u8
{
	MFC_PUT_CMD      = 0x20, MFC_PUTB_CMD     = 0x21, MFC_PUTF_CMD     = 0x22,
	MFC_PUTS_CMD     = 0x28, MFC_PUTBS_CMD    = 0x29, MFC_PUTFS_CMD    = 0x2a,
	MFC_PUTR_CMD     = 0x30, MFC_PUTRB_CMD    = 0x31, MFC_PUTRF_CMD    = 0x32,
	MFC_GET_CMD      = 0x40, MFC_GETB_CMD     = 0x41, MFC_GETF_CMD     = 0x42,
	MFC_GETS_CMD     = 0x48, MFC_GETBS_CMD    = 0x49, MFC_GETFS_CMD    = 0x4a,
	MFC_PUTL_CMD     = 0x24, MFC_PUTLB_CMD    = 0x25, MFC_PUTLF_CMD    = 0x26,
	MFC_PUTRL_CMD    = 0x34, MFC_PUTRLB_CMD   = 0x35, MFC_PUTRLF_CMD   = 0x36,
	MFC_GETL_CMD     = 0x44, MFC_GETLB_CMD    = 0x45, MFC_GETLF_CMD    = 0x46,
	MFC_GETLLAR_CMD  = 0xD0,
	MFC_PUTLLC_CMD   = 0xB4,
	MFC_PUTLLUC_CMD  = 0xB0,
	MFC_PUTQLLUC_CMD = 0xB8,

	MFC_SNDSIG_CMD   = 0xA0, MFC_SNDSIGB_CMD  = 0xA1, MFC_SNDSIGF_CMD  = 0xA2,
	MFC_BARRIER_CMD  = 0xC0,
	MFC_EIEIO_CMD    = 0xC8,
	MFC_SYNC_CMD     = 0xCC,

	MFC_BARRIER_MASK = 0x01,
	MFC_FENCE_MASK   = 0x02,
	MFC_LIST_MASK    = 0x04,
	MFC_START_MASK   = 0x08,
	MFC_RESULT_MASK  = 0x10, // ???

	MFC_SDCRT_CMD   = 0x80,
	MFC_SDCRTST_CMD = 0x81,
	MFC_SDCRZ_CMD   = 0x89,
	MFC_SDCRS_CMD   = 0x8D,
	MFC_SDCRF_CMD   = 0x8F,
};
enum mfc_tag_update : u32
{
	MFC_TAG_UPDATE_IMMEDIATE = 0,
	MFC_TAG_UPDATE_ANY       = 1,
	MFC_TAG_UPDATE_ALL       = 2,
};
struct alignas(16) spu_mfc_cmd
{
	ENABLE_BITWISE_SERIALIZATION;

	MFC cmd;
	u8 tag;
	u16 size;
	u32 lsa;
	u32 eal;
	u32 eah;
};
static_assert(sizeof(spu_mfc_cmd) == 16);

struct { struct { u32 mfc_transfers_shuffling{}; bool mfc_shuffling_in_steps{}; } core; } g_cfg;

// Deterministic clock adapter. For nonempty enabled shuffling, both versions
// must consume the exact same sequence. Every fourth read permits progress.
namespace utils {
u64 clock_calls{};
u64 sample{};
bool fixed{};
u64 get_tsc() {
    ++clock_calls;
    if (fixed) return sample;
    if (clock_calls % 4 == 0) return 0xffff;
    return sample ^ (clock_calls * 0x9e3779b97f4a7c15ull);
}
}
enum class Action : u32 { dma, list, putlluc, barrier, tag, cancel, escape };
using Record = std::tuple<Action, u32, u32, u32>;
struct State;
State* active{};
struct Channel {
    u32 value{}, count{};
    void set_value(u32 next);
};
struct Events {
    struct Value { bool count{}; } value;
    Value load() const { return value; }
};
struct State {
    spu_mfc_cmd mfc_queue[16]{};
    u32 mfc_size{}, mfc_barrier{0xffffffff}, mfc_fence{0xffffffff};
    u32 ch_tag_mask{}, ch_tag_upd{}, pc{0x1000}, srr0{};
    u64 mfc_last_timestamp{}, system_reads{}, clock_reads{};
    Channel ch_tag_stat;
    Events ch_events;
    bool interrupts_enabled{}, timer_armed{true}, complete_lists{};
    u32 interrupt_word{0x30000100};
    u8* ls{};
    std::vector<Record> actions;
    template<class T> T& _ref(u32 address) { static_assert(sizeof(T) == 4); assert(address == 0); return interrupt_word; }
    void cancel_dec_interrupt() { timer_armed = false; actions.emplace_back(Action::cancel,0,0,0); }
    bool do_list_transfer(spu_mfc_cmd& command) {
        actions.emplace_back(Action::list,command.eah,command.tag,command.size);
        if (!complete_lists && command.eah % 3 == 0) {
            command.tag |= 0x80;
            command.eal += 8; command.lsa += 16;
            if (command.size > 8) command.size -= 8;
            return false;
        }
        return true;
    }
    void do_putlluc(const spu_mfc_cmd& command) { actions.emplace_back(Action::putlluc,command.eah,command.tag,command.size); }
    static void do_dma_transfer(State* self, const spu_mfc_cmd& command, u8*) {
        self->actions.emplace_back(Action::dma,command.eah,command.tag,command.size);
    }
};
void Channel::set_value(u32 next) {
    value = next; count = 1;
    active->actions.emplace_back(Action::tag,next,0,0);
}
void atomic_fence_seq_cst() { active->actions.emplace_back(Action::barrier,0,0,0); }
u64 get_system_time() { return 10000 + ++active->system_reads; }
struct Escaped {};
namespace spu_runtime {
[[noreturn]] void g_escape(State* self) {
    self->actions.emplace_back(Action::escape,self->pc,self->srr0,0);
    throw Escaped{};
}
}

namespace before {
struct spu_thread : State {
    bool do_mfc(bool can_escape, bool must_finish);
    u32 get_mfc_completed() const;
    bool check_mfc_interrupts(u32 next_pc);
};
bool spu_thread::do_mfc(bool can_escape, bool must_finish)
{
	u32 removed = 0;
	u32 barrier = 0;
	u32 fence = 0;
	u16 exec_mask = 0;
	bool pending = false;

	auto process_command = [&](spu_mfc_cmd& args)
	{
		// Select tag bit in the tag mask or the stall mask
		const u32 mask = std::rotl<u32>(1, args.tag);

		if ((args.cmd & ~0xc) == MFC_BARRIER_CMD)
		{
			if (&args - mfc_queue <= removed)
			{
				// Remove barrier-class command if it's the first in the queue
				atomic_fence_seq_cst();
				removed++;
				return true;
			}

			// Block all tags
			barrier |= -1;
			fence |= mask;
			return false;
		}

		if (barrier & mask)
		{
			fence |= mask;
			return false;
		}

		if (args.cmd & (MFC_BARRIER_MASK | MFC_FENCE_MASK) && fence & mask)
		{
			if (args.cmd & MFC_BARRIER_MASK)
			{
				barrier |= mask;
			}

			return false;
		}

		// If command is not enabled in execution mask, execute it later
		if (!(exec_mask & (1u << (&args - mfc_queue))))
		{
			if (args.cmd & MFC_BARRIER_MASK)
			{
				barrier |= mask;
			}

			// Fence is set for any command
			fence |= mask;
			pending = true;
			return false;
		}

		if (args.cmd & MFC_LIST_MASK)
		{
			if (!(args.tag & 0x80))
			{
				if (do_list_transfer(args))
				{
					removed++;
					return true;
				}
			}

			if (args.cmd & MFC_BARRIER_MASK)
			{
				barrier |= mask;
			}

			fence |= mask;
			return false;
		}

		if (args.cmd == MFC_PUTQLLUC_CMD)
		{
			if (fence & mask)
			{
				return false;
			}

			do_putlluc(args);
		}
		else if (args.size)
		{
			do_dma_transfer(this, args, ls);
		}

		removed++;
		return true;
	};

	auto get_exec_mask = [&size = mfc_size]
	{
		// Get commands' execution mask
		const u32 shuffle_count = std::min<u32>(g_cfg.core.mfc_transfers_shuffling, size);
		if (!shuffle_count)
		{
			// All commands are enabled. Reading the host clock cannot affect
			// this mask, including an empty queue with shuffling enabled.
			return u16{0xffff};
		}

		return static_cast<u16>((0 - (1u << shuffle_count)) | utils::get_tsc());
	};

	// Process enqueued commands
	while (true)
	{
		removed = 0;
		barrier = 0;
		fence = 0;

		// Shuffle commands execution (if enabled), explicit barriers are obeyed
		pending = false;
		exec_mask = get_exec_mask();

		static_cast<void>(std::remove_if(mfc_queue + 0, mfc_queue + mfc_size, process_command));

		mfc_size -= removed;
		mfc_barrier = barrier;
		mfc_fence = fence;

		if (removed && ch_tag_upd)
		{
			const u32 completed = get_mfc_completed();

			if (completed && ch_tag_upd == MFC_TAG_UPDATE_ANY)
			{
				ch_tag_stat.set_value(completed);
				ch_tag_upd = MFC_TAG_UPDATE_IMMEDIATE;
			}
			else if (completed == ch_tag_mask && ch_tag_upd == MFC_TAG_UPDATE_ALL)
			{
				ch_tag_stat.set_value(completed);
				ch_tag_upd = MFC_TAG_UPDATE_IMMEDIATE;
			}
		}

		if (can_escape && check_mfc_interrupts(pc + 4))
		{
			spu_runtime::g_escape(this);
		}

		if (!pending)
		{
			break;
		}

		if (!must_finish && g_cfg.core.mfc_shuffling_in_steps)
		{
			// Exit early, not all pending commands have to be executed at a single iteration
			// Update last timestamp so the next MFC timeout check will use the current time
			mfc_last_timestamp = get_system_time();
			return true;
		}
	}

	return false;
}
u32 spu_thread::get_mfc_completed() const
{
	return ch_tag_mask & ~mfc_fence;
}
bool spu_thread::check_mfc_interrupts(u32 next_pc)
{
	if (interrupts_enabled && ch_events.load().count && std::exchange(interrupts_enabled, false))
	{
		cancel_dec_interrupt();
		srr0 = next_pc;

		// Test for BR/BRA instructions (they are equivalent at zero pc)
		const u32 br = _ref<u32>(0);
		pc = (br & 0xfd80007f) == 0x30000000 ? (br >> 5) & 0x3fffc : 0;
		return true;
	}

	return false;
}
[[gnu::noinline]] u16 mask(u32 mfc_size) {
auto get_exec_mask = [&size = mfc_size]
	{
		// Get commands' execution mask
		const u32 shuffle_count = std::min<u32>(g_cfg.core.mfc_transfers_shuffling, size);
		if (!shuffle_count)
		{
			// All commands are enabled. Reading the host clock cannot affect
			// this mask, including an empty queue with shuffling enabled.
			return u16{0xffff};
		}

		return static_cast<u16>((0 - (1u << shuffle_count)) | utils::get_tsc());
	};
return get_exec_mask();
}
}

namespace after {
struct spu_thread : State {
    bool do_mfc(bool can_escape, bool must_finish);
    u32 get_mfc_completed() const;
    bool check_mfc_interrupts(u32 next_pc);
};
bool spu_thread::do_mfc(bool can_escape, bool must_finish)
{
	u32 removed = 0;
	u32 barrier = 0;
	u32 fence = 0;
	u16 exec_mask = 0;
	bool pending = false;

	auto process_command = [&](spu_mfc_cmd& args)
	{
		// Select tag bit in the tag mask or the stall mask
		const u32 mask = std::rotl<u32>(1, args.tag);

		if ((args.cmd & ~0xc) == MFC_BARRIER_CMD)
		{
			if (&args - mfc_queue <= removed)
			{
				// Remove barrier-class command if it's the first in the queue
				atomic_fence_seq_cst();
				removed++;
				return true;
			}

			// Block all tags
			barrier |= -1;
			fence |= mask;
			return false;
		}

		if (barrier & mask)
		{
			fence |= mask;
			return false;
		}

		if (args.cmd & (MFC_BARRIER_MASK | MFC_FENCE_MASK) && fence & mask)
		{
			if (args.cmd & MFC_BARRIER_MASK)
			{
				barrier |= mask;
			}

			return false;
		}

		// If command is not enabled in execution mask, execute it later
		if (!(exec_mask & (1u << (&args - mfc_queue))))
		{
			if (args.cmd & MFC_BARRIER_MASK)
			{
				barrier |= mask;
			}

			// Fence is set for any command
			fence |= mask;
			pending = true;
			return false;
		}

		if (args.cmd & MFC_LIST_MASK)
		{
			if (!(args.tag & 0x80))
			{
				if (do_list_transfer(args))
				{
					removed++;
					return true;
				}
			}

			if (args.cmd & MFC_BARRIER_MASK)
			{
				barrier |= mask;
			}

			fence |= mask;
			return false;
		}

		if (args.cmd == MFC_PUTQLLUC_CMD)
		{
			if (fence & mask)
			{
				return false;
			}

			do_putlluc(args);
		}
		else if (args.size)
		{
			do_dma_transfer(this, args, ls);
		}

		removed++;
		return true;
	};

	auto get_exec_mask = [&size = mfc_size]
	{
		// Get commands' execution mask
		const u32 shuffle_limit = g_cfg.core.mfc_transfers_shuffling;
		if (!shuffle_limit || !size)
		{
			// All commands are enabled. Reading the host clock cannot affect
			// this mask, including an empty queue with shuffling enabled.
			return u16{0xffff};
		}

		return static_cast<u16>((0 - (1u << std::min(shuffle_limit, size))) | utils::get_tsc());
	};

	// Process enqueued commands
	while (true)
	{
		removed = 0;
		barrier = 0;
		fence = 0;

		// Shuffle commands execution (if enabled), explicit barriers are obeyed
		pending = false;
		exec_mask = get_exec_mask();

		static_cast<void>(std::remove_if(mfc_queue + 0, mfc_queue + mfc_size, process_command));

		mfc_size -= removed;
		mfc_barrier = barrier;
		mfc_fence = fence;

		if (removed && ch_tag_upd)
		{
			const u32 completed = get_mfc_completed();

			if (completed && ch_tag_upd == MFC_TAG_UPDATE_ANY)
			{
				ch_tag_stat.set_value(completed);
				ch_tag_upd = MFC_TAG_UPDATE_IMMEDIATE;
			}
			else if (completed == ch_tag_mask && ch_tag_upd == MFC_TAG_UPDATE_ALL)
			{
				ch_tag_stat.set_value(completed);
				ch_tag_upd = MFC_TAG_UPDATE_IMMEDIATE;
			}
		}

		if (can_escape && check_mfc_interrupts(pc + 4))
		{
			spu_runtime::g_escape(this);
		}

		if (!pending)
		{
			break;
		}

		if (!must_finish && g_cfg.core.mfc_shuffling_in_steps)
		{
			// Exit early, not all pending commands have to be executed at a single iteration
			// Update last timestamp so the next MFC timeout check will use the current time
			mfc_last_timestamp = get_system_time();
			return true;
		}
	}

	return false;
}
u32 spu_thread::get_mfc_completed() const
{
	return ch_tag_mask & ~mfc_fence;
}
bool spu_thread::check_mfc_interrupts(u32 next_pc)
{
	if (interrupts_enabled && ch_events.load().count && std::exchange(interrupts_enabled, false))
	{
		cancel_dec_interrupt();
		srr0 = next_pc;

		// Test for BR/BRA instructions (they are equivalent at zero pc)
		const u32 br = _ref<u32>(0);
		pc = (br & 0xfd80007f) == 0x30000000 ? (br >> 5) & 0x3fffc : 0;
		return true;
	}

	return false;
}
[[gnu::noinline]] u16 mask(u32 mfc_size) {
auto get_exec_mask = [&size = mfc_size]
	{
		// Get commands' execution mask
		const u32 shuffle_limit = g_cfg.core.mfc_transfers_shuffling;
		if (!shuffle_limit || !size)
		{
			// All commands are enabled. Reading the host clock cannot affect
			// this mask, including an empty queue with shuffling enabled.
			return u16{0xffff};
		}

		return static_cast<u16>((0 - (1u << std::min(shuffle_limit, size))) | utils::get_tsc());
	};
return get_exec_mask();
}
}


struct Counts {
    u64 mask_cases{}, zero_masks{}, enabled_masks{}, old_mask_clocks{}, new_mask_clocks{};
    u64 queue_scenarios{}, queue_calls{}, old_zero_queue_clocks{}, new_zero_queue_clocks{};
    u64 empty_escapes{}, tags{}, barriers{}, deferrals{}, resumptions{};
} counts;

void masks() {
    utils::fixed = true;
    for (u32 limit = 0; limit <= 16; ++limit) for (u32 size = 0; size <= 16; ++size) {
        g_cfg.core.mfc_transfers_shuffling = limit;
        for (u32 bits = 0; bits != 65536; ++bits) {
            // High timestamp bits must not affect the 16-bit result.
            utils::sample = (u64{bits ^ 0xa5a5u} << 32) | bits;
            utils::clock_calls = 0;
            const u16 old = before::mask(size);
            const u64 old_calls = utils::clock_calls;
            utils::clock_calls = 0;
            const u16 fresh = after::mask(size);
            const u64 new_calls = utils::clock_calls;
            assert(old == fresh && old_calls == (limit && size ? 1u : 0u));
            assert(new_calls == (limit && size ? 1u : 0u));
            if (!limit || !size) { assert(fresh == 0xffff); ++counts.zero_masks; }
            else ++counts.enabled_masks;
            ++counts.mask_cases;
            counts.old_mask_clocks += old_calls;
            counts.new_mask_clocks += new_calls;
        }
    }
}

u32 random_word(u32& state) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5;
    return state;
}
State fixture(u32 seed, u32 tag_update, u32 interrupt_mode) {
    State state;
    u32 random = seed + 1;
    state.mfc_size = seed % 17;
    state.ch_tag_mask = random_word(random);
    state.ch_tag_upd = tag_update;
    state.ch_tag_stat = {0xc001d00d,1};
    state.ch_events.value.count = interrupt_mode != 0;
    state.interrupts_enabled = interrupt_mode == 1;
    state.interrupt_word = seed % 2 ? 0x30000100 : 0;
    state.pc += seed * 4;
    constexpr std::array<MFC,15> commands{
        MFC_PUT_CMD,MFC_PUTB_CMD,MFC_PUTF_CMD,MFC_GET_CMD,MFC_GETB_CMD,MFC_GETF_CMD,
        MFC_PUTL_CMD,MFC_PUTLB_CMD,MFC_PUTLF_CMD,MFC_GETL_CMD,MFC_GETLB_CMD,
        MFC_PUTQLLUC_CMD,MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD};
    for (u32 i = 0; i != state.mfc_size; ++i) {
        auto& command = state.mfc_queue[i];
        command.cmd = commands[random_word(random) % commands.size()];
        command.tag = random_word(random) % 32;
        command.size = (i % 4) * 16;
        command.lsa = 0x200 + i * 64;
        command.eal = 0x10000 + i * 64;
        command.eah = i + 1;
        if (command.cmd & MFC_LIST_MASK) {
            command.size = 8 + command.size;
            if (random_word(random) % 4 == 0) command.tag |= 0x80;
        }
    }
    return state;
}
auto snapshot(const State& state) {
    return std::tuple{state.mfc_size,state.mfc_barrier,state.mfc_fence,state.ch_tag_mask,
        state.ch_tag_upd,state.pc,state.srr0,state.mfc_last_timestamp,state.system_reads,
        state.ch_tag_stat.value,state.ch_tag_stat.count,state.ch_events.value.count,
        state.interrupts_enabled,state.timer_armed};
}
template<class Thread> std::pair<bool,bool> invoke(Thread& thread, u64 sample, bool can_escape, bool must_finish) {
    active = &thread;
    utils::clock_calls = 0; utils::sample = sample; utils::fixed = false;
    bool pending = false, escaped = false;
    try { pending = thread.do_mfc(can_escape,must_finish); }
    catch (const Escaped&) { escaped = true; }
    thread.clock_reads = utils::clock_calls;
    active = nullptr;
    return {pending,escaped};
}
void compare(before::spu_thread& old, after::spu_thread& fresh, u64 sample, bool can_escape, bool must_finish) {
    const auto initial_size = old.mfc_size;
    const auto old_result = invoke(old,sample,can_escape,must_finish);
    const auto fresh_result = invoke(fresh,sample,can_escape,must_finish);
    assert(old_result == fresh_result);
    assert(snapshot(old) == snapshot(fresh));
    assert(old.actions == fresh.actions);
    assert(std::memcmp(old.mfc_queue,fresh.mfc_queue,sizeof(old.mfc_queue)) == 0);
    if (!g_cfg.core.mfc_transfers_shuffling) {
        counts.old_zero_queue_clocks += old.clock_reads;
        counts.new_zero_queue_clocks += fresh.clock_reads;
        assert(old.clock_reads == 0 && fresh.clock_reads == 0);
    } else if (initial_size) assert(old.clock_reads == fresh.clock_reads);
    else assert(old.clock_reads == 0 && fresh.clock_reads == 0);
    if (!initial_size && old_result.second) ++counts.empty_escapes;
    if (old_result.first) ++counts.deferrals;
    for (const auto& record : fresh.actions) {
        if (std::get<0>(record) == Action::tag) ++counts.tags;
        if (std::get<0>(record) == Action::barrier) ++counts.barriers;
    }
    old.actions.clear(); fresh.actions.clear();
    ++counts.queue_calls;
}
void queues() {
    for (u32 seed = 0; seed != 64; ++seed) for (u32 limit = 0; limit <= 16; ++limit)
    for (bool steps : {false,true}) for (bool must_finish : {false,true})
    for (bool can_escape : {false,true}) for (u32 tag_update = 0; tag_update != 3; ++tag_update)
    for (u32 interrupt_mode = 0; interrupt_mode != 3; ++interrupt_mode) {
        g_cfg.core.mfc_transfers_shuffling = limit;
        g_cfg.core.mfc_shuffling_in_steps = steps;
        before::spu_thread old; after::spu_thread fresh;
        static_cast<State&>(old) = fixture(seed,tag_update,interrupt_mode);
        static_cast<State&>(fresh) = static_cast<State&>(old);
        const u64 sample = (u64{seed} << 37) | (seed * 0x12345u);
        compare(old,fresh,sample,can_escape,must_finish);
        for (u32 i = 0; i != old.mfc_size; ++i) {
            if (old.mfc_queue[i].tag & 0x80) ++counts.resumptions;
            old.mfc_queue[i].tag &= 0x7f;
            fresh.mfc_queue[i].tag &= 0x7f;
        }
        old.complete_lists = fresh.complete_lists = true;
        compare(old,fresh,sample,true,true);
        compare(old,fresh,sample,false,true);
        assert(old.mfc_size == 0 && fresh.mfc_size == 0);
        assert(old.mfc_fence == 0 && old.mfc_barrier == 0);
        ++counts.queue_scenarios;
    }
}

int main() {
    masks(); queues();
    std::cout << "{\"passed\":true,\"assertionsActive\":true,"
        "\"maskCases\":" << counts.mask_cases <<
        ",\"noShuffleOrEmptyMaskCases\":" << counts.zero_masks <<
        ",\"enabledNonemptyMaskCases\":" << counts.enabled_masks <<
        ",\"baselineMaskClockReads\":" << counts.old_mask_clocks <<
        ",\"candidateMaskClockReads\":" << counts.new_mask_clocks <<
        ",\"queueScenarios\":" << counts.queue_scenarios <<
        ",\"queueCalls\":" << counts.queue_calls <<
        ",\"baselineZeroLimitQueueClockReads\":" << counts.old_zero_queue_clocks <<
        ",\"candidateZeroLimitQueueClockReads\":" << counts.new_zero_queue_clocks <<
        ",\"emptyQueueInterruptEscapes\":" << counts.empty_escapes <<
        ",\"deliveredTags\":" << counts.tags <<
        ",\"executedBarriers\":" << counts.barriers <<
        ",\"stepDeferrals\":" << counts.deferrals <<
        ",\"listResumptions\":" << counts.resumptions << "}\n";
}
