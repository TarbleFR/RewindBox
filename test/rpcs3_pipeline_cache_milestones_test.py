#!/usr/bin/env python3
"""Execute the production cache-boundary classifier, admission and routing.

The harness uses a portable mutex/clock shim for os_unfair_lock and CACurrentMediaTime.
This checks host routing, not Foundation writes, MoltenVK or an iPhone fix.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
host = HOST.read_text()


def function(name):
    start = host.index(name)
    start = host.rindex('\nstatic ', 0, start) + 1
    return host[start:host.index('\n}\n', start) + 3]


classifier = function('BOOL RPCS3PipelineCacheBoundary(const char* message)')
admission = function('BOOL RPCS3AdmitPipelineCacheMilestone(void)')
log = host.split('static void RPCS3Log(void* context, int32_t level, const char* message) {', 1)[1].split('\n}', 1)[0]
begin = log.index('  } else if (RPCS3PipelineCacheBoundary(message)) {')
end = log.index('  } else if (const char* stage = RPCS3Build487MilestoneStage(message))', begin)
route = '  if' + log[begin + len('  } else if'):end] + '  }\n'
call = 'RPCS3Milestone(@"vk_pipeline_cache", RPCS3Build487MilestoneText(message));'
assert route.count(call) == 1
route = route.replace(call, 'recordMilestone(message);')
assert begin < log.index('  const BOOL profiler =')
logic = log[log.index('  const BOOL profiler ='):log.index('  NSString* text =')].replace('return;', 'return false;')

source = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>
using BOOL = bool;
constexpr BOOL YES = true, NO = false;
using CFTimeInterval = double;
using os_unfair_lock = std::mutex;
#define OS_UNFAIR_LOCK_INIT {}
static std::atomic<double> testNow{0};
double CACurrentMediaTime() { return testNow.load(std::memory_order_relaxed); }
void os_unfair_lock_lock(os_unfair_lock* lock) { lock->lock(); }
void os_unfair_lock_unlock(os_unfair_lock* lock) { lock->unlock(); }
void RPCS3ReportDroppedLines(uint32_t) {}
static std::atomic<unsigned> milestones{0};
void recordMilestone(const char*) { ++milestones; }
''' + classifier + admission + r'''
bool permitLog(int32_t level, const char* message) {
''' + route + logic + r'''
  return true;
}
int main() {
  const char* boundaries[] = {
    "RSX: Vulkan driver pipeline cache: starting file read and validation.",
    "Vulkan driver pipeline cache path: /cache/title/shaders_cache/vk_pipeline_cache.bin",
    "Vulkan driver pipeline cache: using an in-memory cache for this session.",
    "Vulkan driver pipeline cache could not be read completely; starting empty.",
    "Vulkan driver pipeline cache is incompatible or invalid; starting empty.",
    "Vulkan driver pipeline cache has an invalid size (17 bytes); starting empty.",
    "Vulkan driver pipeline cache: file read and validation finished in 4 ms (100 usable bytes).",
    "Vulkan driver pipeline cache: starting driver preparation from 100 bytes; shader library compilation may take several minutes.",
    "Vulkan driver pipeline cache: driver preparation returned VkResult 0 after 77 ms.",
    "Vulkan driver rejected 100 bytes of persisted pipeline cache data (VkResult -1); retrying empty.",
    "Vulkan driver pipeline cache: empty-cache retry returned VkResult 0 after 2 ms.",
    "Vulkan driver pipeline cache is unavailable (VkResult -1).",
    "Vulkan driver pipeline cache initialized empty.",
    "Vulkan driver pipeline cache initialized from 100 bytes of persisted data."
  };
  // Every existing boundary survives as a milestone while raw notice
  // admission remains unchanged. A clock starting at zero is a real window.
  for (const char* line : boundaries) {
    assert(RPCS3PipelineCacheBoundary(line));
    assert(!permitLog(6, line));
  }
  assert(milestones == 14);
  assert(!permitLog(6, boundaries[0]));
  assert(!permitLog(6, boundaries[0]));
  assert(milestones == 16);
  for (unsigned i = 0; i < 100; ++i) assert(!permitLog(6, boundaries[0]));
  assert(milestones == 16);
  testNow = 0.999;
  assert(!permitLog(6, boundaries[0]));
  assert(milestones == 16);
  testNow = 1.0;
  assert(!permitLog(6, boundaries[0]));
  assert(milestones == 17);

  for (const char* line : {"Vulkan driver pipeline cacheable entry", "Vulkan driver rejected an unrelated allocation",
                           "LLVM: Compiling module", "COREPROF frames=0", "SAVESTATE_RESTORE phase=tar_begin"}) {
    assert(!RPCS3PipelineCacheBoundary(line));
  }
  // Cache notices do not spend the ordinary raw/error budget, and the
  // profiler and existing milestone tokens retain their old raw admission.
  for (unsigned i = 0; i < 128; ++i) assert(permitLog(2, "ordinary error"));
  assert(!permitLog(2, "ordinary error"));
  assert(permitLog(6, "COREPROF frames=0"));
  assert(permitLog(6, "JITPROF_BOOT session=2"));
  assert(permitLog(6, "SAVESTATE_RESTORE phase=tar_begin"));
  assert(!permitLog(6, "ordinary notice"));

  // A fresh group of simultaneous callback writers shares one cap, with
  // no duplicate allowance from a race or repeated boot initialization.
  testNow = 2.0;
  const unsigned before = milestones;
  std::vector<std::thread> threads;
  for (unsigned t = 0; t < 32; ++t) threads.emplace_back([&] {
    for (unsigned i = 0; i < 100; ++i) assert(!permitLog(6, boundaries[i % 14]));
  });
  for (auto& thread : threads) thread.join();
  assert(milestones == before + 16);
  testNow = 2.999;
  assert(!RPCS3AdmitPipelineCacheMilestone());
  testNow = 3.0;
  assert(RPCS3AdmitPipelineCacheMilestone());
}
'''
compiler = shutil.which('clang++') or shutil.which('g++')
if compiler is None:
    raise SystemExit('A C++ compiler is required')
with tempfile.TemporaryDirectory(prefix='rpcs3-pipeline-cache-milestones-') as directory:
    cpp = Path(directory) / 'test.cpp'
    binary = Path(directory) / 'test'
    cpp.write_text(source)
    subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-pthread', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('PASS: 14 native cache boundaries, independent 16/s cap, notice routing, raw128 budget and 32 concurrent writers (portable mutex/clock shim).')
