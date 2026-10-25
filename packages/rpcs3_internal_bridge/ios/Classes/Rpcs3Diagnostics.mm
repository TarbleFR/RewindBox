#import "Rpcs3Diagnostics.h"

#import <Foundation/Foundation.h>
#include <sys/stat.h>
#include <unistd.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>

static const unsigned long long kRPCS3DiagnosticLimit = 2 * 1024 * 1024;
static const unsigned long long kRPCS3MilestoneLimit = 512 * 1024;
static const unsigned long long kRPCS3RuntimeHistoryLimit = 2 * 1024 * 1024;
// CELL546: one restore writes up to ~350 KiB of constructor/file stages.
static const unsigned long long kRPCS3RestoreTraceLimit = 1024 * 1024;
// CELL546: one compact row per Core report window (~5 s, ~1.9 KiB): each
// generation holds ~1100 windows (~90 min); with the previous one, ~3 h.
static const unsigned long long kRPCS3TimelineLimit = 2 * 1024 * 1024;
static uint64_t RPCS3MonotonicUs() {
  return std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}
// A separate bounded history excludes verbose restore-constructor traces.
// It shares the existing asynchronous diagnostics worker, not a guest thread.
static BOOL RPCS3KeepRuntimeHistory(NSString* message) {
  for (NSString* token in @[@"COREPROF ", @"SPUPROF ", @"JITPROF ",
      @"RANGELOCKPROF ", @"COREPROF_RESILIENCE ",
      @"JITPROF_BOOT ", @"CONFIG_LAYERS ", @"JITMEM ", @"NEOSWAP_VDEC ",
      @"FREEZE_DUMP snapshot\n", @"SAVESTATE_RESTORE phase=missing_resource ",
      @"SAVESTATE_RESTORE phase=fxo_resource_abort ",
      @"SAVESTATE_RESTORE phase=worker_exception", @"LOG_BUDGET "])
    if ([message rangeOfString:token].location != NSNotFound) return YES;
  return NO;
}

// CELL546: generations discarded by each bounded file since launch. A reader
// of the compact timeline sees how much history rotated away.
enum RPCS3LogFile : size_t {
  kRPCS3DiagnosticFile, kRPCS3PerformanceFile, kRPCS3MilestoneFile,
  kRPCS3RestoreTraceFile, kRPCS3TimelineFile, kRPCS3LogFileCount
};
static std::atomic<uint32_t> gRPCS3Rotations[kRPCS3LogFileCount];

// One previous generation; NO when the rename failed.
static BOOL RPCS3RotateLog(NSString* path) {
  NSFileManager* files = NSFileManager.defaultManager;
  NSString* previous = [[path stringByDeletingPathExtension]
      stringByAppendingString:@".1.log"];
  [files removeItemAtPath:previous error:nil];
  return [files moveItemAtPath:path toPath:previous error:nil];
}

static BOOL RPCS3HandleOwnsPath(NSFileHandle* handle, NSString* path) {
  if (!handle || path.length == 0) return NO;
  struct stat descriptorInfo = {};
  struct stat pathInfo = {};
  if (fstat(handle.fileDescriptor, &descriptorInfo) != 0 ||
      stat(path.fileSystemRepresentation, &pathInfo) != 0) {
    return NO;
  }
  return descriptorInfo.st_dev == pathInfo.st_dev &&
      descriptorInfo.st_ino == pathInfo.st_ino;
}

// Value of a `key=` token of a Core profiler line, at most 96 bytes.
static NSString* RPCS3TokenValue(const char* line, const char* key) {
  const size_t keyLength = strlen(key);
  for (const char* at = strstr(line, key); at; at = strstr(at + 1, key)) {
    if ((at == line || at[-1] == ' ') && at[keyLength] == '=') {
      const char* value = at + keyLength + 1;
      const size_t length = std::min<size_t>(strcspn(value, " \n"), 96);
      return [[NSString alloc] initWithBytes:value length:length encoding:NSUTF8StringEncoding];
    }
  }
  return nil;
}

