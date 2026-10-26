import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as path;
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

import 'logger_service.dart';
import 'rpcs3_disc_image.dart';
import 'rpcs3_internal_service.dart';
import 'rpcs3_library_file_deletion.dart';
import 'rpcs3_launch_service.dart';
import 'rpcs3_library_service.dart';
import 'storage/storage_import_activity.dart';

/// Why a library-folder disc image could not be made launchable.
enum Rpcs3LibraryFileFailure {
  firmwareMissing,
  notEnoughSpace,
  discKeyRequired,
  corruptImage,
  unidentified,
  installFailed,
}

/// A disc image RPCS3 has to install before its first launch: what the
/// launcher shows before copying it.
class Rpcs3LibraryFilePlan {
  const Rpcs3LibraryFilePlan({
    required this.romPath,
    required this.sizeBytes,
    this.identity,
    this.keyPath,
  });

  final String romPath;
  final int sizeBytes;

  /// PARAM.SFO read in place; null when the image did not let it be read.
  final Rpcs3DiscIdentity? identity;

  /// The `.dkey` or `.key` beside the image, if any.
  final String? keyPath;

  String get fileName => path.basename(romPath);
}

class Rpcs3LibraryFileOutcome {
  const Rpcs3LibraryFileOutcome.ready(
    String this.titleId, {
    this.installed = false,
  }) : plan = null,
       failure = null,
       details = '';

  const Rpcs3LibraryFileOutcome.install(Rpcs3LibraryFilePlan this.plan)
    : titleId = null,
      installed = false,
      failure = null,
      details = '';

  const Rpcs3LibraryFileOutcome.failed(
    Rpcs3LibraryFileFailure this.failure,
    this.details,
  ) : titleId = null,
      installed = false,
      plan = null;

  /// The RPCS3 title to boot; set when the row is linked and ready.
  final String? titleId;

  /// True when this launch copied the disc into RPCS3.
  final bool installed;

  /// Set when RPCS3 does not hold the disc yet: ask, then [Rpcs3LibraryFileService.install].
  final Rpcs3LibraryFilePlan? plan;

  final Rpcs3LibraryFileFailure? failure;

  /// Technical detail (RPCS3's own message), kept for the failure dialog and the log.
  final String details;

  bool get ready => titleId != null;
}

/// Build 554: PS3 disc images found by the library scan (`roms/ps3/*.iso`).
///
/// RPCS3 boots only titles installed in its private library, and on iOS a
/// PS3 row used to reach RPCS3 only when it carried a title ID, which a
/// scanned file never has: the launch fell through to the RetroArch route,
/// which runs no PS3 game ("No persisted RetroArch export is available").
/// Now such a row is resolved here first. A disc RPCS3 already holds (same
/// title ID, or the same image when the title ID cannot be read) is linked
/// at once; otherwise the launcher asks, then RPCS3 installs the image with
/// its own validated import (a copy: the file stays in the folder unless
/// the user chose to free its space, Build 557), and the row is linked to
/// the installed title.
abstract final class Rpcs3LibraryFileService {
  static final LoggerService _log = LoggerService.instance;

  @visibleForTesting
  static Future<bool> Function() firmwareInstalled =
      Rpcs3InternalService.hasFirmware;

  @visibleForTesting
  static Future<List<Rpcs3LibraryGame>> Function() installedGames =
      Rpcs3LibraryService.installedGames;

  @visibleForTesting
  static Future<void> Function() prepareRuntime =
      Rpcs3InternalService.ensureManagementInitialized;

  @visibleForTesting
  static Future<Map<String, dynamic>> Function(String isoPath, String? keyPath)
  installImage = _installImage;

  @visibleForTesting
  static Future<void> Function(String romPath, String titleId) linkRow =
      Rpcs3LibraryService.linkLibraryFile;

  @visibleForTesting
  static Future<void> Function() syncLibrary = _syncLibrary;

  @visibleForTesting
  static Future<bool> Function(String romPath, String? keyPath)
  removeOriginalFiles = Rpcs3LibraryFileDeletion.removeOriginal;

