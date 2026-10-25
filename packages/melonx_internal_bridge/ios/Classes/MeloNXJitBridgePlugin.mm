#import "MeloNXJitBridgePlugin.h"

#import <Foundation/Foundation.h>
#import <Security/Security.h>
#import <UIKit/UIKit.h>
#import <objc/message.h>
#import <poll.h>
#import <stdio.h>
#import <string.h>
#import <arpa/inet.h>
#import <netinet/in.h>
#import <sys/socket.h>
#import <sys/types.h>
#import <sys/sysctl.h>
#import <unistd.h>
#import <mach/mach.h>
#import <os/proc.h>
#import <sys/mman.h>
#import <libkern/OSCacheControl.h>

static void MeloNXDiagnostic(NSString* stage, NSString* message) {
  NSLog(@"[MeloNX:JIT] %@ %@", stage ?: @"", message ?: @"");
  // Export legacy startup evidence only; modern JIT timing remains unchanged.
  if (NSProcessInfo.processInfo.operatingSystemVersion.majorVersion >= 26) return;
  @autoreleasepool {
    NSURL* documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory
        inDomains:NSUserDomainMask].firstObject;
    if (documents == nil) return;
    NSString* path = [documents URLByAppendingPathComponent:@"melonx_jit_debug.log"].path;
    FILE* file = fopen(path.fileSystemRepresentation, "a");
    if (file == NULL) return;
    fseek(file, 0, SEEK_END);
    if (ftell(file) > 524288) {
      fclose(file);
      file = fopen(path.fileSystemRepresentation, "w");
      if (file == NULL) return;
    }
    NSString* bounded = message.length > 4096 ? [message substringToIndex:4096] : message;
    NSString* line = [NSString stringWithFormat:@"%@ %@ %@\n", NSDate.date,
        stage ?: @"", bounded ?: @""];
    NSData* data = [line dataUsingEncoding:NSUTF8StringEncoding];
    if (data.length) fwrite(data.bytes, 1, data.length, file);
    fclose(file);
  }
}
static void MeloNXMilestone(NSString* stage, NSString* message) {
  NSLog(@"[MeloNX:JIT:MILESTONE] %@ %@", stage ?: @"", message ?: @"");
}

static NSString* const kMeloNXJitChannel = @"neostation/melonx_jit";
static NSString* const kMeloNXJitRequestType = @"com.neogamelab.neostation.melonx-jit-request";
static NSTimeInterval const kMeloNXHelperConnectTimeout = 30.0;
// First use may download and mount a DDI. Dart allows this native deadline
// (plus the connection deadline) to finish and report its actual error.
static NSTimeInterval const kMeloNXAttachTimeout = 600.0;
static NSTimeInterval const kMeloNXCompletionTimeout = 120.0;

extern "C" {
void* SecTaskCreateFromSelf(CFAllocatorRef allocator);
CFTypeRef SecTaskCopyValueForEntitlement(
    void* task,
    CFStringRef entitlement,
    CFErrorRef* error);
int csops(pid_t pid, unsigned int ops, void* useraddr, size_t usersize);
}

#ifndef CS_OPS_STATUS
#define CS_OPS_STATUS 0
#endif
#ifndef CS_DEBUGGED
#define CS_DEBUGGED 0x10000000
#endif

static BOOL MeloNXHostHasGetTaskAllow(void) {
  void* task = SecTaskCreateFromSelf(NULL);
  if (task == NULL) return NO;
  CFTypeRef value = SecTaskCopyValueForEntitlement(
      task,
      CFSTR("get-task-allow"),
      NULL);
  BOOL allowed = value == kCFBooleanTrue;
  if (value != NULL) CFRelease(value);
  CFRelease(task);
  return allowed;
}

