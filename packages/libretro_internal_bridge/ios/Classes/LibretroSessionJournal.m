#import "LibretroSessionJournal.h"
#include "LibretroCrashCapture.h"

#include <fcntl.h>
#include <mach/mach_time.h>
#include <os/lock.h>
#include <unistd.h>
#include <pthread.h>
#include <mach-o/dyld.h>
#include <stdatomic.h>

static _Atomic uintptr_t gNativeCaptureOwner;

static NSString *const kCurrentName = @"session.log";
static NSString *const kPreviousName = @"previous-session.log";
static NSString *const kUnfinishedName = @"unfinished-session.log";
static NSString *const kFailedLaunchName = @"failed-launch.log";
static NSString *const kFailedLaunchOutcome = @"launch failed";
static NSString *const kEndMarker = @"\nEND ";

/// A finished journal ends with its END line; only the tail is searched.
static BOOL JournalHasEnd(NSData *data) {
  NSData *marker = [kEndMarker dataUsingEncoding:NSUTF8StringEncoding];
  NSUInteger tail = MIN(data.length, (NSUInteger)4096);
  NSRange range = [data rangeOfData:marker
                            options:NSDataSearchBackwards
                              range:NSMakeRange(data.length - tail, tail)];
  return range.location != NSNotFound;
}

static NSString *JournalTimestamp(void) {
  static NSISO8601DateFormatter *formatter;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    formatter = [NSISO8601DateFormatter new];
    formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
  });
  return [formatter stringFromDate:[NSDate date]];
}

@implementation LibretroSessionJournal {
  os_unfair_lock _lock;
  int _descriptor;
  uint64_t _start;
  mach_timebase_info_data_t _timebase;
}

