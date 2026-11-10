#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <new>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>

#ifdef NDEBUG
#error Timer tests require assertions
#endif
using u32=std::uint32_t; using u64=std::uint64_t;
using namespace std::literals;
constexpr u64 umax=std::numeric_limits<u64>::max();
enum class cpu_flag : u32
{
	stop, // Thread not running (HLE, initial state)
	exit, // Irreversible exit
	wait, // Indicates waiting state, set by the thread itself
	temp, // Indicates that the thread cannot properly return after next check_state()
	pause, // Thread suspended by suspend_all technique
	suspend, // Thread suspended
	ret, // Callback return requested
	again, // Thread must complete the syscall after deserialization
	signal, // Thread received a signal (HLE)
	memory, // Thread must unlock memory mutex
	pending, // Thread has postponed work
	pending_recheck, // Thread needs to recheck if there is pending work before ::pending removal
	notify, // Flag meant solely to allow atomic notification on state without changing other flags
	yield, // Thread is being requested to yield its execution time if it's running
	preempt, // Thread is being requested to preempt the execution of all CPU threads

	req_exit, // Request the thread to exit
	dbg_global_pause, // Emulation paused
	dbg_pause, // Thread paused
	dbg_step, // Thread forced to pause after one step (one instruction, etc)

	__bitset_enum_max
};

constexpr u32 operator+(cpu_flag a,cpu_flag b) { return (1u<<u32(a))|(1u<<u32(b)); }
struct { struct { u32 clocks_scale{100}; } core; } g_cfg;

// Scheduling, locking, IDM and channel boundaries are deterministic adapters.
// Production locking scopes and all timer decisions below remain verbatim.
struct Environment {
    u64 now{}, lock_depth{}, clock_reads{}, timer_notifications{}, lookups{}, rejected_tokens{};
    u64 allocation_attempts{}, due_allocations{}, fail_allocation{}, erases{}, shifts{};
    bool abort{}, timing_retain_checked{};
    std::vector<u64> ticks, waits;
    std::vector<std::tuple<u32,u64,u32>> notified;
    std::vector<std::vector<std::tuple<u64,u32,u64>>> pending;
    std::function<void()> inspect_pending;
    std::function<void(std::size_t)> on_wait;
    std::function<void(u32)> on_notify, on_lookup;
    void* timer{};
} env;
struct shared_mutex {
    std::mutex value;
    void lock() { assert(env.lock_depth==0); value.lock(); ++env.lock_depth; }
    void unlock() { assert(env.lock_depth==1); --env.lock_depth; value.unlock(); }
};
template<class T> struct ArmedVector : std::vector<T> {
    using Base=std::vector<T>; using typename Base::iterator;
    iterator erase(iterator it) {
        ++env.erases; env.shifts+=this->end()-it-1;
        return Base::erase(it);
    }
    iterator erase(iterator first,iterator last) {
        if(first!=last) { ++env.erases; env.shifts+=this->end()-last; }
        return Base::erase(first,last);
    }
};
template<class T> struct DueVector : std::vector<T> {
    using Base=std::vector<T>;
    void allocation() {
        ++env.allocation_attempts;
        if(env.fail_allocation==env.allocation_attempts) throw std::bad_alloc{};
        ++env.due_allocations;
    }
    void reserve(std::size_t count) {
        if(count>this->capacity()) allocation();
        Base::reserve(count);
    }
    void push_back(const T& value) {
        if(this->size()==this->capacity()) allocation();
        Base::push_back(value);
    }
};
enum class thread_state { running,aborting };
namespace thread_ctrl {
thread_state state() { return env.abort?thread_state::aborting:thread_state::running; }
template<class T> void notify(T&) { assert(env.lock_depth==0); ++env.timer_notifications; }
void wait_for(u64 delay) {
    assert(env.lock_depth==0);
    if(env.on_wait) env.on_wait(env.waits.size());
    if(env.inspect_pending) env.inspect_pending();
    env.waits.push_back(delay);
    if(env.waits.size()>env.ticks.size()) { env.abort=true; return; }
    env.now=env.ticks[env.waits.size()-1];
}
}
u64 get_timebased_time() { ++env.clock_reads; return env.now; }
template<class T> using named_thread=T;
struct FXO {
    template<class T> T& get() { assert(env.timer); return *static_cast<T*>(env.timer); }
} fxo;
FXO* g_fxo=&fxo;
struct Token {
    u64 value{};
    bool compare_and_swap_test(u64 expected,u64 next) {
        if(value!=expected) { ++env.rejected_tokens; return false; }
        value=next; return true;
    }
};
struct Flags {
    u32 id{}, value{};
    void operator+=(u32 mask) { assert(env.lock_depth==0); value|=mask; }
    void notify_one() {
        assert(env.lock_depth==0);
        env.notified.emplace_back(id,env.now,value);
        if(env.on_notify) env.on_notify(id);
    }
};
struct spu_thread { u32 id{}; Token dec_intr_armed; Flags state; };
std::map<u32,std::shared_ptr<spu_thread>> registry;
namespace idm {
template<class T,class F> std::shared_ptr<T> get(u32 id,F callback) {
    assert(env.lock_depth==0); ++env.lookups;
    if(env.on_lookup) env.on_lookup(id);
    const auto found=registry.find(id);
    if(found==registry.end()) return {};
    callback(*found->second);
    return found->second;
}
}

