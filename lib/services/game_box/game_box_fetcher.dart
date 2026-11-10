import 'dart:io';

import 'package:path/path.dart' as p;

import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/repositories/scraper_repository.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/screenscraper/media_downloader.dart';
import 'package:neostation/services/screenscraper/rom_hasher.dart';
import 'package:neostation/services/screenscraper/screenscraper_exceptions.dart';
import 'package:neostation/services/screenscraper_service.dart';

enum GameBoxFetchStatus {
  updated,
  nothingNew,
  needsLogin,
  systemNotMapped,
  notFound,
  quota,
  failed,
}

class GameBoxFetchResult {
  const GameBoxFetchResult(this.status, {this.downloaded = const {}, this.listing});
  final GameBoxFetchStatus status;
  final Set<GameBoxMediaKind> downloaded;

  /// What ScreenScraper lists for the game (only from [GameBoxMediaFetcher.list]).
  final GameBoxScreenScraperListing? listing;
}

/// ScreenScraper's answer for one game: its editions (credential-free
/// entries), how it was identified, the regions of the player's copy, and
/// the candidates of the box faces. The download addresses carry the
/// credentials and live in memory only (never in the manifest).
class GameBoxScreenScraperListing {
  GameBoxScreenScraperListing({
    required this.systemId,
    required this.gameId,
    required this.matchedBy,
    required this.entries,
    required this.candidates,
    this.gameRegions = const [],
    this.gameRegionSource,
    this.frontRegion,
    this.title,
  });

  final String systemId;
  final String gameId;
  final GameBoxMatch matchedBy;
  final List<GameBoxMediaEntry> entries;
  final List<GameBoxCandidate> candidates;
  final List<String> gameRegions;
  final String? gameRegionSource;

  /// Region of the front already in the library, when its MD5 is listed.
  final String? frontRegion;

  /// The game's name as ScreenScraper lists it (world, US, then European
  /// name): GameTDB matches Switch titles exactly.
  final String? title;
}

/// Gets the faces of a game's box from ScreenScraper, through the scraper's
/// own client, credentials, quota counter and payload validation.
///
/// Identification: the ScreenScraper system of the console, the ROM's MD5
/// when the file is local and small enough to hash quickly, its serial when
/// known, and its file name (No-Intro/Redump names carry the region). A game
/// is never matched by its display title alone. The front already in the
/// library is never replaced; it is only compared with the listed fronts to
/// record which edition it shows.
class GameBoxMediaFetcher {
  GameBoxMediaFetcher._();

  static final _log = LoggerService.instance;

  /// ROMs up to this size are hashed (cartridges, small discs).
  static const int md5Limit = 64 * 1024 * 1024;

  /// Gets the missing faces of a game's box from ScreenScraper, checked
  /// before adoption (docs/game-box-3d.md § 14–15). The front already in the
  /// library is kept unless it is not a cover (an icon), and a face chosen
  /// by hand is never replaced.
  static Future<GameBoxFetchResult> fetch({
    required GameModel game,
    required String appSystemId,
    required String systemFolder,
    required FileProvider fileProvider,
  }) async {
    final profile = await GameBoxProfiles.load(appSystemId);
    final ctx = GameBoxSearchContext(
      game: game,
      systemFolder: systemFolder,
      fileProvider: fileProvider,
      profile: profile,
      appSystemId: appSystemId,
    );
    final search = await GameBoxMediaService.search(ctx, providers: const {GameBoxProvider.screenscraper});
    final status = search.statuses[GameBoxProvider.screenscraper];
    if (status != null && status != GameBoxSourceStatus.ok) {
      return GameBoxFetchResult(switch (status) {
        GameBoxSourceStatus.needsLogin => GameBoxFetchStatus.needsLogin,
        GameBoxSourceStatus.systemNotMapped => GameBoxFetchStatus.systemNotMapped,
        GameBoxSourceStatus.notFound => GameBoxFetchStatus.notFound,
        GameBoxSourceStatus.quota => GameBoxFetchStatus.quota,
        _ => GameBoxFetchStatus.failed,
      });
    }
    final report = await GameBoxMediaService.complete(ctx, search: search);
    final downloaded = {
      ...report.withOutcome(GameBoxFaceOutcome.added),
      ...report.withOutcome(GameBoxFaceOutcome.improved),
    };
    return GameBoxFetchResult(
      downloaded.isEmpty ? GameBoxFetchStatus.nothingNew : GameBoxFetchStatus.updated,
      downloaded: downloaded,
    );
  }

