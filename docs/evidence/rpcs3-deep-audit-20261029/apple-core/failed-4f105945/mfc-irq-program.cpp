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

#include <functional>
#include <set>
constexpr u32 MFC_Cmd=21;
enum class cpu_flag { wait, again };
struct Flags {
 u32 bits{};
 u32 add_fetch(cpu_flag bit) { bits |= 1u<<u32(bit); return bits; }
 bool operator&(cpu_flag bit) const { return (bits & (1u<<u32(bit)))!=0; }
};
inline bool is_stopped(u32 value) { return (value&0x80000000u)!=0; }
std::function<void()> wait_action;
u64 wait_calls{};
namespace thread_ctrl { void wait_on(Flags&,u32) { ++wait_calls; assert(wait_action); wait_action(); } }

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
    u32 accepted_commands{};
    Flags state;
    bool stopped{};
    u32 stop_checks{};
    bool test_stopped() { ++stop_checks; return stopped; }

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

namespace production {
struct spu_thread : State {
    bool do_mfc(bool can_escape = true, bool must_finish = true);
    u32 get_mfc_completed() const;
    bool check_mfc_interrupts(u32 next_pc);
spu_mfc_cmd ch_mfc_cmd{};
 bool process_mfc_cmd() {
	// Stall infinitely if MFC queue is full
	while (mfc_size >= 16) [[unlikely]]
	{
		// Reset MFC timestamp in the case of full queue
		mfc_last_timestamp = 0;

		if (test_stopped())
		{
			return false;
		}

		// The new channel command has not been accepted yet. If draining
		// takes an interrupt, resume this WRCH rather than the next instruction.
		do_mfc(false);
		if (check_mfc_interrupts(pc))
		{
			spu_runtime::g_escape(this);
		}

		if (mfc_size < 16)
		{
			break;
		}

		auto old = state.add_fetch(cpu_flag::wait);

		if (is_stopped(old))
		{
			return false;
		}

		thread_ctrl::wait_on(state, old);
	}

 return reference_enqueue(); }
bool process_mfc_cmd_before_irq() {
	// Stall infinitely if MFC queue is full
	while (mfc_size >= 16) [[unlikely]]
	{
		// Reset MFC timestamp in the case of full queue
		mfc_last_timestamp = 0;

		if (test_stopped())
		{
			return false;
		}

		// Process MFC commands
		do_mfc();

		if (mfc_size < 16)
		{
			break;
		}

		auto old = state.add_fetch(cpu_flag::wait);

		if (is_stopped(old))
		{
			return false;
		}

		thread_ctrl::wait_on(state, old);
	}

 return reference_enqueue(); }
bool set_ch_value(u32 ch,u32 value) { switch(ch) { case MFC_Cmd:
	{
		ch_mfc_cmd.cmd = MFC(value & 0xff);
		return process_mfc_cmd();
	} default: throw Escaped{}; } }

bool reference_enqueue() { ++accepted_commands; switch(ch_mfc_cmd.cmd) { case MFC_BARRIER_CMD:
	case MFC_EIEIO_CMD:
	case MFC_SYNC_CMD:
	{
		if (mfc_size == 0)
		{
			atomic_fence_seq_cst();
		}
		else
		{
			mfc_queue[mfc_size++] = ch_mfc_cmd;
			mfc_barrier |= -1;
			mfc_fence |= std::rotl<u32>(1, ch_mfc_cmd.tag);
		}

		return true;
	} default: throw Escaped{}; } }
bool request_tag_update(u32 value) { switch (0) { case 0: {
		if (value > MFC_TAG_UPDATE_ALL)
		{
			break;
		}

		const u32 completed = get_mfc_completed();

		if (!value)
		{
			ch_tag_upd = MFC_TAG_UPDATE_IMMEDIATE;
			ch_tag_stat.set_value(completed);
		}
		else if (completed && value == MFC_TAG_UPDATE_ANY)
		{
			ch_tag_upd = MFC_TAG_UPDATE_IMMEDIATE;
			ch_tag_stat.set_value(completed);
		}
		else if (completed == ch_tag_mask && value == MFC_TAG_UPDATE_ALL)
		{
			ch_tag_upd = MFC_TAG_UPDATE_IMMEDIATE;
			ch_tag_stat.set_value(completed);
		}
		else
		{
			ch_tag_upd = value;
		}

		return true;
	}} return false; }
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

using spu_thread=production::spu_thread;
static void exec_wrch_result(spu_thread* _spu, bool completed)
	{
		if (!completed || _spu->state & cpu_flag::again)
		{
			spu_runtime::g_escape(_spu);
		}

		static_cast<void>(_spu->test_stopped());
	}
static void exec_wrch(spu_thread* _spu, u32 ch, u32 value)
	{
		exec_wrch_result(_spu, _spu->set_ch_value(ch, value));
	}


struct spu_opcode_t {};
namespace spu_interpreter {
// The handler acknowledges the modeled event before IRET; interrupt-control
// instruction flags are not emulated. The real IRET PC assignment is executed.
void set_interrupt_status(spu_thread& spu,spu_opcode_t) { assert(!spu.interrupts_enabled); }
}
bool IRET(spu_thread& spu, spu_opcode_t op)
{
	spu.pc = spu.srr0;
	spu_interpreter::set_interrupt_status(spu, op);
	return false;
}
static void exec_list_unstall(spu_thread* _spu, u32 tag)
	{
		for (u32 i = 0; i < _spu->mfc_size; i++)
		{
			if (_spu->mfc_queue[i].tag == (tag | 0x80))
			{
				_spu->mfc_queue[i].tag &= 0x7f;
			}
		}

		_spu->do_mfc();
	}

#include <memory>
#include <stdexcept>
#include <type_traits>

// Evaluates only the integer/pointer/load/store IR operations emitted by the
// extracted fallback. Every memory operation checks the selected allocation.
// LLVM optimization, machine-code emission and native ordering are not modeled.
struct Value {
    u64 bits{}; unsigned width{};
    u64 getZExtValue() const { return bits; }
};
struct Memory {
    u8* base{}; std::size_t length{}, offset{};
};
struct GuardedAccess : std::runtime_error { GuardedAccess():std::runtime_error("guarded invalid MFC slot"){} };
Memory _ptr(Memory base, Value* offset) { base.offset += offset->bits; return base; }
Memory _ptr(Memory base, u64 offset) { base.offset += offset; return base; }
template<class C,class T> Memory _ptr(Memory base,T C::*member) {
    C layout{};
    base.offset += reinterpret_cast<const u8*>(&(layout.*member))-reinterpret_cast<const u8*>(&layout);
    return base;
}
template<class T> constexpr unsigned get_type() { return sizeof(T); }
namespace llvm {
struct BasicBlock { static u64 Create(int,const char*,int) { static u64 id=2; return id++; } };
}
struct Builder {
    std::set<u64> reachable{0}; bool executing=true;

