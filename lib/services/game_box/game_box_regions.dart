/// Regions of retail editions and the language their print most likely uses.
///
/// ScreenScraper tags each scan with a region code (`us`, `eu`, `jp`, `fr`,
/// …), not a language. The language of a scan is therefore a presumption
/// from its region ([languageOfRegion]), shown as such, and confirmed only by
/// the text recognition of the back (docs/game-box-3d.md § 6).
class GameBoxRegions {
  GameBoxRegions._();

  /// No-Intro / Redump filename tags → ScreenScraper region codes.
  static const Map<String, String> _tagToRegion = {
    'usa': 'us', 'u': 'us', 'us': 'us', 'america': 'us', 'ntsc-u': 'us',
    'europe': 'eu', 'e': 'eu', 'eu': 'eu', 'pal': 'eu',
    'japan': 'jp', 'j': 'jp', 'jp': 'jp', 'ntsc-j': 'jp',
    'world': 'wor', 'w': 'wor',
    'france': 'fr', 'f': 'fr', 'fr': 'fr',
    'germany': 'de', 'g': 'de', 'de': 'de',
    'spain': 'sp', 's': 'sp', 'es': 'sp',
    'italy': 'it', 'i': 'it', 'it': 'it',
    'korea': 'kr', 'k': 'kr', 'kr': 'kr',
    'china': 'cn', 'ch': 'cn', 'cn': 'cn',
    'taiwan': 'tw', 'tw': 'tw', 'hong kong': 'asi',
    'asia': 'asi', 'as': 'asi',
    'brazil': 'br', 'b': 'br', 'br': 'br',
    'portugal': 'pt', 'pt': 'pt',
    'australia': 'au', 'a': 'au', 'au': 'au',
    'uk': 'uk', 'united kingdom': 'uk',
    'canada': 'ca', 'c': 'ca', 'ca': 'ca',
    'russia': 'ru', 'r': 'ru', 'ru': 'ru',
    'netherlands': 'nl', 'nl': 'nl', 'sweden': 'se', 'se': 'se',
    'denmark': 'dk', 'finland': 'fi', 'norway': 'no', 'poland': 'pl',
    'greece': 'gr', 'scandinavia': 'eu',
  };

  /// Region codes of a ROM filename, in the order of its tags, or empty when
  /// the name carries none. Only parenthesised groups made entirely of known
  /// region names count, so "(Rev 1)" or "(Disc 2)" never count as regions.
  static List<String> fromFileName(String fileName) {
    final out = <String>[];
    for (final m in RegExp(r'\(([^)]*)\)').allMatches(fileName)) {
      final tokens = m.group(1)!.split(',').map((t) => t.trim().toLowerCase()).where((t) => t.isNotEmpty).toList();
      if (tokens.isEmpty) continue;
      final mapped = tokens.map((t) => _tagToRegion[t]).toList();
      if (mapped.any((r) => r == null)) continue;
      for (final r in mapped) {
        if (!out.contains(r)) out.add(r!);
      }
    }
    return out;
  }

  /// Language tags such as "(En,Fr,De)" → NeoStation language codes.
  static List<String> languagesFromFileName(String fileName) {
    const map = {
      'en': 'en', 'fr': 'fr', 'de': 'de', 'es': 'es', 'it': 'it', 'pt': 'pt',
      'ja': 'ja', 'ko': 'ko', 'ru': 'ru', 'zh': 'zh', 'zh-hant': 'zh_Hant',
      'zh-hans': 'zh', 'id': 'id', 'nl': 'nl', 'sv': 'sv',
    };
    final out = <String>[];
    for (final m in RegExp(r'\(([^)]*)\)').allMatches(fileName)) {
      final tokens = m.group(1)!.split(',').map((t) => t.trim().toLowerCase()).toList();
      if (tokens.isEmpty || tokens.any((t) => !map.containsKey(t))) continue;
      for (final t in tokens) {
        final l = map[t]!;
        if (!out.contains(l)) out.add(l);
      }
    }
    return out;
  }

  /// Presumed language of a scan printed for [region] (ScreenScraper code),
  /// as a NeoStation language code, or null when the region does not imply
  /// one (custom scans, multilingual or unknown regions).
  static String? languageOfRegion(String region) {
    switch (region.toLowerCase()) {
      case 'us':
      case 'uk':
      case 'au':
      case 'nz':
      case 'wor':
      case 'eu':
      case 'ca':
      case 'ame':
      case 'oce':
        return 'en';
      case 'jp':
        return 'ja';
      case 'fr':
        return 'fr';
      case 'de':
        return 'de';
      case 'sp':
        return 'es';
      case 'it':
        return 'it';
      case 'pt':
      case 'br':
        return 'pt';
      case 'kr':
        return 'ko';
      case 'cn':
        return 'zh';
      case 'tw':
        return 'zh_Hant';
      case 'ru':
        return 'ru';
      default:
        return null;
    }
  }

  /// Regions whose language is only a presumption even for English: European
  /// and world editions are often printed in several languages.
  static bool isMultilingualRegion(String region) =>
      const {'eu', 'wor', 'ca', 'asi'}.contains(region.toLowerCase());

  /// Vision recognition language hints for a scan of [region], most likely
  /// first (BCP 47 identifiers Vision understands).
  static List<String> recognitionHints(String? region) {
    switch (region?.toLowerCase()) {
      case 'jp':
        return const ['ja-JP', 'en-US'];
      case 'kr':
        return const ['ko-KR', 'en-US'];
      case 'cn':
        return const ['zh-Hans', 'en-US'];
      case 'tw':
      case 'asi':
        return const ['zh-Hant', 'en-US'];
      case 'ru':
        return const ['ru-RU', 'en-US'];
      case 'fr':
        return const ['fr-FR', 'en-US'];
      case 'de':
        return const ['de-DE', 'en-US'];
      case 'sp':
        return const ['es-ES', 'en-US'];
      case 'it':
        return const ['it-IT', 'en-US'];
      case 'pt':
      case 'br':
        return const ['pt-BR', 'en-US'];
      case 'eu':
        return const ['en-US', 'fr-FR', 'de-DE', 'es-ES', 'it-IT'];
      default:
        return const ['en-US'];
    }
  }
}
