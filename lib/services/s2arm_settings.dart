/// User settings of the Switch 2 (S2Arm) engine, stored by the native host and read and written through
/// `getSettings` / `setSettings` of the `neostation/s2arm_internal` channel. All of them take effect at the next game start.
class S2ArmSettings {
  const S2ArmSettings({
    this.resolutionScale = '1',
    this.antiAliasing = 'None',
    this.scalingFilter = 'Bilinear',
    this.frameRateLimit = '0',
    this.docked = false,
    this.widescreen = true,
    this.performanceOverlay = false,
    this.gameLanguage = 'auto',
  });

  static const defaults = S2ArmSettings();

  static const List<String> resolutionScales = <String>['0.5', '0.75', '1'];
  static const List<String> antiAliasingModes = <String>['None', 'SmaaMedium', 'SmaaHigh'];
  static const List<String> scalingFilters = <String>['Bilinear', 'Nearest'];

  /// '0' means no limit.
  static const List<String> frameRateLimits = <String>['30', '60', '120', '0'];

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

    bool flag(String key, bool fallback) {
      final value = map[key];
      return value is bool ? value : fallback;
    }

    return S2ArmSettings(
      resolutionScale: pick('resolutionScale', resolutionScales, defaults.resolutionScale),
      antiAliasing: pick('antiAliasing', antiAliasingModes, defaults.antiAliasing),
      scalingFilter: pick('scalingFilter', scalingFilters, defaults.scalingFilter),
      frameRateLimit: pick('frameRateLimit', frameRateLimits, defaults.frameRateLimit),
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
    bool? docked,
    bool? widescreen,
    bool? performanceOverlay,
    String? gameLanguage,
  }) => S2ArmSettings(
    resolutionScale: resolutionScale ?? this.resolutionScale,
    antiAliasing: antiAliasing ?? this.antiAliasing,
    scalingFilter: scalingFilter ?? this.scalingFilter,
    frameRateLimit: frameRateLimit ?? this.frameRateLimit,
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
      other.docked == docked &&
      other.widescreen == widescreen &&
      other.performanceOverlay == performanceOverlay &&
      other.gameLanguage == gameLanguage;

  @override
  int get hashCode => Object.hash(
    resolutionScale, antiAliasing, scalingFilter, frameRateLimit, docked, widescreen, performanceOverlay, gameLanguage,
  );
}