    std::vector<std::unique_ptr<Value>> values;
    u32 writes{}, queue_writes{};
    Value* value(u64 bits,unsigned width) {
        if(width<8) bits &= (u64{1}<<(8*width))-1;
        values.push_back(std::make_unique<Value>(Value{bits,width})); return values.back().get();
    }
    Value* getInt32(u32 bits) { return value(bits,4); }
    static u8* checked(Memory memory,unsigned bytes) {
        if(!memory.base || memory.offset>memory.length || bytes>memory.length-memory.offset) throw GuardedAccess{};
        return memory.base+memory.offset;
    }
    Value* CreateLoad(unsigned width,Memory memory) {
        u64 bits{}; if(executing)std::memcpy(&bits,checked(memory,width),width); return value(bits,width);
    }
    void CreateStore(Value* input,Memory memory) {
        if(!executing){return;} std::memcpy(checked(memory,input->width),&input->bits,input->width); ++writes;
        if(memory.offset<sizeof(State::mfc_queue))++queue_writes;
    }
    Value* CreateAdd(Value* a,Value* b) { return value(a->bits+b->bits,a->width); }
    Value* CreateMul(Value* a,Value* b) { return value(a->bits*b->bits,a->width); }
    Value* CreateOr(Value* a,Value* b) { return value(a->bits|b->bits,a->width); }
    Value* CreateZExt(Value* a,unsigned width) { return value(a->bits,width); }
    Value* CreateICmpULT(Value* a,Value* b) { return value(a->bits<b->bits,1); }
    Memory CreateSelect(Value* condition,Memory yes,Memory no) { return condition->bits?yes:no; }
    void SetInsertPoint(u64 block) { executing=reachable.contains(block); }
void CreateBr(u64 block) { if(executing)reachable.insert(block); }
void CreateCondBr(Value* condition,u64 yes,u64 no,int) { if(executing)reachable.insert(condition->bits?yes:no); }
    [[noreturn]] void CreateUnreachable() { throw std::logic_error("unexpected IR unreachable"); }
};
template<class C,class T> u32 offset32(T C::*member) {
    C layout{};
    return static_cast<u32>(reinterpret_cast<const u8*>(&(layout.*member))-reinterpret_cast<const u8*>(&layout));
}
struct Scalar { Value* value{}; };
struct Emitter {
    using spu_thread=State;
    Builder storage;
    Builder* m_ir=&storage;
    Memory m_thread,m_memptr{};
    Scalar tag,size,lsa,eal;
    Value* mask{}; Value* ci{};
    Memory pf,pb;
    
