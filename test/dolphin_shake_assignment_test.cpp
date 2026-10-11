// Portable execution of the header-only Shake assignment policy.
#include <cassert>
#include <iostream>
#include <string>
#include "../packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinShakeAssignment.h"
#include "../packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinPhoneShakeBinding.h"

using namespace DolphinShakeAssignment;

static std::string Touch(int axis) {
  return "`iOS/4/Touchscreen:Button " + std::to_string(132 + axis) + "`";
}

int main() {
  assert(std::string(ControlId(0)) == "Shake/X");
  assert(std::string(ControlId(1)) == "Shake/Y");
  assert(std::string(ControlId(2)) == "Shake/Z");
  for (int slot = -1; slot <= 4; ++slot) assert(ValidSlot(slot) == (slot >= 0 && slot <= 3));
  const char* inputs[] = {
    "`MFi/0/Gamepad:Button A`", "`R Shoulder`", "`L Trigger` & !`Button A`",
    "if(`Button A`, 1, 0)", "(`Button X`) | (`Button Y`)", "`MFi/0/Gamepad:Button A` /* (note) */",
    "'quoted ) | text'"};
  for (int axis = 0; axis < 3; ++axis) {
    assert(TouchInput(axis) == Touch(axis));
    // Player 1 keeps the touch and phone branch next to the chosen input.
    assert(Compose("", 0, axis) == Touch(axis));
    assert(Strip(Compose("", 0, axis), 0, axis).empty());
    for (const char* raw : inputs) {
      const std::string input = raw;
      const std::string composed = Compose(input, 0, axis);
      assert(composed == "(" + input + ") | " + Touch(axis));
      // The same transform as the phone routing: no duplicate branch.
      assert(DolphinPhoneShakeBinding::Augment(composed, 132 + axis) == composed);
      assert(Compose(composed, 0, axis) == composed);
      assert(Strip(composed, 0, axis) == input);
      // Other players get exactly the chosen input.
      for (int slot = 1; slot <= 3; ++slot) {
        assert(Compose(input, slot, axis) == input);
        assert(Strip(input, slot, axis) == input);
      }
    }
    // The Touch profile default and the phone-routed defaults show as no
    // controller input; a gamepad default shows its own input.
    const std::string bare = "`Button " + std::to_string(132 + axis) + "`";
    assert(Strip(bare, 0, axis).empty());
    assert(Strip(DolphinPhoneShakeBinding::Augment(bare, 132 + axis), 0, axis).empty());
    assert(Strip(DolphinPhoneShakeBinding::Augment("`R Shoulder`", 132 + axis), 0, axis) == "`R Shoulder`");
    assert(Strip("  `R Shoulder`  ", 0, axis) == "`R Shoulder`");
    // Another axis's branch is not this axis's branch.
    const std::string other = Touch((axis + 1) % 3);
    assert(Strip(other, 0, axis) == other);
    // A suffix that does not close the leading parenthesis is not a branch.
    const std::string unbalanced = "(`A`) | (`B`) | " + Touch(axis);
    assert(Strip(unbalanced, 0, axis) == unbalanced);
    assert(Strip("(`A`) | `B`", 0, axis) == "(`A`) | `B`");
    // Unterminated quotes or comments are left untouched.
    const std::string broken = "(`A) | " + Touch(axis);
    assert(Strip(broken, 0, axis) == broken);
  }
  // The composite row: one shared input, nothing, or different axes.
  Summary common = Summarize(Compose("`R Shoulder`", 0, 0), Compose("`R Shoulder`", 0, 1),
                             Compose("`R Shoulder`", 0, 2), 0);
  assert(!common.mixed && common.input == "`R Shoulder`");
  Summary touch = Summarize("`Button 132`", "`Button 133`", "`Button 134`", 0);
  assert(!touch.mixed && touch.input.empty());
  Summary routed = Summarize(DolphinPhoneShakeBinding::Augment("`Button 132`", 132),
                             DolphinPhoneShakeBinding::Augment("`Button 133`", 133),
                             DolphinPhoneShakeBinding::Augment("`Button 134`", 134), 0);
  assert(!routed.mixed && routed.input.empty());
  Summary mixed = Summarize(Compose("`R Shoulder`", 0, 0), Compose("`L Shoulder`", 0, 1),
                            Compose("`R Shoulder`", 0, 2), 0);
  assert(mixed.mixed && mixed.input.empty());
  Summary second = Summarize("`Button A`", "`Button A`", "`Button A`", 1);
  assert(!second.mixed && second.input == "`Button A`");
  // On player 2 the touchscreen buttons are ordinary inputs, not the branch.
  Summary secondTouch = Summarize("`Button 132`", "`Button 133`", "`Button 134`", 1);
  assert(secondTouch.mixed);
  Summary empty = Summarize("", " ", "", 2);
  assert(!empty.mixed && empty.input.empty());
  std::cout << "PASS: Shake X/Y/Z composition keeps player 1 touch/phone branch, exact strip, summaries\n";
}
