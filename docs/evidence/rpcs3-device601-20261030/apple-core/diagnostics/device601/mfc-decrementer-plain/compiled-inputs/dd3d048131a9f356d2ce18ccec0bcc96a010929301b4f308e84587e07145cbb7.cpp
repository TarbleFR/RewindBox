#include "ios/IOSSignalTrace.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <utility>

using u8=std::uint8_t; using u16=std::uint16_t; using u32=std::uint32_t;
using u64=std::uint64_t; using s64=std::int64_t; using usz=std::size_t; using uint=unsigned;
constexpr u64 umax=~u64{0};
#define ensure(x,...) assert(x)
#define ENABLE_BITWISE_SERIALIZATION
struct Escaped {};
struct WouldBlock {};
std::mutex wait_mutex;
std::condition_variable wait_cv;
std::atomic<u64> notify_calls{};
std::function<void()> before_state_wait, before_list_wait;
bool concurrent_wait=false;
std::atomic<bool> list_entered{};

// A mutex-backed atomic adapter preserves indivisible update callbacks.
// The production notification latch and wait-list construction are extracted
// below. The platform futex/ulock backend is replaced by a condition variable.
template<class T> struct atomic_t {
    mutable std::mutex mutex;
    T value{};
    atomic_t()=default;
    atomic_t(T initial):value(initial){}
    T load()const{std::lock_guard guard(mutex);return value;}
    operator T()const{return load();}
    void release(T next){std::lock_guard guard(mutex);value=next;}
    atomic_t& operator=(T next){release(next);return *this;}
    T fetch_add(T n){std::lock_guard guard(mutex);T old=value;value+=n;return old;}
    T exchange(T next){std::lock_guard guard(mutex);return std::exchange(value,next);}
    auto fetch_op(auto fn){
        std::lock_guard guard(mutex);T old=value;T next=old;
        if constexpr(std::is_void_v<decltype(fn(next))>){fn(next);value=next;return old;}
        else{bool commit=fn(next);if(commit)value=next;return std::pair<T,bool>{old,commit};}
    }
    auto atomic_op(auto fn){std::lock_guard guard(mutex);return fn(value);}
    bool compare_and_swap_test(T old,T next){std::lock_guard guard(mutex);if(value!=old)return false;value=next;return true;}
    T fetch_and(T mask){std::lock_guard guard(mutex);T old=value;value&=mask;return old;}
    bool bit_test_reset(uint index){std::lock_guard guard(mutex);T mask=T{1}<<index;bool old=bool(value&mask);value&=~mask;return old;}
    void operator|=(T bits){std::lock_guard guard(mutex);value|=bits;}
    void notify_one(){notify_all();}
    void notify_all(){std::lock_guard guard(wait_mutex);++notify_calls;wait_cv.notify_all();}
};


enum class cpu_flag:u32 {wait=1,stop=2,again=4,pending=8,pending_recheck=16,dbg_pause=32};
template<class T>using bs_t=u32;
u32 operator&(u32 v,cpu_flag b){return v&u32(b);}
u32 operator+(cpu_flag a,cpu_flag b){return u32(a)|u32(b);}
u32 operator-(u32 v,cpu_flag b){return v&~u32(b);}
u32& operator-=(u32&v,cpu_flag b){v&=~u32(b);return v;}

struct CpuState:atomic_t<u32>{
    void operator+=(u32 bits){*this|=bits;}

    u32 add_fetch(cpu_flag bit){
        if(before_state_wait){auto f=std::move(before_state_wait);before_state_wait={};f();}
        return atomic_op([&](u32& x){return x|=u32(bit);});
    }
    void operator+=(cpu_flag bit){*this|=u32(bit);}
};
struct cpu_thread;
struct thread_base {
    atomic_t<u32> m_sync{},m_taskq{};
    void notify();
};
void thread_base::notify()
{
	// Set notification
	m_sync |= 4;
	m_sync.notify_all();
}

enum class thread_class{ppu,spu,rsx};
template<class>struct result_storage{};
template <class Context>
class named_thread final : public Context, result_storage<Context>, thread_base
{
    friend struct thread_ctrl;
public:
    thread_base& host_thread(){return *this;}
};
struct atomic_wait_timeout{u64 value;};
namespace atomic_wait {
template<uint Size>struct list {
    std::array<std::function<bool()>,Size> changed;
    template<uint Index,class Atomic,class Value>void set(Atomic& atomic,Value old){changed[Index]=[&atomic,old]{return atomic.load()!=static_cast<decltype(atomic.load())>(old);};}
    template<uint Index,class Atomic>void set(Atomic& atomic){set<Index>(atomic,atomic.load());}
    void wait(atomic_wait_timeout timeout){
        assert(timeout.value==umax); // Production never adds a recovery timeout.
        if(before_list_wait){auto f=std::move(before_list_wait);before_list_wait={};f();}
        auto ready=[&]{for(auto& f:changed)if(f&&f())return true;return false;};
        if(!concurrent_wait){if(!ready())throw WouldBlock{};return;}
        std::unique_lock guard(wait_mutex);list_entered.store(true,std::memory_order_release);wait_cv.notify_all();
        // This deadline is solely a test watchdog, not candidate code.
        assert(wait_cv.wait_for(guard,std::chrono::seconds(2),ready));
    }
};
}
struct thread_ctrl {
    static thread_local thread_base* g_tls_this_thread;
    template <typename T>
	static void notify(named_thread<T>& thread)
	{
		static_cast<thread_base&>(thread).notify();
	}
    template <uint Max, typename Func>
	static inline void wait_on_custom(Func&& setter, u64 usec = -1)
	{
		auto _this = g_tls_this_thread;

		if (_this->m_sync.bit_test_reset(2) || _this->m_taskq)
		{
			return;
		}

		atomic_wait::list<Max + 2> list{};
		list.template set<Max>(_this->m_sync, 0);
		list.template set<Max + 1>(_this->m_taskq);
		setter(list);
		list.wait(atomic_wait_timeout{usec <= 0xffff'ffff'ffff'ffff / 1000 ? usec * 1000 : 0xffff'ffff'ffff'ffff});
	}
    template <typename T, typename U>
	static inline void wait_on(T& wait, U old, u64 usec = -1)
	{
		wait_on_custom<1>([&](atomic_wait::list<3>& list) { list.template set<0>(wait, old); }, usec);
	}
};
thread_local thread_base* thread_ctrl::g_tls_this_thread=nullptr;
namespace utils {
template<class T>T* bless(void*){static T sink[2];return sink;}
u64 get_tsc(){return 0xffff;}
}
void atomic_fence_seq_cst(){std::atomic_thread_fence(std::memory_order_seq_cst);}

