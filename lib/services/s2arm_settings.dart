/// User settings of the Switch 2 (S2Arm) engine, stored by the native host and read and written through
/// `getSettings` / `setSettings` of the `neostation/s2arm_internal` channel. All of them take effect at the next game start
/// (the in-game menu also changes the frame-rate limit and frame generation during play).
class S2ArmSettings {
  const S2ArmSettings({
    this.resolutionScale = '1',
    this.antiAliasing = 'None',
    this.scalingFilter = 'Bilinear',
    this.frameRateLimit = '0',
    this.frameInterpolation = false,
    this.frameInterpolationAll = false,
    this.shadowQuality = '1',
    this.pipelineMode = 'fluid',
    this.performanceProfile = 'balanced',
    this.docked = false,
    this.widescreen = true,
    this.performanceOverlay = false,
    this.gameLanguage = 'auto',
  });

  static const defaults = S2ArmSettings();

  static const List<String> resolutionScales = <String>['0.5', '0.75', '1'];
  static const List<String> antiAliasingModes = <String>['None', 'SmaaMedium', 'SmaaHigh'];
  static const List<String> scalingFilters = <String>['Bilinear', 'Nearest'];
  static const List<String> shadowQualities = <String>['1', '0.75', '0.5'];
  static const List<String> pipelineModes = <String>['fluid', 'strict'];
  static const List<String> performanceProfiles = <String>['balanced', 'performance', 'thermalDrs'];

  /// '0' means no limit.
  // No 30 (engine patch 0319): a 30 stored by an earlier build reads as no limit.
  static const List<String> frameRateLimits = <String>['60', '120', '0'];

  /// The SystemLanguage names the native host accepts, besides 'auto'.
  static const List<String> gameLanguages = <String>[
    'AmericanEnglish', 'BritishEnglish', 'French', 'CanadianFrench', 'German', 'Italian', 'Spanish', 'LatinAmericanSpanish',
    'Dutch', 'Portuguese', 'BrazilianPortuguese', 'Russian', 'Polish', 'Japanese', 'Korean', 'SimplifiedChinese',
    'TraditionalChinese', 'Thai',
  ];

  final String resolutionScale;
  final String antiAliasing;
  final String scalingFilter;
  final String frameRateLimit;

  /// Frame generation (engine patch 0345, MetalFX frame interpolation, iOS 26): 60 frames per second on screen for games
  /// that ask for 30 or less. Off by default.
  final bool frameInterpolation;

  /// Adaptive frame generation for all games running below ~42 FPS (engine patch 0421). Off by default.
  final bool frameInterpolationAll;

  /// Shadow map resolution scale (engine patch 0421): '1' (native), '0.75', or '0.5'.
  final String shadowQuality;

  /// Render pipeline compilation mode (engine patch 0419): 'fluid' (non-blocking) or 'strict' (wait).
  final String pipelineMode;

  /// Performance / thermal profile (engine patch 0421): 'balanced', 'performance', or 'thermalDrs'.
  final String performanceProfile;
  final bool docked;
  final bool widescreen;
  final bool performanceOverlay;
  final String gameLanguage;

  /// Reads a native map; a missing or unknown value falls back to its default.
  factory S2ArmSettings.fromMap(Map<Object?, Object?> map) {
    String pick(String key, List<String> allowed, String fallback) {
      final value = map[key]?.toString();
      return value != null && allowed.contains(value) ? value : fallback;
    }

    // A number counts too: an Objective-C comparison boxed as a C int arrives as 1 or 0 (S2ArmInternalService.flag).
    bool flag(String key, bool fallback) {
      final value = map[key];
      return value is bool ? value : value is num ? value != 0 : fallback;
    }

    return S2ArmSettings(
      resolutionScale: pick('resolutionScale', resolutionScales, defaults.resolutionScale),
      antiAliasing: pick('antiAliasing', antiAliasingModes, defaults.antiAliasing),
      scalingFilter: pick('scalingFilter', scalingFilters, defaults.scalingFilter),
      frameRateLimit: pick('frameRateLimit', frameRateLimits, defaults.frameRateLimit),
      frameInterpolation: flag('frameInterpolation', defaults.frameInterpolation),
      frameInterpolationAll: flag('frameInterpolationAll', defaults.frameInterpolationAll),
      shadowQuality: pick('shadowQuality', shadowQualities, defaults.shadowQuality),
      pipelineMode: pick('pipelineMode', pipelineModes, defaults.pipelineMode),
      performanceProfile: pick('performanceProfile', performanceProfiles, defaults.performanceProfile),
      docked: flag('docked', defaults.docked),
      widescreen: flag('widescreen', defaults.widescreen),
      performanceOverlay: flag('performanceOverlay', defaults.performanceOverlay),
      gameLanguage: pick('gameLanguage', <String>['auto', ...gameLanguages], defaults.gameLanguage),
    );
  }

