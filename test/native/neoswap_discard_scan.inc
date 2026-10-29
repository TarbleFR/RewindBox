// SPDX-License-Identifier: MIT
// Exact collect_discarded/discard bodies; metadata-only boundary, no storage I/O.
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <deque>
#include <iostream>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>
using u64=std::uint64_t;
enum class Code {ok,missing};
struct Handle {u64 session,id;};
struct Entry {
    u64 id=0,offset=0,span=0;
    bool discarded=false,busy=false;
    std::shared_ptr<int> raw;
};
struct Job {u64 id;};
struct Wake {u64 count=0;void notify_one(){++count;}};
struct Base {
    u64 session=1;
    std::mutex mu,tm;
    Wake cv;
    struct {u64 discarded_entries=0;} stats;
    std::unordered_map<u64,Entry> entries;
    std::deque<std::unique_ptr<Job>> queue;
    std::unordered_map<u64,std::shared_ptr<int>> pins;
    std::vector<std::pair<u64,u64>> extents;
    void return_extent(u64 offset,u64 span){extents.emplace_back(offset,span);}
    void add(u64 id){
        if(entries.count(id))return;
        entries.emplace(id,Entry{id,id*4096,4096,false,false,std::make_shared<int>(int(id))});
    }
    void pin(u64 id){if(auto i=entries.find(id);i!=entries.end())pins[id]=i->second.raw;}
};
@PRODUCTION@

