// SPDX-License-Identifier: GPL-3.0-or-later
// Pure placement of the RPCS3 in-game Menu / Performances buttons and the
// performance panel. Plain C++ (no UIKit) so a host test can compile it.
#pragma once

#include <algorithm>
#include <vector>

namespace rpcs3_overlay {

struct Rect {
  double x = 0, y = 0, w = 0, h = 0;
  double maxX() const { return x + w; }
  double maxY() const { return y + h; }
  bool empty() const { return w <= 0 || h <= 0; }
};

struct Insets {
  double top = 0, left = 0, bottom = 0, right = 0;
};

struct Layout {
  Rect menu;
  Rect performanceButton;
  Rect panel;
};

constexpr double kTarget = 44.0;      // hit area, also when the glyph is smaller
constexpr double kMargin = 10.0;      // inside the safe area
constexpr double kGap = 8.0;          // between button and panel
constexpr double kPanelWidth = 320.0;
constexpr double kPanelHeight = 250.0;
constexpr double kPanelMin = 120.0;
constexpr double kClearance = 4.0;    // kept free around occupied controls

inline bool intersects(const Rect& a, const Rect& b, double pad = 0) {
  if (a.empty() || b.empty()) return false;
  return a.x < b.maxX() + pad && b.x < a.maxX() + pad && a.y < b.maxY() + pad && b.y < a.maxY() + pad;
}

namespace detail {
inline bool blocked(const Rect& r, const std::vector<Rect>& occupied, const Rect* avoid) {
  for (const Rect& o : occupied)
    if (intersects(r, o, kClearance)) return true;
  return avoid && intersects(r, *avoid, kGap);
}

// Candidates, nearest first: the corner, then along the top edge toward the
// centre, then down the side edge. `fromLeft` picks the corner.
inline Rect place(const Rect& safe, const Rect& image, const std::vector<Rect>& occupied,
                  bool fromLeft, const Rect* avoid) {
  const double minX = safe.x + kMargin, maxX = safe.maxX() - kMargin - kTarget;
  const double minY = safe.y + kMargin, maxY = safe.maxY() - kMargin - kTarget;
  std::vector<Rect> cands;
  const double step = 4.0;
  for (double d = 0; minX + d <= maxX; d += step)
    cands.push_back({fromLeft ? minX + d : maxX - d, minY, kTarget, kTarget});
  for (double d = step; minY + d <= maxY; d += step)
    cands.push_back({fromLeft ? minX : maxX, minY + d, kTarget, kTarget});
  Rect corner = cands.empty() ? Rect{minX, minY, kTarget, kTarget} : cands.front();
  // Pass 1: free band outside the emulated image; pass 2: any free spot.
  for (int pass = 0; pass < 2; ++pass)
    for (const Rect& c : cands) {
      if (blocked(c, occupied, avoid)) continue;
      if (pass == 0 && intersects(c, image)) continue;
      return c;
    }
  return corner;
}
}  // namespace detail

inline Layout compute(const Rect& bounds, const Insets& insets, const Rect& image,
                      const std::vector<Rect>& occupied) {
  Rect safe{bounds.x + insets.left, bounds.y + insets.top,
            std::max(0.0, bounds.w - insets.left - insets.right),
            std::max(0.0, bounds.h - insets.top - insets.bottom)};
  Layout out;
  out.menu = detail::place(safe, image, occupied, true, nullptr);
  out.performanceButton = detail::place(safe, image, occupied, false, &out.menu);

  // Panel: right-aligned under the Performances button, bounded by the safe area.
  const Rect& pb = out.performanceButton;
  double top = pb.maxY() + kGap;
  double w = std::min(kPanelWidth, std::max(0.0, safe.w - 2 * kMargin));
  double right = std::min(pb.maxX(), safe.maxX() - kMargin);
  double x = std::max(safe.x + kMargin, right - w);
  w = std::min(w, right - x);
  double h = std::min(kPanelHeight, safe.maxY() - kMargin - top);
  if (h < kPanelMin) {  // not enough room below: open to the left of the button
    h = std::min(kPanelHeight, std::max(0.0, safe.h - 2 * kMargin));
    top = std::max(safe.y + kMargin, std::min(pb.y, safe.maxY() - kMargin - h));
    right = std::max(safe.x + kMargin, pb.x - kGap);
    w = std::min(w, std::max(0.0, right - (safe.x + kMargin)));
    x = right - w;
  }
  out.panel = {x, top, w, std::max(0.0, h)};
  return out;
}

}  // namespace rpcs3_overlay