u64 clock_now=1;u64 get_system_time(){return clock_now;}u64 get_timebased_time(){return clock_now;}
void busy_wait(u64){}
namespace fmt{template<class...T>[[noreturn]]void throw_exception(T...){throw std::runtime_error("unexpected");}}


struct {struct {u32 mfc_transfers_shuffling{},mfc_transfers_timeout{},clocks_scale{100};bool mfc_shuffling_in_steps{};}core;}g_cfg;
constexpr u32 SPU_EVENT_LR=0x400,SPU_EVENT_TM=0x20,SPU_EVENT_SN=2;
constexpr u32 SPU_EVENT_IMPLEMENTED=SPU_EVENT_LR|SPU_EVENT_TM|SPU_EVENT_SN|0x300;
constexpr u32 SPU_EVENT_INTR_BUSY_CHECK=SPU_EVENT_IMPLEMENTED&~SPU_EVENT_SN;
struct Logger{template<class...T>void error(T...){};}spu_log;
struct spu_dec_intr_timer;template<class T>class named_thread;
struct TimerQueue{u64 calls{},due{},token{};void arm(u64 d,u32,u64 t){++calls;due=d;token=t;}};
struct FixedObjects{template<class T>TimerQueue& get(){static TimerQueue queue;return queue;}}fixed_objects;
auto* g_fxo=&fixed_objects;

constexpr u32 SPU_EVENT_S1=0x200,SPU_EVENT_S2=0x100;
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
struct spu_channel_op_state
{
	u8 old_count;
	u8 count;
	bool notify;
	bool op_done;
};
struct alignas(16) spu_channel
{
	// Low 32 bits contain value
	atomic_t<u64> data{};

	// Pending value to be inserted when it is possible in pop() or pop_wait()
	atomic_t<u64> jostling_value{};

public:
	static constexpr u32 off_wait  = 32;
	static constexpr u32 off_occupy = 33;
	static constexpr u32 off_count = 63;
	static constexpr u64 bit_wait  = 1ull << off_wait;
	static constexpr u64 bit_occupy = 1ull << off_occupy;
	static constexpr u64 bit_count = 1ull << off_count;
	static constexpr u64 occupy_ored_wait = bit_wait | bit_occupy; 

	// Returns true on success
	bool try_push(u32 value)
	{
		return data.fetch_op([value](u64& data)
		{
			if (!(data & bit_count)) [[likely]]
			{
				data = bit_count | value;
				return true;
			}

			return false;
		}).second;
	}

	// Push unconditionally, may require notification
	// Performing bitwise OR with previous value if specified, otherwise overwiting it
	// Returns old count and new count
	spu_channel_op_state push(u32 value, bool to_or = false, bool postpone_notify = false)
	{
		while (true)
		{
			const auto [old, pushed_to_data] = data.fetch_op([&](u64& data)
			{
				if (data & bit_occupy)
				{
					return false;
				}

				if (to_or)
				{
					data = bit_count | (static_cast<u32>(data) | value);
				}
				else
				{
					data = bit_count | value;
				}

				return true;
			});

			if (!pushed_to_data)
			{
				// Insert the pending value in special storage for waiting SPUs, leave no time in which the channel has data
				if (!jostling_value.compare_and_swap_test(bit_occupy, value))
				{
					// Other thread has inserted a value through jostling_value, retry
					continue;
				}

				// Turn off waiting bit manually (must succeed because waiting bit can only be resetted by the thread pushed to jostling_value)
				if (~this->data.fetch_and(~occupy_ored_wait) & bit_wait)
				{
					// Could be fatal or at emulation stopping, to be checked by the caller
					ensure(false);
				}

				// Fallthrough to notification
				ensure(old & bit_wait);
			}

			if (old & bit_wait)
			{
				if (!postpone_notify)
				{
					const usz is_le = std::endian::native == std::endian::little ? 1 : 0;
					utils::bless<atomic_t<u32>>(&data)[is_le].notify_one();
				}
			}

			// Report the old count, including zero when delivering directly to a waiting SPU.
			return { (old & bit_count) != 0, 1, (old & bit_wait) != 0, true };
		}
	}

	void notify()
	{
		const usz is_le = std::endian::native == std::endian::little ? 1 : 0;
		utils::bless<atomic_t<u32>>(&data)[is_le].notify_one();
	}

	// Returns true on success
	bool try_pop(u32& out)
	{
		return data.fetch_op([&out](u64& data)
		{
			if (data & bit_count) [[likely]]
			{
				out = static_cast<u32>(data);
				data = 0;
				return true;
			}

			return false;
		}).second;
	}

	// Reading without modification
	bool try_read(u32& out) const
	{
		const u64 old = data.load();
		out = static_cast<u32>(old);

		if (old & bit_count) [[likely]]
		{
			return true;
		}

		return false;
	}

	// Pop unconditionally (loading last value), may require notification
	// If the SPU tries to insert a value, do it instead the SPU
	u32 pop()
	{
		// Value is not cleared and may be read again
		constexpr u64 mask = bit_count | bit_occupy;

		const u64 old = data.fetch_op([&](u64& data)
		{
			if ((data & mask) == mask)
			{
				// Insert the pending value, leave no time in which the channel has no data
				data = bit_count | static_cast<u32>(jostling_value);
				return;
			}

			data &= ~(mask | bit_wait);
		});

		if (old & bit_wait)
		{
			const usz is_le = std::endian::native == std::endian::little ? 1 : 0;
			utils::bless<atomic_t<u32>>(&data)[is_le].notify_one();
		}

		return static_cast<u32>(old);
	}

	// Waiting for channel pop state availability, actually popping if specified
	s64 pop_wait(cpu_thread& spu, bool pop = true);

	// Waiting for channel push state availability, actually pushing if specified
	bool push_wait(cpu_thread& spu, u32 value, bool push = true);

	void set_value(u32 value, bool count = true)
	{
		data.release(u64{count} << off_count | value);
	}

	u32 get_value() const
	{
		return static_cast<u32>(data);
	}

	u32 get_count() const
	{
		return (data & bit_count) ? 1 : 0;
	}
};
namespace spu_runtime {template<class T>[[noreturn]]void g_escape(T*){throw Escaped{};}}

namespace before {
struct cpu_thread {
    CpuState state;
    
