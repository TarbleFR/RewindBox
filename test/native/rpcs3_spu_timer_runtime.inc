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
@FLAGS@
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

@BEFORE@
@AFTER@

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
int main() {
    for(u32 count:{0u,1u,2u,6u,16u,64u,256u}) for(u32 pattern=0;pattern<6;++pattern)
    for(u32 scale:{0u,1u,25u,100u,200u}) {
        const auto old=run<before::spu_dec_intr_timer>(count,pattern,scale);
        const auto fresh=run<after::spu_dec_intr_timer>(count,pattern,scale);
        compare(old,fresh);
        assert(fresh.remaining.empty());
        ++counts.cases;
    }
    for(u32 pattern:{1u,4u}) {
        const auto old=run<before::spu_dec_intr_timer>(6,pattern,100,true);
        const auto fresh=run<after::spu_dec_intr_timer>(6,pattern,100,true);
        compare(old,fresh);
        assert(fresh.threw && fresh.notified.empty() && fresh.remaining==fresh.pending.front());
        ++counts.failures;
    }
    const auto old_reentrant=run<before::spu_dec_intr_timer>(6,1,100,false,true);
    const auto fresh_reentrant=run<after::spu_dec_intr_timer>(6,1,100,false,true);
    compare(old_reentrant,fresh_reentrant);
    assert(fresh_reentrant.retained && fresh_reentrant.notified.size()==7);
    ++counts.reentrant;
    const auto old_shutdown=run<before::spu_dec_intr_timer>(6,1,100,false,false,true);
    const auto fresh_shutdown=run<after::spu_dec_intr_timer>(6,1,100,false,false,true);
    compare(old_shutdown,fresh_shutdown);
    assert(fresh_shutdown.clock_reads==0 && fresh_shutdown.allocations==0 && fresh_shutdown.notified.empty());
    assert(fresh_shutdown.remaining==fresh_shutdown.pending.front());
    ++counts.shutdown;
    std::cout<<"{\"passed\":true,\"assertionsActive\":true,\"matrixCases\":"<<counts.cases
        <<",\"reentrantCases\":"<<counts.reentrant<<",\"shutdownCases\":"<<counts.shutdown
        <<",\"firstAllocationFailureCases\":"<<counts.failures
        <<",\"baselineNonemptyErases\":"<<counts.old_erases<<",\"candidateNonemptyErases\":"<<counts.new_erases
        <<",\"baselineShiftedSlots\":"<<counts.old_shifts<<",\"candidateShiftedSlots\":"<<counts.new_shifts
        <<",\"baselineDueAllocations\":"<<counts.old_allocations<<",\"candidateDueAllocations\":"<<counts.new_allocations
        <<",\"obsoleteTokensRejected\":"<<counts.rejected<<",\"notifications\":"<<counts.notifications
        <<",\"pendingOrderComparisons\":"<<counts.orders<<",\"waitDeadlineComparisons\":"<<counts.deadlines
        <<",\"callbacksWhileLocked\":0,\"reentrantRetainedUntilCallbackReturned\":true}\n";
}
