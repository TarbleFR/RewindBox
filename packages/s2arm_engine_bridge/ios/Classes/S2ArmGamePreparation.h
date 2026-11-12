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
/// The game-independent system data shipped with the app: the systemdata/ folder of <app>/S2ArmSystemData (the tree the
/// delivery places there with its licences), linked as each game's resource pack systemdata; nil when absent.
NSString *_Nullable S2ArmShippedSystemData(void);
/// rb_s2arm_ns2_detect: {success, exportDir, programId, gid} or {success: NO, code, diagnostic}.
NSDictionary *S2ArmDetectExport(NSString *folder);

/// Light metadata for the library scan and scraping, read without unpacking: the title id (ns2-detect) and, from the first
/// control.nacp found in the export, the title (NACP, language chosen for localePref) and publisher, the display version,
/// and the icon.jpg path when one sits beside it. {success, titleId, gid, title, publisher, displayVersion, iconPath} or
/// {success: NO, code}. No game content is read beyond these display fields.
NSDictionary *S2ArmGameInfo(NSString *folder, NSString *_Nullable localePref);

/// [fraction] is the share of [step] done (0–1). [detail] names the part of the step running (the code stage's module, e.g.
/// "main"), or "reused" when a finished preparation of the same inputs is reused; nil otherwise.
typedef void (^S2ArmPrepareProgress)(NSString *step, NSInteger stepIndex, NSInteger stepCount, double fraction,
                                     NSString *_Nullable detail);

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