+ (instancetype)journalInDirectory:(NSString *)directory {
  if (directory.length == 0) return nil;
  NSFileManager *files = NSFileManager.defaultManager;
  [files createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
  NSString *current = [directory stringByAppendingPathComponent:kCurrentName];
  BOOL unfinished = NO;
  if ([files fileExistsAtPath:current]) {
    NSData *data = [NSData dataWithContentsOfFile:current options:NSDataReadingMappedIfSafe error:nil];
    unfinished = data.length > 0 && !JournalHasEnd(data);
    if (unfinished) {
      // Kept until a later unfinished session replaces it.
      NSString *kept = [directory stringByAppendingPathComponent:kUnfinishedName];
      [files removeItemAtPath:kept error:nil];
      [files copyItemAtPath:current toPath:kept error:nil];
    }
    NSString *previous = [directory stringByAppendingPathComponent:kPreviousName];
    [files removeItemAtPath:previous error:nil];
    [files moveItemAtPath:current toPath:previous error:nil];
  }
  int descriptor = open(current.fileSystemRepresentation, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
  if (descriptor < 0) return nil;
  LibretroSessionJournal *journal = [[self alloc] init];
  journal->_descriptor = descriptor;
  journal->_start = mach_absolute_time();
  mach_timebase_info(&journal->_timebase);
  journal->_previousSessionUnfinished = unfinished;
  journal->_path = [current copy];
  journal->_sessionIdentifier = NSUUID.UUID.UUIDString;
  [journal writeText:[NSString stringWithFormat:@"RewindBox libretro session journal 1, started %@\n",
                                                JournalTimestamp()]];
  static int crashDescriptor = -1;
  static dispatch_once_t captureOnce;
  dispatch_once(&captureOnce, ^{
    NSString *crash = [directory stringByAppendingPathComponent:@"native-termination.log"];
    NSData *priorCrash = [NSData dataWithContentsOfFile:crash];
    NSData *fatal = [@"\nfatal signal=" dataUsingEncoding:NSUTF8StringEncoding];
    if (priorCrash.length > 0 && [priorCrash rangeOfData:fatal options:0
        range:NSMakeRange(0, priorCrash.length)].location != NSNotFound) {
      NSString *kept = [directory stringByAppendingPathComponent:@"previous-native-termination.log"];
      [files removeItemAtPath:kept error:nil];
      [files moveItemAtPath:crash toPath:kept error:nil];
    }
    crashDescriptor = open(crash.fileSystemRepresentation, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
  });
  unsigned capturedSignals = LibretroInstallCrashCapture(crashDescriptor);
  atomic_store(&gNativeCaptureOwner, (uintptr_t)(__bridge void *)journal);
  NSString *identity = [NSString stringWithFormat:@"session=%@ pid=%d main-slide=0x%llx fatal-signal-mask=0x%x",
    journal.sessionIdentifier, getpid(), (unsigned long long)_dyld_get_image_vmaddr_slide(0), capturedSignals];
  // Only the latest session identity is needed; keep the crash file bounded
  // during long launch/relaunch runs. A fatal write appends after this header.
  if (crashDescriptor >= 0) {
    ftruncate(crashDescriptor, 0);
    NSData *header = [[identity stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    ssize_t written = write(crashDescriptor, header.bytes, header.length);
    (void)written;
  }
  [journal note:identity];
  if (unfinished) [journal note:@"the previous session ended without its END line: kept as unfinished-session.log"];
  return journal;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _descriptor = -1;
    _lock = OS_UNFAIR_LOCK_INIT;
  }
  return self;
}

- (void)dealloc {
  uintptr_t owner = (uintptr_t)(__bridge void *)self;
  if (atomic_compare_exchange_strong(&gNativeCaptureOwner, &owner, 0)) LibretroUninstallCrashCapture();
  if (_descriptor >= 0) close(_descriptor);
}

/// Appends `text` as is; nothing once the journal is finished.
- (void)writeText:(NSString *)text {
  NSData *data = [text dataUsingEncoding:NSUTF8StringEncoding allowLossyConversion:YES];
  os_unfair_lock_lock(&_lock);
  if (_descriptor >= 0) {
    const uint8_t *bytes = data.bytes;
    size_t remaining = data.length;
    while (remaining > 0) {
      ssize_t written = write(_descriptor, bytes, remaining);
      if (written <= 0) break;
      bytes += written;
      remaining -= (size_t)written;
    }
  }
  os_unfair_lock_unlock(&_lock);
}

- (void)note:(NSString *)line {
  double seconds = (double)(mach_absolute_time() - _start) * _timebase.numer / _timebase.denom / 1e9;
  NSString *single = [[line ?: @"" componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]
      componentsJoinedByString:@" | "];
  uint64_t thread = 0;
  pthread_threadid_np(NULL, &thread);
  [self writeText:[NSString stringWithFormat:@"%@ +%.3fs [session=%@ thread=%llu %@] %@\n", JournalTimestamp(), seconds,
    _sessionIdentifier, (unsigned long long)thread, NSThread.isMainThread ? @"main" : (NSThread.currentThread.name ?: @"worker"), single]];
}

- (void)noteLines:(NSArray<NSString *> *)lines title:(NSString *)title {
  NSMutableString *block = [NSMutableString stringWithFormat:@"---- %@ (%lu lines) ----\n", title,
                                                             (unsigned long)lines.count];
  for (NSString *line in lines) [block appendFormat:@"  %@\n", line];
  [block appendFormat:@"---- end of %@ ----\n", title];
  [self writeText:block];
}

- (void)noteLoadedImages {
  NSString *bundle = NSBundle.mainBundle.bundlePath;
  uint32_t count = _dyld_image_count();
  for (uint32_t index = 0; index < count; index++) {
    const char *name = _dyld_get_image_name(index);
    NSString *path = name ? @(name) : nil;
    if (![path hasPrefix:bundle]) continue;
    const struct mach_header *header = _dyld_get_image_header(index);
    if (header == NULL || header->magic != MH_MAGIC_64) continue;
    const struct mach_header_64 *wide = (const struct mach_header_64 *)header;
    const uint8_t *command = (const uint8_t *)(wide + 1), *end = command + wide->sizeofcmds;
    NSString *uuid = @"unknown";
    for (uint32_t n = 0; n < wide->ncmds && command + sizeof(struct load_command) <= end; n++) {
      const struct load_command *load = (const struct load_command *)command;
      if (load->cmdsize < sizeof(*load) || load->cmdsize > (size_t)(end-command)) break;
      if (load->cmd == LC_UUID && load->cmdsize >= sizeof(struct uuid_command)) {
        uuid = [[NSUUID alloc] initWithUUIDBytes:((const struct uuid_command *)command)->uuid].UUIDString;
        break;
      }
      command += load->cmdsize;
    }
    [self note:[NSString stringWithFormat:@"image: %@ uuid=%@ address=%p slide=0x%llx", path.lastPathComponent,
      uuid, header, (unsigned long long)_dyld_get_image_vmaddr_slide(index)]];
  }
}

- (void)finishWithOutcome:(NSString *)outcome {
  [self note:[NSString stringWithFormat:@"session %@", outcome]];
  [self writeText:[NSString stringWithFormat:@"END %@\n", outcome]];
  os_unfair_lock_lock(&_lock);
  BOOL closed = _descriptor >= 0;
  if (closed) {
    close(_descriptor);
    _descriptor = -1;
  }
  os_unfair_lock_unlock(&_lock);
  if (closed) {
    uintptr_t owner = (uintptr_t)(__bridge void *)self;
    if (atomic_compare_exchange_strong(&gNativeCaptureOwner, &owner, 0)) LibretroUninstallCrashCapture();
  }
  if (closed && [outcome hasPrefix:kFailedLaunchOutcome]) {
    // Kept until another launch fails: the sessions after it rotate
    // session.log and previous-session.log away.
    NSFileManager *files = NSFileManager.defaultManager;
    NSString *kept = [_path.stringByDeletingLastPathComponent stringByAppendingPathComponent:kFailedLaunchName];
    [files removeItemAtPath:kept error:nil];
    [files copyItemAtPath:_path toPath:kept error:nil];
  }
}

@end
