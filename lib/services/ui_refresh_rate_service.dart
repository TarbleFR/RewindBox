import 'package:flutter/foundation.dart';

/// Settings › General › 120 Hz interface (Build 438).
///
/// Contract stub: the 120 Hz package replaces this file with the real service
/// (stored preference, screen capability, FrameTiming measurement). AppScreen
/// already calls [startProbe] on iOS so the measurement listens when the user
/// returns from a game.
class UiRefreshRateService extends ChangeNotifier {
  UiRefreshRateService._();

  static final UiRefreshRateService instance = UiRefreshRateService._();

  /// iOS only; tests override [defaultTargetPlatform].
  static bool get isSupportedPlatform =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  /// Starts the passive frame-rate measurement. Idempotent; never schedules
  /// frames.
  void startProbe() {}
}