namespace before {
struct spu_dec_intr_timer
{
	struct entry
	{
		u64 due;
		u32 id;
		u64 token;
	};

	shared_mutex mutex;
	ArmedVector<entry> armed;

	void arm(u64 due, u32 id, u64 token)
	{
		{
			std::lock_guard lock(mutex);
			const auto it = std::find_if(armed.begin(), armed.end(), [&](const auto& e) { return e.id == id; });
			if (it != armed.end())
				*it = {due, id, token};
			else
				armed.push_back({due, id, token});
		}
		thread_ctrl::notify(g_fxo->get<named_thread<spu_dec_intr_timer>>());
	}

	void operator()()
	{
		u64 sleep_us = umax;
		while (thread_ctrl::state() != thread_state::aborting)
		{
			thread_ctrl::wait_for(sleep_us);
			if (thread_ctrl::state() == thread_state::aborting)
				break;

			const u64 now = get_timebased_time();
			DueVector<entry> due_entries;
			sleep_us = umax;
			{
				std::lock_guard lock(mutex);
				u64 sleep_scaled_ticks = umax;
				const auto pending_end = std::remove_if(armed.begin(), armed.end(), [&](const entry& pending)
				{
					if (pending.due <= now)
					{
						if (due_entries.empty())
						{
							// Allocate before compacting the queue. Entry copies and
							// moves cannot throw, so no allocation can interrupt it.
							due_entries.reserve(armed.size());
						}
						due_entries.push_back(pending);
						return true;
					}
					// Keep the original unsigned multiplication before taking the
					// minimum, including its wraparound for distant deadlines.
					sleep_scaled_ticks = std::min(sleep_scaled_ticks, (pending.due - now) * 100);
					return false;
				});
				// Preserve notification and pending-entry order while moving each
				// survivor at most once, rather than shifting it after every expiry.
				armed.erase(pending_end, armed.end());
				if (!armed.empty())
				{
					// The monotone conversion needs one division per sweep, rather
					// than one per pending entry. No allocation when nothing expires.
					sleep_us = sleep_scaled_ticks / (80 * std::max<u64>(g_cfg.core.clocks_scale, 1)) + 1;
				}
			}
			for (const auto& e : due_entries)
			{
				// Retain the thread while publishing work, outside the timer lock.
				if (const auto spu = idm::get<named_thread<spu_thread>>(e.id, [](auto&) {}))
				{
					if (spu->dec_intr_armed.compare_and_swap_test(e.token, 0))
					{
						spu->state += cpu_flag::pending + cpu_flag::pending_recheck;
						spu->state.notify_one();
					}
				}
			}
		}
	}

	static constexpr auto thread_name = "SPU DEC Interrupts"sv;
};
static_assert(std::is_trivially_copyable_v<spu_dec_intr_timer::entry>);
static_assert(std::is_nothrow_move_assignable_v<spu_dec_intr_timer::entry>);
}

namespace after {
struct spu_dec_intr_timer
{
	struct entry
	{
		u64 due;
		u32 id;
		u64 token;
	};

	shared_mutex mutex;
	ArmedVector<entry> armed;

