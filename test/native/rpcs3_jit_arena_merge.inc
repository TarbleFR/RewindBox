#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <random>
#include <string>

using old_arena = version0::arena_allocator;
using new_arena = version1::arena_allocator;
struct item { std::size_t offset, size; };
static std::uint64_t operations=0, purge_checks=0, model_checks=0, boundary_checks=0;

template <class A, class B> void same_range(A a, B b)
{
    assert(a.offset == b.offset && a.size == b.size);
}

void randomized()
{
    for (unsigned seed=1; seed<=8; ++seed)
    {
        std::mt19937_64 rng(seed * 0x7a83e012ULL);
        const std::size_t capacity=4096;
        old_arena a(capacity); new_arena b(capacity);
        std::vector<item> live;
        std::vector<bool> occupied(capacity);
        for (unsigned step=0; step<30000; ++step)
        {
            ++operations;
            if (!live.empty() && rng()%3 == 0)
            {
                const auto index=rng()%live.size(); const auto span=live[index];
                assert(a.release(span.offset,span.size)); assert(b.release(span.offset,span.size));
                for(auto i=span.offset;i<span.offset+span.size;++i) { assert(occupied[i]); occupied[i]=false; }
                live.erase(live.begin()+index);
            }
            else
            {
                const auto size=1+rng()%128, alignment=std::size_t{1} << (rng()%8);
                version0::arena_range x{77,88}; version1::arena_range y{77,88};
                const bool high=rng()&1;
                const bool ok=high?a.allocate_highest(size,alignment,x):a.allocate_lowest(size,alignment,x);
                assert(ok == (high?b.allocate_highest(size,alignment,y):b.allocate_lowest(size,alignment,y)));
                same_range(x,y);
                if(ok) {
                    assert(x.offset%alignment==0 && x.size==size);
                    for(auto i=x.offset;i<x.offset+x.size;++i) { assert(i<capacity && !occupied[i]); occupied[i]=true; }
                    live.push_back({x.offset,x.size});
                }
            }
            assert(a.free_bytes()==b.free_bytes());
            assert(a.largest_free_bytes()==b.largest_free_bytes());
            for(unsigned n=0;n<3;++n)
            {
                const auto offset=rng()%(capacity+32), size=rng()%512, page=std::size_t{1}<<(rng()%9);
                const auto x=a.released_data_pages(offset,size,page);
                const auto y=b.released_data_pages(offset,size,page);
                same_range(x,y); ++purge_checks;
                if(y.size) {
                    assert(y.offset%page==0 && y.size%page==0 && y.offset+y.size<=capacity);
                    for(auto i=y.offset;i<y.offset+y.size;++i) assert(!occupied[i]);
                }
            }
            if(step%32==0) {
                std::size_t free=0, longest=0, run=0;
                for(bool busy:occupied) { free+=!busy;run=busy?0:run+1;longest=std::max(run,longest); }
                assert(a.free_bytes()==free && a.largest_free_bytes()==longest); ++model_checks;
            }
        }
        for(auto span:live) { assert(a.release(span.offset,span.size)); assert(b.release(span.offset,span.size)); }
        assert(a.free_bytes()==capacity && b.largest_free_bytes()==capacity);
    }
}

void boundaries()
{
    const std::size_t max=std::numeric_limits<std::size_t>::max();
    const std::size_t values[]={0,1,2,3,16,4096,max/2,max-1,max};
    for(auto capacity:values) for(auto size:values) for(auto offset:values) for(auto page:values)
    {
        old_arena a(capacity); new_arena b(capacity);
        same_range(a.released_data_pages(offset,size,page),b.released_data_pages(offset,size,page));
        assert(a.release(offset,size)==b.release(offset,size));
        version0::arena_range x{1,2}; version1::arena_range y{1,2};
        assert(a.allocate_highest(size,page,x)==b.allocate_highest(size,page,y)); same_range(x,y);
        same_range(a.released_data_pages(offset,size,page),b.released_data_pages(offset,size,page));
        assert(a.free_bytes()==b.free_bytes() && a.largest_free_bytes()==b.largest_free_bytes());
        ++boundary_checks;
    }
}

std::pair<std::size_t,std::size_t> adjacent_allocations()
{
    old_arena a(4096); new_arena b(4096);
    version0::arena_range x; version1::arena_range y;
    assert(a.allocate_lowest(2048,1,x)); assert(b.allocate_lowest(2048,1,y));
    counts<0>::allocations=0;counts<1>::allocations=0;
    assert(a.release(x.offset,x.size)); assert(b.release(y.offset,y.size));
    assert(counts<0>::allocations==1 && counts<1>::allocations==0);
    return {counts<0>::allocations,counts<1>::allocations};
}

