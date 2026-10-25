import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' show Size;

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';

/// Kinds of box media fetched for the 3D box, with their ScreenScraper type
/// and NeoStation media folder (`media/<system>/<folder>/<rom>.<ext>`).
enum GameBoxMediaKind {
  front('box-2D', 'box2d'),
  back('box-2D-back', 'box2dback'),
  spine('box-2D-side', 'box2dside'),
  support('support-2D', 'support2d');

  const GameBoxMediaKind(this.screenScraperType, this.folder);
  final String screenScraperType;
  final String folder;

  static GameBoxMediaKind? ofType(String type) {
    for (final k in values) {
      if (k.screenScraperType == type) return k;
    }
    return null;
  }
}

/// Media folders written by the 3D box, for cleanup and storage lists.
abstract final class GameBoxMediaFolders {
  static const back = 'box2dback';
  static const spine = 'box2dside';
  static const support = 'support2d';

  /// Back scans of other editions, one folder per game.
  static const backEditions = 'box2dback-editions';

  /// Per-game JSON manifest of the editions ScreenScraper lists.
  static const manifest = 'boxmeta';

  static const all = [back, spine, support, backEditions, manifest];
}

/// One scan listed by ScreenScraper for a game, without any credential.
///
/// [token] is the `media` argument of `mediaJeu.php` (`box-2D-back(fr)`):
/// with the game and system ids of the manifest it is enough to download
/// the same scan later, credentials being added at request time only.
class GameBoxMediaEntry {
  const GameBoxMediaEntry({
    required this.kind,
    required this.region,
    required this.format,
    required this.token,
    this.md5,
    this.sha1,
    this.crc,
    this.size,
  });

  final GameBoxMediaKind kind;
  final String region;
  final String format;
  final String token;
  final String? md5;
  final String? sha1;
  final String? crc;
  final int? size;

  /// Presumed print language (see [GameBoxRegions.languageOfRegion]).
  String? get language => GameBoxRegions.languageOfRegion(region);

  /// Identity used to avoid downloading the same scan twice: ScreenScraper
  /// often lists one picture under several regions (`wor`, `us`).
  String get identity => (md5?.isNotEmpty ?? false)
      ? 'md5:${md5!.toLowerCase()}'
      : (sha1?.isNotEmpty ?? false)
          ? 'sha1:${sha1!.toLowerCase()}'
          : 'token:$token';

  Map<String, dynamic> toJson() => {
        'type': kind.screenScraperType,
        'region': region,
        'format': format,
        'media': token,
        if (md5 != null) 'md5': md5,
        if (sha1 != null) 'sha1': sha1,
        if (crc != null) 'crc': crc,
        if (size != null) 'size': size,
      };

  static GameBoxMediaEntry? fromJson(Map<String, dynamic> json) {
    final kind = GameBoxMediaKind.ofType(json['type']?.toString() ?? '');
    final token = json['media']?.toString() ?? '';
    if (kind == null || token.isEmpty) return null;
    return GameBoxMediaEntry(
      kind: kind,
      region: json['region']?.toString() ?? '',
      format: _format(json['format']),
      token: token,
      md5: _optional(json['md5']),
      sha1: _optional(json['sha1']),
      crc: _optional(json['crc']),
      size: int.tryParse(json['size']?.toString() ?? ''),
    );
  }

  /// Reads one entry of a `jeuInfos.php` `medias` list. The URL is only used
  /// to extract its `media` token; it is never stored.
  static GameBoxMediaEntry? fromScreenScraper(Map<dynamic, dynamic> media) {
    final kind = GameBoxMediaKind.ofType(media['type']?.toString() ?? '');
    if (kind == null) return null;
    final region = media['region']?.toString() ?? '';
    var token = '';
    final url = media['url']?.toString() ?? '';
    final uri = Uri.tryParse(url);
    if (uri != null) token = uri.queryParameters['media'] ?? '';
    if (token.isEmpty) {
      token = region.isEmpty ? kind.screenScraperType : '${kind.screenScraperType}($region)';
    }
    return GameBoxMediaEntry(
      kind: kind,
      region: region,
      format: _format(media['format']),
      token: token,
      md5: _optional(media['md5']),
      sha1: _optional(media['sha1']),
      crc: _optional(media['crc']),
      size: int.tryParse(media['size']?.toString() ?? ''),
    );
  }

  static String _format(Object? raw) {
    final f = raw?.toString().toLowerCase() ?? '';
    return const {'png', 'jpg', 'jpeg', 'webp'}.contains(f) ? (f == 'jpeg' ? 'jpg' : f) : 'png';
  }

