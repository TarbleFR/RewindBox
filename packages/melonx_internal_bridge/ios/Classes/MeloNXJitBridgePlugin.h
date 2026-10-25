#pragma once
#import <Flutter/Flutter.h>
#import <Foundation/Foundation.h>
// CocoaPods flattens public headers into the framework's Headers directory.
// The source-tree spelling remains available to standalone SDK checks.
#if __has_include("MLXRamDonor.h")
#import "MLXRamDonor.h"
#else
#import "../Memory/MLXRamDonor.h"
#endif

@interface MeloNXJitBridgePlugin : NSObject <FlutterPlugin>
@end

#ifdef __cplusplus
extern "C" {
#endif
BOOL MeloNXJitHasActiveCoreHandshake(void);
BOOL MeloNXJitConfirmCoreLoadHandoff(void);
BOOL MeloNXJitWaitForDetach(NSTimeInterval timeout, NSString* _Nullable * _Nullable message);
void MeloNXJitAbortTransaction(void);
// One real executable dual-mapping probe for methods that already enabled
// this process. CS_DEBUGGED by itself never makes this return success.
NSDictionary* MeloNXJitExecutableMappingProbe(void);
NSDictionary* _Nonnull MeloNXMemoryEntitlements(void);
// Real process footprint and OS-reported headroom; absent fields mean unavailable.
NSDictionary* _Nonnull MeloNXMemorySnapshot(void);
#ifdef __cplusplus
}
#endif
