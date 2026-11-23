import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'logger_service.dart';

/// What Nintendo's own eShop catalogues say about a game, in the shape of a
/// ScreenScraper `jeu` (names, synopsis, dates, genre, publisher, players,
/// medias), so the scraper saves and downloads it exactly as a ScreenScraper
/// answer (docs/s2arm-switch2-library.md, Scraping).
///
/// - Europe (`searching.nintendo-europe.com`, the search of nintendo.com/fr-fr)
///   is asked for the program ID read from the game: an exact match, in the
///   scraping language when Europe has it (fr, en, de, it, es, nl, pt), else in
///   English. Title, description, genre, publisher, release date, players; the
///   16:9 (or 2:1) banner as fanart; the PEGI packshot as box when there is one.
/// - Japan (`search.nintendo.jp`) is asked for the game's Japanese title, then
///   its European one, and an item is taken only when its title is the same:
///   screenshots (1920 × 1080, without text), the hero picture when Europe has
///   no banner, the case of Nintendo's own Switch 2 games.
///
/// Only the ID or a title is sent, nothing about the user. Answers are kept for
/// the app's lifetime and requests are spaced by [interval]. The pictures stay
/// on Nintendo's servers until a scrape downloads them; none is bundled.
abstract final class NintendoEshopCatalogue {
  static final _log = LoggerService.instance;

  static const String europeHost = 'searching.nintendo-europe.com';
  static const String japanHost = 'search.nintendo.jp';
  static const String japanImages = 'https://img-eshop.cdn.nintendo.net/i/';

  /// Hosts the scraper downloads these pictures from directly (never through
  /// the ScreenScraper client, which would count them in its quota).
  static const Set<String> pictureHosts = {'www.nintendo.com', 'img-eshop.cdn.nintendo.net'};

  /// Languages of the European catalogue.
  static const Set<String> europeLanguages = {'fr', 'en', 'de', 'it', 'es', 'nl', 'pt'};

  /// Pause between two requests to Nintendo.
  static Duration interval = const Duration(milliseconds: 250);

  @visibleForTesting
  static http.Client? clientOverride;

  static final Map<String, Future<Map<String, dynamic>?>> _answers = {};
  static Future<void> _turn = Future.value();

  @visibleForTesting
  static void clearCache() => _answers.clear();

  /// A program or title ID: 16 hexadecimal digits.
  static final RegExp programIdPattern = RegExp(r'^[0-9a-fA-F]{16}$');

  /// A title ID written in a file name, as `Game [0100000000010000][v0].nsp`.
  static String? programIdInName(String? name) =>
      RegExp(r'\[([0-9a-fA-F]{16})\]').firstMatch(name ?? '')?.group(1)?.toLowerCase();

  /// The game's info, or null when neither catalogue knows it. [switch2]
  /// chooses the platform: the Switch 2 entry of an ID that also has a
  /// Switch one (a "Nintendo Switch 2 Edition"), and the Japanese platform.
  /// [titles] are tried in order on the Japanese catalogue (its own title
  /// first: the game's Japanese title from its control data).
  static Future<Map<String, dynamic>?> gameInfo({
    required String? programId,
    required bool switch2,
    String? language,
    List<String?> titles = const [],
  }) {
    final id = programId?.trim().toLowerCase() ?? '';
    final wanted = [for (final t in titles) if ((t?.trim() ?? '').isNotEmpty) t!.trim()];
    if (!programIdPattern.hasMatch(id) && wanted.isEmpty) return Future.value(null);
    final lang = europeLanguages.contains(language?.toLowerCase()) ? language!.toLowerCase() : 'en';
    final key = '$id|$switch2|$lang|${wanted.join('|')}';
    return _answers[key] ??= _lookUp(key, id, switch2: switch2, language: lang, titles: wanted);
  }

  static Future<Map<String, dynamic>?> _lookUp(
    String key,
    String id, {
    required bool switch2,
    required String language,
    required List<String> titles,
  }) async {
    var failed = false;
    Map<String, dynamic>? europe;
    if (programIdPattern.hasMatch(id)) {
      try {
        europe = await _europe(id, switch2: switch2, language: language);
      } catch (e) {
        failed = true;
        _log.w('Nintendo catalogue (Europe) unavailable: $e');
      }
    }
    final europeTitle = europe?['title']?.toString();
    Map<String, dynamic>? japan;
    for (final title in {...titles, ?europeTitle}) {
      try {
        japan = await _japan(title, switch2: switch2);
      } catch (e) {
        failed = true;
        _log.w('Nintendo catalogue (Japan) unavailable: $e');
        break;
      }
      if (japan != null) break;
    }
    if (europe == null && japan == null) {
      // A failed request is asked again next time; "unknown" is kept.
      if (failed) _answers.remove(key);
      return null;
    }
    return _info(europe, japan, switch2: switch2, language: language);
  }

  // ---------------- Europe ----------------

