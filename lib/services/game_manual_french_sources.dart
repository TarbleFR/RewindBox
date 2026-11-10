import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/game_model.dart';
import 'game_box/game_box_rom_id.dart';
import 'game_box/game_box_sources.dart';
import 'logger_service.dart';

/// A French manual found outside ScreenScraper.
@immutable
class GameManualFound {
  const GameManualFound({
    required this.url,
    required this.source,
    required this.title,
    this.byProduct = false,
    this.bytes,
  });

  /// Address of the PDF.
  final String url;

  /// `archive.org` or `nintendo.eu`.
  final String source;

  /// Title of the item at its source.
  final String title;

  /// Found by the product code of the player's edition (not by title).
  final bool byProduct;

  /// The PDF itself when finding it already downloaded it.
  final Uint8List? bytes;
}

/// French manuals from other sources than ScreenScraper (docs/game-box-3d.md
/// § 26), used when the scraping language is French and the game has no
/// manual yet:
///
/// 1. the Internet Archive's manual collections, by the product code of the
///    player's edition in the item's title (`IM-DOL-GALP-FRA` for Super
///    Smash Bros. Melee, `AGB-AMKP-NEU5`…), French items only;
/// 2. Nintendo Europe's own French PDF of a DS game;
/// 3. the Internet Archive by exact title, when the item names the same
///    platform.
///
/// Every download must be a PDF (`%PDF`), at most [maxBytes]; nothing is
/// written otherwise, and no manual already on the device is replaced.
class GameManualFrenchSources {
  GameManualFrenchSources._();

  static const String archiveSearch = 'https://archive.org/advancedsearch.php';
  static const String archiveMetadata = 'https://archive.org/metadata';
  static const String archiveDownload = 'https://archive.org/download';
  static const String nintendoDs =
      'https://www.nintendo.com/eu/media/downloads/games_8/emanuals/nintendo_ds_21';

  static const int maxBytes = 150 * 1024 * 1024;

  /// Replaces the network in tests: answers [url] with its body (null: 404).
  @visibleForTesting
  static Future<Uint8List?> Function(String url)? debugGet;

  /// Platform prefix of product codes in manual titles and names a source
  /// gives a platform, by NeoStation system.
  static const Map<String, (String?, List<String>)> platforms = {
    'gc': ('DOL', ['gamecube', 'game cube']),
    'triforce': ('DOL', ['gamecube']),
    'wii': ('RVL', [' wii ', '(wii)', 'nintendo wii']),
    'wiiu': ('WUP', ['wii u']),
    'ds': ('NTR', ['nintendo ds', ' nds ']),
    '3ds': ('CTR', ['3ds']),
    'gba': ('AGB', ['game boy advance', 'gba']),
    'gb': ('DMG', ['game boy']),
    'gbc': ('CGB', ['game boy color']),
    'n64': ('NUS', ['nintendo 64', 'n64']),
    'snes': ('SNSP', ['super nintendo', 'snes']),
    'nes': ('NES', [' nes ', '(nes)', 'nintendo entertainment system']),
    'switch': ('HAC', ['switch']),
    'ps1': (null, ['playstation', 'psx', 'ps1']),
    'ps2': (null, ['playstation 2', 'ps2']),
    'ps3': (null, ['playstation 3', 'ps3']),
    'psp': (null, ['psp']),
    'md': (null, ['mega drive', 'megadrive', 'genesis']),
    'sms': (null, ['master system']),
    'gg': (null, ['game gear']),
    'sat': (null, ['saturn']),
    'dc': (null, ['dreamcast']),
  };

  /// Names of neighbour platforms that contain a platform's own name
  /// ("PlayStation 2" contains "PlayStation"): an item naming them is not
  /// taken by title for that platform.
  static const Map<String, List<String>> neighbours = {
    'ps1': ['playstation 2', 'playstation 3', 'playstation portable', 'ps2', 'ps3', 'psp', 'vita'],
    'ps2': ['playstation 3', 'ps3'],
    'gb': ['game boy advance', 'game boy color', 'gba', 'gbc'],
    'gbc': ['game boy advance', 'gba'],
    'wii': ['wii u'],
    'ds': ['3ds'],
    'nes': ['snes', 'super nes', 'super nintendo'],
  };

