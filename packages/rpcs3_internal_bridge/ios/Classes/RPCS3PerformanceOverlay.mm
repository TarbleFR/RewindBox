// SPDX-License-Identifier: GPL-3.0-or-later
#import "RPCS3PerformanceOverlay.h"
#import "RPCS3InGameLocalization.h"
#include "NeoSwapUsagePolicy.h"
#include "RPCS3OverlayButtonLayout.h"
#include <cmath>

// Minimal performance overlay on RPCS3's own model (maintainer, 16 Nov 2026: « reprends celui de RPCS3 comme base
// minimaliste »). RPCS3's perf_metrics_overlay, at its low detail level, writes "FPS : %05.2f" and "CPU : %04.1f %%"
// as a monospaced block of yellow text (Body Color #FFE138) on a dark blue box (Body Background #002339), both at
// 70 % opacity (rpcs3/Emu/RSX/Overlays/overlay_perf_metrics.cpp and the Performance Overlay defaults of
// system_config.h). The same block here, with the two memory lines the maintainer asked for, the colons aligned as
// RPCS3 aligns its medium level (" PPU   : ", " Total : "):
//   FPS     : 59.94    frames presented per second (Core metric, its validity bit kept);
//   CPU     : 45.2 %   the process's CPU time over all the device's cores, 0-100 % (Core metric rpcs3_ios_performance_cpu);
//   RAM     : 2.81 GB  the app's kernel footprint (phys_footprint), decimal GB;
//   NeoSwap : 1.20 GB  the backing NeoSwap currently donates to RPCS3 (published guest objects plus active relay and
//                      donor loans), decimal GB; never prepared capacity, idle shelves or aliases (NeoSwapMemoryGraph).
// The two memory values stay independent: no sum, no graph. Numbers follow the user's locale (decimal separator, GB
// unit). Drawn by UIKit above the game image, not inside it, so it keeps updating while a game is frozen; RPCS3's own
// overlay stays available in the emulator settings. Four single-line labels, updated by the owner's sampler only while
// the block is visible.
namespace {
constexpr CGFloat kPaddingX = 6.0;
constexpr CGFloat kLineHeight = 15.0;
constexpr CGFloat kFontSize = 12.0;
constexpr NSUInteger kNameWidth = 7;    // "NeoSwap", the longest name: the colons line up
constexpr uint32_t kCPUValid = 1U << 1; // rpcs3_ios_performance_cpu (Rpcs3CoreABI.h)

// RPCS3's default colours at its default opacity (Performance Overlay: Opacity 70 %).
UIColor* RPCS3BodyColor() { return [UIColor colorWithRed:0xFF / 255.0 green:0xE1 / 255.0 blue:0x38 / 255.0 alpha:0.7]; }
UIColor* RPCS3BackgroundColor() { return [UIColor colorWithRed:0x00 / 255.0 green:0x23 / 255.0 blue:0x39 / 255.0 alpha:0.7]; }
}

@interface RPCS3PerformanceOverlay ()
@property(nonatomic, strong) UILabel* fpsValue;
@property(nonatomic, strong) UILabel* cpuValue;
@property(nonatomic, strong) UILabel* ramValue;
@property(nonatomic, strong) UILabel* neoswapValue;
@property(nonatomic, strong) NSArray<UILabel*>* lines;
@property(nonatomic, copy) NSString* fpsText;
@property(nonatomic, copy) NSString* cpuText;
@property(nonatomic, copy) NSString* ramText;
@property(nonatomic, copy) NSString* neoswapText;
@property(nonatomic, strong) NSNumberFormatter* fpsFormatter;
@property(nonatomic, strong) NSNumberFormatter* cpuFormatter;
@property(nonatomic, strong) NSNumberFormatter* memoryFormatter;
@property(nonatomic, copy) NSString* localeIdentifier;
@end

