// Motion profile derived from Mau Ali, Interactive iOS 26 Inspired Tab Menu.
// Lottie Simple License FL 9.13.21, assets/legal/Lottie-Simple-License.txt.
// Generated from assets/data/mau-ali-tab-menu.lottie; see its SHA/profile.
import 'package:flutter/animation.dart';

abstract final class MauAliTabMotion {
  static const duration = Duration(milliseconds: 330);
  static const position = Cubic(0.358, 0.965, 0.56, 1);
  static const _keys = <(double, double, double, Cubic)>[
    (
      0.0,
      1.0,
      1.0,
      Cubic(0.453101546201988, 0, 0.6927696649895692, 0.16862541416124666),
    ),
    (
      0.12121212,
      1.03891748,
      1.06213032,
      Cubic(0.34433894555957734, 0.25099692881430297, 0.6075536726262294, 1),
    ),
    (
      0.24242424,
      1.16740033,
      1.27280055,
      Cubic(0.15883038650998318, 0, 0.3902175604935222, 0.7371075835019069),
    ),
    (
      0.66666667,
      1.13078306,
      0.90791122,
      Cubic(
        0.3416925053533191,
        0.8361576017130588,
        0.6736925053533187,
        0.8948466809421838,
      ),
    ),
    (
      0.84848485,
      0.97413355,
      1.03560667,
      Cubic(0.297377466581795, 0.3146371737746665, 0.6267218332272437, 1),
    ),
    (1.0, 1.0, 1.0, Cubic(0.167, 0.167, 0.833, 0.833)),
  ];
  static (double, double) scale(double t) {
    for (var i = 0; i < _keys.length - 1; i++) {
      final a = _keys[i], b = _keys[i + 1];
      if (t <= b.$1) {
        final u = a.$4.transform(((t - a.$1) / (b.$1 - a.$1)).clamp(0.0, 1.0));
        return (
          1 + ((a.$2 + (b.$2 - a.$2) * u) - 1) * .55,
          1 + ((a.$3 + (b.$3 - a.$3) * u) - 1) * .55,
        );
      }
    }
    return (1, 1);
  }
}