	void arm(u64 due, u32 id, u64 token)
	{
		{
			std::lock_guard lock(mutex);
			const auto it = std::find_if(armed.begin(), armed.end(), [&](const auto& e) { return e.id == id; });
			if (it != armed.end())
				*it = {due, id, token};
			else
				armed.push_back({due, id, token});
		}
		thread_ctrl::notify(g_fxo->get<named_thread<spu_dec_intr_timer>>());
	}

	void operator()()
	{
		u64 sleep_us = umax;
		// Reuse the worker's trivial expiry scratch across wakeups. Growing it
		// still happens before queue compaction; no thread references are retained.
		DueVector<entry> due_entries;
		while (thread_ctrl::state() != thread_state::aborting)
		{
			thread_ctrl::wait_for(sleep_us);
			if (thread_ctrl::state() == thread_state::aborting)
				break;

			const u64 now = get_timebased_time();
			sleep_us = umax;
			{
				std::lock_guard lock(mutex);
				u64 sleep_scaled_ticks = umax;
				const auto pending_end = std::remove_if(armed.begin(), armed.end(), [&](const entry& pending)
				{
					if (pending.due <= now)
					{
						if (due_entries.empty())
						{
							// Allocate before compacting the queue. Entry copies and
							// moves cannot throw, so no allocation can interrupt it.
							due_entries.reserve(armed.size());
						}
						due_entries.push_back(pending);
						return true;
					}
					// Keep the original unsigned multiplication before taking the
					// minimum, including its wraparound for distant deadlines.
					sleep_scaled_ticks = std::min(sleep_scaled_ticks, (pending.due - now) * 100);
					return false;
				});
				// Preserve notification and pending-entry order while moving each
				// survivor at most once, rather than shifting it after every expiry.
				armed.erase(pending_end, armed.end());
				if (!armed.empty())
				{
					// The monotone conversion needs one division per sweep, rather
					// than one per pending entry. No allocation when nothing expires.
					sleep_us = sleep_scaled_ticks / (80 * std::max<u64>(g_cfg.core.clocks_scale, 1)) + 1;
				}
			}
			for (const auto& e : due_entries)
			{
				// Retain the thread while publishing work, outside the timer lock.
				if (const auto spu = idm::get<named_thread<spu_thread>>(e.id, [](auto&) {}))
				{
					if (spu->dec_intr_armed.compare_and_swap_test(e.token, 0))
					{
						spu->state += cpu_flag::pending + cpu_flag::pending_recheck;
						spu->state.notify_one();
					}
				}
			}
			due_entries.clear();
		}
	}

	static constexpr auto thread_name = "SPU DEC Interrupts"sv;
};
static_assert(std::is_trivially_copyable_v<spu_dec_intr_timer::entry>);
static_assert(std::is_nothrow_move_assignable_v<spu_dec_intr_timer::entry>);
}


