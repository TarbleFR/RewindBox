import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_fetcher.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/screenscraper/media_downloader.dart';
import 'package:neostation/services/screenscraper/region_config.dart';

/// The game whose box faces are searched.
class GameBoxSearchContext {
  const GameBoxSearchContext({
    required this.game,
    required this.systemFolder,
    required this.fileProvider,
    required this.profile,
    this.appSystemId,
  });

  final GameModel game;
  final String systemFolder;
  final FileProvider fileProvider;

  /// The box family (physical case) of the game.
  final GameBoxProfile profile;

  /// The id the scraper maps to ScreenScraper (null: no ScreenScraper).
  final String? appSystemId;

  String get title => game.name;

  /// Product code of the player's copy when the library knows it (RPCS3
  /// title id = PS3 serial).
  String? get productId {
    final id = game.titleId?.trim().toUpperCase();
    if (id == null || id.isEmpty) return null;
    return id;
  }
}

/// How one provider answered.
enum GameBoxSourceStatus {
  ok,
  notConfigured,
  notSupported,
  needsLogin,
  systemNotMapped,
  notFound,
  quota,
  offline,
  failed,
  cancelled,
}

/// Cooperative cancellation of a search or a download.
class GameBoxCancel {
  bool _cancelled = false;
  bool get cancelled => _cancelled;
  void cancel() => _cancelled = true;
}

/// Everything found for a game.
class GameBoxSearch {
  GameBoxSearch({
    required this.candidates,
    required this.statuses,
    required this.hint,
    this.listing,
    this.caseColor,
    this.gameTdbId,
  });

  /// Usable candidates, best first, per face.
  final Map<GameBoxMediaKind, List<GameBoxCandidate>> candidates;
  final Map<GameBoxProvider, GameBoxSourceStatus> statuses;
  final GameBoxEditionHint hint;

  /// ScreenScraper's listing of the game, kept for the manifest.
  final GameBoxScreenScraperListing? listing;

  /// Case colour GameTDB lists for the identified product code.
  final String? caseColor;
  final String? gameTdbId;

  List<GameBoxCandidate> of(GameBoxMediaKind kind) => candidates[kind] ?? const [];
}

/// One face after a completion run.
enum GameBoxFaceOutcome { added, improved, kept, manualKept, missing, refused }

/// Summary shown after "Complete the faces" (docs/game-box-3d.md § 14).
class GameBoxCompletionReport {
  GameBoxCompletionReport({
    required this.outcomes,
    required this.statuses,
    required this.changedPaths,
    this.refusals = const [],
    this.frontChanged = false,
  });

  final Map<GameBoxMediaKind, GameBoxFaceOutcome> outcomes;
  final Map<GameBoxProvider, GameBoxSourceStatus> statuses;

  /// Files written or replaced (caches of exactly these are dropped).
  final Set<String> changedPaths;

  /// Downloaded pictures refused by their check: (face, provider, reason).
  final List<(GameBoxMediaKind, GameBoxProvider, GameBoxImageVerdict)> refusals;

  /// The front changed: the library's own covers must be read again.
  final bool frontChanged;

  Iterable<GameBoxMediaKind> withOutcome(GameBoxFaceOutcome o) =>
      outcomes.entries.where((e) => e.value == o).map((e) => e.key);
}

/// Result of adopting one candidate or one imported file.
class GameBoxAdoption {
  const GameBoxAdoption({this.path, this.verdict = GameBoxImageVerdict.ok, this.status = GameBoxSourceStatus.ok});
  final String? path;
  final GameBoxImageVerdict verdict;
  final GameBoxSourceStatus status;
  bool get ok => path != null;
}

/// Finds, checks and adopts the faces of a game's box from several sources
/// (docs/game-box-3d.md § 14): ScreenScraper first, GameTDB for PS3 and
/// Switch, MobyGames with the player's own key, and pictures the player
/// imports. Every file is checked before it is adopted, written atomically,
/// and its provenance recorded; a face chosen by hand is never replaced
/// automatically.
class GameBoxMediaService {
  GameBoxMediaService._();

  static final _log = LoggerService.instance;

  /// Largest download accepted for one picture.
  static const int maxBytes = 40 * 1024 * 1024;

