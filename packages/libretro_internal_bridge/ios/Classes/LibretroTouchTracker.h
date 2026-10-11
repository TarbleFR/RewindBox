#import <Foundation/Foundation.h>

#import "LibretroGeometry.h"
#import "LibretroInputMap.h"
#import "LibretroSkinLayout.h"

NS_ASSUME_NONNULL_BEGIN

/// What one finger is doing.
typedef NS_ENUM(NSInteger, LibretroTouchMode) {
  /// Buttons and D-pads under the finger, hit-tested again on every move
  /// (Delta: a finger slides between buttons).
  LibretroTouchModeFree = 0,
  /// Started on a D-pad alone: stays bound to it, directions follow the
  /// finger even past its edge.
  LibretroTouchModeDPad,
  /// Started on a thumbstick: bound to it until released.
  LibretroTouchModeStick,
  /// RETRO_DEVICE_POINTER on the DS / 3DS touch screen.
  LibretroTouchModePointer,
  /// Controls disabled and outside the touch screen.
  LibretroTouchModeIgnored,
};

/// One finger as resolved by the tracker (touch diagnostics).
@interface LibretroTouchContact : NSObject
/// Arrival order of the finger in this tracker.
@property(nonatomic, readonly) NSUInteger serial;
@property(nonatomic, readonly) LibretroTouchMode mode;
@property(nonatomic, readonly) double x;
@property(nonatomic, readonly) double y;
/// Items under the finger (free mode) or bound to it (D-pad, stick).
@property(nonatomic, readonly, copy) NSArray<NSString *> *itemIdentifiers;
/// Logical inputs this finger really sends now (to the core, or frontend
/// actions); "touchScreen" for the pointer.
@property(nonatomic, readonly, copy) NSArray<NSString *> *sentInputs;
/// Inputs of the touched items that send nothing for this console
/// (unsupported or blocked), shown so a dead button is never mistaken for a
/// working one.
@property(nonatomic, readonly, copy) NSArray<NSString *> *inertInputs;
@end

/// Everything the touches produce at one instant.
@interface LibretroTouchResolution : NSObject
/// Port 0 RetroPad buttons and analog axes from the touch controls.
@property(nonatomic, readonly) LibretroCoreInput coreInput;
/// RETRO_DEVICE_POINTER (DS / 3DS touch screen); when released, the place
/// it was last seen.
@property(nonatomic, readonly) BOOL pointerPressed;
@property(nonatomic, readonly) int16_t pointerX;
@property(nonatomic, readonly) int16_t pointerY;
/// Items that send at least one input (or action) now: the only ones the
/// skin may highlight.
@property(nonatomic, readonly, copy) NSSet<NSString *> *pressedItems;
/// Items under a finger that send nothing (no supported input for the
/// console, blocked button, empty remap). Never highlighted.
@property(nonatomic, readonly, copy) NSSet<NSString *> *inertItems;
/// Frontend actions held now (LibretroFrontendAction values).
@property(nonatomic, readonly, copy) NSSet<NSNumber *> *actions;
/// Deflection of every thumbstick held by a finger: {itemId: NSValue of a
/// CGPoint-compatible pair (x, y in -1...1, y positive downward)} stored as
/// LibretroSize {w: x, h: y}.
@property(nonatomic, readonly, copy) NSDictionary<NSString *, NSValue *> *stickVectors;
/// One entry per finger, by arrival order; empty unless the tracker
/// `recordsContacts`.
@property(nonatomic, readonly, copy) NSArray<LibretroTouchContact *> *contacts;
@end

/// Touch handling of a skin, without UIKit: hit test, finger modes, D-pad,
/// sticks, pointer and translation of every item to the core's input
/// through the console's LibretroInputMap. LibretroTouchOverlay feeds it
/// the UITouch events; the macOS tests feed it scripted fingers, so the
/// whole chain "finger -> item -> logical input -> RetroPad state" is
/// tested without a device.
///
/// Rules (Delta): every item under a finger fires, "menu" is exclusive, a
/// finger can slide across the D-pad or between buttons, sticks stay bound
/// to their finger. A touch inside a touch-screen screen (DS / 3DS bottom
/// screen) that hits no other item becomes RETRO_DEVICE_POINTER through
/// LibretroPointerFromPoint with the screen's real output rectangle
/// (`touchScreenMappings`). On the drawn touch screen a control answers
/// only inside its visible frame. Digital targets need at least half a
/// stick deflection; analog targets take the magnitude.
@interface LibretroTouchTracker : NSObject

/// `touchRemap` {itemId: [logical inputs]} replaces an item's inputs
/// (a D-pad or stick remap names its four directions). Fingers already
/// down follow their items to the new places.
- (void)applyLayout:(nullable LibretroSkinLayoutResult *)layout
           inputMap:(LibretroInputMap *)inputMap
         touchRemap:(nullable NSDictionary<NSString *, NSArray<NSString *> *> *)touchRemap;

/// Touch-screen mappings in layout points (LibretroScreenMapping in
/// NSValue). When they change, a finger held on the touch screen keeps its
/// mapping while that screen is still drawn at the same place, follows the
/// touch screen now under it, or is released when there is none.
@property(nonatomic, copy) NSArray<NSValue *> *touchScreenMappings;

/// Physical controller connected or touch controls switched off: buttons,
/// D-pads and sticks are ignored, the touch screen keeps working.
@property(nonatomic, assign) BOOL controlsDisabled;

/// Fills LibretroTouchResolution.contacts (diagnostics only).
@property(nonatomic, assign) BOOL recordsContacts;

/// Fingers, identified by any copyable key (the overlay uses the UITouch
/// pointer). Coordinates in layout points.
- (void)beginTouch:(id<NSCopying>)key x:(double)x y:(double)y;
- (void)moveTouch:(id<NSCopying>)key x:(double)x y:(double)y;
/// Ended or cancelled: the finger's inputs are released.
- (void)endTouch:(id<NSCopying>)key;
- (void)endAllTouches;
@property(nonatomic, readonly) NSUInteger touchCount;

/// The state every finger produces now.
- (LibretroTouchResolution *)resolve;

@end

NS_ASSUME_NONNULL_END