void add_thread(u32 id,u64 token) {
    auto thread=std::make_shared<spu_thread>();
    thread->id=id; thread->dec_intr_armed.value=token; thread->state.id=id;
    registry[id]=std::move(thread);
}
using Snapshot=std::vector<std::tuple<u64,u32,u64>>;
template<class Timer> Snapshot snapshot(const Timer& timer) {
    Snapshot result;
    for(const auto& entry:timer.armed) result.emplace_back(entry.due,entry.id,entry.token);
    return result;
}
struct Result {
    std::vector<u64> waits;
    std::vector<std::tuple<u32,u64,u32>> notified;
    std::vector<Snapshot> pending;
    Snapshot remaining;
    u64 erases{},shifts{},allocations{},rejected{},clock_reads{},arm_notifications{};
    bool threw{},retained{};
};
template<class Timer> Result run(u32 count,u32 pattern,u32 scale,bool fail=false,bool reenter=false,bool shutdown=false) {
    env={}; registry.clear(); g_cfg.core.clocks_scale=scale;
    Timer timer; env.timer=&timer;
    env.ticks=shutdown?std::vector<u64>{}:std::vector<u64>{1000,4000};
    env.fail_allocation=fail?1:0;
    env.inspect_pending=[&]{env.pending.push_back(snapshot(timer));};
    for(u32 i=0;i<count;++i) {
        u64 due=2000+i;
        if(pattern==1 || (pattern==2 && i%2==0) || (pattern==3 && i==0) || (pattern==4 && i+1==count)) due=1000;
        if(pattern==5) due=999+i%3;
        const u64 token=100+i;
        timer.arm(due,i,token);
        if(reenter || i%5==0) add_thread(i,token);
        else if(i%5==1) add_thread(i,0); // cancellation
        else if(i%5==2) add_thread(i,token+1000); // newer countdown
        else if(i%5==4) add_thread(i,token+10000); // same ID, another lifetime
        // i%5==3: thread no longer exists.
    }
    // Replacing an existing ID must retain its position in the pending queue.
    if(count>1) {
        const auto& old=timer.armed[1];
        timer.arm(old.due,old.id,old.token);
    }
    std::weak_ptr<spu_thread> old_thread;
    bool reentered=false;
    if(reenter) {
        old_thread=registry.at(0);
        env.on_notify=[&](u32 id) {
            if(id==0 && !reentered) {
                reentered=true;
                registry.erase(id);
                assert(!old_thread.expired()); // production local shared_ptr retains it
                add_thread(id,9999);
                timer.arm(4000,id,9999); // callback outside timer lock
                env.timing_retain_checked=true;
            }
        };
    }
    // A token may change after the timer snapshot, immediately before CAS.
    env.on_lookup=[&](u32 id) {
        if(!reenter && id==5 && env.now==1000) registry.at(id)->dec_intr_armed.value=70000;
    };
    bool threw=false;
    try { timer(); } catch(const std::bad_alloc&) { threw=true; }
    assert(env.lock_depth==0);
    if(reenter) { assert(reentered && old_thread.expired()); assert(env.timing_retain_checked); }
    Result result{env.waits,env.notified,env.pending,snapshot(timer),env.erases,env.shifts,
                  env.due_allocations,env.rejected_tokens,env.clock_reads,env.timer_notifications,
                  threw,env.timing_retain_checked};
    env={}; registry.clear();
    return result;
}
struct Counts {
    u64 cases{},reentrant{},shutdown{},failures{},old_erases{},new_erases{},old_shifts{},new_shifts{};
    u64 old_allocations{},new_allocations{},rejected{},notifications{},orders{},deadlines{};
} counts;
void compare(const Result& old,const Result& fresh) {
    assert(old.waits==fresh.waits);
    assert(old.notified==fresh.notified);
    assert(old.pending==fresh.pending);
    assert(old.remaining==fresh.remaining);
    assert(old.rejected==fresh.rejected && old.clock_reads==fresh.clock_reads);
    assert(old.arm_notifications==fresh.arm_notifications && old.threw==fresh.threw);
    assert(old.retained==fresh.retained);
    counts.old_erases+=old.erases; counts.new_erases+=fresh.erases;
    counts.old_shifts+=old.shifts; counts.new_shifts+=fresh.shifts;
    counts.old_allocations+=old.allocations; counts.new_allocations+=fresh.allocations;
    counts.rejected+=fresh.rejected; counts.notifications+=fresh.notified.size();
    counts.orders+=fresh.pending.size(); counts.deadlines+=fresh.waits.size();
}
// Uses the existing deterministic scheduler/IDM/atomic adapters and complete
// production class bodies. Only this additional driver and assertions are new.
template<class Timer> Result repeated_run(const std::vector<u32>& batches,int fail_round=-1) {
    env={};registry.clear();g_cfg.core.clocks_scale=100;
    Timer timer;env.timer=&timer;
    for(u32 i=0;i<batches.size();++i)env.ticks.push_back(1000+1000*i);
    env.inspect_pending=[&]{env.pending.push_back(snapshot(timer));};
    env.on_wait=[&](std::size_t round){
        if(round>=batches.size())return;
        for(u32 id=0;id<batches[round];++id){
            const u64 token=1+id+u64{round}*10000;
            add_thread(id,token);timer.arm(env.ticks[round],id,token);
        }
        if(static_cast<int>(round)==fail_round)env.fail_allocation=env.allocation_attempts+1;
    };
    bool threw=false;
    try{timer();}catch(const std::bad_alloc&){threw=true;}
    assert(env.lock_depth==0);
    Result result{env.waits,env.notified,env.pending,snapshot(timer),env.erases,env.shifts,
                  env.due_allocations,env.rejected_tokens,env.clock_reads,env.timer_notifications,
                  threw,env.timing_retain_checked};
    env={};registry.clear();return result;
}
int main(){
    for(u32 count:{0u,1u,2u,6u,16u,64u,256u})for(u32 pattern=0;pattern<6;++pattern)
    for(u32 scale:{0u,1u,25u,100u,200u}){
        const auto old=run<before::spu_dec_intr_timer>(count,pattern,scale);
        const auto fresh=run<after::spu_dec_intr_timer>(count,pattern,scale);
        compare(old,fresh);assert(fresh.remaining.empty());++counts.cases;
    }
    for(u32 pattern:{1u,4u}){
        const auto old=run<before::spu_dec_intr_timer>(6,pattern,100,true);
        const auto fresh=run<after::spu_dec_intr_timer>(6,pattern,100,true);
        compare(old,fresh);assert(fresh.threw&&fresh.notified.empty()&&fresh.remaining==fresh.pending.front());++counts.failures;
    }
    const auto old_reentrant=run<before::spu_dec_intr_timer>(6,1,100,false,true);
    const auto fresh_reentrant=run<after::spu_dec_intr_timer>(6,1,100,false,true);
    compare(old_reentrant,fresh_reentrant);assert(fresh_reentrant.retained&&fresh_reentrant.notified.size()==7);++counts.reentrant;
    const auto old_shutdown=run<before::spu_dec_intr_timer>(6,1,100,false,false,true);
    const auto fresh_shutdown=run<after::spu_dec_intr_timer>(6,1,100,false,false,true);
    compare(old_shutdown,fresh_shutdown);
    assert(fresh_shutdown.clock_reads==0&&fresh_shutdown.allocations==0&&fresh_shutdown.notified.empty());++counts.shutdown;

    const std::vector<u32> stable(128,6);
    const auto repeated_old=repeated_run<before::spu_dec_intr_timer>(stable);
    const auto repeated_new=repeated_run<after::spu_dec_intr_timer>(stable);
    compare(repeated_old,repeated_new);
    assert(repeated_old.allocations==128&&repeated_new.allocations==1);
    assert(repeated_new.notified.size()==768&&repeated_new.remaining.empty());
    std::vector<u32> varied;
    for(u32 round=0;round<128;++round)for(u32 size:{0u,1u,6u,64u,6u,257u,0u,16u})varied.push_back(size);
    const auto varied_old=repeated_run<before::spu_dec_intr_timer>(varied);
    const auto varied_new=repeated_run<after::spu_dec_intr_timer>(varied);
    compare(varied_old,varied_new);
    assert(varied_old.allocations==768&&varied_new.allocations==4);
    // A later growth failure must leave the pending queue untouched just like
    // the first allocation failure. The failure is injected at the same wake.
    const auto fail_old=repeated_run<before::spu_dec_intr_timer>({6,6,64},2);
    const auto fail_new=repeated_run<after::spu_dec_intr_timer>({6,6,64},2);
    compare(fail_old,fail_new);
    assert(fail_new.threw&&fail_new.remaining.size()==64&&fail_new.notified.size()==12);
    std::cout<<"{\"passed\":true,\"assertionsActive\":true,\"matrixCases\":"<<counts.cases
        <<",\"reentrantCases\":"<<counts.reentrant<<",\"shutdownCases\":"<<counts.shutdown
        <<",\"firstAllocationFailureCases\":"<<counts.failures<<",\"laterGrowthFailureCases\":1"
        <<",\"stableWakes\":128,\"baselineStableAllocations\":"<<repeated_old.allocations
        <<",\"candidateStableAllocations\":"<<repeated_new.allocations
        <<",\"variableWakes\":1024,\"baselineVariableAllocations\":"<<varied_old.allocations
        <<",\"candidateVariableAllocations\":"<<varied_new.allocations
        <<",\"obsoleteTokensRejected\":"<<counts.rejected<<",\"notifications\":"<<counts.notifications
        <<",\"pendingOrderComparisons\":"<<counts.orders<<",\"waitDeadlineComparisons\":"<<counts.deadlines
        <<",\"callbacksWhileLocked\":0,\"samePublicationAndWaitOrder\":true,\"reentrantRetainedUntilCallbackReturned\":true}\n";
}