  static const _faces = [
    GameBoxMediaKind.front,
    GameBoxMediaKind.back,
    GameBoxMediaKind.spine,
    GameBoxMediaKind.support,
  ];

  /// Test hook: replaces network reads (url → bytes, null for not found).
  @visibleForTesting
  static Future<Uint8List?> Function(String url)? debugFetch;

  /// Test hook: replaces the ScreenScraper listing.
  @visibleForTesting
  static Future<(GameBoxScreenScraperListing?, GameBoxSourceStatus)> Function(GameBoxSearchContext ctx)?
      debugScreenScraper;

  static final Map<String, String> _pageCache = {};

  // Search --------------------------------------------------------------------

  /// Lists the candidates of every enabled source for [ctx].
  static Future<GameBoxSearch> search(
    GameBoxSearchContext ctx, {
    Set<GameBoxProvider> providers = const {
      GameBoxProvider.screenscraper,
      GameBoxProvider.gametdb,
      GameBoxProvider.mobygames,
    },
    GameBoxCancel? cancel,
    void Function(GameBoxProvider provider)? onProvider,
  }) async {
    final statuses = <GameBoxProvider, GameBoxSourceStatus>{};
    final found = <GameBoxCandidate>[];
    GameBoxScreenScraperListing? listing;
    String? caseColor, tdbId;

    if (providers.contains(GameBoxProvider.screenscraper)) {
      onProvider?.call(GameBoxProvider.screenscraper);
      if (ctx.appSystemId == null) {
        statuses[GameBoxProvider.screenscraper] = GameBoxSourceStatus.systemNotMapped;
      } else {
        final (l, status) = await (debugScreenScraper ?? _screenScraper)(ctx);
        listing = l;
        statuses[GameBoxProvider.screenscraper] = status;
        if (l != null) found.addAll(l.candidates);
      }
    }
    if (cancel?.cancelled ?? false) return _cancelled(statuses, found, listing);

    if (providers.contains(GameBoxProvider.gametdb)) {
      onProvider?.call(GameBoxProvider.gametdb);
      final r = await _gameTdb(ctx, cancel);
      statuses[GameBoxProvider.gametdb] = r.status;
      found.addAll(r.candidates);
      caseColor = r.caseColor;
      tdbId = r.id;
    }
    if (cancel?.cancelled ?? false) return _cancelled(statuses, found, listing);

    if (providers.contains(GameBoxProvider.mobygames)) {
      onProvider?.call(GameBoxProvider.mobygames);
      final r = await _mobyGames(ctx, cancel);
      statuses[GameBoxProvider.mobygames] = r.$2;
      found.addAll(r.$1);
    }

    final hint = await _hint(ctx, listing);
    final byKind = <GameBoxMediaKind, List<GameBoxCandidate>>{};
    for (final kind in GameBoxMediaKind.values) {
      byKind[kind] = GameBoxCandidateRanking.rank(found.where((c) => c.kind == kind), hint);
    }
    return GameBoxSearch(
      candidates: byKind,
      statuses: statuses,
      hint: hint,
      listing: listing,
      caseColor: caseColor,
      gameTdbId: tdbId,
    );
  }

  static GameBoxSearch _cancelled(
    Map<GameBoxProvider, GameBoxSourceStatus> statuses,
    List<GameBoxCandidate> found,
    GameBoxScreenScraperListing? listing,
  ) {
    for (final p in GameBoxProvider.values) {
      if (p != GameBoxProvider.manual) statuses.putIfAbsent(p, () => GameBoxSourceStatus.cancelled);
    }
    return GameBoxSearch(
      candidates: const {},
      statuses: statuses,
      hint: const GameBoxEditionHint(),
      listing: listing,
    );
  }

