/// iPhone verdict of a skin for one console: the native
/// LibretroSkinCompatibility report (the single source of truth, computed on
/// the real parsed skin), or a refusal the catalogs decide before any
/// download (desktop overlay, decoration, unreachable file...).
library;

enum LibretroSkinVerdict { compatible, adaptable, incompatible }

class LibretroSkinCompatibility {
  const LibretroSkinCompatibility({
    required this.verdict,
    required this.console,
    this.orientations = const <String, String>{},
    this.reasons = const <String>[],
    this.missingControls = const <String>[],
    this.missingOptionalControls = const <String>[],
    this.adaptedInputs = const <String>[],
    this.unsupportedInputs = const <String>[],
    this.deadItems = 0,
    this.tabletLayout = false,
    this.smallestControlPoints = 0,
  });

  /// Refusal decided without the native analysis (one reason code of
  /// [catalogReasonKeys]).
  factory LibretroSkinCompatibility.excluded(String console, String reason) => LibretroSkinCompatibility(
        verdict: LibretroSkinVerdict.incompatible,
        console: console,
        reasons: <String>[reason],
      );

  final LibretroSkinVerdict verdict;
  final String console;

  /// {"portrait" | "landscape": "compatible" | "adaptable" | "incompatible" |
  /// "missing"}.
  final Map<String, String> orientations;

  /// Reason codes, most important first (`SKIN_COMPAT_*`).
  final List<String> reasons;

  /// Essential controls missing ("directions" for the D-pad or stick,
  /// "touchScreen", canonical button names).
  final List<String> missingControls;
  final List<String> missingOptionalControls;

  /// Skin input names converted for NeoStation, and names that stay dead.
  final List<String> adaptedInputs;
  final List<String> unsupportedInputs;
  final int deadItems;

  /// The iPhone uses the skin's iPad layouts.
  final bool tabletLayout;
  final double smallestControlPoints;

  /// Reasons decided by the catalogs, before the native analysis, and their
  /// LibretroLocale keys.
  static const String notDirect = 'SKIN_COMPAT_NOT_DIRECT';
  static const String unreachable = 'SKIN_COMPAT_UNREACHABLE';
  static const String invalid = 'SKIN_COMPAT_INVALID';
  static const String desktop = 'SKIN_COMPAT_DESKTOP';
  static const String decorative = 'SKIN_COMPAT_DECORATIVE';
  static const String deviceSpecific = 'SKIN_COMPAT_DEVICE_SPECIFIC';
  static const String overlayUnsupported = 'SKIN_COMPAT_OVERLAY_UNSUPPORTED';
  static const String system = 'SKIN_COMPAT_SYSTEM';
  static const String noTouchControls = 'SKIN_COMPAT_NO_TOUCH_CONTROLS';

  static const Map<String, String> catalogReasonKeys = <String, String>{
    notDirect: 'catalogNotDirect',
    unreachable: 'skinCompatUnreachable',
    invalid: 'skinCompatInvalid',
    desktop: 'skinCompatDesktop',
    decorative: 'skinCompatDecorative',
    deviceSpecific: 'skinCompatDeviceSpecific',
    overlayUnsupported: 'skinCompatOverlayUnsupported',
    system: 'skinCompatSystem',
  };

  /// Offered to the user (installable, shown in the catalogs).
  bool get offered => verdict != LibretroSkinVerdict.incompatible;

  /// Usable in that orientation on an iPhone.
  bool playableIn(String orientation) {
    final state = orientations[orientation];
    return state == 'compatible' || state == 'adaptable';
  }

  static LibretroSkinVerdict? verdictNamed(Object? name) => switch (name) {
        'compatible' => LibretroSkinVerdict.compatible,
        'adaptable' => LibretroSkinVerdict.adaptable,
        'incompatible' => LibretroSkinVerdict.incompatible,
        _ => null,
      };

  /// The native report (LibretroSkinCompatibilityReport.dictionary) or a
  /// stored [toJson]; null when unreadable.
  static LibretroSkinCompatibility? fromJson(Object? json, {String? console}) {
    if (json is! Map) return null;
    final verdict = verdictNamed(json['status']);
    final name = json['console'];
    final resolvedConsole = name is String && name.isNotEmpty ? name : console;
    if (verdict == null || resolvedConsole == null) return null;
    final orientations = <String, String>{};
    final rawOrientations = json['orientations'];
    if (rawOrientations is Map) {
      rawOrientations.forEach((key, value) {
        if (key is String && value is String) orientations[key] = value;
      });
    }
    final dead = json['deadItems'];
    final smallest = json['smallestControlPoints'];
    return LibretroSkinCompatibility(
      verdict: verdict,
      console: resolvedConsole,
      orientations: orientations,
      reasons: _texts(json['reasons']),
      missingControls: _texts(json['missingControls']),
      missingOptionalControls: _texts(json['missingOptionalControls']),
      adaptedInputs: _texts(json['adaptedInputs']),
      unsupportedInputs: _texts(json['unsupportedInputs']),
      deadItems: dead is num ? dead.toInt() : 0,
      tabletLayout: json['tabletLayout'] == true,
      smallestControlPoints: smallest is num ? smallest.toDouble() : 0,
    );
  }

  /// {console: report} of an inspectSkin summary ("compatibility").
  static Map<String, LibretroSkinCompatibility> fromSummary(Object? json) {
    final reports = <String, LibretroSkinCompatibility>{};
    if (json is! Map) return reports;
    json.forEach((console, value) {
      if (console is! String) return;
      final report = fromJson(value, console: console);
      if (report != null) reports[console] = report;
    });
    return reports;
  }

  Map<String, Object?> toJson() => <String, Object?>{
        'status': verdict.name,
        'console': console,
        'orientations': orientations,
        'reasons': reasons,
        'missingControls': missingControls,
        'missingOptionalControls': missingOptionalControls,
        'adaptedInputs': adaptedInputs,
        'unsupportedInputs': unsupportedInputs,
        'deadItems': deadItems,
        'tabletLayout': tabletLayout,
        'smallestControlPoints': smallestControlPoints,
      };
}

List<String> _texts(Object? value) =>
    value is List ? <String>[for (final item in value) if (item is String && item.isNotEmpty) item] : const <String>[];
