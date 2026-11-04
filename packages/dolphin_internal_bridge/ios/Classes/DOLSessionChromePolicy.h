// Where the session's own floating buttons go over a controller skin. Plain C
// so the decision is tested without UIKit (test/orientation_policy).
//
// The session draws two system buttons of its own above the game: the menu
// (hamburger) and the performance toggle, at the safe area's top leading
// corner. A skin draws its controls there too (L, C, Z...), so they used to
// cover them. They stay separate from the skin's art (never painted into an
// asset) and move out of its controls:
// - a visible skin with its own Menu control: the floating menu is hidden (the
//   skin's Menu opens the same session menu);
// - the performance toggle, the only one in the session, goes inside the top
//   leading corner of the skin's game screen, where no control can be;
// - no visible skin, or a skin without Menu: both buttons stay where they were.
#pragma once
#include <stdbool.h>

typedef struct {
  double x, y, width, height;
} DOLChromeRect;

typedef struct {
  bool showMenuButton;
  bool performanceInScreen;
  double performanceX, performanceY;  // view points, when performanceInScreen
} DOLChromePlacement;

/// `screen`: the skin's game screen in the session view; `button`: side of a
/// floating button; `margin`: its distance from the screen's edges.
static inline DOLChromePlacement DOLSessionChromePlace(bool skinShown, bool skinHasMenu, DOLChromeRect screen,
                                                       double button, double margin) {
  DOLChromePlacement placement = {true, false, 0, 0};
  if (!skinShown) return placement;
  placement.showMenuButton = !skinHasMenu;
  if (screen.width >= button + 2 * margin && screen.height >= button + 2 * margin) {
    placement.performanceInScreen = true;
    placement.performanceX = screen.x + margin;
    placement.performanceY = screen.y + margin;
  }
  return placement;
}
