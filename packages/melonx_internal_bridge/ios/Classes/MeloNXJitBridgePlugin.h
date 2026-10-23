#pragma once
#import <Flutter/Flutter.h>
#import <Foundation/Foundation.h>

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
#ifdef __cplusplus
}
#endif
