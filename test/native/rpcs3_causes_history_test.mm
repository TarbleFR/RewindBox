// New causal history/timeline scenarios only. Requires actual macOS Foundation.
#import <Foundation/Foundation.h>
#import "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h"
#include <cassert>
#include <cstdio>

static NSArray<NSDictionary*>* entries(NSString* path) {
  NSString* text = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];
  if (!text) return @[];
  assert([text hasSuffix:@"\n"]);
  NSMutableArray* result = [NSMutableArray new];
  for (NSString* line in [text componentsSeparatedByString:@"\n"]) {
    if (!line.length) continue;
    NSDictionary* value = [NSJSONSerialization JSONObjectWithData:
        [line dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    assert([value isKindOfClass:NSDictionary.class]);
    [result addObject:value];
  }
  return result;
}

static NSDictionary* withMessage(NSArray<NSDictionary*>* rows, NSString* message) {
  NSDictionary* found = nil;
  for (NSDictionary* row in rows) if ([row[@"message"] isEqualToString:message]) {
    assert(!found); found = row;
  }
  assert(found);
  return found;
}

static unsigned long long sizeOf(NSString* path) {
  return [[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil] fileSize];
}

int main(int argc, const char* argv[]) {
  @autoreleasepool {
    assert(argc == 2);
    NSString* directory = [NSString stringWithUTF8String:argv[1]];
    RPCS3DiagnosticsSetDirectoryForTesting(directory);
    NSString* (^path)(NSString*) = ^(NSString* name) { return [directory stringByAppendingPathComponent:name]; };
    NSString* current = path(@"RPCS3-causes.log");
    NSString* previous = path(@"RPCS3-causes.1.log");
    RPCS3Milestone(@"game_boot_begin", @"BLES01717");
    RPCS3Diagnostic(@"core_log", @"CONFIG_LAYERS title=BLES01717 database=1 shader_mode=Async");
    RPCS3Diagnostic(@"core_log", @"JITPROF_BOOT session=7 boot_kind=normal part=ppu");
    NSString* frame = @"COREPROF FRAMEPROF527 session=7 window=2 phase=guest_unclassified intervals=13 median_ms=16.6 p95_ms=18.0 p99_ms=19.0 max_ms=19.0 over50ms=0 over100ms=0 window_ms=5078.760 total_interval_ms=215.742 window_guest_flips=13 wall_guest_fps=2.559 completed_interval_fps=60.257 last_guest_flip_age_ms=4800.0 guest_progress_boundary_approximate=1";
    NSString* extra = [@"x" stringByPaddingToLength:12000 withString:@"x" startingAtIndex:0];
    NSString* event = [NSString stringWithFormat:@"COREPROF FRAMECAUSE_EVENT session=7 window=2 seq=18 t_us=42 elapsed_us=60001 opaque=%@", extra];
    NSArray<NSString*>* causal = @[
      frame,
      @"COREPROF FRAMECAUSE session=7 window=2 captured=1 frames=13 slow=2 sampled=1 retained=3 unretained=0 contended=0 threshold_us=50000 capacity=16",
      event,
      @"COREPROF RENDERCAUSE session=7 window=2 captured=1 retained=4 vertex_range=1 sampler_refresh=2 sampler_cyclic_fast=1 dropped=0 contended=0",
      @"COREPROF RENDERCAUSE_EVENT session=7 window=2 draw=18 old=0x60300510 new=0x60301000 raw_future_field=complete",
      @"COREPROF SIGNALCAUSE session=7 window=2 enabled=1 watch_valid=1 watch_active=1 watch_stalled=1 acquire=18 address=0x60300510 expected=0x1A24 observed=0x1A23 events_dropped=2 history_overwritten=3 stale_session_dropped=0 producer_dropped=0 producer_replaced=1 read_busy=0 stalls_total=1 stall_latched=1 stall_overwritten=0 stall_dropped=0 dump=1 coverage=rsx_cpu_label_and_spu_put_copy excluded=ppu_direct_gpu_commit_reservation_store",
      @"COREPROF SIGNALCAUSE_EVENT session=7 seq=4 pc=0xB710 value=0x1A23 command=0x20",
      @"COREPROF SIGNALCAUSE_PRODUCER session=7 id=3 serial=9 phase=wait command=0x20",
      @"RSX_ACQUIRE waiting_after_recovery address=0x60300510 expected=0x1A24 observed=0x1A23 waited_us=2001715",
      @"FREEZE_DUMP snapshot\nRSX acquire=0x60300510 expected=0x1A24 observed=0x1A23\nSPU id=3 pc=0xB710 state=wait\n",
    ];
    for (NSString* message in causal) RPCS3Diagnostic(@"core_log", message);
    RPCS3Diagnostic(@"core_log", @"COREPROF frames=13 avg_fps=60.257 wall_guest_fps=2.559 last_guest_flip_age_ms=4800.0 avg_fps_scope=completed_present_intervals");
    RPCS3Milestone(@"game_boot_return", @"BLES01717 status=0");
    RPCS3DiagnosticsFlushForTesting();
    NSArray<NSDictionary*>* retained = entries(current);
    assert(retained.count == causal.count + 4);
    NSArray<NSDictionary*>* diagnostic = entries(path(@"RPCS3-diagnostic.log"));
    for (NSString* message in causal) {
      NSDictionary* cause = withMessage(retained, message);
      NSDictionary* original = withMessage(diagnostic, message);
      assert([cause[@"title"] isEqualToString:@"BLES01717"]);
      assert([cause[@"session"] intValue] == 7 && [cause[@"boot_kind"] isEqualToString:@"normal"]);
      for (NSString* key in @[@"message", @"stage", @"pid", @"build", @"timestamp",
                              @"clockMonotonicBeginUs", @"clockMonotonicEndUs", @"clockAnchorScope"])
        assert([cause[key] isEqual:original[key]]);
    }
    assert([withMessage(retained, event)[@"message"] length] == event.length);
    NSArray<NSDictionary*>* timeline = entries(path(@"RPCS3-timeline.log"));
    assert(timeline.count == 1);
    NSDictionary* row = timeline.firstObject;
    assert([row[@"frame_ms"][@"window_guest_flips"] intValue] == 13);
    assert([row[@"frame_ms"][@"wall_guest_fps"] doubleValue] < 3.0);
    assert([row[@"frame_ms"][@"completed_interval_fps"] doubleValue] > 60.0);
    assert([row[@"frame_ms"][@"last_guest_flip_age_ms"] doubleValue] == 4800.0);
    assert([row[@"frame_ms"][@"total_interval_ms"] doubleValue] > 215.7);
    assert([row[@"frame_ms"][@"guest_progress_boundary_approximate"] intValue] == 1);
    assert([row[@"summary"][@"avg_fps_scope"] isEqualToString:@"completed_present_intervals"]);
    assert([row[@"frame_cause"][@"retained"] intValue] == 3 && [row[@"render_cause"][@"retained"] intValue] == 4);
    assert(row[@"frame_cause"][@"seq"] == nil && row[@"render_cause"][@"draw"] == nil);
    assert([row[@"signal_cause"][@"watch_stalled"] intValue] == 1);
    assert([row[@"signal_cause"][@"events_dropped"] intValue] == 2 && [row[@"signal_cause"][@"history_overwritten"] intValue] == 3);
    assert([row[@"signal_cause"][@"address"] isEqualToString:@"0x60300510"]);
    assert([row[@"signal_cause"][@"coverage"] isEqualToString:@"rsx_cpu_label_and_spu_put_copy"]);
    assert([row[@"signal_cause"][@"excluded"] isEqualToString:@"ppu_direct_gpu_commit_reservation_store"]);
    assert(row[@"signal_cause"][@"pc"] == nil);

    // Ordinary profiler reports and per-operation poll/draw tokens cannot evict
    // these records from the cause channel even though they reach the journal.
    const auto originalSize = sizeOf(current);
    for (unsigned i = 0; i < 200; ++i) {
      RPCS3Diagnostic(@"core_log", @"COREPROF RENDERCAUSE_DRAW draw=100");
      RPCS3Diagnostic(@"core_log", @"COREPROF SIGNALCAUSE_POLL count=1000");
    }
    RPCS3Diagnostic(@"performance_sample", @"fps=30 available=4000000000 thermal=1");
    RPCS3DiagnosticsFlushForTesting();
    assert(sizeOf(current) == originalSize);

    // Seed valid prior history near the actual 4 MiB bound; one real snapshot
    // then rotates it. This fixture does not claim a gameplay retention time.
    constexpr unsigned long long limit = 4 * 1024 * 1024;
    NSMutableData* filled = [[NSData dataWithContentsOfFile:current] mutableCopy];
    NSString* padding = [@"p" stringByPaddingToLength:4000 withString:@"p" startingAtIndex:0];
    NSMutableData* paddingRow = [[NSJSONSerialization dataWithJSONObject:
        @{@"fixture": @YES, @"message": padding} options:0 error:nil] mutableCopy];
    [paddingRow appendBytes:"\n" length:1];
    while (filled.length + paddingRow.length + 2048 < limit) [filled appendData:paddingRow];
    assert([filled writeToFile:current atomically:NO]);
    NSString* freeze = [@"FREEZE_DUMP snapshot\n" stringByAppendingString:
        [@"frame\n" stringByPaddingToLength:30000 withString:@"frame\n" startingAtIndex:0]];
    RPCS3Diagnostic(@"core_log", freeze);
    RPCS3DiagnosticsFlushForTesting();
    assert(sizeOf(current) <= limit && sizeOf(previous) <= limit);
    NSArray<NSDictionary*>* oldRows = entries(previous);
    NSArray<NSDictionary*>* newRows = entries(current);
    assert([oldRows.firstObject[@"stage"] isEqualToString:@"game_boot_begin"]);
    assert([oldRows.firstObject[@"title"] isEqualToString:@"BLES01717"]);
    assert([newRows.firstObject[@"stage"] isEqualToString:@"log_rotation"]);
    assert([newRows.firstObject[@"message"] containsString:@"kept_previous=1"]);
    assert([newRows.lastObject[@"message"] isEqualToString:freeze]);
    assert([newRows.lastObject[@"title"] isEqualToString:@"BLES01717"]);

    // The shared append path reopens correctly after exporting/moving the file.
    assert([NSFileManager.defaultManager moveItemAtPath:current toPath:[current stringByAppendingString:@".exported"] error:nil]);
    RPCS3Diagnostic(@"core_log", @"COREPROF SIGNALCAUSE_EVENT session=7 seq=19 value=0x1A24");
    assert(entries(current).count == 1);

    // A new boot must not inherit the previous title/session. An early acquire
    // before JITPROF_BOOT legitimately has no known session in the wrapper.
    RPCS3Milestone(@"game_boot_begin", @"BCES00510");
    RPCS3Diagnostic(@"core_log", @"CONFIG_LAYERS title=BCES00510 database=1");
    NSString* early = @"RSX_ACQUIRE waiting_after_recovery address=0x60300510 expected=2 observed=1 marker=before_session";
    RPCS3Diagnostic(@"core_log", early);
    NSDictionary* earlyRow = withMessage(entries(current), early);
    assert([earlyRow[@"title"] isEqualToString:@"BCES00510"] && earlyRow[@"session"] == nil && earlyRow[@"boot_kind"] == nil);
    RPCS3Diagnostic(@"core_log", @"JITPROF_BOOT session=8 boot_kind=savestate part=spu");
    RPCS3Diagnostic(@"core_log", @"COREPROF SIGNALCAUSE_EVENT session=8 seq=20 value=0x1A24");
    NSDictionary* last = entries(current).lastObject;
    assert([last[@"title"] isEqualToString:@"BCES00510"] && [last[@"session"] intValue] == 8);
    assert([last[@"boot_kind"] isEqualToString:@"savestate"]);
    std::printf("{\"passed\":true,\"causeMessagesChecked\":%lu,\"excludedPollDrawMessages\":400,\"rotation\":true,\"exportReopen\":true,\"newBootIdentity\":true}\n", (unsigned long)causal.count);
  }
  return 0;
}
