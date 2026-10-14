#import <UIKit/UIKit.h>

#import "LibretroFrontendStore.h"
#import "LibretroInputMap.h"
#import "LibretroSessionMenu.h"
#import "LibretroSkin.h"

@class NeoSlangProgram;

NS_ASSUME_NONNULL_BEGIN

/// What the frontend pages of the in-game menu need from the running
/// session. Implemented by LibretroSession. Main thread only.
@protocol LibretroFrontendMenuHost <NSObject>
/// Translated label (uiText); returns the key itself when missing.
- (NSString *)text:(NSString *)key;
@property(nonatomic, readonly, copy) NSString *uiLocale;
@property(nonatomic, readonly, copy) NSString *console;
@property(nonatomic, readonly, copy) NSString *consoleName;
@property(nonatomic, readonly, copy) NSString *gameKey;
@property(nonatomic, readonly) LibretroFrontendStore *frontendStore;
@property(nonatomic, readonly) LibretroInputMap *inputMap;
/// Default skin first, then imported skins compatible with the console
/// (parsed once per menu opening).
@property(nonatomic, readonly, copy) NSArray<LibretroSkin *> *availableSkins;
/// Representation used for a skin's preview in an orientation at the
/// current view size (default skins are generated for it); nil when the
/// skin lacks that orientation.
- (nullable LibretroSkinRepresentation *)previewRepresentationForSkin:(LibretroSkin *)skin
                                                         orientation:(LibretroSkinOrientation)orientation;
/// Renders a preview off the main thread (LibretroSkinRenderer).
- (void)renderPreviewForRepresentation:(LibretroSkinRepresentation *)representation
                                  size:(CGSize)size
                            completion:(void (^)(UIImage *_Nullable image))completion;
@property(nonatomic, readonly) LibretroSkinOrientation currentOrientation;
/// Skin and representation on screen now.
@property(nonatomic, readonly) LibretroSkin *currentSkin;
@property(nonatomic, readonly) LibretroSkinRepresentation *currentRepresentation;
/// Display aspect of the whole core picture.
@property(nonatomic, readonly) double coreAspectRatio;
/// NO when Vulkan frames cannot reach Metal (legacy presentation).
@property(nonatomic, readonly) BOOL screensAndShadersAvailable;
@property(nonatomic, readonly) BOOL physicalControllerConnected;
/// Re-resolves every frontend setting from the store (game > console >
/// default) and applies it live: layout, screens, format, input remaps,
/// opacity; then redraws the last frame (coalesced). Shader settings are
/// applied by applyShaderPreset... below.
- (void)frontendSettingsDidChange;
/// Compiles and activates a preset (nil = none): a built-in preset on the
/// emulation thread, a slang preset ("slang:<catalog id>", Build 450) off
/// the main and emulation threads first. `completion` (main queue) gets NO
/// when it could not be applied: the caller must not save the preset (the
/// preceding picture is retained on a handled failure).
- (void)applyShaderPreset:(nullable NSString *)presetIdentifier
               parameters:(nullable NSDictionary<NSString *, NSNumber *> *)parameters
               completion:(void (^)(BOOL success))completion;
/// Live parameter change while a slider moves (not saved, redraw coalesced).
- (void)previewShaderParameter:(NSString *)identifier value:(float)value;
/// Compiled program of the slang preset in effect (its parameters, passes,
/// compile times), nil when the preset in effect is built-in or none.
@property(nonatomic, readonly, nullable) NeoSlangProgram *activeSlangProgram;
/// Why the last shader was not applied (SHADER_NOT_INSTALLED, a shader kit
/// code, interrupted attempt or GPU failure); nil after a success confirmed
/// by the first actual GPU frame, with the previous rendering restored on
/// a handled slang activation failure.
@property(nonatomic, readonly, copy, nullable) NSString *lastShaderFailureCode;
/// GPU memory of the slang chains in effect, bytes.
@property(nonatomic, readonly) NSUInteger slangTextureBytes;
/// Median GPU time of the active preset measured on the last frame
/// (completion on the main queue, milliseconds, 0 when unknown).
- (void)measureShaderWithCompletion:(void (^)(double milliseconds))completion;
/// Closes the menu and starts "Déplacer et redimensionner" for the current
/// skin and orientation; the overrides are saved for `gameKey` (game
/// scope) or nil (console scope) when the user taps Done.
- (void)beginControlsEditingForGame:(nullable NSString *)gameKey;
- (void)showStatus:(NSString *)message;
@end

/// Builds the "Skins", "Format d'écran", "Disposition des écrans" (DS / 3DS),
/// "Shaders" and "Commandes" entries of the in-game menu and their pages.
/// Every page starts with a "Save for" section (this console / this game
/// only), shows where each value comes from (valueFromGame /
/// valueFromConsole / valueDefault), offers "Restore defaults" for the
/// chosen scope, and writes LibretroFrontendStore keys (see its header)
/// before asking the host to apply them. Pages whose effect is visible on
/// the game set `previewsGame`.
@interface LibretroFrontendMenu : NSObject

- (instancetype)initWithHost:(id<LibretroFrontendMenuHost>)host;

/// Rows to insert in the root menu's "display" section, in this order:
/// Skins, Format d'écran, Disposition des écrans (DS / 3DS only), Shaders,
/// Commandes. Each row has a detail summarising the current value and
/// pushes its page.
- (NSArray<LibretroMenuRow *> *)rootRows;

/// The presets of one category of the shader catalogue ("upscaling",
/// "pixel-art"): the page Shaders › Catalogue › that category shows, saved
/// for the console unless the game has its own shader. Nil when the
/// catalogue is unavailable or the category empty.
- (nullable LibretroMenuPage *)shaderCategoryPage:(NSString *)category;
/// Translated name of a shader catalogue category.
- (NSString *)textForCategory:(NSString *)category;

@end

NS_ASSUME_NONNULL_END
