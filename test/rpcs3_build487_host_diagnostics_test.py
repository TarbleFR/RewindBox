#!/usr/bin/env python3
"""Build 487 host diagnostics (NEOSTATION_BUILD487_HOST_DIAGNOSTICS_V1): behaviour, not device proof.

1. The production log admission block of RPCS3Log (the same slice that
   test/rpcs3_build283_boot_stability_test.py executes) is compiled as plain C++
   and run: every Build 487 Core token (JITPROF, JITPROF_BOOT, CONFIG_LAYERS,
   NEOSTATION_RESTART, SAVESTATE_BOOT, FREEZE_DUMP, MUTEX_DESTROY_BUSY) passes at
   notice/warning level without consuming the ordinary budget; plain notices and
   look-alike prefixes are still dropped; the Build 283 budget is unchanged.
2. The milestone helpers (stage selection, mutex cap, text bound) are compiled
   with an Objective-C shim and run: exact stage names, only the FREEZE_DUMP
   "begin" line is mirrored, MUTEX_DESTROY_BUSY is capped at 64 per process.
3. Source contracts: performance_sample appends emu_state/boot_progress/
   guest_frames/native_ui, printed "-" without the Core validity bit; the
   change-only rule of neoswap_guest_sample_ext applies to the "sample" phase
   only; the diagnostic file rotates to RPCS3-diagnostic.1.log; the host ABI
   mirror of rpcs3_ios_performance_metrics has the Build 487 tail and bits.
   With --core <materialized Core tree> the mirror is compared field by field
   with rpcs3/ios/RPCS3IOS.h.

The rotation itself runs on Foundation in test/rpcs3_diagnostics_native_test.py
(macOS only). Nothing here is iPhone evidence.
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes'
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--core', type=Path, default=None, help='materialized RPCS3 Core tree (optional)')
args = parser.parse_args()

host = (CLASSES / 'Rpcs3InternalBridgePlugin.mm').read_text()
abi = (CLASSES / 'Rpcs3CoreABI.h').read_text()
diag = (CLASSES / 'Rpcs3Diagnostics.mm').read_text()
MARK = 'NEOSTATION_BUILD487_HOST_DIAGNOSTICS_V1'
TOKENS = ['JITPROF ', 'JITPROF_BOOT ', 'CONFIG_LAYERS ', 'NEOSTATION_RESTART ', 'SAVESTATE_BOOT ',
          'FREEZE_DUMP ', 'MUTEX_DESTROY_BUSY ', 'SAVESTATE_RESTORE ', 'RSX_ACQUIRE ']


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def compile_and_run(source: str, name: str, extra=()):
    compiler = shutil.which('clang++') or shutil.which('g++')
    require(compiler is not None, 'a C++ compiler is required')
    with tempfile.TemporaryDirectory(prefix='rpcs3-487-host-') as tmp:
        path = Path(tmp) / (name + '.cpp')
        binary = Path(tmp) / name
        path.write_text(source)
        subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', *extra, str(path), '-o', str(binary)],
                       check=True)
        subprocess.run([str(binary)], check=True)


for path, text in (('Rpcs3InternalBridgePlugin.mm', host), ('Rpcs3CoreABI.h', abi), ('Rpcs3Diagnostics.mm', diag)):
    require(MARK in text, f'{path} lacks {MARK}')

# --- 1. admission block -------------------------------------------------------
core_log = host.split('static void RPCS3Log(void* context, int32_t level, const char* message) {', 1)[1].split('\n}', 1)[0]
logic = core_log[core_log.index('  const BOOL profiler ='):core_log.index('  NSString* text =')]
for token in TOKENS:
    require(f'strstr(message, "{token}") != nullptr' in logic, f'admission does not whitelist {token!r}')
require('if (level > 2 && !profiler && !videoArchive) return;' in logic, 'Build 283 level filter changed')
logic = logic.replace('return;', 'return false;')
checks = '\n'.join(f'  assert(permitLog(6, "{t}x=1"));' for t in TOKENS)
compile_and_run(r'''
#include <cassert>
#include <cstdint>
#include <cstring>
using BOOL = bool;
constexpr BOOL YES = true, NO = false;
using CFTimeInterval = double;
using os_unfair_lock = int;
#define OS_UNFAIR_LOCK_INIT 0
static double testNow = 1.0;
static unsigned locks = 0;
double CACurrentMediaTime() { return testNow; }
void os_unfair_lock_lock(os_unfair_lock*) { ++locks; }
void os_unfair_lock_unlock(os_unfair_lock*) {}
bool permitLog(int32_t level, const char* message) {
''' + logic + r'''
  return true;
}
int main() {
''' + checks + r'''
  // Prefixed by the Core listener (thread prefix): still recognised.
  assert(permitLog(6, "PPU[0x1000000] main_thread: CONFIG_LAYERS title=BCES00510 database=1"));
  assert(permitLog(5, "SPU[0x2000004] Thread (x): MUTEX_DESTROY_BUSY mutex_id=0x1"));
  // Build 487 tokens bypass the ordinary budget like the profiler lines.
  assert(locks == 0);
  // Look-alikes and plain notices are still dropped.
  assert(!permitLog(6, "JITPROFILE detail"));
  assert(!permitLog(6, "CONFIG_LAYERSX"));
  assert(!permitLog(6, "FREEZE_DUMPING"));
  assert(!permitLog(6, "LLVM: Compiling module"));
  assert(!permitLog(3, "ordinary notice"));
  // The ordinary budget (Build 283) still applies to level <= 2 lines.
  for (unsigned i = 0; i < 128; ++i) assert(permitLog(2, "ordinary error"));
  assert(!permitLog(2, "ordinary error"));
  assert(permitLog(6, "JITPROF session=1"));
  return 0;
}
''', 'admission')

# --- 2. milestone helpers -----------------------------------------------------
def function(name: str) -> str:
    start = host.index(name)
    start = host.rindex('\nstatic ', 0, start) + 1
    end = host.index('\n}\n', start) + 3
    return host[start:end]

stage_fn = function('const char* RPCS3Build487MilestoneStage(const char* message)')
cap_fn = function('BOOL RPCS3Build487AdmitBoundedLine(const char* message)')
compile_and_run(r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
using BOOL = bool;
constexpr BOOL YES = true;
''' + stage_fn + cap_fn + r'''
static bool same(const char* a, const char* b) { return a && b && std::strcmp(a, b) == 0; }
int main() {
  assert(same(RPCS3Build487MilestoneStage("JITPROF_BOOT session=1 boot_kind=fresh"), "jitprof_boot"));
  assert(same(RPCS3Build487MilestoneStage("x: CONFIG_LAYERS title=A"), "config_layers"));
  assert(same(RPCS3Build487MilestoneStage("NEOSTATION_RESTART reason=savestate_create"), "internal_restart"));
  assert(same(RPCS3Build487MilestoneStage("SAVESTATE_BOOT title=A applied_patches=0"), "savestate_boot"));
  assert(same(RPCS3Build487MilestoneStage("FREEZE_DUMP begin dump=1 reason=no_frames"), "freeze_dump"));
  assert(same(RPCS3Build487MilestoneStage("MUTEX_DESTROY_BUSY mutex_id=0x1"), "mutex_destroy_busy"));
  assert(same(RPCS3Build487MilestoneStage("FREEZE_DUMP snapshot\nFREEZE_DUMP begin dump=1"), "freeze_snapshot"));
  assert(same(RPCS3Build487MilestoneStage("SAVESTATE_RESTORE phase=tar_begin"), "savestate_restore"));
  assert(same(RPCS3Build487MilestoneStage("RSX_ACQUIRE waiting_after_recovery"), "rsx_acquire"));
  // Individual legacy detail lines are not separate synchronous writes.
  assert(RPCS3Build487MilestoneStage("FREEZE_DUMP spu id=0x1") == nullptr);
  assert(RPCS3Build487MilestoneStage("FREEZE_DUMP end dump=1") == nullptr);
  assert(RPCS3Build487MilestoneStage("JITPROF session=3 ppu_translate=1:2:3:4") == nullptr);
  assert(RPCS3Build487MilestoneStage("COREPROF frames=0") == nullptr);
  // MUTEX_DESTROY_BUSY: 64 lines per process, other lines are never capped.
  for (int i = 0; i < 64; ++i) assert(RPCS3Build487AdmitBoundedLine("MUTEX_DESTROY_BUSY mutex_id=0x1"));
  assert(!RPCS3Build487AdmitBoundedLine("MUTEX_DESTROY_BUSY mutex_id=0x1"));
  for (int i = 0; i < 1000; ++i) assert(RPCS3Build487AdmitBoundedLine("CONFIG_LAYERS title=A"));
  return 0;
}
''', 'milestones')
require('RPCS3Build487MilestoneText(message)' in host and 'strstr(message, "FREEZE_DUMP begin ") != nullptr ? 512 : 1024' in host,
        'milestone text is not bounded (512 bytes for a legacy begin, 1 KiB otherwise)')
require('66 * 1024' in host, 'complete snapshot bound is missing')
mirror = core_log[:core_log.index('  const BOOL profiler =')]
require('else if (const char* stage = RPCS3Build487MilestoneStage(message))' in mirror,
        'Build 487 milestones must be mirrored before the admission block, like boot_policy')
require(mirror.index('RPCS3Build487AdmitBoundedLine(message)') < mirror.index('RPCS3Milestone(@(stage)'),
        'the mutex cap must apply before the milestone and the diagnostic line')

# --- 3. source contracts ------------------------------------------------------
require('process_resident=%llu emu_state=%@ boot_progress=%@ guest_frames=%@ native_ui=%@"' in host,
        'performance_sample does not append the four Build 487 fields')
for bit in ('rpcs3_ios_performance_state', 'rpcs3_ios_performance_boot_progress',
            'rpcs3_ios_performance_guest_frames', 'rpcs3_ios_performance_native_ui'):
    require(f'(metrics.valid_fields & {bit})' in host, f'{bit} is not checked before printing its field')
require('@"-"' in host and 'const uint64_t delta = total >= previous ? total - previous : total;' in host,
        'guest_frames must be a per-sample delta, restarted when the renderer is recreated')
require('_diagnosticGuestFramesKnown = NO;' in host, 'guest frame baseline is not reset when sampling starts')
for name in ('stopped', 'loading', 'ready', 'starting', 'running', 'paused', 'stopping'):
    require(f'return "{name}";' in host, f'emulation state name {name} missing')
require('if (strcmp(phase, "sample") == 0 && !RPCS3Build487AdmitGuestSampleExt(line, title, epoch)) return;' in host,
        'neoswap_guest_sample_ext change-only rule must apply to the sample phase only')
require('now - lastWrite >= 60.0' in host, 'neoswap_guest_sample_ext must still be written every 60 s')
require('rotateDiagnosticFileAtPath:path' in diag and '@".1.log"' in diag, 'diagnostic rotation keeps no previous file')
require(diag.index('rotateDiagnosticFileAtPath:path]') < diag.index('truncateFileAtOffset:0'),
        'in-place truncation must remain only the fallback of a failed rotation')
mirror_struct = abi.split('typedef struct rpcs3_ios_performance_metrics {', 1)[1].split('} rpcs3_ios_performance_metrics;', 1)[0]
fields = re.findall(r'^\s*(u?int\d+_t|double)\s+(\w+);', mirror_struct, re.M)
expected = [('uint32_t', 'size'), ('uint32_t', 'valid_fields'), ('double', 'frames_per_second'),
            ('double', 'cpu_usage_percent'), ('double', 'gpu_usage_percent'), ('uint64_t', 'memory_used_bytes'),
            ('uint64_t', 'memory_total_bytes'), ('uint64_t', 'guest_frames_presented'),
            ('uint32_t', 'native_ui_visible'), ('uint32_t', 'emulation_state'),
            ('uint32_t', 'boot_progress_completed'), ('uint32_t', 'boot_progress_total')]
require(fields == expected, 'host metrics mirror differs from the Build 487 contract: ' + str(fields))
for bit, value in (('guest_frames', 4), ('native_ui', 5), ('state', 6), ('boot_progress', 7)):
    require(f'rpcs3_ios_performance_{bit} = 1u << {value},' in abi, f'validity bit {bit} is not 1u << {value}')
compile_and_run(r'''
#include <cstddef>
#include <cstdint>
#include "Rpcs3CoreABI.h"
static_assert(offsetof(rpcs3_ios_performance_metrics, memory_total_bytes) == 40);
static_assert(offsetof(rpcs3_ios_performance_metrics, guest_frames_presented) == 48);
static_assert(offsetof(rpcs3_ios_performance_metrics, native_ui_visible) == 56);
static_assert(offsetof(rpcs3_ios_performance_metrics, boot_progress_total) == 68);
static_assert(sizeof(rpcs3_ios_performance_metrics) == 72);
int main() { return 0; }
''', 'abi-layout', extra=('-I' + str(CLASSES), '-Wno-unused-parameter'))

if args.core:
    freeze = (args.core / 'rpcs3/ios/RPCS3IOSFreezeDump.cpp').read_text()
    start = freeze.index('\tstd::string snapshot = "FREEZE_DUMP snapshot')
    snapshot = freeze[start:freeze.index('\n}', start)]
    compile_and_run(r'''
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
#include "RPCS3IOSProfilerHelpers.h"
using u32=unsigned int;
using u64=unsigned long long;
using rpcs3::ios::profiler::bound_line;
struct Log {
  unsigned calls=0;
  std::string message;
  void notice(const char*,const std::string& value){++calls;message=value;}
} ios_freeze_dump;
std::string rsx_line(){return "FREEZE_DUMP rsx " + std::string(1000,'r');}
namespace fmt {
template<class... T> void append(std::string& out,const char* format,T... args){
  char tail[256];int n=std::snprintf(tail,sizeof(tail),format,args...);
  assert(n>0 && n<256);out.append(tail,n);
}
}
void capture(std::size_t count){
  const u64 index=7;
  const u32 total_lines=count+3;
  struct {u32 truncated=0;} plan;
  std::string header="FREEZE_DUMP begin dump=7 " + std::string(1100,'h');
  std::vector<std::string> lines(count,std::string(1024,'p'));
''' + snapshot + r'''
}
int main(){
  for(auto count:{0u,1u,61u}){
    ios_freeze_dump={};capture(count);
    assert(ios_freeze_dump.calls==1);
    const auto& text=ios_freeze_dump.message;
    assert(text.starts_with("FREEZE_DUMP snapshot\nFREEZE_DUMP begin dump=7 "));
    assert(text.find("FREEZE_DUMP rsx ")!=std::string::npos);
    assert(text.find("FREEZE_DUMP end dump=7")!=std::string::npos);
    assert(text.size()<66*1024);
    assert(std::count(text.begin(),text.end(),'\n')==count+3);
  }
}
''', 'complete-freeze-snapshot', extra=('-I'+str(args.core / 'rpcs3/ios'),))
    core_header = (args.core / 'rpcs3/ios/RPCS3IOS.h').read_text()
    core_struct = core_header.split('typedef struct rpcs3_ios_performance_metrics', 1)[1].split('} rpcs3_ios_performance_metrics;', 1)[0]
    core_fields = re.findall(r'^\s*(u?int\d+_t|double)\s+(\w+);', core_struct, re.M)
    require([f for f in core_fields] == [('uint32_t', 'struct_size')] + expected[1:],
            'Core metrics struct differs from the host mirror: ' + str(core_fields))
    for bit, value in (('GUEST_FRAMES', 4), ('NATIVE_UI', 5), ('STATE', 6), ('BOOT_PROGRESS', 7)):
        require(f'RPCS3_IOS_PERFORMANCE_{bit}_VALID = 1u << {value}' in core_header, f'Core bit {bit} differs')
    exports = (args.core / 'rpcs3/ios/RPCS3IOS.exports').read_text().split()
    for name in re.findall(r'LOAD\("([^"]+)"', host):
        require('_' + name in exports, f'host loads {name} but the Core does not export it')
    print('PASS: host mirror equals the Core metrics struct and validity bits; every loaded symbol is exported')

print('PASS: Build 487 host diagnostics (admission, milestones and cap, sample fields, change-only NeoSwap line, rotation, ABI mirror)')
