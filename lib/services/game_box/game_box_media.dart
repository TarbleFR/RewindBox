import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' show Color, Size;

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
  support('support-2D', 'support2d'),

  /// The whole cover sheet laid flat (back | spine | front), kept as the
  /// original from which faces are cut (GameTDB `coverfull`, ScreenScraper
  /// `box-texture` when its layout is recognised).
  full('box-texture', 'box2dfull');

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

  /// Full cover sheets (back | spine | front), kept as downloaded.
  static const full = 'box2dfull';

  /// Back scans of other editions, one folder per game.
  static const backEditions = 'box2dback-editions';

  /// Per-game JSON manifest of the editions ScreenScraper lists.
  static const manifest = 'boxmeta';

  static const all = [back, spine, support, full, backEditions, manifest];
}

/// Where one face file on disk comes from (docs/game-box-3d.md § 14).
///
/// Written by the faces search for every file it adopts, and by a manual
/// import. A face whose record is [manual] is never replaced automatically:
/// only an explicit choice of the player replaces it.
class GameBoxFaceRecord {
  GameBoxFaceRecord({
    required this.provider,
    required this.type,
    this.region,
    this.language,
    this.edition,
    this.productId,
    this.sourceIdentity,
    this.width,
    this.height,
    this.transforms = const [],
    this.md5,
    this.bytes,
    this.manual = false,
    this.note,
    this.attribution,
    DateTime? fetchedAt,
  }) : fetchedAt = fetchedAt ?? DateTime.now().toUtc();

  /// `screenscraper`, `gametdb`, `mobygames`, `manual`, `rpcs3`, `melonx`.
  final String provider;

  /// Provider media type, prefixed (`screenscraper:box-2D-back`,
  /// `gametdb:coverfullHQ`, `manual:import`…).
  final String type;

  /// Region or language code of the scan at its provider (`eu`, `fr`, `EN`).
  final String? region;
  final String? language;

  /// Edition label when known (a "Deluxe Edition" sheet, a coloured case).
  final String? edition;

  /// Product code of the scanned edition when known (PS3 serial, Switch
  /// product code).
  final String? productId;

  /// Identity of the scan at its provider (MD5 or URL path), never a URL
  /// with credentials.
  final String? sourceIdentity;

  /// Native pixel size of the downloaded original.
  final int? width;
  final int? height;

  /// Changes made to the original (`crop:front 0.5249,0,0.4751,1 of …`).
  final List<String> transforms;

  /// MD5 and length of the file saved on disk: a record whose length no
  /// longer matches the file describes a file replaced since.
  final String? md5;
  final int? bytes;
  final bool manual;

  /// Free note of a manual import (for example "The Cover Project — Retail").
  final String? note;

  /// Credit shown with the scan (provider name and site).
  final String? attribution;
  final DateTime fetchedAt;

  Map<String, dynamic> toJson() => {
        'provider': provider,
        'type': type,
        if (region != null) 'region': region,
        if (language != null) 'language': language,
        if (edition != null) 'edition': edition,
        if (productId != null) 'productId': productId,
        if (sourceIdentity != null) 'sourceIdentity': sourceIdentity,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
        if (transforms.isNotEmpty) 'transforms': transforms,
        if (md5 != null) 'md5': md5,
        if (bytes != null) 'bytes': bytes,
        if (manual) 'manual': true,
        if (note != null) 'note': note,
        if (attribution != null) 'attribution': attribution,
        'fetchedAt': fetchedAt.toIso8601String(),
      };

  static GameBoxFaceRecord? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final provider = raw['provider']?.toString() ?? '';
    final type = raw['type']?.toString() ?? '';
    if (provider.isEmpty || type.isEmpty) return null;
    String? s(String k) {
      final v = raw[k]?.toString().trim() ?? '';
      return v.isEmpty ? null : v;
    }
    return GameBoxFaceRecord(
      provider: provider,
      type: type,
      region: s('region'),
      language: s('language'),
      edition: s('edition'),
      productId: s('productId'),
      sourceIdentity: s('sourceIdentity'),
      width: int.tryParse(raw['width']?.toString() ?? ''),
      height: int.tryParse(raw['height']?.toString() ?? ''),
      transforms: [for (final t in (raw['transforms'] as List? ?? const [])) t.toString()],
      md5: s('md5'),
      bytes: int.tryParse(raw['bytes']?.toString() ?? ''),
      manual: raw['manual'] == true,
      note: s('note'),
      attribution: s('attribution'),
      fetchedAt: DateTime.tryParse(raw['fetchedAt']?.toString() ?? ''),
    );
  }
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