  static String? _optional(Object? raw) {
    final s = raw?.toString().trim() ?? '';
    return s.isEmpty ? null : s;
  }
}

/// How the game was identified when its editions were listed.
enum GameBoxMatch { md5, serial, fileName, title }

/// Record of the editions available for one game (`boxmeta/<rom>.json`).
///
/// It is the offline source of truth of the 3D box: which scans exist, for
/// which regions, which one is on disk for each face, and how the game was
/// identified. It never holds credentials or full URLs.
class GameBoxManifest {
  GameBoxManifest({
    required this.screenScraperSystemId,
    required this.screenScraperGameId,
    required this.matchedBy,
    required this.entries,
    this.gameRegions = const [],
    this.gameRegionSource,
    this.frontRegion,
    this.frontConfirmed = false,
    Map<GameBoxMediaKind, String>? defaults,
    Map<String, String>? backEditionFiles,
    DateTime? fetchedAt,
  })  : defaults = defaults ?? {},
        backEditionFiles = backEditionFiles ?? {},
        fetchedAt = fetchedAt ?? DateTime.now().toUtc();

  static const int version = 1;

  final String screenScraperSystemId;
  final String screenScraperGameId;
  final GameBoxMatch matchedBy;
  final List<GameBoxMediaEntry> entries;

  /// Regions of the user's own copy, when known, and where they come from
  /// (`filename`: No-Intro/Redump tags; `screenscraper`: the ROM record of a
  /// checksum match).
  final List<String> gameRegions;
  final String? gameRegionSource;

  /// Region of the front scan already in the library, confirmed when its
  /// MD5 equals one listed by ScreenScraper for this game.
  final String? frontRegion;
  final bool frontConfirmed;

  /// Identity ([GameBoxMediaEntry.identity]) of the scan saved as the default
  /// face of each kind.
  final Map<GameBoxMediaKind, String> defaults;

  /// Back scans of other editions already downloaded: identity → file name
  /// in the game's `box2dback-editions` folder.
  final Map<String, String> backEditionFiles;
  final DateTime fetchedAt;

  List<GameBoxMediaEntry> of(GameBoxMediaKind kind) =>
      entries.where((e) => e.kind == kind).toList();

  GameBoxMediaEntry? defaultEntry(GameBoxMediaKind kind) {
    final id = defaults[kind];
    if (id == null) return null;
    for (final e in of(kind)) {
      if (e.identity == id) return e;
    }
    return null;
  }

  /// Distinct back scans (one per picture), with every region that lists it.
  List<GameBoxBackEdition> backEditions() {
    final byId = <String, GameBoxBackEdition>{};
    for (final e in of(GameBoxMediaKind.back)) {
      final existing = byId[e.identity];
      if (existing == null) {
        byId[e.identity] = GameBoxBackEdition(entry: e, regions: [e.region]);
      } else if (!existing.regions.contains(e.region)) {
        existing.regions.add(e.region);
      }
    }
    return byId.values.toList();
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'screenscraper': {'systemId': screenScraperSystemId, 'gameId': screenScraperGameId},
        'matchedBy': matchedBy.name,
        'gameRegions': gameRegions,
        if (gameRegionSource != null) 'gameRegionSource': gameRegionSource,
        if (frontRegion != null) 'frontRegion': frontRegion,
        'frontConfirmed': frontConfirmed,
        'defaults': {for (final e in defaults.entries) e.key.name: e.value},
        'backEditionFiles': backEditionFiles,
        'fetchedAt': fetchedAt.toIso8601String(),
        'media': [for (final e in entries) e.toJson()],
      };

