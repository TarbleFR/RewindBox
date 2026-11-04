#import "SkinOverlayRecorder.h"
#import "TouchController/TCManagerInterface.h"

static NSMutableArray<NSString*>* gEvents;
static NSMutableDictionary<NSNumber*, NSNumber*>* gAxes;
static NSMutableSet<NSNumber*>* gHeld;

void SkinRecorderReset(void) {
  gEvents = [NSMutableArray array];
  gAxes = [NSMutableDictionary dictionary];
  gHeld = [NSMutableSet set];
}
NSArray<NSString*>* SkinRecorderEvents(void) { return [gEvents copy] ?: @[]; }
NSDictionary<NSNumber*, NSNumber*>* SkinRecorderAxes(void) { return [gAxes copy] ?: @{}; }
NSSet<NSNumber*>* SkinRecorderHeldButtons(void) { return [gHeld copy] ?: [NSSet set]; }

@implementation TCManagerInterface
+ (void)setButtonStateFor:(NSInteger)button controller:(NSInteger)controllerId state:(BOOL)state {
  if (gEvents == nil) SkinRecorderReset();
  [gEvents addObject:[NSString stringWithFormat:@"b%ld%@", (long)button, state ? @"+" : @"-"]];
  if (state) [gHeld addObject:@(button)]; else [gHeld removeObject:@(button)];
}
+ (void)setAxisValueFor:(NSInteger)axis controller:(NSInteger)controllerId value:(float)value {
  if (gEvents == nil) SkinRecorderReset();
  [gEvents addObject:[NSString stringWithFormat:@"a%ld=%.3f", (long)axis, value]];
  gAxes[@(axis)] = @(value);
}
+ (BOOL)preparePhoneShakeRouting { return NO; }
+ (NSInteger)phoneShakeRoutingStatus { return 0; }
+ (void)reportPhoneShakeSensorUnavailable {}
@end
