// SPDX-License-Identifier: GPL-3.0-or-later
#import "RPCS3PerformanceOverlay.h"
#import "RPCS3InGameLocalization.h"
#include "NeoSwapUsagePolicy.h"
#include <cmath>

// Minimal performance HUD (maintainer, 16 Nov 2026: « minimaliste », FPS, CPU, RAM and NeoSwap usage). One compact
// bar, four columns, the value above its caption:
//   FPS      frames presented per second (Core metric, its validity bit kept);
//   CPU      the process's CPU time over all the device's cores, 0-100 % (Core metric rpcs3_ios_performance_cpu);
//   RAM      the app's kernel footprint (phys_footprint), decimal GB;
//   NeoSwap  the backing NeoSwap currently donates to RPCS3 (published guest objects plus active relay and donor
//            loans), decimal GB; never prepared capacity, idle shelves or aliases (NeoSwapMemoryGraph).
// The two memory values stay independent: no sum, no graph. Nothing is drawn by hand: four value labels and four
// caption labels, updated by the owner's sampler only while the bar is visible.
namespace {
constexpr CGFloat kPadding = 8.0;
// The memory columns carry a unit and are wider.
constexpr CGFloat kColumnWeights[4] = {0.20, 0.20, 0.30, 0.30};
constexpr uint32_t kCPUValid = 1U << 1; // rpcs3_ios_performance_cpu (Rpcs3CoreABI.h)
}

@interface RPCS3PerformanceOverlay ()
@property(nonatomic, strong) UILabel* fpsValue;
@property(nonatomic, strong) UILabel* cpuValue;
@property(nonatomic, strong) UILabel* ramValue;
@property(nonatomic, strong) UILabel* neoswapValue;
@property(nonatomic, strong) NSArray<UILabel*>* values;
@property(nonatomic, strong) NSArray<UILabel*>* captions;
@property(nonatomic, strong) NSNumberFormatter* fpsFormatter;
@property(nonatomic, strong) NSNumberFormatter* percentFormatter;
@property(nonatomic, strong) NSNumberFormatter* memoryFormatter;
@property(nonatomic, copy) NSString* localeIdentifier;
@end

