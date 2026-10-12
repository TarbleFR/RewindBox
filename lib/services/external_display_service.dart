import 'dart:async';
import 'dart:convert';

import 'package:external_display/external_display.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:neostation/external_display/external_display_entrypoint.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/services/logger_service.dart';

export 'package:external_display/external_display.dart'
    show ExternalDisplayContent, ExternalDisplayMode, ExternalDisplayState;

/// Why the last user action on the option did not apply.
enum ExternalDisplayError { saveFailed }

/// The preference a failed action was writing.
enum ExternalDisplayField { enabled, mode, menuOnTV }

/// Settings › General › "AirPlay and external screen" (Build 447, iOS).
///
/// - The three preferences live in NSUserDefaults on the native side
///   (`NeoStation.ExternalDisplay.{Enabled,Mode,MenuOnTV}`,
///   `NeoExternalDisplayPreferences`); every write is re-read from the
///   native answer, and a choice that iOS did not keep is reported as a
///   save failure, never as saved.
/// - The connection, the content of the external window and the TV size
///   come from the native coordinator through the method channel and the
///   event channel (`NeoStation.ExternalDisplayStateChanged`).
/// - [init] names the Dart entrypoint of the TV menu engine to the native
///   host; without it no second engine is ever created.
class ExternalDisplayService extends ChangeNotifier {
  ExternalDisplayService._({
    ExternalDisplayChannel? channel,
    Stream<ExternalDisplayState>? events,
  }) : _channel = channel ?? ExternalDisplayChannel(),
       _eventsOverride = events;

  static final ExternalDisplayService instance = ExternalDisplayService._();

  /// A separate service for tests (own channel wrapper and event stream).
  @visibleForTesting
  factory ExternalDisplayService.forTesting({
    ExternalDisplayChannel? channel,
    Stream<ExternalDisplayState>? events,
  }) => ExternalDisplayService._(channel: channel, events: events);

  /// iOS only; tests override [defaultTargetPlatform].
  static bool get isSupportedPlatform =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  static final _log = LoggerService.instance;

  final ExternalDisplayChannel _channel;
  final Stream<ExternalDisplayState>? _eventsOverride;

  ExternalDisplayState? _state;
  Future<ExternalDisplayState>? _refreshing;
  StreamSubscription<ExternalDisplayState>? _events;
  bool _initialized = false;
  int _menuEngineConfigured = 0;
  bool _saving = false;
  ExternalDisplayError? _error;
  ExternalDisplayField? _errorField;
  String? _errorCode;

  /// Native state, null until the first [refresh] or [init] completes.
  ExternalDisplayState? get state => _state;

  bool get saving => _saving;

  /// Last action error (cleared by the next successful action).
  ExternalDisplayError? get error => _error;

  /// The preference the failed action was writing.
  ExternalDisplayField? get errorField => _errorField;

  /// Raw technical code of [error] (platform error code), never translated.
  String? get errorCode => _errorCode;

  /// [init] ran (the event subscription exists and the menu entrypoint was
  /// sent to the native host).
  bool get initialized => _initialized;

  /// How many times `configureMenuEngine` was sent (once per process).
  int get menuEngineConfigured => _menuEngineConfigured;

  /// Names the TV menu entrypoint to the native host, follows the native
  /// state events and reads the first state. Idempotent: a second call does
  /// nothing. Never throws: a missing plugin leaves an unsupported state.
  Future<void> init() async {
    if (_initialized) return;
    _initialized = true;
    _subscribe();
    ExternalDisplayState next;
    try {
      next = await _channel.configureMenuEngine(
        entrypoint: kExternalDisplayEntrypoint,
        libraryUri: kExternalDisplayLibraryUri,
      );
      _menuEngineConfigured++;
      _log.i(
        'External display: menu engine configured '
        '($kExternalDisplayEntrypoint, $kExternalDisplayLibraryUri)',
      );
    } on MissingPluginException {
      _log.w('External display: plugin missing, menu engine not configured');
      next = ExternalDisplayState.unreachable();
    } on PlatformException catch (error) {
      _log.w('External display: configureMenuEngine refused (${error.code})');
      next = ExternalDisplayState.unreachable(error.code);
    } catch (error) {
      _log.w('External display: configureMenuEngine unreadable ($error)');
      next = ExternalDisplayState.unreachable('invalidState');
    }
    _apply(next);
  }

  void _subscribe() {
    if (_events != null) return;
    _events = (_eventsOverride ?? _channel.events).listen(
      _apply,
      onError: (Object error) {
        _log.w('External display: event stream error ($error)');
      },
    );
  }

  /// Reads the native state again (connection, content, TV size, stored
  /// preferences).
  Future<ExternalDisplayState> refresh() {
    final pending = _refreshing;
    if (pending != null) return pending;
    final future = _readState();
    _refreshing = future;
    return future.whenComplete(() => _refreshing = null);
  }

