import 'package:flutter/services.dart';

/// Placement of NeoStation's picture on the external screen
/// (`NeoExternalDisplayLayout.h`).
enum ExternalDisplayMode {
  /// Menu: whole window; game: [fit].
  automatic(0),

  /// Whole image; bars only when the aspect ratios differ.
  fit(1),

  /// A 4:3 image zoomed to the TV width, top and bottom cut.
  fill(2),

  /// The iPhone's own format, centred at the TV height.
  original(3);

  const ExternalDisplayMode(this.value);

  /// The integer stored by the native side (`NeoStation.ExternalDisplay.Mode`).
  final int value;

  /// Out-of-range or non-numeric values are [automatic], like the native
  /// `NeoExternalDisplayModeFromValue`.
  static ExternalDisplayMode fromValue(Object? value) {
    final number = value is num ? value.toInt() : null;
    for (final mode in values) {
      if (mode.value == number) return mode;
    }
    return automatic;
  }

  /// The next mode of the settings chip (Automatic → Fit → Fill → Original).
  ExternalDisplayMode get next => values[(index + 1) % values.length];

  /// Only [fill] cuts part of the image.
  bool get crops => this == fill;
}

/// What the external window shows.
enum ExternalDisplayContent {
  none,
  menu,
  game;

  static ExternalDisplayContent fromName(Object? name) {
    for (final content in values) {
      if (content.name == name) return content;
    }
    return none;
  }
}

/// Native state of the external display (iOS).
///
/// Field names follow the `neostation/external_display` channel contract
/// (`ExternalDisplayPlugin.m`, `NeoExternalDisplayCoordinator.m`).
class ExternalDisplayState {
  const ExternalDisplayState({
    required this.supported,
    required this.connected,
    required this.content,
    required this.screenWidth,
    required this.screenHeight,
    required this.screenScale,
    required this.mode,
    required this.enabled,
    required this.menuOnTV,
    this.suspended = false,
    required this.mirroringActive,
    required this.accessoryStatus,
    required this.sceneRole,
    required this.menuEngine,
  });

  factory ExternalDisplayState.fromMap(Map<Object?, Object?> map) =>
      ExternalDisplayState(
        supported: map['supported'] as bool? ?? false,
        connected: map['connected'] as bool? ?? false,
        content: ExternalDisplayContent.fromName(map['content']),
        screenWidth: (map['screenWidth'] as num?)?.toDouble() ?? 0,
        screenHeight: (map['screenHeight'] as num?)?.toDouble() ?? 0,
        screenScale: (map['screenScale'] as num?)?.toDouble() ?? 0,
        mode: ExternalDisplayMode.fromValue(map['mode']),
        enabled: map['enabled'] as bool? ?? true,
        menuOnTV: map['menuOnTV'] as bool? ?? true,
        suspended: map['suspended'] as bool? ?? false,
        mirroringActive: map['mirroringActive'] as bool? ?? false,
        accessoryStatus:
            map['accessoryStatus'] as String? ?? accessoryUnavailable,
        sceneRole: map['sceneRole'] as String? ?? sceneRoleNone,
        menuEngine: map['menuEngine'] as String? ?? menuEngineNone,
      );

  /// State reported when the native side cannot answer: the plugin is not
  /// part of the app ([pluginMissing]) or the channel failed (the raw error
  /// code). Never supported.
  factory ExternalDisplayState.unreachable([String status = pluginMissing]) =>
      ExternalDisplayState(
        supported: false,
        connected: false,
        content: ExternalDisplayContent.none,
        screenWidth: 0,
        screenHeight: 0,
        screenScale: 0,
        mode: ExternalDisplayMode.automatic,
        enabled: true,
        menuOnTV: true,
        mirroringActive: false,
        accessoryStatus: status,
        sceneRole: sceneRoleNone,
        menuEngine: menuEngineNone,
      );

  static const String pluginMissing = 'pluginMissing';
  static const String accessoryUnavailable = 'unavailable';
  static const String accessoryRegistered = 'registered';
  static const String sceneRoleScene = 'scene';
  static const String sceneRoleLegacy = 'legacy';
  static const String sceneRoleNone = 'none';
  static const String menuEngineNone = 'none';
  static const String menuEngineCreated = 'created';
  static const String menuEngineAttached = 'attached';
  static const String menuEngineDestroyed = 'destroyed';

  /// The plugin exists on this platform.
  final bool supported;

  /// NeoStation owns a window on an external screen.
  final bool connected;

  final ExternalDisplayContent content;

  /// Points of the external window; 0 when disconnected.
  final double screenWidth;
  final double screenHeight;
  final double screenScale;

  /// Stored preference (`NeoStation.ExternalDisplay.Mode`).
  final ExternalDisplayMode mode;

  /// `NeoStation.ExternalDisplay.Enabled`; false = system mirroring.
  final bool enabled;

  /// `NeoStation.ExternalDisplay.MenuOnTV`.
  final bool menuOnTV;

  /// An engine that cannot draw on the external screen runs (Dusklight,
  /// KartPad): NeoStation's window is hidden and iOS mirrors the iPhone.
  final bool suspended;

  /// iOS mirrors the iPhone on the connected screen (NeoStation shows
  /// nothing of its own there).
  final bool mirroringActive;

  /// iOS 27 scene accessory: `unavailable`, `registered` or `failed:<reason>`;
  /// [pluginMissing] or a raw error code when unreachable.
  final String accessoryStatus;