NSDictionary* MeloNXMemoryEntitlements(void) {
  void* task = SecTaskCreateFromSelf(NULL);
  if (task == NULL) return @{ @"checked": @NO, @"allowed": @NO };
  CFTypeRef memory = SecTaskCopyValueForEntitlement(task,
      CFSTR("com.apple.developer.kernel.increased-memory-limit"), NULL);
  CFTypeRef extended = SecTaskCopyValueForEntitlement(task,
      CFSTR("com.apple.developer.kernel.extended-virtual-addressing"), NULL);
  BOOL hasMemory = memory == kCFBooleanTrue;
  BOOL hasExtended = extended == kCFBooleanTrue;
  if (memory != NULL) CFRelease(memory);
  if (extended != NULL) CFRelease(extended);
  CFRelease(task);
  // Upstream's device capability test reserves address space only. No RAM is
  // committed, and every successful mapping is released immediately.
  BOOL needsExtended = NO;
  if (!hasExtended) {
    static dispatch_once_t capacityOnce;
    static BOOL capacityRequiresExtended = NO;
    dispatch_once(&capacityOnce, ^{
      size_t length = (size_t)4 * 1024 * 1024 * 1024;
      void* address = mmap(NULL, length, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
      capacityRequiresExtended = address == MAP_FAILED;
      if (address != MAP_FAILED && munmap(address, length) != 0) capacityRequiresExtended = YES;
    });
    needsExtended = capacityRequiresExtended;
  }
  BOOL allowed = hasMemory && (hasExtended || !needsExtended);
  return @{ @"checked": @YES, @"allowed": allowed ? @YES : @NO,
      @"increasedMemoryLimit": hasMemory ? @YES : @NO,
      @"extendedVirtualAddressing": hasExtended ? @YES : @NO,
      @"extendedRequired": needsExtended ? @YES : @NO };
}

static BOOL MeloNXHostIsDebugged(void) {
  uint32_t flags = 0;
  if (csops(getpid(), CS_OPS_STATUS, &flags, sizeof(flags)) != 0) return NO;
  return (flags & CS_DEBUGGED) != 0;
}

static BOOL MeloNXHostHasLiveDebugger(void) {
  int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()};
  struct kinfo_proc info = {};
  size_t size = sizeof(info);
  return sysctl(mib, 4, &info, &size, NULL, 0) == 0 &&
      size == sizeof(info) && (info.kp_proc.p_flag & P_TRACED) != 0;
}

