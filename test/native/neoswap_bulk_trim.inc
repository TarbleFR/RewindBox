// SPDX-License-Identifier: MIT
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <random>
#include <unordered_map>
#include <vector>
#include <functional>
#include <cstdlib>
#include <new>
#include <atomic>
#include <thread>
using uint64_t=std::uint64_t;
static bool count_allocations=false;
static uint64_t trim_allocations=0;
void* operator new(std::size_t n) { if(count_allocations)++trim_allocations; if(auto p=std::malloc(n?n:1))return p;throw std::bad_alloc(); }
void operator delete(void* p) noexcept {std::free(p);}
void operator delete(void* p,std::size_t) noexcept {std::free(p);}

enum class Heat {cold,hot};
struct Bytes {
    uint64_t size, id; std::vector<uint64_t>* retired; std::function<void(uint64_t)>* hook;
    uint64_t mapped_size() const { return size; }
    ~Bytes() { retired->push_back(id); if(*hook)(*hook)(id); }
};
struct Entry {
    uint64_t id=0,size=0,stamp=0;
    bool busy=false,disk=false,prefetched=false;
    Heat heat=Heat::cold;
    std::shared_ptr<Bytes> raw,warm;
};
struct Base {
    // Destruction events are compared, including raw/warm order.
    std::vector<uint64_t> retired;
    std::unordered_map<uint64_t,Entry> entries;
    std::vector<std::shared_ptr<Bytes>> pins;
    uint64_t loading=0;
    mutable uint64_t ram_calls=0;
    uint64_t selection_visits=0,priority_visits=0;
    std::function<void(uint64_t)> hook;
    std::vector<std::pair<Entry*,size_t>> trim_candidates;
    Base(){retired.reserve(8192);trim_candidates.reserve(4096);}
    ~Base(){hook={};pins.clear();entries.clear();}

    std::mutex tm;
    struct {uint64_t evicted_logical_bytes=0,prefetch_wasted=0;} stats;
    void add(uint64_t id, uint64_t bits) {
        auto& e=entries[id];e.id=id;e.size=(1+bits%32)*4096;e.stamp=bits%23;
        e.busy=bits&64;e.disk=bits&128;e.prefetched=bits&256;e.heat=(bits&512)?Heat::hot:Heat::cold;
        if(bits&1)e.raw=std::shared_ptr<Bytes>(new Bytes{e.size,id*2,&retired,&hook});
        if(bits&2)e.warm=std::shared_ptr<Bytes>(new Bytes{4096*(1+bits%4),id*2+1,&retired,&hook});
        if((bits&1024)&&e.raw)pins.push_back(e.raw);
    }
};
@PRODUCTION@

void same(const before::Impl& a,const after::Impl& b) {
    assert(a.retired==b.retired && a.entries.size()==b.entries.size());
    assert(a.stats.evicted_logical_bytes==b.stats.evicted_logical_bytes && a.stats.prefetch_wasted==b.stats.prefetch_wasted);
    for(const auto& [id,x]:a.entries) {
        const auto& y=b.entries.at(id);
        assert(bool(x.raw)==bool(y.raw) && bool(x.warm)==bool(y.warm));
        assert(x.prefetched==y.prefetched && x.raw.use_count()==y.raw.use_count());
    }
}

std::uint64_t cases=0,sweeps=0,old_calls=0,new_calls=0,old_visits=0,new_visits=0,dynamic_cases=0;
template<class Impl> std::vector<uint64_t> dynamic_case(unsigned release_at,bool concurrent){
    Impl a;
    for(unsigned i=1;i<=64;++i){a.add(i,129);a.entries.at(i).stamp=i;}
    a.pins.push_back(a.entries.at(1).raw);
    std::atomic<bool> ready=false,released=false;
    std::thread worker;
    if(concurrent)worker=std::thread([&]{while(!ready.load())std::this_thread::yield();a.pins[0].reset();released.store(true);});
    unsigned retired=0;
    a.hook=[&](uint64_t){if(++retired==release_at){if(concurrent){ready.store(true);while(!released.load())std::this_thread::yield();}else a.pins[0].reset();}};
    assert(a.trim_to(0));
    if(worker.joinable())worker.join();
    assert(a.retired.size()==64&&a.retired[release_at]==2);
    return a.retired;
}
void unpin_cases(){
    for(unsigned n:{1u,4u,5u,6u,8u,20u,40u,63u})for(bool concurrent:{false,true}){
        assert(dynamic_case<before::Impl>(n,concurrent)==dynamic_case<after::Impl>(n,concurrent));++dynamic_cases;
    }
}