// Plain decimal tokens become exact JSON numbers; tuples such as
// count:total:max and hexadecimal values stay text.
static id RPCS3TimelineValue(NSString* token) {
  if (token.length == 0 || token.length > 32) return token ?: @"";
  NSUInteger digits = 0, dots = 0;
  for (NSUInteger i = 0; i < token.length; ++i) {
    const unichar c = [token characterAtIndex:i];
    if (c >= '0' && c <= '9') ++digits;
    else if (c == '.') ++dots;
    else if (!(c == '-' && i == 0)) return token;
  }
  if (!digits || dots > 1 || [token characterAtIndex:token.length - 1] == '.') return token;
  NSDecimalNumber* number = [NSDecimalNumber decimalNumberWithString:token
      locale:@{NSLocaleDecimalSeparator: @"."}];
  return [number isEqualToNumber:NSDecimalNumber.notANumber] ? token : number;
}

static NSMutableDictionary* RPCS3TimelineFamily(const char* line, NSArray<NSString*>* keys) {
  NSMutableDictionary* family = [NSMutableDictionary new];
  for (NSString* key in keys) {
    if (NSString* value = RPCS3TokenValue(line, key.UTF8String)) family[key] = RPCS3TimelineValue(value);
  }
  return family;
}

@interface RPCS3DiagnosticsWriter : NSObject
- (void)writeDiagnosticStage:(nullable NSString*)stage
                      message:(nullable NSString*)message;
- (void)writeMilestoneStage:(nullable NSString*)stage
                     message:(nullable NSString*)message;
- (void)writeRestoreTrace:(nullable NSString*)message;
#if defined(RPCS3_DIAGNOSTICS_TESTING)
- (void)setDirectoryForTesting:(NSString*)directory;
- (void)flushForTesting;
#endif
@end

@implementation RPCS3DiagnosticsWriter {
  dispatch_queue_t _diagnosticQueue;
  NSObject* _milestoneLock;
  NSObject* _restoreTraceLock;
  NSString* _diagnosticPath;
  NSString* _milestonePath;
  NSString* _restoreTracePath;
  NSFileHandle* _diagnosticFile;
  unsigned long long _diagnosticLength;
  NSFileHandle* _restoreTraceFile;
  unsigned long long _restoreTraceLength;
  // CELL546 compact timeline, owned by the diagnostic queue.
  NSMutableDictionary* _timelineRow;
  NSMutableDictionary<NSString*, NSNumber*>* _timelineStallStages;
  unsigned long long _timelineStallEvents;
  unsigned long long _timelineStallTotalUs;
  unsigned long long _timelineStallMaxUs;
  unsigned long long _timelineLogDropped;
  unsigned long long _hostSamples;
  double _hostFpsMin;
  long long _hostAvailableMin;
  long long _hostThermalMax;
  NSDictionary* _hostSwap;
  NSDictionary* _hostNeoSwap;
#if defined(RPCS3_DIAGNOSTICS_TESTING)
  NSString* _testDirectory;
#endif
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _diagnosticQueue = dispatch_queue_create(
        "com.neogamelab.neostation.rpcs3.diagnostics",
        DISPATCH_QUEUE_SERIAL);
    dispatch_set_target_queue(
        _diagnosticQueue,
        dispatch_get_global_queue(QOS_CLASS_UTILITY, 0));
    _milestoneLock = [NSObject new];
    _restoreTraceLock = [NSObject new];
    [self resetTimelineAccumulators];
  }
  return self;
}

- (NSString*)documentsDirectory {
#if defined(RPCS3_DIAGNOSTICS_TESTING)
  if (_testDirectory.length > 0) return _testDirectory;
#endif
  NSString* documents = NSSearchPathForDirectoriesInDomains(
      NSDocumentDirectory, NSUserDomainMask, YES).firstObject ?: @"";
  if (documents.length == 0) return @"";
  NSString* diagnostics = [documents stringByAppendingPathComponent:@"Diagnostics"];
  [NSFileManager.defaultManager createDirectoryAtPath:diagnostics
                           withIntermediateDirectories:YES
                                            attributes:nil
                                                 error:nil];
  return diagnostics;
}

