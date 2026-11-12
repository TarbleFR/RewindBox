// See S2ArmJitSession.h. The session logic is RPCS3JitSession (Rpcs3JitBridgePlugin.mm) with S2Arm names; differences:
// Objective-C instead of Objective-C++, no RPCS3 diagnostics sink (the helper's messages are kept in memory only, never
// written to the journal, because StikJIT lines can carry paths), and the helper start is a method of the session.
#import "S2ArmJitSession.h"

#import <Security/Security.h>
#import <objc/message.h>
#import <poll.h>
#import <stdio.h>
#import <arpa/inet.h>
#import <netinet/in.h>
#import <sys/socket.h>
#import <sys/sysctl.h>
#import <sys/types.h>
#import <unistd.h>

NSString *const S2ArmJitRequestType = @"com.neogamelab.neostation.s2arm-jit-request";
NSString *const S2ArmJitHelperMarker = @"NeoStationS2ArmJITHelper";
static NSTimeInterval const kS2ArmHelperConnectTimeout = 30.0;

void *SecTaskCreateFromSelf(CFAllocatorRef allocator);
CFTypeRef SecTaskCopyValueForEntitlement(void *task, CFStringRef entitlement, CFErrorRef *error);
int csops(pid_t pid, unsigned int ops, void *useraddr, size_t usersize);

#ifndef CS_OPS_STATUS
#define CS_OPS_STATUS 0
#endif
#ifndef CS_DEBUGGED
#define CS_DEBUGGED 0x10000000
#endif

BOOL S2ArmHostHasGetTaskAllow(void) {
  void *task = SecTaskCreateFromSelf(NULL);
  if (task == NULL) return NO;
  CFTypeRef value = SecTaskCopyValueForEntitlement(task, CFSTR("get-task-allow"), NULL);
  BOOL allowed = value == kCFBooleanTrue;
  if (value != NULL) CFRelease(value);
  CFRelease(task);
  return allowed;
}

BOOL S2ArmHostIsDebugged(void) {
  uint32_t flags = 0;
  if (csops(getpid(), CS_OPS_STATUS, &flags, sizeof(flags)) != 0) return NO;
  return (flags & CS_DEBUGGED) != 0;
}

BOOL S2ArmHostHasLiveDebugger(void) {
  int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()};
  struct kinfo_proc info = {0};
  size_t size = sizeof(info);
  return sysctl(mib, 4, &info, &size, NULL, 0) == 0 && size == sizeof(info) && (info.kp_proc.p_flag & P_TRACED) != 0;
}

BOOL S2ArmRequiresCoreHandshake(void) {
  if (@available(iOS 26.0, *)) return YES;
  return NO;
}

NSString *_Nullable S2ArmFindHelperBundleIdentifier(void) {
  NSURL *plugins = NSBundle.mainBundle.builtInPlugInsURL;
  if (plugins == nil) return nil;
  NSArray<NSURL *> *entries = [NSFileManager.defaultManager contentsOfDirectoryAtURL:plugins
                                                          includingPropertiesForKeys:nil
                                                                             options:0
                                                                               error:nil];
  for (NSURL *entry in entries) {
    if (![entry.pathExtension.lowercaseString isEqualToString:@"appex"]) continue;
    NSBundle *bundle = [NSBundle bundleWithURL:entry];
    NSDictionary *extension = [bundle objectForInfoDictionaryKey:@"NSExtension"];
    NSString *point = [extension isKindOfClass:NSDictionary.class] ? extension[@"NSExtensionPointIdentifier"] : nil;
    NSString *marker = [bundle objectForInfoDictionaryKey:S2ArmJitHelperMarker];
    if ([point isEqualToString:@"com.apple.share-services"] && [marker isEqualToString:@"1"] && bundle.bundleIdentifier.length > 0) {
      return bundle.bundleIdentifier;
    }
  }
  return nil;
}

static NSError *S2ArmJitError(NSInteger code, NSString *message) {
  return [NSError errorWithDomain:@"NeoStationS2ArmJIT" code:code userInfo:@{NSLocalizedDescriptionKey : message}];
}

@interface S2ArmJitSession ()
@property(nonatomic, strong, nullable) id extensionObject;
@property(nonatomic, strong, nullable) id requestIdentifier;
@end

@implementation S2ArmJitSession {
  int _listener;
  int _client;
  uint16_t _port;
  uint32_t _probeNonce;
  NSString *_token;
  NSCondition *_condition;
  BOOL _connected;
  BOOL _attached;
  BOOL _finished;
  BOOL _success;
  BOOL _closed;
  NSString *_finalMessage;
  NSMutableArray<NSString *> *_mutableLogs;
  dispatch_queue_t _readerQueue;
}

