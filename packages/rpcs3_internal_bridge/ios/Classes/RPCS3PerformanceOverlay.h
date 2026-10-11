// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#include <neo_swap/NeoSwapHost.h>
#include <neo_swap/NeoSwapClientStats.h>

NS_ASSUME_NONNULL_BEGIN

/// Passive NeoStation overlay for RPCS3's lock-independent iOS performance API.
/// The owner samples only while this view is visible.
@interface RPCS3PerformanceOverlay : UIView
- (void)setLocaleIdentifier:(NSString*)localeIdentifier;
- (void)appendMetricsWithFPS:(double)fps
                         cpu:(double)cpu
                         gpu:(double)gpu
                  memoryUsed:(uint64_t)memoryUsed
                 memoryTotal:(uint64_t)memoryTotal
                 validFields:(uint32_t)validFields
                   timestamp:(double)timestampMs;
- (void)reset;
// Independent measures: the app's physical footprint and the backing currently
// donated to RPCS3 (published guest objects plus active host relay/donor loans).
// No sum with footprint, prepared capacity, idle shelves, disk bytes or aliases.
- (void)appendNeoSwapWithClient:(const NeoSwapClientStats* _Nullable)client
                          host:(const NeoSwapHostStats* _Nullable)host
                relayGuestPublishedBytes:(uint64_t)relayGuestPublishedBytes
                 relayGuestMeasured:(BOOL)relayGuestMeasured
         processFootprintBytes:(uint64_t)processFootprintBytes
                     timestamp:(double)timestampMs;
@end

NS_ASSUME_NONNULL_END
