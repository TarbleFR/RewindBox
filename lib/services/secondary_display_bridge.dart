import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/services/external_display_service.dart';
import 'package:neostation/services/logger_service.dart';

/// Main engine → TV menu engine (iOS, Build 447).
///
/// On Android the producers (systems grid, game lists, app tabs…) share
/// their display state with the bottom screen through
/// `SecondaryDisplayState.updateState`, which is a no-op elsewhere. On iOS
/// the same state goes to the external display's second engine instead:
/// a producer calls [forward] next to its `updateState` call with the same
/// `copyWith` arguments, and this bridge keeps the merged state (like the
/// shared state does) and pushes its JSON through
/// `ExternalDisplayService.pushMenuState`. The `Platform.isIOS` gate lives
/// here, never in the producers nor in the locked files.
class SecondaryDisplayBridge {
  SecondaryDisplayBridge._({ExternalDisplayService? service, bool? supported})
    : _serviceOverride = service,
      _supportedOverride = supported;

  static final SecondaryDisplayBridge instance = SecondaryDisplayBridge._();

  /// A separate bridge for tests (own service, platform gate forced).
  @visibleForTesting
  factory SecondaryDisplayBridge.forTesting({
    ExternalDisplayService? service,
    bool supported = true,
  }) => SecondaryDisplayBridge._(service: service, supported: supported);

  static final _log = LoggerService.instance;

  final ExternalDisplayService? _serviceOverride;
  final bool? _supportedOverride;

  SecondaryDisplayStateData? _latest;
  int _forwarded = 0;

  ExternalDisplayService get _service =>
      _serviceOverride ?? ExternalDisplayService.instance;

  /// iOS only: the producers' `Platform.isAndroid` gates use `dart:io` too.
  bool get isSupportedPlatform => _supportedOverride ?? Platform.isIOS;

  /// The last state forwarded to the TV menu (null before the first one).
  SecondaryDisplayStateData? get latest => _latest;

  /// States accepted by the native host.
  int get forwarded => _forwarded;

  /// Applies [merge] to the last forwarded state (the `WELCOME` default
  /// before the first one, like `SecondaryDisplayState.updateState`) and
  /// pushes the result to the TV menu engine. Returns false outside iOS,
  /// when [merge] throws, or when the native host did not accept it; never
  /// throws.
  Future<bool> forward(
    SecondaryDisplayStateData Function(SecondaryDisplayStateData current) merge,
  ) async {
    if (!isSupportedPlatform) return false;
    final current = _latest ?? SecondaryDisplayStateData(systemName: 'WELCOME');
    final SecondaryDisplayStateData next;
    try {
      next = merge(current);
    } catch (error) {
      _log.w('External display: menu state not built ($error)');
      return false;
    }
    _latest = next;
    final accepted = await _service.pushMenuState(next);
    if (accepted) _forwarded++;
    return accepted;
  }

  /// Pushes [state] as is (no merge).
  Future<bool> forwardState(SecondaryDisplayStateData state) =>
      forward((_) => state);
}
