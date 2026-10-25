#import <Foundation/Foundation.h>
#include <cassert>
#include <cstdio>

#import "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h"

// CELL546 scenarios on the actual Foundation logger. CELL546_CONTROL builds the
// milestone scenario alone against the 545 logger, which truncated to zero.

static NSArray<NSDictionary*>* readEntries(NSString* path) {
  NSString* data = [NSString stringWithContentsOfFile:path
      encoding:NSUTF8StringEncoding error:nil];
  if (!data) return @[];
  assert([data hasSuffix:@"\n"]);
  NSMutableArray* entries = [NSMutableArray new];
  for (NSString* line in [data componentsSeparatedByString:@"\n"]) {
    if (line.length == 0) continue;
    NSDictionary* entry = [NSJSONSerialization JSONObjectWithData:
        [line dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    assert([entry isKindOfClass:NSDictionary.class]);
    [entries addObject:entry];
  }
  return entries;
}

static bool near(double a, double b) { return a - b < 1e-6 && b - a < 1e-6; }

static unsigned long long fileSize(NSString* path) {
  return [[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil] fileSize];
}

int main(int argc, const char* argv[]) {
  @autoreleasepool {
    assert(argc == 2);
    NSString* directory = [NSString stringWithUTF8String:argv[1]];
    RPCS3DiagnosticsSetDirectoryForTesting(directory);
    NSString* (^at)(NSString*) = ^(NSString* name) { return [directory stringByAppendingPathComponent:name]; };
    NSString* pad = [@"m" stringByPaddingToLength:900 withString:@"m" startingAtIndex:0];

    // 1. Milestones: an earlier process's boot facts survive a later restore
    // that writes more than 512 KiB (build 541 truncated the file to zero).
    RPCS3Milestone(@"config_layers", @"CONFIG_LAYERS title=BCES00510 marker=earlier_process");
    for (unsigned i = 0; i < 700; ++i)
      RPCS3Milestone(@"savestate_restore", [NSString stringWithFormat:@"SAVESTATE_RESTORE phase=step index=%u %@", i, pad]);
    NSString* milestones = at(@"RPCS3-milestones.log");
    NSString* previousMilestones = at(@"RPCS3-milestones.1.log");
    assert(fileSize(milestones) <= 512 * 1024);
    NSArray* current = readEntries(milestones);
    NSArray* previous = readEntries(previousMilestones);
    std::printf("milestones current=%lu previous=%lu\n", (unsigned long)current.count, (unsigned long)previous.count);
    assert(previous.count > 0 && fileSize(previousMilestones) <= 512 * 1024);
    assert([previous.firstObject[@"message"] containsString:@"marker=earlier_process"]);
    assert([current.firstObject[@"stage"] isEqualToString:@"log_rotation"]);
    assert([current.firstObject[@"message"] containsString:@"kept_previous=1"]);
    assert([current.lastObject[@"message"] hasPrefix:@"SAVESTATE_RESTORE phase=step index=699 "]);
    // Nothing between the two generations is lost: 701 records plus the marker.
    assert(previous.count + current.count == 702);

#if !defined(CELL546_CONTROL)
    // 2. Restore steps: their own bounded file; ordinary logs are untouched.
    RPCS3Diagnostic(@"core_test", @"before_trace");
    RPCS3DiagnosticsFlushForTesting();
    const unsigned long long diagnosticBefore = fileSize(at(@"RPCS3-diagnostic.log"));
    const unsigned long long milestonesBefore = fileSize(milestones);
    NSString* step = [@"t" stringByPaddingToLength:1200 withString:@"t" startingAtIndex:0];
    for (unsigned i = 0; i < 1000; ++i)
      RPCS3RestoreTrace([NSString stringWithFormat:@"SAVESTATE_RESTORE phase=fxo_type_begin index=%u %@", i, step]);
    RPCS3DiagnosticsFlushForTesting();
    NSString* trace = at(@"RPCS3-restore-trace.log");
    NSString* previousTrace = at(@"RPCS3-restore-trace.1.log");
    assert(fileSize(trace) <= 1024 * 1024 && fileSize(previousTrace) <= 1024 * 1024);
    NSArray* traceRows = readEntries(trace);
    NSArray* previousTraceRows = readEntries(previousTrace);
    assert([traceRows.firstObject[@"stage"] isEqualToString:@"log_rotation"]);
    assert([previousTraceRows.firstObject[@"message"] hasPrefix:@"SAVESTATE_RESTORE phase=fxo_type_begin index=0 "]);
    assert([traceRows.lastObject[@"message"] hasPrefix:@"SAVESTATE_RESTORE phase=fxo_type_begin index=999 "]);
    assert(traceRows.count + previousTraceRows.count == 1001);
    assert([previousTraceRows.firstObject[@"stage"] isEqualToString:@"savestate_restore_trace"]);
    assert(fileSize(at(@"RPCS3-diagnostic.log")) == diagnosticBefore);
    assert(fileSize(milestones) == milestonesBefore);
    // An export that moves the file is detected; the next step reopens the path.
    assert([NSFileManager.defaultManager moveItemAtPath:trace toPath:[trace stringByAppendingString:@".exported"] error:nil]);
    RPCS3RestoreTrace(@"SAVESTATE_RESTORE phase=fs_stage stage=name_ready");
    assert(readEntries(trace).count == 1);

    // 3. Compact timeline: one row per Core window from the profiler families.
    NSArray<NSString*>* window = @[
      @"TID: 7: COREPROF FRAMEPROF527 session=4 window=21 phase=guest_unclassified intervals=87 median_ms=29.410 p95_ms=33.269 p99_ms=2536.533 max_ms=2536.533 over50ms=1 over100ms=1 window_ms=5029.221",
      @"TID: 7: COREPROF VDECIO528 session=4 window=21 demand_reads=0 demand_read_max_us=0 prefetch_hits=0",
      @"TID: 7: COREPROF SHADERCFG536 session=4 window=21 configured=0 applied=0 fallback=0",
      @"TID: 7: COREPROF SHADERCOST534 session=4 window=21 tuple=count:total_us:max_us source=13:27959:3486 module=13:236:33 graphics=15:2474657:540573 compute=0:0:0",
      @"TID: 7: COREPROF SHADERSTALL538 session=4 window=21 captured=1 retained=2 dropped=0 capacity=32 threshold_us=50000",
      @"TID: 7: COREPROF SHADERSTALL538_EVENT stage=2 begin_us=1 end_us=540574 duration_us=540573 report_session=4 report_window=21",
      @"TID: 7: COREPROF SHADERSTALL538_EVENT stage=2 begin_us=540575 end_us=945844 duration_us=405269 report_session=4 report_window=21",
      @"TID: 7: COREPROF WAITPROF527 session=4 window=21 cpu_gpu_fence=148:507.763:11.869 vm_range_episode=125:6.736:0.885",
      @"TID: 7: COREPROF MEMPROF527 session=4 window=21 footprint=2171016800 peak_footprint=2171180640 compressed=978026496",
      @"TID: 7: COREPROF PRESSURE547 session=4 window=21 tuple=count:total_ms:max_ms blocking_builds=15:2474.657:540.573 spu_passive_waits=812 fence_spin_completed=3 fence_blocked=145:503.112:11.802 fence_spin_limit_us=100 scope=process_window",
      @"TID: 7: JITPROF session=4 ppu_codegen=1:6927.308:6927.308:0 ppu_cache_write=1:3578.573:3578.573:6665088",
      @"TID: 7: RANGELOCKPROF session=4 episodes=125 total_ms=6.736 max_ms=0.885 wl_putllc=40603:8.242:0.259",
      @"TID: 7: COREPROF_RESILIENCE memory_pressure_peak=0 memory_reclaims=0 shader_cache_misses=15",
      @"LOG_BUDGET dropped=7 limit_per_s=128",
    ];
    for (NSString* line in window) RPCS3Diagnostic(@"core_log", line);
    RPCS3Diagnostic(@"performance_sample", @"title=BLES01658 fps=35.11 available=4950026704 thermal=1 swap_attempts=355 swap_successes=83 swap_failures=272");
    RPCS3Diagnostic(@"performance_sample", @"title=BLES01658 fps=0.39 available=4900000000 thermal=2 swap_attempts=356 swap_successes=84 swap_failures=272");
    RPCS3Diagnostic(@"core_log", @"TID: 7: COREPROF frames=87 avg_fps=17.227 low1_fps=0.394 frametime_ms=58.048 p95_ms=33.270 p99_ms=2536.533 ppu_ms=7.324 spu_ms=51.564 rsx_ms=19.672 gpu_fence_wait_ms=5.836 memory_mib=2070 headroom_mib=4585 rsx_fifo_busy=73.6");
    // A window whose summary never arrived is exported incomplete.
    RPCS3Diagnostic(@"core_log", @"TID: 7: COREPROF FRAMEPROF527 session=4 window=22 intervals=0 max_ms=0");
    RPCS3Diagnostic(@"core_log", @"TID: 7: COREPROF FRAMEPROF527 session=4 window=23 intervals=1 max_ms=33.1");
    RPCS3Diagnostic(@"core_log", @"TID: 7: COREPROF frames=1 avg_fps=30.0");
    RPCS3DiagnosticsFlushForTesting();
    NSArray<NSDictionary*>* rows = readEntries(at(@"RPCS3-timeline.log"));
    assert(rows.count == 3);
    NSDictionary* row = rows[0];
    assert([row[@"complete"] isEqual:@YES] && [row[@"session"] intValue] == 4 && [row[@"window"] intValue] == 21);
    assert(near([row[@"frame_ms"][@"p99_ms"] doubleValue], 2536.533) && [row[@"frame_ms"][@"intervals"] intValue] == 87);
    assert([row[@"shader_cost_us"][@"graphics"] isEqualToString:@"15:2474657:540573"]);
    assert([row[@"shader_stall_events"][@"count"] intValue] == 2);
    assert([row[@"shader_stall_events"][@"max_us"] intValue] == 540573);
    assert([row[@"shader_stall_events"][@"total_us"] intValue] == 945842);
    assert([row[@"shader_stall_events"][@"stages"] isEqualToString:@"2:2"]);
    assert([row[@"wait_ms"][@"cpu_gpu_fence"] isEqualToString:@"148:507.763:11.869"]);
    assert([row[@"jit"][@"ppu_cache_write"] isEqualToString:@"1:3578.573:3578.573:6665088"]);
    assert([row[@"memory_bytes"][@"footprint"] longLongValue] == 2171016800LL);
    assert([row[@"pressure"][@"blocking_builds"] isEqualToString:@"15:2474.657:540.573"]);
    assert([row[@"pressure"][@"spu_passive_waits"] intValue] == 812 && [row[@"pressure"][@"fence_spin_completed"] intValue] == 3);
    assert([row[@"pressure"][@"fence_blocked"] isEqualToString:@"145:503.112:11.802"]);
    assert(near([row[@"summary"][@"avg_fps"] doubleValue], 17.227) && near([row[@"summary"][@"spu_ms"] doubleValue], 51.564));
    assert([row[@"host"][@"samples"] intValue] == 2 && near([row[@"host"][@"fps_min"] doubleValue], 0.39));
    assert([row[@"host"][@"available_min_bytes"] longLongValue] == 4900000000LL && [row[@"host"][@"thermal_max"] intValue] == 2);
    assert([row[@"host"][@"swap_process_lifetime"][@"swap_successes"] intValue] == 84);
    assert([row[@"lost"][@"log_budget_dropped"] intValue] == 7);
    assert([row[@"lost"][@"rotations"] containsString:@"milestones=1 restore_trace=1"]);
    assert([row[@"scope"] isEqualToString:@"core_report_window_values_not_additive"]);
    assert([rows[1][@"complete"] isEqual:@NO] && [rows[1][@"window"] intValue] == 22);
    assert([rows[1][@"lost"][@"log_budget_dropped"] intValue] == 0);
    assert([rows[2][@"complete"] isEqual:@YES] && [rows[2][@"window"] intValue] == 23);
    std::printf("timeline row bytes=%lu\n", (unsigned long)[NSJSONSerialization dataWithJSONObject:row options:0 error:nil].length);
#endif
  }
  return 0;
}