    static cpu_thread* get_current(){return nullptr;}
    thread_class get_class()const{return thread_class::spu;}
    void notify();
};
struct ppu_thread:cpu_thread{};
struct spu_thread:cpu_thread {
    struct ch_events_t{u32 events{};u8 locks{};bool waiting{},count{};u32 mask{};};
    atomic_t<ch_events_t> ch_events;
    spu_channel ch_snr1,ch_snr2,ch_tag_stat;
    u64 snr_config{};
    u32 id{0x2000001},ch_stall_mask{},mfc_size{},mfc_barrier{},mfc_fence{},ch_tag_mask{},ch_tag_upd{};
    u64 mfc_last_timestamp{};
    spu_mfc_cmd mfc_queue[16]{},ch_mfc_cmd{};
    u32 pc{0x1240},srr0{},interrupt_word{0x30000100};
    bool interrupts_enabled{true},complete_lists{};
    u32 accepted{},dma_calls{},list_calls{},interrupt_cancels{},notified{};
    u8* ls{};
    bool in_cpu_work{},allow_interrupts_in_cpu_work{},interrupt_requires_escape{},has_active_local_bps{};
    u32 cpu_work_iteration_count{};u64 current_bp_pc{};u32 raddr{},rdata{};
    std::array<u8,0x10000> local_breakpoints{};
    u32 ch_dec_value{};u64 ch_dec_start_timestamp{};bool is_dec_frozen{};
    u64 dec_intr_deadline{umax};atomic_t<u64> dec_intr_armed{};
    bool reservation_check(u32&,u32&){return false;}
    std::pair<u32,u32> read_dec()const;
    ch_events_t get_events(u64 mask_hint=0,bool waiting=false,bool reading=false);
    void arm_dec_interrupt();void cpu_work();

    
    // CPUThread::check_state boundary: pending invokes real cpu_work, then wait
    // is cleared before returning to the real full-queue loop. Suspend/debug
    // scheduling and the kernel wait implementation are outside this fixture.
    bool test_stopped(){
        if(state.load()&u32(cpu_flag::pending))cpu_work();
        state.atomic_op([](u32& s){s-=cpu_flag::wait;});
        return is_stopped(state.load());
    }
    bool is_stopped()const{return is_stopped(state.load());}
    static bool is_stopped(u32 flags){return flags&u32(cpu_flag::stop);}
    void cancel_dec_interrupt();
    template<class T>T _ref(u32 addr){assert(addr==0);return interrupt_word;}
    bool do_list_transfer(spu_mfc_cmd& command){++list_calls;if(complete_lists)return true;command.tag|=0x80;return false;}
    void do_putlluc(const spu_mfc_cmd&){++dma_calls;}
    static void do_dma_transfer(spu_thread* self,const spu_mfc_cmd&,u8*){++self->dma_calls;}
    bool do_mfc(bool can_escape=true,bool must_finish=true);
    u32 get_mfc_completed()const;
    bool check_mfc_interrupts(u32 next_pc);
    void push_snr(u32 number,u32 value);
    void set_events(u32 bits);
    bool process_prefix();
};

void cpu_thread::notify()
{
	state.notify_one();

	// Downcast to correct type
	switch (get_class())
	{
	case thread_class::ppu:
	{
		thread_ctrl::notify(*static_cast<named_thread<ppu_thread>*>(this));
		break;
	}
	case thread_class::spu:
	{
		thread_ctrl::notify(*static_cast<named_thread<spu_thread>*>(this));
		break;
	}
	case thread_class::rsx:
	{
		break;
	}
	default:
	{
		fmt::throw_exception("Invalid cpu_thread type");
	}
	}
}
static void ios_publish_mfc_snapshot(const spu_thread& spu, rpcs3::ios::signal_trace::producer_phase phase, u64 session)
{
	namespace trace = rpcs3::ios::signal_trace;
	trace::producer_state value{};
	value.session = session;
	value.published_us = get_system_time();
	value.id = spu.id;
	value.pc = spu.pc;
	value.return_pc = spu.srr0;
	value.size = spu.mfc_size;
	value.barrier = spu.mfc_barrier;
	value.fence = spu.mfc_fence;
	value.stall_mask = spu.ch_stall_mask;
	value.tag_mask = spu.ch_tag_mask;
	value.tag_update = spu.ch_tag_upd;
	const auto events = spu.ch_events.load();
	value.event_bits = events.events;
	value.event_mask = events.mask;
	value.event_count = events.count;
	value.event_waiting = events.waiting;
	value.interrupts_enabled = spu.interrupts_enabled;
	value.snr1_count = spu.ch_snr1.get_count();
	value.snr2_count = spu.ch_snr2.get_count();
	value.phase = phase;
	const auto copy = [](const spu_mfc_cmd& cmd) -> trace::queue_entry { return {cmd.cmd, cmd.tag, cmd.lsa, cmd.eal, cmd.size}; };
	value.unaccepted = copy(spu.ch_mfc_cmd);
	for (u32 i = 0; i < std::min<u32>(spu.mfc_size, trace::queue_capacity); ++i)
		value.queue[i] = copy(spu.mfc_queue[i]);
	trace::publish_producer(value);
}
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
void spu_thread::push_snr(u32 number, u32 value)
{
	// Get channel
	const auto channel = number & 1 ? &ch_snr2 : &ch_snr1;

	// Prepare some data
	const u32 event_bit = SPU_EVENT_S1 >> (number & 1);
	const bool bitor_bit = !!((snr_config >> number) & 1);

	// Lock event channel in case it needs event notification
	ch_events.atomic_op([](ch_events_t& ev)
	{
		ev.locks++;
	});

	// Check corresponding SNR register settings
	auto push_state = channel->push(value, bitor_bit);

	if (push_state.old_count < push_state.count)
	{
		set_events(event_bit);
	}
	else if (!push_state.op_done)
	{
		ensure(is_stopped());

		if (auto cpu = cpu_thread::get_current())
		{
			cpu->state += cpu_flag::again;
		}
	}

	ch_events.atomic_op([](ch_events_t& ev)
	{
		ev.locks--;
	});
}
void spu_thread::set_events(u32 bits)
{
	if (ch_events.atomic_op([&](ch_events_t& events)
	{
		events.events |= bits;

		// If one masked event was fired, set the channel count (even if the event bit was already 1)
		if (events.mask & bits)
		{
			events.count = true;
			return !!events.waiting && (bits & (SPU_EVENT_S1 | SPU_EVENT_S2));
		}

		return false;
	}))
	{
		notify();
	}
}
void spu_thread::cpu_work()
{
	if (std::exchange(in_cpu_work, true))
	{
		return;
	}

	// Only calls that may take an interrupt advance the count. Compiled code alternates checks
	// where it may (every register in memory) with checks where it may not, and counting both
	// could park the every-16th interrupt check below on the second kind for good.
	const u32 old_iter_count = allow_interrupts_in_cpu_work ? cpu_work_iteration_count++ : cpu_work_iteration_count;

	bool work_left = false;

	if (has_active_local_bps)
	{
		const u32 pos_at = pc / 4;
		const u32 pos_bit = 1u << (pos_at % 8);

		if (local_breakpoints[pos_at / 8] & pos_bit)
		{
			// Ignore repeatations until a different instruction is issued
			if (pc != current_bp_pc)
			{
				// Breakpoint hit
				state += cpu_flag::dbg_pause;
			}
		}

		current_bp_pc = pc;
		work_left = true;
	}
	else
	{
		current_bp_pc = umax;
	}

	const auto timeout = +g_cfg.core.mfc_transfers_timeout;

	if (u32 shuffle_count = g_cfg.core.mfc_transfers_shuffling)
	{
		// If either MFC size exceeds limit or timeout has been reached execute pending MFC commands
		if (mfc_size > shuffle_count || (timeout && get_system_time() - mfc_last_timestamp >= timeout))
		{
			work_left = do_mfc(false, false);
		}
		else
		{
			work_left = mfc_size != 0; // TODO: Optimize
		}
	}

	bool gen_interrupt = false;

	const u32 busy_mask = ch_events.load().mask & SPU_EVENT_INTR_BUSY_CHECK;

	// The decrementer has underflowed with interrupts on (spu_dec_intr_timer raised ::pending):
	// take it at the first check that may, not the next 16th
	const bool dec_due = interrupts_enabled && (busy_mask & SPU_EVENT_TM) && read_dec().second;

	// Check interrupts every 16 iterations
	if ((!(old_iter_count % 16) || dec_due) && allow_interrupts_in_cpu_work)
	{
		if (u32 mask = busy_mask)
		{
			// LR check is expensive, do it once in a while
			if (old_iter_count % 256)
			{
				mask &= ~SPU_EVENT_LR;
			}

			get_events(mask);
		}

		gen_interrupt = check_mfc_interrupts(pc);
		arm_dec_interrupt();
	}

	// Busy checking has to keep going while an interrupt can still be taken. Only the line above
	// kept ::pending, and only on every 16th call, so the next call with no MFC work cleared it
	// and the busy check stopped after one round. Reservation loss and signals are polled for as
	// long as they are enabled; the decrementer only once it has underflowed.
	if (interrupts_enabled && ((busy_mask & ~SPU_EVENT_TM) || dec_due))
	{
		work_left = true;
	}

	in_cpu_work = false;

	if (!work_left)
	{
		// No more pending work
		state.atomic_op([](bs_t<cpu_flag>& flags)
		{
			if (flags & cpu_flag::pending_recheck)
			{
				// Do not really remove ::pending because external thread may have pushed more pending work
				flags -= cpu_flag::pending_recheck;
			}
			else
			{
				flags -= cpu_flag::pending;
			}
		});
	}

	if (gen_interrupt && interrupt_requires_escape)
	{
		// Interrupt! escape everything and restart execution
		spu_runtime::g_escape(this);
	}
}
spu_thread::ch_events_t spu_thread::get_events(u64 mask_hint, bool waiting, bool reading)
{
	if (auto mask1 = ch_events.load().mask; mask1 & ~SPU_EVENT_IMPLEMENTED)
	{
		fmt::throw_exception("SPU Events not implemented (mask=0x%x)", mask1);
	}

retry:
	u32 collect = 0;

	// Check reservation status and set SPU_EVENT_LR if lost
	if (mask_hint & SPU_EVENT_LR)
	{
		if (reservation_check(raddr, rdata))
		{
			collect |= SPU_EVENT_LR;
			raddr = 0;
		}
	}

	// SPU Decrementer Event on underflow (use the upper 32-bits to determine it)
	if (mask_hint & SPU_EVENT_TM)
	{
		if (const u64 res = read_dec().second)
		{
			// Set next event to the next time the decrementer underflows
			ch_dec_start_timestamp -= res << 32;
			collect |= SPU_EVENT_TM;
			arm_dec_interrupt();
		}
	}

	if (collect)
	{
		set_events(collect);
	}

	auto [res, ok] = ch_events.fetch_op([&](ch_events_t& events)
	{
		if (!reading)
			return false;
		if (waiting)
			events.waiting = !events.count;

		events.count = false;
		return true;
	});

	if (reading && res.locks && mask_hint & (SPU_EVENT_S1 | SPU_EVENT_S2))
	{
		busy_wait(100);
		goto retry;
	}

	return res;
}
std::pair<u32, u32> spu_thread::read_dec() const
{
	const u64 res = ch_dec_value - (is_dec_frozen ? 0 : (get_timebased_time() - ch_dec_start_timestamp));
	return {static_cast<u32>(res), static_cast<u32>(res >> 32)};
}
void spu_thread::cancel_dec_interrupt()
{
	dec_intr_armed = 0;
	dec_intr_deadline = umax;
}
void spu_thread::arm_dec_interrupt()
{
	if (!interrupts_enabled || is_dec_frozen || !(ch_events.load().mask & SPU_EVENT_TM))
	{
		cancel_dec_interrupt();
		return;
	}
	if (read_dec().second)
	{
		cancel_dec_interrupt();
		state += cpu_flag::pending;
		return;
	}

	// Underflow is one tick after zero, including a write of zero.
	const u64 due = ch_dec_start_timestamp + ch_dec_value + 1;
	if (dec_intr_deadline != due || !dec_intr_armed.load())
	{
		static atomic_t<u64> next_token{1};
		const u64 token = next_token.fetch_add(1);
		dec_intr_deadline = due;
		dec_intr_armed = token;
		g_fxo->get<named_thread<spu_dec_intr_timer>>().arm(due, id, token);
	}
}
bool spu_thread::process_prefix(){
#ifdef RPCS3_IOS
	const bool trace_full_queue = mfc_size >= 16 && rpcs3::ios::signal_trace::enabled.load(std::memory_order_relaxed);
	const u64 trace_session = trace_full_queue ? rpcs3::ios::signal_trace::current_session.load(std::memory_order_acquire) : 0;
#endif
	// Stall infinitely if MFC queue is full
	while (mfc_size >= 16) [[unlikely]]
	{
		// Reset MFC timestamp in the case of full queue
		mfc_last_timestamp = 0;

		if (test_stopped())
		{
#ifdef RPCS3_IOS
			if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_stopped, trace_session);
#endif
			return false;
		}

		// The new channel command has not been accepted yet. If draining
		// takes an interrupt, resume this WRCH rather than the next instruction.
		do_mfc(false);

		// A stalled queue can need an interrupt handler to acknowledge a list.
		// Register before checking the event: a later SNR must notify this
		// blocked WRCH too, including the interval before wait_on starts.
		const bool wait_for_events = mfc_size >= 16 && interrupts_enabled;
		if (wait_for_events)
		{
			ch_events.atomic_op([](ch_events_t& events) { events.waiting = true; });
		}

		if (check_mfc_interrupts(pc))
		{
			if (wait_for_events)
			{
				ch_events.atomic_op([](ch_events_t& events) { events.waiting = false; });
			}

#ifdef RPCS3_IOS
			if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_irq, trace_session);
#endif
			spu_runtime::g_escape(this);
		}