/// A case variant identified for the game's edition by a source that lists
/// it for this product code (GameTDB `case color`), never guessed.
class GameBoxIdentifiedCase {
  const GameBoxIdentifiedCase({required this.color, required this.source});
  final Color color;
  final String source;

  Map<String, dynamic> toJson() => {
        'color': (color.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0'),
        'source': source,
      };

  static GameBoxIdentifiedCase? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final hex = raw['color']?.toString() ?? '';
    final source = raw['source']?.toString() ?? '';
    final value = int.tryParse(hex, radix: 16);
    if (value == null || hex.length != 6 || source.isEmpty) return null;
    return GameBoxIdentifiedCase(color: Color(0xFF000000 | value), source: source);
  }
}

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
    Map<GameBoxMediaKind, GameBoxFaceRecord>? faces,
    Set<String>? rejected,
    this.identifiedCase,
    DateTime? fetchedAt,
  })  : defaults = defaults ?? {},
        backEditionFiles = backEditionFiles ?? {},
        faces = faces ?? {},
        rejected = rejected ?? {},
        fetchedAt = fetchedAt ?? DateTime.now().toUtc();

  /// Written version. Version 1 manifests (no face records) are still read.
  static const int version = 2;
  static const Set<int> readable = {1, 2};

  /// Where each face file on disk comes from (version 2).
  final Map<GameBoxMediaKind, GameBoxFaceRecord> faces;

  /// Scans refused after download (uniform, empty or unreadable picture),
  /// by provider identity: never adopted again (docs/game-box-3d.md § 15).
  final Set<String> rejected;

  /// Case variant of the identified edition, when a source lists one.
  final GameBoxIdentifiedCase? identifiedCase;

  /// The same manifest with other face records, rejections or defaults.
  GameBoxManifest copyWith({
    Map<GameBoxMediaKind, GameBoxFaceRecord>? faces,
    Set<String>? rejected,
    Map<GameBoxMediaKind, String>? defaults,
    Map<String, String>? backEditionFiles,
    List<GameBoxMediaEntry>? entries,
    String? screenScraperSystemId,
    String? screenScraperGameId,
    GameBoxMatch? matchedBy,
    List<String>? gameRegions,
    String? gameRegionSource,
    GameBoxIdentifiedCase? identifiedCase,
  }) =>
      GameBoxManifest(
        screenScraperSystemId: screenScraperSystemId ?? this.screenScraperSystemId,
        screenScraperGameId: screenScraperGameId ?? this.screenScraperGameId,
        matchedBy: matchedBy ?? this.matchedBy,
        entries: entries ?? this.entries,
        gameRegions: gameRegions ?? this.gameRegions,
        gameRegionSource: gameRegionSource ?? this.gameRegionSource,
        frontRegion: frontRegion,
        frontConfirmed: frontConfirmed,
        defaults: defaults ?? Map.of(this.defaults),
        backEditionFiles: backEditionFiles ?? Map.of(this.backEditionFiles),
        faces: faces ?? Map.of(this.faces),
        rejected: rejected ?? Set.of(this.rejected),
        identifiedCase: identifiedCase ?? this.identifiedCase,
        fetchedAt: fetchedAt,
      );

  /// An empty manifest for a game known only locally (manual import,
  /// GameTDB) until ScreenScraper identifies it.
  static GameBoxManifest local() => GameBoxManifest(
        screenScraperSystemId: '',
        screenScraperGameId: '',
        matchedBy: GameBoxMatch.title,
        entries: const [],
      );

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
        if (faces.isNotEmpty) 'faces': {for (final e in faces.entries) e.key.name: e.value.toJson()},
        if (rejected.isNotEmpty) 'rejected': rejected.toList()..sort(),
        if (identifiedCase != null) 'identifiedCase': identifiedCase!.toJson(),
        'fetchedAt': fetchedAt.toIso8601String(),
        'media': [for (final e in entries) e.toJson()],
      };

  static GameBoxManifest? fromJson(Map<String, dynamic> json) {
    if (!readable.contains(json['version'])) return null;
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
    final faces = <GameBoxMediaKind, GameBoxFaceRecord>{};
    final rawFaces = json['faces'];
    if (rawFaces is Map) {
      for (final k in GameBoxMediaKind.values) {
        final record = GameBoxFaceRecord.fromJson(rawFaces[k.name]);
        if (record != null) faces[k] = record;
      }
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
      faces: faces,
      rejected: {for (final r in (json['rejected'] as List? ?? const [])) r.toString()},
      identifiedCase: GameBoxIdentifiedCase.fromJson(json['identifiedCase']),
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
    this.full,
    this.manifest,
    this.manifestPath,
    this.backEditionsDir,
  });

  final String? front;
  final String? back;
  final String? spine;
  final String? support;

  /// The full cover sheet kept as downloaded, when one was fetched.
  final String? full;
  final GameBoxManifest? manifest;
  final String? manifestPath;
  final String? backEditionsDir;

  bool get hasBack => back != null;

  /// Path of the file of [kind] (null when missing).
  String? pathOf(GameBoxMediaKind kind) => switch (kind) {
        GameBoxMediaKind.front => front,
        GameBoxMediaKind.back => back,
        GameBoxMediaKind.spine => spine,
        GameBoxMediaKind.support => support,
        GameBoxMediaKind.full => full,
      };

  /// Provenance of the file of [kind], when the faces search or a manual
  /// import recorded it and the file is still the one recorded (same
  /// length; a file replaced by another tool loses its record).
  GameBoxFaceRecord? recordOf(GameBoxMediaKind kind) {
    final record = manifest?.faces[kind];
    final path = pathOf(kind);
    if (record == null || path == null) return null;
    final expected = record.bytes;
    if (expected == null) return record;
    try {
      return File(path).lengthSync() == expected ? record : null;
    } catch (_) {
      return null;
    }
  }

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
      full: orNull(_existing(game, system, GameBoxMediaFolders.full)),
      manifest: manifest,
      manifestPath: mPath,
      backEditionsDir: backEditionsDir(game, system),
    );
  }

  /// Records that the player chose the file of [kind] by hand (Game Settings
  /// › Scraping › Media): the faces search never replaces it automatically
  /// (docs/game-box-3d.md § 14).
  Future<void> recordManualFace(GameModel game, String system, GameBoxMediaKind kind, String path) async {
    final file = File(path);
    if (!await file.exists()) return;
    final bytes = await file.readAsBytes();
    final size = GameBoxImageSize.fromBytes(bytes);
    final current = read(game, system).manifest ??
        GameBoxManifest(
          screenScraperSystemId: '',
          screenScraperGameId: '',
          matchedBy: GameBoxMatch.title,
          entries: const [],
        );
    final faces = Map.of(current.faces)
      ..[kind] = GameBoxFaceRecord(
        provider: 'manual',
        type: 'manual:settings',
        width: size?.width.round(),
        height: size?.height.round(),
        md5: md5.convert(bytes).toString(),
        bytes: bytes.length,
        manual: true,
      );
    await writeManifest(game, system, current.copyWith(faces: faces));
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

/// Pixel size of an image from its header, without decoding it: PNG, JPEG,
/// WebP (lossy VP8, lossless VP8L, extended VP8X), GIF and BMP — the formats
/// the scraper accepts (docs/game-box-3d.md § 16).
class GameBoxImageSize {
  GameBoxImageSize._();

  /// Results by path, with the length and modification time they were read
  /// at: a file replaced at the same path is read again.
  static final Map<String, (int, int, Size?)> _cache = {};

  /// Bytes read at most to find the size (a JPEG's EXIF or ICC block can
  /// come before its frame header).
  static const int headerLimit = 1024 * 1024;

  static void evict(String path) => _cache.remove(path);

  static Size? of(String path) {
    int length, modified;
    try {
      final stat = File(path).statSync();
      if (stat.type == FileSystemEntityType.notFound) return null;
      length = stat.size;
      modified = stat.modified.microsecondsSinceEpoch;
    } catch (_) {
      return null;
    }
    final hit = _cache[path];
    if (hit != null && hit.$1 == length && hit.$2 == modified) return hit.$3;
    Size? result;
    try {
      final raf = File(path).openSync();
      try {
        final len = raf.lengthSync().clamp(0, headerLimit).toInt();
        final buf = Uint8List(len);
        raf.readIntoSync(buf);
        result = fromBytes(buf);
      } finally {
        raf.closeSync();
      }
    } catch (_) {
      result = null;
    }
    _cache[path] = (length, modified, result);
    return result;
  }

  static Size? _size(int w, int h) =>
      (w > 0 && h > 0 && w < 65536 && h < 65536) ? Size(w.toDouble(), h.toDouble()) : null;

  static Size? fromBytes(Uint8List b) {
    // PNG: IHDR is the first chunk.
    if (b.length >= 24 && b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47) {
      final w = (b[16] << 24) | (b[17] << 16) | (b[18] << 8) | b[19];
      final h = (b[20] << 24) | (b[21] << 16) | (b[22] << 8) | b[23];
      return _size(w, h);
    }
    if (b.length > 4 && b[0] == 0xFF && b[1] == 0xD8) return _jpeg(b);
    // WebP: RIFF....WEBP then a VP8 , VP8L or VP8X chunk.
    if (b.length >= 30 &&
        b[0] == 0x52 && b[1] == 0x49 && b[2] == 0x46 && b[3] == 0x46 &&
        b[8] == 0x57 && b[9] == 0x45 && b[10] == 0x42 && b[11] == 0x50) {
      return _webp(b);
    }
    // GIF87a / GIF89a: logical screen size, little endian.
    if (b.length >= 10 && b[0] == 0x47 && b[1] == 0x49 && b[2] == 0x46 && b[3] == 0x38) {
      return _size(b[6] | (b[7] << 8), b[8] | (b[9] << 8));
    }
    // BMP: BITMAPINFOHEADER (or later) width and height, little endian; a
    // negative height is a top-down bitmap.
    if (b.length >= 26 && b[0] == 0x42 && b[1] == 0x4D) {
      final header = b[14] | (b[15] << 8) | (b[16] << 16) | (b[17] << 24);
      if (header == 12) return _size(b[18] | (b[19] << 8), b[20] | (b[21] << 8));
      final data = ByteData.sublistView(b);
      return _size(data.getInt32(18, Endian.little).abs(), data.getInt32(22, Endian.little).abs());
    }
    return null;
  }

  static Size? _jpeg(Uint8List b) {
    var i = 2;
    while (i + 3 < b.length) {
      if (b[i] != 0xFF) {
        i++;
        continue;
      }
      final marker = b[i + 1];
      // Fill bytes before a marker.
      if (marker == 0xFF) {
        i++;
        continue;
      }
      // Markers without a length: TEM, RST0..7, SOI, EOI.
      if (marker == 0x01 || (marker >= 0xD0 && marker <= 0xD9)) {
        i += 2;
        continue;
      }
      // Start of frame (baseline, progressive, lossless…), not DHT/JPG/DAC.
      if (marker >= 0xC0 && marker <= 0xCF && marker != 0xC4 && marker != 0xC8 && marker != 0xCC) {
        if (i + 8 >= b.length) return null;
        final h = (b[i + 5] << 8) | b[i + 6];
        final w = (b[i + 7] << 8) | b[i + 8];
        return _size(w, h);
      }
      // Start of scan before a frame header: not a usable JPEG.
      if (marker == 0xDA) return null;
      final length = (b[i + 2] << 8) | b[i + 3];
      if (length < 2) return null;
      i += length + 2;
    }
    return null;
  }

  static Size? _webp(Uint8List b) {
    var i = 12;
    while (i + 8 <= b.length) {
      final tag = String.fromCharCodes(b.sublist(i, i + 4));
      final size = b[i + 4] | (b[i + 5] << 8) | (b[i + 6] << 16) | (b[i + 7] << 24);
      final d = i + 8;
      if (tag == 'VP8X' && d + 10 <= b.length) {
        final w = 1 + (b[d + 4] | (b[d + 5] << 8) | (b[d + 6] << 16));
        final h = 1 + (b[d + 7] | (b[d + 8] << 8) | (b[d + 9] << 16));
        return _size(w, h);
      }
      if (tag == 'VP8 ' && d + 10 <= b.length) {
        // Key frame start code 9D 01 2A, then 14-bit width and height.
        if (b[d + 3] != 0x9D || b[d + 4] != 0x01 || b[d + 5] != 0x2A) return null;
        final w = (b[d + 6] | (b[d + 7] << 8)) & 0x3FFF;
        final h = (b[d + 8] | (b[d + 9] << 8)) & 0x3FFF;
        return _size(w, h);
      }
      if (tag == 'VP8L' && d + 5 <= b.length) {
        if (b[d] != 0x2F) return null;
        final bits = b[d + 1] | (b[d + 2] << 8) | (b[d + 3] << 16) | (b[d + 4] << 24);
        return _size((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1);
      }
      if (size < 0) return null;
      i = d + size + (size & 1);
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
