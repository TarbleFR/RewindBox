#import <Foundation/Foundation.h>

@class LibretroCoreOption;
@class LibretroCoreOptions;

NS_ASSUME_NONNULL_BEGIN

/// When a new internal resolution takes effect.
typedef NS_ENUM(NSInteger, LibretroResolutionApply) {
  /// The core reads the option only when it starts the game: close and
  /// relaunch. Also the rule for an option recognized by its name only.
  LibretroResolutionApplyRelaunch = 0,
  /// The core reads the option again during the game and draws at the new
  /// resolution as soon as the game resumes.
  LibretroResolutionApplyLive = 1,
};

/// One value of a resolution option and the scale it names.
@interface LibretroResolutionChoice : NSObject
/// The core's own value, stored as is.
@property(nonatomic, copy, readonly) NSString *value;
/// 1 for the native resolution, 2 for twice it…
@property(nonatomic, readonly) double factor;
/// The size a value such as "960x544" names; 0 for a multiplier ("2x").
@property(nonatomic, readonly) NSUInteger width;
@property(nonatomic, readonly) NSUInteger height;
@property(nonatomic, readonly) BOOL isNative;
@end

/// The option through which a core renders the game at a higher internal
/// resolution, with the values NeoStation offers.
@interface LibretroResolutionCapability : NSObject
@property(nonatomic, copy, readonly) NSString *key;
@property(nonatomic, copy, readonly) NSString *coreDescription;
@property(nonatomic, readonly) LibretroResolutionApply apply;
/// "profile": the key is in a profile of NeoStation's catalog; "generic":
/// recognized by its name or description (applies after a relaunch).
@property(nonatomic, copy, readonly) NSString *source;
/// Smallest factor first, at least two.
@property(nonatomic, copy, readonly) NSArray<LibretroResolutionChoice *> *choices;
/// The core's own default value.
@property(nonatomic, copy, readonly) NSString *coreDefault;
/// The factor-1 choice, nil when the core offers none.
@property(nonatomic, readonly, nullable) LibretroResolutionChoice *nativeChoice;
- (nullable LibretroResolutionChoice *)choiceForValue:(nullable NSString *)value;
/// JSON description written to Config/Resolution/<core>.json for the
/// console settings of NeoStation (Dart `LibretroResolutionSnapshot`).
- (NSDictionary<NSString *, id> *)snapshot;
@end

/// The renderer a core obtained from the session once its content is
/// loaded (`LibretroSession rendererName`), as profiles name it.
FOUNDATION_EXPORT NSString *const LibretroResolutionRendererGLES;
FOUNDATION_EXPORT NSString *const LibretroResolutionRendererVulkan;
/// No hardware context: the core sends its frames to the frontend.
FOUNDATION_EXPORT NSString *const LibretroResolutionRendererSoftware;

/// NeoStation's rules (Dart `LibretroResolution.nativeRules()`): profiles
/// of known option names, generic name and description patterns, largest
/// picture side. Recognizes the resolution option among those a core
/// declared.
@interface LibretroResolutionRules : NSObject
/// `rules`: {"profiles": [{"keys": [..], "apply": "live"|"relaunch",
/// "nativeSize"?: [w, h], "maxFactor"?: n, "requires"?: {key: [values]},
/// "renderers"?: [..]}], "keyPattern": regex, "descriptionPattern": regex,
/// "maxDimension": n}. Missing or malformed entries are ignored (no
/// profile, no pattern).
- (instancetype)initWithDictionary:(nullable NSDictionary *)rules NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;

