#include <algorithm>
#include <array>
#include <atomic>
#include <barrier>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <limits>
#include <thread>
#include <vector>
#include "before.h"
#include "after.h"

template<class C> using Totals=std::array<typename C::Total,C::sources>;
template<class C> void merge(Totals<C>& a,const Totals<C>& b) {
 for(unsigned i=0;i<C::sources;++i) {
  a[i].count+=b[i].count;a[i].acquire+=b[i].acquire;a[i].hold+=b[i].hold;
  a[i].maximum=std::max(a[i].maximum,b[i].maximum);
 }
}
template<class C> void accuracy() {
 C counters,other;
 constexpr unsigned threads=96,n=4096;
 std::barrier start(threads+1);
 std::vector<std::thread> workers;
 std::atomic<bool> done=false;
 Totals<C> from1{},from2{},all{},expected{};
 // Two concurrent readers exercise cursor serialization as well as updates.
 std::thread r1([&]{while(!done.load()) {merge<C>(from1,counters.drain());std::this_thread::yield();}});
 std::thread r2([&]{while(!done.load()) {merge<C>(from2,counters.drain());std::this_thread::yield();}});
 for(unsigned t=0;t<threads;++t) {
  auto& e=expected[t%C::sources];e.count+=n+1;e.acquire+=5+n*13/2;e.hold+=7+n*5/2;e.maximum=7;
  workers.emplace_back([&,t] {
   // Keep all leases live before starting; more than63 writers exercise overflow.
   counters.record(t%C::sources,5,7);start.arrive_and_wait();
   for(unsigned i=0;i<n;++i) {
    counters.record(t%C::sources,3+(i&7),1+(i&3));
    if((i&127)==0)other.record(t%C::sources,0,0);
   }
  });
 }
 start.arrive_and_wait();for(auto& w:workers)w.join();done=true;r1.join();r2.join();
 merge<C>(all,from1);merge<C>(all,from2);merge<C>(all,counters.drain());
 for(unsigned i=0;i<C::sources;++i) {
  assert(all[i].count==expected[i].count && all[i].acquire==expected[i].acquire && all[i].hold==expected[i].hold);
  assert(all[i].maximum==7);
 }
 uint64_t count=0;for(auto s:other.drain())count+=s.count;assert(count==threads*(n/128));
 for(auto s:counters.drain())assert(!s.count&&!s.acquire&&!s.hold&&!s.maximum);
 // Retired slots can be reused without resetting cumulative totals or leaking
 // an ownership pointer into a destroyed counter object.
 for(unsigned wave=0;wave<128;++wave) {
  std::thread([&]{counters.record(99,11,13);}).join();
  auto value=counters.drain();assert(value[0].count==1&&value[0].acquire==11&&value[0].hold==13&&value[0].maximum==13);
 }
 counters.record(1,std::numeric_limits<uint64_t>::max(),std::numeric_limits<uint64_t>::max());
 auto wrap1=counters.drain();assert(wrap1[1].count==1 && wrap1[1].acquire==std::numeric_limits<uint64_t>::max());
 counters.record(1,9,10);auto wrap2=counters.drain();assert(wrap2[1].count==1&&wrap2[1].acquire==9&&wrap2[1].hold==10);
 for(int i=0;i<16;++i){C fresh;fresh.record(1,2,3);auto v=fresh.drain();assert(v[1].count==1&&v[1].acquire==2&&v[1].hold==3);}
}

// Construct this TLS cleanup before the first record, so it runs after the
// profiler lease has retired. A new writer claims a free slot concurrently.
template<class C> void late_tls_cleanup() {
 C counters;std::atomic<bool> retired=false,go=false;
 constexpr unsigned n=100000;
 struct Cleanup {
  C* counters;std::atomic<bool>* retired;std::atomic<bool>* go;
  ~Cleanup(){retired->store(true);while(!go->load())std::this_thread::yield();for(unsigned i=0;i<n;++i)counters->record(1,3,2);}
 };
 std::thread first([&]{thread_local Cleanup cleanup{&counters,&retired,&go};counters.record(1,3,2);});
 while(!retired.load())std::this_thread::yield();
 std::thread second([&]{counters.record(1,3,2);go=true;for(unsigned i=0;i<n;++i)counters.record(1,3,2);});
 first.join();second.join();auto result=counters.drain();
 assert(result[1].count==2*(n+1)&&result[1].acquire==6*(n+1)&&result[1].hold==4*(n+1));
}

template<class C> double bench(unsigned threads) {
 C counters;std::barrier start(threads+1);std::vector<std::thread> workers;
 constexpr unsigned iterations=250000;
 for(unsigned t=0;t<threads;++t)workers.emplace_back([&,t] {
  counters.record(t%5,3,2);start.arrive_and_wait();
  for(unsigned i=0;i<iterations;++i)counters.record(t%5,3+(i&7),1+(i&3));
 });
 auto begin=std::chrono::steady_clock::now();start.arrive_and_wait();for(auto& w:workers)w.join();
 auto elapsed=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
 uint64_t count=0;for(auto s:counters.drain())count+=s.count;assert(count==uint64_t{threads}*(iterations+1));
 return elapsed;
}
int main() {
 using Before=before::WriterCounters;using After=after::WriterCounters;
 accuracy<Before>();accuracy<After>();late_tls_cleanup<Before>();late_tls_cleanup<After>();
 std::cout<<"{\"accuracy\":true,\"writers\":96,\"concurrentReaders\":2,\"retirementWaves\":128,\"bytesBefore\":"<<sizeof(Before)<<",\"bytesAfter\":"<<sizeof(After)<<",\"benchmarks\":[";
 for(unsigned threads:{1u,8u}) {
  std::array<double,5> a{},b{};
  for(unsigned i=0;i<5;++i){if(i&1){b[i]=bench<After>(threads);a[i]=bench<Before>(threads);}else{a[i]=bench<Before>(threads);b[i]=bench<After>(threads);}}
  std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
  if(threads!=1)std::cout<<',';
  std::cout<<"{\"threads\":"<<threads<<",\"eventsPerThread\":250000,\"trials\":5,\"beforeMedianMs\":"<<a[2]<<",\"afterMedianMs\":"<<b[2]<<'}';
 }
 std::cout<<"]}\n";
}