  /// Product codes of the player's copy, as manual titles write them.
  static Future<List<String>> productCodes(GameModel game, String systemId) async {
    final platform = switch (systemId) {
      'gc' || 'triforce' || 'wii' => 'wii',
      'wiiu' || 'ds' || '3ds' || 'gba' => systemId,
      _ => null,
    };
    final codes = <String>[];
    if (platform != null) {
      final id = await GameBoxRomId.forGame(game, platform);
      // A disc id's first four characters are its product code.
      if (id != null) codes.add(id.length > 4 ? id.substring(0, 4) : id);
    }
    final serial = game.titleId?.trim().toUpperCase();
    if (serial != null && GameTdb.ps3Id.hasMatch(serial)) {
      codes.add(serial);
      codes.add('${serial.substring(0, 4)}-${serial.substring(4)}');
    }
    return codes;
  }

  /// The best French manual for [game] on [systemId], or null.
  static Future<GameManualFound?> find(GameModel game, String systemId, {bool byTitle = true}) async {
    final codes = await productCodes(game, systemId);
    for (final code in codes) {
      final found = await _archive(game, systemId, code: code);
      if (found != null) return found;
    }
    if (systemId == 'ds') {
      final official = await _nintendoDs(game);
      if (official != null) return official;
    }
    if (!byTitle) return null;
    return _archive(game, systemId);
  }

  /// Finds and downloads a French manual into [target] when there is none.
  /// Returns what was written, or null.
  static Future<GameManualFound?> fill(GameModel game, String systemId, String target, {bool byTitle = true}) async {
    try {
      if (await File(target).exists()) return null;
      final found = await find(game, systemId, byTitle: byTitle);
      if (found == null) return null;
      return await download(found, target) ? found : null;
    } catch (e) {
      LoggerService.instance.w('Manual (French sources) for ${game.romname} failed: $e');
      return null;
    }
  }