  static GameBoxManifest? fromJson(Map<String, dynamic> json) {
    if (json['version'] != version) return null;
    final ss = json['screenscraper'];
    if (ss is! Map) return null;
    final entries = <GameBoxMediaEntry>[];
    for (final raw in (json['media'] as List? ?? const [])) {
      if (raw is Map) {
        final e = GameBoxMediaEntry.fromJson(Map<String, dynamic>.from(raw));
        if (e != null) entries.add(e);
      }
    }
    final defaults = <GameBoxMediaKind, String>{};
    final rawDefaults = json['defaults'];
    if (rawDefaults is Map) {
      for (final k in GameBoxMediaKind.values) {
        final v = rawDefaults[k.name];
        if (v is String) defaults[k] = v;
      }
    }
    final files = <String, String>{};
    final rawFiles = json['backEditionFiles'];
    if (rawFiles is Map) {
      rawFiles.forEach((k, v) {
        final name = v.toString();
        // Only plain file names inside the game's own folder.
        if (name == p.basename(name) && !name.startsWith('.')) files[k.toString()] = name;
      });
    }
    return GameBoxManifest(
      screenScraperSystemId: ss['systemId']?.toString() ?? '',
      screenScraperGameId: ss['gameId']?.toString() ?? '',
      matchedBy: GameBoxMatch.values.firstWhere(
        (m) => m.name == json['matchedBy'],
        orElse: () => GameBoxMatch.title,
      ),
      entries: entries,
      gameRegions: [for (final r in (json['gameRegions'] as List? ?? const [])) r.toString()],
      gameRegionSource: json['gameRegionSource']?.toString(),
      frontRegion: json['frontRegion']?.toString(),
      frontConfirmed: json['frontConfirmed'] == true,
      defaults: defaults,
      backEditionFiles: files,
      fetchedAt: DateTime.tryParse(json['fetchedAt']?.toString() ?? ''),
    );
  }
}

/// One distinct back scan and the regions that list it.
class GameBoxBackEdition {
  GameBoxBackEdition({required this.entry, required this.regions});
  final GameBoxMediaEntry entry;
  final List<String> regions;

  /// Languages presumed from all of its regions.
  Set<String> get languages => {
        for (final r in regions)
          if (GameBoxRegions.languageOfRegion(r) != null) GameBoxRegions.languageOfRegion(r)!,
      };
}

/// Choice of default scans, kept pure for tests.
class GameBoxMediaSelection {
  GameBoxMediaSelection._();

  /// Best scan of [kind] for a copy of [gameRegions], then the region of the
  /// front scan already shown, then the user's region priority.
  static GameBoxMediaEntry? choose(
    List<GameBoxMediaEntry> entries,
    GameBoxMediaKind kind, {
    List<String> gameRegions = const [],
    String? frontRegion,
    Map<String, int> regionPriority = const {},
  }) {
    final candidates = entries.where((e) => e.kind == kind).toList();
    if (candidates.isEmpty) return null;
    int score(GameBoxMediaEntry e) {
      var s = regionPriority[e.region] ?? 5;
      final i = gameRegions.indexOf(e.region);
      if (i >= 0) s += 1000 - i;
      if (frontRegion != null && e.region == frontRegion) s += 500;
      return s;
    }
    candidates.sort((a, b) => score(b).compareTo(score(a)));
    return candidates.first;
  }

  /// Back scan to read in [language]: one whose region presumes that
  /// language, preferring the default edition, then the copy's own regions.
  static GameBoxBackEdition? backForLanguage(
    GameBoxManifest manifest,
    String language, {
    List<String> gameRegions = const [],
  }) {
    final editions = manifest.backEditions().where((e) => e.languages.contains(language)).toList();
    if (editions.isEmpty) return null;
    final defaultId = manifest.defaults[GameBoxMediaKind.back];
    int score(GameBoxBackEdition e) {
      var s = 0;
      if (e.entry.identity == defaultId) s += 100;
      if (e.regions.any(gameRegions.contains)) s += 50;
      // A region that names the language alone (fr) over a multilingual one.
      if (e.regions.any((r) => !GameBoxRegions.isMultilingualRegion(r))) s += 10;
      return s;
    }
    editions.sort((a, b) => score(b).compareTo(score(a)));
    return editions.first;
  }
}

/// The files of a game's box as they are on disk.
class GameBoxLocalMedia {
  const GameBoxLocalMedia({
    this.front,
    this.back,
    this.spine,
    this.support,
    this.manifest,
    this.manifestPath,
    this.backEditionsDir,
  });

  final String? front;
  final String? back;
  final String? spine;
  final String? support;
  final GameBoxManifest? manifest;
  final String? manifestPath;
  final String? backEditionsDir;

  bool get hasBack => back != null;

  /// Path of an already downloaded back scan of another edition.
  String? backEditionFile(GameBoxMediaEntry entry) {
    final m = manifest;
    final dir = backEditionsDir;
    if (m == null || dir == null) return null;
    if (m.defaults[GameBoxMediaKind.back] == entry.identity && back != null) return back;
    final name = m.backEditionFiles[entry.identity];
    if (name == null) return null;
    final f = File(p.join(dir, name));
    return f.existsSync() ? f.path : null;
  }
}

/// Reads the box media of a game from the media folders.
class GameBoxMediaStore {
  GameBoxMediaStore(this.fileProvider);
  final FileProvider fileProvider;