void random_cases() {
    std::mt19937_64 rng(0xb914376);
    for(unsigned k=0;k<2400;++k) {
        before::Impl a;after::Impl b;
        const auto count=rng()%384;
        for(uint64_t i=1;i<=count;++i){auto bits=rng();a.add(i,bits);b.add(i,bits);}
        a.loading=b.loading=(rng()%8)*4096;
        for(unsigned stage=0;stage<5;++stage) {
            auto limit=stage==4?0:rng()%(count*16384+1),except=rng()%(count+1);
            a.ram_calls=0;b.ram_calls=0;
            count_allocations=true;const bool old=a.trim_to(limit,except),current=b.trim_to(limit,except);count_allocations=false;assert(old==current);assert(trim_allocations==0);
            old_calls+=a.ram_calls;new_calls+=b.ram_calls;assert(b.ram_calls==1);++sweeps;
            same(a,b);assert(a.ram()==b.ram());old_visits+=a.selection_visits+a.priority_visits;new_visits+=b.selection_visits+b.priority_visits;a.selection_visits=a.priority_visits=b.selection_visits=b.priority_visits=0;
            if(stage==1){a.pins.clear();b.pins.clear();}
            if(stage==2)for(auto& [id,e]:a.entries){e.busy=false;b.entries.at(id).busy=false;}
        }
        ++cases;
    }
}

template<class Impl> double bench(unsigned count,unsigned evict) {
    std::vector<std::unique_ptr<Impl>> states;
    const unsigned rounds=count>512?8:64;
    for(unsigned r=0;r<rounds;++r) {
        auto p=std::make_unique<Impl>();p->retired.reserve(count*2);
        for(unsigned i=1;i<=count;++i){p->add(i,129);p->entries.at(i).stamp=i;}
        states.push_back(std::move(p));
    }
    const auto start=std::chrono::steady_clock::now();
    for(auto& p:states)assert(p->trim_to(uint64_t(count-evict)*8192));
    return std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/rounds;
}

int main(int argc,char**) {
    random_cases();unpin_cases();
    std::cout<<"{\"passed\":true,\"cases\":"<<cases<<",\"sweeps\":"<<sweeps
             <<",\"baselineRamScans\":"<<old_calls<<",\"candidateRamScans\":"<<new_calls<<",\"baselineSelectionVisits\":"<<old_visits<<",\"candidateSelectionVisits\":"<<new_visits<<",\"dynamicUnpinCases\":"<<dynamic_cases<<",\"trimAllocations\":"<<trim_allocations<<",\"benchmarks\":[";
    bool first=true;
    if(argc>1)for(unsigned count:{16,128,1024,4096})for(unsigned evict:{0u,1u,4u,8u,count/2,count}) {
        std::vector<double> old,newer;
        for(unsigned i=0;i<7;++i) {
            if(i%2){newer.push_back(bench<after::Impl>(count,evict));old.push_back(bench<before::Impl>(count,evict));}
            else {old.push_back(bench<before::Impl>(count,evict));newer.push_back(bench<after::Impl>(count,evict));}
        }
        auto x=old,y=newer;std::sort(x.begin(),x.end());std::sort(y.begin(),y.end());
        if(!first)std::cout<<',';first=false;
        std::cout<<"{\"entries\":"<<count<<",\"evictions\":"<<evict<<",\"baselineMedianNs\":"<<x[3]
                 <<",\"candidateMedianNs\":"<<y[3]<<",\"baselineSamplesNs\":[";
        for(unsigned i=0;i<7;++i){if(i)std::cout<<',';std::cout<<old[i];}
        std::cout<<"],\"candidateSamplesNs\":[";
        for(unsigned i=0;i<7;++i){if(i)std::cout<<',';std::cout<<newer[i];}
        std::cout<<"]}";
    }
    std::cout<<"]}\n";
}