  /// The player's edition: ScreenScraper's ROM record or file name tags, the
  /// PS3 serial's region, the edition of the front already shown.
  static Future<GameBoxEditionHint> _hint(GameBoxSearchContext ctx, GameBoxScreenScraperListing? listing) async {
    final regions = <String>[...?listing?.gameRegions];
    if (regions.isEmpty) {
      final product = ctx.productId;
      if (product != null) regions.addAll(GameTdb.regionsOfPs3Serial(product));
      regions.addAll(GameBoxRegions.fromFileName(ctx.game.romname).where((r) => !regions.contains(r)));
    }
    final store = GameBoxMediaStore(ctx.fileProvider);
    final local = store.read(ctx.game, ctx.systemFolder);
    final frontRecord = local.recordOf(GameBoxMediaKind.front);
    Map<String, int> priority = const {};
    try {
      priority = await ScreenscraperRegionConfig.getRegionPriority();
    } catch (_) {}
    return GameBoxEditionHint(
      gameRegions: regions,
      frontRegion: listing?.frontRegion ?? frontRecord?.region ?? local.manifest?.frontRegion,
      productId: ctx.productId,
      regionPriority: priority,
    );
  }

  static Future<(GameBoxScreenScraperListing?, GameBoxSourceStatus)> _screenScraper(GameBoxSearchContext ctx) async {
    final result = await GameBoxMediaFetcher.list(
      game: ctx.game,
      appSystemId: ctx.appSystemId!,
      systemFolder: ctx.systemFolder,
      fileProvider: ctx.fileProvider,
    );
    final status = switch (result.status) {
      GameBoxFetchStatus.needsLogin => GameBoxSourceStatus.needsLogin,
      GameBoxFetchStatus.systemNotMapped => GameBoxSourceStatus.systemNotMapped,
      GameBoxFetchStatus.notFound => GameBoxSourceStatus.notFound,
      GameBoxFetchStatus.quota => GameBoxSourceStatus.quota,
      GameBoxFetchStatus.failed => GameBoxSourceStatus.failed,
      GameBoxFetchStatus.updated || GameBoxFetchStatus.nothingNew => GameBoxSourceStatus.ok,
    };
    return (result.listing, status);
  }

  /// GameTDB: the PS3 serial is the GameTDB id; a Switch product code is
  /// found by exact title in `switchtdb.txt` (several prints can share it).
  static Future<({List<GameBoxCandidate> candidates, GameBoxSourceStatus status, String? caseColor, String? id})>
      _gameTdb(GameBoxSearchContext ctx, GameBoxCancel? cancel) async {
    final platform = GameTdb.platformOf(ctx.profile.id);
    if (platform == null) {
      return (candidates: <GameBoxCandidate>[], status: GameBoxSourceStatus.notSupported, caseColor: null, id: null);
    }
    try {
      final ids = <String>[];
      if (platform == 'ps3') {
        final serial = ctx.productId;
        if (serial != null && GameTdb.ps3Id.hasMatch(serial)) ids.add(serial);
      } else {
        final txt = await _switchTitles();
        if (txt != null) {
          for (final name in {ctx.title, ctx.game.realname}) {
            for (final id in GameTdb.idsForTitle(txt, name)) {
              if (!ids.contains(id)) ids.add(id);
            }
          }
        }
      }
      if (ids.isEmpty) {
        return (candidates: <GameBoxCandidate>[], status: GameBoxSourceStatus.notFound, caseColor: null, id: null);
      }
      final out = <GameBoxCandidate>[];
      String? color, firstId;
      for (final id in ids.take(4)) {
        if (cancel?.cancelled ?? false) break;
        final page = await _page('${GameTdb.site}/${GameTdb.pagePlatform(platform)}/$id');
        if (page == null) continue;
        final parsed = GameTdb.parsePage(page, id);
        // A Switch code found by title alone is not the player's product.
        final byProduct = platform == 'ps3';
        out.addAll([
          for (final c in parsed.candidates)
            byProduct
                ? c
                : GameBoxCandidate(
                    provider: c.provider,
                    kind: c.kind,
                    type: c.type,
                    identity: c.identity,
                    nature: c.nature,
                    region: c.region,
                    edition: c.edition,
                    productId: c.productId,
                    url: c.url,
                    width: c.width,
                    height: c.height,
                    quality: c.quality,
                    format: c.format,
                  ),
        ]);
        firstId ??= parsed.candidates.isEmpty ? null : id;
        color ??= byProduct ? parsed.caseColor : null;
      }
      return (
        candidates: out,
        status: out.isEmpty ? GameBoxSourceStatus.notFound : GameBoxSourceStatus.ok,
        caseColor: color,
        id: firstId,
      );
    } on SocketException {
      return (candidates: <GameBoxCandidate>[], status: GameBoxSourceStatus.offline, caseColor: null, id: null);
    } catch (e) {
      _log.e('[GameBox] GameTDB search failed: $e');
      return (candidates: <GameBoxCandidate>[], status: GameBoxSourceStatus.failed, caseColor: null, id: null);
    }
  }