		if (mfc_size < 16)
		{
			break;
		}

		auto old = state.add_fetch(cpu_flag::wait);

		if (is_stopped(old))
		{
			if (wait_for_events)
			{
				ch_events.atomic_op([](ch_events_t& events) { events.waiting = false; });
			}

#ifdef RPCS3_IOS
			if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_stopped, trace_session);
#endif
			return false;
		}

#ifdef RPCS3_IOS
		if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_blocked, trace_session);
#endif
		thread_ctrl::wait_on(state, old);
		if (wait_for_events)
		{
			ch_events.atomic_op([](ch_events_t& events) { events.waiting = false; });
		}
#ifdef RPCS3_IOS
		if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_woke, trace_session);
#endif
	}
#ifdef RPCS3_IOS
	if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_ready, trace_session);
#endif

++accepted;switch(ch_mfc_cmd.cmd){
	case MFC_BARRIER_CMD:
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
	}
 default: assert(false);return false;} }

void publish_timer(named_thread<spu_thread>& target,u64 token){auto* spu=&target;struct{u64 token;}e{token};
if (spu->dec_intr_armed.compare_and_swap_test(e.token, 0))
					{
						spu->state += cpu_flag::pending + cpu_flag::pending_recheck;
						spu->state.notify_one();
					}
}

