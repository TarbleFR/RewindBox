// SPDX-License-Identifier: GPL-3.0-or-later
// Build 484 test support, linked into the stand-in dolphin_internal_bridge
// framework of test/touch_layout_ui_test.py next to the real DolphiniOS touch
// controls. It replaces the three Dolphin Core entry points those controls
// call: every touch input is recorded (port, button or axis, value) instead
// of reaching Dolphin's ButtonManager, and the menu entry points used by the
// Shake routing report that no session is running.
#import <Foundation/Foundation.h>
#include <cstdint>

static NSObject* TLLock(void) {
  static NSObject* lock;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ lock = [NSObject new]; });
  return lock;
}

static NSMutableDictionary<NSString*, NSNumber*>* gTLInputs;
static NSUInteger gTLEvents;

extern "C" __attribute__((visibility("default"))) void neostation_dolphin_touch_event(int32_t port, int32_t control,
                                                                                       float value, int32_t axis) {
  @synchronized(TLLock()) {
    if (!gTLInputs) gTLInputs = [NSMutableDictionary dictionary];
    gTLInputs[[NSString stringWithFormat:@"%s%d.%d", axis ? "a" : "b", port, control]] = @(value);
    gTLEvents++;
  }
}

extern "C" __attribute__((visibility("default"))) char* neostation_dolphin_menu_snapshot(int32_t, int32_t) {
  return nullptr;
}

extern "C" __attribute__((visibility("default"))) int32_t neostation_dolphin_menu_apply(const char*) {
  return 0;
}

/// Last value of every input the controls sent ("b<port>.<button>", "a<port>.<axis>").
extern "C" __attribute__((visibility("default"))) NSDictionary<NSString*, NSNumber*>* TLDolphinInputs(void) {
  @synchronized(TLLock()) {
    return [gTLInputs copy] ?: @{};
  }
}

extern "C" __attribute__((visibility("default"))) NSUInteger TLDolphinEventCount(void) {
  @synchronized(TLLock()) {
    return gTLEvents;
  }
}

extern "C" __attribute__((visibility("default"))) void TLDolphinResetInputs(void) {
  @synchronized(TLLock()) {
    [gTLInputs removeAllObjects];
    gTLEvents = 0;
  }
}
