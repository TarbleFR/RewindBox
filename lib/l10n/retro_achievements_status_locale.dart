import 'app_locale.dart';

/// Localized texts for the native in-game RetroAchievements launch status.
///
/// The central native hub decides *which* status applies from the state each
/// engine actually published; it receives these labels with the launch
/// snapshot so every language stays in the application catalogs (12 locales)
/// instead of a second native copy. `{unlocked}` and `{total}` are replaced
/// natively. None of these strings carries account data.
abstract final class RetroAchievementsStatusLocale {
  /// Native status key -> application catalog key.
  static const keys = <String, String>{
    'active': AppLocale.raSessionActive,
    'progress': AppLocale.raStatusProgress,
    'hardcoreOn': AppLocale.raStatusHardcoreOn,
    'hardcoreOff': AppLocale.raStatusHardcoreOff,
    'hardcoreNotApplied': AppLocale.raStatusHardcoreNotApplied,
    'signingIn': AppLocale.raStatusSigningIn,
    'identifying': AppLocale.raStatusIdentifying,
    'noAchievements': AppLocale.raStatusNoAchievements,
    'setUnsupported': AppLocale.raStatusSetUnsupported,
    'unknownGame': AppLocale.raStatusUnknownGame,
    'unsupported': AppLocale.raStatusUnsupported,
    'signIn': AppLocale.raStatusSignIn,
    'authRejected': AppLocale.raStatusAuthRejected,
    'network': AppLocale.raStatusNetwork,
    'loginFailed': AppLocale.raStatusLoginFailed,
    'hardcoreOptions': AppLocale.raStatusHardcoreOptions,
    'loadFailed': AppLocale.raStatusLoadFailed,
    'unavailable': AppLocale.raStatusUnavailable,
    'unconfirmed': AppLocale.raStatusUnconfirmed,
    // Existing unit label ("pts", "points", "Punkte"…) for unlock toasts.
    'points': AppLocale.points,
  };

  /// Catalog for an application language tag (`fr`, `zh_Hant`, `zh-Hant-TW`,
  /// `pt-BR`...). Traditional Chinese is selected by script or region.
  static Map<String, dynamic> catalogFor(String tag) {
    final normalized = tag.replaceAll('_', '-').toLowerCase();
    final parts = normalized.split('-');
    if (parts.first == 'zh') {
      final traditional = parts.contains('hant') ||
          parts.any((part) => part == 'tw' || part == 'hk' || part == 'mo');
      return traditional ? AppLocale.zhHant : AppLocale.zh;
    }
    return switch (parts.first) {
      'es' => AppLocale.es,
      'ru' => AppLocale.ru,
      'pt' => AppLocale.pt,
      'fr' => AppLocale.fr,
      'de' => AppLocale.de,
      'it' => AppLocale.it,
      'id' => AppLocale.id,
      'ja' => AppLocale.ja,
      'ko' => AppLocale.ko,
      _ => AppLocale.en,
    };
  }

  /// Status labels for the launch snapshot, English only for a missing key.
  static Map<String, String> forLanguage(String tag) {
    final catalog = catalogFor(tag);
    return {
      for (final entry in keys.entries)
        entry.key: (catalog[entry.value] ?? AppLocale.en[entry.value] ?? '') as String,
    };
  }
}
