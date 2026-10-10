import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';

/// The two switches a reader needs to rotate to portrait on iOS.
///
/// NeoStation's Info.plist and `lib/main.dart` are landscape only (both
/// locked). Portrait therefore needs the app-level mask of the libretro
/// bridge (`LibretroOrientation`, the same one the embedded games use) AND
/// Flutter's preferred orientations: UIKit only rotates to an orientation
/// both allow, and refuses an empty intersection.
abstract interface class LibraryReaderOrientationPlatform {
  /// Native app mask: true allows portrait, false restores landscape only
  /// (applied after Flutter's queued orientation update). Returns false when
  /// the native side refused (an embedded game owns the mask) or is missing.
  Future<bool> setNativePortraitAllowed(bool allowed);

  /// Flutter's preferred orientations ([SystemChrome]).
  Future<void> setPreferredOrientations(List<DeviceOrientation> orientations);
}

/// Default platform: the libretro bridge and [SystemChrome].
class LibraryReaderSystemOrientationPlatform
    implements LibraryReaderOrientationPlatform {
  const LibraryReaderSystemOrientationPlatform();

  @override
  Future<bool> setNativePortraitAllowed(bool allowed) =>
      LibretroInternalBridge.setReaderOrientation(allowPortrait: allowed);

  @override
  Future<void> setPreferredOrientations(List<DeviceOrientation> orientations) =>
      SystemChrome.setPreferredOrientations(orientations);
}

/// Portrait orientation for the Library readers (iOS only).
///
/// Ordering rules (UIKit rejects a Flutter preference with nothing in
/// common with the app mask):
/// * [enter]: the native mask allows portrait FIRST, then Flutter adds
///   portrait to its preferences. Flutter never asks for portrait when the
///   native call returned false.
/// * [exit]: Flutter goes back to landscape FIRST, then the native mask is
///   restored (the plugin queues it after Flutter's own update).
///
/// Readers can nest (a reader opened from another one): only the first
/// [enter] and the last [exit] change the orientation. Calls are serialized
/// so an exit never overtakes the enter it follows.
class LibraryReaderOrientation {
  LibraryReaderOrientation({
    LibraryReaderOrientationPlatform? platform,
    bool? isIOS,
  }) : _platform = platform ?? const LibraryReaderSystemOrientationPlatform(),
       _isIOS = isIOS;

  static LibraryReaderOrientation? _instance;

  static LibraryReaderOrientation get instance =>
      _instance ??= LibraryReaderOrientation();

  @visibleForTesting
  static set instance(LibraryReaderOrientation value) => _instance = value;

  /// Orientations of the rest of the app (as set by `lib/main.dart`).
  static const List<DeviceOrientation> landscape = <DeviceOrientation>[
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ];

  /// Orientations while a reader allows rotation.
  static const List<DeviceOrientation> readerOrientations = <DeviceOrientation>[
    DeviceOrientation.portraitUp,
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ];

  final LibraryReaderOrientationPlatform _platform;
  final bool? _isIOS;

  int _depth = 0;
  bool _wanted = false;
  bool _portraitActive = false;
  Future<void> _queue = Future<void>.value();

  bool get _supported => _isIOS ?? (!kIsWeb && Platform.isIOS);

  /// Number of open readers.
  int get depth => _depth;

  /// Whether portrait is currently allowed (both switches set).
  bool get portraitActive => _portraitActive;

  /// A reader opened. [allowRotation] is the reader setting.
  Future<void> enter({required bool allowRotation}) {
    _depth++;
    if (_depth == 1) _wanted = allowRotation;
    return _enqueue(_apply);
  }

  /// The reader setting changed while readers are open.
  Future<void> setAllowRotation(bool allowRotation) {
    if (_depth == 0) return _queue;
    _wanted = allowRotation;
    return _enqueue(_apply);
  }

  /// A reader closed.
  Future<void> exit() {
    if (_depth == 0) return _queue;
    _depth--;
    return _enqueue(_apply);
  }

  Future<void> _enqueue(Future<void> Function() step) {
    final next = _queue.then((_) => step()).catchError((Object _) {});
    _queue = next;
    return next;
  }

  Future<void> _apply() async {
    final allow = _supported && _depth > 0 && _wanted;
    if (allow == _portraitActive) return;
    if (allow) {
      await _allowPortrait();
    } else {
      await _restoreLandscape();
    }
  }

  /// Native mask first, then Flutter.
  Future<void> _allowPortrait() async {
    bool granted;
    try {
      granted = await _platform.setNativePortraitAllowed(true);
    } catch (_) {
      granted = false;
    }
    if (!granted) return;
    _portraitActive = true;
    await _platform.setPreferredOrientations(readerOrientations);
  }

  /// Flutter first, then the native mask.
  Future<void> _restoreLandscape() async {
    _portraitActive = false;
    try {
      await _platform.setPreferredOrientations(landscape);
    } finally {
      try {
        await _platform.setNativePortraitAllowed(false);
      } catch (_) {
        // The bridge restores nothing it did not set; nothing else to undo.
      }
    }
  }
}
