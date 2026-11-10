#include <array>
#include <bit>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <type_traits>
#include <utility>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using s64=std::int64_t;using usz=std::size_t;
constexpr u64 umax=~u64{0};
#define ensure(x,...) assert(x)
u64 channel_notifies=0,spu_notifies=0;
// Deterministic atomic-operation boundary: callbacks receive a copy, a simulated
// competing commit causes retry, and publication occurs only on successful CAS.
// These adapters do not prove hardware atomic ordering or scheduler behavior.
template<class T>struct atomic_t{
 T value{};u64 generation=0;std::function<void()> before_commit;
 T load()const{return value;}operator T()const{return load();}
 void release(T x){value=x;++generation;}
 T exchange(T x){T old=value;release(x);return old;}
 auto fetch_op(auto f){
  using R=decltype(f(value));
  for(;;){T old=value,next=old;const auto gen=generation;
   if constexpr(std::is_void_v<R>){f(next);if(before_commit){auto cb=std::move(before_commit);before_commit={};cb();}if(gen!=generation)continue;release(next);return old;}
   else{bool success=f(next);if(!success)return std::pair<T,bool>{old,false};if(before_commit){auto cb=std::move(before_commit);before_commit={};cb();}if(gen!=generation)continue;release(next);return std::pair<T,bool>{old,true};}
  }
 }
 auto atomic_op(auto f){
  using R=decltype(f(value));
  if constexpr(std::is_void_v<R>){f(value);++generation;}
  else{auto result=f(value);++generation;return result;}
 }
 bool compare_and_swap_test(T old,T next){if(value!=old)return false;release(next);return true;}
 T fetch_and(T mask){return exchange(value&mask);}
 void notify_one(){++channel_notifies;}
};
// Production notification aliases target the high word of a 64-bit channel.
// The deterministic adapter records that notification without aliasing storage.
namespace utils{template<class T> T* bless(void*){static T notification_sink[2];return notification_sink;}}
namespace fmt{template<class...A>[[noreturn]]void throw_exception(const char*,A...){throw std::runtime_error("unexpected production exception");}}
enum class cpu_flag{again};
struct cpu_thread{struct State{void operator+=(cpu_flag){}}state;static cpu_thread* get_current(){return nullptr;}};
void busy_wait(u32){throw std::runtime_error("unexpected event lock left held");}
constexpr u32 SPU_EVENT_LR=0x400,SPU_EVENT_S1=0x200,SPU_EVENT_S2=0x100,SPU_EVENT_TM=0x20,SPU_EVENT_SN=2;
constexpr u32 SPU_EVENT_IMPLEMENTED=SPU_EVENT_LR|SPU_EVENT_TM|SPU_EVENT_SN|SPU_EVENT_S1|SPU_EVENT_S2;
namespace before {
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

			// Return true if count has changed from 0 to 1, this condition is considered satisfied even if we pushed a value directly to the special storage for waiting SPUs
			return { (old & bit_count) == 0, 1, (old & bit_wait) != 0, true };
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
struct spu_thread{
 struct ch_events_t{u32 events{};u8 locks{};bool waiting{},count{};u32 mask{};};
 spu_channel ch_snr1,ch_snr2;u32 snr_config=0;atomic_t<ch_events_t> ch_events;
 u32 raddr=0;std::array<u8,128>rdata{};u64 ch_dec_start_timestamp=0;
 bool is_stopped()const{return false;}void notify(){++spu_notifies;}
 bool reservation_check(u32,const std::array<u8,128>&){throw std::runtime_error("reservation path outside SNR test");}
 std::pair<u32,u32>read_dec(){throw std::runtime_error("timer path outside SNR test");}
 void arm_dec_interrupt(){throw std::runtime_error("timer path outside SNR test");}
 void push_snr(u32,u32);void set_events(u32);
 ch_events_t get_events(u64 mask_hint=umax,bool waiting=false,bool reading=false);
};
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
}
namespace after {
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
struct spu_thread{
 struct ch_events_t{u32 events{};u8 locks{};bool waiting{},count{};u32 mask{};};
 spu_channel ch_snr1,ch_snr2;u32 snr_config=0;atomic_t<ch_events_t> ch_events;
 u32 raddr=0;std::array<u8,128>rdata{};u64 ch_dec_start_timestamp=0;
 bool is_stopped()const{return false;}void notify(){++spu_notifies;}
 bool reservation_check(u32,const std::array<u8,128>&){throw std::runtime_error("reservation path outside SNR test");}
 std::pair<u32,u32>read_dec(){throw std::runtime_error("timer path outside SNR test");}
 void arm_dec_interrupt(){throw std::runtime_error("timer path outside SNR test");}
 void push_snr(u32,u32);void set_events(u32);
 ch_events_t get_events(u64 mask_hint=umax,bool waiting=false,bool reading=false);
};
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
}