  /// Identifies the game on ScreenScraper and lists the scans of its box,
  /// without downloading any: the system of the console, the ROM's MD5 when
  /// it is local and small, its serial when known, and its file name — never
  /// the displayed title alone.
  static Future<GameBoxFetchResult> list({
    required GameModel game,
    required String appSystemId,
    required String systemFolder,
    required FileProvider fileProvider,
  }) async {
    try {
      if (!await ScreenScraperService.hasSavedCredentials()) {
        return const GameBoxFetchResult(GameBoxFetchStatus.needsLogin);
      }
      var ssSystem = await ScraperRepository.getScreenScraperIdByAppSystemId(appSystemId);
      if (ssSystem == null) {
        await ScreenScraperService.syncSystemIds();
        ssSystem = await ScraperRepository.getScreenScraperIdByAppSystemId(appSystemId);
      }
      if (ssSystem == null) return const GameBoxFetchResult(GameBoxFetchStatus.systemNotMapped);

      final md5 = await _romMd5(game.romPath);
      final serial = game.titleId?.trim();
      Map<String, dynamic>? info;
      var matched = GameBoxMatch.fileName;
      if (md5 != null) {
        info = await ScreenScraperService.fetchGameInfo(
          ssSystem.toString(), game.romname,
          appSystemId: appSystemId, md5: md5, maxDailyRequests: 0,
          serialNumber: (serial?.isEmpty ?? true) ? null : serial,
        );
        if (info?['gameInfo'] != null) matched = GameBoxMatch.md5;
      }
      if (info?['gameInfo'] == null) {
        info = await ScreenScraperService.fetchGameInfo(
          ssSystem.toString(), game.romname,
          appSystemId: appSystemId, maxDailyRequests: 0,
          serialNumber: (serial?.isEmpty ?? true) ? null : serial,
        );
        matched = (serial?.isNotEmpty ?? false) ? GameBoxMatch.serial : GameBoxMatch.fileName;
      }
      final jeu = info?['gameInfo'];
      if (jeu is! Map) return const GameBoxFetchResult(GameBoxFetchStatus.notFound);
      return GameBoxFetchResult(
        GameBoxFetchStatus.nothingNew,
        listing: listingOf(
          game: game,
          jeu: jeu,
          screenScraperSystemId: ssSystem.toString(),
          matchedBy: matched,
          systemFolder: systemFolder,
          fileProvider: fileProvider,
        ),
      );
    } on ScreenscraperQuotaExceededException {
      return const GameBoxFetchResult(GameBoxFetchStatus.quota);
    } catch (e) {
      _log.e('[GameBox] faces listing failed: $e');
      return const GameBoxFetchResult(GameBoxFetchStatus.failed);
    }
  }

  /// The box scans of a game ScreenScraper already answered for ([jeu], the
  /// `jeuInfos` record): the batch scrape reuses its answer, no request.
  static GameBoxScreenScraperListing listingOf({
    required GameModel game,
    required Map jeu,
    required String screenScraperSystemId,
    required GameBoxMatch matchedBy,
    required String systemFolder,
    required FileProvider fileProvider,
  }) {
    final gameId = jeu['id']?.toString() ?? '';
    final rawMedias = jeu['medias'];
    final medias = rawMedias is List ? rawMedias : const [];

    final entries = <GameBoxMediaEntry>[];
    final candidates = <GameBoxCandidate>[];
    final seen = <String>{};
    final byProduct = matchedBy == GameBoxMatch.md5 || matchedBy == GameBoxMatch.serial;
    for (final m in medias) {
      if (m is! Map) continue;
      final e = GameBoxMediaEntry.fromScreenScraper(m);
      if (e == null) continue;
      entries.add(e);
      final url = m['url']?.toString() ?? '';
      // One picture listed under several regions is one candidate.
      if (url.isNotEmpty && seen.add('${e.kind.name}|${e.identity}')) {
        candidates.add(ScreenScraperBoxSource.candidate(e, url, byProduct: byProduct, gameId: gameId));
      }
    }

    final local = GameBoxMediaStore(fileProvider).read(game, systemFolder);
    final (regions, regionSource) = _gameRegions(jeu, game.romname, trustRom: matchedBy == GameBoxMatch.md5);
    final front = _frontEdition(local.front, entries);
    String? title;
    final noms = jeu['noms'];
    if (noms is List) {
      final byRegion = <String, String>{
        for (final n in noms)
          if (n is Map && (n['text']?.toString().trim().isNotEmpty ?? false))
            n['region']?.toString() ?? '': n['text'].toString().trim(),
      };
      title = byRegion['wor'] ?? byRegion['us'] ?? byRegion['eu'] ?? byRegion['ss'] ??
          (byRegion.isEmpty ? null : byRegion.values.first);
    }
    return GameBoxScreenScraperListing(
      title: title,
      systemId: screenScraperSystemId,
      gameId: gameId,
      matchedBy: matchedBy,
      entries: entries,
      candidates: candidates,
      gameRegions: regions,
      gameRegionSource: regionSource,
      frontRegion: front?.region,
    );
  }