@implementation RPCS3PerformanceOverlay
- (instancetype)initWithFrame:(CGRect)frame {
  self = [super initWithFrame:frame];
  if (!self) return nil;
  self.opaque = NO;
  self.backgroundColor = RPCS3BackgroundColor();
  self.clipsToBounds = YES;
  self.userInteractionEnabled = NO;
  self.isAccessibilityElement = YES;
  self.accessibilityTraits = UIAccessibilityTraitStaticText;
  self.accessibilityIdentifier = @"rpcs3.performance.overlay";
  self.fpsValue = [self newLineLabel];
  self.cpuValue = [self newLineLabel];
  self.ramValue = [self newLineLabel];
  self.neoswapValue = [self newLineLabel];
  self.lines = @[self.fpsValue, self.cpuValue, self.ramValue, self.neoswapValue];
  // RPCS3's widths: "%05.2f" (FPS) and "%04.1f" (CPU) keep two integer digits.
  self.fpsFormatter = [self newFormatterWithIntegerDigits:2 fractionDigits:2];
  self.cpuFormatter = [self newFormatterWithIntegerDigits:2 fractionDigits:1];
  self.memoryFormatter = [self newFormatterWithIntegerDigits:1 fractionDigits:2];
  [self setLocaleIdentifier:NSLocale.preferredLanguages.firstObject ?: @"en"];
  return self;
}
- (UILabel*)newLineLabel {
  UILabel* label = [UILabel new];
  label.font = [UIFont monospacedSystemFontOfSize:kFontSize weight:UIFontWeightMedium];
  label.textColor = RPCS3BodyColor();
  label.textAlignment = NSTextAlignmentLeft;
  label.adjustsFontSizeToFitWidth = YES;
  label.minimumScaleFactor = 0.75;
  label.isAccessibilityElement = NO;
  [self addSubview:label];
  return label;
}
- (NSNumberFormatter*)newFormatterWithIntegerDigits:(NSUInteger)integerDigits fractionDigits:(NSUInteger)fractionDigits {
  NSNumberFormatter* formatter = [NSNumberFormatter new];
  formatter.numberStyle = NSNumberFormatterDecimalStyle;
  formatter.usesGroupingSeparator = NO;
  formatter.minimumIntegerDigits = integerDigits;
  formatter.minimumFractionDigits = fractionDigits;
  formatter.maximumFractionDigits = fractionDigits;
  return formatter;
}
- (void)setLocaleIdentifier:(NSString*)localeIdentifier {
  _localeIdentifier = RPCS3CanonicalLocale(localeIdentifier);
  NSLocale* locale = [NSLocale localeWithLocaleIdentifier:_localeIdentifier];
  self.fpsFormatter.locale = locale;
  self.cpuFormatter.locale = locale;
  self.memoryFormatter.locale = locale;
  self.accessibilityLabel = RPCS3LocalizedString(@"performance", _localeIdentifier);
  if (self.neoswapValue) [self reset];
}
- (CGSize)intrinsicContentSize { return CGSizeMake(rpcs3_overlay::kPanelWidth, rpcs3_overlay::kPanelHeight); }
- (void)layoutSubviews {
  [super layoutSubviews];
  const CGFloat width = MAX(0.0, self.bounds.size.width - 2.0 * kPaddingX);
  // The four lines sit in the middle of whatever height the layout gives the block.
  const CGFloat top = MAX(0.0, (self.bounds.size.height - kLineHeight * self.lines.count) / 2.0);
  for (NSUInteger row = 0; row < self.lines.count; ++row) {
    self.lines[row].frame = CGRectMake(kPaddingX, top + kLineHeight * row, width, kLineHeight);
  }
}
- (NSString*)line:(NSString*)name value:(NSString*)value {
  return [NSString stringWithFormat:@"%@ : %@", [name stringByPaddingToLength:kNameWidth withString:@" " startingAtIndex:0], value];
}
- (NSString*)memoryText:(uint64_t)bytes valid:(BOOL)valid {
  if (!valid) return @"—";
  return [NSString stringWithFormat:@"%@ %@", [self.memoryFormatter stringFromNumber:@(NeoSwapDecimalGB(bytes))],
      RPCS3LocalizedString(@"memoryUnitGB", _localeIdentifier)];
}
- (void)refreshLines {
  self.fpsValue.text = [self line:@"FPS" value:self.fpsText];
  self.cpuValue.text = [self line:@"CPU" value:self.cpuText];
  self.ramValue.text = [self line:@"RAM" value:self.ramText];
  self.neoswapValue.text = [self line:@"NeoSwap" value:self.neoswapText];
  // Spoken with the full names of the two memory values (12 languages).
  self.accessibilityValue = [NSString stringWithFormat:@"FPS %@. CPU %@. %@: %@. %@: %@",
      self.fpsText, self.cpuText,
      RPCS3LocalizedString(@"memoryDevice", _localeIdentifier), self.ramText,
      RPCS3LocalizedString(@"memoryNeoSwap", _localeIdentifier), self.neoswapText];
}
- (void)reset {
  NSAssert(NSThread.isMainThread, @"RPCS3 performance UI must run on the main thread");
  self.fpsText = @"—";
  self.cpuText = @"—";
  self.ramText = @"—";
  self.neoswapText = @"—";
  [self refreshLines];
}
- (void)appendMetricsWithFPS:(double)fps cpu:(double)cpu gpu:(double)gpu
                  memoryUsed:(uint64_t)memoryUsed memoryTotal:(uint64_t)memoryTotal
                 validFields:(uint32_t)validFields timestamp:(double)timestampMs {
  NSAssert(NSThread.isMainThread, @"RPCS3 performance UI must run on the main thread");
  (void)gpu; (void)memoryUsed; (void)memoryTotal;
  if (self.hidden || !std::isfinite(timestampMs)) return;
  self.fpsText = NeoSwapFPSValid(fps, validFields) ? [self.fpsFormatter stringFromNumber:@(fps)] : @"—";
  const bool cpuValid = (validFields & kCPUValid) && std::isfinite(cpu) && cpu >= 0.0;
  self.cpuText = cpuValid ? [NSString stringWithFormat:@"%@ %%", [self.cpuFormatter stringFromNumber:@(std::fmin(cpu, 100.0))]] : @"—";
  [self refreshLines];
}
- (void)appendNeoSwapWithClient:(const NeoSwapClientStats*)client
                          host:(const NeoSwapHostStats*)host
                relayGuestPublishedBytes:(uint64_t)relayGuestPublishedBytes
                 relayGuestMeasured:(BOOL)relayGuestMeasured
         processFootprintBytes:(uint64_t)processFootprintBytes
                     timestamp:(double)timestampMs {
  NSAssert(NSThread.isMainThread, @"RPCS3 performance UI must run on the main thread");
  if (self.hidden || !std::isfinite(timestampMs)) return;
  (void)client;
  // The app's actual kernel footprint and, independently, the backing currently donated to RPCS3.
  const auto point = NeoSwapMemoryGraph(host, relayGuestPublishedBytes, relayGuestMeasured, processFootprintBytes);
  self.ramText = [self memoryText:point.footprint valid:point.footprintValid];
  self.neoswapText = [self memoryText:point.donated valid:point.donatedValid];
  [self refreshLines];
}
@end
