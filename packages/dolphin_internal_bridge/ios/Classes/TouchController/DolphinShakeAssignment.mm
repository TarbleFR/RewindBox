// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <string>
#include "DolphinShakeAssignment.h"

extern "C" char* neostation_dolphin_menu_snapshot(int32_t, int32_t);
extern "C" int32_t neostation_dolphin_menu_apply(const char*);

static bool DOLShakeAssignmentFailed(const char* reason) {
  NSLog(@"[Dolphin Shake] Controller shake assignment refused: %s", reason);
  return false;
}

// One existing donor binding request; the donor saves the profile itself.
static bool DOLApplyShakeAxisBinding(int32_t slot, int axis, const std::string& expression) {
  NSString* value = [NSString stringWithUTF8String:expression.c_str()];
  if (!value) return false;
  NSDictionary* request = @{@"kind": @"binding", @"wii": @YES, @"slot": @(slot),
    @"id": @(DolphinShakeAssignment::ControlId(axis)), @"expression": value};
  NSData* data = [NSJSONSerialization dataWithJSONObject:request options:0 error:nil];
  if (!data) return false;
  NSString* json = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
  return json && neostation_dolphin_menu_apply(json.UTF8String) != 0;
}

bool DOLApplyShakeAssignmentOnRuntime(int32_t slot, NSString* input) {
  @autoreleasepool {
    if (!DolphinShakeAssignment::ValidSlot(slot)) return DOLShakeAssignmentFailed("player");
    if (![input isKindOfClass:NSString.class] || !input.UTF8String) return DOLShakeAssignmentFailed("input");
    const std::string chosen = input.UTF8String;
    // Executes on the emulator runtime queue, like every other menu request.
    // The donor serializes with Dolphin's host/CPU/input locks; no UIKit here.
    char* text = neostation_dolphin_menu_snapshot(1, slot);
    if (!text) return DOLShakeAssignmentFailed("snapshot");
    NSData* data = [NSData dataWithBytes:text length:std::strlen(text)];
    std::free(text);
    id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![decoded isKindOfClass:NSDictionary.class]) return DOLShakeAssignmentFailed("snapshot");
    id controls = ((NSDictionary*)decoded)[@"controls"];
    if (![controls isKindOfClass:NSArray.class]) return DOLShakeAssignmentFailed("controls");
    std::string previous[3];
    for (int axis = 0; axis < 3; ++axis) {
      NSString* identifier = @(DolphinShakeAssignment::ControlId(axis));
      NSString* found = nil;
      for (id control in (NSArray*)controls) {
        if (![control isKindOfClass:NSDictionary.class]) return DOLShakeAssignmentFailed("controls");
        if ([((NSDictionary*)control)[@"id"] isEqual:identifier]) {
          id expression = ((NSDictionary*)control)[@"expression"];
          if ([expression isKindOfClass:NSString.class]) found = expression;
          break;
        }
      }
      if (!found || !found.UTF8String) return DOLShakeAssignmentFailed("shake control");
      previous[axis] = found.UTF8String;
    }
    bool changed[3] = {false, false, false};
    for (int axis = 0; axis < 3; ++axis) {
      const std::string wanted = DolphinShakeAssignment::Compose(chosen, slot, axis);
      if (wanted == previous[axis]) continue;
      if (!DOLApplyShakeAxisBinding(slot, axis, wanted)) {
        // Never leave the three axes half assigned: restore what was there.
        for (int undo = axis - 1; undo >= 0; --undo)
          if (changed[undo] && !DOLApplyShakeAxisBinding(slot, undo, previous[undo]))
            NSLog(@"[Dolphin Shake] Could not restore %s.", DolphinShakeAssignment::ControlId(undo));
        return DOLShakeAssignmentFailed("binding");
      }
      changed[axis] = true;
    }
    return true;
  }
}

bool DOLApplyShakeAssignmentRequestOnRuntime(id request) {
  if (!DOLIsShakeAssignmentRequest(request)) return DOLShakeAssignmentFailed("kind");
  NSDictionary* values = request;
  // GameCube controllers have no Wii Remote shake.
  id wii = values[@"wii"];
  if (![wii isKindOfClass:NSNumber.class] || ![wii boolValue]) return DOLShakeAssignmentFailed("not a Wii Remote");
  id slot = values[@"slot"];
  if (![slot isKindOfClass:NSNumber.class]) return DOLShakeAssignmentFailed("player");
  const double number = [slot doubleValue];
  if (!std::isfinite(number) || number != std::floor(number) || number < 0 || number > 3)
    return DOLShakeAssignmentFailed("player");
  id expression = values[@"expression"];
  if (![expression isKindOfClass:NSString.class]) return DOLShakeAssignmentFailed("input");
  return DOLApplyShakeAssignmentOnRuntime((int32_t)number, expression);
}