/// The option of `options` that sets the internal resolution, nil when the
/// core has none NeoStation can offer. Profiles first, in their order (a
/// profile whose `requires` are not met by `valueForKey`, whose `renderers`
/// do not include `renderer`, or whose option is hidden, is skipped), then
/// the visible options matching the generic patterns whose values include
/// the native resolution, except keys a profile names. `renderer`: the
/// core's renderer, nil before its content is loaded (no renderer
/// condition then). `consoleWidth` x `consoleHeight`: the console's whole
/// picture (0 x 0 when unknown), for the largest side.
- (nullable LibretroResolutionCapability *)capabilityForOptions:(NSArray<LibretroCoreOption *> *)options
                                                     valueForKey:(NSString *_Nullable (^)(NSString *key))valueForKey
                                                        renderer:(nullable NSString *)renderer
                                                    consoleWidth:(double)consoleWidth
                                                   consoleHeight:(double)consoleHeight;
/// The same before the renderer is known.
- (nullable LibretroResolutionCapability *)capabilityForOptions:(NSArray<LibretroCoreOption *> *)options
                                                     valueForKey:(NSString *_Nullable (^)(NSString *key))valueForKey
                                                    consoleWidth:(double)consoleWidth
                                                   consoleHeight:(double)consoleHeight;
/// The same for the options of a core's store, with their current values.
- (nullable LibretroResolutionCapability *)capabilityForCoreOptions:(LibretroCoreOptions *)options
                                                            renderer:(nullable NSString *)renderer
                                                        consoleWidth:(double)consoleWidth
                                                       consoleHeight:(double)consoleHeight;
- (nullable LibretroResolutionCapability *)capabilityForCoreOptions:(LibretroCoreOptions *)options
                                                        consoleWidth:(double)consoleWidth
                                                       consoleHeight:(double)consoleHeight;
/// The first declared option a profile names, visible or not, whether or
/// not the profile applies: with no capability, the core has an internal
/// resolution that does not apply to the way it draws now (another
/// renderer, another of its settings). Nil when no profile names one.
- (nullable NSString *)profileKeyForOptions:(NSArray<LibretroCoreOption *> *)options;
@end

/// Once the core declared its options, before retro_init: a core whose own
/// default is not its native resolution starts at native, unless a value
/// is assigned (this game, every game, NeoStation's default, the session).
/// Returns the native value applied, nil when nothing was applied.
FOUNDATION_EXPORT NSString *_Nullable LibretroResolutionApplyNativeDefault(LibretroResolutionCapability *_Nullable capability,
                                                                           LibretroCoreOptions *options);

/// A choice of the "Resolution and picture" page, saved at once for this
/// game only (`game` YES) or every game of the core: in effect when the
/// game resumes for a live option, at the next launch otherwise. NO when
/// `value` is not one of the capability's choices or the store refused it.
FOUNDATION_EXPORT BOOL LibretroResolutionSelect(LibretroResolutionCapability *capability, LibretroCoreOptions *options,
                                                NSString *value, BOOL game);

/// Removes this game's resolution (it follows the core's again) or the
/// core's saved one (back to the default), applied like a choice.
FOUNDATION_EXPORT BOOL LibretroResolutionClear(LibretroResolutionCapability *capability, LibretroCoreOptions *options,
                                               BOOL game);

/// What one value names (Dart `LibretroResolution.token`): YES with
/// `factor` > 0 for a multiplier ("2x", "x2", "1x (native)", "2", "Native"),
/// YES with `factor` 0 and the size for a size ("960x544"), NO otherwise.
FOUNDATION_EXPORT BOOL LibretroResolutionParseValue(NSString *value, double *factor, NSUInteger *width,
                                                    NSUInteger *height);

/// Dart `LibretroResolution.choices`: the values offered, smallest factor
/// first. `nativeSize` (two numbers) divides sizes, else the smallest
/// declared size; `maxFactor` 0 and `maxDimension` 0 mean no limit.
FOUNDATION_EXPORT NSArray<LibretroResolutionChoice *> *LibretroResolutionChoices(
    NSArray<NSString *> *values, NSArray<NSString *> *_Nullable labels, NSArray<NSNumber *> *_Nullable nativeSize,
    double consoleWidth, double consoleHeight, double maxFactor, NSInteger maxDimension);

NS_ASSUME_NONNULL_END
