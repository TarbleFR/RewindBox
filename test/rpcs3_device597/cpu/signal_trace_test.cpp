#include "ios/IOSSignalTrace.h"
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <new>
#include <thread>

namespace trace = rpcs3::ios::signal_trace;
static std::atomic<bool> forbid_allocations{};
void* operator new(std::size_t size) { if(forbid_allocations.load())std::abort();if(auto p=std::malloc(size))return p;throw std::bad_alloc{}; }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* p)noexcept{std::free(p);}
void operator delete[](void* p)noexcept{std::free(p);}
void operator delete(void* p,std::size_t)noexcept{std::free(p);}
void operator delete[](void* p,std::size_t)noexcept{std::free(p);}

constexpr std::uint32_t label=0x60300510;
int main(){
    forbid_allocations=true;
    trace::reset(1,false);
    assert(!trace::begin_acquire(label,2,1,10));
    assert(!trace::overlap(label,4));
    assert(trace::snapshot().event_count==0);
    trace::reset(2,true);
    auto first=trace::begin_acquire(label,1,1,20);
    auto prior=trace::overlap(label,4);
    trace::write_event(prior,trace::event_kind::spu_dma_commit,2,30,label,4,0x2000001,0x1230,0x20);
    auto second=trace::begin_acquire(label,3,2,40);
    assert(second.acquire_sequence>first.acquire_sequence);
    assert(trace::summary().watch.watch_since_us==20);
    auto s=trace::snapshot();assert(s.event_count==3);
    assert(trace::snapshot().event_count==3); // Non-destructive history.
    bool found=false;for(std::size_t i=0;i<s.event_count;++i){auto e=s.events[i];if(e.kind==trace::event_kind::spu_dma_commit){assert(e.acquire_sequence==first.acquire_sequence&&e.timestamp_us<40&&!e.value_is_written_argument);found=true;}}
    assert(found);
    assert(!trace::overlap(label+4,4));assert(!trace::overlap(label-4,4));
    assert(trace::overlap(label-3,4));assert(trace::overlap(label+3,1));assert(!trace::overlap(label,0));
    assert(!trace::overlap(0xfffffff0,0x100));
    trace::acquire_state(second,trace::event_kind::stalled,2,50);
    assert(trace::summary().watch.stalled&&trace::summary().watch.active);
    trace::acquire_state(second,trace::event_kind::resolved,3,60);
    assert(!trace::summary().watch.stalled&&!trace::summary().watch.active);
    assert(trace::overlap(label,4)); // Last address survives completion.

    auto old=trace::overlap(label,4);
    trace::snapshot_result latched{};
    for(std::uint32_t i=0;i<200;++i)trace::begin_acquire(label,3,3,61+i);
    assert(trace::take_stall_snapshot(latched));
    assert(latched.watch.stalled&&latched.watch.acquire_sequence==second.acquire_sequence&&latched.watch.observed==2);
    assert(!trace::take_stall_snapshot(latched));
    trace::reset(3,true);
    trace::write_event(old,trace::event_kind::spu_dma_commit,4,70,label,4);
    assert(trace::snapshot().event_count==0&&!trace::overlap(label,4));
    assert(trace::summary().totals.stale_session_dropped==1);
    auto token=trace::begin_acquire(label,5,4,80);
    trace::acquire_state(token,trace::event_kind::stalled,4,81);
    trace::acquire_state(token,trace::event_kind::stalled,4,82);
    assert(trace::summary().totals.stall_overwritten==1);
    assert(trace::retained_stall.try_lock());auto sdrops=trace::stall_dropped.load();
    trace::acquire_state(token,trace::event_kind::stalled,4,83);trace::retained_stall.unlock();assert(trace::stall_dropped.load()==sdrops+1);
    for(std::uint32_t i=0;i<200;++i)trace::write_event(token,trace::event_kind::rsx_cpu_commit,i,90+i,label,4);
    s=trace::snapshot();assert(s.event_count==trace::history_capacity&&s.totals.history_overwritten>0);
    assert(trace::watch.try_lock());auto drops=trace::events_dropped.load();assert(!trace::overlap(label,4));trace::watch.unlock();assert(trace::events_dropped.load()==drops+1);
    const auto next=trace::next_event.load();auto& target=trace::history[next%trace::history_capacity];assert(target.try_lock());
    drops=trace::events_dropped.load();trace::write_event(token,trace::event_kind::rsx_cpu_commit,5,300,label,4);target.unlock();assert(trace::events_dropped.load()==drops+1);

    trace::producer_state p{};p.session=3;p.id=0x2000001;p.size=16;p.phase=trace::producer_phase::mfc_blocked;p.published_us=100;p.queue[0]={0x44,0x80,0x40,0x2000,16};
    trace::publish_producer(p);s=trace::snapshot();assert(s.producer_count==1&&s.producers[0].last_progress_us==0&&s.producers[0].blocked_since_us==100);
    p.published_us=110;trace::publish_producer(p);s=trace::snapshot();assert(s.producers[0].blocked_since_us==100);
    p.phase=trace::producer_phase::mfc_ready;p.size=0;p.published_us=120;trace::publish_producer(p);s=trace::snapshot();assert(s.producers[0].last_progress_us==120);
    p.id+=32;trace::publish_producer(p);assert(trace::summary().totals.producer_replaced==1);
    auto& producer=trace::producers[p.id%trace::producer_capacity];assert(producer.try_lock());auto pdrops=trace::producer_dropped.load();trace::publish_producer(p);producer.unlock();assert(trace::producer_dropped.load()==pdrops+1);
    forbid_allocations=false;

    // Concurrent readers may skip a busy slot; every returned record must be
    // individually coherent, and old-session completions stay distinguishable.
    trace::reset(4,true);token=trace::begin_acquire(label,777,776,400);
    std::atomic<unsigned> complete{};std::array<std::thread,5> writers;
    for(unsigned thread=0;thread<4;++thread)writers[thread]=std::thread([&,thread]{
        for(std::uint32_t i=0;i<10000;++i){trace::write_event(token,trace::event_kind::spu_dma_commit,i,500+i,label,4,thread,i^0xa5a5,0x20);
            trace::producer_state row{};row.session=4;row.id=thread;row.pc=i;row.size=i%17;row.queue[0].eal=i^0x5a5a;trace::publish_producer(row);}
        ++complete;
    });
    writers[4]=std::thread([&]{for(std::uint64_t i=0;i<128;++i){trace::acquire_state(token,trace::event_kind::stalled,776,1000+i*2);trace::acquire_state(token,trace::event_kind::resolved,777,1001+i*2);}++complete;});
    std::uint64_t snapshots=0,stall_snapshots=0;
    const auto check_stall=[&]{if(trace::take_stall_snapshot(latched)){assert(latched.session==4&&latched.watch.stalled&&latched.watch.acquire_sequence==token.acquire_sequence&&latched.watch.address==label&&latched.watch.expected==777&&latched.watch.observed==776);++stall_snapshots;}};
    while(complete.load()!=writers.size()){
        auto concurrent=trace::snapshot();assert(concurrent.session==4);
        for(std::size_t i=0;i<concurrent.event_count;++i){auto e=concurrent.events[i];assert(e.session==4&&e.address==label);if(e.kind==trace::event_kind::spu_dma_commit)assert(e.pc==(e.value^0xa5a5));}
        for(std::size_t i=0;i<concurrent.producer_count;++i){auto row=concurrent.producers[i];assert(row.session==4&&row.queue[0].eal==(row.pc^0x5a5a));}
        check_stall();
        ++snapshots;
    }
    for(auto& thread:writers)thread.join();
    check_stall();assert(stall_snapshots);
    trace::reset(5,false);assert(trace::snapshot().event_count==0&&trace::snapshot().producer_count==0&&!trace::take_stall_snapshot(latched));
    std::cout<<"{\"disabledNoRecords\":true,\"priorWriteRetained\":true,\"historyNonDestructive\":true,\"sessionIsolation\":true,\"overlapBoundaryCases\":7,\"historyCapacity\":"<<trace::history_capacity
             <<",\"producerCapacity\":"<<trace::producer_capacity<<",\"overflowAndBusyDrops\":true,\"allocationTrapPassed\":true,\"concurrentWrites\":40000,\"concurrentSnapshots\":"<<snapshots
             <<",\"concurrentStallSnapshots\":"<<stall_snapshots<<",\"resolvedStallRetainedAfter200HealthyAcquires\":true,\"stallReplacementAndBusyDrops\":true,\"storageBytes\":"<<(sizeof(trace::history)+sizeof(trace::producers)+sizeof(trace::watch)+sizeof(trace::retained_stall))<<"}";
}