  /// GameTDB's Switch title list, kept 30 days in the application support
  /// folder (about 0.8 MB).
  static Future<String?> _switchTitles() async {
    File? cache;
    try {
      final dir = await getApplicationSupportDirectory();
      cache = File(p.join(dir.path, 'NeoStation', 'GameBox', 'switchtdb-en.txt'));
      if (await cache.exists()) {
        final age = DateTime.now().difference(await cache.lastModified());
        if (age < const Duration(days: 30)) return await cache.readAsString();
      }
    } catch (_) {
      cache = null;
    }
    final bytes = await _get('${GameTdb.site}/switchtdb.txt?LANG=EN');
    if (bytes == null) {
      try {
        if (cache != null && await cache.exists()) return await cache.readAsString();
      } catch (_) {}
      return null;
    }
    final text = utf8.decode(bytes, allowMalformed: true);
    if (!text.startsWith('TITLES')) return null;
    try {
      if (cache != null) {
        await cache.parent.create(recursive: true);
        final temp = File('${cache.path}.part');
        await temp.writeAsString(text, flush: true);
        await temp.rename(cache.path);
      }
    } catch (_) {}
    return text;
  }

  static Future<String?> _page(String url) async {
    final hit = _pageCache[url];
    if (hit != null) return hit;
    final bytes = await _get(url);
    if (bytes == null) return null;
    final text = utf8.decode(bytes, allowMalformed: true);
    _pageCache[url] = text;
    return text;
  }

  static Future<(List<GameBoxCandidate>, GameBoxSourceStatus)> _mobyGames(
      GameBoxSearchContext ctx, GameBoxCancel? cancel) async {
    final key = await GameBoxPreferences.mobyGamesKey();
    if (key == null) return (<GameBoxCandidate>[], GameBoxSourceStatus.notConfigured);
    final platformName = MobyGames.platformNameOf(ctx.profile.id);
    if (platformName == null) return (<GameBoxCandidate>[], GameBoxSourceStatus.notSupported);
    try {
      final platforms = await _mobyJson('${MobyGames.api}/platforms', key);
      int? platformId;
      for (final pl in (platforms?['platforms'] as List? ?? const [])) {
        if (pl is Map && pl['platform_name']?.toString() == platformName) {
          platformId = int.tryParse(pl['platform_id']?.toString() ?? '');
        }
      }
      if (platformId == null) return (<GameBoxCandidate>[], GameBoxSourceStatus.notFound);
      if (cancel?.cancelled ?? false) return (<GameBoxCandidate>[], GameBoxSourceStatus.cancelled);
      final query = Uri.encodeQueryComponent(ctx.title);
      final games = await _mobyJson('${MobyGames.api}/games?title=$query&platform=$platformId&format=brief', key);
      final wanted = GameTdb.normalizeTitle(ctx.title);
      String? gameId;
      for (final g in (games?['games'] as List? ?? const [])) {
        if (g is Map && GameTdb.normalizeTitle(g['title']?.toString() ?? '') == wanted) {
          gameId = g['game_id']?.toString();
          break;
        }
      }
      if (gameId == null) return (<GameBoxCandidate>[], GameBoxSourceStatus.notFound);
      if (cancel?.cancelled ?? false) return (<GameBoxCandidate>[], GameBoxSourceStatus.cancelled);
      final covers = await _mobyJson('${MobyGames.api}/games/$gameId/platforms/$platformId/covers', key);
      if (covers == null) return (<GameBoxCandidate>[], GameBoxSourceStatus.failed);
      final out = MobyGames.parseCovers(covers, gameId: gameId);
      return (out, out.isEmpty ? GameBoxSourceStatus.notFound : GameBoxSourceStatus.ok);
    } on SocketException {
      return (<GameBoxCandidate>[], GameBoxSourceStatus.offline);
    } catch (e) {
      _log.e('[GameBox] MobyGames search failed: $e');
      return (<GameBoxCandidate>[], GameBoxSourceStatus.failed);
    }
  }

