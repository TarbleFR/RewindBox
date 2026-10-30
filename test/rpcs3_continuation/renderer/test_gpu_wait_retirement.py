#!/usr/bin/env python3
"""Exercise production command retirement and its callers with injected VkResults.

Extracts command_buffer_chunk, command_buffer::reset, frame_context_cleanup,
wait_all and the exact upstream die_with_error implementation. Vulkan handles,
locks and the driver wait are deterministic shims. No GPU is executed.
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

PRELUDE = r'''
#include <cassert>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <source_location>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using u32=std::uint32_t;
using u64=std::uint64_t;
using s32=std::int32_t;
#define ensure(x) assert(x)
__VK_RESULTS__
struct renderer_error : std::exception {};
struct counters {
    u32 waits=0, fence_resets=0, completions=0, heaps=0, driver_resets=0;
    u32 trims=0, globals=0, frames=0, latency_records=0, fatal_errors=0, locks=0;
    u64 last_timeout=0;
} counts;
VkResult injected_wait=VK_SUCCESS, injected_status=VK_NOT_READY;
std::function<void()> upgrade_hook;
struct shared_mutex {};
struct reader_lock {
    explicit reader_lock(shared_mutex&) { ++counts.locks; }
    ~reader_lock() { --counts.locks; }
    void upgrade() { if (upgrade_hook) { auto f=std::exchange(upgrade_hook,{}); f(); } }
};
namespace fmt {
template<class... T> std::string format(const char*, T&&...) { return {}; }
template<class... T> [[noreturn]] void throw_exception(const char*, T&&...) {
    ++counts.fatal_errors; throw renderer_error{};
}
}
struct logger { template<class... T> void error(const char*, T&&...) {} } rsx_log;
namespace utils { inline u64 get_tsc() { return 42; } }
namespace rpcs3::ios::rsx_sync {
enum { cb_reuse, frame_cleanup };
struct SiteScope { explicit SiteScope(int) {} };
struct recorder { void record(u64) { ++counts.latency_records; } } frame_latency_ticks;
}
namespace vk {
void print_debug_markers() {}
std::string retrieve_device_fault_info() { return {}; }
void die_with_error(VkResult error_code, std::string message={}, std::source_location src_loc=std::source_location::current());
__PRODUCTION_ERROR_HANDLER__
struct fence {
    bool flushed=true;
    u32 handle=1;
    void reset() { ++counts.fence_resets; }
    void wait_flush() {}
};
struct command_pool { u32 get_owner() const { return 1; } } pool;
struct command_buffer {
    bool is_pending=true;
    vk::fence owned_fence;
    vk::fence* m_submit_fence=&owned_fence;
    command_pool* pool=&vk::pool;
    u32 commands=1;
    void reset();
};
VkResult wait_for_fence(fence*, u64 timeout) {
    ++counts.waits; counts.last_timeout=timeout; return injected_wait;
}
u64 get_event_id() { return 10; }
void on_event_completed(u64) { ++counts.completions; }
namespace data_heap_manager {
using managed_heap_snapshot_t=std::vector<u64>;
bool use_command_buffer_reclamation() { return true; }
managed_heap_snapshot_t get_heap_snapshot() { return {7}; }
u64 next_snapshot_id() { return 1; }
void restore_snapshot(managed_heap_snapshot_t&, u64) { ++counts.heaps; }
}
}
VkResult vkGetFenceStatus(u32,u32) { return injected_status; }
VkResult vkResetCommandBuffer(u32,u32) { ++counts.driver_resets; return VK_SUCCESS; }
__CHECK_RESULT_MACRO__
#define FRAME_PRESENT_TIMEOUT 10000000ull
namespace vk {
__PRODUCTION_COMMAND_RESET__
__PRODUCTION_CHUNK__
struct command_chain {
    command_buffer_chunk m_cb_list[4];
__PRODUCTION_WAIT_ALL__
};
struct frame_context_t {
    command_buffer_chunk* swap_command_buffer=nullptr;
    u64 ios_submit_tsc=1,last_frame_sync_time=1,heap_snapshot_id=1;
    data_heap_manager::managed_heap_snapshot_t heap_snapshot{9};
};
struct ui_overlay_renderer { void remove_temp_resources(u32) {} } ui;
template<class T> T* get_overlay_pass() { return &ui; }
struct resources { void trim() { ++counts.trims; } } resource_manager;
resources* get_resource_manager() { return &resource_manager; }
void reset_global_resources() { ++counts.globals; }
void advance_completed_frame_counter() { ++counts.frames; }
}
struct view { u32 uid=0; };
struct overlays {
    bool has_dirty() const { return false; }
    void lock_shared() {} void unlock_shared() {}
    std::vector<view*> get_dirty() { return {}; }
    void dispose(const std::vector<u32>&) {}
};
class VKGSRender {
public:
    bool swapchain_unavailable=false;
    overlays* m_overlay_manager=nullptr;
    u64 m_last_heap_sync_time=0;
    std::deque<vk::frame_context_t*> m_queued_frames;
    void frame_context_cleanup(vk::frame_context_t*);
};
__PRODUCTION_FRAME_CLEANUP__
'''

MAIN = r'''
void start(VkResult result=VK_SUCCESS) {
    assert(counts.locks==0); counts={}; injected_wait=result;
    injected_status=VK_NOT_READY; upgrade_hook={};
}
void initialize(vk::command_buffer_chunk& cb) {
    cb.eid_tag=77; cb.heap_snapshot.clear(); cb.heap_snapshot.push_back(5); cb.heap_snapshot_id=99;
}
template<class F> bool throws(F&& f) {
    try { f(); return false; } catch (const renderer_error&) { return true; }
}
bool unchanged(const vk::command_buffer_chunk& cb) {
    return cb.is_pending && cb.eid_tag==77 && cb.heap_snapshot_id==99 && cb.heap_snapshot==std::vector<u64>{5};
}
bool no_retirement() {
    return counts.fence_resets==0 && counts.completions==0 && counts.heaps==0 && counts.driver_resets==0;
}
int main() {
    u32 failure_cases=0, failure_mismatches=0, success_cases=0, success_mismatches=0;
    u32 false_completions=0, false_fence_resets=0, false_heap_restores=0, unsafe_driver_resets=0, unsafe_frame_cleanup=0;
    auto failed_case=[&](bool ok) {
        ++failure_cases; failure_mismatches+=!ok;
        assert(counts.locks==0);
    };
    auto passed_case=[&](bool ok) {
        ++success_cases; success_mismatches+=!ok;
        assert(counts.locks==0);
    };
    auto count_unsafe=[&] {
        false_completions+=counts.completions;
        false_fence_resets+=counts.fence_resets;
        false_heap_restores+=counts.heaps;
        unsafe_driver_resets+=counts.driver_resets;
        unsafe_frame_cleanup+=counts.frames;
    };
    const VkResult errors[]={VK_TIMEOUT,VK_ERROR_DEVICE_LOST,VK_ERROR_OUT_OF_HOST_MEMORY,VK_ERROR_OUT_OF_DEVICE_MEMORY};
    for (const auto result:errors) {
        // Direct wait: no retirement on failure and a repeated call must not
        // turn the unfinished work into an immediate success.
        start(result); vk::command_buffer_chunk direct; initialize(direct);
        bool caught=throws([&] { direct.wait(FRAME_PRESENT_TIMEOUT); });
        failed_case(caught && unchanged(direct) && no_retirement() && counts.last_timeout==FRAME_PRESENT_TIMEOUT);
        count_unsafe();
        const u32 waits_before=counts.waits;
        caught=throws([&] { direct.wait(FRAME_PRESENT_TIMEOUT); });
        failed_case(caught && unchanged(direct) && no_retirement() && counts.waits==waits_before+1);

        // The actual command-buffer reuse caller must not increment reset_id
        // or call vkResetCommandBuffer after a failed timed wait.
        for (bool flushed:{false,true}) {
            start(result); vk::command_buffer_chunk cb; initialize(cb);
            cb.owned_fence.flushed=flushed;
            caught=throws([&] { cb.reset(); });
            failed_case(caught && unchanged(cb) && cb.reset_id==0 && no_retirement() && counts.last_timeout==FRAME_PRESENT_TIMEOUT);
            count_unsafe();
        }

        // The actual frame cleanup caller must preserve queued work, frame
        // ownership and both heap snapshots; no resource cleanup may run.
        start(result); vk::command_buffer_chunk cb; initialize(cb);
        vk::frame_context_t ctx; ctx.swap_command_buffer=&cb;
        VKGSRender renderer; renderer.m_queued_frames.push_back(&ctx);
        caught=throws([&] { renderer.frame_context_cleanup(&ctx); });
        failed_case(caught && unchanged(cb) && no_retirement() && ctx.swap_command_buffer==&cb
            && renderer.m_queued_frames.size()==1 && renderer.m_last_heap_sync_time==0
            && counts.frames==0 && counts.trims==0 && counts.globals==0 && counts.latency_records==0);
        count_unsafe();

        // wait_all propagates the exception at any slot. Already completed
        // predecessors are allowed to retire; failing/subsequent work is not.
        for (u32 failed_slot=0;failed_slot<4;++failed_slot) {
            start(result); vk::command_chain chain;
            for (auto& item:chain.m_cb_list) initialize(item);
            for (u32 i=0;i<failed_slot;++i) chain.m_cb_list[i].is_pending=false;
            caught=throws([&] { chain.wait_all(); });
            bool safe=caught && no_retirement() && counts.waits==1 && counts.last_timeout==0;
            for (u32 i=failed_slot;i<4;++i) safe &= unchanged(chain.m_cb_list[i]);
            failed_case(safe); count_unsafe();
        }
    }

    // Success and already-finished paths retain their old behavior.
    for (u64 timeout:{0ull,FRAME_PRESENT_TIMEOUT}) {
        start(); vk::command_buffer_chunk cb; initialize(cb);
        const bool success=cb.wait(timeout)==VK_SUCCESS;
        passed_case(success && !cb.is_pending && cb.eid_tag==0 && cb.heap_snapshot_id==0 && cb.heap_snapshot.empty()
            && counts.waits==1 && counts.last_timeout==timeout && counts.fence_resets==1 && counts.completions==1 && counts.heaps==1);
        const auto before=counts;
        passed_case(cb.wait(timeout)==VK_SUCCESS && counts.waits==before.waits && counts.completions==before.completions && counts.fence_resets==before.fence_resets && counts.heaps==before.heaps);
    }
    start(); vk::command_buffer_chunk no_snapshot; initialize(no_snapshot); no_snapshot.heap_snapshot_id=0;
    passed_case(no_snapshot.wait()==VK_SUCCESS && counts.heaps==0 && counts.completions==1);

    for (u32 path=0;path<3;++path) {
        start(); vk::command_buffer_chunk cb; initialize(cb);
        if (path==1) injected_status=VK_SUCCESS;
        if (path==2) cb.is_pending=false;
        cb.reset();
        passed_case(cb.reset_id==1 && counts.driver_resets==1 && counts.waits==(path==0)
            && counts.completions==(path!=2) && counts.fence_resets==(path!=2) && counts.heaps==(path!=2));
    }
    for (bool pending:{false,true}) {
        start(); vk::command_buffer_chunk cb; initialize(cb); cb.is_pending=pending;
        vk::frame_context_t ctx; ctx.swap_command_buffer=&cb;
        VKGSRender renderer; renderer.m_queued_frames.push_back(&ctx);
        renderer.frame_context_cleanup(&ctx);
        passed_case(ctx.swap_command_buffer==nullptr && renderer.m_queued_frames.empty()
            && counts.waits==pending && counts.heaps==1u+pending && counts.frames==1
            && counts.trims==1 && counts.globals==1 && counts.latency_records==1);
    }
    start(); vk::command_chain chain;
    for (auto& cb:chain.m_cb_list) initialize(cb);
    chain.wait_all();
    passed_case(counts.waits==4 && counts.completions==4 && counts.fence_resets==4 && counts.heaps==4);

    // Another waiter may retire the command before the lock is upgraded.
    // Deterministic interleaving checks the post-upgrade is_pending guard.
    start(); vk::command_buffer_chunk raced; initialize(raced);
    upgrade_hook=[&] { raced.is_pending=false; raced.eid_tag=0; raced.heap_snapshot_id=0; raced.heap_snapshot.clear(); };
    passed_case(raced.wait()==VK_SUCCESS && counts.waits==1 && no_retirement());

    std::cout << "{\"failure_cases\":" << failure_cases << ",\"failure_mismatches\":" << failure_mismatches
        << ",\"success_cases\":" << success_cases << ",\"success_mismatches\":" << success_mismatches
        << ",\"false_completions\":" << false_completions << ",\"false_fence_resets\":" << false_fence_resets
        << ",\"false_heap_restores\":" << false_heap_restores << ",\"unsafe_driver_resets\":" << unsafe_driver_resets
        << ",\"unsafe_frame_cleanup\":" << unsafe_frame_cleanup << "}\n";
}
'''


def extract_function(source, start, end):
    a = source.index(start)
    return source[a:source.index(end, a)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--core', type=Path, required=True)
    ap.add_argument('--caller-core', type=Path)
    ap.add_argument('--shared-source', type=Path, default=HERE/'fixtures/shared.cpp')
    ap.add_argument('--shared-header', type=Path, default=HERE/'fixtures/shared.h')
    ap.add_argument('--output-dir', type=Path, default=HERE/'evidence')
    ap.add_argument('--label', required=True)
    ap.add_argument('--sanitize', action='store_true')
    ap.add_argument('--expect-failures', action='store_true')
    ap.add_argument('--generate-only', action='store_true')
    args = ap.parse_args()
    callers = args.caller_core or args.core
    header = (args.core/REL/'VKGSRenderTypes.hpp').read_text()
    present = (callers/REL/'VKPresent.cpp').read_text()
    commands = (callers/REL/'vkutils/commands.cpp').read_text()
    shared = args.shared_source.read_text()
    shared_header = args.shared_header.read_text()
    chunk = extract_function(header, '\tstruct command_buffer_chunk :', '\n\tstruct occlusion_data')
    wait_all = extract_function(header, '\t\tvoid wait_all()', '\n\t\tinline command_buffer_chunk* next()')
    reset = extract_function(commands, '\tvoid command_buffer::reset()', '\n\tvoid command_buffer::clear_state_cache()')
    frame = extract_function(present, 'void VKGSRender::frame_context_cleanup(', '\nvk::viewable_image* VKGSRender::get_present_source(')
    error = extract_function(shared, '\tvoid die_with_error(', '\n\tVKAPI_ATTR VkBool32 VKAPI_CALL dbgFunc(')
    macro = next(x for x in shared_header.splitlines() if x.startswith('#define CHECK_RESULT('))
    statuses = ['VK_SUCCESS','VK_NOT_READY','VK_TIMEOUT','VK_EVENT_SET','VK_EVENT_RESET','VK_INCOMPLETE']
    statuses += sorted(set(re.findall(r'case (VK_[A-Z0-9_]+):', error))-set(statuses))
    vk_results = 'enum VkResult { '+', '.join(f'{status}={i}' for i,status in enumerate(statuses))+' };'
    fragments = {'VK_RESULTS': vk_results, 'PRODUCTION_ERROR_HANDLER': error,
        'CHECK_RESULT_MACRO': macro, 'PRODUCTION_COMMAND_RESET': reset,
        'PRODUCTION_CHUNK': chunk, 'PRODUCTION_WAIT_ALL': wait_all, 'PRODUCTION_FRAME_CLEANUP': frame}
    program = PRELUDE
    for key, value in fragments.items():
        program = program.replace('__'+key+'__',value)
    program += MAIN
    args.output_dir.mkdir(parents=True,exist_ok=True)
    cpp = args.output_dir/(args.label+'.cpp')
    cpp.write_text(program)
    fingerprints = dict(
        source_sha256=hashlib.sha256(header.encode()).hexdigest(),
        caller_sha256=hashlib.sha256(present.encode()).hexdigest(),
        error_handler_source_sha256=hashlib.sha256(shared.encode()).hexdigest(),
        extracted_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in fragments.items() if k.startswith('PRODUCTION_')},
        harness_sha256=hashlib.sha256(program.encode()).hexdigest())
    if args.generate_only:
        generated = dict(fingerprints,mode='generate-only',native_compilation=False,native_execution=False)
        (args.output_dir/(args.label+'.generated.json')).write_text(json.dumps(generated,indent=2)+'\n')
        print(json.dumps(generated))
        return
    exe = args.output_dir/(args.label+'.exe')
    cmd = ['g++','-std=c++20','-DRPCS3_IOS','-Wall','-Wextra','-Werror','-O2',str(cpp),'-o',str(exe)]
    if args.sanitize:
        cmd[1:1] = ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    compiled = subprocess.run(cmd,capture_output=True,text=True)
    (args.output_dir/(args.label+'-compile.txt')).write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode:
        raise SystemExit(compiled.stderr)
    run = subprocess.run([str(exe)],capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
    (args.output_dir/(args.label+'-output.txt')).write_text(run.stdout+run.stderr)
    if run.returncode:
        raise SystemExit(run.stderr or run.returncode)
    result = json.loads(run.stdout)
    assert bool(result['failure_mismatches']) == args.expect_failures,result
    assert result['success_mismatches'] == 0,result
    if not args.expect_failures:
        assert all(result[k]==0 for k in ('false_completions','false_fence_resets','false_heap_restores','unsafe_driver_resets','unsafe_frame_cleanup')),result
    result.update(fingerprints,
        command=cmd,sanitized=args.sanitize,
        scope='Exact production command_buffer_chunk/reset/frame_context_cleanup/wait_all/die_with_error; injected driver results and deterministic lock-upgrade interleaving; no Vulkan/GPU execution')
    (args.output_dir/(args.label+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