  String _existing(GameModel game, String system, String folder) {
    final path = game.getImagePath(system, folder, fileProvider);
    return File(path).existsSync() ? path : '';
  }

  /// Canonical path of [folder] for [game] with [extension]: the reader's
  /// own lookup (see [GameModel.getImagePath]) so writer and reader agree.
  String canonicalPath(GameModel game, String system, String folder, String extension) {
    final png = game.getImagePath(system, folder, fileProvider);
    return '${p.withoutExtension(png)}.$extension';
  }

  String manifestPath(GameModel game, String system) =>
      canonicalPath(game, system, GameBoxMediaFolders.manifest, 'json');

  String backEditionsDir(GameModel game, String system) {
    final key = p.basenameWithoutExtension(manifestPath(game, system));
    return p.join(p.dirname(p.dirname(manifestPath(game, system))), GameBoxMediaFolders.backEditions, key);
  }

  GameBoxLocalMedia read(GameModel game, String system) {
    String? orNull(String s) => s.isEmpty ? null : s;
    final mPath = manifestPath(game, system);
    GameBoxManifest? manifest;
    try {
      final f = File(mPath);
      if (f.existsSync()) {
        final json = jsonDecode(f.readAsStringSync());
        if (json is Map<String, dynamic>) manifest = GameBoxManifest.fromJson(json);
      }
    } catch (_) {
      manifest = null; // Unreadable manifest: the faces stay usable.
    }
    return GameBoxLocalMedia(
      front: orNull(_existing(game, system, GameBoxMediaKind.front.folder)),
      back: orNull(_existing(game, system, GameBoxMediaFolders.back)),
      spine: orNull(_existing(game, system, GameBoxMediaFolders.spine)),
      support: orNull(_existing(game, system, GameBoxMediaFolders.support)),
      manifest: manifest,
      manifestPath: mPath,
      backEditionsDir: backEditionsDir(game, system),
    );
  }

  /// Writes [manifest] atomically.
  Future<void> writeManifest(GameModel game, String system, GameBoxManifest manifest) async {
    final path = manifestPath(game, system);
    final file = File(path);
    await file.parent.create(recursive: true);
    final temp = File('$path.part');
    await temp.writeAsString(const JsonEncoder.withIndent(' ').convert(manifest.toJson()), flush: true);
    await temp.rename(path);
  }
}

/// Pixel size of a PNG or JPEG from its header (no decoding).
class GameBoxImageSize {
  GameBoxImageSize._();

  static final Map<String, Size?> _cache = {};

  static void evict(String path) => _cache.remove(path);

  static Size? of(String path) {
    if (_cache.containsKey(path)) return _cache[path];
    Size? result;
    try {
      final raf = File(path).openSync();
      try {
        final len = raf.lengthSync().clamp(0, 262144).toInt();
        final buf = Uint8List(len);
        raf.readIntoSync(buf);
        result = fromBytes(buf);
      } finally {
        raf.closeSync();
      }
    } catch (_) {
      result = null;
    }
    _cache[path] = result;
    return result;
  }

  static Size? fromBytes(Uint8List b) {
    if (b.length > 24 && b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47) {
      final w = (b[16] << 24) | (b[17] << 16) | (b[18] << 8) | b[19];
      final h = (b[20] << 24) | (b[21] << 16) | (b[22] << 8) | b[23];
      return (w > 0 && h > 0 && w < 30000 && h < 30000) ? Size(w.toDouble(), h.toDouble()) : null;
    }
    if (b.length > 4 && b[0] == 0xFF && b[1] == 0xD8) {
      var i = 2;
      while (i + 9 < b.length) {
        if (b[i] != 0xFF) {
          i++;
          continue;
        }
        final marker = b[i + 1];
        if (marker >= 0xC0 && marker <= 0xCF && marker != 0xC4 && marker != 0xC8 && marker != 0xCC) {
          final h = (b[i + 5] << 8) | b[i + 6];
          final w = (b[i + 7] << 8) | b[i + 8];
          return (w > 0 && h > 0) ? Size(w.toDouble(), h.toDouble()) : null;
        }
        i += ((b[i + 2] << 8) | b[i + 3]) + 2;
      }
    }
    return null;
  }
}

/// MD5 of a small local file (scans), hex.
String? gameBoxFileMd5(String path) {
  try {
    final f = File(path);
    if (!f.existsSync() || f.lengthSync() > 64 * 1024 * 1024) return null;
    return md5.convert(f.readAsBytesSync()).toString();
  } catch (_) {
    return null;
  }
}
