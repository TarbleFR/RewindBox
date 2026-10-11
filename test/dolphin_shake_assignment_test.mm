// Executes the production DolphinShakeAssignment.mm against a controlled
// donor menu C ABI (JSON snapshot and binding requests), on a serial queue
// standing in for the Dolphin runtime queue.
#import <Foundation/Foundation.h>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include "../packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinShakeAssignment.h"

static NSMutableDictionary* s_snapshot;
static NSMutableArray<NSDictionary*>* s_requests;
static NSMutableArray<NSNumber*>* s_snapshotSlots;
static int s_failApply;
static const char* s_badJSON;
static int s_runtimeMarker;

extern "C" char* neostation_dolphin_menu_snapshot(int32_t wii, int32_t slot) {
  assert(dispatch_get_specific(&s_runtimeMarker) == &s_runtimeMarker);
  assert(wii == 1);
  [s_snapshotSlots addObject:@(slot)];
  if (s_badJSON) return strdup(s_badJSON);
  if (!s_snapshot) return nullptr;
  NSData* data = [NSJSONSerialization dataWithJSONObject:s_snapshot options:0 error:nil];
  return strdup([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String);
}

extern "C" int32_t neostation_dolphin_menu_apply(const char* text) {
  assert(dispatch_get_specific(&s_runtimeMarker) == &s_runtimeMarker);
  NSDictionary* request = [NSJSONSerialization JSONObjectWithData:[[NSString stringWithUTF8String:text]
      dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
  // Only the existing per-control binding request ever reaches the donor.
  assert([request[@"kind"] isEqual:@"binding"] && [request[@"wii"] isEqual:@YES]);
  assert(([@[@"Shake/X", @"Shake/Y", @"Shake/Z"] containsObject:request[@"id"]]));
  assert([request[@"expression"] isKindOfClass:NSString.class]);
  assert([request[@"slot"] isEqual:s_snapshotSlots.lastObject]);
  [s_requests addObject:request];
  if (s_failApply > 0 && --s_failApply == 0) return 0;
  for (NSMutableDictionary* control in s_snapshot[@"controls"])
    if ([control[@"id"] isEqual:request[@"id"]]) control[@"expression"] = request[@"expression"];
  return 1;
}

static void Profile(NSArray<NSString*>* shake) {
  s_requests = [NSMutableArray new];
  s_snapshotSlots = [NSMutableArray new];
  s_failApply = 0;
  s_badJSON = nullptr;
  NSMutableArray* controls = [NSMutableArray new];
  [controls addObject:[@{@"id": @"Buttons/A", @"expression": @"`Button 100`"} mutableCopy]];
  NSArray* names = @[@"Shake/X", @"Shake/Y", @"Shake/Z"];
  for (NSUInteger axis = 0; axis < 3; ++axis)
    [controls addObject:[@{@"id": names[axis], @"expression": shake[axis]} mutableCopy]];
  [controls addObject:[@{@"id": @"Extension/Nunchuk/Shake/X", @"expression": @"`Button 220`"} mutableCopy]];
  s_snapshot = [@{@"device": @"iOS/4/Touchscreen", @"controls": controls} mutableCopy];
}

static NSString* Expression(NSString* identifier) {
  for (NSDictionary* control in s_snapshot[@"controls"])
    if ([control[@"id"] isEqual:identifier]) return control[@"expression"];
  return nil;
}

static NSString* Touch(int axis) {
  return [NSString stringWithFormat:@"`iOS/4/Touchscreen:Button %d`", 132 + axis];
}

static NSArray<NSString*>* TouchDefaults(void) {
  return @[@"`Button 132`", @"`Button 133`", @"`Button 134`"];
}

static dispatch_queue_t s_runtime;

// Runs on the stand-in runtime queue like the bridge's applySettings block.
// A dispatch_sync onto that queue from inside would deadlock: bounded wait.
static bool Apply(id request) {
  __block bool result = false;
  dispatch_semaphore_t done = dispatch_semaphore_create(0);
  dispatch_async(s_runtime, ^{
    result = DOLApplyShakeAssignmentRequestOnRuntime(request);
    dispatch_semaphore_signal(done);
  });
  assert(dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC)) == 0);
  return result;
}

static NSDictionary* Request(id slot, id expression) {
  NSMutableDictionary* request = [@{@"kind": @"shakeBinding", @"wii": @YES} mutableCopy];
  if (slot) request[@"slot"] = slot;
  if (expression) request[@"expression"] = expression;
  return request;
}

int main() { @autoreleasepool {
  s_runtime = dispatch_queue_create("test.dolphin.runtime", DISPATCH_QUEUE_SERIAL);
  dispatch_queue_set_specific(s_runtime, &s_runtimeMarker, &s_runtimeMarker, nullptr);
  NSString* pad = @"`MFi/0/Gamepad:Button A`";

  // Player 1, Touch profile: one gamepad button for the three axes, with the
  // touch/phone branch kept. Nothing else in the profile changes.
  Profile(TouchDefaults());
  assert(DOLIsShakeAssignmentRequest(Request(@0, pad)));
  assert(Apply(Request(@0, pad)));
  assert(s_requests.count == 3 && [s_snapshotSlots isEqual:@[@0]]);
  for (int axis = 0; axis < 3; ++axis)
    assert([Expression(@[@"Shake/X", @"Shake/Y", @"Shake/Z"][axis]) isEqual:
        ([NSString stringWithFormat:@"(%@) | %@", pad, Touch(axis)])]);
  assert([Expression(@"Buttons/A") isEqual:@"`Button 100`"]);
  assert([Expression(@"Extension/Nunchuk/Shake/X") isEqual:@"`Button 220`"]);
  // Same choice again: no write at all.
  assert(Apply(Request(@0, pad)) && s_requests.count == 3);

  // Clear keeps only the touch/phone branch for player 1.
  assert(Apply(Request(@0, @"")));
  for (int axis = 0; axis < 3; ++axis)
    assert([Expression(@[@"Shake/X", @"Shake/Y", @"Shake/Z"][axis]) isEqual:Touch(axis)]);

  // Other players get exactly the chosen input, read from their own profile.
  Profile(@[@"", @"", @""]);
  assert(Apply(Request(@2, @"`MFi/1/Gamepad:R Shoulder`")));
  assert([s_snapshotSlots isEqual:@[@2]] && s_requests.count == 3);
  for (NSString* name in @[@"Shake/X", @"Shake/Y", @"Shake/Z"])
    assert([Expression(name) isEqual:@"`MFi/1/Gamepad:R Shoulder`"]);
  assert(Apply(Request(@3, @"")));

  // A failed write restores every axis already changed, in the same profile.
  for (int failing = 1; failing <= 3; ++failing) {
    NSArray* before = @[@"(`R Shoulder`) | `iOS/4/Touchscreen:Button 132`",
                        @"(`R Shoulder`) | `iOS/4/Touchscreen:Button 133`",
                        @"(`R Shoulder`) | `iOS/4/Touchscreen:Button 134`"];
    Profile(before);
    s_failApply = failing;
    assert(!Apply(Request(@0, pad)));
    for (int axis = 0; axis < 3; ++axis)
      assert([Expression(@[@"Shake/X", @"Shake/Y", @"Shake/Z"][axis]) isEqual:before[axis]]);
    // failing writes + one restore per axis written before it.
    assert(s_requests.count == (NSUInteger)(failing + failing - 1));
    for (int undo = 0; undo < failing - 1; ++undo) {
      NSDictionary* restore = s_requests[failing + undo];
      assert([restore[@"expression"] isEqual:before[failing - 2 - undo]]);
    }
    assert([Expression(@"Buttons/A") isEqual:@"`Button 100`"]);
  }

  // GameCube, bad players and non-string inputs are refused before any read.
  Profile(TouchDefaults());
  NSMutableDictionary* gameCube = [Request(@0, pad) mutableCopy];
  gameCube[@"wii"] = @NO;
  assert(!Apply(gameCube));
  [gameCube removeObjectForKey:@"wii"];
  assert(!Apply(gameCube));
  for (id slot in @[@(-1), @4, @1.5, @"0", NSNull.null])
    assert(!Apply(Request(slot, pad)));
  assert(!Apply(Request(nil, pad)));
  for (id expression in @[@1, NSNull.null, @[pad]])
    assert(!Apply(Request(@0, expression)));
  assert(!Apply(Request(@0, nil)));
  NSMutableDictionary* other = [Request(@0, pad) mutableCopy];
  other[@"kind"] = @"binding";
  assert(!DOLIsShakeAssignmentRequest(other) && !Apply(other));
  assert(!DOLIsShakeAssignmentRequest(nil) && !Apply(nil));
  assert(!DOLIsShakeAssignmentRequest(@[@"shakeBinding"]) && !Apply(@[@"shakeBinding"]));
  assert(s_snapshotSlots.count == 0 && s_requests.count == 0);

  // Invalid donor snapshots: nothing is written.
  s_snapshot = nil;
  assert(!Apply(Request(@0, pad)));
  Profile(TouchDefaults());
  s_badJSON = "broken";
  assert(!Apply(Request(@0, pad)));
  Profile(TouchDefaults());
  s_snapshot[@"controls"] = NSNull.null;
  assert(!Apply(Request(@0, pad)));
  Profile(TouchDefaults());
  s_snapshot[@"controls"] = @[NSNull.null];
  assert(!Apply(Request(@0, pad)));
  Profile(TouchDefaults());
  [s_snapshot[@"controls"] removeObjectAtIndex:3];  // Shake/Z missing
  assert(!Apply(Request(@0, pad)));
  Profile(TouchDefaults());
  s_snapshot[@"controls"][2][@"expression"] = NSNull.null;  // Shake/Y not a string
  assert(!Apply(Request(@0, pad)));
  assert(s_requests.count == 0);
  std::cout << "PASS: production Shake X/Y/Z assignment on the runtime queue, three binding requests, rollback, Wii-only refusals\n";
} }
