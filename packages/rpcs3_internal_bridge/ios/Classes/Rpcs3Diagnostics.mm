#import "Rpcs3Diagnostics.h"

#import <Foundation/Foundation.h>
#include "Rpcs3CoreLogAdmission.h"
#include "Rpcs3IncidentReport.h"
#include <sys/stat.h>
#include <unistd.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

static const unsigned long long kRPCS3DiagnosticLimit = 2 * 1024 * 1024;
static const unsigned long long kRPCS3MilestoneLimit = 512 * 1024;
static const unsigned long long kRPCS3RuntimeHistoryLimit = 2 * 1024 * 1024;
// Compact causal evidence keeps two bounded generations independently of the
// verbose profiler/restore stream (at most 8 MiB across both cause files).
static const unsigned long long kRPCS3CauseHistoryLimit = 4 * 1024 * 1024;
// CELL546: one restore writes up to ~350 KiB of constructor/file stages.
static const unsigned long long kRPCS3RestoreTraceLimit = 1024 * 1024;
// CELL546: one compact row per Core report window (~5 s, ~1.9 KiB): each
// generation holds ~1100 windows (~90 min); with the previous one, ~3 h.
static const unsigned long long kRPCS3TimelineLimit = 2 * 1024 * 1024;
static uint64_t RPCS3MonotonicUs() {
  return std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}

// REWINDBOX_CORE_LOG_BOUNDED_621: a record the admission did not count.
static const uint64_t kRPCS3NotAccounted = UINT64_MAX;

// REWINDBOX_CORE_LOG_BOUNDED_621: one admission per process (Rpcs3Diagnostics.h).
// RPCS3Log keeps its Build 283 budget of 128 ordinary lines per second (and its
// LOG_BUDGET line) before this admission, so this one does not budget them
// again: it collapses repeats and bounds the writer backlog (LOG_BACKLOG).
rpcs3_host::core_log_admission& RPCS3CoreLogAdmissionShared() {
  static rpcs3_host::core_log_admission admission([] {
    rpcs3_host::core_log_limits limits;
    limits.per_second = 0;
    return limits;
  }());
  return admission;
}

// REWINDBOX_INCIDENT_REPORT_621: RPCS3-last-fatal.log, written on the logging thread.
static rpcs3_host::fatal_slot& RPCS3FatalSlotShared() {
  static rpcs3_host::fatal_slot slot;
  return slot;
}

static std::string RPCS3StdString(NSString* text) {
  const char* raw = text.UTF8String;
  return raw ? std::string(raw) : std::string();
}

// File names of incidents: letters, digits, '-' and '_' only.
static std::string RPCS3IncidentFileName(std::string name) {
  for (char& c : name) {
    const bool keep = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
    if (!keep) c = '_';
  }
  return name.substr(0, 120);
}
// A separate bounded history excludes verbose restore-constructor traces.
// It shares the existing asynchronous diagnostics worker, not a guest thread.
static BOOL RPCS3KeepRuntimeHistory(NSString* message) {
  for (NSString* token in @[@"COREPROF ", @"SPUPROF ", @"JITPROF ",
      @"RANGELOCKPROF ", @"COREPROF_RESILIENCE ",
      @"JITPROF_BOOT ", @"CONFIG_LAYERS ", @"JITMEM ", @"NEOSWAP_VDEC ",
      @"FREEZE_DUMP snapshot\n", @"SAVESTATE_RESTORE phase=missing_resource ",
      @"SAVESTATE_RESTORE phase=fxo_resource_abort ",
      @"SAVESTATE_RESTORE phase=worker_exception", @"LOG_BUDGET ",
      // REWINDBOX_INCIDENT_REPORT_621
      @"FREEZE_EPISODE ", @"HOST_STATE ", @"LOG_REPEAT "])
    if ([message rangeOfString:token].location != NSNotFound) return YES;
  return NO;
}

// Plain C++ admission: only bounded Core reports/events and boot/freeze facts.
// Keep the complete original message, including unknown future fields. The
// producers bound the event records; per-draw/per-poll families are excluded.
static bool RPCS3CauseToken(const char* message, const char* token) noexcept {
  if (!message) return false;
  for (const char* at = strstr(message, token); at; at = strstr(at + 1, token)) {
    if (at == message || at[-1] == ' ' || at[-1] == '\n' || at[-1] == '\t') return true;
  }
  return false;
}

static bool RPCS3KeepCauseHistory(const char* message) noexcept {
  for (const char* token : {
      "CONFIG_LAYERS ", "JITPROF_BOOT ", "SAVESTATE_BOOT ", "NEOSTATION_RESTART ",
      "COREPROF FRAMEPROF527 ", "COREPROF FRAMECAUSE ", "COREPROF FRAMECAUSE_EVENT ",
      "COREPROF RENDERCAUSE ", "COREPROF RENDERCAUSE_EVENT ",
      "COREPROF SIGNALCAUSE ", "COREPROF SIGNALCAUSE_EVENT ", "COREPROF SIGNALCAUSE_PRODUCER ",
      "RSX_ACQUIRE ", "FREEZE_DUMP snapshot\n", "LOG_BUDGET ",
      // REWINDBOX_GPU_TIMING_621 / REWINDBOX_INCIDENT_REPORT_621
      "COREPROF GPUTIME621 ", "COREPROF GPUTIME621_BOOT ", "FREEZE_EPISODE ", "HOST_STATE ", "LOG_REPEAT "}) {
    if (RPCS3CauseToken(message, token)) return true;
  }
  return false;
}