  static Future<Uint8List?> _get(String url, {int? limit}) async {
    final debug = debugGet;
    if (debug != null) return debug(url);
    final client = http.Client();
    try {
      final request = http.Request('GET', Uri.parse(url))..headers['User-Agent'] = 'RewindBox';
      final response = await client.send(request).timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) return null;
      final out = BytesBuilder(copy: false);
      await for (final chunk in response.stream.timeout(const Duration(seconds: 60))) {
        out.add(chunk);
        if (out.length > (limit ?? maxBytes)) return null;
      }
      return out.takeBytes();
    } finally {
      client.close();
    }
  }

  /// Words of a manual or game title, for exact comparison.
  static String _bare(String title) {
    // The game's name is what comes before the first " - ", "[" or "(".
    var t = title;
    for (final cut in [' - ', '[', '(']) {
      final i = t.indexOf(cut);
      if (i > 0) t = t.substring(0, i);
    }
    return GameTdb.normalizeTitle(t);
  }

  static bool _french(Object? language) {
    final values = language is List ? language.map((e) => '$e') : [if (language != null) '$language'];
    return values.any((l) => const {'fre', 'fra', 'fr', 'french', 'français', 'francais'}.contains(l.toLowerCase()));
  }

  /// An Internet Archive item: by [code] when given, else by exact title.
  static Future<GameManualFound?> _archive(GameModel game, String systemId, {String? code}) async {
    final (prefix, names) = platforms[systemId] ?? (null, const <String>[]);
    if (code == null && names.isEmpty) return null;
    final title = game.name.trim().isNotEmpty ? game.name : game.realname;
    final words = _bare(title);
    if (code == null && words.isEmpty) return null;
    final what = code != null ? 'title:("$code")' : 'title:("${words.replaceAll('"', '')}")';
    final query = 'collection:(consolemanuals OR gamemanuals OR manuals) AND mediatype:texts AND '
        'language:(fre OR fra OR French OR fr) AND $what';
    final url = Uri.parse(archiveSearch).replace(queryParameters: {
      'q': query,
      'fl[]': ['identifier', 'title', 'language', 'subject', 'collection'],
      'rows': '25',
      'output': 'json',
    }).toString();
    final body = await _get(url, limit: 2 * 1024 * 1024);
    if (body == null) return null;
    final json = jsonDecode(utf8.decode(body, allowMalformed: true));
    final docs = (json is Map ? json['response'] : null) is Map ? json['response']['docs'] : null;
    if (docs is! List) return null;
    for (final d in docs) {
      if (d is! Map || !_french(d['language'])) continue;
      final itemTitle = d['title']?.toString() ?? '';
      final about = ' ${[itemTitle, d['subject'], d['collection']].join(' ').toLowerCase()} ';
      if (code != null) {
        // The code itself, with the platform's prefix when it has one
        // (DOL-GALP, AGB-AMKP, NTR-AMCP, CTR-P-AMKP).
        final token = RegExp('(^|[^A-Z0-9])${RegExp.escape(code)}([^A-Z0-9]|\$)');
        if (!token.hasMatch(itemTitle.toUpperCase())) continue;
        if (prefix != null && !itemTitle.toUpperCase().contains(prefix) && !names.any(about.contains)) continue;
      } else {
        if (_bare(itemTitle) != words) continue;
        if (!names.any(about.contains) && !(prefix != null && itemTitle.toUpperCase().contains('$prefix-'))) continue;
        if ((neighbours[systemId] ?? const []).any(about.contains)) continue;
      }
      final id = d['identifier']?.toString();
      if (id == null || id.isEmpty) continue;
      final pdf = await _archivePdf(id);
      if (pdf == null) continue;
      return GameManualFound(url: pdf, source: 'archive.org', title: itemTitle, byProduct: code != null);
    }
    return null;
  }

  /// Largest original scan taken as it is; above it, the archive's
  /// compressed copy (`…_text.pdf`, with its text layer) is preferred.
  static const int originalLimit = 60 * 1024 * 1024;

  /// The PDF of an Internet Archive item: the original scan when it is of a
  /// reasonable size, else the archive's compressed copy of it.
  static Future<String?> _archivePdf(String identifier) async {
    final body = await _get('$archiveMetadata/${Uri.encodeComponent(identifier)}', limit: 4 * 1024 * 1024);
    if (body == null) return null;
    final json = jsonDecode(utf8.decode(body, allowMalformed: true));
    final files = json is Map ? json['files'] : null;
    if (files is! List) return null;
    String? original, compressed, largeOriginal;
    for (final f in files) {
      if (f is! Map) continue;
      final name = f['name']?.toString() ?? '';
      final lower = name.toLowerCase();
      if (!lower.endsWith('.pdf')) continue;
      final size = int.tryParse(f['size']?.toString() ?? '') ?? 0;
      if (size <= 0 || size > maxBytes) continue;
      if (lower.endsWith('_text.pdf')) {
        compressed ??= name;
      } else if (f['source'] == 'original') {
        if (size <= originalLimit) {
          original ??= name;
        } else {
          largeOriginal ??= name;
        }
      }
    }
    final chosen = original ?? compressed ?? largeOriginal;
    if (chosen == null) return null;
    return '$archiveDownload/${Uri.encodeComponent(identifier)}/${Uri.encodeComponent(chosen)}';
  }

  /// Nintendo Europe's French PDF of a DS game, named after its title
  /// (`Manual_NintendoDS_MarioKartDS_FR.pdf`). The server answers an
  /// unknown name with a page, not an error: only a PDF counts.
  static Future<GameManualFound?> _nintendoDs(GameModel game) async {
    final name = nintendoDsName(game.name.trim().isNotEmpty ? game.name : game.realname);
    if (name == null) return null;
    final url = '$nintendoDs/Manual_NintendoDS_${name}_FR.pdf';
    final head = await _get(url, limit: maxBytes);
    if (head == null || !isPdf(head)) return null;
    return GameManualFound(url: url, source: 'nintendo.eu', title: game.name, bytes: head);
  }

  /// The title as Nintendo Europe writes it in its manual names: each word
  /// capitalised, without spaces or punctuation (`MarioKartDS`).
  static String? nintendoDsName(String title) {
    var t = title;
    for (final cut in ['[', '(']) {
      final i = t.indexOf(cut);
      if (i > 0) t = t.substring(0, i);
    }
    t = t.replaceAll(RegExp(r'[™®©]'), '').replaceAll('&', ' and ');
    final words = t.split(RegExp(r"[^A-Za-z0-9]+")).where((w) => w.isNotEmpty);
    final name = words.map((w) => w[0].toUpperCase() + w.substring(1)).join();
    return name.isEmpty ? null : name;
  }

  static bool isPdf(Uint8List b) => b.length > 4 && b[0] == 0x25 && b[1] == 0x50 && b[2] == 0x44 && b[3] == 0x46;

  /// Downloads [found] to [target] when it is a PDF, atomically.
  static Future<bool> download(GameManualFound found, String target) async {
    final bytes = found.bytes ?? await _get(found.url);
    if (bytes == null || !isPdf(bytes)) return false;
    final file = File(target);
    await file.parent.create(recursive: true);
    final temp = File('$target.part');
    await temp.writeAsBytes(bytes, flush: true);
    await temp.rename(target);
    LoggerService.instance.i('Manual (French) for ${found.title} from ${found.source}${found.byProduct ? ' by product code' : ''}.');
    return true;
  }
}
