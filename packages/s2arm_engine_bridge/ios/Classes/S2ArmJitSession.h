#pragma once
// Host side of the S2Arm JIT helper transaction (packages/s2arm_jit_helper, a renamed copy of RPCS3's helper), on the model of
// packages/rpcs3_internal_bridge/ios/Classes/Rpcs3JitBridgePlugin.mm: a loopback listener with a token and a probe nonce,
// the helper extension (marker NeoStationS2ArmJITHelper) started through NSExtension with the request
// com.neogamelab.neostation.s2arm-jit-request, its reporter events helper_connected, log, pid_attached, complete.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSString *const S2ArmJitRequestType;      // com.neogamelab.neostation.s2arm-jit-request
FOUNDATION_EXPORT NSString *const S2ArmJitHelperMarker;     // NeoStationS2ArmJITHelper (helper Info.plist)

/// get-task-allow in this process's entitlements (the helper attaches a debugger to the host).
BOOL S2ArmHostHasGetTaskAllow(void);
/// CS_DEBUGGED: the process was debugged at least once (stays set after a detach).
BOOL S2ArmHostIsDebugged(void);
/// P_TRACED: a debugger is attached right now.
BOOL S2ArmHostHasLiveDebugger(void);
/// iOS 26 and later: the universal handshake (the host drives commands 3, 1 and 0); before it the helper attaches and
/// detaches by itself (classic) and the process maps executable pages itself afterwards.
BOOL S2ArmRequiresCoreHandshake(void);
/// Bundle identifier of the embedded helper extension, or nil when this app does not carry it.
NSString *_Nullable S2ArmFindHelperBundleIdentifier(void);

@interface S2ArmJitSession : NSObject
@property(nonatomic, readonly) uint16_t port;
@property(nonatomic, readonly) uint32_t probeNonce;
@property(nonatomic, readonly) NSString *token;
@property(nonatomic, readonly) BOOL connected;
@property(nonatomic, readonly) BOOL attached;
@property(nonatomic, readonly) BOOL finished;
@property(nonatomic, readonly) BOOL success;
@property(nonatomic, readonly) BOOL closed;
@property(nonatomic, readonly) NSString *finalMessage;
@property(nonatomic, readonly) NSArray<NSString *> *logs;   // the helper's last 64 log lines (never journaled: they may hold paths)
@property(nonatomic, assign) BOOL requiresCoreHandshake;
- (nullable instancetype)initWithError:(NSError **)error;
- (void)startReader;
/// Starts the helper extension with this session's request. NO with error when it cannot be started.
- (BOOL)launchHelperWithPairingData:(NSData *)pairingData error:(NSError **)error;
- (BOOL)waitUntilConnected:(NSTimeInterval)timeout;
- (BOOL)waitUntilAttached:(NSTimeInterval)timeout;
- (BOOL)waitUntilFinished:(NSTimeInterval)timeout;
- (void)close;
@end

NS_ASSUME_NONNULL_END
