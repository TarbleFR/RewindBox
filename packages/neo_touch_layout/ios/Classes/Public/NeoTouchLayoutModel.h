// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Layout keys: one touch layout per pad. GameCube "gc", Wii Remote and
/// Nunchuk "wii", Wii Classic Controller "wii-classic", PlayStation 2 "ps2",
/// PlayStation 3 "ps3". The console of "wii-classic" is "wii".
FOUNDATION_EXPORT NSString* const NeoTouchLayoutKeyGameCube;
FOUNDATION_EXPORT NSString* const NeoTouchLayoutKeyWii;
FOUNDATION_EXPORT NSString* const NeoTouchLayoutKeyWiiClassic;
FOUNDATION_EXPORT NSString* const NeoTouchLayoutKeyPlayStation2;
FOUNDATION_EXPORT NSString* const NeoTouchLayoutKeyPlayStation3;

FOUNDATION_EXPORT NSString* const NeoTouchLayoutOrientationLandscape;
FOUNDATION_EXPORT NSString* const NeoTouchLayoutOrientationPortrait;

/// "portrait" when the surface is taller than wide, else "landscape".
FOUNDATION_EXPORT NSString* NeoTouchLayoutOrientationForSize(CGSize size);
/// Console of a layout key: "gc", "wii", "ps2" or "ps3" (the key itself otherwise).
FOUNDATION_EXPORT NSString* NeoTouchLayoutConsoleForKey(NSString* key);
/// YES for a key made of a-z, 0-9 and '-' (1-32 characters).
FOUNDATION_EXPORT BOOL NeoTouchLayoutKeyIsValid(NSString* _Nullable key);
/// Stable per-game key: trimmed, lower-cased, at most 200 characters. nil
/// when nothing identifies the game (BIOS or system menu sessions).
FOUNDATION_EXPORT NSString* _Nullable NeoTouchLayoutGameKey(NSString* _Nullable raw);

typedef NS_ENUM(NSInteger, NeoTouchElementKind) {
  NeoTouchElementKindButton = 0,
  NeoTouchElementKindDirectionalPad = 1,
  NeoTouchElementKindStick = 2,
  NeoTouchElementKindTrigger = 3,
  NeoTouchElementKindSystem = 4,
};

/// One movable touch control of an engine: the engine's own view, its stable
/// identifier and its stock geometry on the current surface. The applier
/// places the view with one transform, so its drawing and its touch area
/// always stay together.
@interface NeoTouchElement : NSObject
- (instancetype)initWithIdentifier:(NSString*)identifier
                              name:(NSString*)name
                              kind:(NeoTouchElementKind)kind
                              view:(UIView*)view NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;
@property(nonatomic, copy, readonly) NSString* identifier;
@property(nonatomic, copy) NSString* name;
@property(nonatomic, readonly) NeoTouchElementKind kind;
@property(nonatomic, weak, readonly, nullable) UIView* view;
/// Stock centre in canvas coordinates, without any layout transform.
@property(nonatomic) CGPoint defaultCenter;
/// Stock size (the view's bounds size).
@property(nonatomic) CGSize defaultSize;
/// Stock alpha of the view (read once, before any layout opacity); the
/// layout opacity multiplies it.
@property(nonatomic) CGFloat defaultAlpha;
/// Captures defaultCenter, defaultSize and defaultAlpha from the view as the
/// engine laid it out (identity transform), converted to `canvas`.
- (void)captureDefaultGeometryInCanvas:(UIView*)canvas;
@end

/// Customisation of one control. Absent values are the stock values.
@interface NeoTouchControlState : NSObject <NSCopying>
@property(nonatomic) BOOL hasPosition;
/// Centre relative to the safe area (NeoTouchLayoutGeometry.h).
@property(nonatomic) double x;
@property(nonatomic) double y;
/// Factor of the stock size, NEO_TOUCH_MIN_SCALE...NEO_TOUCH_MAX_SCALE.
@property(nonatomic) double scale;
/// Factor of the stock alpha, NEO_TOUCH_MIN_OPACITY...1.
@property(nonatomic) double opacity;
@property(nonatomic) BOOL hidden;
/// Validated state; damaged values fall back to their stock value.
+ (instancetype)stateFromDictionary:(nullable NSDictionary*)dictionary;
/// JSON object; nil when every value is the stock value.
- (nullable NSDictionary<NSString*, id>*)dictionaryRepresentation;
@property(nonatomic, readonly) BOOL isDefault;
@end

/// The customised controls of one layout, orientation and scope. Controls
/// that are absent keep their stock placement.
@interface NeoTouchLayout : NSObject <NSCopying>
+ (instancetype)layoutFromDictionary:(nullable NSDictionary*)dictionary;
/// Copy of the stored state, or a stock state.
- (NeoTouchControlState*)stateForIdentifier:(NSString*)identifier;
/// A default (or nil) state removes the control's customisation.
- (void)setState:(nullable NeoTouchControlState*)state forIdentifier:(NSString*)identifier;
@property(nonatomic, readonly) NSArray<NSString*>* customizedIdentifiers;
@property(nonatomic, readonly, getter=isEmpty) BOOL empty;
/// {"elements": {identifier: state}}
- (NSDictionary<NSString*, id>*)dictionaryRepresentation;
- (BOOL)isEqualToLayout:(nullable NeoTouchLayout*)other;
@end

NS_ASSUME_NONNULL_END