  /// `scene`, `legacy` or `none`.
  final String sceneRole;

  /// `none`, `created`, `attached` or `destroyed`.
  final String menuEngine;

  bool get gameOnExternal =>
      connected && content == ExternalDisplayContent.game;

  bool get menuOnExternal =>
      connected && content == ExternalDisplayContent.menu;

  bool get accessoryFailed => accessoryStatus.startsWith('failed:');

  /// The stored mode as applied to a game (Automatic → Fit).
  ExternalDisplayMode get effectiveGameMode =>
      mode == ExternalDisplayMode.automatic ? ExternalDisplayMode.fit : mode;
}

/// Method and event channel wrapper (`neostation/external_display`).
class ExternalDisplayChannel {
  ExternalDisplayChannel();

  static const MethodChannel channel = MethodChannel(
    'neostation/external_display',
  );

  static const EventChannel eventChannel = EventChannel(
    'neostation/external_display/events',
  );

  static Stream<ExternalDisplayState>? _events;

  /// The native state at every `NeoStation.ExternalDisplayStateChanged`
  /// (one broadcast stream shared by every listener). A missing plugin
  /// yields a single [ExternalDisplayState.unreachable] state.
  Stream<ExternalDisplayState> get events => _events ??= eventChannel
      .receiveBroadcastStream()
      .map(_stateFromEvent)
      .handleError(
        (Object error) => ExternalDisplayState.unreachable(),
        test: (error) => error is MissingPluginException,
      )
      .asBroadcastStream();

  static ExternalDisplayState _stateFromEvent(Object? event) =>
      ExternalDisplayState.fromMap(
        event is Map
            ? event.cast<Object?, Object?>()
            : const <Object?, Object?>{},
      );

  Future<ExternalDisplayState> _invoke(
    String method, [
    Map<String, Object?>? arguments,
  ]) async {
    final map = await channel.invokeMapMethod<Object?, Object?>(
      method,
      arguments,
    );
    return ExternalDisplayState.fromMap(map ?? const <Object?, Object?>{});
  }

  /// Current state. A missing plugin reports
  /// [ExternalDisplayState.pluginMissing]; other platform errors propagate.
  Future<ExternalDisplayState> getState() async {
    try {
      return await _invoke('getState');
    } on MissingPluginException {
      return ExternalDisplayState.unreachable();
    }
  }

  /// Stores the switch and returns the re-read state. Throws
  /// [PlatformException] `SAVE_FAILED` when iOS did not keep it.
  Future<ExternalDisplayState> setEnabled(bool enabled) =>
      _invoke('setEnabled', <String, Object?>{'enabled': enabled});

  /// Stores the mode and returns the re-read state (`BAD_ARGS` out of
  /// 0..3, `SAVE_FAILED` when iOS did not keep it).
  Future<ExternalDisplayState> setMode(ExternalDisplayMode mode) =>
      _invoke('setMode', <String, Object?>{'mode': mode.value});

  /// Stores whether the menu's second engine is shown on the TV.
  Future<ExternalDisplayState> setMenuOnTV(bool enabled) =>
      _invoke('setMenuOnTV', <String, Object?>{'enabled': enabled});

  /// Names the Dart entrypoint of the TV menu, with the language and the
  /// theme it starts with (the second engine never reads the database);
  /// without it the native side never creates the second engine.
  Future<ExternalDisplayState> configureMenuEngine({
    required String entrypoint,
    required String libraryUri,
    String? languageCode,
    String? themeName,
  }) =>
      _invoke('configureMenuEngine', <String, Object?>{
        'entrypoint': entrypoint,
        'libraryUri': libraryUri,
        'languageCode': languageCode,
        'themeName': themeName,
      });

  /// The app language or theme changed: the native copy given to the next
  /// TV engine follows, and a running one applies a new language at once.
  /// A null value is left as it was. Returns false when the plugin is
  /// missing; other platform errors propagate.
  Future<bool> updateMenuEngine({String? languageCode, String? themeName}) async {
    try {
      final accepted = await channel.invokeMethod<bool>(
        'updateMenuEngine',
        <String, Object?>{'languageCode': languageCode, 'themeName': themeName},
      );
      return accepted ?? false;
    } on MissingPluginException {
      return false;
    }
  }

  /// Relays the JSON of `SecondaryDisplayStateData` to the second engine
  /// (`neostation/external_display/menu`). Returns false when the plugin is
  /// missing.
  Future<bool> pushMenuState(String json) async {
    try {
      final accepted = await channel.invokeMethod<bool>(
        'pushMenuState',
        <String, Object?>{'json': json},
      );
      return accepted ?? false;
    } on MissingPluginException {
      return false;
    }
  }

  /// Hides NeoStation's window on the external screen while an engine that
  /// cannot draw there runs (iOS mirrors the iPhone meanwhile). Returns
  /// false when the plugin is missing; other platform errors propagate.
  Future<bool> suspendForUnsupportedEngine() =>
      _invokeFlag('suspendForUnsupportedEngine');

  /// Shows the window again after [suspendForUnsupportedEngine].
  Future<bool> resumeAfterUnsupportedEngine() =>
      _invokeFlag('resumeAfterUnsupportedEngine');

  Future<bool> _invokeFlag(String method) async {
    try {
      return await channel.invokeMethod<bool>(method) ?? false;
    } on MissingPluginException {
      return false;
    }
  }
}
