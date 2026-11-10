import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as path;

import '../data/datasources/sqlite_service.dart';
import 'game_file_deletion.dart';
import 'logger_service.dart';
import 'rpcs3_disc_image.dart';
import 'rpcs3_internal_service.dart';

/// Build 557: deletion of the PS3 disc images of the library folder
/// (`roms/ps3/*.iso`) and of RPCS3's copy of them.
///
/// RPCS3 boots a library-folder disc from the copy it installed (Build 554),
/// so such a game is two things on disk: the file in the folder and the
/// installation in RPCS3's private library. Deleting the game removes both;
/// freeing space after an installation removes only the file.
abstract final class Rpcs3LibraryFileDeletion {
  static final LoggerService _log = LoggerService.instance;

  /// Title IDs RPCS3's installation deletion accepts (`Rpcs3GameDeletion`).
  static final RegExp _installedTitle = RegExp(r'^[A-Z]{4}[0-9]{5}$');

  @visibleForTesting
  static Future<void> Function(String target) deleteFile =
      GameFileDeletion.delete;

  @visibleForTesting
  static Future<void> Function(String titleId) deleteInstalledTitle =
      Rpcs3InternalService.deleteInstalledGame;

  @visibleForTesting
  static void resetForTesting() {
    deleteFile = GameFileDeletion.delete;
    deleteInstalledTitle = Rpcs3InternalService.deleteInstalledGame;
  }

  /// Deletes the game of the PS3 row [romPath]: its disc image first (a
  /// refused deletion leaves everything in place), its disc key, then, for
  /// a row linked to an RPCS3 title, that installation with every row of
  /// its title (RPCS3 keeps save data, firmware and savestates), and the
  /// row. Returns whether the scraped media of [filename] may go too, as
  /// [SqliteService.deleteGame] does.
  static Future<bool> deleteGame({
    required String appSystemId,
    required String filename,
    required String romPath,
  }) async {
    final db = await SqliteService.getDatabase();
    final rows = await db.rawQuery(
      'SELECT title_id FROM user_roms WHERE app_system_id = ? AND rom_path = ?',
      <Object?>[appSystemId, romPath],
    );
    final titleId = rows.isEmpty
        ? ''
        : (rows.first['title_id']?.toString() ?? '').trim().toUpperCase();
    final name = path.basename(romPath);
    await deleteFile(romPath);
    _log.i('RPCS3 library file: deleted $name.');
    await _deleteDiscKey(romPath);
    if (_installedTitle.hasMatch(titleId)) {
      await deleteInstalledTitle(titleId);
      _log.i('RPCS3 library file: deleted the installation of $titleId.');
    }
    return SqliteService.deleteGame(appSystemId, filename, romPath: romPath);
  }

  /// Frees the space of a disc RPCS3 has just installed: deletes the
  /// original [romPath] and its disc key [keyPath]. The row stays, linked to
  /// the installed title, and launches by its title ID. Returns false, with
  /// the file left in place, when the deletion is refused.
  static Future<bool> removeOriginal(String romPath, String? keyPath) async {
    final name = path.basename(romPath);
    try {
      await deleteFile(romPath);
    } catch (error) {
      _log.w('RPCS3 library file: $name kept; its deletion failed: $error');
      return false;
    }
    _log.i('RPCS3 library file: deleted $name after its installation.');
    if (keyPath != null) {
      await _deleteKeyFile(keyPath);
    } else {
      await _deleteDiscKey(romPath);
    }
    return true;
  }

  static Future<void> _deleteDiscKey(String romPath) async {
    final keyPath = await Rpcs3DiscImage.findDiscKey(romPath);
    if (keyPath != null) await _deleteKeyFile(keyPath);
  }

  /// A key left behind is a few bytes: its deletion never undoes the rest.
  static Future<void> _deleteKeyFile(String keyPath) async {
    try {
      await deleteFile(keyPath);
      _log.i('RPCS3 library file: deleted ${path.basename(keyPath)}.');
    } catch (error) {
      _log.w(
        'RPCS3 library file: ${path.basename(keyPath)} kept; its deletion '
        'failed: $error',
      );
    }
  }
}
