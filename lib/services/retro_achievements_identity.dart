import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import '../data/datasources/sqlite_service.dart';
import 'logger_service.dart';

/// How a library game was matched to its RetroAchievements set
/// (NEOSTATION_RA_IDENTIFICATION_V1).
///
/// Only [launch], [hash] and [online] come from the file itself: the emulator
/// will recognize the game too. [name] and [history] are guesses from the
/// title; the achievements shown are the right game's, but RetroAchievements
/// may not accept this particular file in game.
enum RetroAchievementsMatch { launch, hash, online, name, history, none }

class RetroAchievementsIdentity {
  const RetroAchievementsIdentity({this.gameId, this.hash, required this.match});

  static const unknown = RetroAchievementsIdentity(match: RetroAchievementsMatch.none);

  final int? gameId;

  /// The file's RetroAchievements hash, when it could be computed.
  final String? hash;
  final RetroAchievementsMatch match;

  /// The file itself is known to RetroAchievements (not only its title).
  bool get recognizedByFile => match == RetroAchievementsMatch.launch ||
      match == RetroAchievementsMatch.hash || match == RetroAchievementsMatch.online;

  /// A set was found from the title only: the file may not track in game.
  bool get matchedByTitleOnly =>
      match == RetroAchievementsMatch.name || match == RetroAchievementsMatch.history;
}

/// What the app remembers about one library file.
class RomIdentityRecord {
  const RomIdentityRecord({this.hash, this.consoleId, this.algorithm = 0, this.gameId, this.source});

  final String? hash;
  final int? consoleId;

  /// [RetroAchievementsNativeHash.algorithm] when the hash came from rcheevos;
  /// 0 or 1 for the older Dart implementation (not trusted for disc images).
  final int algorithm;
  final int? gameId;

  /// `launch` (an emulator loaded the set), `online` or `local`.
  final String? source;
}

/// Storage of the identification results. The SQL implementation lives in the
/// application database; tests use [MemoryRetroAchievementsIdentityStore].
abstract class RetroAchievementsIdentityStore {
  Future<RomIdentityRecord?> rom(String romPath);
  Future<void> saveHash(String romPath, String hash, {int? consoleId, required int algorithm});
  Future<void> saveGameId(String romPath, int gameId, {required String source});

  /// A cached online answer: a game id, 0 for "unknown to RetroAchievements",
  /// or null when nothing fresh is cached.
  Future<int?> cachedLookup(String hash, DateTime now);
  Future<void> saveLookup(String hash, int gameId, DateTime now);
}

class MemoryRetroAchievementsIdentityStore implements RetroAchievementsIdentityStore {
  final roms = <String, RomIdentityRecord>{};
  final lookups = <String, (int, DateTime)>{};

  @override
  Future<RomIdentityRecord?> rom(String romPath) async => roms[romPath];

  @override
  Future<void> saveHash(String romPath, String hash, {int? consoleId, required int algorithm}) async {
    final previous = roms[romPath];
    final sameFile = previous?.hash == hash;
    roms[romPath] = RomIdentityRecord(hash: hash, consoleId: consoleId, algorithm: algorithm,
      gameId: sameFile ? previous?.gameId : null, source: sameFile ? previous?.source : null);
  }

  @override
  Future<void> saveGameId(String romPath, int gameId, {required String source}) async {
    final previous = roms[romPath];
    roms[romPath] = RomIdentityRecord(hash: previous?.hash, consoleId: previous?.consoleId,
      algorithm: previous?.algorithm ?? 0, gameId: gameId, source: source);
  }

  @override
  Future<int?> cachedLookup(String hash, DateTime now) async {
    final entry = lookups[hash];
    if (entry == null) return null;
    return RetroAchievementsHashLookup.isFresh(entry.$1, entry.$2, now) ? entry.$1 : null;
  }

  @override
  Future<void> saveLookup(String hash, int gameId, DateTime now) async => lookups[hash] = (gameId, now);
}

/// SQL store in the application database (tables created on first use).
class SqlRetroAchievementsIdentityStore implements RetroAchievementsIdentityStore {
  const SqlRetroAchievementsIdentityStore();