- (NSString*)diagnosticPath {
  if (_diagnosticPath.length == 0) {
    NSString* directory = [self documentsDirectory];
    _diagnosticPath = directory.length > 0
        ? [directory stringByAppendingPathComponent:@"RPCS3-diagnostic.log"]
        : @"";
  }
  return _diagnosticPath;
}

- (NSString*)milestonePath {
  if (_milestonePath.length == 0) {
    NSString* directory = [self documentsDirectory];
    _milestonePath = directory.length > 0
        ? [directory stringByAppendingPathComponent:@"RPCS3-milestones.log"]
        : @"";
  }
  return _milestonePath;
}

- (NSString*)restoreTracePath {
  if (_restoreTracePath.length == 0) {
    NSString* directory = [self documentsDirectory];
    _restoreTracePath = directory.length > 0
        ? [directory stringByAppendingPathComponent:@"RPCS3-restore-trace.log"]
        : @"";
  }
  return _restoreTracePath;
}

- (void)closeDiagnosticFile {
  @try {
    [_diagnosticFile closeFile];
  } @catch (__unused NSException* exception) {
  }
  _diagnosticFile = nil;
  _diagnosticLength = 0;
}

- (BOOL)diagnosticFileStillOwnsPath:(NSString*)path {
  return RPCS3HandleOwnsPath(_diagnosticFile, path);
}

- (BOOL)openDiagnosticFileAtPath:(NSString*)path {
  if (path.length == 0) return NO;
  if (_diagnosticFile && ![self diagnosticFileStillOwnsPath:path]) {
    [self closeDiagnosticFile];
  }
  if (_diagnosticFile) return YES;

  NSFileManager* files = NSFileManager.defaultManager;
  if (![files fileExistsAtPath:path] &&
      ![files createFileAtPath:path contents:nil attributes:nil]) {
    return NO;
  }
  _diagnosticFile = [NSFileHandle fileHandleForWritingAtPath:path];
  if (!_diagnosticFile) return NO;
  _diagnosticLength = [_diagnosticFile seekToEndOfFile];
  return YES;
}

// NEOSTATION_BUILD487_HOST_DIAGNOSTICS_V1 (D9): one previous generation.
// Returns NO when the rename fails; the caller then truncates in place as
// before, so the 2 MiB bound of the current file always holds.
- (BOOL)rotateDiagnosticFileAtPath:(NSString*)path {
  [self closeDiagnosticFile];
  const BOOL moved = RPCS3RotateLog(path);
  gRPCS3Rotations[kRPCS3DiagnosticFile].fetch_add(1, std::memory_order_relaxed);
  if (![self openDiagnosticFileAtPath:path]) return NO;
  return moved && self->_diagnosticLength == 0;
}

