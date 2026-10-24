#import "Rpcs3Diagnostics.h"

#import <Foundation/Foundation.h>
#include <sys/stat.h>
#include <unistd.h>
#include <chrono>

static const unsigned long long kRPCS3DiagnosticLimit = 2 * 1024 * 1024;
static const unsigned long long kRPCS3MilestoneLimit = 512 * 1024;
static const unsigned long long kRPCS3RuntimeHistoryLimit = 2 * 1024 * 1024;
static uint64_t RPCS3MonotonicUs() {
  return std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}
// A separate bounded history excludes verbose restore-constructor traces.
// It shares the existing asynchronous diagnostics worker, not a guest thread.
static BOOL RPCS3KeepRuntimeHistory(NSString* message) {
  for (NSString* token in @[@"COREPROF ", @"SPUPROF ", @"JITPROF ",
      @"JITPROF_BOOT ", @"CONFIG_LAYERS ", @"JITMEM ", @"NEOSWAP_VDEC ",
      @"FREEZE_DUMP snapshot\n", @"SAVESTATE_RESTORE phase=missing_resource ",
      @"SAVESTATE_RESTORE phase=fxo_resource_abort ",
      @"SAVESTATE_RESTORE phase=worker_exception"])
    if ([message rangeOfString:token].location != NSNotFound) return YES;
  return NO;
}

@interface RPCS3DiagnosticsWriter : NSObject
- (void)writeDiagnosticStage:(nullable NSString*)stage
                      message:(nullable NSString*)message;
- (void)writeMilestoneStage:(nullable NSString*)stage
                     message:(nullable NSString*)message;
#if defined(RPCS3_DIAGNOSTICS_TESTING)
- (void)setDirectoryForTesting:(NSString*)directory;
- (void)flushForTesting;
#endif
@end

@implementation RPCS3DiagnosticsWriter {
  dispatch_queue_t _diagnosticQueue;
  NSObject* _milestoneLock;
  NSString* _diagnosticPath;
  NSString* _milestonePath;
  NSFileHandle* _diagnosticFile;
  unsigned long long _diagnosticLength;
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

- (void)closeDiagnosticFile {
  @try {
    [_diagnosticFile closeFile];
  } @catch (__unused NSException* exception) {
  }
  _diagnosticFile = nil;
  _diagnosticLength = 0;
}

- (BOOL)diagnosticFileStillOwnsPath:(NSString*)path {
  if (!_diagnosticFile || path.length == 0) return NO;
  struct stat descriptorInfo = {};
  struct stat pathInfo = {};
  if (fstat(_diagnosticFile.fileDescriptor, &descriptorInfo) != 0 ||
      stat(path.fileSystemRepresentation, &pathInfo) != 0) {
    return NO;
  }
  return descriptorInfo.st_dev == pathInfo.st_dev &&
      descriptorInfo.st_ino == pathInfo.st_ino;
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
  NSString* previous = [[path stringByDeletingPathExtension]
      stringByAppendingString:@".1.log"];
  [self closeDiagnosticFile];
  NSFileManager* files = NSFileManager.defaultManager;
  [files removeItemAtPath:previous error:nil];
  const BOOL moved = [files moveItemAtPath:path toPath:previous error:nil];
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

- (void)writeRuntimeHistory:(NSData*)line {
  // No extra RAM cache, allocation reserve or synchronous flush. The current
  // plus one previous generation occupy at most 4 MiB on disk.
  if (!line.length || line.length > kRPCS3RuntimeHistoryLimit) return;
  NSString* directory = [self documentsDirectory];
  if (!directory.length) return;
  NSString* path = [directory stringByAppendingPathComponent:@"RPCS3-performance.log"];
  NSFileManager* files = NSFileManager.defaultManager;
  unsigned long long size = [[files attributesOfItemAtPath:path error:nil] fileSize];
  if (size + line.length > kRPCS3RuntimeHistoryLimit) {
    NSString* previous = [directory stringByAppendingPathComponent:@"RPCS3-performance.1.log"];
    [files removeItemAtPath:previous error:nil];
    if (![files moveItemAtPath:path toPath:previous error:nil]) {
      // Rotation failure retains a bounded current file, as the main writer.
      NSFileHandle* old = [NSFileHandle fileHandleForWritingAtPath:path];
      [old truncateFileAtOffset:0]; [old closeFile];
    }
  }
  if (![files fileExistsAtPath:path]) [files createFileAtPath:path contents:nil attributes:nil];
  NSFileHandle* file = [NSFileHandle fileHandleForWritingAtPath:path];
  [file seekToEndOfFile]; [file writeData:line]; [file closeFile];
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
          [file truncateFileAtOffset:0];
          [file seekToFileOffset:0];
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

#if defined(RPCS3_DIAGNOSTICS_TESTING)
void RPCS3DiagnosticsSetDirectoryForTesting(NSString* directory) {
  [RPCS3SharedDiagnosticsWriter() setDirectoryForTesting:directory];
}

void RPCS3DiagnosticsFlushForTesting(void) {
  [RPCS3SharedDiagnosticsWriter() flushForTesting];
}
#endif