  static Future<DatabaseAdapter>? _ready;

  static Future<DatabaseAdapter> _database() => _ready ??= () async {
    final db = await SqliteService.getDatabase();
    await db.execute('''CREATE TABLE IF NOT EXISTS ra_rom_identity (
      rom_path TEXT PRIMARY KEY,
      hash TEXT,
      console_id INTEGER,
      algorithm INTEGER NOT NULL DEFAULT 0,
      game_id INTEGER,
      source TEXT,
      updated_at INTEGER NOT NULL DEFAULT 0
    )''');
    await db.execute('''CREATE TABLE IF NOT EXISTS ra_hash_lookup (
      hash TEXT PRIMARY KEY,
      game_id INTEGER NOT NULL DEFAULT 0,
      checked_at INTEGER NOT NULL
    )''');
    return db;
  }();

  @override
  Future<RomIdentityRecord?> rom(String romPath) async {
    final db = await _database();
    final rows = await db.query('ra_rom_identity', where: 'rom_path = ?', whereArgs: [romPath], limit: 1);
    if (rows.isEmpty) return null;
    final row = rows.first;
    return RomIdentityRecord(hash: row['hash'] as String?, consoleId: (row['console_id'] as num?)?.toInt(),
      algorithm: (row['algorithm'] as num?)?.toInt() ?? 0, gameId: (row['game_id'] as num?)?.toInt(),
      source: row['source'] as String?);
  }

  @override
  Future<void> saveHash(String romPath, String hash, {int? consoleId, required int algorithm}) async {
    final db = await _database();
    // A different hash means a different file: its previous game id is stale.
    await db.rawInsert('''INSERT INTO ra_rom_identity (rom_path, hash, console_id, algorithm, updated_at)
      VALUES (?, ?, ?, ?, ?) ON CONFLICT(rom_path) DO UPDATE SET
      game_id = CASE WHEN ra_rom_identity.hash = excluded.hash THEN ra_rom_identity.game_id ELSE NULL END,
      source = CASE WHEN ra_rom_identity.hash = excluded.hash THEN ra_rom_identity.source ELSE NULL END,
      hash = excluded.hash, console_id = excluded.console_id, algorithm = excluded.algorithm,
      updated_at = excluded.updated_at''',
      [romPath, hash, consoleId, algorithm, DateTime.now().millisecondsSinceEpoch]);
    await db.rawUpdate('UPDATE user_roms SET ra_hash = ? WHERE rom_path = ?', [hash, romPath]);
  }

  @override
  Future<void> saveGameId(String romPath, int gameId, {required String source}) async {
    final db = await _database();
    await db.rawInsert('''INSERT INTO ra_rom_identity (rom_path, game_id, source, updated_at)
      VALUES (?, ?, ?, ?) ON CONFLICT(rom_path) DO UPDATE SET
      game_id = excluded.game_id, source = excluded.source, updated_at = excluded.updated_at''',
      [romPath, gameId, source, DateTime.now().millisecondsSinceEpoch]);
    await db.rawUpdate('UPDATE user_roms SET id_ra = ? WHERE rom_path = ?', [gameId, romPath]);
  }

  @override
  Future<int?> cachedLookup(String hash, DateTime now) async {
    final db = await _database();
    final rows = await db.query('ra_hash_lookup', where: 'hash = ?', whereArgs: [hash], limit: 1);
    if (rows.isEmpty) return null;
    final gameId = (rows.first['game_id'] as num?)?.toInt() ?? 0;
    final checked = DateTime.fromMillisecondsSinceEpoch((rows.first['checked_at'] as num?)?.toInt() ?? 0);
    return RetroAchievementsHashLookup.isFresh(gameId, checked, now) ? gameId : null;
  }

  @override
  Future<void> saveLookup(String hash, int gameId, DateTime now) async {
    final db = await _database();
    await db.rawInsert('''INSERT INTO ra_hash_lookup (hash, game_id, checked_at) VALUES (?, ?, ?)
      ON CONFLICT(hash) DO UPDATE SET game_id = excluded.game_id, checked_at = excluded.checked_at''',
      [hash, gameId, now.millisecondsSinceEpoch]);
  }
}

