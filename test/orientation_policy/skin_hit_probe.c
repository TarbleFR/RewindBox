// Runs DOLSkinHitIndex (DOLSkinHitTest.h) for test/pocket_skin_input_chain_test.py.
// stdin: N, then N items "x y w h hx hy hw hh active aw ah" each followed by aw*ah
// alpha bytes as integers (aw = ah = 0: no alpha map), then M, then M points "x y".
// stdout: one item index per point (-1: none).
#include <stdio.h>
#include <stdlib.h>
#include "../../packages/dolphin_internal_bridge/ios/Classes/DOLSkinHitTest.h"

int main(void) {
  long n;
  if (scanf("%ld", &n) != 1 || n < 0 || n > 256) return 2;
  DOLSkinHitItem* items = calloc((size_t)(n ? n : 1), sizeof(DOLSkinHitItem));
  for (long i = 0; i < n; i++) {
    DOLSkinHitItem* it = &items[i];
    int active;
    if (scanf("%lf %lf %lf %lf %lf %lf %lf %lf %d %ld %ld", &it->x, &it->y, &it->width, &it->height, &it->hx, &it->hy,
              &it->hwidth, &it->hheight, &active, &it->alphaWidth, &it->alphaHeight) != 11)
      return 2;
    it->active = active;
    const long size = it->alphaWidth * it->alphaHeight;
    if (size > 0) {
      uint8_t* alpha = malloc((size_t)size);
      for (long k = 0; k < size; k++) {
        int v;
        if (scanf("%d", &v) != 1) return 2;
        alpha[k] = (uint8_t)v;
      }
      it->alpha = alpha;
    }
  }
  long m;
  if (scanf("%ld", &m) != 1) return 2;
  for (long j = 0; j < m; j++) {
    double x, y;
    if (scanf("%lf %lf", &x, &y) != 2) return 2;
    printf("%ld\n", DOLSkinHitIndex(items, n, x, y));
  }
  return 0;
}