  static const _europeFields = [
    'title', 'excerpt', 'product_catalog_description_s', 'pretty_game_categories_txt', 'publisher',
    'developer', 'dates_released_dts', 'date_from', 'players_from', 'players_to', 'system_type',
    'image_url', 'image_url_h16x9_s', 'image_url_h2x1_s', 'type',
  ];

  static Future<Map<String, dynamic>?> _europe(String id, {required bool switch2, required String language}) async {
    final uri = Uri.https(europeHost, '/$language/select', {
      'q': '*',
      'fq': 'type:GAME AND application_id_s:$id',
      'wt': 'json',
      'rows': '10',
      'fl': _europeFields.join(','),
    });
    final response = await _get(uri);
    if (response.statusCode != 200) throw _CatalogueError('Europe ${response.statusCode}');
    final docs = (jsonDecode(utf8.decode(response.bodyBytes))['response']?['docs'] as List?)
            ?.whereType<Map<String, dynamic>>()
            .toList() ??
        const <Map<String, dynamic>>[];
    if (docs.isEmpty) return null;
    bool isSwitch2(Map<String, dynamic> doc) =>
        (doc['system_type'] as List?)?.any((t) => t.toString().contains('nintendoswitch2')) ?? false;
    // The Switch 2 entry of a Switch game's ID is its Switch 2 Edition.
    final preferred = docs.where((d) => isSwitch2(d) == switch2);
    return preferred.isNotEmpty ? preferred.first : docs.first;
  }

  // ---------------- Japan ----------------

  static Future<Map<String, dynamic>?> _japan(String title, {required bool switch2}) async {
    final uri = Uri.https(japanHost, '/nintendo_soft/search.json', {
      'q': title,
      'opt_hard[]': switch2 ? '05_BEE' : '1_HAC',
      'limit': '20',
      'page': '1',
    });
    final response = await _get(uri);
    if (response.statusCode != 200) throw _CatalogueError('Japan ${response.statusCode}');
    final items = (jsonDecode(utf8.decode(response.bodyBytes))['result']?['items'] as List?)
            ?.whereType<Map<String, dynamic>>() ??
        const <Map<String, dynamic>>[];
    final wanted = sameTitleKey(title);
    for (final item in items) {
      if (sameTitleKey(item['title']?.toString() ?? '') == wanted) return item;
    }
    return null;
  }

  // ---------------- shape ----------------

  static Future<Map<String, dynamic>> _info(
    Map<String, dynamic>? europe,
    Map<String, dynamic>? japan, {
    required bool switch2,
    required String language,
  }) async {
    String? text(Object? value) {
      final s = value is List ? (value.isEmpty ? null : value.first) : value;
      final t = s?.toString().trim() ?? '';
      return t.isEmpty || t == 'null' ? null : t;
    }

    final names = <Map<String, String>>[
      if (text(europe?['title']) case final t?) {'region': 'wor', 'text': t},
      if (text(japan?['title']) case final t?) {'region': 'jp', 'text': t},
    ];
    final description = text(europe?['product_catalog_description_s']) ?? text(europe?['excerpt']);
    final synopsis = <Map<String, String>>[
      if (description != null) {'langue': language, 'text': description},
      if (text(japan?['text']) case final t?) {'langue': 'ja', 'text': t},
    ];
    final released = text(europe?['dates_released_dts']) ?? text(europe?['date_from']);
    final japanDate = text(japan?['dsdate']) ?? text(japan?['pdate']);
    final dates = <Map<String, String>>[
      if (released != null) {'region': 'eu', 'text': released.split('T').first},
      if (japanDate != null) {'region': 'jp', 'text': japanDate.split(' ').first},
    ];
    final genres = (europe?['pretty_game_categories_txt'] as List?)?.map((g) => g.toString()).toList() ?? const [];
    final publisher = text(europe?['publisher']) ?? text(japan?['maker']);
    final developer = text(europe?['developer']);
    final playersTo = int.tryParse(text(europe?['players_to']) ?? '');
    final playersFrom = int.tryParse(text(europe?['players_from']) ?? '') ?? 1;

    final medias = <Map<String, String>>[];
    // Fanart: the European banner (international logo), else Japan's hero picture.
    final banner = text(europe?['image_url_h16x9_s']) ?? text(europe?['image_url_h2x1_s']);
    if (banner != null) {
      medias.add({'type': 'fanart', 'format': _format(banner), 'region': 'eu', 'url': await largestBanner(banner)});
    }
    final hero = text(japan?['siurl']);
    if (hero != null) {
      medias.add({'type': 'fanart', 'format': 'jpg', 'region': 'jp', 'url': '$japanImages$hero.jpg'});
    }
    // Screenshot: the first of Japan's, never with text.
    final shots = (japan?['sslurl'] as List?)?.map((s) => s.toString()).where((s) => s.isNotEmpty).toList();
    if (shots != null && shots.isNotEmpty) {
      medias.add({'type': 'ss', 'format': 'jpg', 'region': 'wor', 'url': '$japanImages${shots.first}.jpg'});
    }
    // Box: a European packshot (Switch games), the Japanese case of Nintendo's
    // own Switch 2 games.
    final packshot = text(europe?['image_url']);
    if (packshot != null && packshot.contains('/05_packshots/')) {
      medias.add({'type': 'box-2D', 'format': _format(packshot), 'region': 'eu', 'url': packshot});
    }
    final code = text(japan?['icode']);
    if (switch2 && code != null && RegExp(r'^[A-Za-z0-9]{5}$').hasMatch(code)) {
      final url = 'https://www.nintendo.com/jp/games/switch2/${code.toLowerCase()}/products/assets/img/software_img_package.webp';
      if (await _exists(url)) medias.add({'type': 'box-2D', 'format': 'webp', 'region': 'jp', 'url': url});
    }

    return {
      'noms': names,
      'synopsis': synopsis,
      'dates': dates,
      if (genres.isNotEmpty)
        'genres': [
          {
            'noms': [
              {'langue': language, 'text': genres.join(', ')},
            ],
          },
        ],
      if (publisher != null) 'editeur': {'text': publisher},
      if (developer != null) 'developpeur': {'text': developer},
      if (playersTo != null)
        'joueurs': {'text': playersTo > playersFrom ? '$playersFrom-$playersTo' : '$playersTo'},
      'medias': medias,
    };
  }