- (nullable instancetype)initWithError:(NSError **)error {
  self = [super init];
  if (!self) return nil;
  _client = -1;
  _listener = socket(AF_INET, SOCK_STREAM, 0);
  if (_listener < 0) {
    if (error) *error = S2ArmJitError(2101, @"Could not create the S2Arm JIT helper socket.");
    return nil;
  }
  int reuse = 1;
  setsockopt(_listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
  struct sockaddr_in address = {0};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = 0;
  if (bind(_listener, (struct sockaddr *)&address, sizeof(address)) != 0 || listen(_listener, 1) != 0) {
    close(_listener);
    _listener = -1;
    if (error) *error = S2ArmJitError(2102, @"Could not bind the S2Arm JIT helper socket.");
    return nil;
  }
  socklen_t length = sizeof(address);
  if (getsockname(_listener, (struct sockaddr *)&address, &length) != 0) {
    close(_listener);
    _listener = -1;
    if (error) *error = S2ArmJitError(2103, @"Could not determine the S2Arm JIT helper port.");
    return nil;
  }
  _port = ntohs(address.sin_port);
  _token = NSUUID.UUID.UUIDString;
  _probeNonce = arc4random_uniform(UINT32_MAX - 1) + 1;
  _condition = [NSCondition new];
  _mutableLogs = [NSMutableArray new];
  _finalMessage = @"";
  _readerQueue = dispatch_queue_create("com.neogamelab.neostation.s2arm.helper-reader", DISPATCH_QUEUE_SERIAL);
  return self;
}

- (uint16_t)port { return _port; }
- (uint32_t)probeNonce { return _probeNonce; }
- (NSString *)token { return _token; }

#define S2ARM_LOCKED_GETTER(type, name, ivar) \
  - (type)name {                              \
    [_condition lock];                        \
    type value = ivar;                        \
    [_condition unlock];                      \
    return value;                             \
  }
S2ARM_LOCKED_GETTER(BOOL, closed, _closed)
S2ARM_LOCKED_GETTER(BOOL, connected, _connected)
S2ARM_LOCKED_GETTER(BOOL, attached, _attached)
S2ARM_LOCKED_GETTER(BOOL, finished, _finished)
S2ARM_LOCKED_GETTER(BOOL, success, _success)
#undef S2ARM_LOCKED_GETTER

- (NSString *)finalMessage {
  [_condition lock];
  NSString *value = [_finalMessage copy];
  [_condition unlock];
  return value;
}

- (NSArray<NSString *> *)logs {
  [_condition lock];
  NSArray<NSString *> *value = [_mutableLogs copy];
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
      ((void (*)(id, SEL, id))objc_msgSend)(extension, selector, identifier);
    }
  });
}

- (void)markFinished:(BOOL)success message:(NSString *)message {
  [_condition lock];
  _finished = YES;
  _success = success;
  _finalMessage = message ?: @"";
  [_condition broadcast];
  [_condition unlock];
}