  Map<String, Object?> toMap() => <String, Object?>{
    'resolutionScale': resolutionScale,
    'antiAliasing': antiAliasing,
    'scalingFilter': scalingFilter,
    'frameRateLimit': frameRateLimit,
    'frameInterpolation': frameInterpolation,
    'frameInterpolationAll': frameInterpolationAll,
    'shadowQuality': shadowQuality,
    'pipelineMode': pipelineMode,
    'performanceProfile': performanceProfile,
    'docked': docked,
    'widescreen': widescreen,
    'performanceOverlay': performanceOverlay,
    'gameLanguage': gameLanguage,
  };

  S2ArmSettings copyWith({
    String? resolutionScale,
    String? antiAliasing,
    String? scalingFilter,
    String? frameRateLimit,
    bool? frameInterpolation,
    bool? frameInterpolationAll,
    String? shadowQuality,
    String? pipelineMode,
    String? performanceProfile,
    bool? docked,
    bool? widescreen,
    bool? performanceOverlay,
    String? gameLanguage,
  }) => S2ArmSettings(
    resolutionScale: resolutionScale ?? this.resolutionScale,
    antiAliasing: antiAliasing ?? this.antiAliasing,
    scalingFilter: scalingFilter ?? this.scalingFilter,
    frameRateLimit: frameRateLimit ?? this.frameRateLimit,
    frameInterpolation: frameInterpolation ?? this.frameInterpolation,
    frameInterpolationAll: frameInterpolationAll ?? this.frameInterpolationAll,
    shadowQuality: shadowQuality ?? this.shadowQuality,
    pipelineMode: pipelineMode ?? this.pipelineMode,
    performanceProfile: performanceProfile ?? this.performanceProfile,
    docked: docked ?? this.docked,
    widescreen: widescreen ?? this.widescreen,
    performanceOverlay: performanceOverlay ?? this.performanceOverlay,
    gameLanguage: gameLanguage ?? this.gameLanguage,
  );

  @override
  bool operator ==(Object other) =>
      other is S2ArmSettings &&
      other.resolutionScale == resolutionScale &&
      other.antiAliasing == antiAliasing &&
      other.scalingFilter == scalingFilter &&
      other.frameRateLimit == frameRateLimit &&
      other.frameInterpolation == frameInterpolation &&
      other.frameInterpolationAll == frameInterpolationAll &&
      other.shadowQuality == shadowQuality &&
      other.pipelineMode == pipelineMode &&
      other.performanceProfile == performanceProfile &&
      other.docked == docked &&
      other.widescreen == widescreen &&
      other.performanceOverlay == performanceOverlay &&
      other.gameLanguage == gameLanguage;

  @override
  int get hashCode => Object.hash(
    resolutionScale, antiAliasing, scalingFilter, frameRateLimit, frameInterpolation, frameInterpolationAll,
    shadowQuality, pipelineMode, performanceProfile, docked, widescreen, performanceOverlay, gameLanguage,
  );
}

/// A game's Switch 2 settings, as the native host answers `getGameSettings`, `createGameSettings`, `setGameSettings` and
/// `removeGameSettings`. [custom]: the game has its own settings profile (made from the global values of the moment, then
/// changed for that game alone; a global change leaves it as it is). [settings]: what the game starts with, its profile when
/// [custom], else the global settings.
class S2ArmGameSettings {
  const S2ArmGameSettings({required this.custom, required this.settings});

  final bool custom;
  final S2ArmSettings settings;

  /// Reads a native map; a flag boxed as a number counts too (see S2ArmSettings.fromMap).
  factory S2ArmGameSettings.fromMap(Map<Object?, Object?> map) {
    final custom = map['custom'];
    final settings = map['settings'];
    return S2ArmGameSettings(
      custom: custom is bool ? custom : custom is num && custom != 0,
      settings: settings is Map ? S2ArmSettings.fromMap(settings) : S2ArmSettings.defaults,
    );
  }

  @override
  bool operator ==(Object other) => other is S2ArmGameSettings && other.custom == custom && other.settings == settings;

  @override
  int get hashCode => Object.hash(custom, settings);
}
