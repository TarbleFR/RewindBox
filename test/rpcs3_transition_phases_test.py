#!/usr/bin/env python3
"""REWINDBOX_TRANSITION_PHASES_609: bounded Core lines that separate the seven phases of a SELF transition.

The BO2 multiplayer entry (internal exitspawn to t6mp_ps3f.self) still freezes
on delivered 608, and the existing journals cannot separate: (1) the old
process stop on UIKit, (2-4) BootGame on the reboot worker, (5) the RPCS3
pipeline warmup, (6) RunPPU through UIKit up to the running state and (7) the
first guest flip. This test checks, without a device:

1. Source contract: every new format string exists exactly once in the
   candidate Core and not in the delivered tree; the stop_main line is written
   on the worker after the UIKit hand-off returns, RunPPU (UIKit) stores only a
   timestamp, and the running line is skipped outside emulator threads.
2. Routing: the host bridge predicates of the delivered application (extracted
   verbatim from Rpcs3InternalBridgePlugin.mm and Rpcs3Diagnostics.mm, compiled
   as plain C++) admit each exact line, with its channel prefix, to the stated
   journal and to no cause or timeline history.

No game, UIKit, Metal or iPhone executes here; ordering on the device is
verified by the next journal itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
DIAG = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm'
FORMATS = {
    'rpcs3/Emu/Cell/lv2/sys_process.cpp': ['COREPROF EXITSPAWN phase=request scheduled=%u generation=%llu emulation_id=%llu target=%s'],
    'rpcs3/ios/RPCS3IOS.cpp': ['COREPROF EXITSPAWN phase=stop_main executed=%u failure=%u ui_wait_ms=%.3f generation=%llu emulation_id=%llu',
                               'COREPROF EXITSPAWN phase=boot_begin generation=%llu emulation_id=%llu',
                               'COREPROF EXITSPAWN phase=boot_return raw_state=%u boot_ms=%.3f'],
    'rpcs3/Emu/RSX/rsx_cache.h': ['COREPROF SHADERWARMUP phase=begin entries=%u workers=%u',
                                  'COREPROF SHADERWARMUP phase=end entries=%u valid=%u preload_ms=%.3f compile_ms=%.3f stopped=%u',
                                  'COREPROF SHADERWARMUP phase=end entries=0 reason=disabled'],
    'rpcs3/Emu/RSX/VK/vkutils/device.cpp': ['Vulkan driver pipeline cache: save skipped (reason=%s, no library added).',
                                            'Vulkan driver pipeline cache: save started (reason=%s, unsaved=%llu).',
                                            'Vulkan driver pipeline cache: save returned after %llu ms (reason=%s, bytes=%llu, result=%s).'],
    'rpcs3/Emu/RSX/RSXThread.cpp': ['COREPROF RUNPPU phase=dispatch starting=%u raw_state=%u'],
    'rpcs3/Emu/System.cpp': ['COREPROF RUNPPU phase=running raw_state=%u since_dispatch_ms=%.3f ui_latency_ms=%.3f since_main_ms=%.3f restore=%u'],
    'rpcs3/ios/RPCS3IOSPerformance.cpp': ['COREPROF FIRSTFLIP session=%llu'],
}
# Exact lines as the host receives them (logs::level notice = 6, "channel: " prefix).
LINES = [
    ('sys_process: COREPROF EXITSPAWN phase=request scheduled=1 generation=3 emulation_id=7 target=t6mp_ps3f.self', 'profiler'),
    ('COREPROF EXITSPAWN phase=stop_main executed=1 failure=0 ui_wait_ms=812.125 generation=3 emulation_id=7', 'profiler'),
    ('COREPROF EXITSPAWN phase=boot_begin generation=3 emulation_id=8', 'profiler'),
    ('COREPROF EXITSPAWN phase=boot_return raw_state=7 boot_ms=4210.000', 'profiler'),
    ('RSX: COREPROF SHADERWARMUP phase=begin entries=4100 workers=6', 'profiler'),
    ('RSX: COREPROF SHADERWARMUP phase=end entries=4100 valid=4098 preload_ms=1200.000 compile_ms=88000.000 stopped=0', 'profiler'),
    ('RSX: COREPROF SHADERWARMUP phase=end entries=0 reason=empty', 'profiler'),
    ('RSX: Vulkan driver pipeline cache: save started (reason=checkpoint, unsaved=3).', 'milestone'),
    ('RSX: Vulkan driver pipeline cache: save returned after 2100 ms (reason=teardown, bytes=104857600, result=saved).', 'milestone'),
    ('RSX: Vulkan driver pipeline cache: save skipped (reason=checkpoint, no library added).', 'milestone'),
    ('RSX: COREPROF RUNPPU phase=dispatch starting=1 raw_state=7', 'profiler'),
    ('SYS: COREPROF RUNPPU phase=running raw_state=3 since_dispatch_ms=9000.000 ui_latency_ms=3.000 since_main_ms=8997.000 restore=0', 'profiler'),
    ('iOS Core Profiler: COREPROF FIRSTFLIP session=4', 'profiler'),
    ('iOS Experimental: Resolved boot policy: swap=1 restart=1 precomputed=1 position_invariance=1 mvk_async=1', 'boot_policy'),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def body(src: str, signature: str) -> str:
    start = src.index(signature)
    brace = src.index('{', start)
    depth = 0
    for i in range(brace, len(src)):
        depth += (src[i] == '{') - (src[i] == '}')
        if depth == 0:
            return src[start:i + 1]
    raise AssertionError('unterminated ' + signature)


def source_contract(source: Path, baseline: Path) -> dict:
    found = {}
    for rel, formats in FORMATS.items():
        text, old = (source / rel).read_text(), (baseline / rel).read_text()
        for fmt in formats:
            if text.count(fmt) != 1 or fmt in old:
                raise AssertionError(f'{rel}: format must be new and unique: {fmt}')
        found[rel] = sha((source / rel).read_bytes())
    ios = (source / 'rpcs3/ios/RPCS3IOS.cpp').read_text()
    stop = body(ios, 'bool schedule_continuous_stop(std::shared_ptr<continuous_stop_request> request) noexcept')
    ui = stop[stop.index('Emu.GetCallbacks().call_from_main_thread([&]'):stop.index('}, nullptr);')]
    if 'COREPROF' in ui or 'emit_log' in ui:
        raise AssertionError('a transition line is written from the UIKit lambda')
    if stop.index('completed_cv.wait(lock, [&] { return completed; });') > stop.index('COREPROF EXITSPAWN phase=stop_main'):
        raise AssertionError('stop_main is not written after the UIKit hand-off returns')
    system = (source / 'rpcs3/Emu/System.cpp').read_text()
    run_ppu = body(system, 'void Emulator::RunPPU()')
    if 'COREPROF' in run_ppu or 'runppu_main_us.store(get_system_time()' not in run_ppu:
        raise AssertionError('RunPPU (UIKit) must only store its timestamp')
    finalize = body(system, 'void Emulator::FinalizeRunRequest()')
    if 'if (thread_ctrl::get_current())' not in finalize[finalize.index('REWINDBOX_TRANSITION_PHASES_609'):]:
        raise AssertionError('the running line is not restricted to emulator threads')
    return {'files_sha256': found, 'stop_main_after_ui_handoff': True, 'run_ppu_ui_store_only': True}


def routing(work: Path) -> dict:
    bridge, diag = BRIDGE.read_text(), DIAG.read_text()
    log_fn = body(bridge, 'static void RPCS3Log(void* context, int32_t level, const char* message)')
    profiler = re.search(r'const BOOL profiler =(.*?);\n', log_fn, re.S).group(1)
    video = re.search(r'const BOOL videoArchive = (.*?);\n', log_fn, re.S).group(1)
    literal = re.findall(r'strstr\(message, "([^"]+)"\) != nullptr\) \{\n\s+RPCS3Milestone\(@"([a-z0-9_]+)"', log_fn)
    runtime = re.findall(r'@"((?:[^"\\]|\\.)*)"', body(diag, 'static BOOL RPCS3KeepRuntimeHistory(NSString* message)'))
    timeline = re.findall(r'(?:strstr\(line, |RPCS3CauseToken\(line, )"([^"]+)"', body(diag, '- (void)observeTimelineStage:(NSString*)stage'))
    code = ['#include <cstdio>\n#include <cstring>\n#include <cstdint>\n#include <string>\n#include <vector>\n'
            'using BOOL = bool;\n#define YES true\n#define NO false\n',
            body(bridge, 'static BOOL RPCS3PipelineCacheBoundary(const char* message)'),
            body(bridge, 'static const char* RPCS3Build487MilestoneStage(const char* message)'),
            body(bridge, 'static BOOL RPCS3RestoreTraceDetail(const char* message)'),
            body(diag, 'static bool RPCS3CauseToken(const char* message, const char* token) noexcept'),
            body(diag, 'static bool RPCS3KeepCauseHistory(const char* message) noexcept'),
            'static bool profiler_line(const char* message) { return' + profiler + '; }',
            'static bool video_line(const char* message) { return ' + video + '; }',
            'static const std::vector<std::pair<const char*, const char*>> kLiteral = {' +
            ''.join('{"%s","%s"},' % (n.replace('"', '\\"'), m) for n, m in literal) + '};',
            'static const std::vector<const char*> kRuntime = {' + ''.join('"%s",' % t for t in runtime) + '};',
            'static const std::vector<const char*> kTimeline = {' + ''.join('"%s",' % t for t in timeline) + '};',
            r'''
static std::string route(int level, const char* m) {
  std::string r; bool milestone = false;
  for (auto& p : kLiteral) if (strstr(m, p.first)) { r += std::string("milestone:") + p.second + " "; milestone = true; break; }
  if (!milestone) {
    if (RPCS3RestoreTraceDetail(m)) return "restore-trace-only";
    else if (RPCS3PipelineCacheBoundary(m)) r += "milestone:vk_pipeline_cache ";
    else if (const char* s = RPCS3Build487MilestoneStage(m)) r += std::string("milestone:") + s + " ";
  }
  const bool prof = profiler_line(m), vid = video_line(m);
  if (level > 2 && !prof && !vid) return r;
  r += prof ? "diagnostic:profiler " : "diagnostic:budget ";
  for (auto t : kRuntime) if (strstr(m, t)) { r += "performance "; break; }
  if (RPCS3KeepCauseHistory(m)) r += "causes ";
  for (auto t : kTimeline) if (strstr(m, t)) { r += "timeline "; break; }
  return r;
}
int main(int c, char** v) { for (int i = 1; i < c; ++i) std::printf("%s\n", route(6, v[i]).c_str()); }
''']
    cpp = work / 'routing.cpp'
    cpp.write_text('\n'.join(code))
    subprocess.run(['g++', '-std=c++20', '-O1', str(cpp), '-o', str(work / 'routing')], check=True)
    out = subprocess.run([str(work / 'routing'), *[line for line, _ in LINES]], check=True,
                         capture_output=True, text=True).stdout.splitlines()
    result = {}
    for (line, kind), route in zip(LINES, out):
        if 'causes' in route or 'timeline' in route:
            raise AssertionError('unexpected history side effect: ' + line)
        expected = {'profiler': route == 'diagnostic:profiler performance ',
                    'milestone': route == 'milestone:vk_pipeline_cache ',
                    'boot_policy': route == 'milestone:boot_policy '}[kind]
        if not expected:
            raise AssertionError(f'{line!r} routed to {route!r}')
        result[line] = route.strip()
    return {'bridge_sha256': sha(BRIDGE.read_bytes()), 'diagnostics_sha256': sha(DIAG.read_bytes()), 'routes': result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='materialized candidate Core')
    parser.add_argument('--baseline', type=Path, required=True, help='materialized delivered Core')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'schema': 1, 'source_contract': source_contract(args.source, args.baseline)}
    with tempfile.TemporaryDirectory(prefix='rpcs3-phases-') as temp:
        report['routing'] = routing(Path(temp))
    report.update(result='passed', host_build_required=False, physicalDeviceTested=False,
                  limits=['Thread ordering and timings are observed only in the next device journal.'])
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