void failure_semantics()
{
    old_arena a(4096);new_arena b(4096);
    version0::arena_range x;version1::arena_range y;
    assert(a.allocate_highest(2048,1,x));assert(b.allocate_highest(2048,1,y));
    counts<0>::fail=true;counts<1>::fail=true;
    bool threw=false;try { a.release(x.offset,x.size); } catch(const std::bad_alloc&) { threw=true; }
    assert(threw && a.free_bytes()==2048 && a.largest_free_bytes()==2048);
    assert(b.release(y.offset,y.size));assert(b.free_bytes()==4096);
    counts<0>::fail=false;counts<1>::fail=false;
    assert(a.release(x.offset,x.size));assert(a.free_bytes()==4096);

    // A genuinely separate interval still allocates; failure remains atomic.
    old_arena c(4096);new_arena d(4096);
    assert(c.allocate_lowest(3072,1,x));assert(d.allocate_lowest(3072,1,y));
    counts<0>::fail=true;counts<1>::fail=true;
    bool old_throw=false,new_throw=false;
    try { c.release(0,1024); } catch(const std::bad_alloc&) { old_throw=true; }
    try { d.release(0,1024); } catch(const std::bad_alloc&) { new_throw=true; }
    assert(old_throw && new_throw && c.free_bytes()==1024 && d.free_bytes()==1024);
    counts<0>::fail=false;counts<1>::fail=false;
}

template <class Arena> Arena fragmented(std::size_t count)
{
    Arena a(count*8192);
    for(std::size_t i=0;i<count;++i) {
        typename std::conditional_t<std::is_same_v<Arena,old_arena>,version0::arena_range,version1::arena_range> span;
        assert(a.allocate_lowest(8192,1,span));
    }
    for(std::size_t i=0;i<count;i+=2) assert(a.release(i*8192,8192));
    return a;
}

static volatile std::uint64_t sink=0;
template <class Arena> double bench(std::size_t count,bool purge)
{
    const unsigned loops=purge?100000:64;
    std::vector<Arena> arenas;arenas.reserve(purge?1:loops);
    for(unsigned i=0;i<(purge?1:loops);++i)arenas.push_back(fragmented<Arena>(count));
    const auto start=std::chrono::steady_clock::now();
    std::uint64_t sum=0;
    if(purge) {
        for(unsigned i=0;i<loops;++i) {
            const auto r=arenas[0].released_data_pages(((i*37ULL)%(count/2))*16384,8192,4096);
            sum+=r.size+r.offset;
        }
    } else {
        for(auto& a:arenas) for(std::size_t i=1;i<count;i+=2) sum+=a.release(i*8192,8192);
    }
    const auto elapsed=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count();
    sink=sum;return elapsed/(purge?loops:loops*(count/2));
}

int main(int argc,char**)
{
    randomized();boundaries();auto allocations=adjacent_allocations();failure_semantics();
    std::cout << "{\"passed\":true,\"randomOperations\":" << operations << ",\"purgeChecks\":" << purge_checks
              << ",\"occupancyModelChecks\":" << model_checks << ",\"boundaryCases\":" << boundary_checks
              << ",\"baselineAdjacentReleaseAllocations\":" << allocations.first
              << ",\"candidateAdjacentReleaseAllocations\":" << allocations.second
              << ",\"allocationFailureCases\":2,\"benchmarks\":[";
    bool first=true;
    if(argc>1) for(auto count:{2,16,128,1024}) for(bool purge:{false,true}) {
        std::vector<double> old,newer;
        for(unsigned i=0;i<7;++i) {
            if(i%2) {newer.push_back(bench<new_arena>(count,purge));old.push_back(bench<old_arena>(count,purge));}
            else {old.push_back(bench<old_arena>(count,purge));newer.push_back(bench<new_arena>(count,purge));}
        }
        auto x=old,y=newer;std::sort(x.begin(),x.end());std::sort(y.begin(),y.end());
        if(!first)std::cout<<',';
        first=false;
        std::cout<<"{\"fragmentSlots\":"<<count<<",\"operation\":\""<<(purge?"purge_lookup":"adjacent_release")
                 <<"\",\"baselineMedianNs\":"<<x[3]<<",\"candidateMedianNs\":"<<y[3]<<",\"baselineSamplesNs\":[";
        for(unsigned i=0;i<7;++i){if(i)std::cout<<',';std::cout<<old[i];}
        std::cout<<"],\"candidateSamplesNs\":[";
        for(unsigned i=0;i<7;++i){if(i)std::cout<<',';std::cout<<newer[i];}
        std::cout<<"]}";
    }
    std::cout<<"]}\n";
}