- (void)startReader {
  __weak S2ArmJitSession *weakSelf = self;
  dispatch_async(_readerQueue, ^{
    S2ArmJitSession *strongSelf = weakSelf;
    if (strongSelf == nil) return;
    struct pollfd descriptor = {strongSelf->_listener, POLLIN, 0};
    if (poll(&descriptor, 1, (int)(kS2ArmHelperConnectTimeout * 1000.0)) <= 0) {
      [strongSelf markFinished:NO message:@"The S2Arm JIT helper did not connect to RewindBox."];
      return;
    }
    int accepted = accept(strongSelf->_listener, NULL, NULL);
    if (accepted < 0) {
      [strongSelf markFinished:NO message:@"The S2Arm JIT helper socket could not be accepted."];
      return;
    }
    FILE *stream = fdopen(accepted, "r");
    if (stream == NULL) {
      close(accepted);
      [strongSelf markFinished:NO message:@"The S2Arm JIT helper stream could not be opened."];
      return;
    }
    // A duplicate kept solely for shutdown: fclose owns the original, and closing a timed-out session must unblock fgets.
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
        NSString *line = [[NSString alloc] initWithUTF8String:buffer];
        line = [line stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if (line.length == 0) continue;
        NSDictionary *payload = [NSJSONSerialization JSONObjectWithData:[line dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        if (![payload isKindOfClass:NSDictionary.class] || ![payload[@"token"] isEqual:strongSelf->_token]) continue;
        NSString *event = [payload[@"event"] isKindOfClass:NSString.class] ? payload[@"event"] : @"unknown";
        NSString *message = [payload[@"message"] isKindOfClass:NSString.class] ? payload[@"message"] : @"";
        [strongSelf->_condition lock];
        if ([event isEqualToString:@"helper_connected"]) {
          strongSelf->_connected = YES;
        } else if ([event isEqualToString:@"pid_attached"] && strongSelf->_connected) {
          NSNumber *targetPID = [payload[@"targetPID"] isKindOfClass:NSNumber.class] ? payload[@"targetPID"] : nil;
          if ([targetPID isEqualToNumber:@(getpid())]) strongSelf->_attached = YES;
        } else if ([event isEqualToString:@"log"]) {
          if (message.length > 0) {
            [strongSelf->_mutableLogs addObject:message.length > 4096 ? [message substringToIndex:4096] : message];
            if (strongSelf->_mutableLogs.count > 64) [strongSelf->_mutableLogs removeObjectAtIndex:0];
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
      [strongSelf markFinished:NO message:@"The S2Arm JIT helper disconnected before completing the transaction."];
    }
  });
}

- (BOOL)waitForPredicate:(BOOL (^)(void))predicate timeout:(NSTimeInterval)timeout {
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
  [_condition lock];
  while (!predicate()) {
    if (![_condition waitUntilDate:deadline]) break;
  }
  BOOL value = predicate();
  [_condition unlock];
  return value;
}

- (BOOL)waitUntilConnected:(NSTimeInterval)timeout {
  [self waitForPredicate:^BOOL { return self->_connected || self->_finished || self->_closed; } timeout:timeout];
  return self.connected && !self.closed;
}

- (BOOL)waitUntilAttached:(NSTimeInterval)timeout {
  [self waitForPredicate:^BOOL { return self->_attached || self->_finished || self->_closed; } timeout:timeout];
  // The classic (pre-iOS 26) path attaches and detaches by itself and reports no vAttach line: its successful completion
  // is the only proof there, exactly as in the RPCS3 session.
  return (self.attached && !self.closed && !self.finished) ||
         (!self.requiresCoreHandshake && self.connected && self.finished && self.success);
}

- (BOOL)waitUntilFinished:(NSTimeInterval)timeout {
  return [self waitForPredicate:^BOOL { return self->_finished || self->_closed; } timeout:timeout];
}

- (BOOL)launchHelperWithPairingData:(NSData *)pairingData error:(NSError **)error {
  NSString *helperIdentifier = S2ArmFindHelperBundleIdentifier();
  if (helperIdentifier.length == 0) {
    if (error) *error = S2ArmJitError(2201, @"The embedded S2Arm JIT helper extension is missing.");
    return NO;
  }
  NSDictionary *request = @{
    @"protocolVersion" : @1,
    @"probeNonce" : @(self.probeNonce),
    @"targetPID" : @(getpid()),
    @"port" : @(self.port),
    @"token" : self.token,
    @"pairingData" : [pairingData base64EncodedStringWithOptions:0],
    @"requiresCoreHandshake" : @(self.requiresCoreHandshake),
  };
  NSData *requestData = [NSJSONSerialization dataWithJSONObject:request options:0 error:error];
  if (requestData == nil) return NO;
  NSItemProvider *provider = [[NSItemProvider alloc] initWithItem:requestData typeIdentifier:S2ArmJitRequestType];
  NSExtensionItem *item = [NSExtensionItem new];
  item.attachments = @[ provider ];

  Class extensionClass = NSClassFromString(@"NSExtension");
  SEL createSelector = NSSelectorFromString(@"extensionWithIdentifier:error:");
  SEL beginSelector = NSSelectorFromString(@"beginExtensionRequestWithInputItems:completion:");
  if (extensionClass == Nil || ![extensionClass respondsToSelector:createSelector]) {
    if (error) *error = S2ArmJitError(2202, @"This iOS build cannot start the embedded S2Arm JIT helper.");
    return NO;
  }
  id extensionObject = ((id (*)(id, SEL, NSString *, NSError **))objc_msgSend)(extensionClass, createSelector, helperIdentifier, error);
  if (extensionObject == nil || ![extensionObject respondsToSelector:beginSelector]) {
    if (error && !*error) *error = S2ArmJitError(2203, @"The S2Arm JIT helper extension could not be opened.");
    return NO;
  }
  self.extensionObject = extensionObject;
  // The session is retained (strong capture, as in RPCS3) until the launch returns its request identifier, even if the
  // connection timed out first, so that a late extension can still be cancelled.
  S2ArmJitSession *session = self;
  void (^completion)(id) = ^(id requestIdentifier) {
    session.requestIdentifier = requestIdentifier;
    if (session.closed) [session cancelExtensionRequest];
  };
  ((void (*)(id, SEL, NSArray *, id))objc_msgSend)(extensionObject, beginSelector, @[ item ], completion);
  return YES;
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