// CELL546: generations discarded by each bounded file since launch. A reader
// of the compact timeline sees how much history rotated away.
enum RPCS3LogFile : size_t {
  kRPCS3DiagnosticFile, kRPCS3PerformanceFile, kRPCS3MilestoneFile,
  kRPCS3RestoreTraceFile, kRPCS3TimelineFile, kRPCS3CauseFile, kRPCS3LogFileCount
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

// Value of a `key=` token of a Core profiler line, at most `limit` bytes.
static NSString* RPCS3TokenValueBounded(const char* line, const char* key, size_t limit) {
  const size_t keyLength = strlen(key);
  for (const char* at = strstr(line, key); at; at = strstr(at + 1, key)) {
    if ((at == line || at[-1] == ' ') && at[keyLength] == '=') {
      const char* value = at + keyLength + 1;
      const size_t length = std::min<size_t>(strcspn(value, " \n"), limit);
      return [[NSString alloc] initWithBytes:value length:length encoding:NSUTF8StringEncoding];
    }
  }
  return nil;
}

// Value of a `key=` token of a Core profiler line, at most 96 bytes.
static NSString* RPCS3TokenValue(const char* line, const char* key) {
  return RPCS3TokenValueBounded(line, key, 96);
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

// LOG_REPEAT / LOG_BUDGET lines of the admission (joined by '\n'), one journal
// record each; their bytes add up to what the admission reserved.
static void RPCS3WriteAdmissionLines(const std::string& text) {
  size_t at = 0;
  while (at < text.size()) {
    const size_t newline = text.find('\n', at);
    const size_t end = newline == std::string::npos ? text.size() : newline;
    const std::string piece = text.substr(at, end - at);
    RPCS3CoreLogLine([NSString stringWithUTF8String:piece.c_str()] ?: @"",
                     piece.size() + (newline == std::string::npos ? 0 : 1));
    at = end + 1;
  }
}

@interface RPCS3DiagnosticsWriter : NSObject
- (void)writeDiagnosticStage:(nullable NSString*)stage
                      message:(nullable NSString*)message;
- (void)writeDiagnosticStage:(nullable NSString*)stage
                      message:(nullable NSString*)message
                     reserved:(uint64_t)reserved;
- (void)recordFatal:(NSString*)message gameStopped:(BOOL)gameStopped;
- (void)hostMenuOpen:(BOOL)menuOpen background:(BOOL)background;
- (void)sessionStopped;
- (void)drainWithin:(uint32_t)milliseconds;
- (nullable NSString*)takePreviousSessionIncident;
- (void)buildReport:(void (^)(NSString* _Nullable path))completion;
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
  // CELL551: title and effective layers of the current boot (CONFIG_LAYERS).
  NSString* _timelineTitle;
  NSDictionary* _timelineConfig;
  // Owned by the same serial diagnostic queue. Every causal record carries
  // its identity, even if the original boot has rotated out of both files.
  NSString* _causeTitle;
  NSString* _causeSession;
  NSString* _causeBootKind;
  // REWINDBOX_INCIDENT_REPORT_621: owned by the same serial diagnostic queue.
  rpcs3_host::incident_model _incidents;
  rpcs3_host::session_record _session;
  BOOL _sessionActive;
  NSTimeInterval _sessionWrittenAt;
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
  NSString* diagnostics = [[documents stringByAppendingPathComponent:@"Diagnostics"]
      stringByAppendingPathComponent:@"PS3"];
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
  return [self lineForStage:stage message:message timestamp:timestamp
            monotonicBegin:monotonicBegin monotonicEnd:monotonicEnd context:nil];
}

- (NSData*)lineForStage:(nullable NSString*)stage
                message:(nullable NSString*)message
              timestamp:(NSTimeInterval)timestamp
         monotonicBegin:(uint64_t)monotonicBegin
           monotonicEnd:(uint64_t)monotonicEnd
                 context:(nullable NSDictionary*)context {
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
  if (context.count) {
    NSMutableDictionary* contextual = [entry mutableCopy];
    [contextual addEntriesFromDictionary:context];
    entry = contextual;
  }
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
    if (index == kRPCS3TimelineFile || index == kRPCS3CauseFile)
      marker = [self rotationLineForFile:path rotated:rotated index:index];
  }
  if (![files fileExistsAtPath:path]) [files createFileAtPath:path contents:nil attributes:nil];
  NSFileHandle* file = [NSFileHandle fileHandleForWritingAtPath:path];
  [file seekToEndOfFile];
  // An unusually large complete record wins over the optional marker, so
  // adding a rotation header can never exceed the file's byte limit.
  if (marker && marker.length + line.length <= limit) [file writeData:marker];
  [file writeData:line]; [file closeFile];
}

- (void)writeRuntimeHistory:(NSData*)line {
  // The current plus one previous generation occupy at most 4 MiB on disk.
  [self appendLine:line name:@"RPCS3-performance.log"
             limit:kRPCS3RuntimeHistoryLimit index:kRPCS3PerformanceFile];
}

