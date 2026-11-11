#pragma once
// The per-game preparation chain of docs/s2arm-study-2026-11-11.md § 8, run on the phone with S2ArmPrepare.xcframework
// (native/s2arm/prepare): ns2-dump in reference mode (RomFS and DLC read in place through relative links), code stage, caps,
// direct skeleton, module directory with the image pack, resource pack. Everything is written into the app's private
// Library/S2Arm/<gid>/ (excluded from backups, never shared or exported), except the game's documents (saves), which
// Library/S2Arm/<gid>/docs keeps across preparations.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Error codes shared with lib/services/s2arm_internal_service.dart (same spelling).
FOUNDATION_EXPORT NSString *const S2ArmErrorNotExportFolder;
FOUNDATION_EXPORT NSString *const S2ArmErrorExportInvalid;
FOUNDATION_EXPORT NSString *const S2ArmErrorGameUnsupported;
FOUNDATION_EXPORT NSString *const S2ArmErrorRewriterFailed;
FOUNDATION_EXPORT NSString *const S2ArmErrorIo;
FOUNDATION_EXPORT NSString *const S2ArmErrorCancelled;
FOUNDATION_EXPORT NSString *const S2ArmErrorInsufficientSpace;
FOUNDATION_EXPORT NSString *const S2ArmErrorSystemDataMissing;
FOUNDATION_EXPORT NSString *const S2ArmErrorEngineChainMissing;
FOUNDATION_EXPORT NSString *const S2ArmErrorPrepareFailed;
FOUNDATION_EXPORT NSString *const S2ArmErrorGameIdMismatch;
FOUNDATION_EXPORT NSString *const S2ArmErrorInvalidArguments;

/// Library/S2Arm (created when missing).
NSString *S2ArmLibraryRoot(void);
/// Library/S2Arm/<gid>.
NSString *S2ArmGameDirectory(NSString *gid);
/// The direct library chain version of the shipped engine: S2ArmEngine.framework/S2ArmDirectChain.txt, or nil.
NSString *_Nullable S2ArmShippedDirectChain(void);
/// The game-independent system data tree shipped with the app (<app>/S2ArmSystemData), or nil when absent.
NSString *_Nullable S2ArmShippedSystemData(void);
/// rb_s2arm_ns2_detect: {success, exportDir, programId, gid} or {success: NO, code, diagnostic}.
NSDictionary *S2ArmDetectExport(NSString *folder);

typedef void (^S2ArmPrepareProgress)(NSString *step, NSInteger stepIndex, NSInteger stepCount, double fraction);

@interface S2ArmGamePreparation : NSObject
@property(nonatomic, copy) NSString *exportFolder;                // absolute, inside Documents/S2Arm/Games
@property(nonatomic, copy, nullable) NSString *directChain;       // nil = S2ArmShippedDirectChain()
@property(nonatomic, copy, nullable) NSString *systemDataFolder;  // nil = S2ArmShippedSystemData()
@property(nonatomic, copy, nullable) S2ArmPrepareProgress progress;
/// Runs the chain on the calling thread (a background queue). Returns {success, gid, sizes, durationsMs} or
/// {success: NO, code, stage, diagnostic}. The diagnostic is the library's line; it is never journaled.
- (NSDictionary *)run;
/// Any thread: the next poll of the library stops the chain with S2ArmErrorCancelled.
- (void)cancel;
@end

NS_ASSUME_NONNULL_END
