// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdint.h>
#include <string>
#include "DolphinPhoneShakeBinding.h"

// One controller button for the three Wii Remote shake axes (Shake/X, Y, Z),
// written through the donor's existing per-control binding API. Header-only
// policy: the in-game menu and the portable test use it without linking.
namespace DolphinShakeAssignment {
inline bool ValidSlot(int slot) { return slot >= 0 && slot <= 3; }
inline bool ValidAxis(int axis) { return axis >= 0 && axis <= 2; }
inline const char* ControlId(int axis) {
  return axis == 0 ? "Shake/X" : axis == 1 ? "Shake/Y" : "Shake/Z";
}
// Touchscreen buttons 132-134 of the first Wii Remote (port 4): the touch
// Shake button and the phone gesture both press them.
inline int TouchButton(int axis) { return 132 + axis; }
inline std::string TouchInput(int axis) {
  return "`iOS/4/Touchscreen:Button " + std::to_string(TouchButton(axis)) + "`";
}

// Player 1 keeps the touch and phone branch next to the chosen input; the
// other players get exactly the chosen input. An empty input clears the
// controller part only.
inline std::string Compose(const std::string& input, int slot, int axis) {
  if (slot != 0 || !ValidAxis(axis)) return input;
  return DolphinPhoneShakeBinding::Augment(input, TouchButton(axis));
}

namespace Detail {
inline std::string Trim(const std::string& text) {
  const char* blank = " \t\r\n";
  const size_t first = text.find_first_not_of(blank);
  if (first == std::string::npos) return std::string();
  const size_t last = text.find_last_not_of(blank);
  return text.substr(first, last - first + 1);
}

// True when the '(' at index 0 is closed exactly at index `close`. Quoted
// input names and block comments are skipped like the pinned parser does.
inline bool Encloses(const std::string& text, size_t close) {
  if (text.empty() || text[0] != '(') return false;
  int depth = 0;
  for (size_t offset = 0; offset < text.size();) {
    if (text.compare(offset, 2, "/*") == 0) {
      const size_t end = text.find("*/", offset + 2);
      if (end == std::string::npos) return false;
      offset = end + 2;
      continue;
    }
    const char current = text[offset];
    if (current == '`' || current == '\'') {
      const size_t end = text.find(current, offset + 1);
      if (end == std::string::npos) return false;
      offset = end + 1;
      continue;
    }
    if (current == '(') {
      ++depth;
    } else if (current == ')') {
      --depth;
      if (depth == 0) return offset == close;
      if (depth < 0) return false;
    }
    ++offset;
  }
  return false;
}
}  // namespace Detail

// The controller part of an axis binding, for display: removes the touch
// and phone branch added by Compose or by the phone routing, and the Touch
// profile's own default (`Button 132`..`Button 134` on the touchscreen).
inline std::string Strip(const std::string& expression, int slot, int axis) {
  std::string current = Detail::Trim(expression);
  if (slot != 0 || !ValidAxis(axis)) return current;
  const std::string touch = TouchInput(axis);
  const std::string bare = "`Button " + std::to_string(TouchButton(axis)) + "`";
  const std::string suffix = ") | " + touch;
  for (int depth = 0; depth < 8; ++depth) {
    if (current == touch || current == bare) return std::string();
    if (current.size() > suffix.size() + 1 &&
        current.compare(current.size() - suffix.size(), suffix.size(), suffix) == 0 &&
        Detail::Encloses(current, current.size() - suffix.size())) {
      current = Detail::Trim(current.substr(1, current.size() - suffix.size() - 1));
      continue;
    }
    break;
  }
  return current;
}

// What the composite row shows: the shared controller input of the three
// axes ("" when none), or `mixed` when the axes differ.
struct Summary {
  bool mixed;
  std::string input;
};
inline Summary Summarize(const std::string& x, const std::string& y, const std::string& z, int slot) {
  const std::string first = Strip(x, slot, 0);
  if (Strip(y, slot, 1) != first || Strip(z, slot, 2) != first) return Summary{true, std::string()};
  return Summary{false, first};
}
}  // namespace DolphinShakeAssignment

#ifdef __OBJC__
#import <Foundation/Foundation.h>
// Request sent by the in-game Controls menu: {kind, wii, slot, expression}.
static inline NSString* DOLShakeAssignmentKind(void) { return @"shakeBinding"; }
// Placeholder control id of the composite row inside the menu only; it never
// reaches the donor API.
static inline NSString* DOLShakeAssignmentControlId(void) { return @"NeoStation/ShakeXYZ"; }
static inline bool DOLIsShakeAssignmentRequest(id request) {
  return [request isKindOfClass:NSDictionary.class] &&
      [((NSDictionary*)request)[@"kind"] isEqual:DOLShakeAssignmentKind()];
}
// Run these on the Dolphin runtime queue only. They call the donor C ABI
// inline and never dispatch_sync onto that queue. The first validates the
// request (Wii only, slot 0-3, string expression); both take one snapshot,
// write Shake/X, Y and Z, and restore the previous bindings if any write fails.
bool DOLApplyShakeAssignmentRequestOnRuntime(id request);
bool DOLApplyShakeAssignmentOnRuntime(int32_t slot, NSString* input);
#endif
