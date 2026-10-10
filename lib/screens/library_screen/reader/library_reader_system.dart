import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

/// Turns the screen wake lock on or off.
typedef LibraryReaderWakelockSetter = Future<void> Function(bool enabled);

/// System state owned by an open reader: portrait orientation (iOS) and
/// the screen wake lock, both following the reader settings.
class LibraryReaderSystemSession {
  LibraryReaderSystemSession({LibraryReaderOrientation? orientation})
    : _orientation = orientation ?? LibraryReaderOrientation.instance;

  /// Wake lock implementation (tests replace it).
  @visibleForTesting
  static LibraryReaderWakelockSetter wakelock = _defaultWakelock;

  static int _wakelockHolders = 0;

  static Future<void> _defaultWakelock(bool enabled) async {
    try {
      await WakelockPlus.toggle(enable: enabled);
    } catch (_) {
      // No wake lock on this platform: reading still works.
    }
  }

  final LibraryReaderOrientation _orientation;
  bool _started = false;
  bool _stopped = false;
  bool _holdsWakelock = false;
  bool? _allowRotation;

  /// Applies [settings] for the first time.
  Future<void> start(LibraryReaderSettings settings) async {
    if (_started || _stopped) return;
    _started = true;
    _allowRotation = settings.allowRotation;
    _setWakelock(settings.keepScreenOn);
    await _orientation.enter(allowRotation: settings.allowRotation);
  }

  /// Follows a settings change while the reader is open.
  void update(LibraryReaderSettings settings) {
    if (!_started || _stopped) return;
    _setWakelock(settings.keepScreenOn);
    if (_allowRotation != settings.allowRotation) {
      _allowRotation = settings.allowRotation;
      unawaited(_orientation.setAllowRotation(settings.allowRotation));
    }
  }

  /// The reader closed.
  Future<void> stop() async {
    if (_stopped) return;
    _stopped = true;
    _setWakelock(false);
    if (_started) await _orientation.exit();
  }

  void _setWakelock(bool on) {
    if (on == _holdsWakelock) return;
    _holdsWakelock = on;
    final before = _wakelockHolders;
    _wakelockHolders += on ? 1 : -1;
    if (_wakelockHolders < 0) _wakelockHolders = 0;
    if ((before == 0) != (_wakelockHolders == 0)) {
      unawaited(wakelock(_wakelockHolders > 0));
    }
  }
}
