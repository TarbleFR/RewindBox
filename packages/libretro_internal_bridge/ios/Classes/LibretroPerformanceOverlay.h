#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Performance overlay of a libretro game ("Performance overlay" toggle of
/// the in-game menu, NSUserDefaults "libretro.performanceOverlay"): a few
/// lines of technical text (numbers and identifiers, not translated, like
/// LibretroTouchDiagnosticsView) on a dark rounded panel, in the manner of
/// MeloNX's overlay. The game view controller places it at the top-left of
/// the safe area, refreshes it from its display link and never lets it take
/// a touch. The lines come from LibretroSession (performanceLines).
@interface LibretroPerformanceOverlay : UIView

/// Replaces the lines shown and resizes the panel to fit them.
- (void)showLines:(NSArray<NSString *> *)lines;

@end

NS_ASSUME_NONNULL_END