u64 cases=0,beforeMissing=0,beforeSpurious=0,payloadChecks=0,notificationChecks=0,retryCases=0;
struct Outcome{u32 event_bits,payload,count,locks;bool event_count;u64 host_notifies,channel_notifies;};
template<class S>Outcome signal(u32 number,bool filled,bool occupied,bool waiting,u32 mask,bool to_or,u32 initial,u32 value){
 channel_notifies=spu_notifies=0;S s;auto& ch=number?s.ch_snr2:s.ch_snr1;
 using C=std::remove_reference_t<decltype(ch)>;
 s.snr_config=to_or?(1u<<number):0;
 ch.data.release((filled?C::bit_count:0)|(occupied?C::bit_occupy|C::bit_wait:0)|initial);
 if(occupied)ch.jostling_value.release(C::bit_occupy);
 typename S::ch_events_t events{};events.mask=mask;events.waiting=waiting;s.ch_events.release(events);
 s.push_snr(number,value);
 auto e=s.get_events(mask,true,true);
 assert(s.ch_events.load().count==false);
 return{e.events,occupied?static_cast<u32>(ch.jostling_value.load()):ch.get_value(),ch.get_count(),e.locks,e.count,spu_notifies,channel_notifies};
}
template<class C>void direct_channel_cases(){
 for(bool occupied:{false,true})for(bool postponed:{false,true})for(bool to_or:{false,true}){
  C c;c.data.release(C::bit_wait|(occupied?C::bit_occupy:0));if(occupied)c.jostling_value.release(C::bit_occupy);
  channel_notifies=0;auto r=c.push(0x55aa,to_or,postponed);
  assert(r.old_count==0&&r.count==1&&r.op_done&&r.notify);
  assert(channel_notifies==(postponed?0u:1u));
  assert(static_cast<u32>(occupied?c.jostling_value.load():c.data.load())==0x55aa);
  if(postponed){c.notify();assert(channel_notifies==1);}++notificationChecks;
 }
}
template<class S>void retry(bool corrected){
 for(u32 number:{0u,1u})for(bool to_or:{false,true}){
  S s;auto& ch=number?s.ch_snr2:s.ch_snr1;const u32 bit=SPU_EVENT_S1>>number;
  typename S::ch_events_t events{};events.mask=bit;events.waiting=true;s.ch_events.release(events);s.snr_config=to_or?(1u<<number):0;
  spu_notifies=0;
  ch.data.before_commit=[&]{s.push_snr(number,0x0f);assert(s.ch_events.load().count==corrected);};
  s.push_snr(number,0xf0);
  assert(ch.get_value()==(to_or?0xffu:0xf0u));
  assert(s.ch_events.load().locks==0&&spu_notifies==1);
  // Both versions happen to emit once in this two-writer schedule; which writer
  // causes it differs. The baseline loses the first empty->full publication.
  assert(s.get_events(bit,true,true).count);
  if(corrected)++retryCases;
 }
}
int main(){
 for(u32 number:{0u,1u})for(bool filled:{false,true})for(bool occupied:{false,true})for(bool waiting:{false,true})for(bool to_or:{false,true})
 for(u32 initial:{0u,1u,0x55aa55aau,0xffffffffu})for(u32 value:{0u,1u,0xaa55aa55u,0xffffffffu}){
  if(occupied&&filled)continue;
  if(!filled&&initial)continue;
  const u32 bit=SPU_EVENT_S1>>number;
  for(u32 mask:{0u,bit,SPU_EVENT_S1|SPU_EVENT_S2,bit==SPU_EVENT_S1?SPU_EVENT_S2:SPU_EVENT_S1}){
   auto old=signal<before::spu_thread>(number,filled,occupied,waiting,mask,to_or,initial,value);
   auto fresh=signal<after::spu_thread>(number,filled,occupied,waiting,mask,to_or,initial,value);
   const bool should_event=!filled;const bool should_count=should_event&&(mask&bit);
   assert(fresh.event_bits==(should_event?bit:0));assert(fresh.event_count==should_count);
   assert(fresh.host_notifies==u64(should_count&&waiting));assert(fresh.locks==0&&old.locks==0);
   assert(old.payload==fresh.payload&&old.count==fresh.count&&old.channel_notifies==fresh.channel_notifies);
   assert(fresh.payload==((to_or&&!occupied)?initial|value:value));
   if(should_event&&!(old.event_bits&bit))++beforeMissing;
   if(!should_event&&(old.event_bits&bit))++beforeSpurious;
   ++cases;++payloadChecks;
  }
 }
 direct_channel_cases<after::spu_channel>();
 for(u32 number:{0u,1u})for(bool to_or:{false,true}){
  after::spu_thread s;auto& ch=number?s.ch_snr2:s.ch_snr1;const u32 bit=SPU_EVENT_S1>>number;s.snr_config=to_or?(1u<<number):0;
  for(u32 cycle=0;cycle<128;++cycle){
   typename after::spu_thread::ch_events_t e{};e.mask=bit;s.ch_events.release(e);
   assert(!s.get_events(bit,true,true).count);spu_notifies=0;s.push_snr(number,cycle);
   auto event=s.get_events(bit,true,true);assert(event.count&&(event.events&bit)&&spu_notifies==1);
   u32 out=~cycle;assert(ch.try_pop(out)&&out==cycle&&ch.get_count()==0);++payloadChecks;
  }
 }
 retry<before::spu_thread>(false);retry<after::spu_thread>(true);
 assert(beforeMissing&&beforeSpurious);
 std::cout<<"{\"matrixCases\":"<<cases<<",\"baselineMissingEvents\":"<<beforeMissing<<",\"baselineSpuriousEvents\":"<<beforeSpurious
 <<",\"candidateEventMismatches\":0,\"payloadComparisons\":"<<payloadChecks<<",\"postponedAndJostlingCases\":"<<notificationChecks
 <<",\"deterministicCasRetryCases\":"<<retryCases<<",\"repeatPopRepushCycles\":512,\"sameChannelPayloadAndNotify\":true,\"eventLocksReleased\":true}";
}
