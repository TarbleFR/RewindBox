#!/usr/bin/env python3
"""Host test for RPCS3OverlayButtonLayout.h plus static wiring checks."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLASSES = ROOT / "packages/rpcs3_internal_bridge/ios/Classes"

CPP = r'''
#include "RPCS3OverlayButtonLayout.h"
#include <cstdio>
#include <cstdlib>
using namespace rpcs3_overlay;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); ++fails; } } while (0)
static bool inside(const Rect& r, const Rect& o) {
  return r.x >= o.x - 1e-9 && r.y >= o.y - 1e-9 && r.maxX() <= o.maxX() + 1e-9 && r.maxY() <= o.maxY() + 1e-9;
}
static Rect safeOf(const Rect& b, const Insets& i) {
  return {b.x + i.left, b.y + i.top, b.w - i.left - i.right, b.h - i.top - i.bottom};
}
static void common(const Rect& b, const Insets& i, const Layout& l, const std::vector<Rect>& occ) {
  Rect s = safeOf(b, i);
  CHECK(l.menu.w == 44 && l.menu.h == 44 && l.performanceButton.w == 44 && l.performanceButton.h == 44);
  CHECK(inside(l.menu, s) && inside(l.performanceButton, s) && inside(l.panel, s));
  CHECK(!intersects(l.menu, l.performanceButton));
  CHECK(!intersects(l.panel, l.performanceButton));
  for (const Rect& o : occ) CHECK(!intersects(l.menu, o) && !intersects(l.performanceButton, o));
  CHECK(l.panel.maxX() <= l.performanceButton.maxX() + 1e-9);
}
int main() {
  // Landscape, notch on the left, home indicator at the bottom.
  Rect b{0, 0, 874, 402}; Insets in1{0, 62, 21, 62}; Rect img = b;
  Layout l = compute(b, in1, img, {});
  CHECK(l.menu.x == 62 + kMargin && l.menu.y == kMargin);
  CHECK(l.performanceButton.maxX() == 874 - 62 - kMargin && l.performanceButton.y == kMargin);
  CHECK(l.panel.maxX() == l.performanceButton.maxX() && l.panel.y == l.performanceButton.maxY() + kGap);
  CHECK(l.panel.w == 320 && l.panel.h == 250);
  common(b, in1, l, {});
  // Other landscape orientation (notch on the right) and no insets.
  Insets in2{0, 21, 21, 62};
  l = compute(b, in2, img, {});
  CHECK(l.menu.x == 21 + kMargin && l.performanceButton.maxX() == 874 - 62 - kMargin);
  common(b, in2, l, {});
  Insets in0{};
  l = compute(b, in0, img, {});
  CHECK(l.menu.x == kMargin && l.performanceButton.maxX() == 874 - kMargin);
  common(b, in0, l, {});
  // Letterbox band: top band free of image, both buttons stay in the band.
  Rect lb{0, 80, 874, 242};
  l = compute(b, in1, lb, {});
  CHECK(!intersects(l.menu, lb) && !intersects(l.performanceButton, lb));
  common(b, in1, l, {});
  // Pillarbox: image 536 wide centred; side bands hold the buttons.
  Rect pb{169, 0, 536, 402};
  l = compute(b, in0, pb, {});
  CHECK(!intersects(l.menu, pb) && !intersects(l.performanceButton, pb));
  CHECK(l.menu.x == kMargin);
  // Image fills everything (no band): corners are used.
  l = compute(b, in0, b, {});
  CHECK(l.menu.x == kMargin && l.menu.y == kMargin);
  // L1 / R1 style controls in the corners force a non-overlapping fallback.
  std::vector<Rect> occ{{20, 8, 100, 40}, {754, 8, 100, 40}};
  l = compute(b, in0, img, occ);
  CHECK(l.menu.x >= 20 + 100);  // moved along the top edge
  CHECK(l.performanceButton.maxX() <= 754);
  CHECK(l.menu.y == kMargin && l.performanceButton.y == kMargin);
  common(b, in0, l, occ);
  // Controller connected (no occupied rects): corner again.
  l = compute(b, in0, img, {});
  CHECK(l.menu.x == kMargin);
  // Whole top row occupied: falls down the side edge, still no overlap.
  std::vector<Rect> row{{0, 0, 874, 70}};
  l = compute(b, in0, img, row);
  common(b, in0, l, row);
  // Small portrait-ish area: panel bounded by the safe area.
  Rect sb{0, 0, 300, 200}; Insets in3{10, 10, 10, 10};
  l = compute(sb, in3, sb, {});
  common(sb, in3, l, {});
  CHECK(l.panel.w <= 300 - 20 - 2 * kMargin + 1e-9);
  std::printf(fails ? "FAILED\n" : "OK\n");
  return fails ? 1 : 0;
}
'''


def main() -> int:
    plugin = (CLASSES / "Rpcs3InternalBridgePlugin.mm").read_text()
    assert "constant:70" not in plugin, "old +70 constraint still present"
    for needle in ("rpcs3_overlay::compute", "viewSafeAreaInsetsDidChange",
                   "[self layoutOverlayButtons];", "controlForIdentifier:identifier"):
        assert needle in plugin, needle
    vdl = plugin[plugin.index("- (void)viewDidLayoutSubviews"):]
    assert "layoutOverlayButtons" in vdl[:700], "layout not called from viewDidLayoutSubviews"
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / "t.cpp"
        exe = pathlib.Path(tmp) / "t"
        src.write_text(CPP)
        cxx = "clang++" if subprocess.call(["which", "clang++"], stdout=subprocess.DEVNULL) == 0 else "g++"
        subprocess.check_call([cxx, "-std=c++17", "-Wall", "-Werror", f"-I{CLASSES}", str(src), "-o", str(exe)])
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        print(r.stdout, end="")
        return r.returncode


if __name__ == "__main__":
    sys.exit(main())