  static DateTime _lastMoby = DateTime.fromMillisecondsSinceEpoch(0);

  /// One MobyGames request, never closer than [MobyGames.interval] to the
  /// previous one; the key is added here and never stored with a result.
  static Future<Map<String, dynamic>?> _mobyJson(String url, String key) async {
    final wait = MobyGames.interval - DateTime.now().difference(_lastMoby);
    if (wait > Duration.zero) await Future<void>.delayed(wait);
    _lastMoby = DateTime.now();
    final sep = url.contains('?') ? '&' : '?';
    final bytes = await _get('$url${sep}api_key=${Uri.encodeQueryComponent(key)}');
    if (bytes == null) return null;
    final json = jsonDecode(utf8.decode(bytes));
    return json is Map<String, dynamic> ? json : null;
  }

  static http.Client? _client;

  /// GET for GameTDB and MobyGames (ScreenScraper keeps its own client,
  /// credentials and quota counter): null for 404, throws when offline.
  static Future<Uint8List?> _get(String url) async {
    final hook = debugFetch;
    if (hook != null) return hook(url);
    final client = _client ??= http.Client();
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final response = await client
            .get(Uri.parse(url), headers: const {'User-Agent': 'RewindBox (3D box covers)'})
            .timeout(const Duration(seconds: 40));
        if (response.statusCode == 404) return null;
        if (response.statusCode == 200) {
          if (response.bodyBytes.length > maxBytes) return null;
          return response.bodyBytes;
        }
        if (response.statusCode >= 500 && attempt == 0) {
          await Future<void>.delayed(const Duration(seconds: 2));
          continue;
        }
        return null;
      } on TimeoutException {
        if (attempt == 1) return null;
      }
    }
    return null;
  }

  // Adoption ------------------------------------------------------------------

  /// Downloads [candidate], checks it and writes it as the face it fills
  /// (or, for a full cover sheet, as the kept original). Refused pictures are
  /// recorded so they are never adopted again.
  static Future<GameBoxAdoption> adopt(
    GameBoxSearchContext ctx,
    GameBoxCandidate candidate, {
    GameBoxCancel? cancel,
    GameBoxScreenScraperListing? listing,
    bool manualChoice = false,
  }) async {
    final store = GameBoxMediaStore(ctx.fileProvider);
    final url = candidate.url;
    if (url == null) return const GameBoxAdoption(status: GameBoxSourceStatus.failed);
    Uint8List? bytes;
    try {
      if (candidate.provider == GameBoxProvider.screenscraper && debugFetch == null) {
        bytes = await _screenScraperBytes(ctx, candidate, url);
      } else {
        bytes = await _get(url);
      }
    } on SocketException {
      return const GameBoxAdoption(status: GameBoxSourceStatus.offline);
    } catch (e) {
      _log.e('[GameBox] download failed: $e');
      return const GameBoxAdoption(status: GameBoxSourceStatus.failed);
    }
    if (cancel?.cancelled ?? false) return const GameBoxAdoption(status: GameBoxSourceStatus.cancelled);
    if (bytes == null) return const GameBoxAdoption(status: GameBoxSourceStatus.notFound);
    return _write(
      ctx,
      store,
      candidate.kind,
      bytes,
      record: (size, md5) => GameBoxFaceRecord(
        provider: candidate.provider.id,
        type: candidate.type,
        region: candidate.region.isEmpty ? null : candidate.region,
        language: candidate.language,
        edition: candidate.edition,
        productId: candidate.productId,
        sourceIdentity: candidate.identity,
        width: size?.width.round() ?? candidate.width,
        height: size?.height.round() ?? candidate.height,
        md5: md5,
        bytes: bytes!.length,
        manual: manualChoice,
        attribution: candidate.provider.attribution,
      ),
      identity: candidate.identity,
      expected: candidate.nature,
    );
  }

  /// Imports a picture chosen by the player for [kind] (The Cover Project,
  /// an own scan…). [note] says where it comes from.
  static Future<GameBoxAdoption> importFile(
    GameBoxSearchContext ctx,
    GameBoxMediaKind kind,
    String sourcePath, {
    String? note,
  }) async {
    Uint8List bytes;
    try {
      bytes = await File(sourcePath).readAsBytes();
    } catch (_) {
      return const GameBoxAdoption(verdict: GameBoxImageVerdict.unreadable);
    }
    if (bytes.length > maxBytes) return const GameBoxAdoption(verdict: GameBoxImageVerdict.unreadable);
    final store = GameBoxMediaStore(ctx.fileProvider);
    return _write(
      ctx,
      store,
      kind,
      bytes,
      record: (size, md5) => GameBoxFaceRecord(
        provider: GameBoxProvider.manual.id,
        type: 'manual:import',
        width: size?.width.round(),
        height: size?.height.round(),
        md5: md5,
        bytes: bytes.length,
        manual: true,
        note: note,
      ),
      identity: null,
      expected: kind == GameBoxMediaKind.full ? GameBoxArtNature.wrap : GameBoxArtNature.scan,
    );
  }

  static Future<Uint8List?> _screenScraperBytes(GameBoxSearchContext ctx, GameBoxCandidate c, String url) async {
    final staging = Directory(p.join(Directory.systemTemp.path, 'rewindbox-gamebox'));
    await staging.create(recursive: true);
    final target = p.join(staging.path, '${DateTime.now().microsecondsSinceEpoch}.${c.format}');
    try {
      final ok = await ScreenscraperMediaDownloader.downloadValidatedMedia(
        ScreenScraperBoxSource.fullSize(url),
        target,
        mediaType: c.kind.screenScraperType,
        forceOverwrite: true,
      );
      if (!ok) return null;
      return await File(target).readAsBytes();
    } finally {
      try {
        final f = File(target);
        if (await f.exists()) await f.delete();
      } catch (_) {}
    }
  }

  /// Checks [bytes] and writes them as [kind] (atomically, other extensions
  /// of the same face removed), then records their provenance.
  static Future<GameBoxAdoption> _write(
    GameBoxSearchContext ctx,
    GameBoxMediaStore store,
    GameBoxMediaKind kind,
    Uint8List bytes, {
    required GameBoxFaceRecord Function(ui.Size? size, String md5) record,
    required String? identity,
    required GameBoxArtNature expected,
  }) async {
    if (!ScreenscraperMediaDownloader.isValidMediaPayload(bytes, mediaType: kind.screenScraperType)) {
      await _reject(ctx, store, identity);
      return const GameBoxAdoption(verdict: GameBoxImageVerdict.unreadable);
    }
    final check = await GameBoxMediaChecker.checkBytes(bytes);
    if (!check.ok) {
      await _reject(ctx, store, identity);
      return GameBoxAdoption(verdict: check.verdict);
    }
    final size = GameBoxImageSize.fromBytes(bytes);
    // What arrives must be what was announced: a render or a logo is not a
    // flat face; a cover sheet must have a verified layout.
    if (kind != GameBoxMediaKind.support) {
      final nature = GameBoxArtClassifier.classify(
        profile: ctx.profile,
        size: size,
        opaqueShare: check.opaqueShare,
        front: kind == GameBoxMediaKind.front,
      );
      final wrapOk = size != null && (GameBoxWrapLayout.forProfile(ctx.profile)?.matches(size) ?? false);
      final acceptable = switch (kind) {
        GameBoxMediaKind.full => wrapOk,
        _ => nature == GameBoxArtNature.scan || (kind == GameBoxMediaKind.spine && nature != GameBoxArtNature.render3d),
      };
      if (!acceptable || expected == GameBoxArtNature.render3d || expected == GameBoxArtNature.promo) {
        await _reject(ctx, store, identity);
        return const GameBoxAdoption(verdict: GameBoxImageVerdict.unreadable);
      }
    }
    final ext = _extensionOf(bytes);
    final target = store.canonicalPath(ctx.game, ctx.systemFolder, kind.folder, ext);
    final file = File(target);
    await file.parent.create(recursive: true);
    final temp = File('$target.part');
    await temp.writeAsBytes(bytes, flush: true);
    await temp.rename(target);
    for (final other in const ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp']) {
      if (other == ext) continue;
      final sibling = File('${p.withoutExtension(target)}.$other');
      try {
        if (await sibling.exists()) await sibling.delete();
      } catch (_) {}
    }
    final digest = md5.convert(bytes).toString();
    await _record(ctx, store, kind, record(size, digest), identity: identity);
    GameBoxImageSize.evict(target);
    GameBoxMediaChecker.evict(target);
    return GameBoxAdoption(path: target);
  }

  static String _extensionOf(Uint8List b) {
    if (b.length > 3 && b[0] == 0x89 && b[1] == 0x50) return 'png';
    if (b.length > 2 && b[0] == 0xFF && b[1] == 0xD8) return 'jpg';
    if (b.length > 11 && b[8] == 0x57 && b[9] == 0x45 && b[10] == 0x42 && b[11] == 0x50) return 'webp';
    if (b.length > 3 && b[0] == 0x47 && b[1] == 0x49) return 'gif';
    return 'png';
  }

  static Future<GameBoxManifest> _manifest(GameBoxSearchContext ctx, GameBoxMediaStore store) async =>
      store.read(ctx.game, ctx.systemFolder).manifest ?? GameBoxManifest.local();

  static Future<void> _record(
    GameBoxSearchContext ctx,
    GameBoxMediaStore store,
    GameBoxMediaKind kind,
    GameBoxFaceRecord record, {
    String? identity,
  }) async {
    final manifest = await _manifest(ctx, store);
    final faces = Map.of(manifest.faces)..[kind] = record;
    // A ScreenScraper scan is also the default edition of its face, as the
    // editions list and the reading language expect (§ 5, § 6); a scan from
    // another source is not one of ScreenScraper's editions.
    final defaults = Map.of(manifest.defaults);
    const prefix = 'screenscraper:';
    if (identity != null && identity.startsWith(prefix)) {
      defaults[kind] = identity.substring(prefix.length);
    } else {
      defaults.remove(kind);
    }
    await store.writeManifest(ctx.game, ctx.systemFolder, manifest.copyWith(faces: faces, defaults: defaults));
  }

  static Future<void> _reject(GameBoxSearchContext ctx, GameBoxMediaStore store, String? identity) async {
    if (identity == null) return;
    final manifest = await _manifest(ctx, store);
    if (manifest.rejected.contains(identity)) return;
    await store.writeManifest(
      ctx.game,
      ctx.systemFolder,
      manifest.copyWith(rejected: {...manifest.rejected, identity}),
    );
  }

  // Completion ----------------------------------------------------------------

  /// State of a face before a run.
  static Future<({String? path, GameBoxImageCheck? check, GameBoxFaceRecord? record, bool cover})> _current(
    GameBoxSearchContext ctx,
    GameBoxLocalMedia local,
    GameBoxMediaKind kind,
  ) async {
    final path = local.pathOf(kind);
    if (path == null) return (path: null, check: null, record: null, cover: false);
    final check = await GameBoxMediaChecker.checkFile(path);
    final record = local.recordOf(kind);
    var cover = check.ok;
    if (cover && (kind == GameBoxMediaKind.front || kind == GameBoxMediaKind.back)) {
      final nature = GameBoxArtClassifier.classify(
        profile: ctx.profile,
        size: GameBoxImageSize.of(path),
        provenance: record?.type,
        opaqueShare: check.opaqueShare,
        front: kind == GameBoxMediaKind.front,
      );
      cover = nature == GameBoxArtNature.scan || nature == GameBoxArtNature.wrap;
    }
    return (path: path, check: check, record: record, cover: cover);
  }

  /// "Complete the faces": every face that is missing, refused by its check
  /// or not a cover (an icon used as front) gets the best candidate of a
  /// coherent edition; faces already good, and any face chosen by hand, are
  /// kept. Returns what was added, kept, refused and still missing.
  static Future<GameBoxCompletionReport> complete(
    GameBoxSearchContext ctx, {
    GameBoxSearch? search,
    GameBoxCancel? cancel,
    void Function(GameBoxMediaKind kind)? onFace,
  }) async {
    final found = search ?? await GameBoxMediaService.search(ctx, cancel: cancel);
    final store = GameBoxMediaStore(ctx.fileProvider);
    var local = store.read(ctx.game, ctx.systemFolder);
    final outcomes = <GameBoxMediaKind, GameBoxFaceOutcome>{};
    final changed = <String>{};
    final refusals = <(GameBoxMediaKind, GameBoxProvider, GameBoxImageVerdict)>[];
    var frontChanged = false;

    // ScreenScraper's listing and the GameTDB case colour go to the manifest
    // first, so that later records extend it.
    await _mergeListing(ctx, store, found);
    local = store.read(ctx.game, ctx.systemFolder);
    final rejected = local.manifest?.rejected ?? const <String>{};

    // The edition the set follows: the front's when it is a known scan.
    String? setProduct = local.recordOf(GameBoxMediaKind.front)?.productId;
    GameBoxProvider? setProvider;

    for (final kind in _faces) {
      if (cancel?.cancelled ?? false) break;
      onFace?.call(kind);
      final current = await _current(ctx, local, kind);
      if (current.record?.manual ?? false) {
        outcomes[kind] = GameBoxFaceOutcome.manualKept;
        continue;
      }
      if (current.path != null && current.cover) {
        outcomes[kind] = GameBoxFaceOutcome.kept;
        setProduct ??= current.record?.productId;
        continue;
      }
      // A spine comes from a full cover sheet when no separate scan exists.
      final candidates = [
        ...found.of(kind),
        if (kind == GameBoxMediaKind.spine) ...found.of(GameBoxMediaKind.full),
      ].where((c) => !rejected.contains(c.identity)).toList();
      // Coherence: the same product (edition) as the faces already chosen.
      candidates.sort((a, b) {
        int coherent(GameBoxCandidate c) =>
            (setProduct != null && c.productId == setProduct ? 2 : 0) + (setProvider == c.provider ? 1 : 0);
        final byCoherence = coherent(b).compareTo(coherent(a));
        if (byCoherence != 0) return byCoherence;
        return GameBoxCandidateRanking.score(b, found.hint).compareTo(GameBoxCandidateRanking.score(a, found.hint));
      });
      var done = false;
      for (final c in candidates.take(4)) {
        if (cancel?.cancelled ?? false) break;
        final adoption = await adopt(ctx, c, cancel: cancel, listing: found.listing);
        if (adoption.ok) {
          changed.add(adoption.path!);
          outcomes[kind] = current.path == null ? GameBoxFaceOutcome.added : GameBoxFaceOutcome.improved;
          if (kind == GameBoxMediaKind.front) frontChanged = true;
          setProduct ??= c.productId;
          setProvider ??= c.provider;
          done = true;
          break;
        }
        if (adoption.verdict != GameBoxImageVerdict.ok) refusals.add((kind, c.provider, adoption.verdict));
      }
      if (!done) {
        outcomes[kind] = current.path != null && current.check != null && !current.check!.ok
            ? GameBoxFaceOutcome.refused
            : GameBoxFaceOutcome.missing;
      }
      local = store.read(ctx.game, ctx.systemFolder);
    }
    return GameBoxCompletionReport(
      outcomes: outcomes,
      statuses: found.statuses,
      changedPaths: changed,
      refusals: refusals,
      frontChanged: frontChanged,
    );
  }

  /// Writes ScreenScraper's listing (editions, regions, identification) and
  /// GameTDB's case colour into the manifest, keeping face records,
  /// rejections and downloaded editions.
  static Future<void> _mergeListing(GameBoxSearchContext ctx, GameBoxMediaStore store, GameBoxSearch found) async {
    final current = store.read(ctx.game, ctx.systemFolder).manifest;
    final listing = found.listing;
    final color = found.caseColor;
    if (listing == null && color == null) return;
    var manifest = current ?? GameBoxManifest.local();
    if (listing != null) {
      manifest = manifest.copyWith(
        screenScraperSystemId: listing.systemId,
        screenScraperGameId: listing.gameId,
        matchedBy: listing.matchedBy,
        entries: listing.entries,
        gameRegions: listing.gameRegions,
        gameRegionSource: listing.gameRegionSource,
      );
    }
    if (color != null && found.gameTdbId != null) {
      final value = int.tryParse(color, radix: 16);
      // Only a coloured case is a variant; black and white are listed too.
      if (value != null) {
        manifest = manifest.copyWith(
          identifiedCase: GameBoxIdentifiedCase(
            color: ui.Color(0xFF000000 | value),
            source: 'gametdb:${found.gameTdbId}',
          ),
        );
      }
    }
    await store.writeManifest(ctx.game, ctx.systemFolder, manifest);
  }
}