  @visibleForTesting
  static void resetForTesting() {
    firmwareInstalled = Rpcs3InternalService.hasFirmware;
    installedGames = Rpcs3LibraryService.installedGames;
    prepareRuntime = Rpcs3InternalService.ensureManagementInitialized;
    installImage = _installImage;
    linkRow = Rpcs3LibraryService.linkLibraryFile;
    syncLibrary = _syncLibrary;
    removeOriginalFiles = Rpcs3LibraryFileDeletion.removeOriginal;
  }

  static Future<Map<String, dynamic>> _installImage(
    String isoPath,
    String? keyPath,
  ) => Rpcs3InternalBridge.installIso(isoPath, keyPath: keyPath);

  static Future<void> _syncLibrary() async {
    await Rpcs3LibraryService.syncInternalLibrary();
  }

  /// Whether the row of [romPath] must be resolved here before launching:
  /// a disc image of the library folder whose [titleId] RPCS3 does not hold
  /// (no title ID yet, or a title since removed from RPCS3).
  static bool needsResolution(String? romPath, String? titleId) {
    if (romPath == null ||
        Rpcs3LibraryService.isVirtualLibraryPath(romPath) ||
        !Rpcs3DiscImage.isDiscImagePath(romPath)) {
      return false;
    }
    final id = Rpcs3LaunchService.normalizeTitleId(titleId);
    return id == null || Rpcs3LibraryService.cachedGameForTitleId(id) == null;
  }

  /// Links [romPath] to the RPCS3 title holding the same disc, or returns
  /// the plan of its installation.
  static Future<Rpcs3LibraryFileOutcome> resolve(String romPath) async {
    final name = path.basename(romPath);
    if (!await firmwareInstalled()) {
      _log.w('RPCS3 library file: $name needs the PS3 firmware first.');
      return const Rpcs3LibraryFileOutcome.failed(
        Rpcs3LibraryFileFailure.firmwareMissing,
        'PS3 firmware not installed',
      );
    }
    final identity = await Rpcs3DiscImage.readIdentity(romPath);
    final held = await _installedCopy(
      romPath,
      identity,
      await installedGames(),
    );
    if (held != null) {
      await linkRow(romPath, held);
      await syncLibrary();
      _log.i(
        'RPCS3 library file: $name is already installed as $held; '
        'row linked.',
      );
      return Rpcs3LibraryFileOutcome.ready(held);
    }
    final keyPath = await Rpcs3DiscImage.findDiscKey(romPath);
    final size = await File(romPath).length();
    _log.i(
      'RPCS3 library file: $name needs installation '
      '(titleId=${identity?.titleId ?? 'unreadable'} '
      'category=${identity?.category ?? '-'} size=$size '
      'discKey=${keyPath == null ? 'none' : path.basename(keyPath)}).',
    );
    return Rpcs3LibraryFileOutcome.install(
      Rpcs3LibraryFilePlan(
        romPath: romPath,
        sizeBytes: size,
        identity: identity,
        keyPath: keyPath,
      ),
    );
  }

  static Future<String?> _installedCopy(
    String romPath,
    Rpcs3DiscIdentity? identity,
    List<Rpcs3LibraryGame> installed,
  ) async {
    if (identity != null) {
      for (final game in installed) {
        if (game.titleId.toUpperCase() == identity.titleId) {
          return identity.titleId;
        }
      }
      return null;
    }
    for (final game in installed) {
      final disc = _installedDiscImage(game);
      if (disc != null && await Rpcs3DiscImage.sameImage(romPath, disc)) {
        return game.titleId.toUpperCase();
      }
    }
    return null;
  }

  /// `DiscImages/<TITLE_ID>/disc.iso`, where RPCS3 keeps an installed disc.
  static String? _installedDiscImage(Rpcs3LibraryGame game) {
    if (game.sourceKind != 'disc-image' &&
        game.sourceKind != 'disc-image-folder') {
      return null;
    }
    if (Rpcs3DiscImage.isDiscImagePath(game.sourcePath)) return game.sourcePath;
    return path.join(game.sourcePath, 'disc.iso');
  }

