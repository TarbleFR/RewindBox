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
using uint64_t=std::uint64_t;
enum class Heat {cold,hot};
struct Bytes {
    uint64_t size, id; std::vector<uint64_t>* retired;
    uint64_t mapped_size() const { return size; }
    ~Bytes() { retired->push_back(id); }
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
    std::mutex tm;
    struct {uint64_t evicted_logical_bytes=0,prefetch_wasted=0;} stats;
    void add(uint64_t id, uint64_t bits) {
        auto& e=entries[id];e.id=id;e.size=(1+bits%32)*4096;e.stamp=bits%23;
        e.busy=bits&64;e.disk=bits&128;e.prefetched=bits&256;e.heat=(bits&512)?Heat::hot:Heat::cold;
        if(bits&1)e.raw=std::shared_ptr<Bytes>(new Bytes{e.size,id*2,&retired});
        if(bits&2)e.warm=std::shared_ptr<Bytes>(new Bytes{4096*(1+bits%4),id*2+1,&retired});
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

std::uint64_t cases=0,sweeps=0,old_calls=0,new_calls=0;
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
            assert(a.trim_to(limit,except)==b.trim_to(limit,except));
            old_calls+=a.ram_calls;new_calls+=b.ram_calls;assert(b.ram_calls==1);++sweeps;
            same(a,b);assert(a.ram()==b.ram());
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
    random_cases();
    std::cout<<"{\"passed\":true,\"cases\":"<<cases<<",\"sweeps\":"<<sweeps
             <<",\"baselineRamScans\":"<<old_calls<<",\"candidateRamScans\":"<<new_calls<<",\"benchmarks\":[";
    bool first=true;
    if(argc>1)for(unsigned count:{16,128,1024})for(unsigned evict:{0u,1u,count/2,count}) {
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