u64 random_next(u64& x){x^=x<<13;x^=x>>7;x^=x<<17;return x;}
u64 audits=0,operations=0,collects=0,discard_calls=0;
void compare(const before::Store& a,const after::Store& b){
    ++audits;
    assert(a.p_->entries.size()==b.p_->entries.size());
    assert(a.p_->stats.discarded_entries==b.p_->stats.discarded_entries);
    assert(a.p_->extents==b.p_->extents&&a.p_->cv.count==b.p_->cv.count);
    bool retired=false;
    for(const auto& [id,x]:a.p_->entries){
        const auto& y=b.p_->entries.at(id);
        assert(x.id==y.id&&x.offset==y.offset&&x.span==y.span);
        assert(x.busy==y.busy&&x.discarded==y.discarded);
        assert(x.raw.use_count()==y.raw.use_count());
        retired|=y.discarded;
    }
    assert(!retired||b.p_->discarded_pending);
}
void collect(before::Store& a,after::Store& b){
    // These methods execute with Store::Impl::mu held in the real worker.
    std::lock_guard la(a.p_->mu);std::lock_guard lb(b.p_->mu);
    a.p_->collect_discarded();b.p_->collect_discarded();++collects;compare(a,b);
}
void discard(before::Store& a,after::Store& b,Handle h){
    assert(a.discard(h)==b.discard(h));++discard_calls;compare(a,b);
}
void boundaries(){
    before::Store a;after::Store b;
    collect(a,b);discard(a,b,{2,1});discard(a,b,{1,1});
    for(u64 id=1;id<=4;++id){a.p_->add(id);b.p_->add(id);}
    a.p_->pin(1);b.p_->pin(1);
    a.p_->entries.at(2).busy=true;b.p_->entries.at(2).busy=true;
    a.p_->queue.push_back(std::make_unique<Job>(Job{3}));b.p_->queue.push_back(std::make_unique<Job>(Job{3}));
    for(u64 id=1;id<=4;++id)discard(a,b,{1,id});
    discard(a,b,{1,1});collect(a,b);
    assert(a.p_->entries.size()==3&&b.p_->discarded_pending);
    collect(a,b);a.p_->pins.clear();b.p_->pins.clear();collect(a,b);
    assert(a.p_->entries.size()==2);
    a.p_->entries.at(2).busy=false;b.p_->entries.at(2).busy=false;collect(a,b);
    a.p_->queue.clear();b.p_->queue.clear();collect(a,b);
    assert(a.p_->entries.empty()&&!b.p_->discarded_pending);
    for(int i=0;i<100;++i)collect(a,b);
    // Explicit erase can leave a conservative true flag; one pass clears it.
    a.p_->add(7);b.p_->add(7);discard(a,b,{1,7});
    a.p_->entries.erase(7);b.p_->entries.erase(7);collect(a,b);
    assert(!b.p_->discarded_pending);
}
void traces(){
    for(u64 seed=1;seed<=8;++seed){
        before::Store a;after::Store b;u64 random=seed;
        for(unsigned i=0;i<12000;++i){
            ++operations;const u64 id=random_next(random)%128+1;
            switch(random_next(random)%10){
            case 0:case 1:a.p_->add(id);b.p_->add(id);break;
            case 2:discard(a,b,{1,id});break;
            case 3:collect(a,b);break;
            case 4:if(a.p_->entries.count(id)){a.p_->entries.at(id).busy=!a.p_->entries.at(id).busy;b.p_->entries.at(id).busy=!b.p_->entries.at(id).busy;}break;
            case 5:a.p_->pin(id);b.p_->pin(id);break;
            case 6:a.p_->pins.erase(id);b.p_->pins.erase(id);break;
            case 7:if(a.p_->queue.size()<16){a.p_->queue.push_back(std::make_unique<Job>(Job{id}));b.p_->queue.push_back(std::make_unique<Job>(Job{id}));}break;
            case 8:if(!a.p_->queue.empty()){a.p_->queue.pop_front();b.p_->queue.pop_front();}break;
            case 9:discard(a,b,{2,id});break;
            }
            compare(a,b);
        }
        a.p_->pins.clear();b.p_->pins.clear();a.p_->queue.clear();b.p_->queue.clear();
        for(auto& [id,x]:a.p_->entries){x.busy=false;b.p_->entries.at(id).busy=false;}
        collect(a,b);assert(!b.p_->discarded_pending);
    }
}
template<class Impl> [[gnu::noinline]] void step(Impl& impl){impl.collect_discarded();}
template<class Impl> double measure(Impl& impl,unsigned iterations){
    const auto begin=std::chrono::steady_clock::now();
    for(unsigned i=0;i<iterations;++i){
        asm volatile("" : : "g"(&impl) : "memory");step(impl);
    }
    return std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-begin).count()/iterations;
}
void benchmarks(){
    std::cout<<",\"benchmarks\":[";bool first=true;
    for(unsigned n:{0,16,256,1024,4096}){
        before::Store a;after::Store b;
        for(unsigned i=1;i<=n;++i){a.p_->add(i);b.p_->add(i);}
        for(unsigned i=0;i<16;++i){a.p_->queue.push_back(std::make_unique<Job>(Job{n+i+1}));b.p_->queue.push_back(std::make_unique<Job>(Job{n+i+1}));}
        for(bool blocked:{false,true}){
            if(blocked){a.p_->add(n+1);b.p_->add(n+1);a.p_->pin(n+1);b.p_->pin(n+1);discard(a,b,{1,n+1});}
            std::array<double,7> old{},now{};
            const unsigned rounds=n<256?20000:2000;
            for(unsigned i=0;i<7;++i){
                if(i%2){now[i]=measure(*b.p_,rounds);old[i]=measure(*a.p_,rounds);}
                else {old[i]=measure(*a.p_,rounds);now[i]=measure(*b.p_,rounds);}
            }
            std::sort(old.begin(),old.end());std::sort(now.begin(),now.end());
            if(!first)std::cout<<',';first=false;
            std::cout<<"{\"liveEntries\":"<<n<<",\"blockedRetiredEntries\":"<<(blocked?1:0)
                     <<",\"queueSize\":16,\"series\":7,\"iterationsPerSeries\":"<<rounds
                     <<",\"baselineNsPerCollect\":"<<old[3]<<",\"candidateNsPerCollect\":"<<now[3]<<'}';
        }
    }
    std::cout<<']';
}
int main(int argc,char**){
#ifdef NDEBUG
#error Assertions must be active
#endif
    boundaries();traces();
    std::cout<<"{\"passed\":true,\"assertionsActive\":true,\"operations\":"<<operations
             <<",\"audits\":"<<audits<<",\"collectCallsPerVersion\":"<<collects
             <<",\"discardCallsPerVersion\":"<<discard_calls;
    if(argc>1)benchmarks();
    std::cout<<"}\n";
}
