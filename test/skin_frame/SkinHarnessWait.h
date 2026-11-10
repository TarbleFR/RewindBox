// Waiting for something a skin overlay delivers on a later turn of the main queue (its
// Menu and system buttons are sent with dispatch_async). A fixed 20 ms wait was too short
// on a loaded simulator: the delivery arrived after the window and was counted at the
// next point instead (0 then 2 where 1 was expected).
#pragma once
#import <Foundation/Foundation.h>

/// Spins the main run loop until `done()` is true, at most `limit` seconds, then 30 ms
/// more so that a second, unwanted delivery is seen by the caller's "once" assertion.
static void SkinHarnessWait(BOOL (^done)(void), NSTimeInterval limit) {
  NSDate* end = [NSDate dateWithTimeIntervalSinceNow:limit];
  while (!done() && end.timeIntervalSinceNow > 0) {
    [[NSRunLoop mainRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.005]];
  }
  [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.03]];
}
