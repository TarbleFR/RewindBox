#!/usr/bin/env python3
"""Exercise the production vertex-cache block against uncached production copies.

Extracts calculate_required_range, the complete weak_vertex_cache, the complete
single/persistent upload cache block and the persistent-copy loop. GPU buffers,
VM address translation and draw metadata are host adapters; no GPU is executed.
"""
from pathlib import Path
import argparse, hashlib, json, os, platform, shlex, subprocess

HERE = Path(__file__).resolve().parent
REL = Path('rpcs3/Emu/RSX/VK/VKVertexBuffers.cpp')

def block(text, marker):
    start = text.index(marker)
    pos = text.index('{', start)
    depth = 0
    for end in range(pos, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start:end + 1]
    raise ValueError(marker)

PRELUDE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>
using u8=std::uint8_t; using u16=std::uint16_t; using u32=std::uint32_t;
using u64=std::uint64_t; using uptr=std::uintptr_t; using usz=std::size_t;
constexpr u32 umax=~0u;
__CAUSALITY_HELPER__
#define FORCE_INLINE inline
#define ensure(x) assert(x)
template<class T> using be_t=T;
template<class T> T read_from_ptr_unsafe(const std::byte* p,usz at) { T r; std::memcpy(&r,p+at,sizeof(r)); return r; }
alignas(64) std::array<std::byte,1<<20> guest;
u64 reads=0,copied=0,copies=0;
namespace utils {
template<class T> T add_saturate(T a,T b) {return a>std::numeric_limits<T>::max()-b?std::numeric_limits<T>::max():a+b;}
template<class T,class U> T* bless(U* p) {return reinterpret_cast<T*>(p);}
}
namespace vm {
template<class T> T* get_super_ptr(u32 at) {++reads;if(at>=guest.size())throw std::out_of_range("guest address");return reinterpret_cast<T*>(guest.data()+at);}
template<class T> T* _ptr(u32 at) {return get_super_ptr<T>(at);}
}
constexpr u32 CELL_GCM_LOCATION_LOCAL=1;
u32 get_location(u32) {return 0;}
namespace rsx {
template<class A,class B> using unordered_map=std::unordered_map<A,B>;
namespace constants {constexpr u32 local_mem_base=0xc0000000;}
namespace limits {constexpr u32 vertex_count=16;}
enum class draw_command {array,indexed,inlined_array};
enum class index_array_type {u16,u32};
struct draw_clause {draw_command command=draw_command::array;bool is_immediate_draw=false;};
struct regs_t {
    draw_clause current_draw_clause;
    rsx::index_array_type index_type() const{return rsx::index_array_type::u32;}
    bool restart_index_enabled() const{return false;}
    u32 restart_index() const{return ~0u;}
    u32 index_array_address() const{return 0;}
    u32 index_array_location() const{return 0;}
    u32 transform_program_start() const{return 19;}
} method_registers;
u32 get_address(u32 at,u32) {return at;}
struct processor_t {std::vector<u32> indices;const auto& element_push_buffer() const{return indices;}};
struct renderer_t {u32 local_mem_size=1<<20;processor_t processor;processor_t* draw_processor(){return &processor;}} renderer;
renderer_t* get_current_renderer(){return &renderer;}
struct interleaved_attribute_t {u8 index;bool modulo;u16 frequency;};
struct interleaved_range_info {
    bool interleaved=true,single_vertex=false;
    u32 base_offset=0,real_offset_address=0;u8 memory_location=0,attribute_stride=16;
    std::pair<u32,u32> vertex_range{};
    std::vector<interleaved_attribute_t> locations;
    std::pair<u32,u32> calculate_required_range(u32 first,u32 count);
__GET_REQUIRED_RANGE__
};
struct vertex_input_layout {
    std::vector<interleaved_range_info*> interleaved_blocks;
    u32 calculate_interleaved_memory_requirements(u32 first,u32 count) const {
        u32 total=0;for(auto* b:interleaved_blocks)total+=b->calculate_required_range(first,count).second*b->attribute_stride;
        return total;
    }
};
struct dma_manager {void copy(void* dst,const void* src,u32 n){std::memcpy(dst,src,n);copied+=n;++copies;}};
}
struct fxo_t {rsx::dma_manager dma;template<class T> T& get(){return dma;}} fxo;
fxo_t* g_fxo=&fxo;
__RANGE_METHOD__
namespace rsx {
__VERTEX_CACHE__
}
struct heap_t {
    std::vector<std::byte> bytes=std::vector<std::byte>(1<<20);
    u32 next=0;
    template<u32 alignment> u32 alloc(u32 n){next=(next+alignment-1)&~(alignment-1);u32 off=next;next+=n;assert(next<bytes.size());return off;}
};
struct upload_t {
    rsx::vertex_input_layout m_vertex_layout;
    rsx::vertex_cache::weak_vertex_cache cache;
    rsx::vertex_cache::default_vertex_cache<rsx::vertex_cache::uploaded_range>* m_vertex_cache=&cache;
    heap_t m_attrib_ring_info;
    struct {u32 vertex_cache_request_count=0,vertex_cache_miss_count=0,draw_calls=17;} m_frame_stats;
    u64 int_flip_index=23;
    struct {u32 offset=0x20000;}current_fragment_program;
    u32 upload(u32 vertex_base,u32 vertex_count) {
        auto required=std::pair{m_vertex_layout.calculate_interleaved_memory_requirements(vertex_base,vertex_count),0u};
        u32 persistent_range_base=-1;
        usz persistent_offset=static_cast<u32>(-1);
__CACHE_BLOCK__
        if(persistent_offset!=umax)copy(m_attrib_ring_info.bytes.data()+persistent_offset,vertex_base,vertex_count);
        return persistent_range_base;
    }
    void copy(void* persistent_data,u32 first_vertex,u32 vertex_count) const {
        char* persistent=static_cast<char*>(persistent_data);
        const auto& layout=m_vertex_layout;
__COPY_LOOP__
    }
    bool agrees_with_uncached(u32 first,u32 count) {
        namespace cause=rpcs3::ios::renderer_causality;
        cause::profile.reset(101);
        u32 off=upload(first,count);
        u32 len=m_vertex_layout.calculate_interleaved_memory_requirements(first,count);
        std::vector<std::byte> expected(len);
        copy(expected.data(),first,count);
        const auto observation=cause::profile.take();
#ifdef CANDIDATE
        const auto* b=m_vertex_layout.interleaved_blocks[0];
        const auto source_first=b->vertex_range.first;
        assert((observation.size!=0)==(first!=source_first));
        if(observation.size){
            assert(observation.size==1&&observation.dropped==0);
            const auto& event=observation.events[0];
            assert(event.kind==cause::Kind::vertex_range&&event.reasons==cause::source_range);
            assert(event.frame==23&&event.draw==17&&event.session==101&&event.vertex);
            assert(event.fragment_offset==0x20000&&event.vertex_start==19);
            assert(event.legacy_address==b->real_offset_address+first*b->attribute_stride);
            assert(event.actual_address==b->real_offset_address+source_first*b->attribute_stride);
            assert(event.bytes==len&&event.count==count&&event.stride==b->attribute_stride);
        }
#else
        assert(observation.size==0);
#endif
        return std::memcmp(expected.data(),m_attrib_ring_info.bytes.data()+off,len)==0;
    }
};
'''

MAIN = r'''
int main() {
    for(usz i=0;i<guest.size();++i)guest[i]=std::byte((i*37+(i/16)*13)%251);
    u64 cases=0,mismatches=0,ordinary_mismatches=0,reuse_uploads=0;
    for(u32 stride:{8u,16u,32u,64u})
    for(u32 first:{8u,16u,32u,64u})
    for(u32 freq:{2u,4u,8u})
    for(u32 kind=0;kind<3;++kind)
    for(u32 reverse=0;reverse<2;++reverse) {
        upload_t r;
        rsx::interleaved_range_info ordinary,frequency;
        ordinary.real_offset_address=4096;ordinary.attribute_stride=stride;
        ordinary.locations.push_back({0,false,1});
        frequency=ordinary;frequency.single_vertex=(kind==0);
        frequency.locations[0]={0,kind==2,static_cast<u16>(freq)};
        const u32 n=kind==2?freq:1;
        const u32 frequency_n=kind==0?freq:kind==1?freq:n;
        r.m_vertex_layout.interleaved_blocks={reverse?&frequency:&ordinary};
        bool first_ok=r.agrees_with_uncached(first,reverse?frequency_n:n);++cases;assert(first_ok);
        r.m_vertex_layout.interleaved_blocks={reverse?&ordinary:&frequency};
        bool second_ok=r.agrees_with_uncached(first,reverse?n:frequency_n);++cases;mismatches+=!second_ok;
    }
    // The fingerprint must examine the range that was copied, not a distant draw index.
    for(u32 stride:{8u,16u,32u,64u})for(u32 freq:{2u,4u,8u}) {
        upload_t r;rsx::interleaved_range_info b;b.real_offset_address=8192;b.attribute_stride=stride;
        b.locations.push_back({0,false,static_cast<u16>(freq)});
        r.m_vertex_layout.interleaved_blocks={&b};
        assert(r.agrees_with_uncached(32,freq));++cases;
        const auto at=b.real_offset_address+b.get_required_range(32,freq).first*stride;
        guest[at]^=std::byte{127};
        bool ok=r.agrees_with_uncached(32,freq);++cases;mismatches+=!ok;
        guest[at]^=std::byte{127};
    }
    // Different draw indices that use the exact same source range should share it.
    for(u32 kind=0;kind<2;++kind)for(u32 stride:{8u,16u,32u,64u}) {
        upload_t r;rsx::interleaved_range_info b;b.real_offset_address=12288;b.attribute_stride=stride;
        b.single_vertex=(kind==0);b.locations.push_back({0,false,4});r.m_vertex_layout.interleaved_blocks={&b};
        for(u32 first=32;first<36;++first){b.vertex_range={};assert(r.agrees_with_uncached(first,1));++cases;}
        reuse_uploads+=r.m_frame_stats.vertex_cache_miss_count;
    }
    // Unmodified ordinary arrays retain the same hits, and first-byte writes miss.
    for(u32 stride:{8u,16u,32u,64u})for(u32 first=0;first<64;++first) {
        upload_t r;rsx::interleaved_range_info b;b.real_offset_address=16384;b.attribute_stride=stride;b.locations.push_back({0,false,1});
        r.m_vertex_layout.interleaved_blocks={&b};
        for(u32 pass=0;pass<3;++pass){ordinary_mismatches+=!r.agrees_with_uncached(first,8);++cases;}
        assert(r.m_frame_stats.vertex_cache_miss_count==1);
        guest[b.real_offset_address+first*stride]^=std::byte{91};
        ordinary_mismatches+=!r.agrees_with_uncached(first,8);++cases;assert(r.m_frame_stats.vertex_cache_miss_count==2);
        guest[b.real_offset_address+first*stride]^=std::byte{91};
    }
    assert(ordinary_mismatches==0);
#ifdef CANDIDATE
    assert(mismatches==0);assert(reuse_uploads==8);
#else
    assert(mismatches>0);assert(reuse_uploads==32);
#endif
    std::cout<<"{\"cases\":"<<cases<<",\"wrong_range_reuses\":"<<mismatches
      <<",\"ordinary_mismatches\":"<<ordinary_mismatches<<",\"equivalent_range_uploads\":"<<reuse_uploads
      <<",\"weak_first_eight_byte_validation_unchanged\":true}"<<std::endl;
}
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--sanitizer',action='store_true')
    ap.add_argument('--compiler',default=os.environ.get('CXX','g++'),help='C++ command; defaults to CXX')
    args=ap.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    source=args.source.resolve()
    text=(source/'rpcs3/Emu/RSX/RSXThread.cpp').read_text()
    range_method=block(text,'std::pair<u32, u32> interleaved_range_info::calculate_required_range')
    range_method=range_method.replace('interleaved_range_info::','rsx::interleaved_range_info::',1)
    cachetext=(source/'rpcs3/Emu/RSX/rsx_cache.h').read_text()
    cache=block(cachetext,'namespace vertex_cache')
    header=(source/'rpcs3/Emu/RSX/Core/RSXVertexTypes.h').read_text()
    getter=block(header,'std::pair<u32, u32> get_required_range')
    copytext=(source/'rpcs3/Emu/RSX/Core/RSXDrawCommands.cpp').read_text()
    start=copytext.index('void draw_command_processor::write_vertex_data_to_memory')
    copy_loop=block(copytext[start:],'for (interleaved_range_info* block : layout.interleaved_blocks)')
    copy_loop=copy_loop.replace('interleaved_range_info*','rsx::interleaved_range_info*',1)
    causality_path=source/'rpcs3/ios/IOSRendererCausality.h';causality=causality_path.read_text().replace('#pragma once','')
    report={'scope':'production vertex upload cache range vs uncached production copy; host VM/DMA/heap adapters; no GPU',
      'inputs':{},'sanitizer':args.sanitizer,'variants':{}}
    for rel in [REL,Path('rpcs3/ios/IOSRendererCausality.h'),Path('rpcs3/Emu/RSX/RSXThread.cpp'),Path('rpcs3/Emu/RSX/rsx_cache.h'),Path('rpcs3/Emu/RSX/Core/RSXVertexTypes.h'),Path('rpcs3/Emu/RSX/Core/RSXDrawCommands.cpp')]:
        report['inputs'][str(rel)]=hashlib.sha256((source/rel).read_bytes()).hexdigest()
    for name,vertex in [('before',(HERE/'fixtures/VKVertexBuffers.before.cpp').read_text()),('after',(source/REL).read_text())]:
        cache_block=block(vertex[vertex.index('VKGSRender::upload_vertex_data'):],'if (required.first > 0)')
        cpp=PRELUDE.replace('__CAUSALITY_HELPER__',causality).replace('__GET_REQUIRED_RANGE__',getter).replace('__RANGE_METHOD__',range_method).replace('__VERTEX_CACHE__',cache).replace('__CACHE_BLOCK__',cache_block).replace('__COPY_LOOP__',copy_loop)+MAIN
        path=args.output/(name+'.cpp');path.write_text(cpp)
        binary=args.output/name
        cmd=shlex.split(args.compiler)+['-std=c++20','-O2','-g','-UNDEBUG','-Wall','-Wextra','-Werror','-DRPCS3_IOS',str(path),'-o',str(binary)]
        if platform.system()=='Darwin' and os.environ.get('HOST_MACOS_SDK'):
            cmd+=['-isysroot',os.environ['HOST_MACOS_SDK']]
        if name=='after':cmd+=['-DCANDIDATE']
        if args.sanitizer:
            cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all']
            if platform.system()=='Linux':cmd+=['-no-pie']
        build=subprocess.run(cmd,text=True,capture_output=True);(args.output/(name+'-build.log')).write_text(build.stdout+build.stderr);build.check_returncode()
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
        run=subprocess.run([str(binary)],text=True,capture_output=True,env=env,timeout=45)
        (args.output/(name+'-run.log')).write_text(run.stdout+run.stderr);run.check_returncode()
        report['variants'][name]={'result':json.loads(run.stdout),'generated_sha256':hashlib.sha256(cpp.encode()).hexdigest(),'command':cmd,'returncode':run.returncode}
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['variants'],indent=2))

if __name__=='__main__':main()
