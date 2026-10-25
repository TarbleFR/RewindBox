#import <UIKit/UIKit.h>

#include "Rpcs3CoreABI.h"

NS_ASSUME_NONNULL_BEGIN

@class RPCS3TouchControlsView;

// Owns all PS3 input while the embedded RPCS3 full-screen view is active.
// Physical GameController input is sent directly to the Core ABI. The native
// touch overlay is shown unless a compatible controller is connected and the
// PS3 "hide touch controls with a controller" preference is on (default);
// with that preference off, touch and controller feed the same pad.
@interface RPCS3GameInputController : NSObject

- (instancetype)initWithHostView:(UIView*)hostView
                             api:(rpcs3_ios_api*)api
                          locale:(nullable NSString*)locale NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithHostView:(UIView*)hostView api:(rpcs3_ios_api*)api;
- (instancetype)init NS_UNAVAILABLE;

- (void)start;
- (void)stop;
@property(nonatomic, assign, getter=isTouchControlsEnabled) BOOL touchControlsEnabled;
// Home / PS and Select+Start use the same NeoStation menu as the on-screen
// action button. The embedded input path never opens a second native menu.
@property(nonatomic, copy, nullable) dispatch_block_t menuRequested;
- (void)layoutControlsInBounds:(CGRect)bounds safeAreaInsets:(UIEdgeInsets)insets;

// Build 484: per-game layout key, the on-screen editor and its state.
@property(nonatomic, copy, nullable) NSString* gameKey;
@property(nonatomic, readonly) RPCS3TouchControlsView* touchControls;
@property(nonatomic, readonly, getter=isEditingTouchLayout) BOOL editingTouchLayout;
/// The editor while it is shown (kept above the action rail by the host).
@property(nonatomic, readonly, weak, nullable) UIView* activeEditor;
/// Shows the editor over the touch controls. While it is open the Core
/// receives a released, connected pad: no touch and no controller input.
- (void)beginTouchLayoutEditingWithTitle:(nullable NSString*)title completion:(dispatch_block_t)completion;
/// Re-reads the visibility policy (controller, preference, switch).
- (void)updateTouchVisibility;

@end

NS_ASSUME_NONNULL_END
