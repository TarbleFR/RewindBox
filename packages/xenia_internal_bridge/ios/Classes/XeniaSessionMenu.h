// SPDX-License-Identifier: BSD-3-Clause
// The Xbox 360 in-game menu and performance overlay (docs/xenios-playlist.md
// § In-game menu). Texts come from Dart (XeniaLocale, 12 locales) with English
// fallbacks; values are the XeniOS cvar values RewindBox manages.
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Performance overlay levels, in menu order: off, simple, detailed.
FOUNDATION_EXPORT NSArray<NSString*>* RBXeniaOverlayLevels(void);
/// The resolution XeniOS reports for internal_display_resolution 0...16 (8 is the engine default).
FOUNDATION_EXPORT NSString* RBXeniaResolutionLabel(NSInteger index);
/// Number of internal_display_resolution values offered (17, the custom size, is not).
FOUNDATION_EXPORT const NSInteger RBXeniaResolutionCount;

/// What the menu asks of the session that opened it. Every call is on main.
@protocol RBXeniaSessionMenuHost <NSObject>
- (void)sessionMenuResume;
- (void)sessionMenuEditTouchControls;
- (void)sessionMenuQuit;
/// Applies at once and is saved for every Xbox 360 game.
- (void)sessionMenuSetOverlayLevel:(NSString*)level;
/// Saved for this game; the engine reads it at the next launch.
- (void)sessionMenuSetGameSetting:(NSString*)key value:(NSString*)value;
@end

/// Resume, Display (performance overlay), This game (aspect ratio, reported
/// resolution, letterbox), touch controls and Quit, as the other playlists'
/// in-game menus. Presented inside a UINavigationController.
@interface RBXeniaSessionMenu : UITableViewController <UIAdaptivePresentationControllerDelegate>
- (instancetype)initWithTitle:(NSString*)title
                        texts:(NSDictionary<NSString*, NSString*>*)texts
                       locale:(NSString*)locale
                     settings:(NSDictionary<NSString*, NSString*>*)settings
                 overlayLevel:(NSString*)overlayLevel
                         host:(id<RBXeniaSessionMenuHost>)host NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithStyle:(UITableViewStyle)style NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder*)coder NS_UNAVAILABLE;
- (instancetype)initWithNibName:(nullable NSString*)nibName bundle:(nullable NSBundle*)bundle NS_UNAVAILABLE;
@end

/// Passive, non-interactive overlay: the session feeds it guest frame samples
/// (NeoXeniaAPI get_stats); it adds the process memory footprint and the
/// device thermal state. All methods on main.
@interface RBXeniaPerformanceOverlay : UIView
- (instancetype)initWithTexts:(NSDictionary<NSString*, NSString*>*)texts locale:(NSString*)locale;
/// off | simple | detailed. Off hides the view and forgets the samples.
@property(nonatomic, copy) NSString* level;
/// Forget the previous sample (after a pause, so the rate never spans it).
- (void)resetSamples;
- (void)sampleGuestFrames:(uint64_t)frames atNanoseconds:(uint64_t)nanoseconds;
@end

NS_ASSUME_NONNULL_END