  /// Path of the back scan of [edition], downloading it once if needed.
  ///
  /// A scan whose identity (MD5, else SHA-1) is already on disk, as the
  /// default back or as another edition, is never downloaded again. Offline,
  /// an edition not yet downloaded returns null.
  static Future<String?> ensureBackEdition({
    required GameModel game,
    required String systemFolder,
    required FileProvider fileProvider,
    required GameBoxBackEdition edition,
  }) async {
    final store = GameBoxMediaStore(fileProvider);
    final local = store.read(game, systemFolder);
    final manifest = local.manifest;
    if (manifest == null) return null;
    final existing = local.backEditionFile(edition.entry);
    if (existing != null) return existing;
    // A scan refused once (uniform placeholder…) is never fetched again.
    final identity = 'screenscraper:${edition.entry.identity}';
    if (manifest.rejected.contains(identity)) return null;
    final uri = await ScreenScraperService.mediaJeuUri(
      systemId: manifest.screenScraperSystemId,
      gameId: manifest.screenScraperGameId,
      media: edition.entry.token,
    );
    if (uri == null || manifest.screenScraperGameId.isEmpty) return null;
    final name = '${_safe(edition.entry.region)}-${_safe(edition.entry.identity)}.${edition.entry.format}';
    final dir = local.backEditionsDir!;
    final target = p.join(dir, name);
    final ok = await ScreenscraperMediaDownloader.downloadValidatedMedia(
      ScreenScraperBoxSource.fullSize(uri.toString()), target, mediaType: GameBoxMediaKind.back.screenScraperType,
    );
    if (!ok) return null;
    final check = await GameBoxMediaChecker.checkFile(target);
    if (!check.ok) {
      try {
        await File(target).delete();
      } catch (_) {}
      GameBoxMediaChecker.evict(target);
      await store.writeManifest(game, systemFolder, manifest.copyWith(rejected: {...manifest.rejected, identity}));
      return null;
    }
    final files = Map<String, String>.from(manifest.backEditionFiles)..[edition.entry.identity] = name;
    // copyWith keeps the face records, rejections and identified case.
    await store.writeManifest(game, systemFolder, manifest.copyWith(backEditionFiles: files));
    return target;
  }

  static String _safe(String s) => s.replaceAll(RegExp(r'[^A-Za-z0-9]'), '_');

  static Future<String?> _romMd5(String? romPath) async {
    if (romPath == null || romPath.isEmpty || romPath.contains('://')) return null;
    try {
      final f = File(romPath);
      if (!await f.exists()) return null;
      final size = await f.length();
      if (size <= 0 || size > md5Limit) return null;
      return await ScreenscraperRomHasher.calculateMd5InIsolate(romPath);
    } catch (_) {
      return null;
    }
  }

  /// Regions of the user's copy: the ROM record of a checksum match, else the
  /// file name's region tags.
  static (List<String>, String?) _gameRegions(Map jeu, String romName, {required bool trustRom}) {
    if (trustRom) {
      final rom = jeu['rom'];
      if (rom is Map) {
        final raw = rom['romregions'] ?? rom['regions'];
        final regions = <String>[];
        if (raw is String) {
          regions.addAll(raw.split(RegExp(r'[,;\s]+')).where((r) => r.isNotEmpty));
        } else if (raw is Map) {
          for (final v in raw.values) {
            if (v is String && v.isNotEmpty) regions.add(v);
          }
        } else if (raw is List) {
          for (final v in raw) {
            final s = v is Map ? (v['shortname'] ?? v['nomcourt'] ?? '').toString() : v.toString();
            if (s.isNotEmpty) regions.add(s);
          }
        }
        if (regions.isNotEmpty) return (regions.map((r) => r.toLowerCase()).toList(), 'screenscraper');
      }
    }
    final fromName = GameBoxRegions.fromFileName(romName);
    return (fromName, fromName.isEmpty ? null : 'filename');
  }

  /// The listed front whose MD5 equals the local front: proves which edition
  /// the library already shows.
  static GameBoxMediaEntry? _frontEdition(String? frontPath, List<GameBoxMediaEntry> entries) {
    if (frontPath == null) return null;
    final md5 = gameBoxFileMd5(frontPath);
    if (md5 == null) return null;
    for (final e in entries) {
      if (e.kind == GameBoxMediaKind.front && e.md5 != null && e.md5!.toLowerCase() == md5) return e;
    }
    return null;
  }
}
