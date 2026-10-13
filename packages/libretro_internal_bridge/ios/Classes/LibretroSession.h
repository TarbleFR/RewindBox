#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Launch description assembled by Dart. Every user-visible label arrives
/// translated in `uiText`; native code shows no text of its own.
@interface LibretroSessionConfiguration : NSObject
@property(nonatomic, copy) NSString *corePath;
@property(nonatomic, copy) NSString *contentPath;
@property(nonatomic, copy) NSString *gameTitle;
@property(nonatomic, copy) NSString *systemDirectory;
@property(nonatomic, copy) NSString *saveDirectory;
@property(nonatomic, copy) NSString *stateDirectory;
@property(nonatomic, copy) NSString *optionsDirectory;
@property(nonatomic, copy) NSString *cheatsDirectory;
@property(nonatomic, copy) NSString *cacheDirectory;
@property(nonatomic, copy) NSString *uiLocale;
@property(nonatomic, assign) unsigned retroLanguage;
@property(nonatomic, copy) NSDictionary<NSString *, NSString *> *uiText;
/// NeoStation defaults for core options, used until the user changes them.
@property(nonatomic, copy) NSDictionary<NSString *, NSString *> *optionDefaults;
/// Interpreter settings forced while cores cannot use JIT.
@property(nonatomic, copy) NSDictionary<NSString *, NSString *> *noJitOverrides;
/// Curated, translated settings: [{key, label, values: [{value, label}]}].
@property(nonatomic, copy) NSArray<NSDictionary *> *coreSettings;
@property(nonatomic, assign) BOOL achievementsAllowed;
@property(nonatomic, assign) unsigned achievementsConsoleId;
/// RETRO_HW_CONTEXT_* answered to GET_PREFERRED_HW_RENDER for this core.
@property(nonatomic, assign) unsigned preferredHardwareContext;
/// NeoStation console of the game ("gba", "psp", "3ds"...): key of skins,
/// screen format, shaders and controls, independent of the core.
@property(nonatomic, copy) NSString *console;
/// Product name of the console ("Nintendo 3DS"), never translated.
@property(nonatomic, copy) NSString *consoleName;
/// Per-game key of the frontend settings ("<system>/<rom file name>").
@property(nonatomic, copy) NSString *gameKey;
/// Documents/Libretro/Skins: one directory per imported skin.
@property(nonatomic, copy) NSString *skinsDirectory;
/// Documents/Libretro/Config/Frontend (LibretroFrontendStore).
@property(nonatomic, copy) NSString *frontendDirectory;
/// Geometry of every console, for skins (see +[LibretroSkin
/// skinWithDirectory:consoleGeometry:errorCode:]):
/// {console: {"size": [w, h], "regions": {"top": [x,y,w,h], "bottom": [...]}}}.
@property(nonatomic, copy) NSDictionary<NSString *, NSDictionary *> *consoleGeometry;
/// Core options NeoStation locks for this session so it can crop the two
/// screens and route touches (DeSmuME: desmume_screens_layout=top/bottom,
/// desmume_screens_gap=0, desmume_pointer_type=touch,
/// desmume_pointer_mouse=enabled; Azahar: citra_layout_option=default,
/// citra_swap_screen=Top, citra_analog_function=c_stick,
/// citra_render_3d=off). Applied before retro_init and read-only in the
/// menu.
@property(nonatomic, copy) NSDictionary<NSString *, NSString *> *lockedOptions;
/// Documents/Libretro/Logs: the session journal (LibretroSessionJournal);
/// empty for none.
@property(nonatomic, copy) NSString *logsDirectory;
/// NeoStation core id ("ppsspp", "azahar"): names the core's resolution
/// snapshot, Config/Resolution/<coreId>.json. Empty: none written.
@property(nonatomic, copy) NSString *coreId;
/// Internal resolution rules (Dart `LibretroResolution.nativeRules()`, see
/// LibretroResolutionRules); empty: the core's resolution is not offered.
@property(nonatomic, copy) NSDictionary *resolutionRules;
@end

/// One embedded game: core host on its own emulation thread, presentation,
/// audio, input, menu, save states, cheats and RetroAchievements.
@interface LibretroSession : NSObject

- (instancetype)initWithConfiguration:(LibretroSessionConfiguration *)configuration;

/// Presents the game over `presenter` and loads the content. `completion`
/// runs once on the main thread with {success, code, message, ...}:
/// success once the core has run for the startup period (or the user left
/// the game before), failure when the content could not be loaded or when
/// the core stopped by itself during that period (LIBRETRO_CORE_STOPPED,
/// with the core's error lines and log). On failure the game view is
/// already dismissed.
- (void)startFromViewController:(UIViewController *)presenter
                     completion:(void (^)(NSDictionary<NSString *, id> *result))completion;

/// Saves, unloads the core and dismisses the game. `completion` runs on the
/// main thread after the view controller is gone.
- (void)stopWithCompletion:(nullable dispatch_block_t)completion;

@property(nonatomic, readonly) BOOL active;
@property(nonatomic, copy, nullable) dispatch_block_t endedHandler;
@property(nonatomic, readonly) NSArray<NSString *> *recentLog;

/// Size of the last frame the core produced (software pixels, or the
/// rendered part of its hardware frame), {0, 0} before the first one: the
/// internal resolution really in effect. Any thread.
@property(nonatomic, readonly) CGSize producedFrameSize;
/// Main thread. The internal resolution of the running core as the in-game
/// "Resolution and picture" page shows it, nil when the core offers none:
/// {key, apply ("live" | "relaunch"), source, current, nextLaunch, game?,
/// core?, choices: [value]}.
- (nullable NSDictionary<NSString *, id> *)internalResolutionState;
/// Main thread. The choice of that page: `value` (one of the choices) for
/// this game only (`game` YES) or every game of the core. Applies when the
/// game resumes for a core that reads the option during the game, else at
/// the next launch. NO when the core offers no such value.
- (BOOL)selectInternalResolution:(NSString *)value forGame:(BOOL)game;

@end

NS_ASSUME_NONNULL_END
