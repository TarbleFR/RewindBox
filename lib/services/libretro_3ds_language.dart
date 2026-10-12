import 'package:flutter/widgets.dart';

import '../l10n/libretro_locale.dart';

/// System language of the Nintendo 3DS core (`citra_language_value` of
/// Azahar) that matches a NeoStation language.
///
/// The core never asks the frontend for its language
/// (RETRO_ENVIRONMENT_GET_LANGUAGE), so NeoStation hands the matching
/// value as a launch default while `Config/Azahar.json` stores none (see
/// `LibretroInternalService.launch`). The console has no Indonesian: `id`
/// and any unknown language fall back to English, which the Nintendo 3DS
/// page says explicitly (`lang3dsFallback`). The core applies the language
/// only while its region is Auto.
abstract final class Libretro3dsLanguage {
  /// Core option the table feeds.
  static const String optionKey = 'citra_language_value';

  /// Core value used when the NeoStation language has no 3DS equivalent.
  static const String fallback = 'English';

  /// The core's own values, in the order of the catalog setting
  /// (`LibretroCoreCatalog.cores['azahar']`, `citra_language_value`).
  static const List<String> coreValues = <String>[
    'English',
    'Japanese',
    'French',
    'Spanish',
    'German',
    'Italian',
    'Dutch',
    'Portuguese',
    'Russian',
    'Korean',
    'Traditional Chinese',
    'Simplified Chinese',
  ];

  static const Map<String, String> _labelKeys = <String, String>{
    'English': 'lang3dsEnglish',
    'Japanese': 'lang3dsJapanese',
    'French': 'lang3dsFrench',
    'Spanish': 'lang3dsSpanish',
    'German': 'lang3dsGerman',
    'Italian': 'lang3dsItalian',
    'Dutch': 'lang3dsDutch',
    'Portuguese': 'lang3dsPortuguese',
    'Russian': 'lang3dsRussian',
    'Korean': 'lang3dsKorean',
    'Traditional Chinese': 'lang3dsZhHant',
    'Simplified Chinese': 'lang3dsZhHans',
  };

  /// NeoStation language (key of `LibretroLocale.values`) to core value;
  /// `id` is absent on purpose.
  static const Map<String, String> _byLanguage = <String, String>{
    'en': 'English',
    'ja': 'Japanese',
    'fr': 'French',
    'es': 'Spanish',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'ko': 'Korean',
    'zh_Hant': 'Traditional Chinese',
    'zh': 'Simplified Chinese',
  };

  /// Core value for a NeoStation locale; script or region selects
  /// Traditional Chinese like the rest of the engine. [fallback] for
  /// Indonesian and for any language NeoStation does not ship.
  static String forAppLocale(Locale locale) =>
      _byLanguage[LibretroLocale.localeKey(locale)] ?? fallback;

  /// True when [forAppLocale] had to fall back to English because the
  /// console has no such language: the page then shows `lang3dsFallback`.
  static bool isFallback(Locale locale) =>
      !_byLanguage.containsKey(LibretroLocale.localeKey(locale));

  /// `LibretroLocale` key of a core value's label, null for a value the
  /// core does not offer.
  static String? labelKeyFor(String coreValue) => _labelKeys[coreValue];
}