// Called only on _diagnosticQueue. No additional queue, flush or truncation
// of individual causes is introduced; appendLine keeps the full JSON record.
- (void)writeCauseStage:(NSString*)stage
                 message:(NSString*)message
               timestamp:(NSTimeInterval)timestamp
          monotonicBegin:(uint64_t)monotonicBegin
            monotonicEnd:(uint64_t)monotonicEnd {
  const char* raw = message.UTF8String;
  const BOOL bootBegin = [stage isEqualToString:@"game_boot_begin"];
  const BOOL bootReturn = [stage isEqualToString:@"game_boot_return"];
  // REWINDBOX_INCIDENT_REPORT_621: the host's own HOST_STATE records join the causes.
  const BOOL coreOrHost = [stage isEqualToString:@"core_log"] || [stage isEqualToString:@"host_state"];
  if (!bootBegin && !bootReturn && (!coreOrHost || !RPCS3KeepCauseHistory(raw))) return;
  if (bootBegin || RPCS3CauseToken(raw, "CONFIG_LAYERS ")) {
    _causeTitle = bootBegin ? [message componentsSeparatedByString:@" "].firstObject
                           : RPCS3TokenValue(raw, "title");
    _causeSession = nil;
    _causeBootKind = nil;
  }
  if (NSString* session = RPCS3TokenValue(raw ?: "", "session")) _causeSession = session;
  else if (NSString* session = RPCS3TokenValue(raw ?: "", "report_session")) _causeSession = session;
  if (NSString* kind = RPCS3TokenValue(raw ?: "", "boot_kind")) _causeBootKind = kind;
  NSMutableDictionary* context = [@{@"title": _causeTitle.length ? _causeTitle : @"unknown"} mutableCopy];
  if (_causeSession.length) context[@"session"] = RPCS3TimelineValue(_causeSession);
  if (_causeBootKind.length) context[@"boot_kind"] = _causeBootKind;
  NSData* line = [self lineForStage:stage message:message timestamp:timestamp
                    monotonicBegin:monotonicBegin monotonicEnd:monotonicEnd context:context];
  [self appendLine:line name:@"RPCS3-causes.log"
             limit:kRPCS3CauseHistoryLimit index:kRPCS3CauseFile];
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
        @"diagnostic=%u performance=%u milestones=%u restore_trace=%u timeline=%u causes=%u",
        gRPCS3Rotations[kRPCS3DiagnosticFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3PerformanceFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3MilestoneFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3RestoreTraceFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3TimelineFile].load(std::memory_order_relaxed),
        gRPCS3Rotations[kRPCS3CauseFile].load(std::memory_order_relaxed)],
  };
  // CELL551: every row names its title; the first row after a boot carries
  // the configuration layers that boot applied.
  if (_timelineTitle.length) row[@"title"] = _timelineTitle;
  if (_timelineConfig.count) {
    row[@"config"] = _timelineConfig;
    _timelineConfig = nil;
  }
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
    NSMutableDictionary* frame = RPCS3TimelineFamily(line, @[@"phase", @"intervals", @"median_ms", @"p95_ms", @"p99_ms",
        @"max_ms", @"over50ms", @"over100ms", @"window_ms", @"total_interval_ms",
        @"window_guest_flips", @"wall_guest_fps", @"completed_interval_fps", @"last_guest_flip_age_ms",
        @"guest_progress_boundary_approximate"]);
    // Build 613: the per-presentation histogram (upper_us:count pairs, at most
    // 256 bins, about 3.3 KiB) is copied whole; the 96-byte bound of ordinary
    // tokens would drop its long-interval bins.
    if (NSString* histogram = RPCS3TokenValueBounded(line, "histogram_upper_us", 4096)) {
      frame[@"histogram_upper_us"] = histogram;
    }
    row[@"frame_ms"] = frame;
    return;
  }
  if (strstr(line, "CONFIG_LAYERS ") != nullptr) {
    _timelineTitle = RPCS3TokenValue(line, "title");
    _timelineConfig = RPCS3TimelineFamily(line, @[@"database", @"legacy_custom", @"sparse_overrides",
        @"inherited", @"kept", @"shader_mode", @"frame_limit", @"rsx_res", @"wcb", @"spu_block",
        @"accurate_res", @"mt_rsx", @"spu_spin", @"mlaa_bypass", @"max_spurs"]);
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
  if (RPCS3CauseToken(line, "COREPROF FRAMECAUSE ")) {
    family = @"frame_cause"; keys = @[@"captured", @"frames", @"slow", @"sampled", @"retained",
        @"unretained", @"contended", @"threshold_us", @"capacity"];
  } else if (RPCS3CauseToken(line, "COREPROF RENDERCAUSE ")) {
    family = @"render_cause"; keys = @[@"captured", @"retained", @"vertex_range", @"sampler_refresh",
        @"sampler_cyclic_fast", @"dropped", @"contended"];
  } else if (RPCS3CauseToken(line, "COREPROF SIGNALCAUSE ")) {
    family = @"signal_cause"; keys = @[@"enabled", @"watch_valid", @"watch_active", @"watch_stalled",
        @"acquire", @"address", @"expected", @"observed", @"events_dropped", @"history_overwritten",
        @"stale_session_dropped", @"producer_dropped", @"producer_replaced", @"read_busy",
        @"stalls_total", @"stall_latched", @"stall_overwritten", @"stall_dropped", @"dump", @"coverage", @"excluded"];
  } else if (strstr(line, "COREPROF SHADERSTALL538 ") != nullptr) {
    family = @"shader_stall"; keys = @[@"retained", @"dropped", @"capacity", @"threshold_us"];
  } else if (strstr(line, "COREPROF SHADERCOST534 ") != nullptr) {
    family = @"shader_cost_us"; keys = @[@"source", @"module", @"graphics", @"compute"];
  } else if (strstr(line, "COREPROF SHADERCFG536 ") != nullptr) {
    family = @"shader_config"; keys = @[@"configured", @"applied", @"fallback"];
  } else if (strstr(line, "COREPROF WAITPROF527 ") != nullptr) {
    family = @"wait_ms"; keys = @[@"cpu_gpu_fence", @"vm_range_episode", @"pipeline_queue",
        @"pipeline_build_callback", @"guest_rsx_semaphore", @"llvm_budget_cv", @"llvm_admission_mutex"];
  } else if (strstr(line, "COREPROF PRESSURE547 ") != nullptr) {
    // CELL547: draw-blocking pipeline builds, SPU polls that waited passively
    // meanwhile, and GPU fence waits that blocked instead of spinning.
    family = @"pressure"; keys = @[@"blocking_builds", @"spu_passive_waits", @"fence_spin_completed",
        @"fence_blocked"];
  } else if (strstr(line, "COREPROF RSXSYNC551 ") != nullptr) {
    // CELL551: GPU waits by reason, vkQueueSubmit (Metal encoding under
    // synchronous MoltenVK submits), drawable acquisition and present.
    family = @"rsx_sync"; keys = @[@"frame_cleanup", @"cb_reuse", @"hard_sync", @"texture", @"other",
        @"submit", @"acquire", @"present", @"frame_latency", @"mvk_async", @"metal_compiles_interactive", @"metal_compiles_default"];
  } else if (strstr(line, "COREPROF ZCULLSYNC613 ") != nullptr) {
    // Build 613: ZCULL report reads on the RSX thread (submission and MoltenVK
    // wait included), the reads that had to submit, and early zcull_sync submits.
    family = @"zcull_sync"; keys = @[@"results", @"result_flushes", @"hint_flushes", @"precise", @"relaxed"];
  } else if (strstr(line, "COREPROF ZCULLWAIT616 ") != nullptr) {
    // Build 616: the MoltenVK wait inside those reads by the path that asked
    // (poll, forced read, conditional render, sync), the gathers per path in
    // that order and the polls left for later instead of waiting.
    family = @"zcull_wait"; keys = @[@"poll", @"forced", @"cond_render", @"sync", @"gathers", @"poll_deferred"];
  } else if (strstr(line, "COREPROF GPUTIME621 ") != nullptr) {
    // REWINDBOX_GPU_TIMING_621: GPU execution of the RSX primary command buffers
    // read in this window (union of overlapping submissions), coverage and probe cost.
    family = @"gpu_time"; keys = @[@"state", @"coverage", @"busy_ms", @"busy_share", @"sum_ms", @"max_cb_ms",
        @"frames_gpu_over33ms", @"frames_gpu_over50ms", @"queue_delay_max_ms", @"pending", @"units",
        @"period_ratio", @"probe_cpu_ms"];
  } else if (strstr(line, "COREPROF SPUPREFETCH616 ") != nullptr) {
    // Build 616: SPU objects read ahead into memory and taken by compile threads.
    family = @"spu_prefetch"; keys = @[@"active", @"done", @"planned", @"read", @"read_ms", @"hits", @"claimed",
        @"dropped", @"failures", @"resident_kib"];
  } else if (strstr(line, "COREPROF RSXFRAME551 ") != nullptr) {
    // CELL551: RPCS3's per-frame RSX statistics; stage times are sampled-frame averages.
    family = @"rsx_frame"; keys = @[@"frames", @"sampled", @"draws_per_frame", @"submits", @"setup_ms", @"vertex_ms",
        @"texture_ms", @"exec_ms", @"flip_ms", @"vertex_cache", @"program_lookups", @"fifo_idle_entries"];
  } else if (strstr(line, "COREPROF SPUWAIT551 ") != nullptr) {
    // CELL551: SPU time outside guest code, summed over the SPU threads.
    family = @"spu_wait"; keys = @[@"getllar_poll", @"getllar_sleep", @"event_wait", @"putllc_ok",
        @"putllc_fail", @"putllc_heavy"];
  } else if (strstr(line, "COREPROF MEMPROF527 ") != nullptr) {
    family = @"memory_bytes"; keys = @[@"footprint", @"peak_footprint", @"resident", @"compressed"];
  } else if (strstr(line, "COREPROF VDECIO528 ") != nullptr) {
    family = @"vdec_io_process_lifetime"; keys = @[@"demand_reads", @"demand_read_total_us", @"demand_read_max_us",
        @"prefetch_hits", @"prefetch_failures", @"consumer_prefetch_wait_max_us"];
  } else if (strstr(line, "JITPROF ") != nullptr) {
    // Build 613: object-cache reads and links of SPU blocks, beside their builds.
    family = @"jit"; keys = @[@"ppu_codegen", @"ppu_cache_write", @"ppu_object_load", @"spu_build",
        @"spu_codegen", @"spu_cache_write", @"spu_cache_read", @"spu_object_load"];
  } else if (strstr(line, "JITMEM ") != nullptr) {
    // Build 613: concurrent admitted LLVM jobs (1 = serialized).
    family = @"jit_mem"; keys = @[@"active", @"active_peak", @"headroom_min_mib"];
  } else if (strstr(line, "SPUPROF ") != nullptr) {
    // Build 613: SPU blocks built on first use and their object-cache outcome.
    family = @"spu_blocks"; keys = @[@"gameplay_attempts", @"gameplay_total_ms", @"gameplay_max_ms",
        @"obj_hits", @"obj_misses"];
  } else if (strstr(line, "RANGELOCKPROF ") != nullptr) {
    family = @"range_lock"; keys = @[@"episodes", @"total_ms", @"max_ms", @"wl_putllc"];
  } else if (strstr(line, "COREPROF_RESILIENCE ") != nullptr) {
    family = @"resilience"; keys = @[@"memory_pressure_peak", @"memory_reclaims", @"shader_cache_misses",
        @"ppu_cache_misses", @"spu_compiles"];
  } else if (strstr(line, "COREPROF frames=") != nullptr) {
    [self timelineRow][@"summary"] = RPCS3TimelineFamily(line, @[@"frames", @"avg_fps", @"low1_fps",
        @"frametime_ms", @"ppu_ms", @"spu_ms", @"rsx_ms", @"gpu_fence_wait_ms", @"memory_mib",
        @"headroom_mib", @"rsx_fifo_busy", @"wall_guest_fps", @"last_guest_flip_age_ms", @"avg_fps_scope"]);
    [self emitTimelineRowAt:timestamp complete:YES];
    return;
  }
  if (family) [self timelineRow][family] = RPCS3TimelineFamily(line, keys);
}