NSDictionary* MeloNXJitExecutableMappingProbe(void) {
#if defined(__arm64__)
  if (!MeloNXHostIsDebugged()) return @{@"success": @NO, @"message": @"JIT is absent for the RewindBox process."};
  const size_t size = (size_t)getpagesize();
  void* rx = mmap(NULL, size, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
  if (rx == MAP_FAILED) return @{@"success": @NO, @"message": @"The selected JIT method cannot allocate an executable mapping."};
  vm_address_t rw = 0;
  vm_prot_t current = 0, maximum = 0;
  kern_return_t result = vm_remap(mach_task_self(), &rw, size, 0, VM_FLAGS_ANYWHERE,
      mach_task_self(), (vm_address_t)rx, FALSE, &current, &maximum, VM_INHERIT_NONE);
  if (result != KERN_SUCCESS) {
    munmap(rx, size);
    return @{@"success": @NO, @"message": @"The selected JIT method cannot create the writable alias required by MeloNX."};
  }
  result = vm_protect(mach_task_self(), rw, size, FALSE, VM_PROT_READ | VM_PROT_WRITE);
  BOOL executable = NO;
  if (result == KERN_SUCCESS) {
    // mov w0, #0x4d4c; ret. This page is real test code, not a RAM donation.
    const uint32_t code[] = {0x5289a980, 0xd65f03c0};
    memcpy((void*)rw, code, sizeof(code));
    sys_icache_invalidate(rx, sizeof(code));
    typedef uint32_t (*MeloNXProbeFunction)(void);
    executable = ((MeloNXProbeFunction)rx)() == 0x4d4c;
  }
  vm_deallocate(mach_task_self(), rw, size);
  munmap(rx, size);
  return @{@"success": @(executable), @"pid": @(getpid()),
      @"message": executable ? @"RewindBox executed code through distinct RX/RW aliases." : @"Executable alias validation failed."};
#else
  return @{@"success": @NO, @"message": @"The executable probe requires ARM64."};
#endif
}

static BOOL MeloNXRequiresCoreHandshake(void) {
  if (@available(iOS 26.0, *)) return YES;
  return NO;
}

// No allocation, Core code or executable-memory preparation occurs in this
// probe. The script must advance PC, set x0 and continue this exact host thread.
#if defined(__arm64__)
__attribute__((naked, noinline)) static uint64_t MeloNXDebuggerProbe(uint64_t nonce) {
  __asm__("mov x16, #3\n" "brk #0xf00d\n" "ret");
}
#else
static uint64_t MeloNXDebuggerProbe(uint64_t nonce) { return 0; }
#endif

@interface MeloNXJitSession : NSObject
@property(nonatomic, readonly) uint16_t port;
@property(nonatomic, readonly) uint32_t probeNonce;
@property(nonatomic, readonly) NSString* token;
@property(nonatomic, readonly) BOOL connected;
@property(nonatomic, readonly) BOOL attached;
@property(nonatomic, readonly) BOOL coreLoadReady;
@property(nonatomic, readonly) BOOL finished;
@property(nonatomic, readonly) BOOL success;
@property(nonatomic, readonly) NSString* finalMessage;
@property(nonatomic, readonly) NSArray<NSString*>* logs;
@property(nonatomic, readonly) BOOL closed;
@property(nonatomic, assign) BOOL requiresCoreHandshake;
@property(nonatomic, strong, nullable) id extensionObject;
@property(nonatomic, strong, nullable) id requestIdentifier;
- (nullable instancetype)initWithError:(NSError**)error;
- (void)startReader;
- (BOOL)waitUntilConnected:(NSTimeInterval)timeout;
- (BOOL)waitUntilAttached:(NSTimeInterval)timeout;
- (BOOL)confirmCoreLoadReady;
- (BOOL)waitUntilFinished:(NSTimeInterval)timeout;
- (void)close;
@end

@implementation MeloNXJitSession {
  int _listener;
  int _client;
  uint16_t _port;
  uint32_t _probeNonce;
  NSString* _token;
  NSCondition* _condition;
  BOOL _connected;
  BOOL _attached;
  BOOL _coreLoadReady;
  BOOL _finished;
  BOOL _success;
  BOOL _closed;
  NSString* _finalMessage;
  NSMutableArray<NSString*>* _mutableLogs;
  dispatch_queue_t _readerQueue;
}

- (nullable instancetype)initWithError:(NSError**)error {
  self = [super init];
  if (!self) return nil;

  _listener = socket(AF_INET, SOCK_STREAM, 0);
  _client = -1;
  if (_listener < 0) {
    if (error != NULL) {
      *error = [NSError errorWithDomain:@"NeoStationMeloNX"
                                   code:2101
                               userInfo:@{NSLocalizedDescriptionKey : @"Could not create the MeloNX JIT helper socket."}];
    }
    return nil;
  }

  int reuse = 1;
  setsockopt(_listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
  struct sockaddr_in address = {};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = 0;
  if (bind(_listener, (struct sockaddr*)&address, sizeof(address)) != 0 ||
      listen(_listener, 1) != 0) {
    close(_listener);
    _listener = -1;
    if (error != NULL) {
      *error = [NSError errorWithDomain:@"NeoStationMeloNX"
                                   code:2102
                               userInfo:@{NSLocalizedDescriptionKey : @"Could not bind the MeloNX JIT helper socket."}];
    }
    return nil;
  }

  socklen_t length = sizeof(address);
  if (getsockname(_listener, (struct sockaddr*)&address, &length) != 0) {
    close(_listener);
    _listener = -1;
    if (error != NULL) {
      *error = [NSError errorWithDomain:@"NeoStationMeloNX"
                                   code:2103
                               userInfo:@{NSLocalizedDescriptionKey : @"Could not determine the MeloNX JIT helper port."}];
    }
    return nil;
  }

  _port = ntohs(address.sin_port);
  _token = NSUUID.UUID.UUIDString;
  _probeNonce = arc4random_uniform(UINT32_MAX - 1) + 1;
  _condition = [NSCondition new];
  _mutableLogs = [NSMutableArray new];
  _finalMessage = @"";
  _readerQueue = dispatch_queue_create(
      "com.neogamelab.neostation.melonx.helper-reader",
      DISPATCH_QUEUE_SERIAL);
  return self;
}

- (uint16_t)port { return _port; }
- (uint32_t)probeNonce { return _probeNonce; }
- (NSString*)token { return _token; }

- (BOOL)closed {
  [_condition lock];
  BOOL value = _closed;
  [_condition unlock];
  return value;
}

- (void)cancelExtensionRequest {
  id extension = self.extensionObject;
  id identifier = self.requestIdentifier;
  if (!extension || !identifier) return;
  dispatch_async(dispatch_get_main_queue(), ^{
    SEL selector = NSSelectorFromString(@"cancelExtensionRequestWithIdentifier:");
    if ([extension respondsToSelector:selector]) {
      void (*cancelMessage)(id, SEL, id) =
          reinterpret_cast<void (*)(id, SEL, id)>(objc_msgSend);
      cancelMessage(extension, selector, identifier);
    }
  });
}

- (BOOL)connected {
  [_condition lock];
  BOOL value = _connected;
  [_condition unlock];
  return value;
}

- (BOOL)attached {
  [_condition lock];
  BOOL value = _attached;
  [_condition unlock];
  return value;
}

- (BOOL)coreLoadReady {
  [_condition lock];
  BOOL value = _coreLoadReady;
  [_condition unlock];
  return value;
}

- (BOOL)finished {
  [_condition lock];
  BOOL value = _finished;
  [_condition unlock];
  return value;
}

- (BOOL)success {
  [_condition lock];
  BOOL value = _success;
  [_condition unlock];
  return value;
}

- (NSString*)finalMessage {
  [_condition lock];
  NSString* value = [_finalMessage copy];
  [_condition unlock];
  return value;
}

- (NSArray<NSString*>*)logs {
  [_condition lock];
  NSArray<NSString*>* value = [_mutableLogs copy];
  [_condition unlock];
  return value;
}

- (void)markFinished:(BOOL)success message:(NSString*)message {
  [_condition lock];
  _finished = YES;
  _success = success;
  _finalMessage = message ?: @"";
  [_condition broadcast];
  [_condition unlock];
}

- (void)startReader {
  __weak MeloNXJitSession* weakSelf = self;
  dispatch_async(_readerQueue, ^{
    MeloNXJitSession* strongSelf = weakSelf;
    if (strongSelf == nil) return;

    struct pollfd descriptor = {strongSelf->_listener, POLLIN, 0};
    int pollResult = poll(
        &descriptor,
        1,
        (int)(kMeloNXHelperConnectTimeout * 1000.0));
    if (pollResult <= 0) {
      [strongSelf markFinished:NO
                       message:@"The MeloNX JIT helper did not connect to RewindBox."];
      return;
    }

    int accepted = accept(strongSelf->_listener, NULL, NULL);
    if (accepted < 0) {
      [strongSelf markFinished:NO
                       message:@"The MeloNX JIT helper socket could not be accepted."];
      return;
    }

    FILE* stream = fdopen(accepted, "r");
    if (stream == NULL) {
      close(accepted);
      [strongSelf markFinished:NO
                       message:@"The MeloNX JIT helper stream could not be opened."];
      return;
    }
    // Keep a duplicate solely for shutdown. fclose owns the original fd;
    // closing a timed-out session must also unblock its fgets reader.
    [strongSelf->_condition lock];
    if (strongSelf->_closed) {
      [strongSelf->_condition unlock];
      fclose(stream);
      return;
    }
    strongSelf->_client = dup(fileno(stream));
    [strongSelf->_condition unlock];

    char buffer[65536];
    while (fgets(buffer, sizeof(buffer), stream) != NULL) {
      @autoreleasepool {
        NSString* line = [[NSString alloc] initWithUTF8String:buffer];
        line = [line stringByTrimmingCharactersInSet:
            NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if (line.length == 0) continue;
        NSData* data = [line dataUsingEncoding:NSUTF8StringEncoding];
        NSDictionary* payload = [NSJSONSerialization JSONObjectWithData:data
                                                                 options:0
                                                                   error:nil];
        if (![payload isKindOfClass:NSDictionary.class] ||
            ![payload[@"token"] isEqualToString:strongSelf->_token]) {
          continue;
        }

        NSString* event = [payload[@"event"] isKindOfClass:NSString.class]
            ? payload[@"event"]
            : @"unknown";
        NSString* message = [payload[@"message"] isKindOfClass:NSString.class]
            ? payload[@"message"]
            : @"";

        if (message.length > 0) {
          NSString* bounded = message.length > 4096
              ? [message substringToIndex:4096]
              : message;
          MeloNXDiagnostic([@"jit_helper_" stringByAppendingString:event], bounded);
        }

        [strongSelf->_condition lock];
        if ([event isEqualToString:@"helper_connected"]) {
          strongSelf->_connected = YES;
        } else if ([event isEqualToString:@"pid_attached"] &&
                   strongSelf->_connected) {
          NSNumber* targetPID = [payload[@"targetPID"] isKindOfClass:NSNumber.class]
              ? payload[@"targetPID"]
              : nil;
          if ([targetPID isEqualToNumber:@(getpid())]) {
            strongSelf->_attached = YES;
          }
        } else if ([event isEqualToString:@"log"]) {
          if (message.length > 0) {
            [strongSelf->_mutableLogs addObject:message];
            if (strongSelf->_mutableLogs.count > 64) {
              [strongSelf->_mutableLogs removeObjectAtIndex:0];
            }
          }
        } else if ([event isEqualToString:@"complete"]) {
          strongSelf->_finished = YES;
          strongSelf->_success = [payload[@"success"] boolValue];
          strongSelf->_finalMessage = message ?: @"";
        }
        [strongSelf->_condition broadcast];
        [strongSelf->_condition unlock];
      }
      if (strongSelf.finished) break;
    }
    fclose(stream);
    if (!strongSelf.finished) {
      [strongSelf markFinished:NO
                       message:@"The MeloNX JIT helper disconnected before completing the transaction."];
    }
  });
}

- (BOOL)waitForPredicate:(BOOL (^)(void))predicate
                 timeout:(NSTimeInterval)timeout {
  NSDate* deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
  [_condition lock];
  while (!predicate()) {
    if (![_condition waitUntilDate:deadline]) break;
  }
  BOOL value = predicate();
  [_condition unlock];
  return value;
}

- (BOOL)waitUntilConnected:(NSTimeInterval)timeout {
  [self waitForPredicate:^BOOL {
    return self->_connected || self->_finished || self->_closed;
  } timeout:timeout];
  return self.connected && !self.closed;
}

- (BOOL)waitUntilAttached:(NSTimeInterval)timeout {
  [self waitForPredicate:^BOOL {
    return self->_attached || self->_finished || self->_closed;
  } timeout:timeout];
  // StikJIT's pre-TXM attach/detach path does not log a universal vAttach
  // reply. Its successful completion is sufficient only on the legacy Core.
  return (self.attached && !self.closed && !self.finished) ||
      (!self.requiresCoreHandshake && self.connected && self.finished && self.success);
}

- (BOOL)confirmCoreLoadReady {
  if (!self.connected || !self.attached || self.finished || self.closed ||
      !MeloNXHostHasLiveDebugger()) return NO;
  MeloNXMilestone(@"debugger_probe_begin", @"Verifying debugger BRK/response/resume before dlopen");
  uint64_t response = MeloNXDebuggerProbe(_probeNonce);
  [_condition lock];
  _coreLoadReady = response == (uint64_t)_probeNonce + 1 && !_closed && !_finished;
  BOOL ready = _coreLoadReady;
  [_condition unlock];
  MeloNXMilestone(@"debugger_probe_end", ready ? @"verified target resumed with nonce response" : @"probe rejected; dlopen blocked");
  return ready;
}

- (BOOL)waitUntilFinished:(NSTimeInterval)timeout {
  return [self waitForPredicate:^BOOL {
    return self->_finished || self->_closed;
  } timeout:timeout];
}

- (void)close {
  [_condition lock];
  if (_closed) {
    [_condition unlock];
    return;
  }
  _closed = YES;
  if (_listener >= 0) {
    shutdown(_listener, SHUT_RDWR);
    close(_listener);
    _listener = -1;
  }
  if (_client >= 0) {
    shutdown(_client, SHUT_RDWR);
    close(_client);
    _client = -1;
  }
  [_condition broadcast];
  [_condition unlock];
  if (!self.finished) [self cancelExtensionRequest];
}

- (void)dealloc {
  [self close];
}

@end

static NSString* _Nullable MeloNXFindHelperBundleIdentifier(void) {
  NSURL* plugins = NSBundle.mainBundle.builtInPlugInsURL;
  if (plugins == nil) return nil;
  NSArray<NSURL*>* entries = [NSFileManager.defaultManager
      contentsOfDirectoryAtURL:plugins
    includingPropertiesForKeys:nil
                       options:0
                         error:nil];
  for (NSURL* entry in entries) {
    if (![entry.pathExtension.lowercaseString isEqualToString:@"appex"]) continue;
    NSBundle* bundle = [NSBundle bundleWithURL:entry];
    NSDictionary* extension = [bundle objectForInfoDictionaryKey:@"NSExtension"];
    NSString* point = [extension isKindOfClass:NSDictionary.class]
        ? extension[@"NSExtensionPointIdentifier"]
        : nil;
    NSString* marker = [bundle objectForInfoDictionaryKey:@"NeoStationMeloNXJITHelper"];
    if ([point isEqualToString:@"com.apple.share-services"] &&
        [marker isEqualToString:@"1"] &&
        bundle.bundleIdentifier.length > 0) {
      return bundle.bundleIdentifier;
    }
  }
  return nil;
}

static BOOL MeloNXLaunchJitHelper(
    MeloNXJitSession* session,
    NSData* pairingData,
    NSError** error) {
  NSString* helperIdentifier = MeloNXFindHelperBundleIdentifier();
  if (helperIdentifier.length == 0) {
    if (error != NULL) {
      *error = [NSError errorWithDomain:@"NeoStationMeloNX"
                                   code:2201
                               userInfo:@{NSLocalizedDescriptionKey : @"The embedded MeloNX JIT helper extension is missing."}];
    }
    return NO;
  }

  NSDictionary* request = @{
    @"protocolVersion" : @1,
    @"probeNonce" : @(session.probeNonce),
    @"targetPID" : @(getpid()),
    @"port" : @(session.port),
    @"token" : session.token,
    @"pairingData" : [pairingData base64EncodedStringWithOptions:0],
    @"requiresCoreHandshake" : @(session.requiresCoreHandshake),
  };
  NSData* requestData = [NSJSONSerialization dataWithJSONObject:request
                                                        options:0
                                                          error:error];
  if (requestData == nil) return NO;

  NSItemProvider* provider = [[NSItemProvider alloc]
      initWithItem:requestData
    typeIdentifier:kMeloNXJitRequestType];
  NSExtensionItem* item = [NSExtensionItem new];
  item.attachments = @[provider];

  Class extensionClass = NSClassFromString(@"NSExtension");
  SEL createSelector = NSSelectorFromString(@"extensionWithIdentifier:error:");
  SEL beginSelector = NSSelectorFromString(
      @"beginExtensionRequestWithInputItems:completion:");
  if (extensionClass == Nil ||
      ![extensionClass respondsToSelector:createSelector]) {
    if (error != NULL) {
      *error = [NSError errorWithDomain:@"NeoStationMeloNX"
                                   code:2202
                               userInfo:@{NSLocalizedDescriptionKey : @"This iOS build cannot start the embedded MeloNX JIT helper."}];
    }
    return NO;
  }

  id (*createMessage)(id, SEL, NSString*, NSError**) =
      reinterpret_cast<id (*)(id, SEL, NSString*, NSError**)>(objc_msgSend);
  id extensionObject = createMessage(
      extensionClass,
      createSelector,
      helperIdentifier,
      error);
  if (extensionObject == nil ||
      ![extensionObject respondsToSelector:beginSelector]) {
    return NO;
  }
  session.extensionObject = extensionObject;

  // Retain until launch returns its request identifier, even if the connection
  // timed out first, so that a late extension can still be cancelled.
  void (^completion)(id) = ^(id requestIdentifier) {
    session.requestIdentifier = requestIdentifier;
    if (session.closed) [session cancelExtensionRequest];
  };
  void (*beginMessage)(id, SEL, NSArray*, id) =
      reinterpret_cast<void (*)(id, SEL, NSArray*, id)>(objc_msgSend);
  beginMessage(extensionObject, beginSelector, @[item], completion);
  return YES;
}

@interface MeloNXJitBridgePlugin ()
@property(nonatomic, strong) FlutterMethodChannel* channel;
@property(atomic, strong, nullable) MeloNXJitSession* activeSession;
@property(nonatomic, assign) BOOL operationInProgress;
@property(nonatomic, assign) BOOL completionInProgress;
@end

static __weak MeloNXJitBridgePlugin* gMeloNXJitBridge;

BOOL MeloNXJitHasActiveCoreHandshake(void) {
  MeloNXJitSession* session = gMeloNXJitBridge.activeSession;
  return session != nil && session.requiresCoreHandshake &&
      session.attached && !session.finished && !session.closed &&
      MeloNXHostHasLiveDebugger();
}

BOOL MeloNXJitConfirmCoreLoadHandoff(void) {
  MeloNXJitSession* session = gMeloNXJitBridge.activeSession;
  if (session == nil || !session.requiresCoreHandshake ||
      !session.attached || session.finished || session.closed) {
    return NO;
  }
  return [session confirmCoreLoadReady];
}

BOOL MeloNXJitWaitForDetach(NSTimeInterval timeout, NSString** message) {
  MeloNXJitSession* session = gMeloNXJitBridge.activeSession;
  if (session == nil) {
    if (message) *message = @"No MeloNX JIT transaction is active.";
    return NO;
  }
  BOOL completed = [session waitUntilFinished:timeout];
  BOOL proofReady = !session.requiresCoreHandshake || session.coreLoadReady;
  BOOL success = completed && session.success && proofReady && MeloNXHostIsDebugged();
  if (message) {
    *message = success ? @"MeloNX helper detached and CS_DEBUGGED remains active." :
        (!proofReady ? @"MeloNX Core nonce handshake was not completed for this JIT transaction." :
         (session.finalMessage.length ? session.finalMessage : @"MeloNX helper did not confirm detach."));
  }
  if (completed && gMeloNXJitBridge.activeSession == session) {
    [session close];
    gMeloNXJitBridge.activeSession = nil;
    gMeloNXJitBridge.operationInProgress = NO;
    gMeloNXJitBridge.completionInProgress = NO;
  }
  return success;
}

void MeloNXJitAbortTransaction(void) {
  MeloNXJitSession* session = gMeloNXJitBridge.activeSession;
  [session close];
  gMeloNXJitBridge.activeSession = nil;
  gMeloNXJitBridge.operationInProgress = NO;
  gMeloNXJitBridge.completionInProgress = NO;
}

@implementation MeloNXJitBridgePlugin {
  dispatch_queue_t _jitQueue;
}

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar {
  FlutterMethodChannel* channel = [FlutterMethodChannel
      methodChannelWithName:kMeloNXJitChannel
            binaryMessenger:registrar.messenger];
  MeloNXJitBridgePlugin* instance = [MeloNXJitBridgePlugin new];
  gMeloNXJitBridge = instance;
  instance.channel = channel;
  [registrar addMethodCallDelegate:instance channel:channel];
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _jitQueue = dispatch_queue_create(
        "com.neogamelab.neostation.melonx.jit",
        DISPATCH_QUEUE_SERIAL);
  }
  return self;
}

- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {
  if ([call.method isEqualToString:@"status"]) {
    result(@{
      @"getTaskAllow" : @(MeloNXHostHasGetTaskAllow()),
      @"debugged" : @(MeloNXHostIsDebugged()),
      @"busy" : @(self.operationInProgress),
      @"requiresCoreHandshake" : @(MeloNXRequiresCoreHandshake()),
      @"message" : self.activeSession.logs.lastObject ?: @"",
    });
    return;
  }

  if ([call.method isEqualToString:@"completeJit"]) {
    MeloNXJitSession* session = self.activeSession;
    if (session == nil || self.completionInProgress) {
      result(@{@"success": @NO, @"message": @"No MeloNX JIT transaction is ready to complete."});
      return;
    }
    self.completionInProgress = YES;
    MeloNXMilestone(@"jit_completion_begin", @"Waiting for Universal detach confirmation");
    dispatch_async(_jitQueue, ^{
      BOOL completed = [session waitUntilFinished:kMeloNXCompletionTimeout];
      BOOL proofReady = !session.requiresCoreHandshake || session.coreLoadReady;
      BOOL success = completed && session.success && proofReady && MeloNXHostIsDebugged();
      NSString* failureMessage = !proofReady
          ? @"MeloNX Core nonce handshake was not completed for this JIT transaction."
          : (session.finalMessage.length ? session.finalMessage :
             @"MeloNX JIT helper did not confirm completion. Relaunch RewindBox before retrying.");
      NSDictionary* response = @{
        @"success": @(success),
        @"logs": session.logs,
        @"message": success ? @"MeloNX JIT arena prepared and helper detached." : failureMessage,
      };
      MeloNXMilestone(@"jit_completion_end", success ? @"detached" : @"failed or timed out");
      // A failed/incomplete handshake may still own a debugger. Keep the
      // transaction locked in that case instead of starting another attach.
      if (completed && self.activeSession == session) {
        [session close];
        self.activeSession = nil;
        self.operationInProgress = NO;
      }
      self.completionInProgress = NO;
      dispatch_async(dispatch_get_main_queue(), ^{ result(response); });
    });
    return;
  }

  if (![call.method isEqualToString:@"prepareJit"]) {
    result(FlutterMethodNotImplemented);
    return;
  }

  NSDictionary* args = [call.arguments isKindOfClass:NSDictionary.class]
      ? call.arguments
      : @{};
  NSString* pairingPath = [args[@"pairingFilePath"] isKindOfClass:NSString.class]
      ? args[@"pairingFilePath"]
      : @"";

  if (@available(iOS 17.4, *)) {
  } else {
    result(@{
      @"success" : @NO,
      @"message" : @"Embedded MeloNX requires iOS 17.4 or newer.",
    });
    return;
  }
  if (!MeloNXHostHasGetTaskAllow()) {
    result(@{
      @"success" : @NO,
      @"message" : @"This RewindBox installation does not preserve get-task-allow.",
    });
    return;
  }
  if (pairingPath.length == 0 ||
      ![NSFileManager.defaultManager isReadableFileAtPath:pairingPath]) {
    result(@{
      @"success" : @NO,
      @"message" : @"Import a readable pairing file before enabling MeloNX JIT.",
    });
    return;
  }

  @synchronized(self) {
    if (self.operationInProgress || self.activeSession != nil) {
      result(@{
        @"success" : @NO,
        @"message" : @"An MeloNX JIT operation is already running.",
      });
      return;
    }
    self.operationInProgress = YES;
  }

  dispatch_async(_jitQueue, ^{
    NSTimeInterval operationStarted = NSProcessInfo.processInfo.systemUptime;
    MeloNXMilestone(@"jit_prepare_begin", @"Launching MeloNX JIT helper");
    NSMutableDictionary* response = [@{
      @"success" : @NO,
      @"pid" : @(getpid()),
      @"helperConnected" : @NO,
      @"pidAttached" : @NO,
      @"coreLoadReady" : @NO,
      @"debugged" : @NO,
      @"logs" : @[],
    } mutableCopy];

    void (^finish)(void) = ^{
      MeloNXMilestone(@"jit_prepare_failed", response[@"message"] ?: @"unknown failure");
      @synchronized(self) {
        [self.activeSession close];
        self.activeSession = nil;
        self.operationInProgress = NO;
      }
      dispatch_async(dispatch_get_main_queue(), ^{
        result(response);
      });
    };

    NSData* pairingData = [[NSData alloc]
        initWithContentsOfFile:pairingPath
                       options:NSDataReadingMappedIfSafe
                         error:nil];
    if (pairingData.length == 0) {
      response[@"message"] = @"The stored pairing file could not be read.";
      finish();
      return;
    }

    NSError* sessionError = nil;
    MeloNXJitSession* session = [[MeloNXJitSession alloc]
        initWithError:&sessionError];
    if (session == nil) {
      response[@"message"] = sessionError.localizedDescription ?: @"Could not prepare the MeloNX JIT helper.";
      finish();
      return;
    }
    self.activeSession = session;
    session.requiresCoreHandshake = MeloNXRequiresCoreHandshake();
    [session startReader];

    NSError* launchError = nil;
    if (!MeloNXLaunchJitHelper(session, pairingData, &launchError)) {
      response[@"message"] = launchError.localizedDescription ?: @"Could not launch the MeloNX JIT helper.";
      finish();
      return;
    }
    if (![session waitUntilConnected:kMeloNXHelperConnectTimeout]) {
      response[@"message"] = session.finalMessage.length
          ? session.finalMessage
          : @"MeloNX JIT helper did not connect.";
      response[@"logs"] = session.logs;
      finish();
      return;
    }
    response[@"helperConnected"] = @YES;
    NSTimeInterval helperConnectedMs =
        (NSProcessInfo.processInfo.systemUptime - operationStarted) * 1000.0;
    response[@"helperConnectedMs"] = @(helperConnectedMs);
    MeloNXMilestone(
        @"jit_helper_connected",
        [NSString stringWithFormat:
            @"Authenticated helper control channel connected; elapsedMs=%.1f",
            helperConnectedMs]);

    if (![session waitUntilAttached:kMeloNXAttachTimeout]) {
      response[@"message"] = session.finalMessage.length
          ? session.finalMessage
          : [NSString stringWithFormat:@"JIT_PREPARATION_TIMEOUT: StikJIT did not complete preparation. Last stage: %@",
              session.logs.lastObject ?: @"No helper stage received."];
      response[@"logs"] = session.logs;
      finish();
      return;
    }
    response[@"pidAttached"] = @YES;
    NSTimeInterval debuggerAttachedMs =
        (NSProcessInfo.processInfo.systemUptime - operationStarted) * 1000.0;
    response[@"debuggerAttachedMs"] = @(debuggerAttachedMs);
    MeloNXMilestone(
        @"jit_debugger_attached",
        [NSString stringWithFormat:
            @"PID identity verified at vAttach stop; elapsedMs=%.1f; "
             "helperToAttachMs=%.1f; final nonce resume proof pending",
            debuggerAttachedMs,
            debuggerAttachedMs - helperConnectedMs]);
    // Do not spend the final readiness proof here and then cross two Flutter
    // channels before loading the Core. The loader performs the nonce probe at
    // the actual dlopen boundary, which closes that race completely.
    response[@"coreLoadReady"] = @(!session.requiresCoreHandshake);

    if (session.finished && !session.success) {
      response[@"message"] = session.finalMessage.length
          ? session.finalMessage
          : @"The MeloNX JIT transaction did not complete successfully.";
      response[@"logs"] = session.logs;
      finish();
      return;
    }

    BOOL debugged = MeloNXHostIsDebugged();
    response[@"debugged"] = @(debugged);
    response[@"logs"] = session.logs;
    if (!debugged) {
      response[@"message"] = @"StikJIT detached without leaving RewindBox JIT-enabled.";
      finish();
      return;
    }

    // Do NOT wait for universal.js to finish here. Core constructors and
    // initialize prepare the RX arena and issue BRK #0xf00d / command 0.
    // Waiting before dlopen deadlocks host and helper (the old 90s failure).
    response[@"success"] = @YES;
    response[@"requiresCompletion"] = @YES;
    response[@"message"] = session.requiresCoreHandshake
        ? @"MeloNX debugger attached; final nonce validation is reserved for the Core load boundary."
        : @"MeloNX JIT is enabled for Core loading.";
    MeloNXMilestone(@"jit_prepare_ready", @"Returning attached session to Core loader");
    dispatch_async(dispatch_get_main_queue(), ^{ result(response); });
  });
}

@end

NSDictionary* MeloNXMemorySnapshot(void) {
  task_vm_info_data_t info = {};
  mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
  NSMutableDictionary* result = [NSMutableDictionary new];
  if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) == KERN_SUCCESS && count >= TASK_VM_INFO_REV1_COUNT)
    result[@"footprintBytes"] = @(info.phys_footprint);
#if TARGET_OS_IOS && !TARGET_OS_SIMULATOR
  result[@"availableBytes"] = @(os_proc_available_memory());
#endif
  return result;
}