struct spu_opcode_t{};
namespace spu_interpreter{
void set_interrupt_status(spu_thread& spu,spu_opcode_t){assert(!spu.interrupts_enabled);}
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
}
namespace after {
struct cpu_thread {
    CpuState state;
    
    static cpu_thread* get_current(){return nullptr;}
    thread_class get_class()const{return thread_class::spu;}
    void notify();
};
struct ppu_thread:cpu_thread{};
struct spu_thread:cpu_thread {
    struct ch_events_t{u32 events{};u8 locks{};bool waiting{},count{};u32 mask{};};
    atomic_t<ch_events_t> ch_events;
    spu_channel ch_snr1,ch_snr2,ch_tag_stat;
    u64 snr_config{};
    u32 id{0x2000001},ch_stall_mask{},mfc_size{},mfc_barrier{},mfc_fence{},ch_tag_mask{},ch_tag_upd{};
    u64 mfc_last_timestamp{};
    spu_mfc_cmd mfc_queue[16]{},ch_mfc_cmd{};
    u32 pc{0x1240},srr0{},interrupt_word{0x30000100};
    bool interrupts_enabled{true},complete_lists{};
    u32 accepted{},dma_calls{},list_calls{},interrupt_cancels{},notified{};
    u8* ls{};
    bool in_cpu_work{},allow_interrupts_in_cpu_work{},interrupt_requires_escape{},has_active_local_bps{};
    u32 cpu_work_iteration_count{};u64 current_bp_pc{};u32 raddr{},rdata{};
    std::array<u8,0x10000> local_breakpoints{};
    u32 ch_dec_value{};u64 ch_dec_start_timestamp{};bool is_dec_frozen{};
    u64 dec_intr_deadline{umax};atomic_t<u64> dec_intr_armed{};
    bool reservation_check(u32&,u32&){return false;}
    std::pair<u32,u32> read_dec()const;
    ch_events_t get_events(u64 mask_hint=0,bool waiting=false,bool reading=false);
    void arm_dec_interrupt();void cpu_work();

    
    // CPUThread::check_state boundary: pending invokes real cpu_work, then wait
    // is cleared before returning to the real full-queue loop. Suspend/debug
    // scheduling and the kernel wait implementation are outside this fixture.
    bool test_stopped(){
        if(state.load()&u32(cpu_flag::pending))cpu_work();
        state.atomic_op([](u32& s){s-=cpu_flag::wait;});
        return is_stopped(state.load());
    }
    bool is_stopped()const{return is_stopped(state.load());}
    static bool is_stopped(u32 flags){return flags&u32(cpu_flag::stop);}
    void cancel_dec_interrupt();
    template<class T>T _ref(u32 addr){assert(addr==0);return interrupt_word;}
    bool do_list_transfer(spu_mfc_cmd& command){++list_calls;if(complete_lists)return true;command.tag|=0x80;return false;}
    void do_putlluc(const spu_mfc_cmd&){++dma_calls;}
    static void do_dma_transfer(spu_thread* self,const spu_mfc_cmd&,u8*){++self->dma_calls;}
    bool do_mfc(bool can_escape=true,bool must_finish=true);
    u32 get_mfc_completed()const;
    bool check_mfc_interrupts(u32 next_pc);
    void push_snr(u32 number,u32 value);
    void set_events(u32 bits);
    bool process_prefix();
};

void cpu_thread::notify()
{
	state.notify_one();

	// Downcast to correct type
	switch (get_class())
	{
	case thread_class::ppu:
	{
		thread_ctrl::notify(*static_cast<named_thread<ppu_thread>*>(this));
		break;
	}
	case thread_class::spu:
	{
		thread_ctrl::notify(*static_cast<named_thread<spu_thread>*>(this));
		break;
	}
	case thread_class::rsx:
	{
		break;
	}
	default:
	{
		fmt::throw_exception("Invalid cpu_thread type");
	}
	}
}
static void ios_publish_mfc_snapshot(const spu_thread& spu, rpcs3::ios::signal_trace::producer_phase phase, u64 session)
{
	namespace trace = rpcs3::ios::signal_trace;
	trace::producer_state value{};
	value.session = session;
	value.published_us = get_system_time();
	value.id = spu.id;
	value.pc = spu.pc;
	value.return_pc = spu.srr0;
	value.size = spu.mfc_size;
	value.barrier = spu.mfc_barrier;
	value.fence = spu.mfc_fence;
	value.stall_mask = spu.ch_stall_mask;
	value.tag_mask = spu.ch_tag_mask;
	value.tag_update = spu.ch_tag_upd;
	const auto events = spu.ch_events.load();
	value.event_bits = events.events;
	value.event_mask = events.mask;
	value.event_count = events.count;
	value.event_waiting = events.waiting;
	value.interrupts_enabled = spu.interrupts_enabled;
	value.snr1_count = spu.ch_snr1.get_count();
	value.snr2_count = spu.ch_snr2.get_count();
	value.phase = phase;
	const auto copy = [](const spu_mfc_cmd& cmd) -> trace::queue_entry { return {cmd.cmd, cmd.tag, cmd.lsa, cmd.eal, cmd.size}; };
	value.unaccepted = copy(spu.ch_mfc_cmd);
	for (u32 i = 0; i < std::min<u32>(spu.mfc_size, trace::queue_capacity); ++i)
		value.queue[i] = copy(spu.mfc_queue[i]);
	trace::publish_producer(value);
}
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
void spu_thread::push_snr(u32 number, u32 value)
{
	// Get channel
	const auto channel = number & 1 ? &ch_snr2 : &ch_snr1;

	// Prepare some data
	const u32 event_bit = SPU_EVENT_S1 >> (number & 1);
	const bool bitor_bit = !!((snr_config >> number) & 1);

	// Lock event channel in case it needs event notification
	ch_events.atomic_op([](ch_events_t& ev)
	{
		ev.locks++;
	});

	// Check corresponding SNR register settings
	auto push_state = channel->push(value, bitor_bit);

	if (push_state.old_count < push_state.count)
	{
		set_events(event_bit);
	}
	else if (!push_state.op_done)
	{
		ensure(is_stopped());

		if (auto cpu = cpu_thread::get_current())
		{
			cpu->state += cpu_flag::again;
		}
	}

	ch_events.atomic_op([](ch_events_t& ev)
	{
		ev.locks--;
	});
}
void spu_thread::set_events(u32 bits)
{
	if (ch_events.atomic_op([&](ch_events_t& events)
	{
		events.events |= bits;

		// If one masked event was fired, set the channel count (even if the event bit was already 1)
		if (events.mask & bits)
		{
			events.count = true;
			return !!events.waiting && (bits & (SPU_EVENT_S1 | SPU_EVENT_S2));
		}

		return false;
	}))
	{
		notify();
	}
}
void spu_thread::cpu_work()
{
	if (std::exchange(in_cpu_work, true))
	{
		return;
	}

	// Only calls that may take an interrupt advance the count. Compiled code alternates checks
	// where it may (every register in memory) with checks where it may not, and counting both
	// could park the every-16th interrupt check below on the second kind for good.
	const u32 old_iter_count = allow_interrupts_in_cpu_work ? cpu_work_iteration_count++ : cpu_work_iteration_count;

	bool work_left = false;

	if (has_active_local_bps)
	{
		const u32 pos_at = pc / 4;
		const u32 pos_bit = 1u << (pos_at % 8);

		if (local_breakpoints[pos_at / 8] & pos_bit)
		{
			// Ignore repeatations until a different instruction is issued
			if (pc != current_bp_pc)
			{
				// Breakpoint hit
				state += cpu_flag::dbg_pause;
			}
		}

		current_bp_pc = pc;
		work_left = true;
	}
	else
	{
		current_bp_pc = umax;
	}

	const auto timeout = +g_cfg.core.mfc_transfers_timeout;

	if (u32 shuffle_count = g_cfg.core.mfc_transfers_shuffling)
	{
		// If either MFC size exceeds limit or timeout has been reached execute pending MFC commands
		if (mfc_size > shuffle_count || (timeout && get_system_time() - mfc_last_timestamp >= timeout))
		{
			work_left = do_mfc(false, false);
		}
		else
		{
			work_left = mfc_size != 0; // TODO: Optimize
		}
	}

	bool gen_interrupt = false;

	const u32 busy_mask = ch_events.load().mask & SPU_EVENT_INTR_BUSY_CHECK;

	// The decrementer has underflowed with interrupts on (spu_dec_intr_timer raised ::pending):
	// take it at the first check that may, not the next 16th
	const bool dec_due = interrupts_enabled && (busy_mask & SPU_EVENT_TM) && read_dec().second;

	// Check interrupts every 16 iterations
	if ((!(old_iter_count % 16) || dec_due) && allow_interrupts_in_cpu_work)
	{
		if (u32 mask = busy_mask)
		{
			// LR check is expensive, do it once in a while
			if (old_iter_count % 256)
			{
				mask &= ~SPU_EVENT_LR;
			}

			get_events(mask);
		}

		gen_interrupt = check_mfc_interrupts(pc);
		arm_dec_interrupt();
	}

	// Busy checking has to keep going while an interrupt can still be taken. Only the line above
	// kept ::pending, and only on every 16th call, so the next call with no MFC work cleared it
	// and the busy check stopped after one round. Reservation loss and signals are polled for as
	// long as they are enabled; the decrementer only once it has underflowed.
	if (interrupts_enabled && ((busy_mask & ~SPU_EVENT_TM) || dec_due))
	{
		work_left = true;
	}

	in_cpu_work = false;

	if (!work_left)
	{
		// No more pending work
		state.atomic_op([](bs_t<cpu_flag>& flags)
		{
			if (flags & cpu_flag::pending_recheck)
			{
				// Do not really remove ::pending because external thread may have pushed more pending work
				flags -= cpu_flag::pending_recheck;
			}
			else
			{
				flags -= cpu_flag::pending;
			}
		});
	}

	if (gen_interrupt && interrupt_requires_escape)
	{
		// Interrupt! escape everything and restart execution
		spu_runtime::g_escape(this);
	}
}
spu_thread::ch_events_t spu_thread::get_events(u64 mask_hint, bool waiting, bool reading)
{
	if (auto mask1 = ch_events.load().mask; mask1 & ~SPU_EVENT_IMPLEMENTED)
	{
		fmt::throw_exception("SPU Events not implemented (mask=0x%x)", mask1);
	}

retry:
	u32 collect = 0;

	// Check reservation status and set SPU_EVENT_LR if lost
	if (mask_hint & SPU_EVENT_LR)
	{
		if (reservation_check(raddr, rdata))
		{
			collect |= SPU_EVENT_LR;
			raddr = 0;
		}
	}

	// SPU Decrementer Event on underflow (use the upper 32-bits to determine it)
	if (mask_hint & SPU_EVENT_TM)
	{
		if (const u64 res = read_dec().second)
		{
			// Set next event to the next time the decrementer underflows
			ch_dec_start_timestamp -= res << 32;
			collect |= SPU_EVENT_TM;
			arm_dec_interrupt();
		}
	}

	if (collect)
	{
		set_events(collect);
	}

	auto [res, ok] = ch_events.fetch_op([&](ch_events_t& events)
	{
		if (!reading)
			return false;
		if (waiting)
			events.waiting = !events.count;

		events.count = false;
		return true;
	});

	if (reading && res.locks && mask_hint & (SPU_EVENT_S1 | SPU_EVENT_S2))
	{
		busy_wait(100);
		goto retry;
	}

	return res;
}
std::pair<u32, u32> spu_thread::read_dec() const
{
	const u64 res = ch_dec_value - (is_dec_frozen ? 0 : (get_timebased_time() - ch_dec_start_timestamp));
	return {static_cast<u32>(res), static_cast<u32>(res >> 32)};
}
void spu_thread::cancel_dec_interrupt()
{
	dec_intr_armed = 0;
	dec_intr_deadline = umax;
}
void spu_thread::arm_dec_interrupt()
{
	if (!interrupts_enabled || is_dec_frozen || !(ch_events.load().mask & SPU_EVENT_TM))
	{
		cancel_dec_interrupt();
		return;
	}
	if (read_dec().second)
	{
		cancel_dec_interrupt();
		state += cpu_flag::pending;
		return;
	}

	// Underflow is one tick after zero, including a write of zero.
	const u64 due = ch_dec_start_timestamp + ch_dec_value + 1;
	if (dec_intr_deadline != due || !dec_intr_armed.load())
	{
		static atomic_t<u64> next_token{1};
		const u64 token = next_token.fetch_add(1);
		dec_intr_deadline = due;
		dec_intr_armed = token;
		g_fxo->get<named_thread<spu_dec_intr_timer>>().arm(due, id, token);
	}
}
bool spu_thread::process_prefix(){
#ifdef RPCS3_IOS
	const bool trace_full_queue = mfc_size >= 16 && rpcs3::ios::signal_trace::enabled.load(std::memory_order_relaxed);
	const u64 trace_session = trace_full_queue ? rpcs3::ios::signal_trace::current_session.load(std::memory_order_acquire) : 0;
#endif
	// Stall infinitely if MFC queue is full
	while (mfc_size >= 16) [[unlikely]]
	{
		// Reset MFC timestamp in the case of full queue
		mfc_last_timestamp = 0;

		if (test_stopped())
		{
#ifdef RPCS3_IOS
			if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_stopped, trace_session);
#endif
			return false;
		}

		// The new channel command has not been accepted yet. If draining
		// takes an interrupt, resume this WRCH rather than the next instruction.
		do_mfc(false);

		// A stalled queue can need an interrupt handler to acknowledge a list.
		// Register before checking the event: a later SNR must notify this
		// blocked WRCH too, including the interval before wait_on starts.
		const bool wait_for_events = mfc_size >= 16 && interrupts_enabled;
		if (wait_for_events)
		{
			ch_events.atomic_op([](ch_events_t& events) { events.waiting = true; });
		}

		// A blocked WRCH suppresses cpu_work's ordinary interrupt collection:
		// its command is not accepted yet and must resume at this PC. Collect
		// an expired decrementer on the owner before checking the interrupt;
		// the timer only publishes pending work, not the guest event itself.
		if (interrupts_enabled && (ch_events.load().mask & SPU_EVENT_TM))
		{
			get_events(SPU_EVENT_TM);
		}

		if (check_mfc_interrupts(pc))
		{
			if (wait_for_events)
			{
				ch_events.atomic_op([](ch_events_t& events) { events.waiting = false; });
			}

#ifdef RPCS3_IOS
			if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_irq, trace_session);
#endif
			spu_runtime::g_escape(this);
		}

