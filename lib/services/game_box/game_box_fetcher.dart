import 'dart:io';

import 'package:path/path.dart' as p;

import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/repositories/scraper_repository.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/screenscraper/media_downloader.dart';
import 'package:neostation/services/screenscraper/region_config.dart';
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
  const GameBoxFetchResult(this.status, {this.downloaded = const {}});
  final GameBoxFetchStatus status;
  final Set<GameBoxMediaKind> downloaded;
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

  static const _faces = [GameBoxMediaKind.back, GameBoxMediaKind.spine, GameBoxMediaKind.support];

  static Future<GameBoxFetchResult> fetch({
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
      final gameId = jeu['id']?.toString() ?? '';
      final rawMedias = jeu['medias'];
      final medias = rawMedias is List ? rawMedias : const [];

      final entries = <GameBoxMediaEntry>[];
      final urls = <String, String>{}; // identity → URL (with credentials, memory only)
      for (final m in medias) {
        if (m is! Map) continue;
        final e = GameBoxMediaEntry.fromScreenScraper(m);
        if (e == null) continue;
        entries.add(e);
        final url = m['url']?.toString() ?? '';
        if (url.isNotEmpty) urls.putIfAbsent('${e.kind.name}|${e.identity}|${e.region}', () => url);
      }

      final store = GameBoxMediaStore(fileProvider);
      final local = store.read(game, systemFolder);
      final (regions, regionSource) = _gameRegions(jeu, game.romname, trustRom: matched == GameBoxMatch.md5);
      final front = _frontEdition(local.front, entries);
      final priority = await ScreenscraperRegionConfig.getRegionPriority();

      final defaults = <GameBoxMediaKind, String>{};
      final downloaded = <GameBoxMediaKind>{};
      for (final kind in _faces) {
        final choice = GameBoxMediaSelection.choose(
          entries, kind,
          gameRegions: regions, frontRegion: front?.region, regionPriority: priority,
        );
        if (choice == null) continue;
        defaults[kind] = choice.identity;
        final previous = local.manifest?.defaults[kind];
        final existing = _localPath(local, kind);
        if (existing != null && previous == choice.identity) continue;
        final url = urls['${kind.name}|${choice.identity}|${choice.region}'];
        if (url == null) continue;
        final target = store.canonicalPath(game, systemFolder, kind.folder, choice.format);
        final ok = await ScreenscraperMediaDownloader.downloadValidatedMedia(
          url, target,
          mediaType: kind.screenScraperType,
          // A different edition replaces the previous default face.
          forceOverwrite: existing != null,
        );
        if (ok) {
          downloaded.add(kind);
          GameBoxImageSize.evict(target);
        } else {
          defaults.remove(kind);
          if (previous != null && existing != null) defaults[kind] = previous;
        }
      }

      final manifest = GameBoxManifest(
        screenScraperSystemId: ssSystem.toString(),
        screenScraperGameId: gameId,
        matchedBy: matched,
        entries: entries,
        gameRegions: regions,
        gameRegionSource: regionSource,
        frontRegion: front?.region,
        frontConfirmed: front != null,
        defaults: defaults,
        backEditionFiles: _keptEditionFiles(local),
      );
      await store.writeManifest(game, systemFolder, manifest);
      return GameBoxFetchResult(
        downloaded.isEmpty ? GameBoxFetchStatus.nothingNew : GameBoxFetchStatus.updated,
        downloaded: downloaded,
      );
    } on ScreenscraperQuotaExceededException {
      return const GameBoxFetchResult(GameBoxFetchStatus.quota);
    } catch (e) {
      _log.e('[GameBox] faces fetch failed: $e');
      return const GameBoxFetchResult(GameBoxFetchStatus.failed);
    }
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
      uri.toString(), target, mediaType: GameBoxMediaKind.back.screenScraperType,
    );
    if (!ok) return null;
    final files = Map<String, String>.from(manifest.backEditionFiles)..[edition.entry.identity] = name;
    await store.writeManifest(
      game, systemFolder,
      GameBoxManifest(
        screenScraperSystemId: manifest.screenScraperSystemId,
        screenScraperGameId: manifest.screenScraperGameId,
        matchedBy: manifest.matchedBy,
        entries: manifest.entries,
        gameRegions: manifest.gameRegions,
        gameRegionSource: manifest.gameRegionSource,
        frontRegion: manifest.frontRegion,
        frontConfirmed: manifest.frontConfirmed,
        defaults: manifest.defaults,
        backEditionFiles: files,
        fetchedAt: manifest.fetchedAt,
      ),
    );
    return target;
  }

  static String _safe(String s) => s.replaceAll(RegExp(r'[^A-Za-z0-9]'), '_');

  static String? _localPath(GameBoxLocalMedia local, GameBoxMediaKind kind) => switch (kind) {
        GameBoxMediaKind.front => local.front,
        GameBoxMediaKind.back => local.back,
        GameBoxMediaKind.spine => local.spine,
        GameBoxMediaKind.support => local.support,
      };

  static Map<String, String> _keptEditionFiles(GameBoxLocalMedia local) {
    final kept = <String, String>{};
    final m = local.manifest;
    final dir = local.backEditionsDir;
    if (m == null || dir == null) return kept;
    m.backEditionFiles.forEach((id, name) {
      if (File(p.join(dir, name)).existsSync()) kept[id] = name;
    });
    return kept;
  }

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
