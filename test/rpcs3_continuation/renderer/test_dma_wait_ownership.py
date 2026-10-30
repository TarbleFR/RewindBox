#!/usr/bin/env python3
"""Compare exact DMA wait callers with injected completion results.

One executable contains baseline and candidate namespaces. The production
command-buffer methods and fence destructor are also extracted unchanged.
The driver, scheduler, guest memory and synchronization counters are shims.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

HERE = Path(__file__).resolve().parent
REL = Path('rpcs3/Emu/RSX/VK')

HEADERS = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <source_location>
#include <span>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
using u8=std::uint8_t; using u16=std::uint16_t; using u32=std::uint32_t;
using u64=std::uint64_t; using s32=std::int32_t;
using VkDevice=u32; using VkFence=u32; using VkCommandBuffer=u32;
using VkQueue=u32; using VkBool32=u32;
constexpr auto VK_NULL_HANDLE=0u; constexpr auto VK_TRUE=1u, VK_FALSE=0u;
constexpr u32 VK_STRUCTURE_TYPE_FENCE_CREATE_INFO=1, VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO=2;
constexpr u32 VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO=3, VK_STRUCTURE_TYPE_COMMAND_BUFFER_INHERITANCE_INFO=4;
constexpr u32 VK_COMMAND_BUFFER_LEVEL_PRIMARY=1, VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT=1;
constexpr u32 VK_PIPELINE_STAGE_TRANSFER_BIT=1, VK_PIPELINE_STAGE_VERTEX_SHADER_BIT=2, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT=4;
constexpr u32 CELL_GCM_TEXTURE_A8R8G8B8=1,CELL_GCM_TEXTURE_DEPTH24_D8=2,CELL_GCM_TEXTURE_R5G6B5=3,CELL_GCM_TEXTURE_DEPTH16=4;
#define FRAME_PRESENT_TIMEOUT 10000000ull
#define GENERAL_WAIT_TIMEOUT 2000000ull
#define AUDIT(x) assert(x)
#define ensure(x) assert(x)
#define CHECK_RESULT(expr) { VkResult _res = (expr); if (_res != VK_SUCCESS) vk::die_with_error(_res); }
__RESULTS__
struct VkFenceCreateInfo { u32 sType=0; };
struct VkCommandBufferAllocateInfo { u32 sType=0,commandBufferCount=0,commandPool=0,level=0; };
struct VkCommandBufferInheritanceInfo { u32 sType=0; };
struct VkCommandBufferBeginInfo { u32 sType=0,flags=0; VkCommandBufferInheritanceInfo* pInheritanceInfo=nullptr; };
struct test_result { u32 fence_failures=0,event_failures=0,success_checks=0,mismatches=0; u32 unsafe_resets=0,unsafe_fence_destructions=0,unsafe_readbacks=0; u32 success_local_fence_creates=0,success_local_fence_destroys=0; };
'''

SHIM = r'''
struct renderer_error : std::exception {};
struct statistics {
    u32 creates=0,destroys=0,pending_fence_destroys=0,resets=0,pending_resets=0,begins=0,ends=0,submits=0;
    u32 timed_waits=0,ready_rechecks=0,unbounded_pending_waits=0,event_waits=0;
    u32 fence_resets=0,state_clears=0,readbacks=0,guest_reads=0,swizzles=0;
    u32 async_flushes=0,wait_semaphores=0,query_closes=0,fatal_errors=0,locks=0;
    u32 event_destroys=0,unprotects=0,callbacks=0;
    u64 last_fence_timeout=0,last_event_timeout=0;
} stats;
VkResult fence_result=VK_SUCCESS,event_result=VK_SUCCESS;
std::unordered_map<u32,bool> pending_fences;
std::unordered_map<u32,u32> command_fences;
u32 next_handle=1;
struct atomic_flag { bool value=false; void release(bool x) { value=x; } operator bool() const { return value; } };
struct shared_mutex { void lock() { ++stats.locks; } void unlock() { --stats.locks; } };
struct reader_lock { shared_mutex& lock; explicit reader_lock(shared_mutex& x):lock(x){lock.lock();} ~reader_lock(){lock.unlock();} void upgrade() {} };
namespace fmt {
template<class... T> std::string format(const char*,T&&...) { return {}; }
template<class... T> [[noreturn]] void throw_exception(const char*,T&&...) { ++stats.fatal_errors; throw renderer_error{}; }
}
struct logger { template<class... T> void error(const char*,T&&...) {} template<class... T> void trace(const char*,T&&...) {} } rsx_log;
namespace utils { template<class A,class B> auto align(A x,B n) { return ((x+n-1)/n)*n; } }
namespace rpcs3::ios::rsx_sync { enum { texture,cb_reuse }; struct SiteScope { explicit SiteScope(int,bool=false) {} }; }
struct range { u32 start=64,bytes=256; u32 length() const { return bytes; } };
namespace rsx {
enum class texture_upload_context { framebuffer_storage,shader_read };
template<class T> using simple_array=std::vector<T>;
struct tile { u32 size=512,pitch=16; } tiled;
struct tile_region { rsx::tile* tile=nullptr; u32 base_address=64; explicit operator bool() const{return tile!=nullptr;} };
bool tiled_enabled=false;
struct renderer { tile_region get_tiled_memory_region(range) { return {tiled_enabled?&tiled:nullptr,64}; } } renderer_instance;
renderer* get_current_renderer() { return &renderer_instance; }
template<class T> void convert_linear_swizzle_bounded(std::span<const u8>,std::span<u8>,u32,u32,u32) { ++stats.swizzles; }
}
namespace vk {
void print_debug_markers() {}
std::string retrieve_device_fault_info() { return {}; }
void die_with_error(VkResult,std::string={},std::source_location=std::source_location::current());
__ERROR_HANDLER__
}
VkResult vkCreateFence(VkDevice,const VkFenceCreateInfo*,void*,VkFence* handle) { *handle=next_handle++; pending_fences[*handle]=false; ++stats.creates; return VK_SUCCESS; }
void vkDestroyFence(VkDevice,VkFence handle,void*) { ++stats.destroys; stats.pending_fence_destroys+=pending_fences.at(handle); pending_fences.erase(handle); }
VkResult vkResetFences(VkDevice,u32,const VkFence* handle) { assert(!pending_fences.at(*handle)); ++stats.fence_resets; return VK_SUCCESS; }
VkResult vkAllocateCommandBuffers(VkDevice,const VkCommandBufferAllocateInfo*,VkCommandBuffer* cb) { *cb=next_handle++; return VK_SUCCESS; }
void vkFreeCommandBuffers(VkDevice,u32,u32,const VkCommandBuffer* cb) { command_fences.erase(*cb); }
VkResult vkResetCommandBuffer(VkCommandBuffer cmd,u32) {
    ++stats.resets;
    if(auto it=command_fences.find(cmd);it!=command_fences.end()) {
        auto f=pending_fences.find(it->second);
        stats.pending_resets+=(f!=pending_fences.end() && f->second);
    }
    return VK_SUCCESS;
}
VkResult vkBeginCommandBuffer(VkCommandBuffer,const VkCommandBufferBeginInfo*) { ++stats.begins; return VK_SUCCESS; }
VkResult vkEndCommandBuffer(VkCommandBuffer) { ++stats.ends; return VK_SUCCESS; }
VkResult vkGetFenceStatus(VkDevice,VkFence handle) { return pending_fences.at(handle)?VK_NOT_READY:VK_SUCCESS; }
namespace vk {
struct fence {
    atomic_flag flushed; VkFence handle=0; VkDevice owner=0;
    explicit fence(VkDevice); ~fence();
    void reset() { vkResetFences(owner,1,&handle); flushed.release(false); }
    void wait_flush() { assert(flushed); }
    void signal_flushed() { flushed.release(true); }
};
__FENCE_CREATE__
__FENCE_DESTROY__
VkResult wait_for_fence(fence* f,u64 timeout=0) {
    f->wait_flush();
    if (!timeout) {
        if (!pending_fences.at(f->handle)) { ++stats.ready_rechecks; return VK_SUCCESS; }
        ++stats.unbounded_pending_waits;
    } else { ++stats.timed_waits; stats.last_fence_timeout=timeout; }
    if (fence_result==VK_SUCCESS || fence_result==VK_ERROR_DEVICE_LOST) pending_fences[f->handle]=false;
    if (!timeout && fence_result!=VK_SUCCESS) die_with_error(fence_result);
    return fence_result;
}
struct event { ~event() { ++stats.event_destroys; } };
VkResult wait_for_event(event*,u64 timeout) {
    ++stats.event_waits; stats.last_event_timeout=timeout;
    // Mirrors sync.cpp: event timeout is returned; other driver errors enter
    // the existing error handler before returning to imp_flush.
    if (event_result!=VK_SUCCESS && event_result!=VK_TIMEOUT) die_with_error(event_result);
    return event_result;
}
struct semaphore {};
struct command_pool { VkDevice get_owner() const {return 1;} operator u32() const{return 1;} } pool;
struct queue_submit_t {
    VkQueue queue=1; fence* pfence=nullptr; VkCommandBuffer commands=0;
    void wait_on(semaphore&,u32 mask) { assert(mask==7); ++stats.wait_semaphores; }
    void queue_signal(semaphore&) {}
};
void queue_submit(const queue_submit_t& info,VkBool32 flush) {
    assert(flush==VK_TRUE && info.pfence); ++stats.submits;
    pending_fences[info.pfence->handle]=true; command_fences[info.commands]=info.pfence->handle;
    info.pfence->signal_flushed();
}
class command_buffer {
protected:
    bool is_open=false,is_pending=false;
    fence* m_submit_fence=nullptr;
    command_pool* pool=nullptr;
    VkCommandBuffer commands=0;
    void clear_state_cache(){++stats.state_clears;}
public:
    enum access_type_hint {flush_only,all} access_hint=flush_only;
    enum command_buffer_data_flag {cb_has_open_query=0x08,cb_load_occluson_task=0x10};
    u32 flags=0;
    void create(command_pool&); void destroy(); void reset(); void begin(); void end(); void submit(queue_submit_t&,VkBool32=VK_FALSE);
    void clear_flags(){flags=0;} bool is_recording()const{return is_open;}
    bool pending()const{return is_pending;} fence* owned_fence()const{return m_submit_fence;}
};
__COMMAND_CREATE__
__COMMAND_DESTROY__
__COMMAND_RESET__
__COMMAND_BEGIN__
__COMMAND_END__
__COMMAND_SUBMIT__
namespace data_heap_manager {
using managed_heap_snapshot_t=std::vector<u64>;
bool use_command_buffer_reclamation(){return true;}
managed_heap_snapshot_t get_heap_snapshot(){return {1};}
u64 next_snapshot_id(){return 1;}
void restore_snapshot(managed_heap_snapshot_t&,u64){assert(false && "DMA path must not retire chunk snapshots");}
}
u64 get_event_id(){assert(false && "DMA path must not assign EIDs");return 0;}
void on_event_completed(u64){assert(false && "DMA path must not publish EIDs");}
__COMMAND_CHUNK__
void do_query_cleanup(command_buffer& cmd){++stats.query_closes;cmd.flags&=~command_buffer::cb_has_open_query;}
struct AsyncTaskScheduler {
    u32 mode=0; semaphore sema;
    bool is_recording()const{return mode>=2;} bool is_host_mode()const{return mode==2;}
    semaphore* get_sema(){return &sema;}
    void flush(queue_submit_t&,VkBool32 flush){assert(flush==VK_TRUE);++stats.async_flushes;}
} scheduler;
void flush_dma(u32,u32){++stats.readbacks;}
struct section_base { virtual void imp_flush()=0; virtual ~section_base()=default; };
class cached_texture_section : public section_base {
public:
    bool synchronized=true,swizzled=false;
    rsx::texture_upload_context context=rsx::texture_upload_context::shader_read;
    std::unique_ptr<vk::event> dma_fence=std::make_unique<vk::event>();
    u32 height=4,width=4,rsx_pitch=16,gcm_format=CELL_GCM_TEXTURE_A8R8G8B8;
    std::array<u8,512> guest{};
    range get_section_range()const{return {64,256};}
    range get_confirmed_range()const{return {72,120};}
    bool is_swizzled()const{return swizzled;}
    void* get_ptr(u32){++stats.guest_reads;return guest.data();}
__IMP_FLUSH__
};
struct cache_tag { u64 load()const{return 0;} };
struct cause_t { bool deferred_flush()const{return true;} cause_t undefer()const{return {};} };
struct thrashed_set { cause_t cause; bool flushed=false; u64 cache_tag=0; range fault_range; };
class texture_cache {
public:
    VkDevice device=1; VkDevice* m_device=&device; VkQueue m_submit_queue=1;
    shared_mutex m_cache_mutex; vk::cache_tag m_cache_update_tag;
    cached_texture_section* section=nullptr;
    using commandbuffer_type=command_buffer;
    void cleanup_after_dma_transfers(command_buffer&);
    template<class... A> void flush_set(command_buffer&,thrashed_set&,std::function<void()> cb,A&&...) {if(cb)cb(); section->imp_flush();}
    void unprotect_set(thrashed_set&){++stats.unprotects;}
    template<class... A> void invalidate_range_impl_base(command_buffer&,range,cause_t,std::function<void()>,A&&...){assert(false);}
__FLUSH_ALL__
};
}
struct fxo { template<class T> T* try_get(){return vk::scheduler.mode?&vk::scheduler:nullptr;} } fx;
fxo* g_fxo=&fx;
namespace vk {
__CLEANUP__
}
'''

RUN = r'''
template<class F> bool caught_error(F&& f){try{f();return false;}catch(const renderer_error&){return true;}}
void reset_statistics(){assert(stats.locks==0);stats={};}
void finish_gpu(){for(auto& [h,p]:pending_fences)p=false;}
test_result run(bool corrected){
    test_result result;
    const VkResult errors[]={VK_TIMEOUT,VK_ERROR_DEVICE_LOST,VK_ERROR_OUT_OF_HOST_MEMORY,VK_ERROR_OUT_OF_DEVICE_MEMORY};
    auto check=[&](bool expected){result.mismatches+=!expected;};
    for(u32 mode=0;mode<4;++mode)for(bool query:{false,true})for(VkResult status:errors){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.eid_tag=77;cmd.heap_snapshot_id=99;
        if(query)cmd.flags|=vk::command_buffer::cb_has_open_query;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=status;
        const auto owned=cmd.owned_fence()->handle;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.fence_failures;
        result.unsafe_resets+=stats.pending_resets;
        result.unsafe_fence_destructions+=stats.pending_fence_destroys;
        if(corrected){
            check(caught && stats.timed_waits==1 && stats.last_fence_timeout==GENERAL_WAIT_TIMEOUT);
            check(stats.resets==0 && stats.begins==0 && stats.creates==0 && stats.destroys==0 && stats.unbounded_pending_waits==0);
            check(cmd.pending() && !cmd.is_recording() && cmd.owned_fence()->handle==owned && cmd.flags==0);
        }else{
            check(!caught && stats.resets==1 && stats.begins==1 && stats.creates==1 && stats.destroys==1);
            check(!cmd.pending() && cmd.is_recording());
        }
        check(cmd.eid_tag==77 && cmd.heap_snapshot_id==99 && stats.query_closes==query);
        check(stats.async_flushes==(mode>=2) && stats.wait_semaphores==(mode==2));
        finish_gpu();cmd.destroy();
    }
    for(u32 mode=0;mode<4;++mode)for(bool query:{false,true}){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.eid_tag=77;cmd.heap_snapshot_id=99;
        if(query)cmd.flags|=vk::command_buffer::cb_has_open_query;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=VK_SUCCESS;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.success_checks;
        check(!caught && stats.timed_waits==1 && stats.last_fence_timeout==GENERAL_WAIT_TIMEOUT && stats.resets==1 && stats.begins==1);
        check(!cmd.pending() && cmd.is_recording() && cmd.eid_tag==77 && cmd.heap_snapshot_id==99);
        check(cmd.flags==(query?u32(vk::command_buffer::cb_load_occluson_task):0u) && stats.query_closes==query);
        check(stats.unbounded_pending_waits==0 && stats.pending_resets==0 && stats.pending_fence_destroys==0);
        check(stats.async_flushes==(mode>=2) && stats.wait_semaphores==(mode==2));
        check(stats.creates==!corrected && stats.destroys==!corrected && stats.ready_rechecks==corrected && stats.fence_resets==corrected);
        result.success_local_fence_creates+=stats.creates;result.success_local_fence_destroys+=stats.destroys;
        finish_gpu();cmd.destroy();
    }
    // Auxiliary buffers keep the original asynchronous submission path.
    for(u32 mode=0;mode<4;++mode){
        vk::command_buffer_chunk cmd;cmd.create(vk::pool);cmd.begin();cmd.access_hint=vk::command_buffer::all;
        vk::scheduler.mode=mode;vk::texture_cache cache;reset_statistics();fence_result=VK_TIMEOUT;
        const bool caught=caught_error([&]{cache.cleanup_after_dma_transfers(cmd);});
        ++result.success_checks;
        check(!caught && stats.submits==1 && stats.timed_waits==0 && stats.resets==0 && stats.begins==0 && cmd.pending());
        check(stats.creates==0 && stats.destroys==0 && stats.async_flushes==0);
        finish_gpu();cmd.destroy();
    }
    for(bool tiled:{false,true})for(bool swizzled:{false,true})for(bool framebuffer:{false,true}){
        for(VkResult status:errors){
            vk::cached_texture_section section;section.swizzled=swizzled;
            section.context=framebuffer?rsx::texture_upload_context::framebuffer_storage:rsx::texture_upload_context::shader_read;
            rsx::tiled_enabled=tiled;vk::texture_cache cache;cache.section=&section;
            vk::command_buffer unused;vk::thrashed_set data;reset_statistics();event_result=status;
            const auto* original_event=section.dma_fence.get();
            const bool caught=caught_error([&]{cache.flush_all(unused,data,[]{++stats.callbacks;});});
            ++result.event_failures;
            const bool should_stop=corrected || status!=VK_TIMEOUT;
            check(caught==should_stop && stats.event_waits==1 && stats.last_event_timeout==GENERAL_WAIT_TIMEOUT);
            check(stats.readbacks==!should_stop && stats.guest_reads==(!should_stop&&swizzled) && stats.swizzles==(!should_stop&&swizzled));
            check(stats.event_destroys==0 && section.dma_fence.get()==original_event && stats.unprotects==!should_stop);
            check(stats.locks==0 && stats.callbacks==1);
            result.unsafe_readbacks+=stats.readbacks;
        }
        vk::cached_texture_section section;section.swizzled=swizzled;
        section.context=framebuffer?rsx::texture_upload_context::framebuffer_storage:rsx::texture_upload_context::shader_read;
        rsx::tiled_enabled=tiled;vk::texture_cache cache;cache.section=&section;
        vk::command_buffer unused;vk::thrashed_set data;reset_statistics();event_result=VK_SUCCESS;
        const bool caught=caught_error([&]{cache.flush_all(unused,data,[]{++stats.callbacks;});});
        ++result.success_checks;
        check(!caught && stats.event_waits==1 && stats.last_event_timeout==GENERAL_WAIT_TIMEOUT && stats.readbacks==1);
        check(stats.guest_reads==swizzled && stats.swizzles==swizzled && stats.unprotects==1 && stats.event_destroys==0 && stats.locks==0);
    }
    return result;
}
'''

MAIN = r'''
void print(const test_result& r){
    std::cout<<"{\"fence_failure_cases\":"<<r.fence_failures<<",\"event_failure_cases\":"<<r.event_failures
    <<",\"success_cases\":"<<r.success_checks<<",\"mismatches\":"<<r.mismatches
    <<",\"unsafe_resets\":"<<r.unsafe_resets<<",\"unsafe_fence_destructions\":"<<r.unsafe_fence_destructions
    <<",\"unsafe_readbacks\":"<<r.unsafe_readbacks<<",\"success_local_fence_creates\":"<<r.success_local_fence_creates
    <<",\"success_local_fence_destroys\":"<<r.success_local_fence_destroys<<"}";
}
int main(){std::cout<<"{\"baseline\":";print(baseline::run(false));std::cout<<",\"candidate\":";print(candidate::run(true));std::cout<<"}\n";}
'''


def between(source, start, end):
    a=source.index(start)
    return source[a:source.index(end,a)]


def function(source, start):
    a=source.index(start)
    brace=source.index('\n',a)
    brace=source.index('{',brace)
    depth=1
    e=brace+1
    while depth:
        if source[e]=='{': depth+=1
        elif source[e]=='}': depth-=1
        e+=1
    return source[a:e]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--baseline',type=Path,required=True)
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--support-core',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--shared-source',type=Path,default=HERE/'fixtures/shared.cpp')
    ap.add_argument('--label',default='dma-wait-comparison')
    ap.add_argument('--generate-only',action='store_true')
    args=ap.parse_args()
    commands=(args.support_core/REL/'vkutils/commands.cpp').read_text()
    sync=(args.support_core/REL/'vkutils/sync.cpp').read_text()
    types=(args.support_core/REL/'VKGSRenderTypes.hpp').read_text()
    common=(args.support_core/'rpcs3/Emu/RSX/Common/texture_cache.h').read_text()
    shared=args.shared_source.read_text()
    error=between(shared,'\tvoid die_with_error(', '\n\tVKAPI_ATTR VkBool32 VKAPI_CALL dbgFunc(')
    status=['VK_SUCCESS','VK_NOT_READY','VK_TIMEOUT','VK_EVENT_SET','VK_EVENT_RESET','VK_INCOMPLETE']
    status+=sorted(set(re.findall(r'case (VK_[A-Z0-9_]+):',error))-set(status))
    results='enum VkResult { '+', '.join(f'{x}={i}' for i,x in enumerate(status))+' };'
    support={
        'ERROR_HANDLER':error,
        'FENCE_CREATE':function(sync,'\tfence::fence(VkDevice dev)'),
        'FENCE_DESTROY':function(sync,'\tfence::~fence()'),
        'COMMAND_CREATE':function(commands,'\tvoid command_buffer::create('),
        'COMMAND_DESTROY':function(commands,'\tvoid command_buffer::destroy()'),
        'COMMAND_RESET':function(commands,'\tvoid command_buffer::reset()'),
        'COMMAND_BEGIN':function(commands,'\tvoid command_buffer::begin()'),
        'COMMAND_END':function(commands,'\tvoid command_buffer::end()'),
        'COMMAND_SUBMIT':function(commands,'\tvoid command_buffer::submit('),
        'COMMAND_CHUNK':between(types,'\tstruct command_buffer_chunk :','\n\tstruct occlusion_data'),
        'FLUSH_ALL': '\t\ttemplate<typename... Args>\n'+function(common,'\t\tbool flush_all('),
    }
    text=HEADERS.replace('__RESULTS__',results)
    variants={}
    for name,core in [('baseline',args.baseline),('candidate',args.candidate)]:
        cpp=(core/REL/'VKTextureCache.cpp').read_text()
        header=(core/REL/'VKTextureCache.h').read_text()
        fragments=dict(support,CLEANUP=function(cpp,'\tvoid texture_cache::cleanup_after_dma_transfers('),IMP_FLUSH=function(header,'\t\tvoid imp_flush() override'))
        variant=SHIM
        for key,body in fragments.items():variant=variant.replace('__'+key+'__',body)
        text+='\nnamespace '+name+' {\n'+variant+RUN+'\n}\n'
        variants[name]={
            'source_sha256':{'VKTextureCache.cpp':hashlib.sha256(cpp.encode()).hexdigest(),'VKTextureCache.h':hashlib.sha256(header.encode()).hexdigest()},
            'extracted_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in fragments.items()}}
    text+=MAIN
    fingerprint={'variants':variants,'harness_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'support_source_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in [('commands.cpp',commands),('sync.cpp',sync),('VKGSRenderTypes.hpp',types),('Common/texture_cache.h',common),('shared.cpp',shared)]}}
    args.output_dir.mkdir(parents=True,exist_ok=True)
    cpp=args.output_dir/(args.label+'.cpp');cpp.write_text(text)
    if args.generate_only:
        result=dict(fingerprint,mode='generate-only',native_compilation=False,native_execution=False)
        (args.output_dir/(args.label+'.generated.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return
    exe=args.output_dir/(args.label+'.exe')
    cmd=['g++','-std=c++20','-DRPCS3_IOS','-Wall','-Wextra','-Werror','-O2','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)]
    compiled=subprocess.run(cmd,capture_output=True,text=True)
    (args.output_dir/(args.label+'-compile.txt')).write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode:raise SystemExit(compiled.stderr)
    run=subprocess.run([str(exe)],capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
    (args.output_dir/(args.label+'-output.txt')).write_text(run.stdout+run.stderr)
    if run.returncode:raise SystemExit(run.stderr or run.returncode)
    result=json.loads(run.stdout)
    assert result['baseline']['mismatches']==0 and result['candidate']['mismatches']==0,result
    for key in ['unsafe_resets','unsafe_fence_destructions','unsafe_readbacks']:
        assert result['baseline'][key]>0 and result['candidate'][key]==0,result
    result.update(fingerprint,command=cmd,sanitized=True,
        scope='Exact production DMA cleanup/imp_flush, command-buffer create/destroy/begin/end/reset/submit/chunk, fence constructor/destructor, flush_all lock and existing error handler; driver/scheduler/guest-copy shims, no GPU execution')
    (args.output_dir/(args.label+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
