// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>
#include "Rpcs3CoreABI.h"

NS_ASSUME_NONNULL_BEGIN
/// Host-only staging for the Core's existing Patch Engine API. Calls are
/// serialized on the RPCS3 runtime queue. Nothing writes guest memory live.
@interface RPCS3UnifiedCheats : NSObject
/// NO only if a transaction could not restore the original global patch files.
@property(nonatomic,readonly) BOOL bootSafe;
- (instancetype)initWithRoot:(NSString*)root api:(rpcs3_ios_patch_api)api;
+ (BOOL)acceptsProgram:(NSDictionary*)program;
- (NSString*)installedVersionForTitle:(NSString*)serial;
- (NSDictionary*)snapshotForTitle:(NSString*)serial version:(NSString*)version;
- (BOOL)stageGame:(NSDictionary*)game programs:(NSArray*)programs
           serial:(NSString*)serial version:(NSString*)version;
- (BOOL)setIdentifier:(NSString*)identifier enabled:(BOOL)enabled serial:(NSString*)serial;
/// Call ONLY after stop_emulation or before boot_game. Validates through the
/// real Core YAML parser and persists explicit requested states for next boot.
- (BOOL)applyPendingWhileStoppedForTitle:(NSString*)serial;
@end
NS_ASSUME_NONNULL_END
