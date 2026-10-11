#import <UIKit/UIKit.h>

#import "LibretroCoreHost.h"
#import "LibretroSkinLayout.h"
#import "LibretroTouchTracker.h"

NS_ASSUME_NONNULL_BEGIN

/// Developer view of the touch chain, drawn above the controls while
/// "Touch diagnostics" is on (never takes a touch):
/// - every control's touch area (dashed) and drawing (solid), green when it
///   can send an input, red when it is dead for this console;
/// - each finger: the items under it, the inputs it really sends, the inert
///   ones;
/// - the state the core really received at its last read (frame number,
///   RetroPad buttons, analog axes, pointer), which is the proof a command
///   arrived, unlike a highlighted button;
/// - the delay iOS took to deliver the last touches (screen-edge gestures).
/// Technical text only (identifiers, numbers), not translated.
@interface LibretroTouchDiagnosticsView : UIView

- (void)showLayout:(nullable LibretroSkinLayoutResult *)layout deadItems:(NSSet<NSString *> *)deadItems;
- (void)showResolution:(LibretroTouchResolution *)resolution;
- (void)showDelivered:(LibretroInputSnapshot)snapshot frame:(uint64_t)frame;
- (void)noteDeliveryDelay:(NSTimeInterval)delay;

@end

NS_ASSUME_NONNULL_END