  /// Copies the disc of [plan] into RPCS3's library with RPCS3's own
  /// validated import, links its row and returns the installed title. With
  /// [removeOriginal] (Build 557), the original file and its disc key are
  /// deleted once RPCS3 holds the title: its row stays, linked, and
  /// launches by title ID; a refused deletion leaves them in place.
  static Future<Rpcs3LibraryFileOutcome> install(
    Rpcs3LibraryFilePlan plan, {
    bool removeOriginal = false,
  }) => StorageImportActivity.run(() async {
    final name = plan.fileName;
    final watch = Stopwatch()..start();
    final started = DateTime.now();
    final before = <String>{
      for (final game in await installedGames()) game.titleId.toUpperCase(),
    };
    _log.i(
      'RPCS3 library file: installing $name '
      '(discKey=${plan.keyPath == null ? 'none' : path.basename(plan.keyPath!)}).',
    );
    Map<String, dynamic> report;
    try {
      await prepareRuntime();
      report = await installImage(plan.romPath, plan.keyPath);
    } on Rpcs3InternalException catch (error) {
      _log.e(
        'RPCS3 library file: RPCS3 could not start for $name: ${error.message}',
      );
      return Rpcs3LibraryFileOutcome.failed(
        Rpcs3LibraryFileFailure.installFailed,
        error.message,
      );
    }
    if (report['success'] != true) {
      final message = report['message']?.toString().trim();
      final details = message == null || message.isEmpty
          ? 'RPCS3 import failed.'
          : message;
      _log.e('RPCS3 library file: installation of $name failed: $details');
      return Rpcs3LibraryFileOutcome.failed(classify(details), details);
    }

    final after = await installedGames();
    String? titleId = plan.identity?.titleId;
    if (titleId == null ||
        !after.any((game) => game.titleId.toUpperCase() == titleId)) {
      titleId = await _installedTitle(after, before, started);
    }
    if (titleId == null) {
      await syncLibrary();
      _log.e(
        'RPCS3 library file: $name was installed but its title could not '
        'be identified; it is listed by RPCS3 itself.',
      );
      return const Rpcs3LibraryFileOutcome.failed(
        Rpcs3LibraryFileFailure.unidentified,
        'Installed title not identified',
      );
    }
    await linkRow(plan.romPath, titleId);
    await syncLibrary();
    _log.i(
      'RPCS3 library file: installed $name as $titleId in '
      '${watch.elapsedMilliseconds} ms; row linked.',
    );
    if (removeOriginal) await removeOriginalFiles(plan.romPath, plan.keyPath);
    return Rpcs3LibraryFileOutcome.ready(titleId, installed: true);
  });

  /// The title this installation added: the only new title ID, else the
  /// only disc folder written since [started] (a reinstalled title).
  static Future<String?> _installedTitle(
    List<Rpcs3LibraryGame> after,
    Set<String> before,
    DateTime started,
  ) async {
    final added = <String>{
      for (final game in after)
        if (!before.contains(game.titleId.toUpperCase()))
          game.titleId.toUpperCase(),
    };
    if (added.length == 1) return added.single;
    if (added.isNotEmpty) return null;
    final written = <String>{};
    final since = started.subtract(const Duration(seconds: 2));
    for (final game in after) {
      if (_installedDiscImage(game) == null) continue;
      try {
        final stat = await FileStat.stat(game.sourcePath);
        if (stat.type != FileSystemEntityType.notFound &&
            !stat.modified.isBefore(since)) {
          written.add(game.titleId.toUpperCase());
        }
      } on FileSystemException {
        continue;
      }
    }
    return written.length == 1 ? written.single : null;
  }

  /// Maps RPCS3's own failure message (English, kept as the technical
  /// detail) to what the user is told.
  @visibleForTesting
  static Rpcs3LibraryFileFailure classify(String message) {
    final text = message.toLowerCase();
    if (text.contains('not enough free space')) {
      return Rpcs3LibraryFileFailure.notEnoughSpace;
    }
    if (text.contains('.dkey') || text.contains('disc key')) {
      return Rpcs3LibraryFileFailure.discKeyRequired;
    }
    if (text.contains('truncated or corrupt') ||
        text.contains('incomplete or corrupt') ||
        text.contains('unterminated iso descriptor') ||
        text.contains('not a valid iso 9660')) {
      return Rpcs3LibraryFileFailure.corruptImage;
    }
    return Rpcs3LibraryFileFailure.installFailed;
  }
}
