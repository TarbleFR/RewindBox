#import <Foundation/Foundation.h>

#include "libretro.h"

NS_ASSUME_NONNULL_BEGIN

/// One option declared by a libretro core, normalised across the option
/// API versions (SET_VARIABLES, SET_CORE_OPTIONS v1/v2 and their _INTL
/// variants).
@interface LibretroCoreOption : NSObject
@property(nonatomic, copy, readonly) NSString *key;
@property(nonatomic, copy, readonly) NSString *coreDescription;
@property(nonatomic, copy, readonly) NSArray<NSString *> *values;
@property(nonatomic, copy, readonly) NSArray<NSString *> *valueLabels;
@property(nonatomic, copy, readonly) NSString *defaultValue;
@property(nonatomic, assign) BOOL visible;
@end

/// Stores the options a core declares and the values chosen for them.
///
/// Values persist as JSON, one file per core, so the same choice applies to
/// every game of that core. A value can also be kept for one game only
/// (Build 455, the internal resolution): `Config/Games/<core>.json`,
/// `{"version": 1, "games": {"<game key>": {key: value}}}`, of which only
/// the running game is read and rewritten (other games and unknown keys
/// are kept). Overrides passed by NeoStation for a session (curated,
/// translated settings) win over the stored values for that session only.
///
/// Value in effect, first that the core offers: a value kept for this
/// session by a change that applies at the next launch, the session
/// overrides, this game's value, the core's stored value, NeoStation's
/// default, then the core's own default.
@interface LibretroCoreOptions : NSObject

/// Without a per-game layer.
- (instancetype)initWithStorePath:(NSString *)storePath;
/// `gameStorePath` and `gameKey`: the per-game file and the running game
/// ("<system>/<rom file name>"); nil for none.
- (instancetype)initWithStorePath:(NSString *)storePath
                    gameStorePath:(nullable NSString *)gameStorePath
                          gameKey:(nullable NSString *)gameKey NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;

/// The running game, nil without a per-game layer.
@property(nonatomic, copy, readonly, nullable) NSString *gameKey;

@property(nonatomic, copy, readonly) NSArray<LibretroCoreOption *> *options;
@property(nonatomic, assign, readonly) BOOL updatePending;
@property(nonatomic, assign, nullable) retro_core_options_update_display_callback_t updateDisplayCallback;

/// Session-only values that take precedence over stored ones (for instance
/// interpreter CPU cores while JIT is unavailable). May be called before
/// the core declares its options. Sets `updatePending` when the effective
/// value of an already declared option changes.
- (void)applySessionOverrides:(NSDictionary<NSString *, NSString *> *)overrides;
/// Same as applySessionOverrides:, and `setValue:forKey:persist:` then
/// refuses these keys for the rest of the session (returns NO, nothing
/// stored).
- (void)lockSessionOverrides:(NSDictionary<NSString *, NSString *> *)overrides;
/// NeoStation defaults, used only while the user has stored no value. Sets
/// `updatePending` when the effective value of a declared option changes.
- (void)applyDefaults:(NSDictionary<NSString *, NSString *> *)defaults;
/// Like applyDefaults:, once the core declared its options and before
/// retro_init: the core has read nothing yet, so no update is flagged.
- (void)applyDefaultsBeforeInit:(NSDictionary<NSString *, NSString *> *)defaults;
/// YES for keys passed to lockSessionOverrides:.
- (BOOL)isLockedKey:(NSString *)key;

/// The value in effect when it comes from a layer above the core's own
/// default (one the core offers), nil when the core's default is used.
- (nullable NSString *)assignedValueForKey:(NSString *)key;
/// The value stored for every game of the core, nil when none.
- (nullable NSString *)storedValueForKey:(NSString *)key;
/// The value stored for the running game only, nil when none.
- (nullable NSString *)gameValueForKey:(NSString *)key;
/// The value every game of the core gets without a value of its own: the
/// stored value, else NeoStation's default, else the core's default (each
/// only when the core offers it). Session values are left out.
- (nullable NSString *)valueForEveryGameForKey:(NSString *)key;
/// What the running core receives (GET_VARIABLE).
- (nullable NSString *)currentValueForKey:(NSString *)key;
/// What the core will receive at the next launch of this game: the value in
/// effect without the values kept for this session.
- (nullable NSString *)nextLaunchValueForKey:(NSString *)key;
/// A choice from the in-game menu, saved at once: for the running game
/// only (`game` YES) or for every game of the core. `applyNow` NO keeps
/// the current value for the running core (an option it reads only when a
/// game starts): the choice takes effect at the next launch. NO, nothing
/// changed, for a locked key, a value the core does not offer, or `game`
/// without a per-game layer.
- (BOOL)setValue:(NSString *)value forKey:(NSString *)key game:(BOOL)game applyNow:(BOOL)applyNow;
/// Removes the running game's value (`game` YES) or the core's stored value
/// (NO), saved at once; `applyNow` as above. NO for a locked key or `game`
/// without a per-game layer.
- (BOOL)removeValueForKey:(NSString *)key game:(BOOL)game applyNow:(BOOL)applyNow;

- (BOOL)declareVariables:(const struct retro_variable *)variables;
- (BOOL)declareDefinitions:(const struct retro_core_option_definition *)definitions
                     local:(const struct retro_core_option_definition *_Nullable)local;
- (BOOL)declareV2:(const struct retro_core_options_v2 *)options
            local:(const struct retro_core_options_v2 *_Nullable)local;
- (void)setDisplay:(const struct retro_core_option_display *)display;

/// GET_VARIABLE: the returned pointer stays valid until the store is
/// released, even after the value changes (a menu change while the core
/// runs never frees a string it is reading).
- (nullable const char *)valueForKey:(const char *)key;
/// SET_VARIABLE (from the core) and user changes from the session menu:
/// the value for every game of the core, in effect at once.
- (BOOL)setValue:(NSString *)value forKey:(NSString *)key persist:(BOOL)persist;
/// GET_VARIABLE_UPDATE: returns YES once after a change, then clears.
- (BOOL)consumeUpdate;

/// Writes the core's file (`{"values": ...}`). The per-game file is
/// written by each change of a game value.
- (void)save;

@end

NS_ASSUME_NONNULL_END
