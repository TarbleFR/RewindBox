// SPDX-License-Identifier: MIT
#include "ios/IOSGraphicsMemorySnapshot.h"
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <unordered_map>
using u64=std::uint64_t;
#define ensure(x) do{if(!(x)){std::cerr<<__LINE__<<" assertion "<<#x<<'\n';std::abort();}}while(false)
namespace vk {
enum vmm_allocation_pool {VMM_ALLOCATION_POOL_UNDEFINED,VMM_ALLOCATION_POOL_SYSTEM,VMM_ALLOCATION_POOL_SURFACE_CACHE,VMM_ALLOCATION_POOL_TEXTURE_CACHE,VMM_ALLOCATION_POOL_SWAPCHAIN,VMM_ALLOCATION_POOL_SCRATCH,VMM_ALLOCATION_POOL_SAMPLER};
struct Registry {std::shared_mutex mutex;std::unordered_map<vmm_allocation_pool,std::atomic<u64>> pool_usage;} g_vmm_stats;
#include "helper.inc"
}
#include "snapshot.inc"
void fill(u64 base){
 auto& map=vk::g_vmm_stats.pool_usage;
 map[vk::VMM_ALLOCATION_POOL_SYSTEM]=base;map[vk::VMM_ALLOCATION_POOL_SURFACE_CACHE]=base*2;
 map[vk::VMM_ALLOCATION_POOL_TEXTURE_CACHE]=base*3;map[vk::VMM_ALLOCATION_POOL_SWAPCHAIN]=base*4;
 map[vk::VMM_ALLOCATION_POOL_SCRATCH]=base*5;map[vk::VMM_ALLOCATION_POOL_UNDEFINED]=base*6;
 map[vk::VMM_ALLOCATION_POOL_SAMPLER]=base*7;
}
void consistent(const rpcs3::ios::graphics_memory_snapshot& s){
 ensure(s.valid&&s.surfaces==s.system*2&&s.textures==s.system*3&&s.swapchain==s.system*4&&s.scratch==s.system*5&&s.other==s.system*6&&s.samplers==s.system*7);
}
int main(){
 auto empty=rpcs3::ios::capture_graphics_memory_snapshot();consistent(empty);ensure(!empty.system&&!empty.samplers&&vk::g_vmm_stats.pool_usage.empty());
 {std::unique_lock lock(vk::g_vmm_stats.mutex);fill(0x1'0000'0000ull);}
 auto wide=rpcs3::ios::capture_graphics_memory_snapshot();consistent(wide);ensure(wide.system==0x1'0000'0000ull);
 // A held writer cannot block the reporter. It is released only after the
 // real snapshot has returned valid=false, so a blocking reader deadlocks.
 std::mutex gate;std::condition_variable cv;bool owned=false,release=false;
 std::thread blocked([&]{std::unique_lock writer(vk::g_vmm_stats.mutex);std::unique_lock lock(gate);owned=true;cv.notify_all();cv.wait(lock,[&]{return release;});});
 {std::unique_lock lock(gate);cv.wait(lock,[&]{return owned;});}
 auto busy=rpcs3::ios::capture_graphics_memory_snapshot();ensure(!busy.valid&&!busy.system&&!busy.samplers);
 {std::lock_guard lock(gate);release=true;cv.notify_all();}blocked.join();
 std::atomic<bool> done{false};std::atomic<unsigned> valid{0},skipped{0};
 std::thread writer([&]{
  for(u64 n=1;n<=30000;++n){std::unique_lock lock(vk::g_vmm_stats.mutex);vk::g_vmm_stats.pool_usage.clear();if(n%8)fill(n);}
  done=true;
 });
 while(!done){auto s=rpcs3::ios::capture_graphics_memory_snapshot();if(s.valid){consistent(s);++valid;}else ++skipped;}
 writer.join();consistent(rpcs3::ios::capture_graphics_memory_snapshot());
 {std::unique_lock lock(vk::g_vmm_stats.mutex);vk::g_vmm_stats.pool_usage.clear();}
 consistent(rpcs3::ios::capture_graphics_memory_snapshot());
 std::cout<<"PASS empty/64-bit/category units/sampler count, held-writer nonblocking refusal, 30000 reset/rebuild epochs, coherent observations="<<valid<<", skipped="<<skipped<<", empty reset; no GPU operation\n";
}