/// Hashes a file with rcheevos inside the libretro bridge (iOS): the same code
/// and the same .chd/.cso reader as the in-game client
/// (NEOSTATION_RA_DISC_READER_V1), so the library shows what the game will
/// recognize. Unavailable elsewhere (desktop, tests): callers then use the
/// Dart implementation.
class RetroAchievementsNativeHash {
  RetroAchievementsNativeHash._();

  /// Stored with each hash; older hashes (Dart, whole-file MD5 for discs) are
  /// recomputed once when this is available.
  static const int algorithm = 2;

  static const MethodChannel _channel = MethodChannel('neostation/libretro_internal');
  static final _md5 = RegExp(r'^[0-9a-f]{32}$');

  @visibleForTesting
  static MethodChannel? channelOverride;
  @visibleForTesting
  static bool? availableOverride;

  static bool get available => availableOverride ?? (!kIsWeb && Platform.isIOS);

  /// The hash, or null when rcheevos cannot hash this file for [consoleId].
  static Future<String?> hash(String path, int consoleId) async {
    if (!available || consoleId <= 0 || path.isEmpty) return null;
    try {
      final value = await (channelOverride ?? _channel).invokeMethod<Object?>(
        'retroAchievementsHash', {'path': path, 'consoleId': consoleId});
      final hash = value is String ? value.toLowerCase() : null;
      return hash != null && _md5.hasMatch(hash) ? hash : null;
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }
}

/// Asks RetroAchievements which game a hash belongs to when the list bundled
/// with the app does not know it (games and dumps added after the app was
/// built). Same public request as rcheevos (`r=gameid`): no account data is
/// sent, only the hash. Answers are cached: known games for 30 days, unknown
/// hashes for 3 days, so the server is asked at most once in that time.
class RetroAchievementsHashLookup {
  RetroAchievementsHashLookup._();

  static final _log = LoggerService.instance;
  static final Uri endpoint = Uri.parse('https://retroachievements.org/dorequest.php');
  static const Duration knownTtl = Duration(days: 30);
  static const Duration unknownTtl = Duration(days: 3);
  static final _md5 = RegExp(r'^[0-9a-f]{32}$');

  @visibleForTesting
  static http.Client? clientOverride;
  @visibleForTesting
  static DateTime Function() clock = DateTime.now;

  static bool isFresh(int gameId, DateTime checkedAt, DateTime now) =>
      now.difference(checkedAt) < (gameId > 0 ? knownTtl : unknownTtl);

  /// The game id (> 0), 0 when RetroAchievements does not know the hash, or
  /// null when it could not be asked (offline, server error).
  static Future<int?> resolve(String hash, RetroAchievementsIdentityStore store) async {
    final normalized = hash.toLowerCase();
    if (!_md5.hasMatch(normalized)) return null;
    final now = clock();
    try {
      final cached = await store.cachedLookup(normalized, now);
      if (cached != null) return cached;
    } catch (error) {
      _log.w('RetroAchievements hash cache unavailable: $error');
    }
    final client = clientOverride ?? http.Client();
    try {
      final response = await client.post(endpoint,
        headers: {'User-Agent': 'NeoStation/1.0 (game identification)', 'Accept': 'application/json'},
        body: {'r': 'gameid', 'm': normalized}).timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) {
        _log.w('RetroAchievements hash lookup: HTTP ${response.statusCode}');
        return null;
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map || decoded['Success'] != true || decoded['GameID'] is! num) return null;
      final gameId = (decoded['GameID'] as num).toInt();
      if (gameId < 0) return null;
      try {
        await store.saveLookup(normalized, gameId, now);
      } catch (error) {
        _log.w('RetroAchievements hash cache not saved: $error');
      }
      return gameId;
    } catch (error) {
      // Offline or unreachable: not cached, asked again next time.
      _log.w('RetroAchievements hash lookup failed: ${error.runtimeType}');
      return null;
    } finally {
      if (clientOverride == null) client.close();
    }
  }
}