  static String _format(String url) {
    final ext = url.split('?').first.split('.').last.toLowerCase();
    return const {'jpg', 'jpeg', 'png', 'webp'}.contains(ext) ? (ext == 'jpeg' ? 'jpg' : ext) : 'jpg';
  }

  /// The European pictures come in fixed widths (`…_image500w.jpg`); a
  /// banner is asked at 1600 then 1280 px, the width the catalogue gives when
  /// neither exists.
  static Future<String> largestBanner(String url) async {
    if (!url.contains('image500w')) return url;
    for (final width in const ['1600w', '1280w']) {
      final larger = url.replaceFirst('image500w', 'image$width');
      if (await _exists(larger)) return larger;
    }
    return url;
  }

  // ---------------- titles ----------------

  /// A title reduced to what tells two writings of it apart: letters and
  /// digits in lower case, without accents, trademark signs, punctuation,
  /// a leading or trailing "The" nor a "Nintendo Switch 2 Edition" mention;
  /// roman numerals II to X written in digits.
  static String sameTitleKey(String title) {
    var t = title.toLowerCase();
    t = t.replaceAll(RegExp(r'[™®©]'), '');
    t = _stripAccents(t);
    t = t.replaceAll(RegExp(r'nintendo\s*switch\s*2\s*edition'), ' ');
    t = t.replaceAll(RegExp(r'[^\p{L}\p{N}]+', unicode: true), ' ').trim();
    const romans = {'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'};
    final words = t.split(' ').where((w) => w.isNotEmpty).map((w) => romans[w] ?? w).toList();
    if (words.isNotEmpty && words.first == 'the') words.removeAt(0);
    if (words.isNotEmpty && words.last == 'the') words.removeLast();
    return words.join();
  }

  static String _stripAccents(String s) {
    const from = 'àáâãäåçèéêëìíîïñòóôõöùúûüýÿœæ';
    const to = 'aaaaaaceeeeiiiinooooouuuuyyoa';
    final out = StringBuffer();
    for (final rune in s.runes) {
      final c = String.fromCharCode(rune);
      final i = from.indexOf(c);
      out.write(i < 0 ? c : to[i]);
    }
    return out.toString();
  }

  // ---------------- network ----------------

  static Future<http.Response> _get(Uri uri) async {
    await _wait();
    final client = clientOverride ?? http.Client();
    try {
      return await client.get(uri).timeout(const Duration(seconds: 15));
    } finally {
      if (clientOverride == null) client.close();
    }
  }

  /// A picture from one of [pictureHosts], for the scrape's downloader.
  static Future<http.Response> fetchPicture(Uri uri) async {
    final client = clientOverride ?? http.Client();
    try {
      return await client.get(uri).timeout(const Duration(seconds: 20));
    } finally {
      if (clientOverride == null) client.close();
    }
  }

  static Future<bool> _exists(String url) async {
    await _wait();
    final client = clientOverride ?? http.Client();
    try {
      final response = await client.head(Uri.parse(url)).timeout(const Duration(seconds: 10));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    } finally {
      if (clientOverride == null) client.close();
    }
  }

  static Future<void> _wait() {
    final previous = _turn;
    final mine = previous.then((_) => Future<void>.delayed(interval));
    _turn = mine;
    return previous;
  }
}

class _CatalogueError implements Exception {
  _CatalogueError(this.message);
  final String message;
  @override
  String toString() => message;
}