- (NSData*)lineForStage:(nullable NSString*)stage
                message:(nullable NSString*)message
              timestamp:(NSTimeInterval)timestamp
         monotonicBegin:(uint64_t)monotonicBegin
           monotonicEnd:(uint64_t)monotonicEnd {
  NSDictionary* entry = @{
    @"pid": @(getpid()),
    @"build": [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown",
    @"timestamp": @(timestamp),
    @"clockMonotonicBeginUs": @(monotonicBegin),
    @"clockMonotonicEndUs": @(monotonicEnd),
    @"clockAnchorScope": @"native_log_capture_not_file_write",
    @"stage": stage ?: @"",
    @"message": message ?: @"",
  };
  NSData* json = [NSJSONSerialization dataWithJSONObject:entry
                                                 options:0
                                                   error:nil];
  if (!json) return nil;
  NSMutableData* line = [json mutableCopy];
  [line appendBytes:"\n" length:1];
  return line;
}

// CELL546: first line of a generation started by rotation, so a reader knows
// where the previous one is and how many were discarded before it.
- (NSData*)rotationLineForFile:(NSString*)path rotated:(BOOL)rotated index:(RPCS3LogFile)index {
  const uint64_t now = RPCS3MonotonicUs();
  NSString* name = path.lastPathComponent;
  NSString* message = [NSString stringWithFormat:
      @"LOG_ROTATION file=%@ previous=%@ kept_previous=%d rotations=%u",
      name, [[name stringByDeletingPathExtension] stringByAppendingString:@".1.log"],
      rotated ? 1 : 0, gRPCS3Rotations[index].load(std::memory_order_relaxed)];
  return [self lineForStage:@"log_rotation"
                    message:message
                  timestamp:[NSDate.date timeIntervalSince1970]
             monotonicBegin:now
               monotonicEnd:now];
}

// Bounded append with one previous generation. No extra RAM cache, allocation
// reserve or synchronous flush.
- (void)appendLine:(NSData*)line
              name:(NSString*)name
             limit:(unsigned long long)limit
             index:(RPCS3LogFile)index {
  if (!line.length || line.length > limit) return;
  NSString* directory = [self documentsDirectory];
  if (!directory.length) return;
  NSString* path = [directory stringByAppendingPathComponent:name];
  NSFileManager* files = NSFileManager.defaultManager;
  unsigned long long size = [[files attributesOfItemAtPath:path error:nil] fileSize];
  NSData* marker = nil;
  if (size + line.length > limit) {
    const BOOL rotated = RPCS3RotateLog(path);
    if (!rotated) {
      // Rotation failure retains a bounded current file, as the main writer.
      NSFileHandle* old = [NSFileHandle fileHandleForWritingAtPath:path];
      [old truncateFileAtOffset:0]; [old closeFile];
    }
    gRPCS3Rotations[index].fetch_add(1, std::memory_order_relaxed);
    if (index == kRPCS3TimelineFile) marker = [self rotationLineForFile:path rotated:rotated index:index];
  }
  if (![files fileExistsAtPath:path]) [files createFileAtPath:path contents:nil attributes:nil];
  NSFileHandle* file = [NSFileHandle fileHandleForWritingAtPath:path];
  [file seekToEndOfFile];
  if (marker) [file writeData:marker];
  [file writeData:line]; [file closeFile];
}

- (void)writeRuntimeHistory:(NSData*)line {
  // The current plus one previous generation occupy at most 4 MiB on disk.
  [self appendLine:line name:@"RPCS3-performance.log"
             limit:kRPCS3RuntimeHistoryLimit index:kRPCS3PerformanceFile];
}

- (void)resetTimelineAccumulators {
  _timelineStallStages = [NSMutableDictionary new];
  _timelineStallEvents = _timelineStallTotalUs = _timelineStallMaxUs = 0;
  _timelineLogDropped = 0;
  _hostSamples = 0;
  _hostFpsMin = -1;
  _hostAvailableMin = -1;
  _hostThermalMax = -1;
}

- (NSMutableDictionary*)timelineRow {
  if (!_timelineRow) _timelineRow = [NSMutableDictionary new];
  return _timelineRow;
}

// CELL546: one JSON row per Core report window. Each family keeps the Core's
// own values and scope. Durations of different families overlap (shader
// builds happen inside frame intervals and waits; ppu_cache_write is part of
// ppu_codegen; JIT tuples are count:total_ms:max_ms:bytes) and are never added.
- (void)emitTimelineRowAt:(NSTimeInterval)timestamp complete:(BOOL)complete {
  NSMutableDictionary* row = _timelineRow;
  _timelineRow = nil;
  if (!row) return;
  row[@"pid"] = @(getpid());
  row[@"build"] = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown";
  row[@"timestamp"] = @(timestamp);
  row[@"complete"] = @(complete);
  NSMutableArray* stages = [NSMutableArray new];
  for (NSString* stage in [_timelineStallStages.allKeys sortedArrayUsingSelector:@selector(compare:)])
    [stages addObject:[NSString stringWithFormat:@"%@:%@", stage, _timelineStallStages[stage]]];
  row[@"shader_stall_events"] = @{
    @"count": @(_timelineStallEvents),
    @"total_us": @(_timelineStallTotalUs),
    @"max_us": @(_timelineStallMaxUs),
    @"stages": [stages componentsJoinedByString:@","],
    @"scope": @"retained_operations_over_threshold_may_overlap",
  };
  NSMutableDictionary* host = [@{@"samples": @(_hostSamples)} mutableCopy];
  if (_hostFpsMin >= 0) host[@"fps_min"] = @(_hostFpsMin);
  if (_hostAvailableMin >= 0) host[@"available_min_bytes"] = @(_hostAvailableMin);
  if (_hostThermalMax >= 0) host[@"thermal_max"] = @(_hostThermalMax);
  if (_hostSwap.count) host[@"swap_process_lifetime"] = _hostSwap;
  if (_hostNeoSwap.count) host[@"neoswap_process_lifetime"] = _hostNeoSwap;
  row[@"host"] = host;
  row[@"lost"] = @{
    @"log_budget_dropped": @(_timelineLogDropped),
    @"rotations": [NSString stringWithFormat:
        @"diagnostic=%u performance=%u milestones=%u restore_trace=%u timeline=%u",
        gRPCS3Rotations[kRPCS3DiagnosticFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3PerformanceFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3MilestoneFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3RestoreTraceFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3TimelineFile].load(std::memory_order_relaxed)],
  };
  row[@"scope"] = @"core_report_window_values_not_additive";
  [self resetTimelineAccumulators];
  NSData* json = [NSJSONSerialization dataWithJSONObject:row
                                                 options:NSJSONWritingSortedKeys
                                                   error:nil];
  if (!json || json.length > 16 * 1024) return;
  NSMutableData* line = [json mutableCopy];
  [line appendBytes:"\n" length:1];
  [self appendLine:line name:@"RPCS3-timeline.log" limit:kRPCS3TimelineLimit index:kRPCS3TimelineFile];
}

- (void)observeTimelineStage:(NSString*)stage
                     message:(NSString*)message
                   timestamp:(NSTimeInterval)timestamp {
  const char* line = message.UTF8String;
  if (!line) return;
  if ([stage isEqualToString:@"performance_sample"]) {
    ++_hostSamples;
    if (NSString* fps = RPCS3TokenValue(line, "fps")) {
      const double value = strtod(fps.UTF8String, nullptr);
      if (_hostFpsMin < 0 || value < _hostFpsMin) _hostFpsMin = value;
    }
    if (NSString* available = RPCS3TokenValue(line, "available")) {
      const long long value = strtoll(available.UTF8String, nullptr, 10);
      if (_hostAvailableMin < 0 || value < _hostAvailableMin) _hostAvailableMin = value;
    }
    if (NSString* thermal = RPCS3TokenValue(line, "thermal")) {
      _hostThermalMax = std::max(_hostThermalMax, strtoll(thermal.UTF8String, nullptr, 10));
    }
    _hostSwap = RPCS3TimelineFamily(line, @[@"swap_attempts", @"swap_successes", @"swap_failures", @"donor_lost"]);
    return;
  }
  if ([stage isEqualToString:@"neoswap_guest_sample"]) {
    _hostNeoSwap = RPCS3TimelineFamily(line, @[@"map_failures", @"first_map_max_ns", @"prepared_misses", @"ordinary_fallbacks"]);
    return;
  }
  if (![stage isEqualToString:@"core_log"]) return;
  if (strstr(line, "COREPROF FRAMEPROF527 ") != nullptr) {
    // A window without its closing summary is still exported, marked incomplete.
    if (_timelineRow) [self emitTimelineRowAt:timestamp complete:NO];
    NSMutableDictionary* row = [self timelineRow];
    row[@"session"] = RPCS3TimelineValue(RPCS3TokenValue(line, "session"));
    row[@"window"] = RPCS3TimelineValue(RPCS3TokenValue(line, "window"));
    row[@"frame_ms"] = RPCS3TimelineFamily(line, @[@"phase", @"intervals", @"median_ms", @"p95_ms", @"p99_ms",
        @"max_ms", @"over50ms", @"over100ms", @"window_ms"]);
    return;
  }
  if (strstr(line, "LOG_BUDGET dropped=") != nullptr) {
    _timelineLogDropped += strtoull(RPCS3TokenValue(line, "dropped").UTF8String ?: "0", nullptr, 10);
    return;
  }
  if (strstr(line, "COREPROF SHADERSTALL538_EVENT ") != nullptr) {
    NSString* stall = RPCS3TokenValue(line, "stage") ?: @"?";
    const unsigned long long duration = strtoull(RPCS3TokenValue(line, "duration_us").UTF8String ?: "0", nullptr, 10);
    ++_timelineStallEvents;
    _timelineStallTotalUs += duration;
    _timelineStallMaxUs = std::max(_timelineStallMaxUs, duration);
    _timelineStallStages[stall] = @(_timelineStallStages[stall].unsignedLongLongValue + 1);
    return;
  }
  NSString* family = nil;
  NSArray<NSString*>* keys = nil;
  if (strstr(line, "COREPROF SHADERSTALL538 ") != nullptr) {
    family = @"shader_stall"; keys = @[@"retained", @"dropped", @"capacity", @"threshold_us"];
  } else if (strstr(line, "COREPROF SHADERCOST534 ") != nullptr) {
    family = @"shader_cost_us"; keys = @[@"source", @"module", @"graphics", @"compute"];
  } else if (strstr(line, "COREPROF SHADERCFG536 ") != nullptr) {
    family = @"shader_config"; keys = @[@"configured", @"applied", @"fallback"];
  } else if (strstr(line, "COREPROF WAITPROF527 ") != nullptr) {
    family = @"wait_ms"; keys = @[@"cpu_gpu_fence", @"vm_range_episode", @"pipeline_queue",
        @"pipeline_build_callback", @"guest_rsx_semaphore", @"llvm_budget_cv", @"llvm_admission_mutex"];
  } else if (strstr(line, "COREPROF MEMPROF527 ") != nullptr) {
    family = @"memory_bytes"; keys = @[@"footprint", @"peak_footprint", @"resident", @"compressed"];
  } else if (strstr(line, "COREPROF VDECIO528 ") != nullptr) {
    family = @"vdec_io_process_lifetime"; keys = @[@"demand_reads", @"demand_read_total_us", @"demand_read_max_us",
        @"prefetch_hits", @"prefetch_failures", @"consumer_prefetch_wait_max_us"];
  } else if (strstr(line, "JITPROF ") != nullptr) {
    family = @"jit"; keys = @[@"ppu_codegen", @"ppu_cache_write", @"ppu_object_load", @"spu_build",
        @"spu_codegen", @"spu_cache_write"];
  } else if (strstr(line, "RANGELOCKPROF ") != nullptr) {
    family = @"range_lock"; keys = @[@"episodes", @"total_ms", @"max_ms", @"wl_putllc"];
  } else if (strstr(line, "COREPROF_RESILIENCE ") != nullptr) {
    family = @"resilience"; keys = @[@"memory_pressure_peak", @"memory_reclaims", @"shader_cache_misses",
        @"ppu_cache_misses", @"spu_compiles"];
  } else if (strstr(line, "COREPROF frames=") != nullptr) {
    [self timelineRow][@"summary"] = RPCS3TimelineFamily(line, @[@"frames", @"avg_fps", @"low1_fps",
        @"frametime_ms", @"ppu_ms", @"spu_ms", @"rsx_ms", @"gpu_fence_wait_ms", @"memory_mib",
        @"headroom_mib", @"rsx_fifo_busy"]);
    [self emitTimelineRowAt:timestamp complete:YES];
    return;
  }
  if (family) [self timelineRow][family] = RPCS3TimelineFamily(line, keys);
}

- (void)writeDiagnosticStage:(nullable NSString*)stage
                      message:(nullable NSString*)message {
  NSString* stageCopy = [stage copy] ?: @"";
  NSString* messageCopy = [message copy] ?: @"";
  const uint64_t monotonicBegin = RPCS3MonotonicUs();
  NSTimeInterval timestamp = [NSDate.date timeIntervalSince1970];
  const uint64_t monotonicEnd = RPCS3MonotonicUs();

  dispatch_async(_diagnosticQueue, ^{
    @autoreleasepool {
      @try {
        [self observeTimelineStage:stageCopy message:messageCopy timestamp:timestamp];
        NSString* path = [self diagnosticPath];
        if (![self openDiagnosticFileAtPath:path]) return;
        NSData* line = [self lineForStage:stageCopy
                                 message:messageCopy
                               timestamp:timestamp
                          monotonicBegin:monotonicBegin
                            monotonicEnd:monotonicEnd];
        if (!line) return;
        if (RPCS3KeepRuntimeHistory(messageCopy)) [self writeRuntimeHistory:line];
        if (self->_diagnosticLength + line.length > kRPCS3DiagnosticLimit) {
          // NEOSTATION_BUILD487_HOST_DIAGNOSTICS_V1 (D9): a session writes about
          // 2.7 KiB/s, so truncating in place lost the boot of every session
          // longer than ~13 min. Keep the previous file as RPCS3-diagnostic.1.log
          // (one generation: at most 2 x 2 MiB on disk) and start a new one.
          if (![self rotateDiagnosticFileAtPath:path]) {
            [self->_diagnosticFile truncateFileAtOffset:0];
            [self->_diagnosticFile seekToFileOffset:0];
            self->_diagnosticLength = 0;
          }
        }
        [self->_diagnosticFile writeData:line];
        self->_diagnosticLength += line.length;
      } @catch (__unused NSException* exception) {
        [self closeDiagnosticFile];
      }
    }
  });
}

- (void)writeMilestoneStage:(nullable NSString*)stage
                     message:(nullable NSString*)message {
  NSString* stageCopy = [stage copy] ?: @"";
  NSString* messageCopy = [message copy] ?: @"";
  const uint64_t monotonicBegin = RPCS3MonotonicUs();
  NSTimeInterval timestamp = [NSDate.date timeIntervalSince1970];
  const uint64_t monotonicEnd = RPCS3MonotonicUs();

  @synchronized(_milestoneLock) {
    @try {
      NSString* path = [self milestonePath];
      if (path.length == 0) return;
      NSFileManager* files = NSFileManager.defaultManager;
      if (![files fileExistsAtPath:path] &&
          ![files createFileAtPath:path contents:nil attributes:nil]) {
        return;
      }
      NSFileHandle* file = [NSFileHandle fileHandleForWritingAtPath:path];
      if (!file) return;
      unsigned long long length = [file seekToEndOfFile];
      NSData* line = [self lineForStage:stageCopy
                               message:messageCopy
                             timestamp:timestamp
                        monotonicBegin:monotonicBegin
                          monotonicEnd:monotonicEnd];
      if (line) {
        if (length + line.length > kRPCS3MilestoneLimit) {
          // CELL546: build 541 truncated this file to zero inside a restore
          // and lost every earlier process. Keep RPCS3-milestones.1.log.
          [file closeFile];
          const BOOL rotated = RPCS3RotateLog(path);
          gRPCS3Rotations[kRPCS3MilestoneFile].fetch_add(1, std::memory_order_relaxed);
          if (![files fileExistsAtPath:path] &&
              ![files createFileAtPath:path contents:nil attributes:nil]) {
            return;
          }
          file = [NSFileHandle fileHandleForWritingAtPath:path];
          if (!file) return;
          // A failed rename keeps the 512 KiB bound by truncating in place.
          if (!rotated) [file truncateFileAtOffset:0];
          [file seekToEndOfFile];
          if (NSData* marker = [self rotationLineForFile:path rotated:rotated index:kRPCS3MilestoneFile]) {
            [file writeData:marker];
          }
        }
        [file writeData:line];
        // Milestones bound process-crash locations, so each entry is durable
        // before control crosses into debugger, dlopen, initialize or boot.
        [file synchronizeFile];
      }
      [file closeFile];
    } @catch (__unused NSException* exception) {
    }
  }
}

- (void)closeRestoreTraceFile {
  @try {
    [_restoreTraceFile closeFile];
  } @catch (__unused NSException* exception) {
  }
  _restoreTraceFile = nil;
  _restoreTraceLength = 0;
}

- (BOOL)openRestoreTraceFileAtPath:(NSString*)path {
  if (path.length == 0) return NO;
  if (_restoreTraceFile && !RPCS3HandleOwnsPath(_restoreTraceFile, path)) {
    [self closeRestoreTraceFile];
  }
  if (_restoreTraceFile) return YES;
  NSFileManager* files = NSFileManager.defaultManager;
  if (![files fileExistsAtPath:path] &&
      ![files createFileAtPath:path contents:nil attributes:nil]) {
    return NO;
  }
  _restoreTraceFile = [NSFileHandle fileHandleForWritingAtPath:path];
  if (!_restoreTraceFile) return NO;
  _restoreTraceLength = [_restoreTraceFile seekToEndOfFile];
  return YES;
}

// CELL546: the restore thread writes each step in order through one open
// descriptor. write(2) puts it in the kernel before the next step, so a crash
// or termination of the app keeps it; only fsync, which cost the build 541
// restore ~0.13 s of milestone writes, is left out.
- (void)writeRestoreTrace:(nullable NSString*)message {
  NSString* messageCopy = [message copy] ?: @"";
  const uint64_t monotonicBegin = RPCS3MonotonicUs();
  NSTimeInterval timestamp = [NSDate.date timeIntervalSince1970];
  const uint64_t monotonicEnd = RPCS3MonotonicUs();

  @synchronized(_restoreTraceLock) {
    @try {
      NSString* path = [self restoreTracePath];
      if (![self openRestoreTraceFileAtPath:path]) return;
      NSData* line = [self lineForStage:@"savestate_restore_trace"
                               message:messageCopy
                             timestamp:timestamp
                        monotonicBegin:monotonicBegin
                          monotonicEnd:monotonicEnd];
      if (!line) return;
      if (_restoreTraceLength + line.length > kRPCS3RestoreTraceLimit) {
        [self closeRestoreTraceFile];
        const BOOL rotated = RPCS3RotateLog(path);
        gRPCS3Rotations[kRPCS3RestoreTraceFile].fetch_add(1, std::memory_order_relaxed);
        if (![self openRestoreTraceFileAtPath:path]) return;
        if (!rotated) {
          [_restoreTraceFile truncateFileAtOffset:0];
          _restoreTraceLength = 0;
        }
        if (NSData* marker = [self rotationLineForFile:path rotated:rotated index:kRPCS3RestoreTraceFile]) {
          [_restoreTraceFile writeData:marker];
          _restoreTraceLength += marker.length;
        }
      }
      [_restoreTraceFile writeData:line];
      _restoreTraceLength += line.length;
    } @catch (__unused NSException* exception) {
      [self closeRestoreTraceFile];
    }
  }
}

#if defined(RPCS3_DIAGNOSTICS_TESTING)
- (void)setDirectoryForTesting:(NSString*)directory {
  NSString* directoryCopy = [directory copy];
  dispatch_sync(_diagnosticQueue, ^{
    [self closeDiagnosticFile];
    self->_testDirectory = directoryCopy;
    self->_diagnosticPath = nil;
  });
  @synchronized(_milestoneLock) {
    _testDirectory = directoryCopy;
    _milestonePath = nil;
  }
  @synchronized(_restoreTraceLock) {
    [self closeRestoreTraceFile];
    _testDirectory = directoryCopy;
    _restoreTracePath = nil;
  }
}

- (void)flushForTesting {
  dispatch_sync(_diagnosticQueue, ^{
    @try {
      [self->_diagnosticFile synchronizeFile];
    } @catch (__unused NSException* exception) {
    }
  });
}
#endif

@end

static RPCS3DiagnosticsWriter* RPCS3SharedDiagnosticsWriter(void) {
  static RPCS3DiagnosticsWriter* writer;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    writer = [RPCS3DiagnosticsWriter new];
  });
  return writer;
}

void RPCS3Diagnostic(NSString* stage, NSString* message) {
  [RPCS3SharedDiagnosticsWriter() writeDiagnosticStage:stage message:message];
}

void RPCS3Milestone(NSString* stage, NSString* message) {
  [RPCS3SharedDiagnosticsWriter() writeMilestoneStage:stage message:message];
}

void RPCS3RestoreTrace(NSString* message) {
  [RPCS3SharedDiagnosticsWriter() writeRestoreTrace:message];
}

#if defined(RPCS3_DIAGNOSTICS_TESTING)
void RPCS3DiagnosticsSetDirectoryForTesting(NSString* directory) {
  [RPCS3SharedDiagnosticsWriter() setDirectoryForTesting:directory];
}

void RPCS3DiagnosticsFlushForTesting(void) {
  [RPCS3SharedDiagnosticsWriter() flushForTesting];
}
#endif