    int fail=0,next=1,m_context{},m_function{},m_md_likely{};
    Scalar val;
    ::spu_thread* thread{};
    u32 gpr_fences{},helper_calls{};
    void update_pc() { if(storage.executing)thread->pc=0x1240; }
    void ensure_gpr_stores() { ++gpr_fences; }
    void call(const char*,void(*function)(::spu_thread*,u32,u32),Memory,Value* ch,Value* command) {
        if(!storage.executing)return;
        assert(thread->pc==0x1240 && gpr_fences==1);
        ++helper_calls;active=thread;
        function(thread,static_cast<u32>(ch->bits),static_cast<u32>(command->bits));
    }

    Emitter(State& state,MFC cmd,u8 desired_tag):m_thread{reinterpret_cast<u8*>(&state),sizeof(state),0} {
        thread=static_cast<::spu_thread*>(&state); val.value=storage.value(cmd,4);
        thread->ch_mfc_cmd={cmd,desired_tag,16,0x40,0x60300510,0};
        tag.value=storage.value(desired_tag,1); size.value=storage.value(16,2);
        lsa.value=storage.value(0x40,4); eal.value=storage.value(0x60300510,4);
        mask=storage.getInt32(1u<<desired_tag); ci=storage.value(cmd,1);
        pf=spu_ptr(&State::mfc_fence); pb=spu_ptr(&State::mfc_barrier);
    }
    template<class T> Memory spu_ptr(T State::*member) { return _ptr(m_thread,member); }
    void before() {
        // Fallback: enqueue the command
				m_ir->SetInsertPoint(fail);

				// Get MFC slot, redirect to invalid memory address
				const auto slot = m_ir->CreateLoad(get_type<u32>(), spu_ptr(&spu_thread::mfc_size));
				const auto off0 = m_ir->CreateAdd(m_ir->CreateMul(slot, m_ir->getInt32(sizeof(spu_mfc_cmd))), m_ir->getInt32(::offset32(&spu_thread::mfc_queue)));
				const auto ptr0 = _ptr(m_thread, m_ir->CreateZExt(off0, get_type<u64>()));
				const auto ptr1 = _ptr(m_memptr, 0xffdeadf0);
				const auto pmfc = m_ir->CreateSelect(m_ir->CreateICmpULT(slot, m_ir->getInt32(16)), ptr0, ptr1);
				m_ir->CreateStore(ci, _ptr(pmfc, &spu_mfc_cmd::cmd));

				switch (u64 cmd = ci->getZExtValue())
				{
				case MFC_GETLLAR_CMD:
				case MFC_PUTLLC_CMD:
				case MFC_PUTLLUC_CMD:
				case MFC_PUTQLLUC_CMD:
				{
					break;
				}
				case MFC_PUTL_CMD:
				case MFC_PUTLB_CMD:
				case MFC_PUTLF_CMD:
				case MFC_PUTRL_CMD:
				case MFC_PUTRLB_CMD:
				case MFC_PUTRLF_CMD:
				case MFC_GETL_CMD:
				case MFC_GETLB_CMD:
				case MFC_GETLF_CMD:
				{
					break;
				}
				case MFC_SDCRZ_CMD:
				{
					break;
				}
				case MFC_SNDSIG_CMD:
				case MFC_SNDSIGB_CMD:
				case MFC_SNDSIGF_CMD:
				case MFC_PUT_CMD:
				case MFC_PUTB_CMD:
				case MFC_PUTF_CMD:
				case MFC_PUTR_CMD:
				case MFC_PUTRB_CMD:
				case MFC_PUTRF_CMD:
				case MFC_GET_CMD:
				case MFC_GETB_CMD:
				case MFC_GETF_CMD:
				{
					m_ir->CreateStore(tag.value, _ptr(pmfc, &spu_mfc_cmd::tag));
					m_ir->CreateStore(size.value, _ptr(pmfc, &spu_mfc_cmd::size));
					m_ir->CreateStore(lsa.value, _ptr(pmfc, &spu_mfc_cmd::lsa));
					m_ir->CreateStore(eal.value, _ptr(pmfc, &spu_mfc_cmd::eal));
					m_ir->CreateStore(m_ir->CreateOr(m_ir->CreateLoad(get_type<u32>(), pf), mask), pf);
					if (cmd & MFC_BARRIER_MASK)
						m_ir->CreateStore(m_ir->CreateOr(m_ir->CreateLoad(get_type<u32>(), pb), mask), pb);
					break;
				}
				case MFC_BARRIER_CMD:
				case MFC_EIEIO_CMD:
				case MFC_SYNC_CMD:
				{
					m_ir->CreateStore(m_ir->getInt32(-1), pb);
					m_ir->CreateStore(m_ir->CreateOr(m_ir->CreateLoad(get_type<u32>(), pf), mask), pf);
					break;
				}
				default:
				{
					m_ir->CreateUnreachable();
					break;
				}
				}

				m_ir->CreateStore(m_ir->CreateAdd(slot, m_ir->getInt32(1)), spu_ptr(&spu_thread::mfc_size));
				m_ir->CreateBr(next);
				m_ir->SetInsertPoint(next);
				return;
    }
    void after() {
        // Fallback: enqueue the command
				m_ir->SetInsertPoint(fail);

				// Get MFC slot, redirect to invalid memory address
				const auto slot = m_ir->CreateLoad(get_type<u32>(), spu_ptr(&spu_thread::mfc_size));

				// A full queue is a blocking channel write, not a guest HALT.
				const auto full = llvm::BasicBlock::Create(m_context, "", m_function);
				const auto enqueue = llvm::BasicBlock::Create(m_context, "", m_function);
				m_ir->CreateCondBr(m_ir->CreateICmpULT(slot, m_ir->getInt32(16)), enqueue, full, m_md_likely);
				m_ir->SetInsertPoint(full);
				update_pc();
				ensure_gpr_stores();
				call("spu_write_channel", &exec_wrch, m_thread, m_ir->getInt32(MFC_Cmd), val.value);
				m_ir->CreateBr(next);
				m_ir->SetInsertPoint(enqueue);

				const auto off0 = m_ir->CreateAdd(m_ir->CreateMul(slot, m_ir->getInt32(sizeof(spu_mfc_cmd))), m_ir->getInt32(::offset32(&spu_thread::mfc_queue)));
				const auto ptr0 = _ptr(m_thread, m_ir->CreateZExt(off0, get_type<u64>()));
				const auto ptr1 = _ptr(m_memptr, 0xffdeadf0);
				const auto pmfc = m_ir->CreateSelect(m_ir->CreateICmpULT(slot, m_ir->getInt32(16)), ptr0, ptr1);
				m_ir->CreateStore(ci, _ptr(pmfc, &spu_mfc_cmd::cmd));

				switch (u64 cmd = ci->getZExtValue())
				{
				case MFC_GETLLAR_CMD:
				case MFC_PUTLLC_CMD:
				case MFC_PUTLLUC_CMD:
				case MFC_PUTQLLUC_CMD:
				{
					break;
				}
				case MFC_PUTL_CMD:
				case MFC_PUTLB_CMD:
				case MFC_PUTLF_CMD:
				case MFC_PUTRL_CMD:
				case MFC_PUTRLB_CMD:
				case MFC_PUTRLF_CMD:
				case MFC_GETL_CMD:
				case MFC_GETLB_CMD:
				case MFC_GETLF_CMD:
				{
					break;
				}
				case MFC_SDCRZ_CMD:
				{
					break;
				}
				case MFC_SNDSIG_CMD:
				case MFC_SNDSIGB_CMD:
				case MFC_SNDSIGF_CMD:
				case MFC_PUT_CMD:
				case MFC_PUTB_CMD:
				case MFC_PUTF_CMD:
				case MFC_PUTR_CMD:
				case MFC_PUTRB_CMD:
				case MFC_PUTRF_CMD:
				case MFC_GET_CMD:
				case MFC_GETB_CMD:
				case MFC_GETF_CMD:
				{
					m_ir->CreateStore(tag.value, _ptr(pmfc, &spu_mfc_cmd::tag));
					m_ir->CreateStore(size.value, _ptr(pmfc, &spu_mfc_cmd::size));
					m_ir->CreateStore(lsa.value, _ptr(pmfc, &spu_mfc_cmd::lsa));
					m_ir->CreateStore(eal.value, _ptr(pmfc, &spu_mfc_cmd::eal));
					m_ir->CreateStore(m_ir->CreateOr(m_ir->CreateLoad(get_type<u32>(), pf), mask), pf);
					if (cmd & MFC_BARRIER_MASK)
						m_ir->CreateStore(m_ir->CreateOr(m_ir->CreateLoad(get_type<u32>(), pb), mask), pb);
					break;
				}
				case MFC_BARRIER_CMD:
				case MFC_EIEIO_CMD:
				case MFC_SYNC_CMD:
				{
					m_ir->CreateStore(tag.value, _ptr(pmfc, &spu_mfc_cmd::tag));
					m_ir->CreateStore(m_ir->getInt32(-1), pb);
					m_ir->CreateStore(m_ir->CreateOr(m_ir->CreateLoad(get_type<u32>(), pf), mask), pf);
					break;
				}
				default:
				{
					m_ir->CreateUnreachable();
					break;
				}
				}

				m_ir->CreateStore(m_ir->CreateAdd(slot, m_ir->getInt32(1)), spu_ptr(&spu_thread::mfc_size));
				m_ir->CreateBr(next);
				m_ir->SetInsertPoint(next);
				return;
    }
};

u64 scenarios{},premature_before{},premature_after{},matched_after{},stale_slot_cases{},full_queue_guards{},unchanged_dma{};
using Thread=production::spu_thread;
Thread fixture(u32 desired,u32 stale,MFC command,u32 prior_count) {
    Thread thread;
    thread.mfc_fence=thread.mfc_barrier=0;
    for(u32 i=0;i<prior_count;++i) {
        const u8 list_tag=static_cast<u8>((desired+13)%32);
        thread.mfc_queue[i]={MFC_GETL_CMD,static_cast<u8>(list_tag|0x80),16,0,0,1};
        thread.mfc_fence|=1u<<list_tag;
    }
    thread.mfc_size=prior_count;
    thread.mfc_queue[prior_count]={MFC_PUT_CMD,static_cast<u8>(stale),4096,0xaaaaaaaa,0xbbbbbbbb,0xcccccccc};
    thread.ch_tag_mask=1u<<desired;
    thread.ch_tag_upd=MFC_TAG_UPDATE_IMMEDIATE;
    // Reference C++ enqueue copies the complete current command.
    (void)command;
    return thread;
}
void sweep(Thread& thread) {
    active=&thread; g_cfg.core.mfc_transfers_shuffling=0;
    assert(!thread.do_mfc(false,true)); active=nullptr;
}
void tag_query(Thread& thread) {
    active=&thread; assert(thread.request_tag_update(MFC_TAG_UPDATE_ALL)); active=nullptr;
}
void resume(Thread& thread) {
    thread.complete_lists=true;
    for(u32 i=0;i<thread.mfc_size;++i)thread.mfc_queue[i].tag&=0x7f;
    sweep(thread);
    assert(thread.mfc_size==0 && thread.mfc_barrier==0 && thread.mfc_fence==0);
    assert(thread.get_mfc_completed()==thread.ch_tag_mask);
}
int tag_cases() {
    // All legal current tags, all stale byte values (including stalled-list
    // tags) and all three barrier opcodes; exercise first and last valid slots.
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})
    for(u32 desired=0;desired<32;++desired)for(u32 stale=0;stale<256;++stale)
    for(u32 prior_count:{1u,15u}) {
        Thread old=fixture(desired,stale,command,prior_count),fresh=old,reference=old;
        Emitter old_ir(old,command,desired),new_ir(fresh,command,desired);
        old_ir.before();new_ir.after();
        reference.ch_mfc_cmd={command,static_cast<u8>(desired),16,0x40,0x60300510,0};
        active=&reference;assert(reference.reference_enqueue());active=nullptr;
        assert(fresh.mfc_queue[prior_count].tag==desired);
        assert(old.mfc_queue[prior_count].tag==stale);
        assert(new_ir.storage.writes==old_ir.storage.writes+1);
        // Tag is the only additional write; irrelevant payload remains untouched.
        assert(fresh.mfc_queue[prior_count].size==4096 && fresh.mfc_queue[prior_count].lsa==0xaaaaaaaa);
        sweep(old);sweep(fresh);sweep(reference);
        assert(fresh.mfc_size==prior_count+1 && reference.mfc_size==fresh.mfc_size);
        assert(fresh.mfc_barrier==reference.mfc_barrier && fresh.mfc_fence==reference.mfc_fence);
        assert(fresh.actions.empty() && reference.actions.empty());
        tag_query(old);tag_query(fresh);tag_query(reference);
        if(old.ch_tag_stat.count)++premature_before;
        if(fresh.ch_tag_stat.count)++premature_after;
        assert(!fresh.ch_tag_stat.count && fresh.ch_tag_upd==MFC_TAG_UPDATE_ALL);
        assert(fresh.get_mfc_completed()==0);
        assert(fresh.ch_tag_upd==reference.ch_tag_upd);
        resume(fresh);resume(reference);
        assert(fresh.actions==reference.actions && fresh.ch_tag_stat.value==reference.ch_tag_stat.value);
        ++scenarios;++matched_after;if(stale!=desired)++stale_slot_cases;
    }
    // Unchanged queue encodings for ordinary fenced/unfenced DMA commands.
    for(MFC command:{MFC_PUT_CMD,MFC_PUTB_CMD,MFC_PUTF_CMD,MFC_GET_CMD,MFC_GETB_CMD,MFC_GETF_CMD})
    for(u32 tag=0;tag<32;++tag) {
        Thread old=fixture(tag,255,command,1),fresh=old;
        Emitter a(old,command,tag),b(fresh,command,tag);a.before();b.after();
        assert(std::memcmp(old.mfc_queue,fresh.mfc_queue,sizeof(old.mfc_queue))==0);
        assert(old.mfc_fence==fresh.mfc_fence && old.mfc_barrier==fresh.mfc_barrier);
        assert(a.storage.writes==b.storage.writes);++unchanged_dma;
    }
    // The existing invalid-slot selection still guards a full queue before a
    // write can occur; the patch adds no bypass or out-of-bounds publication.
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(bool candidate:{false}) {
        Thread thread;thread.mfc_size=16;Emitter emitter(thread,command,31);
        bool caught=false;try{if(candidate)emitter.after();else emitter.before();}catch(const GuardedAccess&){caught=true;}
        assert(caught && emitter.storage.writes==0 && thread.mfc_size==16);++full_queue_guards;
    }
    assert(premature_before==3u*32u*248u*2u && premature_after==0);
    std::cout<<"{\"passed\":true,\"scenarios\":"<<scenarios<<",\"baselinePrematureCompletions\":"<<premature_before
        <<",\"candidatePrematureCompletions\":"<<premature_after<<",\"candidateMatchesReference\":"<<matched_after
        <<",\"staleSlotCases\":"<<stale_slot_cases<<",\"fullQueueGuards\":"<<full_queue_guards
        <<",\"unchangedDMAEncodings\":"<<unchanged_dma<<",\"barriersPreservedUntilListAck\":true,\"publicationOrderPreserved\":true}";
    return 0;
}