		if (mfc_size < 16)
		{
			break;
		}

		auto old = state.add_fetch(cpu_flag::wait);

		if (is_stopped(old))
		{
			if (wait_for_events)
			{
				ch_events.atomic_op([](ch_events_t& events) { events.waiting = false; });
			}

#ifdef RPCS3_IOS
			if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_stopped, trace_session);
#endif
			return false;
		}

#ifdef RPCS3_IOS
		if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_blocked, trace_session);
#endif
		thread_ctrl::wait_on(state, old);
		if (wait_for_events)
		{
			ch_events.atomic_op([](ch_events_t& events) { events.waiting = false; });
		}
#ifdef RPCS3_IOS
		if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_woke, trace_session);
#endif
	}
#ifdef RPCS3_IOS
	if (trace_full_queue) ios_publish_mfc_snapshot(*this, rpcs3::ios::signal_trace::producer_phase::mfc_ready, trace_session);
#endif

++accepted;switch(ch_mfc_cmd.cmd){
	case MFC_BARRIER_CMD:
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
	}
 default: assert(false);return false;} }

void publish_timer(named_thread<spu_thread>& target,u64 token){auto* spu=&target;struct{u64 token;}e{token};
if (spu->dec_intr_armed.compare_and_swap_test(e.token, 0))
					{
						spu->state += cpu_flag::pending + cpu_flag::pending_recheck;
						// Preserve the host notification latch as well as waking a
						// state waiter: the deadline can arrive just before a blocked
						// WRCH registers its wait with these pending flags already set.
						spu->cpu_thread::notify();
					}
}

