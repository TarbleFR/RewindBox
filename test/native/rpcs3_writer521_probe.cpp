// SPDX-License-Identifier: MIT
// Exact production destructor/recorder, with explicit portable atomic adapters.
// This is a host synchronization experiment, not CELL/game emulation.
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>
#include <algorithm>
using u64=uint64_t;using u32=uint32_t;using usz=size_t;
namespace utils { u64 get_tsc(){
#if defined(__aarch64__) || defined(__arm64__)
 u64 value;asm volatile("mrs %0, cntvct_el0":"=r"(value));return value;
#else
 return std::chrono::steady_clock::now().time_since_epoch().count();
#endif
}}
struct alignas(128) word {
 std::atomic<u64> bits{0};
 u64 operator &=(u64 mask){return bits.fetch_and(mask,std::memory_order_acq_rel)&mask;}
 void release(u64 value){bits.store(value,std::memory_order_release);}
 void notify_all(){bits.notify_all();}
};
word g_range_lock_set[64],g_range_lock_bits[2];
std::mutex gate_mutex;std::condition_variable gate_cv;
bool parked=false,entered=false,unpark=false;
struct profile {
 static constexpr size_t writer_lock_source_count=5;
 std::array<std::atomic<u64>,5> m_writer_lock_count{},m_writer_lock_acquire_ticks{},m_writer_lock_hold_ticks{},m_writer_lock_hold_max{};
 #include "writer521-recorder.inc"
 #include "writer521-maximum.inc"
 void reset(){for(size_t i=0;i<5;++i){m_writer_lock_count[i]=0;m_writer_lock_acquire_ticks[i]=0;m_writer_lock_hold_ticks[i]=0;m_writer_lock_hold_max[i]=0;}}
} counters;
namespace rpcs3::ios {void record_writer_lock(u32 source,u64 acquire,u64 hold){
 {
  std::unique_lock lock(gate_mutex,std::defer_lock);
  if(parked){lock.lock();entered=true;gate_cv.notify_all();gate_cv.wait(lock,[]{return unpark;});}
 }
 counters.record_writer_lock(source,acquire,hold);
}}
namespace before {struct writer_lock {
 word* range_lock=nullptr;u64 acquired_tsc=0,acquire_ticks=0;uint8_t source=1;
 ~writer_lock() noexcept;
};
#include "writer521-before.inc"
}
namespace after {struct writer_lock {
 word* range_lock=nullptr;u64 acquired_tsc=0,acquire_ticks=0;uint8_t source=1;
 ~writer_lock() noexcept;
};
#include "writer521-after.inc"
}
template<class Lock> void parked_probe(bool candidate,bool range,bool other_writer){
 g_range_lock_bits[1].bits=range ? (1ull<<3)|(other_writer?1ull<<4:0) : 1;
 g_range_lock_set[3].bits=1;
 {std::lock_guard lock(gate_mutex);parked=true;entered=false;unpark=false;}
 std::thread producer([=]{Lock owner;owner.range_lock=range?&g_range_lock_set[3]:nullptr;owner.acquired_tsc=utils::get_tsc();});
 {
  std::unique_lock lock(gate_mutex);assert(gate_cv.wait_for(lock,std::chrono::seconds(2),[]{return entered;}));
  const auto bits=g_range_lock_bits[1].bits.load(std::memory_order_acquire);
  const auto expected=range?(other_writer?1ull<<4:0):0;
  assert(candidate ? bits==expected : bits!=expected);
  if(range)assert((g_range_lock_set[3].bits.load()==0)==candidate);
  unpark=true;gate_cv.notify_all();
 }
 producer.join();parked=false;
 assert(g_range_lock_bits[1].bits==(range&&other_writer?1ull<<4:0));
 assert(!range||!g_range_lock_set[3].bits);
}
template<class Lock> double measure(unsigned threads,bool range,unsigned iterations){
 counters.reset();g_range_lock_bits[1].bits=0;
 std::array<u64,64> payload{};
 std::atomic<unsigned> ready{0};std::atomic<bool> go{false};std::vector<std::thread> workers;
 for(unsigned t=0;t<threads;++t)workers.emplace_back([&,t]{
  ++ready;while(!go.load(std::memory_order_acquire))std::this_thread::yield();
  for(unsigned n=0;n<iterations;++n){
   const auto begin=utils::get_tsc();
   if(range){g_range_lock_set[t].bits=1;g_range_lock_bits[1].bits.fetch_or(1ull<<t,std::memory_order_acq_rel);}
   else{u64 zero=0;while(!g_range_lock_bits[1].bits.compare_exchange_weak(zero,1,std::memory_order_acquire)){zero=0;std::this_thread::yield();}}
   Lock lock;lock.range_lock=range?&g_range_lock_set[t]:nullptr;lock.acquired_tsc=utils::get_tsc();lock.acquire_ticks=lock.acquired_tsc-begin;
   ++payload[range?t:0];
  }
 });
 while(ready!=threads)std::this_thread::yield();
 const auto start=std::chrono::steady_clock::now();go.store(true,std::memory_order_release);
 for(auto& worker:workers)worker.join();
 const auto ns=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count();
 assert(counters.m_writer_lock_count[1]==u64(threads)*iterations);
 assert(!g_range_lock_bits[1].bits);
 u64 sum=0;for(auto p:payload)sum+=p;assert(sum==u64(threads)*iterations);
 return ns/(threads*iterations);
}
int main(int argc,char** argv){
 assert(argc==2);
 for(bool range:{false,true})for(bool other:{false,true}){
  parked_probe<before::writer_lock>(false,range,other);parked_probe<after::writer_lock>(true,range,other);
 }
 std::ofstream out(argv[1]);out<<"{\"productionAtomicAdapters\":true,\"parkedProfilerReleasesCellLockOnlyAfterFix\":true,\"physicalIPhoneTested\":false,\"gameplayMeasured\":false,\"samples\":[";
 bool comma=false;
 for(bool range:{false,true})for(unsigned threads:{1u,2u,4u,6u}){
  std::vector<double> a,b;
  for(unsigned round=0;round<12;++round){
   double x,y;
   if(round%2){y=measure<after::writer_lock>(threads,range,50000);x=measure<before::writer_lock>(threads,range,50000);}
   else{x=measure<before::writer_lock>(threads,range,50000);y=measure<after::writer_lock>(threads,range,50000);}
   if(round>=2){a.push_back(x);b.push_back(y);}
  }
  std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
  if(comma)out<<',';comma=true;
  out<<"{\"range\":"<<(range?"true":"false")<<",\"threads\":"<<threads<<",\"beforeMedianNs\":"<<(a[4]+a[5])/2<<",\"afterMedianNs\":"<<(b[4]+b[5])/2
   <<",\"beforeMinNs\":"<<a.front()<<",\"beforeMaxNs\":"<<a.back()<<",\"afterMinNs\":"<<b.front()<<",\"afterMaxNs\":"<<b.back()<<'}';
 }
 out<<"]}\n";out.close();std::cout<<"PASS exact destructor branches, parked profiler, exact counters, concurrent payload integrity; host adapters only\n";
}