u64 recovered{},stop_cases{},again_cases{},wait_cases{},interrupt_cases{},baseline_halts{},successful_retries{};
Thread full_fixture(u32 tag) {
    Thread thread;
    thread.mfc_size=16;thread.mfc_barrier=thread.mfc_fence=0;
    for(u32 i=0;i<16;++i){thread.mfc_queue[i]={MFC_PUT_CMD,static_cast<u8>((tag+i)%32),16,i*16,0x10000+i*16,i};thread.mfc_fence|=1u<<thread.mfc_queue[i].tag;}
    return thread;
}
void full_cases() {
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(u32 tag=0;tag<32;++tag) {
        // A legitimate pending queue can drain; no list acknowledgement needed.
        Thread old=full_fixture(tag),fresh=old;
        Emitter original(old,command,tag),fixed(fresh,command,tag);
        bool halted=false;try{original.before();}catch(const GuardedAccess&){halted=true;}
        assert(halted&&old.mfc_size==16&&old.actions.empty());++baseline_halts;
        utils::fixed=true;utils::sample=0xffff;g_cfg.core.mfc_transfers_shuffling=16;
        active=&fresh;fixed.after();active=nullptr;
        assert(fresh.mfc_size==0&&fixed.helper_calls==1&&fixed.storage.queue_writes==0);
        assert(fresh.actions.size()==17&&std::get<0>(fresh.actions.back())==Action::barrier);
        assert(fixed.storage.reachable.contains(1));++recovered;

        // Stop before any DMA: the command must remain current for a retry at
        // the same WRCH PC, and nothing may be appended to the full queue.
        Thread stopped=full_fixture(tag);stopped.stopped=true;
        Emitter stop(stopped,command,tag);bool escaped=false;
        try{stop.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&stopped.pc==0x1240&&stopped.mfc_size==16&&stopped.ch_mfc_cmd.cmd==command);
        assert(stopped.actions.size()==1&&std::get<0>(stopped.actions[0])==Action::escape);
        assert(!stop.storage.reachable.contains(1)&&stop.storage.queue_writes==0);++stop_cases;
        stopped.stopped=false;stopped.actions.clear();Emitter retry(stopped,command,tag);retry.after();
        assert(stopped.mfc_size==0&&retry.helper_calls==1&&stopped.actions.size()==17);++successful_retries;

        // The generic WRCH helper's preexisting ::again contract is retained.
        Thread again=full_fixture(tag);again.state.bits=1u<<u32(cpu_flag::again);
        Emitter repeat(again,command,tag);escaped=false;
        try{repeat.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&again.pc==0x1240&&again.mfc_size==0&&!repeat.storage.reachable.contains(1));++again_cases;

        // A stalled list must stay queued until a wait delivers its ack.
        Thread blocked=full_fixture(tag);blocked.mfc_queue[0].cmd=MFC_GETL_CMD;blocked.mfc_queue[0].tag|=0x80;
        blocked.mfc_queue[1].cmd=MFC_BARRIER_CMD;
        const auto waits_before=wait_calls;bool observed=false;
        wait_action=[&]{assert(blocked.mfc_size==16&&blocked.actions.empty());observed=true;
            blocked.mfc_queue[0].tag&=0x7f;blocked.complete_lists=true;};
        Emitter waiting(blocked,command,tag);waiting.after();wait_action={};
        assert(observed&&wait_calls==waits_before+1&&blocked.mfc_size==0&&waiting.helper_calls==1);++wait_cases;

        // Interruption during the drain is compared with the unchanged generic
        // helper contract; no claim about the complete guest interrupt scheduler.
        Thread interrupt=full_fixture(tag);interrupt.interrupts_enabled=true;interrupt.ch_events.value.count=true;
        Emitter interrupted(interrupt,command,tag);escaped=false;
        try{interrupted.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&!interrupted.storage.reachable.contains(1)&&interrupt.mfc_size==0);
        assert(interrupt.ch_mfc_cmd.cmd==command&&interrupt.srr0==0x1240);++interrupt_cases;
    }
}

