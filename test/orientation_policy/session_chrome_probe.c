// Runs DOLSessionChromePlace (DOLSessionChromePolicy.h) on the arguments
// given by test/dolphin_session_chrome_test.py:
//   shown hasMenu x y width height  ->  "showMenu inScreen px py"
#include <stdio.h>
#include <stdlib.h>
#include "../../packages/dolphin_internal_bridge/ios/Classes/DOLSessionChromePolicy.h"

int main(int argc, char **argv) {
  if (argc != 7) return 2;
  DOLChromeRect screen = {atof(argv[3]), atof(argv[4]), atof(argv[5]), atof(argv[6])};
  DOLChromePlacement p = DOLSessionChromePlace(atoi(argv[1]) != 0, atoi(argv[2]) != 0, screen, 44.0, 8.0);
  printf("%d %d %.3f %.3f\n", p.showMenuButton ? 1 : 0, p.performanceInScreen ? 1 : 0, p.performanceX, p.performanceY);
  return 0;
}
