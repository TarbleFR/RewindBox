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
#include <span>
#include <type_traits>
#include <limits>

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
using s64=std::int64_t;
struct MaxValue {template<class T>constexpr operator T()const{return std::numeric_limits<T>::max();}};constexpr MaxValue umax{};
enum cpu_flag:u32 {pending=1,rbx_wait=2,temp=4};
namespace utils {
struct serial {
 bool writing;std::vector<u8> bytes;std::size_t cursor{};
 bool is_writing()const{return writing;}
 template<class T>void one(T&& v){
  using V=std::remove_reference_t<T>;
  if constexpr(requires {v.data();v.size_bytes();}){
   for(auto& x:v)one(x);
  }else{
   static_assert(std::is_trivially_copyable_v<V>);
   if(writing){const auto* p=reinterpret_cast<const u8*>(&v);bytes.insert(bytes.end(),p,p+sizeof(V));}
   else{if constexpr(std::is_const_v<V>){assert(false);}else{assert(cursor+sizeof(V)<=bytes.size());std::memcpy(&v,bytes.data()+cursor,sizeof(V));cursor+=sizeof(V);}}
  }
 }
 template<class... T>void operator()(T&&...v){(one(v),...);}
 operator u8(){u8 v{};one(v);return v;}
};
}

State* active{};
struct Channel {
    union { struct { u32 value, count; }; u64 data{}; };
    u32 get_count()const{return count;}
    template<class T> s64 pop_wait(T&){if(!count)return -1;count=0;return value;}
    void set_value(u32 next);
};
struct Events {
    struct Value { bool count{}; u64 all{}; } value;
    Value& raw(){return value;}
    Value load() const { return value; }
};
using spu_channel=Channel;
struct State {
 u32 state{},last_getllar_addr{};
 bool test_stopped(){return false;}
 void wakeup_delay(){state&=~cpu_flag::rbx_wait;}
 u64 gpr[2]{};
 spu_mfc_cmd ch_mfc_cmd{},mfc_prxy_cmd{};
 u32 mfc_prxy_mask{},ch_stall_mask{},snr_config{},run_ctrl{};
 struct {u64 all{};}mfc_prxy_write_state;
 Channel ch_stall_stat,ch_atomic_stat,ch_out_mbox,ch_out_intr_mbox,ch_snr1,ch_snr2,exit_status;
 struct {u32 status{};}status;
 struct StatusNpc {u32 status{};StatusNpc& raw(){return *this;}}status_npc;
 u64 ch_dec_start_timestamp{},ch_dec_value{};bool is_dec_frozen{};
 struct InMbox {
  u8 count{};u32 values[4]{};
  u8 try_read(u32* output){std::copy(values,values+count,output);return count;}
  void set_values(u8 n,u32 a,u32 b,u32 c,u32 d){count=n;values[0]=a;values[1]=b;values[2]=c;values[3]=d;}
 }ch_in_mbox;

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

namespace before { struct spu_thread:State { bool do_mfc(bool can_escape=true,bool must_finish=true);u32 get_mfc_completed()const;bool check_mfc_interrupts(u32);void serialize_common(utils::serial&);
void restore(utils::serial& ar){	serialize_common(ar);

}
s64 read_tag(){auto read_channel = [&](spu_channel& channel) -> s64
	{
		if (channel.get_count() == 0)
		{
			state += cpu_flag::rbx_wait + cpu_flag::temp;
		}

		if (state & cpu_flag::pending)
		{
			do_mfc();
		}

		// Reset GETLLAR metadata
		last_getllar_addr = umax;

		const s64 out = channel.pop_wait(*this);

		if (state & cpu_flag::rbx_wait)
		{
			wakeup_delay();
		}

		static_cast<void>(test_stopped());
		return out;
	};return read_channel(ch_tag_stat);}
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
void spu_thread::serialize_common(utils::serial& ar)
{
	ar(gpr, pc, ch_mfc_cmd, mfc_size, mfc_barrier, mfc_fence, mfc_prxy_cmd, mfc_prxy_mask, mfc_prxy_write_state.all
		, srr0, ch_tag_upd, ch_tag_mask, ch_tag_stat.data, ch_stall_mask, ch_stall_stat.data, ch_atomic_stat.data
		, ch_out_mbox.data, ch_out_intr_mbox.data, snr_config, ch_snr1.data, ch_snr2.data, ch_events.raw().all, interrupts_enabled
		, run_ctrl, exit_status.data, status_npc.raw().status, ch_dec_start_timestamp, ch_dec_value, is_dec_frozen);

	ar(std::span(mfc_queue, mfc_size));

	u32 vals[4]{};

	if (ar.is_writing())
	{
		const u8 count = ch_in_mbox.try_read(vals);
		ar(count, std::span(vals, count));
	}
	else
	{
		const u8 count{ar};
		ar(std::span(vals, count));
		ch_in_mbox.set_values(count, vals[0], vals[1], vals[2], vals[3]);
	}
}}
namespace after { struct spu_thread:State { bool do_mfc(bool can_escape=true,bool must_finish=true);u32 get_mfc_completed()const;bool check_mfc_interrupts(u32);void serialize_common(utils::serial&);
void restore(utils::serial& ar){	serialize_common(ar);

	// The MFC queue is serialized, but the host pending-work flag is not.
	// Re-arm deferred transfers so channel waits can drain them after restore.
	if (mfc_size && g_cfg.core.mfc_transfers_shuffling)
	{
		state += cpu_flag::pending;
	}

}
s64 read_tag(){auto read_channel = [&](spu_channel& channel) -> s64
	{
		if (channel.get_count() == 0)
		{
			state += cpu_flag::rbx_wait + cpu_flag::temp;
		}

		if (state & cpu_flag::pending)
		{
			do_mfc();
		}

		// Reset GETLLAR metadata
		last_getllar_addr = umax;

		const s64 out = channel.pop_wait(*this);

		if (state & cpu_flag::rbx_wait)
		{
			wakeup_delay();
		}

		static_cast<void>(test_stopped());
		return out;
	};return read_channel(ch_tag_stat);}
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
void spu_thread::serialize_common(utils::serial& ar)
{
	ar(gpr, pc, ch_mfc_cmd, mfc_size, mfc_barrier, mfc_fence, mfc_prxy_cmd, mfc_prxy_mask, mfc_prxy_write_state.all
		, srr0, ch_tag_upd, ch_tag_mask, ch_tag_stat.data, ch_stall_mask, ch_stall_stat.data, ch_atomic_stat.data
		, ch_out_mbox.data, ch_out_intr_mbox.data, snr_config, ch_snr1.data, ch_snr2.data, ch_events.raw().all, interrupts_enabled
		, run_ctrl, exit_status.data, status_npc.raw().status, ch_dec_start_timestamp, ch_dec_value, is_dec_frozen);

	ar(std::span(mfc_queue, mfc_size));

	u32 vals[4]{};

	if (ar.is_writing())
	{
		const u8 count = ch_in_mbox.try_read(vals);
		ar(count, std::span(vals, count));
	}
	else
	{
		const u8 count{ar};
		ar(std::span(vals, count));
		ch_in_mbox.set_values(count, vals[0], vals[1], vals[2], vals[3]);
	}
}}
struct Counters {u32 cases{},before_stalls{},after_completed{},list_blocks{},empty{},disabled{};} counts;
template<class T>void load(T& thread,const std::vector<u8>& bytes){utils::serial reader{false,bytes};thread.restore(reader);assert(reader.cursor==bytes.size());}
void scenario(u32 shuffle,u32 size,u32 tag,bool stalled,bool steps){
 g_cfg.core.mfc_transfers_shuffling=shuffle;g_cfg.core.mfc_shuffling_in_steps=steps;
 before::spu_thread saved;
 saved.mfc_size=size;saved.mfc_barrier=0;saved.mfc_fence=size?(1u<<tag):0;
 saved.ch_tag_mask=1u<<tag;saved.ch_tag_upd=MFC_TAG_UPDATE_ALL;
 for(u32 i=0;i<size;++i){auto& q=saved.mfc_queue[i];q.cmd=stalled?MFC_GETL_CMD:MFC_PUT_CMD;q.tag=tag|(stalled?0x80:0);q.eah=i+1;q.size=16;q.eal=0x60300510+i*128;}
 utils::serial writer{true,{}};saved.serialize_common(writer);
 before::spu_thread old;after::spu_thread fresh;load(old,writer.bytes);load(fresh,writer.bytes);
 assert(old.mfc_size==fresh.mfc_size&&std::memcmp(old.mfc_queue,fresh.mfc_queue,sizeof(old.mfc_queue))==0);
 assert(fresh.state==(shuffle&&size?cpu_flag::pending:0u));
 active=&old;utils::clock_calls=0;utils::fixed=false;auto prior=old.read_tag();
 active=&fresh;utils::clock_calls=0;utils::fixed=false;auto next=fresh.read_tag();active=nullptr;
 assert(prior==-1);++counts.cases;
 if(!shuffle){assert(next==-1&&fresh.mfc_size==size&&fresh.actions.empty());++counts.disabled;return;}
 if(!size){assert(next==-1&&fresh.mfc_size==0&&fresh.actions.empty());++counts.empty;return;}
 ++counts.before_stalls;
 if(stalled){
  assert(next==-1&&fresh.mfc_size==size&&fresh.ch_tag_stat.count==0);++counts.list_blocks;
  for(u32 i=0;i<size;++i)fresh.mfc_queue[i].tag&=0x7f;
  fresh.complete_lists=true;active=&fresh;next=fresh.read_tag();active=nullptr;
 }
 assert(next==s64{1}<<tag&&fresh.mfc_size==0&&fresh.mfc_fence==0);
 assert(fresh.ch_tag_upd==MFC_TAG_UPDATE_IMMEDIATE);++counts.after_completed;
}
int main(){
 for(u32 shuffle:{0u,1u,16u})for(u32 size:{0u,1u,2u,16u})for(u32 tag:{0u,5u,31u})for(bool stalled:{false,true})for(bool steps:{false,true})scenario(shuffle,size,tag,stalled,steps);
 std::cout<<"{\"cases\":"<<counts.cases<<",\"baselineStalledWaits\":"<<counts.before_stalls<<",\"candidateCompletedWaits\":"<<counts.after_completed<<",\"stalledListsRequireAck\":"<<counts.list_blocks<<",\"emptyQueueCases\":"<<counts.empty<<",\"disabledShufflingCases\":"<<counts.disabled<<",\"queueRoundtripPreserved\":true,\"interruptsDisabled\":true,\"timeoutIndependentChannelDrain\":true}";
}