  Future<ExternalDisplayState> _readState() async {
    ExternalDisplayState next;
    try {
      next = await _channel.getState();
    } on PlatformException catch (error) {
      _log.w('External display: state unavailable (${error.code})');
      next = ExternalDisplayState.unreachable(error.code);
    } catch (error) {
      // A malformed answer must not escape the callers that do not await.
      _log.w('External display: state unreadable ($error)');
      next = ExternalDisplayState.unreachable('invalidState');
    }
    _apply(next);
    return next;
  }

  void _apply(ExternalDisplayState next) {
    final previous = _state;
    _state = next;
    if (previous == null ||
        previous.supported != next.supported ||
        previous.connected != next.connected ||
        previous.content != next.content ||
        previous.mode != next.mode ||
        previous.enabled != next.enabled ||
        previous.menuOnTV != next.menuOnTV ||
        previous.menuEngine != next.menuEngine ||
        previous.sceneRole != next.sceneRole ||
        previous.accessoryStatus != next.accessoryStatus) {
      _log.i(
        'External display: supported=${next.supported} '
        'connected=${next.connected} content=${next.content.name} '
        'screen=${next.screenWidth}x${next.screenHeight}@${next.screenScale} '
        'mode=${next.mode.name} enabled=${next.enabled} '
        'menuOnTV=${next.menuOnTV} mirroring=${next.mirroringActive} '
        'scene=${next.sceneRole} accessory=${next.accessoryStatus} '
        'menuEngine=${next.menuEngine}',
      );
    }
    notifyListeners();
  }

  bool get _canWrite => _state != null && _state!.supported && !_saving;

  /// Stores the switch (own window on the external screen, or system
  /// mirroring). Returns false, with [error] set, when iOS did not keep it.
  Future<bool> setEnabled(bool enabled) => _write(
    ExternalDisplayField.enabled,
    () => _channel.setEnabled(enabled),
    (next) => next.enabled == enabled,
    'enabled=$enabled',
  );

  /// Stores the picture format. Returns false, with [error] set, when iOS
  /// did not keep it.
  Future<bool> setMode(ExternalDisplayMode mode) => _write(
    ExternalDisplayField.mode,
    () => _channel.setMode(mode),
    (next) => next.mode == mode,
    'mode=${mode.name}',
  );

  /// Stores whether the menu's second engine is shown on the TV.
  Future<bool> setMenuOnTV(bool enabled) => _write(
    ExternalDisplayField.menuOnTV,
    () => _channel.setMenuOnTV(enabled),
    (next) => next.menuOnTV == enabled,
    'menuOnTV=$enabled',
  );

  Future<bool> _write(
    ExternalDisplayField field,
    Future<ExternalDisplayState> Function() call,
    bool Function(ExternalDisplayState next) kept,
    String description,
  ) async {
    if (!_canWrite) return false;
    _saving = true;
    notifyListeners();
    try {
      final next = await call();
      if (!kept(next)) {
        throw PlatformException(code: 'SAVE_NOT_KEPT');
      }
      _error = null;
      _errorField = null;
      _errorCode = null;
      _apply(next);
      _log.i('External display: stored $description');
      return true;
    } on PlatformException catch (error) {
      return _saveFailed(field, error.code);
    } on MissingPluginException {
      return _saveFailed(field, ExternalDisplayState.pluginMissing);
    } catch (error) {
      _log.w('External display: unreadable answer to $description ($error)');
      return _saveFailed(field, 'invalidState');
    } finally {
      _saving = false;
      notifyListeners();
    }
  }

  bool _saveFailed(ExternalDisplayField field, String code) {
    _error = ExternalDisplayError.saveFailed;
    _errorField = field;
    _errorCode = code;
    _log.w('External display: ${field.name} not saved ($code)');
    // Show what iOS actually kept, not the choice that failed.
    unawaited(refresh());
    return false;
  }

  /// Flips the stored switch (gamepad A / tap on the row).
  Future<bool> toggleEnabled() {
    final current = _state;
    if (current == null || !current.supported) return Future.value(false);
    return setEnabled(!current.enabled);
  }

  /// Flips the stored "menu on the TV" switch.
  Future<bool> toggleMenuOnTV() {
    final current = _state;
    if (current == null || !current.supported) return Future.value(false);
    return setMenuOnTV(!current.menuOnTV);
  }

  /// Stores the next format (Automatic → Fit → Fill → Original → Automatic).
  Future<bool> cycleMode() {
    final current = _state;
    if (current == null || !current.supported) return Future.value(false);
    return setMode(current.mode.next);
  }

  /// Relays the menu state of the main engine to the TV menu engine (the
  /// native host keeps the last one for an engine created later). False
  /// when the plugin is missing or refused it.
  Future<bool> pushMenuState(SecondaryDisplayStateData data) async {
    final String json;
    try {
      json = jsonEncode(data.toJson());
    } catch (error) {
      _log.w('External display: menu state not encodable ($error)');
      return false;
    }
    try {
      return await _channel.pushMenuState(json);
    } on PlatformException catch (error) {
      _log.w('External display: menu state refused (${error.code})');
      return false;
    }
  }

  @override
  void dispose() {
    unawaited(_events?.cancel());
    _events = null;
    super.dispose();
  }
}
