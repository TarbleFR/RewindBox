// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#import "NeoTouchLayoutModel.h"
#import "NeoTouchLayoutStore.h"

NS_ASSUME_NONNULL_BEGIN

/// What an engine's touch overlay offers to the editor.
@protocol NeoTouchLayoutEditorHost <NSObject>
/// The view the controls live in; stored positions are relative to its safe area.
- (UIView*)touchLayoutCanvas;
/// The movable controls with their stock geometry for the canvas' current
/// bounds, in drawing order (the last one is on top).
- (NSArray<NeoTouchElement*>*)touchLayoutElements;
/// Places the controls from `layout` now and on every later layout pass until
/// called again. `editing` shows hidden controls faintly; the host must not
/// send any input while editing.
- (void)touchLayoutApplyLayout:(nullable NeoTouchLayout*)layout editing:(BOOL)editing;
@optional
/// Orientations the engine's game sessions use (default: all but upside
/// down). The editor opened from the settings offers only these, so a layout
/// is never edited for an orientation the game never shows.
- (UIInterfaceOrientationMask)touchLayoutSupportedInterfaceOrientations;
@end

/// Posted by a host, with its canvas as the object, when it placed its
/// controls again on its own (for example once the engine's layout settled).
/// An editor shown over that canvas reads the controls again.
FOUNDATION_EXPORT NSNotificationName const NeoTouchLayoutHostDidRelayoutNotification;

typedef NS_ENUM(NSInteger, NeoTouchLayoutScope) {
  NeoTouchLayoutScopeGeneral = 0,
  NeoTouchLayoutScopeGame = 1,
};

/// On-screen editor of one touch layout, drawn over the engine's real
/// controls at their real size. It receives every touch on the screen while
/// it is shown: controls are moved, resized, faded and hidden here, never
/// pressed. Nothing is stored before Save; Cancel leaves the stored layouts
/// unchanged. The surface orientation (portrait or landscape) selects the
/// edited layout; a game session can edit its own layout or the general one.
@interface NeoTouchLayoutEditor : UIView
- (instancetype)initWithHost:(id<NeoTouchLayoutEditorHost>)host
                   layoutKey:(NSString*)layoutKey
                     gameKey:(nullable NSString*)gameKey
                       title:(nullable NSString*)title
                      locale:(nullable NSString*)locale
                       store:(NeoTouchLayoutStore*)store NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithFrame:(CGRect)frame NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;

/// Called once, after the editor removed itself, with YES when a layout was saved.
@property(nonatomic, copy, nullable) void (^finished)(BOOL saved);
/// Shows that the touch controls are displayed for editing only.
@property(nonatomic) BOOL controllerConnected;
@property(nonatomic, readonly) NSString* layoutKey;
@property(nonatomic, readonly, nullable) NSString* gameKey;
@property(nonatomic, readonly) NeoTouchLayoutScope scope;
@property(nonatomic, readonly) NSString* orientation;
@property(nonatomic, readonly, nullable) NSString* selectedIdentifier;
@property(nonatomic, readonly) BOOL hasChanges;
@property(nonatomic, readonly) BOOL previewing;

/// Adds the editor above everything in the canvas' superview, with the
/// canvas frame, and shows the current draft on the real controls.
- (void)presentOverCanvas;

// Editing actions, bound to the editor's own controls (and used by tests).
- (void)selectScope:(NeoTouchLayoutScope)scope;
- (void)selectElement:(nullable NSString*)identifier;
/// Moves a control so its centre is `center` (canvas coordinates), kept on screen.
- (void)moveElement:(NSString*)identifier toCenter:(CGPoint)center;
- (void)setScale:(CGFloat)scale forElement:(NSString*)identifier;
- (void)setOpacity:(CGFloat)opacity forElement:(NSString*)identifier;
- (void)setHidden:(BOOL)hidden forElement:(NSString*)identifier;
- (void)resetElement:(NSString*)identifier;
- (void)undo;
- (void)restoreDefaultLayout;
/// Game scope: the game follows the general layout again (on Save).
- (void)useGeneralLayout;
- (void)setPreviewing:(BOOL)previewing;
- (void)toggleToolbarPosition;
/// Stores every changed draft; on success removes the editor and calls
/// `finished(YES)`. On failure the editor stays open and shows the error.
- (BOOL)save;
- (void)cancel;
/// Draft of the current scope and orientation.
- (NeoTouchLayout*)draftLayout;
/// Visible frame of a control under the current draft, in editor coordinates.
- (CGRect)frameOfElement:(NSString*)identifier;
@end

typedef UIView<NeoTouchLayoutEditorHost>* _Nullable (^NeoTouchLayoutPreviewFactory)(NSString* layoutKey,
                                                                                     NSString* locale);

/// Engines register how to build their touch controls without a game, so
/// the editor can be opened from the settings outside a session. A preview
/// never sends input.
@interface NeoTouchLayoutRegistry : NSObject
+ (void)registerPreviewFactory:(NeoTouchLayoutPreviewFactory)factory forLayoutKeys:(NSArray<NSString*>*)keys;
+ (nullable NeoTouchLayoutPreviewFactory)previewFactoryForLayoutKey:(NSString*)key;
@end

/// Full-screen editor outside a game: the engine's preview controls on a
/// neutral background, general layout only.
@interface NeoTouchLayoutEditorController : UIViewController
- (nullable instancetype)initWithLayoutKey:(NSString*)layoutKey locale:(nullable NSString*)locale;
@property(nonatomic, readonly) NSString* layoutKey;
@property(nonatomic, readonly, nullable) NeoTouchLayoutEditor* editor;
@property(nonatomic, copy, nullable) void (^finished)(BOOL saved);
@end

NS_ASSUME_NONNULL_END