@implementation RPCS3PerformanceOverlay
- (instancetype)initWithFrame:(CGRect)frame {
  self = [super initWithFrame:frame];
  if (!self) return nil;
  self.opaque = NO;
  self.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.55];
  self.layer.cornerRadius = 10.0;
  self.clipsToBounds = YES;
  self.userInteractionEnabled = NO;
  self.isAccessibilityElement = YES;
  self.accessibilityTraits = UIAccessibilityTraitStaticText;
  self.accessibilityIdentifier = @"rpcs3.performance.overlay";
  self.fpsValue = [self newValueLabel];
  self.cpuValue = [self newValueLabel];
  self.ramValue = [self newValueLabel];
  self.neoswapValue = [self newValueLabel];
  self.values = @[self.fpsValue, self.cpuValue, self.ramValue, self.neoswapValue];
  // Captions are names, the same in every language; the colours keep the meaning of the former graph (orange: the
  // app's RAM, green: NeoSwap's donated backing).
  self.captions = @[[self newCaption:@"FPS" color:[UIColor colorWithWhite:1.0 alpha:0.6]],
                    [self newCaption:@"CPU" color:[UIColor colorWithWhite:1.0 alpha:0.6]],
                    [self newCaption:@"RAM" color:UIColor.systemOrangeColor],
                    [self newCaption:@"NeoSwap" color:UIColor.systemGreenColor]];
  self.fpsFormatter = [NSNumberFormatter new];
  self.fpsFormatter.numberStyle = NSNumberFormatterDecimalStyle;
  self.fpsFormatter.usesGroupingSeparator = NO;
  self.fpsFormatter.minimumFractionDigits = 1;
  self.fpsFormatter.maximumFractionDigits = 1;
  self.percentFormatter = [NSNumberFormatter new];
  self.percentFormatter.numberStyle = NSNumberFormatterPercentStyle;
  self.percentFormatter.maximumFractionDigits = 0;
  self.memoryFormatter = [NSNumberFormatter new];
  self.memoryFormatter.numberStyle = NSNumberFormatterDecimalStyle;
  self.memoryFormatter.usesGroupingSeparator = NO;
  self.memoryFormatter.minimumFractionDigits = 2;
  self.memoryFormatter.maximumFractionDigits = 2;
  [self setLocaleIdentifier:NSLocale.preferredLanguages.firstObject ?: @"en"];
  return self;
}
- (UILabel*)newValueLabel {
  UILabel* label = [UILabel new];
  label.font = [UIFont monospacedDigitSystemFontOfSize:15 weight:UIFontWeightSemibold];
  label.textColor = UIColor.whiteColor;
  label.textAlignment = NSTextAlignmentCenter;
  label.adjustsFontSizeToFitWidth = YES;
  label.minimumScaleFactor = 0.7;
  label.isAccessibilityElement = NO;
  label.text = @"—";
  [self addSubview:label];
  return label;
}
- (UILabel*)newCaption:(NSString*)text color:(UIColor*)color {
  UILabel* label = [UILabel new];
  label.font = [UIFont systemFontOfSize:9 weight:UIFontWeightMedium];
  label.textColor = color;
  label.textAlignment = NSTextAlignmentCenter;
  label.adjustsFontSizeToFitWidth = YES;
  label.minimumScaleFactor = 0.8;
  label.isAccessibilityElement = NO;
  label.text = text;
  [self addSubview:label];
  return label;
}
- (void)setLocaleIdentifier:(NSString*)localeIdentifier {
  _localeIdentifier = RPCS3CanonicalLocale(localeIdentifier);
  NSLocale* locale = [NSLocale localeWithLocaleIdentifier:_localeIdentifier];
  self.fpsFormatter.locale = locale;
  self.percentFormatter.locale = locale;
  self.memoryFormatter.locale = locale;
  self.accessibilityLabel = RPCS3LocalizedString(@"performance", _localeIdentifier);
  if (self.neoswapValue) [self reset];
}
- (CGSize)intrinsicContentSize { return CGSizeMake(256, 44); }
- (void)layoutSubviews {
  [super layoutSubviews];
  const CGFloat width = MAX(0.0, self.bounds.size.width - 2.0 * kPadding);
  // The two rows sit in the middle of whatever height the layout gives the bar.
  const CGFloat top = MAX(0.0, (self.bounds.size.height - 34.0) / 2.0);
  CGFloat x = kPadding;
  for (NSUInteger column = 0; column < self.values.count; ++column) {
    const CGFloat columnWidth = width * kColumnWeights[column];
    self.values[column].frame = CGRectMake(x, top, columnWidth, 20);
    self.captions[column].frame = CGRectMake(x, top + 21, columnWidth, 12);
    x += columnWidth;
  }
}
- (NSString*)memoryText:(uint64_t)bytes valid:(BOOL)valid {
  if (!valid) return @"—";
  return [NSString stringWithFormat:@"%@ %@", [self.memoryFormatter stringFromNumber:@(NeoSwapDecimalGB(bytes))],
      RPCS3LocalizedString(@"memoryUnitGB", _localeIdentifier)];
}
- (void)updateAccessibility {
  // Spoken with the full names of the two memory values (12 languages).
  self.accessibilityValue = [NSString stringWithFormat:@"FPS %@. CPU %@. %@: %@. %@: %@",
      self.fpsValue.text, self.cpuValue.text,
      RPCS3LocalizedString(@"memoryDevice", _localeIdentifier), self.ramValue.text,
      RPCS3LocalizedString(@"memoryNeoSwap", _localeIdentifier), self.neoswapValue.text];
}
- (void)reset {
  NSAssert(NSThread.isMainThread, @"RPCS3 performance UI must run on the main thread");
  for (UILabel* label in self.values) label.text = @"—";
  [self updateAccessibility];
}
- (void)appendMetricsWithFPS:(double)fps cpu:(double)cpu gpu:(double)gpu
                  memoryUsed:(uint64_t)memoryUsed memoryTotal:(uint64_t)memoryTotal
                 validFields:(uint32_t)validFields timestamp:(double)timestampMs {
  NSAssert(NSThread.isMainThread, @"RPCS3 performance UI must run on the main thread");
  (void)gpu; (void)memoryUsed; (void)memoryTotal;
  if (self.hidden || !std::isfinite(timestampMs)) return;
  self.fpsValue.text = NeoSwapFPSValid(fps, validFields) ? [self.fpsFormatter stringFromNumber:@(fps)] : @"—";
  const bool cpuValid = (validFields & kCPUValid) && std::isfinite(cpu) && cpu >= 0.0;
  self.cpuValue.text = cpuValid ? [self.percentFormatter stringFromNumber:@(std::fmin(cpu, 100.0) / 100.0)] : @"—";
  [self updateAccessibility];
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
  self.ramValue.text = [self memoryText:point.footprint valid:point.footprintValid];
  self.neoswapValue.text = [self memoryText:point.donated valid:point.donatedValid];
  [self updateAccessibility];
}
@end
