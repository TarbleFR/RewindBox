#import <QuartzCore/QuartzCore.h>
#import <UIKit/UIKit.h>
#import <external_display/NeoExternalRenderHost.h>

#import "LibretroSkin.h"
#import "LibretroSkinLayout.h"

@class LibretroInputState;
@class LibretroSkinRenderer;
@class LibretroTouchOverlay;

NS_ASSUME_NONNULL_BEGIN

/// What the game view needs to lay out the current skin. Provided by the
/// session; called on the main thread at every layout (rotation, size or
/// setting change).
@protocol LibretroGameViewLayoutSource <NSObject>
/// Representation to show in the view of `size` points for an orientation;
/// the session resolves the selected skin (game, console, default) and falls
/// back to the default skin when the selected one lacks the orientation.
- (LibretroSkinRepresentation *)representationForOrientation:(LibretroSkinOrientation)orientation
                                                    viewSize:(LibretroSize)size
                                                  safeInsets:(LibretroInsets)insets
                                                        iPad:(BOOL)iPad;
/// User layout overrides for the shown representation.
- (nullable NSDictionary<NSString *, NSDictionary *> *)layoutOverridesForRepresentation:
    (LibretroSkinRepresentation *)representation;
/// Applies the layout to the overlay (remaps) and the picture to the
/// presenter. `layout` is the iPhone view's, where the skin, the overlay and
/// the game areas were laid out. `screens` are the game areas of the
/// picture, in a space of `pointSize` points; `drawableSize` is the surface
/// the picture is drawn into, in pixels. On the phone they are the layout's
/// own screens in the view's bounds and the view's drawable; while the
/// external display shows the game (NeoExternalRenderHost) they are the
/// same areas placed in the TV's surface (LibretroRenderSurfacePlacement:
/// scaled uniformly and centred, the black around them left out) and the
/// TV's drawable. The presenter places each screen in the drawable at its
/// proportional place in `pointSize`.
- (void)gameViewDidLayout:(LibretroSkinLayoutResult *)layout
           representation:(LibretroSkinRepresentation *)representation
                  screens:(NSArray<LibretroLaidOutScreen *> *)screens
             drawableSize:(CGSize)drawableSize
                   points:(CGSize)pointSize;
@end

/// Overrides the controls editor starts from ({item identifier: override}).
typedef NSDictionary<NSString *, NSDictionary *> * (^LibretroControlsOverridesProvider)(void);

/// Full-screen surface of an embedded libretro session: the CAMetalLayer for
/// the picture, the skin renderer, the touch overlay, a menu button and
/// short status messages. Supports portrait and landscape (see
/// LibretroOrientation).
///
/// External display (NeoExternalRenderHost, fixedDrawable == NO): the
/// coordinator moves the Metal view into NeoStation's window on the TV and
/// reports the surface it gave it; the picture is then rendered at the TV's
/// resolution while the skin, the touch overlay, the menu button and the
/// status line stay on the iPhone. The session attaches the controller once
/// its view appeared and detaches it before stopping the core. The surface
/// is the whole TV in every format (each game keeps its own aspect through
/// LibretroRenderSurfacePlacement); a rotation of the iPhone while the
/// picture is on the TV asks the coordinator to place it again (main
/// thread, coalesced).
@interface LibretroGameViewController : UIViewController <NeoExternalRenderHost>

- (instancetype)initWithInput:(LibretroInputState *)input cacheDirectory:(NSString *)cacheDirectory;

@property(nonatomic, readonly) CAMetalLayer *metalLayer;
/// NeoStation language of the session (LibretroSessionConfiguration
/// .uiLocale): selects the native external-display status line
/// (NeoExternalDisplayLabels). Set by the session before the view appears.
@property(nonatomic, copy) NSString *uiLocale;
@property(nonatomic, readonly) LibretroSkinRenderer *skinRenderer;
@property(nonatomic, readonly) LibretroTouchOverlay *overlay;
@property(nonatomic, weak, nullable) id<LibretroGameViewLayoutSource> layoutSource;
@property(nonatomic, copy, nullable) void (^menuHandler)(void);
@property(nonatomic, copy, nullable) void (^layoutHandler)(CGSize drawableSize);
@property(nonatomic, copy, nullable) void (^activeHandler)(BOOL active);
/// Normalized touch-screen mappings of the last frame (presenter).
@property(nonatomic, copy, nullable) NSArray<NSValue *> * (^screenMappingsProvider)(void);
@property(nonatomic, assign) BOOL touchControlsEnabled;
/// Developer touch diagnostics (LibretroTouchDiagnosticsView) above the
/// controls: touch areas, fingers, inputs sent and the state the core read.
@property(nonatomic, assign) BOOL touchDiagnosticsEnabled;
@property(nonatomic, assign) CGFloat controlsOpacity;
@property(nonatomic, copy) NSString *menuAccessibilityLabel;
/// Orientations allowed while the game is shown.
@property(nonatomic, assign) UIInterfaceOrientationMask allowedOrientations;

/// Re-runs the skin layout now (setting changed in the menu).
- (void)setNeedsSkinLayout;
@property(nonatomic, readonly) LibretroSkinOrientation currentOrientation;

/// Controls editing ("Commandes › Modifier la disposition"): shows a small
/// toolbar with Done / Reset defaults (translated titles) above the game.
/// Starts from the overrides in effect for the representation on screen.
- (void)beginEditingControlsWithDoneTitle:(NSString *)doneTitle
                               resetTitle:(NSString *)resetTitle
                                     hint:(NSString *)hint
                                 finished:(void (^)(void))finished
                                    reset:(void (^)(void))reset;

/// Same, starting from what `startingOverrides` returns, asked again after
/// each Reset: the scope being edited decides it (at console scope the
/// console's own layout, never the game's, see LibretroChromeLayout). nil
/// gives the overrides in effect for the representation on screen.
- (void)beginEditingControlsWithDoneTitle:(NSString *)doneTitle
                               resetTitle:(NSString *)resetTitle
                                     hint:(NSString *)hint
                        startingOverrides:(nullable LibretroControlsOverridesProvider)startingOverrides
                                 finished:(void (^)(void))finished
                                    reset:(void (^)(void))reset;

- (void)showStatus:(NSString *)message;
- (void)setLoading:(BOOL)loading;
- (void)stopInputPolling;

@end

NS_ASSUME_NONNULL_END