- (void)writeDiagnosticStage:(nullable NSString*)stage
                      message:(nullable NSString*)message {
  [self writeDiagnosticStage:stage message:message reserved:kRPCS3NotAccounted];
}

// `reserved`: the bytes Rpcs3CoreLogAdmission counted for this core_log line
// (zero included), released once it is written; kRPCS3NotAccounted for every
// other record (REWINDBOX_CORE_LOG_BOUNDED_621).
- (void)writeDiagnosticStage:(nullable NSString*)stage
                      message:(nullable NSString*)message
                     reserved:(uint64_t)reserved {
  NSString* stageCopy = [stage copy] ?: @"";
  NSString* messageCopy = [message copy] ?: @"";
  const uint64_t monotonicBegin = RPCS3MonotonicUs();
  NSTimeInterval timestamp = [NSDate.date timeIntervalSince1970];
  const uint64_t monotonicEnd = RPCS3MonotonicUs();

  dispatch_block_t write = ^{
    @autoreleasepool {
      @try {
        [self observeTimelineStage:stageCopy message:messageCopy timestamp:timestamp];
        @try {
          [self writeCauseStage:stageCopy message:messageCopy timestamp:timestamp
                 monotonicBegin:monotonicBegin monotonicEnd:monotonicEnd];
        } @catch (__unused NSException* exception) {
          // A best-effort cause append must not suppress the existing journal.
        }
        @try {
          [self observeIncidentStage:stageCopy message:messageCopy timestamp:timestamp];
        } @catch (__unused NSException* exception) {
          // The incident files are best effort too.
        }
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
  };
  // REWINDBOX_CORE_LOG_DURABLE_V1 wrote core_log lines with dispatch_sync, so
  // that report_fatal_error's line reached the kernel before its abort(); every
  // emulator thread that logged then waited for this queue and the disk.
  // REWINDBOX_CORE_LOG_BOUNDED_621: every line is asynchronous. The admission
  // (Rpcs3CoreLogAdmission.h) bounds what waits here, and a fatal-level line is
  // also written at once to RPCS3-last-fatal.log by RPCS3RecordFatalLine (one
  // write(2) on the logging thread, kept through an abort).
  dispatch_async(_diagnosticQueue, ^{
    write();
    if (reserved != kRPCS3NotAccounted) RPCS3CoreLogAdmissionShared().written(reserved);
  });
}


// ---- REWINDBOX_INCIDENT_REPORT_621 (Rpcs3IncidentReport.h) -----------------
// The incident model, the session record and the incident files belong to the
// serial diagnostic queue. One file per freeze episode (rewritten as it
// progresses), per fatal stop and per unexpected end found at launch.

- (NSString*)incidentsDirectory {
  NSString* directory = [self documentsDirectory];
  if (!directory.length) return @"";
  NSString* incidents = [directory stringByAppendingPathComponent:@"Incidents"];
  [NSFileManager.defaultManager createDirectoryAtPath:incidents
                          withIntermediateDirectories:YES
                                           attributes:nil
                                                error:nil];
  return incidents;
}

- (NSString*)sessionRecordPath {
  NSString* directory = [self documentsDirectory];
  return directory.length ? [directory stringByAppendingPathComponent:@"RPCS3-session.txt"] : @"";
}

- (NSString*)fatalSlotPath {
  NSString* directory = [self documentsDirectory];
  return directory.length ? [directory stringByAppendingPathComponent:@"RPCS3-last-fatal.log"] : @"";
}

- (void)writeSessionRecordAt:(NSTimeInterval)timestamp force:(BOOL)force {
  if (!_sessionActive) return;
  if (!force && timestamp - _sessionWrittenAt < 5.0) return;
  _sessionWrittenAt = timestamp;
  _session.updated_s = timestamp;
  NSString* path = [self sessionRecordPath];
  if (path.length) rpcs3_host::write_atomically(RPCS3StdString(path), _session.serialize());
}

- (nullable NSString*)writeIncident:(const rpcs3_host::incident&)value {
  NSString* directory = [self incidentsDirectory];
  if (!directory.length) return nil;
  std::string name = value.kind + "-" + (value.title.empty() ? std::string("unknown") : value.title);
  if (value.kind == "freeze") {
    name += "-s" + value.session + "-e" + value.episode;
  } else {
    char stamp[32];
    std::snprintf(stamp, sizeof(stamp), "-%.0f", value.began_s);
    name += stamp;
  }
  NSString* file = [NSString stringWithFormat:@"%s.txt", RPCS3IncidentFileName(name).c_str()];
  NSString* path = [directory stringByAppendingPathComponent:file];
  return rpcs3_host::write_atomically(RPCS3StdString(path), rpcs3_host::summarize(value)) ? path : nil;
}

// Keeps the `keep` newest incident files.
- (void)pruneIncidents:(NSUInteger)keep {
  NSString* directory = [self incidentsDirectory];
  if (!directory.length) return;
  NSFileManager* files = NSFileManager.defaultManager;
  NSMutableArray<NSString*>* paths = [NSMutableArray array];
  for (NSString* name in [files contentsOfDirectoryAtPath:directory error:nil] ?: @[]) {
    if ([name hasSuffix:@".txt"]) [paths addObject:[directory stringByAppendingPathComponent:name]];
  }
  if (paths.count <= keep) return;
  [paths sortUsingComparator:^NSComparisonResult(NSString* a, NSString* b) {
    NSDate* first = [files attributesOfItemAtPath:a error:nil].fileModificationDate ?: NSDate.distantPast;
    NSDate* second = [files attributesOfItemAtPath:b error:nil].fileModificationDate ?: NSDate.distantPast;
    return [second compare:first];
  }];
  for (NSUInteger index = keep; index < paths.count; ++index) [files removeItemAtPath:paths[index] error:nil];
}

- (void)beginIncidentSession:(NSString*)message timestamp:(NSTimeInterval)timestamp {
  NSString* title = [message componentsSeparatedByString:@" "].firstObject ?: @"";
  NSString* build = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown";
  _incidents.begin_session(RPCS3StdString(title), RPCS3StdString(build), "", timestamp);
  _session = rpcs3_host::session_record{};
  _session.state = "running";
  _session.pid = getpid();
  _session.build = RPCS3StdString(build);
  _session.title = RPCS3StdString(title);
  _session.started_s = timestamp;
  _sessionActive = YES;
  [self writeSessionRecordAt:timestamp force:YES];
}

- (void)observeIncidentStage:(NSString*)stage
                     message:(NSString*)message
                   timestamp:(NSTimeInterval)timestamp {
  if ([stage isEqualToString:@"performance_sample"]) {
    if (const char* sample = message.UTF8String) _incidents.host_sample(sample);
    return;
  }
  if (![stage isEqualToString:@"core_log"]) return;
  const char* line = message.UTF8String;
  if (!line || (!strstr(line, "FREEZE_") && !strstr(line, "COREPROF frames="))) return;
  if (const rpcs3_host::incident* value = _incidents.core_line(line, timestamp)) {
    [self writeIncident:*value];
    _session.last_episode = !value->end_line.empty() ? value->end_line
        : (!value->last_line.empty() ? value->last_line : value->begin_line);
    [self writeSessionRecordAt:timestamp force:YES];
    return;
  }
  if (strstr(line, "COREPROF frames=")) {
    _session.last_window = _incidents.last_window();
    [self writeSessionRecordAt:timestamp force:NO];
  }
}

- (void)recordFatal:(NSString*)message gameStopped:(BOOL)gameStopped {
  NSString* copy = [message copy] ?: @"";
  const NSTimeInterval timestamp = NSDate.date.timeIntervalSince1970;
  dispatch_async(_diagnosticQueue, ^{
    @autoreleasepool {
      @try {
        if (const rpcs3_host::incident* value = self->_incidents.fatal(RPCS3StdString(copy), gameStopped, timestamp))
          [self writeIncident:*value];
        self->_session.last_fatal = self->_incidents.last_fatal();
        [self writeSessionRecordAt:timestamp force:YES];
      } @catch (__unused NSException* exception) {
      }
    }
  });
}

- (void)hostMenuOpen:(BOOL)menuOpen background:(BOOL)background {
  const NSTimeInterval timestamp = NSDate.date.timeIntervalSince1970;
  dispatch_async(_diagnosticQueue, ^{
    @autoreleasepool {
      @try {
        const rpcs3_host::host_state previous = self->_incidents.current_host();
        if (previous.menu_open == static_cast<bool>(menuOpen) && previous.background == static_cast<bool>(background)) return;
        if (previous.background && !background) self->_incidents.background_left(timestamp);
        rpcs3_host::host_state state;
        state.menu_open = menuOpen;
        state.background = background;
        self->_incidents.host(state, timestamp);
        NSString* record = [NSString stringWithFormat:
            @"HOST_STATE menu=%@ app=%@ menu_pauses_emulation=0",
            menuOpen ? @"open" : @"closed", background ? @"background" : @"foreground"];
        self->_session.host = RPCS3StdString(record);
        [self writeSessionRecordAt:timestamp force:YES];
        for (const auto& entry : self->_incidents.incidents()) {
          if (entry.second.kind == "freeze" && entry.second.end_line.empty()) [self writeIncident:entry.second];
        }
        // The record joins the journal and the cause history like a Core line.
        [self writeDiagnosticStage:@"host_state" message:record];
      } @catch (__unused NSException* exception) {
      }
    }
  });
}

// A fatal line: wait at most `milliseconds` for the lines queued before it.
// Never called from this queue (the Core logs from its own threads).
- (void)drainWithin:(uint32_t)milliseconds {
  dispatch_semaphore_t drained = dispatch_semaphore_create(0);
  dispatch_async(_diagnosticQueue, ^{
    dispatch_semaphore_signal(drained);
  });
  dispatch_semaphore_wait(drained, dispatch_time(DISPATCH_TIME_NOW, (int64_t)milliseconds * NSEC_PER_MSEC));
}

- (void)sessionStopped {
  const NSTimeInterval timestamp = NSDate.date.timeIntervalSince1970;
  dispatch_async(_diagnosticQueue, ^{
    @autoreleasepool {
      @try {
        // A run of one message still being counted, and refused lines, reach the journal.
        RPCS3WriteAdmissionLines(RPCS3CoreLogAdmissionShared().flush());
        if (!self->_sessionActive) return;
        self->_session.state = "stopped";
        [self writeSessionRecordAt:timestamp force:YES];
        self->_sessionActive = NO;
      } @catch (__unused NSException* exception) {
      }
    }
  });
}

// At launch: the record of a previous process that never stopped becomes an
// "unexpected_end" incident (its last fatal line comes from RPCS3-last-fatal.log
// when the record missed it); the record is then set aside.
- (nullable NSString*)takePreviousSessionIncident {
  __block NSString* result = nil;
  dispatch_sync(_diagnosticQueue, ^{
    @autoreleasepool {
      @try {
        NSString* path = [self sessionRecordPath];
        std::string text;
        if (!path.length || !rpcs3_host::read_small_file(RPCS3StdString(path), text)) return;
        rpcs3_host::incident value;
        if (rpcs3_host::unexpected_end(text, getpid(), value)) {
          rpcs3_host::session_record record;
          rpcs3_host::session_record::parse(text, record);
          std::string fatal;
          if (value.fatal_line.empty() && rpcs3_host::read_small_file(RPCS3StdString([self fatalSlotPath]), fatal, 64 * 1024)) {
            const std::string marker = "pid=" + std::to_string(record.pid) + " ";
            const std::size_t at = fatal.rfind(marker);
            if (at != std::string::npos) {
              const std::size_t begin = fatal.rfind('\n', at);
              const std::size_t end = fatal.find('\n', at);
              value.fatal_line = fatal.substr(begin == std::string::npos ? 0 : begin + 1,
                  end == std::string::npos ? std::string::npos : end - (begin == std::string::npos ? 0 : begin + 1));
            }
          }
          NSString* written = [self writeIncident:value];
          // iOS may end an app it suspended in the background: kept in the report,
          // not announced as a crash.
          if (record.host.find("app=background") == std::string::npos) result = written;
        }
        [self pruneIncidents:40];
        NSString* previous = [[path stringByDeletingPathExtension] stringByAppendingString:@".previous.txt"];
        [NSFileManager.defaultManager removeItemAtPath:previous error:nil];
        [NSFileManager.defaultManager moveItemAtPath:path toPath:previous error:nil];
      } @catch (__unused NSException* exception) {
      }
    }
  });
  return result;
}

// The shareable report: the incidents of this session and the newest incident
// files, then bounded tails of every journal, streamed (Rpcs3IncidentReport.h).
- (void)buildReport:(void (^)(NSString* _Nullable path))completion {
  void (^done)(NSString* _Nullable) = [completion copy];
  dispatch_async(_diagnosticQueue, ^{
    @autoreleasepool {
      std::string summary;
      std::vector<rpcs3_host::export_source> sources;
      NSString* output = nil;
      @try {
        NSString* build = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown";
        NSString* version = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"";
        NSDateFormatter* formatter = [NSDateFormatter new];
        formatter.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
        formatter.dateFormat = @"yyyyMMdd-HHmmss";
        NSString* stamp = [formatter stringFromDate:NSDate.date];
        summary = "RewindBox PS3 diagnostic report\nApp: RewindBox " + RPCS3StdString(version) + " (" + RPCS3StdString(build) +
            ")\nGenerated: " + RPCS3StdString(stamp) + "\nPID: " + std::to_string(getpid()) + "\n\n";
        const std::string pending = RPCS3CoreLogAdmissionShared().flush();
        if (!pending.empty()) {
          summary += pending + "\n\n";
          RPCS3CoreLogAdmissionShared().written(pending.size(), rpcs3_host::core_log_admission::lines(pending));
        }
        const auto counters = RPCS3CoreLogAdmissionShared().counters();
        summary += "Core log admission: admitted=" + std::to_string(counters.admitted) + " budget_dropped=" +
            std::to_string(counters.budget_dropped) + " backlog_dropped=" + std::to_string(counters.backlog_dropped) +
            " repeats=" + std::to_string(counters.repeats) + " fatal=" + std::to_string(counters.fatal) +
            " backlog_peak_lines=" + std::to_string(counters.backlog_peak_lines) + "\n\n";
        if (self->_incidents.incidents().empty()) {
          summary += "No freeze or fatal incident was recorded in this session.\n";
        }
        for (const auto& entry : self->_incidents.incidents()) {
          summary += rpcs3_host::summarize(entry.second);
          summary += "\n";
        }
        NSString* documents = [self documentsDirectory];
        // Earlier incident files (other sessions, unexpected ends), newest first.
        NSString* incidents = [self incidentsDirectory];
        NSMutableArray<NSString*>* files = [NSMutableArray array];
        for (NSString* name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:incidents error:nil] ?: @[]) {
          if ([name hasSuffix:@".txt"]) [files addObject:[incidents stringByAppendingPathComponent:name]];
        }
        [files sortUsingComparator:^NSComparisonResult(NSString* a, NSString* b) {
          NSDate* first = [NSFileManager.defaultManager attributesOfItemAtPath:a error:nil].fileModificationDate ?: NSDate.distantPast;
          NSDate* second = [NSFileManager.defaultManager attributesOfItemAtPath:b error:nil].fileModificationDate ?: NSDate.distantPast;
          return [second compare:first];
        }];
        for (NSUInteger index = 0; index < files.count && index < 8; ++index) {
          sources.push_back({RPCS3StdString(files[index]), "Incident file", 16 * 1024});
        }
        const struct { const char* name; const char* label; uint64_t tail; } journals[] = {
          {"RPCS3-last-fatal.log", "Last fatal errors", 64 * 1024},
          {"RPCS3-session.previous.txt", "Previous session record", 16 * 1024},
          {"RPCS3-milestones.log", "Milestones", 512 * 1024},
          {"RPCS3-milestones.1.log", "Milestones (previous generation)", 256 * 1024},
          {"RPCS3-causes.log", "Cause history", 3 * 1024 * 1024},
          {"RPCS3-causes.1.log", "Cause history (previous generation)", 1024 * 1024},
          {"RPCS3-timeline.log", "Timeline", 512 * 1024},
          {"RPCS3-performance.log", "Performance history", 1024 * 1024},
          {"RPCS3-diagnostic.log", "Diagnostic journal", 2 * 1024 * 1024},
          {"RPCS3-diagnostic.1.log", "Diagnostic journal (previous generation)", 512 * 1024},
          {"RPCS3-restore-trace.log", "Savestate restore trace", 128 * 1024},
        };
        for (const auto& journal : journals) {
          sources.push_back({RPCS3StdString([documents stringByAppendingPathComponent:@(journal.name)]), journal.label, journal.tail});
        }
        // Earlier reports in the temporary directory are removed first.
        for (NSString* name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:NSTemporaryDirectory() error:nil] ?: @[]) {
          if ([name hasPrefix:@"RewindBox-PS3-report-"])
            [NSFileManager.defaultManager removeItemAtPath:[NSTemporaryDirectory() stringByAppendingPathComponent:name] error:nil];
        }
        output = [NSTemporaryDirectory() stringByAppendingPathComponent:
            [NSString stringWithFormat:@"RewindBox-PS3-report-%@.txt", stamp]];
      } @catch (__unused NSException* exception) {
        output = nil;
      }
      if (!output.length) {
        dispatch_async(dispatch_get_main_queue(), ^{ if (done) done(nil); });
        return;
      }
      // The copy runs off the journal queue: core_log lines keep flowing meanwhile.
      const std::string target = RPCS3StdString(output);
      dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        const rpcs3_host::export_result exported = rpcs3_host::export_report(target, summary, sources);
        RPCS3Diagnostic(@"incident_report", [NSString stringWithFormat:
            @"INCIDENT_REPORT ok=%d bytes=%llu sources=%llu missing=%llu truncated=%llu error=%s",
            exported.ok ? 1 : 0, (unsigned long long)exported.bytes, (unsigned long long)exported.sources,
            (unsigned long long)exported.missing, (unsigned long long)exported.truncated,
            exported.error.empty() ? "none" : exported.error.c_str()]);
        dispatch_async(dispatch_get_main_queue(), ^{
          if (done) done(exported.ok ? output : nil);
        });
      });
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

  // These host boot boundaries do not also arrive as core_log. Core boot
  // reports are already mirrored by writeDiagnosticStage and are not doubled.
  if ([stageCopy isEqualToString:@"game_boot_begin"] || [stageCopy isEqualToString:@"game_boot_return"]) {
    dispatch_async(_diagnosticQueue, ^{
      @autoreleasepool {
        @try {
          [self writeCauseStage:stageCopy message:messageCopy timestamp:timestamp
                 monotonicBegin:monotonicBegin monotonicEnd:monotonicEnd];
        } @catch (__unused NSException* exception) {
        }
        // REWINDBOX_INCIDENT_REPORT_621: a new session record and incident model.
        @try {
          if ([stageCopy isEqualToString:@"game_boot_begin"])
            [self beginIncidentSession:messageCopy timestamp:timestamp];
        } @catch (__unused NSException* exception) {
        }
      }
    });
  }

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
    self->_causeTitle = self->_causeSession = self->_causeBootKind = nil;
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
  RPCS3FatalSlotShared().set_path(RPCS3StdString([self fatalSlotPath]));
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

// REWINDBOX_CORE_LOG_BOUNDED_621 / REWINDBOX_INCIDENT_REPORT_621 (Rpcs3Diagnostics.h).
void RPCS3CoreLogLine(NSString* message, uint64_t reservedBytes) {
  [RPCS3SharedDiagnosticsWriter() writeDiagnosticStage:@"core_log" message:message reserved:reservedBytes];
}

void RPCS3RecordFatalLine(const char* message, BOOL gameStopped) {
  if (!message) return;
  RPCS3DiagnosticsWriter* writer = RPCS3SharedDiagnosticsWriter();
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    RPCS3FatalSlotShared().set_path(RPCS3StdString([writer fatalSlotPath]));
  });
  // One write(2) before returning: report_fatal_error aborts right after.
  RPCS3FatalSlotShared().write(message, NSDate.date.timeIntervalSince1970);
  [writer recordFatal:[NSString stringWithUTF8String:message] ?: @"" gameStopped:gameStopped];
}

void RPCS3DiagnosticsDrain(uint32_t timeoutMs) {
  [RPCS3SharedDiagnosticsWriter() drainWithin:timeoutMs];
}

void RPCS3HostState(BOOL menuOpen, BOOL background) {
  [RPCS3SharedDiagnosticsWriter() hostMenuOpen:menuOpen background:background];
}

void RPCS3SessionStopped(void) {
  [RPCS3SharedDiagnosticsWriter() sessionStopped];
}

NSString* _Nullable RPCS3TakePreviousSessionIncident(void) {
  return [RPCS3SharedDiagnosticsWriter() takePreviousSessionIncident];
}

void RPCS3BuildIncidentReport(void (^completion)(NSString* _Nullable path)) {
  [RPCS3SharedDiagnosticsWriter() buildReport:completion];
}

#if defined(RPCS3_DIAGNOSTICS_TESTING)
void RPCS3DiagnosticsSetDirectoryForTesting(NSString* directory) {
  [RPCS3SharedDiagnosticsWriter() setDirectoryForTesting:directory];
}

void RPCS3DiagnosticsFlushForTesting(void) {
  [RPCS3SharedDiagnosticsWriter() flushForTesting];
}
#endif