struct spu_opcode_t{};
namespace spu_interpreter{
void set_interrupt_status(spu_thread& spu,spu_opcode_t){assert(!spu.interrupts_enabled);}
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
}


// Controlled timer callbacks use the extracted production publication body.
// Handler acknowledgements and the clock are explicit test boundaries.
template<class T>void full_fixture(T& t,MFC command=MFC_SYNC_CMD,u32 tag=31){
    rpcs3::ios::signal_trace::reset(100,true);
    typename T::ch_events_t events{};events.mask=SPU_EVENT_TM;t.ch_events.release(events);
    t.mfc_size=16;for(u32 i=0;i<16;++i)t.mfc_queue[i]={MFC_PUT_CMD,u8(i),16,16*i,0x10000+16*i,0};
    t.mfc_queue[0].cmd=MFC_GETL_CMD;t.mfc_queue[0].tag|=0x80;t.mfc_queue[1].cmd=MFC_BARRIER_CMD;
    t.ch_mfc_cmd={command,u8(tag),0,0,0x60300510,0};
    t.ch_dec_value=10;t.ch_dec_start_timestamp=1;t.dec_intr_armed.release(1);t.dec_intr_deadline=12;
    clock_now=1;thread_ctrl::g_tls_this_thread=&t.host_thread();
}
struct Outcome{bool blocked{},escaped{};u32 queue{},accepted{},return_pc{};bool waiting{},count{};};
template<class T>Outcome enter(T& t){
    Outcome out;
    try{t.process_prefix();}catch(const Escaped&){out.escaped=true;}catch(const WouldBlock&){out.blocked=true;}
    before_state_wait={};before_list_wait={};
    out.queue=t.mfc_size;out.accepted=t.accepted;out.return_pc=t.srr0;
    out.waiting=t.ch_events.load().waiting;out.count=t.ch_events.load().count;
    return out;
}
template<class T,class Publish>Outcome deadline(u32 location,Publish publish){
    named_thread<T> t;full_fixture(t);auto send=[&]{clock_now=12;publish(t,1);};
    if(location==0)send();else if(location==1)before_state_wait=send;else before_list_wait=send;
    return enter(t);
}
int main(){
    static_cast<void>(&before::exec_list_unstall);
    u32 reproduced=0,delivered=0,accepted_once=0,snr_preserved=0,masked=0,concurrent=0;
    for(u32 location:{0u,1u,2u}){
        auto old=deadline<before::spu_thread>(location,before::publish_timer);
        auto now=deadline<after::spu_thread>(location,after::publish_timer);
        assert(old.blocked&&!old.escaped&&!old.count&&old.queue==16&&old.accepted==0);++reproduced;
        const bool expected_interrupt=now.escaped&&!now.blocked&&now.count&&!now.waiting&&now.return_pc==0x1240&&now.queue==16&&now.accepted==0;
        assert(expected_interrupt);++delivered;
    }
    // Event collection and notification latching are both required. Mutation
    // runs omit one production change and must fail expected_interrupt above.
    for(bool enabled:{false,true})for(bool mask:{false,true})if(!enabled||!mask){
        named_thread<after::spu_thread> t;full_fixture(t);t.interrupts_enabled=enabled;
        if(!mask)t.ch_events.atomic_op([](auto& e){e.mask=0;});
        clock_now=12;after::publish_timer(t,1);auto out=enter(t);
        assert(out.blocked&&!out.escaped&&!out.count&&t.accepted==0);++masked;
    }
    for(bool frozen:{false,true}){
        named_thread<after::spu_thread> t;full_fixture(t);t.is_dec_frozen=frozen;
        // WRDEC or cancellation leaves an old timer token invalid. The owner
        // must not receive an event merely because that old deadline fires.
        t.dec_intr_armed.release(2);clock_now=5;after::publish_timer(t,1);
        assert(t.state.load()==0&&t.dec_intr_armed.load()==2);
        auto out=enter(t);assert(out.blocked&&!out.escaped&&!out.count);++masked;
    }
    // Frozen DEC with a valid stale scheduling request still cannot generate TM.
    {
        named_thread<after::spu_thread> t;full_fixture(t);t.is_dec_frozen=true;clock_now=20;
        after::publish_timer(t,1);auto out=enter(t);
        assert(out.blocked&&!out.escaped&&!out.count);++masked;
    }
    // Stop before draining, and stop after event registration but before sleep.
    for(bool late:{false,true}){
        named_thread<after::spu_thread> t;full_fixture(t);
        auto stop=[&]{t.state+=cpu_flag::stop;clock_now=12;after::publish_timer(t,1);};
        if(late)before_state_wait=stop;else stop();
        auto out=enter(t);assert(!out.blocked&&!out.escaped&&!out.waiting&&out.accepted==0);++masked;
    }
    // Keep the existing late-SNR path, including arrival before wait registration.
    for(u32 location:{1u,2u})for(u32 number:{0u,1u}){
        named_thread<after::spu_thread> t;full_fixture(t);
        t.ch_events.atomic_op([&](auto& e){e.mask=SPU_EVENT_S1>>number;});
        auto send=[&]{t.push_snr(number,0xfeed);};
        if(location==1)before_state_wait=send;else before_list_wait=send;
        auto out=enter(t);assert(out.escaped&&!out.blocked&&!out.waiting&&out.return_pc==0x1240&&out.accepted==0);++snr_preserved;
    }
    // The interrupted WRCH remains unaccepted. The actual unstall helper drains
    // the queue; actual IRET restores this PC; the real barrier branch accepts
    // the retried command exactly once after the handler acknowledges TM.
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(u32 tag=0;tag<32;++tag){
        named_thread<after::spu_thread> t;full_fixture(t,command,tag);clock_now=12;after::publish_timer(t,1);
        auto out=enter(t);const bool expected_interrupt=out.escaped&&out.return_pc==0x1240&&out.accepted==0;
        assert(expected_interrupt);assert(t.ch_mfc_cmd.cmd==command&&t.ch_mfc_cmd.tag==tag);
        t.ch_events.atomic_op([](auto& e){e.events&=~SPU_EVENT_TM;e.count=false;});
        t.complete_lists=true;after::exec_list_unstall(&t,0);assert(t.mfc_size==0&&t.accepted==0);
        assert(!after::IRET(t,{}));assert(t.pc==0x1240);
        assert(t.process_prefix()&&t.accepted==1&&t.mfc_size==0);++accepted_once;
    }
    // Real producer and owner threads. The native wait-list backend is modeled
    // by the adapter's CV with a two-second test watchdog, never a guest timeout.
    concurrent_wait=true;
    for(u32 iteration=0;iteration<64;++iteration){
        named_thread<after::spu_thread> t;full_fixture(t);list_entered=false;
        std::thread producer([&]{
            {std::unique_lock lock(wait_mutex);assert(wait_cv.wait_for(lock,std::chrono::seconds(2),[]{return list_entered.load(std::memory_order_acquire);}));}
            clock_now=12;after::publish_timer(t,1);
        });
        auto out=enter(t);producer.join();
        const bool expected_interrupt=out.escaped&&!out.blocked&&out.return_pc==0x1240&&out.accepted==0&&!out.waiting;
        assert(expected_interrupt);++concurrent;
    }
    std::cout<<"{\"baselineBlockedDueSchedules\":"<<reproduced<<",\"candidateDeadlineInterrupts\":"<<delivered
      <<",\"commandsAcceptedExactlyOnce\":"<<accepted_once<<",\"lateSnrPreserved\":"<<snr_preserved
      <<",\"maskedDisabledFrozenOrStale\":"<<masked<<",\"concurrentDeadlineInterrupts\":"<<concurrent
      <<",\"currentPcPreserved\":true,\"unacceptedCommandPreserved\":true,\"guestTimeoutAdded\":false}";
}