u64 historical_irq_skips{},irq_retries{},stalled_irq_acks{},multi_pass_drains{},accepted_once{};
u64 barriers(const Thread& thread) {
    return std::count_if(thread.actions.begin(),thread.actions.end(),[](const auto& action){return std::get<0>(action)==Action::barrier;});
}
void irq_cases() {
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(u32 tag=0;tag<32;++tag) {
        g_cfg.core.mfc_transfers_shuffling=16;
        g_cfg.core.mfc_shuffling_in_steps=false;
        // An event is already pending before draining, and the non-stepping
        // clock sequence requires more than one mask to empty this queue.
        Thread historical=full_fixture(tag);
        historical.pc=0x1240;historical.interrupts_enabled=true;historical.ch_events.value.count=true;
        historical.ch_mfc_cmd={command,static_cast<u8>(tag),16,0x40,0x60300510,0};
        utils::fixed=false;utils::sample=0;utils::clock_calls=0;active=&historical;
        bool escaped=false;
        try{historical.process_mfc_cmd_before_irq();}catch(const Escaped&){escaped=true;}
        assert(escaped&&historical.srr0==0x1244&&historical.accepted_commands==0&&barriers(historical)==0);
        assert(utils::clock_calls==1);
        historical.ch_events.value.count=false;
        assert(!IRET(historical,{}));
        assert(historical.pc==0x1244&&historical.ch_mfc_cmd.cmd==command);++historical_irq_skips;

        Thread current=full_fixture(tag);
        current.interrupts_enabled=true;current.ch_events.value.count=true;
        utils::fixed=false;utils::sample=0;utils::clock_calls=0;
        Emitter interrupt(current,command,tag);escaped=false;
        try{interrupt.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&current.srr0==0x1240&&current.mfc_size==0&&current.accepted_commands==0);
        assert(current.ch_mfc_cmd.cmd==command&&barriers(current)==0&&!interrupt.storage.reachable.contains(1));
        assert(utils::clock_calls>1);++multi_pass_drains;
        current.ch_events.value.count=false;
        assert(!IRET(current,{}));assert(current.pc==0x1240);
        active=&current;exec_wrch(&current,MFC_Cmd,command);
        assert(current.accepted_commands==1&&current.mfc_size==0&&barriers(current)==1);
        ++irq_retries;++accepted_once;

        // The full queue cannot drain until its list is acknowledged. An IRQ
        // must remain deliverable before acceptance, even though no slot frees.
        Thread blocked=full_fixture(tag);
        blocked.mfc_queue[0].cmd=MFC_GETL_CMD;blocked.mfc_queue[0].tag|=0x80;
        blocked.mfc_queue[1].cmd=MFC_BARRIER_CMD;
        blocked.interrupts_enabled=true;blocked.ch_events.value.count=true;
        utils::fixed=true;utils::sample=0xffff;utils::clock_calls=0;
        const auto waits=wait_calls;
        Emitter stalled(blocked,command,tag);escaped=false;
        try{stalled.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&blocked.srr0==0x1240&&blocked.mfc_size==16&&blocked.accepted_commands==0);
        assert(blocked.mfc_queue[0].tag&0x80);
        assert(wait_calls==waits&&blocked.actions.size()==2);
        assert(std::get<0>(blocked.actions[0])==Action::cancel&&std::get<0>(blocked.actions[1])==Action::escape);
        // The interrupt handler's explicit ack uses the real unstall helper.
        blocked.ch_events.value.count=false;blocked.complete_lists=true;active=&blocked;
        exec_list_unstall(&blocked,tag);
        assert(blocked.mfc_size==0&&blocked.accepted_commands==0);
        const auto prior_barriers=barriers(blocked);
        assert(!IRET(blocked,{}));assert(blocked.pc==0x1240);
        exec_wrch(&blocked,MFC_Cmd,command);
        assert(blocked.accepted_commands==1&&blocked.mfc_size==0&&barriers(blocked)==prior_barriers+1);
        ++stalled_irq_acks;++accepted_once;
        active=nullptr;
    }
}
int main(){
    std::cout<<"{\"tagRegression\":";tag_cases();full_cases();irq_cases();
    std::cout<<",\"fullQueue\":{\"baselineHalts\":"<<baseline_halts<<",\"recovered\":"<<recovered
        <<",\"stopBeforeDrain\":"<<stop_cases<<",\"successfulRetries\":"<<successful_retries
        <<",\"againEscapes\":"<<again_cases<<",\"stalledListWaits\":"<<wait_cases
        <<",\"interruptDrainEscapes\":"<<interrupt_cases<<",\"noDoubleEnqueue\":true,\"currentPCPreservedOnStop\":true}"
        <<",\"preAcceptanceInterrupt\":{\"historicalSkippedWRCH\":"<<historical_irq_skips
        <<",\"currentPCRetries\":"<<irq_retries<<",\"stalledListIRQAcks\":"<<stalled_irq_acks
        <<",\"multipleMaskPasses\":"<<multi_pass_drains<<",\"commandsAcceptedExactlyOnce\":"<<accepted_once
        <<",\"stepsDisabled\":true,\"eventPendingBeforeDrain\":true}}";
}
