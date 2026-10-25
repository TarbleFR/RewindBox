import 'dart:async';

import 'package:flutter/widgets.dart';

import 'frontend_media_gate.dart';

/// Decides how much of the glass rendering budget the frontend may spend
/// right now. Backdrop blur is the only genuinely expensive part of a glass
/// surface, so it is the first thing given up:
///
/// * an embedded game is running ([FrontendMediaGate]): no blur at all, the
///   emulator owns the GPU;
/// * Low Power Mode: half the blur radius, no decorative motion;
/// * a memory warning: no blur and lighter shadows for a short relief window.
///
/// Surfaces stay translucent in every case; only the blur pass and the
/// shadow strength change, so the interface keeps the same layout.
class GlassPerformanceGovernor extends ChangeNotifier
    with WidgetsBindingObserver {
  GlassPerformanceGovernor._();

  static final GlassPerformanceGovernor instance = GlassPerformanceGovernor._();

  /// How long blur stays off after a memory warning.
  static const Duration memoryRelief = Duration(seconds: 90);

  bool _started = false;
  bool _emulation = false;
  bool _lowPower = false;
  bool _memoryPressure = false;
  Timer? _relief;

  bool get emulationActive => _emulation;
  bool get lowPower => _lowPower;
  bool get memoryPressure => _memoryPressure;

  /// 0 disables the blur pass, 1 keeps the configured radius.
  double get blurBudget {
    if (_emulation || _memoryPressure) return 0;
    if (_lowPower) return 0.5;
    return 1;
  }

  /// Shadow strength multiplier.
  double get depthBudget => _memoryPressure ? 0.5 : 1;

  /// Whether decorative (non-essential) motion may run.
  bool get decorativeMotion => !_lowPower && !_emulation;

  void start() {
    if (_started) return;
    _started = true;
    WidgetsBinding.instance.addObserver(this);
    FrontendMediaGate.instance.addListener(_syncEmulation);
    _syncEmulation();
  }

  void _syncEmulation() {
    final blocked = FrontendMediaGate.instance.blocked;
    if (blocked == _emulation) return;
    _emulation = blocked;
    notifyListeners();
  }

  set lowPower(bool value) {
    if (_lowPower == value) return;
    _lowPower = value;
    notifyListeners();
  }

  @override
  void didHaveMemoryPressure() => noteMemoryPressure();

  /// Also called by widgets that observe memory warnings themselves.
  void noteMemoryPressure() {
    _relief?.cancel();
    _relief = Timer(memoryRelief, _endRelief);
    if (_memoryPressure) return;
    _memoryPressure = true;
    notifyListeners();
  }

  void _endRelief() {
    _relief = null;
    if (!_memoryPressure) return;
    _memoryPressure = false;
    notifyListeners();
  }

  @visibleForTesting
  void debugReset({bool emulation = false, bool lowPower = false}) {
    _relief?.cancel();
    _relief = null;
    final changed =
        _emulation != emulation || _lowPower != lowPower || _memoryPressure;
    _emulation = emulation;
    _lowPower = lowPower;
    _memoryPressure = false;
    if (changed) notifyListeners();
  }

  @visibleForTesting
  void debugEndRelief() => _endRelief();
}
